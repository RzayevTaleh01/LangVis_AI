import platform as _platform
import subprocess as _subprocess

# ── Nuclear: force CREATE_NO_WINDOW on EVERY subprocess call on Windows ───────
# This patches Popen itself, so no per-file flag is needed anywhere.
if _platform.system() == "Windows":
    _OrigPopen = _subprocess.Popen

    class _Popen(_OrigPopen):
        def __init__(self, args, **kw):
            kw["creationflags"] = kw.get("creationflags", 0) | _subprocess.CREATE_NO_WINDOW
            kw.pop("startupinfo", None)   # drop any stale/shared STARTUPINFO
            super().__init__(args, **kw)

    _subprocess.Popen = _Popen

# ── Console encoding ─────────────────────────────────────────────────────────
# Status lines carry emoji and arrows. On a non-UTF-8 console — cp1254 on a
# Turkish Windows, cp1251 on a Russian one — printing one raises
# UnicodeEncodeError, and because the print sits after a tool's own try/except
# the exception escapes into the receive loop and takes the session down.
import sys as _sys
for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Watch our own output ─────────────────────────────────────────────────────
# Installed before anything can print, so no traceback escapes unrecorded.
# Wrapped deliberately: logging must never be what stops the app from starting.
try:
    from core import selflog as _selflog
    _selflog.install()
except Exception as _e:                                  # pragma: no cover
    print(f"[SelfLog] disabled: {_e}")

import asyncio
import json
import re
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd
from google import genai
from google.genai import types

from core import audio_devices
from core.plugin_loader import discover_plugins
from core.wake_word import (
    WakeWordDetector, WAKE_PHRASE, install_and_download as wake_install,
    is_ready as wake_is_ready,
)
from memory.config_manager import (
    get_input_device, get_output_device, get_voice, get_wake_word_enabled,
    save_wake_word_enabled,
)
from memory.memory_manager import (
    format_memory_for_prompt, load_memory, pop_last_session, save_session_summary,
    search_memory, set_trim_notifier, update_memory,
)
from ui import LangVisUI

# How long the tutor stays awake with no speech before it sleeps again
# (wake-word mode only).
WAKE_SLEEP_TIMEOUT = 300.0   # seconds — a lesson has long silences while thinking


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
LIVE_MODEL          = "models/gemini-3.1-flash-live-preview"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024

# RMS below which 16-bit PCM is treated as room silence; above _LEVEL_FULL it
# reads as a full-height waveform.
_LEVEL_FLOOR = 60.0
_LEVEL_FULL  = 2600.0


def _pcm_level(samples) -> float:
    """Map a block of int16 PCM samples to a 0.0–1.0 loudness level for the HUD
    waveform. Returns 0.0 on empty/invalid input so it can never raise."""
    try:
        x = np.asarray(samples, dtype=np.float32)
        if x.size == 0:
            return 0.0
        rms = float(np.sqrt(np.mean(x * x)))
    except Exception:
        return 0.0
    if rms <= _LEVEL_FLOOR:
        return 0.0
    return min(1.0, (rms - _LEVEL_FLOOR) / (_LEVEL_FULL - _LEVEL_FLOOR))


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return ("You are a personal language tutor. Teach the learner to speak, "
                "correct their mistakes gently, and keep them talking.")


_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)


def _clean_transcript(text: str) -> str:
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()


# Closing quotes and brackets can trail a question mark.
_QUESTION_END_RE = re.compile(r"[?？؟]\s*[\"'»”’\)\]]*\s*$")

# A tutor does not only hand the floor over with questions. "Say it." "Now you
# try." "Repeat that, please." all mean the same thing: the next voice in the
# room is supposed to be the learner's. Anything injected into that silence —
# an analyser note, a milestone — is read by the model as the learner's reply,
# and it answers itself: it praises a sentence nobody said, or wraps the lesson
# up mid-drill. So the floor is treated as the learner's after any of these.
_FLOOR_CUES = (
    "say it", "say that", "say this", "now you", "you say", "repeat",
    "your turn", "try again", "try it", "tell me", "go ahead", "one more time",
)


def _holds_floor(text: str) -> bool:
    """True if the tutor's turn was waiting for the learner to speak."""
    low = (text or "").lower()
    if _QUESTION_END_RE.search(text or ""):
        return True
    tail = low[-160:]          # the hand-over is at the end of the turn
    return any(cue in tail for cue in _FLOOR_CUES)


TOOL_DECLARATIONS = [
    {
        "name": "shutdown_langvis",
        "description": (
            "Ends the lesson and closes the program. Call this ONLY when the "
            "learner clearly wants to finish: 'close the app', 'shut yourself "
            "down', 'that's enough for today, goodbye'. They may say it in any "
            "language. Say the short wrap-up FIRST (one thing they did well, one "
            "to practise), then call this."
        ),
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "save_memory",
        "description": (
            "Save a personal fact about the learner so lessons can use it: name, "
            "job, city, family, hobbies, interests, plans, why they are learning "
            "the language. Call it silently — never announce it. Do NOT save "
            "their grammar mistakes or their level; the tutor plugin tracks those. "
            "Values must be in English."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity — name, age, city, job, native language | "
                        "preferences — likes, hobbies, favourite things | "
                        "projects — work, studies, what they are building | "
                        "relationships — family, friends, colleagues | "
                        "wishes — goals, plans, dreams | notes — anything else"
                    ),
                },
                "key":   {"type": "STRING", "description": "Short snake_case key (e.g. job, favourite_food)"},
                "value": {"type": "STRING", "description": "Concise value in English"},
            },
            "required": ["category", "key", "value"],
        },
    },
    {
        "name": "recall_memory",
        "description": (
            "Look up something you were told about the learner but cannot see in "
            "your memory block (the keys listed under [ALSO REMEMBERED]). Call it "
            "before saying you do not remember. Leave the query empty to list "
            "everything. Instant local search."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING",
                          "description": "A name, topic or category to search for."},
            },
            "required": [],
        },
    },
]


class _ReconnectSignal(Exception):
    """Raised inside the session TaskGroup to force a clean, voluntary reconnect
    (e.g. the learner picked a new voice — the voice is fixed at connect time,
    so the session must be rebuilt).

    Carries `keep_context`: True for an ordinary rebuild, where the stored
    resumption handle is replayed and the lesson continues; False when the new
    session must genuinely start clean."""

    def __init__(self, keep_context: bool = True):
        super().__init__()
        self.keep_context = keep_context


def _is_reconnect_signal(exc: BaseException) -> bool:
    if isinstance(exc, _ReconnectSignal):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return any(_is_reconnect_signal(sub) for sub in exc.exceptions)
    return False


def _keep_context_of(exc: BaseException) -> bool:
    """Read `keep_context` off a reconnect signal, unwrapping the group the
    TaskGroup put it in. Defaults to True: an unexpected shape must not
    silently wipe the lesson."""
    if isinstance(exc, _ReconnectSignal):
        return getattr(exc, "keep_context", True)
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            if _is_reconnect_signal(sub):
                return _keep_context_of(sub)
    return True


class LangVisLive:
    def __init__(self, ui: LangVisUI):
        self.ui                = ui
        self._asst_name        = "LangVis"    # updated each session from config
        self.session           = None
        self.audio_in_queue    = None
        self.out_queue         = None
        self._loop             = None
        self._is_speaking      = False
        self._speaking_lock    = threading.Lock()
        self._interrupted      = False   # True while draining audio after an interrupt
        self.ui.on_text_command        = self._on_text_command
        self.ui.on_interrupt           = self.interrupt
        self.ui.on_voice_change        = self._on_voice_change
        self.ui.on_audio_device_change = self._on_audio_device_change
        self._reconnect_event: asyncio.Event | None = None
        self._reconnect_keep = True   # False → next rebuild drops the resumption handle

        # ── Session resumption ───────────────────────────────────────────────
        # The server issues a handle every few seconds. Keeping it means a
        # dropped packet or a device change does not restart the lesson from
        # nothing. Deliberately in RAM only: a fresh launch should begin a new
        # lesson, which is also what produces the end-of-session summary.
        self._resume_handle: str | None = None
        self._turn_done_event: asyncio.Event | None = None
        self._lesson_started   = False   # the opening of the lesson fires once per launch
        self._last_user_speech = time.monotonic()
        self._awaiting_answer  = False   # the floor belongs to the learner
        self._session_log: list[str] = []          # turns, for the end-of-session summary

        self._enhanced_live = True  # proactive audio; auto-disabled if the server rejects it

        _base_dir = Path(__file__).resolve().parent
        _core_names = {t["name"] for t in TOOL_DECLARATIONS}
        self._plugin_registry = discover_plugins(
            plugins_dir=_base_dir / "plugins",
            core_tool_names=_core_names,
            logger=lambda msg: print(f"[Plugins] {msg}"),
        )
        self.ui.get_plugin_settings = self._plugin_registry.settings_schemas  # ⚙ settings
        self.ui.request_say         = self.plugin_say
        self.ui.request_say_when_idle = self.plugin_say_when_idle
        self.ui.get_lesson_status   = self._lesson_status   # header, unit strip, chips
        self.ui.get_syllabus        = self._syllabus        # the course list
        self.ui.on_language_change  = self._on_language_change
        self.ui.get_coaching        = self._coaching

        # ── Wake word ────────────────────────────────────────────────────────
        # _awake gates the mic. It is True whenever wake word is OFF.
        self._wake_enabled       = get_wake_word_enabled()
        self._awake              = not self._wake_enabled
        self._wake_detector: WakeWordDetector | None = None
        self._wake_sleep_timeout = WAKE_SLEEP_TIMEOUT
        self.ui.wake_is_ready    = wake_is_ready
        self.ui.wake_get_state   = self._wake_state
        self.ui.on_wake_toggle   = self._ui_wake_toggle
        self.ui.on_wake_manual   = self._ui_wake_manual
        self.ui.on_wake_install  = self._ui_wake_install

    # ── Wake word: state machine ─────────────────────────────────────────────

    def _wake_state(self) -> dict:
        ready = bool(self._wake_detector and self._wake_detector.ready) or wake_is_ready()
        return {"enabled": self._wake_enabled, "awake": self._awake, "ready": ready}

    def _ensure_wake_detector(self) -> bool:
        if self._wake_detector is None:
            self._wake_detector = WakeWordDetector(
                on_detect=self._on_wake_detected,
                logger=lambda m: (print(f"[Wake] {m}"), self.ui.write_log(f"SYS: {m}")),
            )
        if not self._wake_detector.ready:
            return self._wake_detector.start()
        return True

    def _on_wake_detected(self) -> None:
        self.wake(reason="wake word")

    def wake(self, reason: str = "wake word") -> None:
        if self._awake:
            return
        self._awake = True
        self._last_user_speech = time.monotonic()
        if not self.ui.muted:
            self.ui.set_state("LISTENING")
        self.ui.write_log(f"SYS: Awake — {reason}.")

    def sleep(self, reason: str = "timeout") -> None:
        if not self._awake:
            return
        self._awake = False
        self.set_speaking(False)
        self.ui.set_state("SLEEPING")
        self.ui.write_log(f"SYS: Sleeping — {reason}. Say '{WAKE_PHRASE}' to wake me.")

    async def _run_sleep_watch(self) -> None:
        """Auto-sleep after the configured silence window (wake-word mode only)."""
        while True:
            await asyncio.sleep(5)
            if not self._wake_enabled or not self._awake:
                continue
            with self._speaking_lock:
                speaking = self._is_speaking
            if speaking:
                continue
            if (time.monotonic() - self._last_user_speech) > self._wake_sleep_timeout:
                self.sleep(reason="no speech for a while")

    # ── Wake word: UI callbacks (called from the Qt thread) ──────────────────

    def _ui_wake_toggle(self, enable: bool) -> str:
        """Returns a status token: 'enabled' | 'disabled' | 'need_download'."""
        if enable:
            if not wake_is_ready():
                return "need_download"
            self._wake_enabled = True
            save_wake_word_enabled(True)
            self._ensure_wake_detector()
            self.sleep(reason="wake word enabled")
            return "enabled"
        self._wake_enabled = False
        save_wake_word_enabled(False)
        self.wake(reason="wake word disabled")
        return "disabled"

    def _ui_wake_manual(self) -> None:
        if not self._wake_enabled:
            return
        if self._awake:
            self.sleep(reason="you tapped sleep")
        else:
            self.wake(reason="you tapped wake")

    def _ui_wake_install(self) -> tuple[bool, str]:
        return wake_install(logger=lambda m: self.ui.write_log(f"SYS: {m}"))

    # ── The lesson panel ─────────────────────────────────────────────────────

    def _lesson_status(self) -> dict:
        """Where the learner is, for the HUD panel. Asked of the plugins rather
        than of the tutor by name: a second course plugin only has to expose
        status_for_ui() to appear on screen. Called from the Qt thread once a
        second, so it stays cheap and never raises."""
        for module in list(sys.modules.values()):
            try:
                if not getattr(module, "__name__", "").startswith("plugins."):
                    continue
                getter = getattr(module, "status_for_ui", None)
                if callable(getter):
                    status = getter()
                    if status:
                        return status
            except Exception:
                continue
        return {}

    def _syllabus(self) -> list:
        """The whole course in order, for the syllabus panel. Asked of the
        plugins rather than of the tutor by name, like the status above."""
        for module in list(sys.modules.values()):
            try:
                if not getattr(module, "__name__", "").startswith("plugins."):
                    continue
                getter = getattr(module, "syllabus_for_ui", None)
                if callable(getter):
                    data = getter()
                    if data:
                        return data
            except Exception:
                continue
        return []

    def _coaching(self) -> dict:
        """The correction card for the assistant panel: the sentence just said,
        its fix, the better version and the word checklist. Asked of the
        plugins, like the status and the syllabus."""
        for module in list(sys.modules.values()):
            try:
                if not getattr(module, "__name__", "").startswith("plugins."):
                    continue
                getter = getattr(module, "coaching_for_ui", None)
                if callable(getter):
                    card = getter()
                    if card:
                        return card
            except Exception:
                continue
        return {}

    def _on_language_change(self, name: str) -> None:
        """The learner picked a language in the header select.

        The course decides whether it can be taught at all (Slovak cannot, yet),
        and the session is rebuilt from scratch when it changes: the language is
        baked into the whole system prompt, and carrying over a conversation in
        the old one would have the tutor answer English with Slovak.
        """
        for module in list(sys.modules.values()):
            try:
                if not getattr(module, "__name__", "").startswith("plugins."):
                    continue
                switch = getattr(module, "set_language", None)
                if not callable(switch):
                    continue
                ok, message = switch(name)
                self.ui.write_log(f"SYS: {message}")
                if ok and "Already" not in message:
                    self.request_reconnect(keep_context=False, reason="new language")
                return
            except Exception as e:
                self.ui.write_log(f"ERR: language switch failed — {e}")
                return

    # ── Speech channels for plugins ──────────────────────────────────────────

    def plugin_say(self, instruction: str) -> None:
        """Thread-safe: let a plugin have the tutor say something WHILE its
        run() is still executing. Silently a no-op with no live session."""
        loop = getattr(self, "_loop", None)
        if not loop or not self.session:
            return

        async def _say():
            try:
                await self.session.send_client_content(
                    turns={"role": "user", "parts": [{"text": instruction}]},
                    turn_complete=True,
                )
            except Exception as e:
                print(f"[PluginSay] {e}")

        try:
            asyncio.run_coroutine_threadsafe(_say(), loop)
        except Exception as e:
            print(f"[PluginSay] {e}")

    def plugin_say_when_idle(self, instruction: str,
                             quiet_for: float = 1.2,
                             max_wait: float = 45.0) -> None:
        """Same channel, but it waits for a gap first.

        A correction that lands while the tutor is still speaking — or while the
        learner is trying to repeat a sentence — is an interruption, which is
        the fastest way to make a lesson unbearable. This holds the note until
        nothing is being spoken, nothing is queued, and the learner has been
        quiet briefly. If that moment never comes within max_wait the note is
        dropped: a correction a minute late teaches nothing.
        """
        loop = getattr(self, "_loop", None)
        if not loop or not self.session:
            return

        async def _wait_then_say():
            deadline = time.monotonic() + max_wait
            while time.monotonic() < deadline:
                with self._speaking_lock:
                    speaking = self._is_speaking
                queued = bool(self.audio_in_queue and not self.audio_in_queue.empty())
                quiet = (time.monotonic() - self._last_user_speech) >= quiet_for
                # A turn that ended on a question is holding the floor for the
                # learner — speaking into that silence makes the tutor look like
                # it is answering itself.
                if not speaking and not queued and quiet and not self._awaiting_answer:
                    break
                await asyncio.sleep(0.4)
            else:
                # The learner never got a word in, or they still owe the tutor
                # the sentence it asked for. Dropping the note is right: the
                # mistake is already in their progress file and on the focus
                # list, and speaking into their turn is what makes the tutor
                # answer itself.
                print("[PluginSay] the floor stayed with the learner — note dropped")
                return
            try:
                await self.session.send_client_content(
                    turns={"role": "user", "parts": [{"text": instruction}]},
                    turn_complete=True,
                )
            except Exception as e:
                print(f"[PluginSay] {e}")

        try:
            asyncio.run_coroutine_threadsafe(_wait_then_say(), loop)
        except Exception as e:
            print(f"[PluginSay] {e}")

    # ── Reconnect plumbing ───────────────────────────────────────────────────

    def request_reconnect(self, keep_context: bool = True, reason: str = ""):
        """Thread-safe: ask the run loop to tear down and rebuild the session."""
        loop = getattr(self, "_loop", None)
        ev   = self._reconnect_event
        self._reconnect_keep   = keep_context
        self._reconnect_reason = reason
        if loop and ev is not None:
            loop.call_soon_threadsafe(ev.set)

    def _on_voice_change(self):
        """The voice is baked into the session at connect time, so a rebuild is
        required — and without the resumption handle, since resuming restores
        the server's session state and would appear to ignore the new voice."""
        self.request_reconnect(keep_context=False, reason="new voice")

    def _on_audio_device_change(self):
        """Both audio streams are opened inside the session TaskGroup, so they
        can only be re-opened by rebuilding it — but the lesson is kept."""
        self.request_reconnect(keep_context=True, reason="audio device")

    async def _watch_reconnect(self):
        assert self._reconnect_event is not None
        await self._reconnect_event.wait()
        self._reconnect_event.clear()
        keep   = self._reconnect_keep
        reason = getattr(self, "_reconnect_reason", "") or "settings"
        self.ui.write_log(
            f"SYS: Applying {reason} — reconnecting"
            + ("..." if keep else " (starting a fresh lesson)...")
        )
        raise _ReconnectSignal(keep_context=keep)

    # ── Session I/O ──────────────────────────────────────────────────────────

    def _on_text_command(self, text: str):
        if not self._loop or not self.session:
            return
        if self._wake_enabled and not self._awake:
            self.ui.write_log(f"SYS: I'm asleep — say '{WAKE_PHRASE}' or tap WAKE NOW first.")
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"role": "user", "parts": [{"text": text}]},
                turn_complete=True,
            ),
            self._loop,
        )

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

    def interrupt(self) -> None:
        """Stop the tutor mid-speech: drain queued audio, open the mic now."""
        self._interrupted = True
        q = self.audio_in_queue
        if q:
            drained = 0
            while True:
                try:
                    q.get_nowait()
                    drained += 1
                except Exception:
                    break
            if drained:
                print(f"[LangVis] ✋ Interrupted — {drained} audio chunks discarded")
        self.set_speaking(False)
        if self._turn_done_event:
            self._turn_done_event.clear()
        self.ui.write_log("SYS: Interrupted — listening...")

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"role": "user", "parts": [{"text": text}]},
                turn_complete=True,
            ),
            self._loop,
        )

    def _build_config(self) -> types.LiveConnectConfig:
        try:
            _cfg = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
            self._asst_name = (_cfg.get("assistant_name") or "LangVis").strip()
            _user_name = (_cfg.get("user_name") or "").strip()
        except Exception:
            self._asst_name = "LangVis"
            _user_name = ""

        mem_str    = format_memory_for_prompt(load_memory())
        sys_prompt = _load_system_prompt()

        now      = datetime.now()
        time_ctx = (f"[CURRENT DATE & TIME]\nRight now it is: "
                    f"{now.strftime('%A, %B %d, %Y — %I:%M %p')}\n\n")
        identity_ctx = (
            f"[IDENTITY]\nYour name is {self._asst_name}. Always refer to yourself as "
            f"{self._asst_name}.\n"
            + (f"Call the learner '{_user_name}'.\n\n" if _user_name
               else "Use the learner's first name if you know it.\n\n")
        )

        parts = [time_ctx, identity_ctx]
        if mem_str:
            parts.append(mem_str)
        # The course itself: level, current unit, focus skills, how to speak.
        parts.extend(self._plugin_registry.prompt_blocks())
        parts.append(sys_prompt)

        cfg = dict(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": (
                TOOL_DECLARATIONS + self._plugin_registry.get_tool_declarations()
            )}],
            session_resumption=types.SessionResumptionConfig(handle=self._resume_handle),
            # Sliding-window compression: a lesson can run for hours without the
            # session dying from a full context window.
            context_window_compression=types.ContextWindowCompressionConfig(
                sliding_window=types.SlidingWindow(),
            ),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=get_voice())
                )
            ),
        )
        if self._enhanced_live:
            # Proactive audio: the tutor stays silent when speech is not
            # addressed to it (someone else in the room).
            cfg["proactivity"] = types.ProactivityConfig(proactive_audio=True)
        return types.LiveConnectConfig(**cfg)

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        print(f"[LangVis] 🔧 {name}  {args}")
        self.ui.set_state("THINKING")

        if name == "save_memory":
            key   = args.get("key", "")
            value = args.get("value", "")
            if key and value:
                update_memory({args.get("category", "notes"): {key: {"value": value}}})
                print(f"[Memory] 💾 {key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(id=fc.id, name=name,
                                          response={"result": "ok", "silent": True})

        loop   = asyncio.get_event_loop()
        result = "Done."
        try:
            if name == "recall_memory":
                # Local dictionary scan over a few hundred short strings — a
                # thread hop would cost more than the work.
                result = search_memory(args.get("query", ""), limit=8)

            elif name == "shutdown_langvis":
                self.ui.write_log("SYS: Shutdown requested.")

                async def _do_shutdown():
                    await self._save_session_summary()
                    if self.session:
                        try:
                            await self.session.send_client_content(
                                turns={"role": "user", "parts": [{"text":
                                    "Say a short, warm goodbye in the language you are "
                                    "teaching, at the learner's level."}]},
                                turn_complete=True,
                            )
                        except Exception:
                            pass
                    await asyncio.sleep(2.0)
                    import os as _os
                    _os._exit(0)

                asyncio.create_task(_do_shutdown())

            elif self._plugin_registry.has(name):
                r = await loop.run_in_executor(
                    None,
                    lambda: self._plugin_registry.run(name, args, player=self.ui,
                                                      session_memory=None),
                )
                result = r or "Done."
            else:
                result = f"Unknown tool: {name}"
        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.ui.write_log(f"ERR: {name} — {str(e)[:120]}")

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        _echo = " ".join(str(result).split())[:80]
        print(f"[LangVis] 📤 {name} → {_echo}")
        return types.FunctionResponse(id=fc.id, name=name, response={"result": result})

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            # Gemini 3.x Live rejects the old realtime_input.media_chunks field
            # (what `media=...` maps to) and closes the socket with a 1007.
            await self.session.send_realtime_input(
                audio=types.Blob(data=msg["data"],
                                 mime_type=msg.get("mime_type", "audio/pcm"))
            )

    async def _listen_audio(self):
        print("[LangVis] 🎤 Mic started")
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            # While asleep, mic audio NEVER goes to Gemini — frames are handed
            # to the local detector, which runs its model in its own thread.
            if self._wake_enabled and not self._awake:
                det = self._wake_detector
                if det is not None:
                    det.feed(indata)
                return
            with self._speaking_lock:
                langvis_speaking = self._is_speaking
            if not langvis_speaking and not self.ui.muted:
                loop.call_soon_threadsafe(
                    self.out_queue.put_nowait,
                    {"data": indata.tobytes(), "mime_type": "audio/pcm"},
                )
                try:
                    self.ui.set_audio_level(_pcm_level(indata))
                except Exception:
                    pass

        try:
            def _open_mic(dev):
                return sd.InputStream(
                    samplerate=SEND_SAMPLE_RATE, channels=CHANNELS, dtype="int16",
                    blocksize=CHUNK_SIZE, device=dev, callback=callback,
                )

            # resolve() returns None for "system default" and for a saved device
            # that is no longer present, so a headset unplugged since the last
            # run falls back to the built-in mic instead of raising on startup.
            _mic_name = get_input_device()
            _mic_dev  = audio_devices.resolve(_mic_name, "input")
            if _mic_dev is not None:
                print(f"[LangVis] 🎤 Input device: {_mic_name}")
            try:
                _mic_stream = _open_mic(_mic_dev)
            except Exception as _e:
                if _mic_dev is None:
                    raise
                print(f"[LangVis] ⚠️  Mic '{_mic_name}' failed: {_e} — using default")
                self.ui.write_log(
                    f"SYS: Microphone '{_mic_name}' unavailable — using system default.")
                _mic_stream = _open_mic(None)

            with _mic_stream:
                print("[LangVis] 🎤 Mic stream open")
                while True:
                    await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[LangVis] ❌ Mic: {e}")
            raise

    async def _receive_audio(self):
        print("[LangVis] 👂 Recv started")
        out_buf, in_buf = [], []
        try:
            while True:
                async for response in self.session.receive():

                    # ── Session resumption ───────────────────────────────────
                    # `resumable` goes false while a turn is mid-flight —
                    # replaying a handle from that moment is what the flag
                    # exists to prevent — so only resumable handles are kept.
                    _sru = getattr(response, "session_resumption_update", None)
                    if _sru is not None:
                        if getattr(_sru, "resumable", False) and getattr(_sru, "new_handle", None):
                            if self._resume_handle is None:
                                print("[LangVis] 🔗 Session resumption armed")
                            self._resume_handle = _sru.new_handle

                    # GoAway: the server is about to close the socket. Leaving on
                    # our own terms (the handle is already armed) is what keeps a
                    # forced disconnect from surfacing as a dead session.
                    if response.go_away is not None:
                        _left = getattr(response.go_away, "time_left", None)
                        print(f"[LangVis] ⚠️  Server GoAway (time_left={_left}) — reconnecting")
                        self.request_reconnect(keep_context=True,
                                               reason="server session limit")

                    if response.data:
                        if not self._interrupted:
                            if self._turn_done_event and self._turn_done_event.is_set():
                                self._turn_done_event.clear()
                            # ~50 ms slices so interrupt() stops audio quickly
                            # (24000 Hz × 2 bytes × 0.05 s = 2400 bytes).
                            _audio = response.data
                            for _i in range(0, len(_audio), 2400):
                                self.audio_in_queue.put_nowait(_audio[_i:_i + 2400])

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt and txt != (out_buf[-1] if out_buf else ""):
                                out_buf.append(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                in_buf.append(txt)
                                self._last_user_speech = time.monotonic()
                                self._awaiting_answer = False

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            if self._interrupted:
                                self._interrupted = False
                                in_buf, out_buf = [], []
                                continue

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self.ui.write_log(f"You: {full_in}")
                                self._session_log.append(f"Learner: {full_in}")
                                # The tutor's analyser. It queues and returns;
                                # nothing here waits on it.
                                self._plugin_registry.observe(full_in, player=self.ui)
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                # A turn ending on a question holds the floor for
                                # the learner — see plugin_say_when_idle.
                                self._awaiting_answer = _holds_floor(full_out)
                                self.ui.write_log(f"{self._asst_name}: {full_out}")
                                self._session_log.append(f"{self._asst_name}: {full_out}")
                            out_buf = []

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            print(f"[LangVis] 📞 {fc.name}")
                            fn_responses.append(await self._execute_tool(fc))
                        await self.session.send_tool_response(function_responses=fn_responses)
        except Exception as e:
            print(f"[LangVis] ❌ Recv: {e}")
            traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[LangVis] 🔊 Play started")

        _spk_name = get_output_device()
        _spk_dev  = audio_devices.resolve(_spk_name, "output")
        if _spk_dev is not None:
            print(f"[LangVis] 🔊 Output device: {_spk_name}")

        def _open_spk(dev):
            st = sd.RawOutputStream(
                samplerate=RECEIVE_SAMPLE_RATE, channels=CHANNELS, dtype="int16",
                blocksize=CHUNK_SIZE, device=dev,
            )
            st.start()
            return st

        try:
            stream = _open_spk(_spk_dev)
        except Exception as _e:
            # A chosen output the host API accepts by name but refuses to open
            # must not cost the learner their tutor's voice.
            if _spk_dev is None:
                raise
            print(f"[LangVis] ⚠️  Output '{_spk_name}' failed: {_e} — using default")
            self.ui.write_log(f"SYS: Speaker '{_spk_name}' unavailable — using default.")
            stream = _open_spk(None)

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(self.audio_in_queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    if (self._turn_done_event and self._turn_done_event.is_set()
                            and self.audio_in_queue.empty()):
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                    continue

                self.set_speaking(True)

                # Batch immediately-available chunks into one write, capped at
                # ~200 ms so interrupt() still stops audio quickly.
                batch = bytearray(chunk)
                while len(batch) < 9600:
                    try:
                        batch.extend(self.audio_in_queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break

                try:
                    self.ui.set_audio_level(
                        _pcm_level(np.frombuffer(bytes(batch), dtype=np.int16)))
                except Exception:
                    pass

                try:
                    await asyncio.to_thread(stream.write, bytes(batch))
                except (RuntimeError, asyncio.CancelledError):
                    break   # executor shutting down — exit cleanly
        except Exception as e:
            print(f"[LangVis] ❌ Play: {e}")
            raise
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()

    # ── Starting the lesson ─────────────────────────────────────────────────

    async def _start_lesson(self) -> None:
        """One message that opens the lesson. Everything it needs — level,
        unit, focus skills, words to reuse — is already in the system prompt,
        so there is no tool round-trip and the tutor starts talking at once."""
        await asyncio.sleep(0.4)
        if not self.session:
            return

        memory   = load_memory()
        identity = memory.get("identity", {})
        entry    = identity.get("name", {})
        name     = (entry.get("value", "") if isinstance(entry, dict) else str(entry)).strip()

        last = await asyncio.to_thread(pop_last_session)
        recap = ""
        if last:
            try:
                days = (datetime.now() - datetime.strptime(last["date"], "%Y-%m-%d")).days
                when = "earlier today" if days == 0 else ("yesterday" if days == 1
                                                          else f"{days} days ago")
            except Exception:
                when = "last time"
            recap = (f" In one short sentence, remind them what you practised {when}: "
                     f"{last['summary']}")

        prompt = (
            "[LESSON_START] Begin today's lesson now, following the [LESSON PLAN] in "
            "your instructions. Greet the learner warmly"
            + (f" by name ({name})" if name else "")
            + " in the language you are teaching, at their level."
            + recap
            + " Then start the warm-up: ONE easy question they can answer. Two or three "
              "short sentences in total. Do not call any tools. Do not read this "
              "instruction aloud and never mention the plan itself."
        )
        await self.session.send_client_content(
            turns={"role": "user", "parts": [{"text": prompt}]}, turn_complete=True)
        self.ui.write_log("SYS: Lesson started.")

    # ── End-of-session summary ──────────────────────────────────────────────

    async def _save_session_summary(self) -> None:
        """One or two sentences about this lesson, for the next one to open on."""
        log = self._session_log
        if len(log) < 3:
            return
        self._session_log = []    # reset now so the next lesson starts clean

        convo = "\n".join(log[-40:])
        prompt = (
            "Below is a language lesson between a tutor and a learner. In ONE or TWO "
            "short English sentences, say what was practised (topic and grammar) and "
            "the main mistake to work on next time. No preamble.\n\n" + convo
        )
        try:
            from google import genai as _genai
            client = _genai.Client(api_key=_get_api_key())
            resp   = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-flash-latest", contents=prompt,
            )
            summary = (getattr(resp, "text", "") or "").strip()
            if summary:
                save_session_summary(summary[:280], "English")
        except Exception as e:
            print(f"[Memory] ⚠️ Lesson summary failed: {e}")

    # ── main loop ───────────────────────────────────────────────────────────

    async def run(self):
        self._loop = asyncio.get_event_loop()
        self._reconnect_event = asyncio.Event()

        set_trim_notifier(self.ui.write_log)

        # Tell the device picker the exact rates the streams open at, from the
        # constants that actually open them.
        audio_devices.configure(SEND_SAMPLE_RATE, RECEIVE_SAMPLE_RATE)
        audio_devices.prefetch()

        while True:
            try:
                print("[LangVis] Connecting...")
                self.ui.set_state("THINKING")
                _resumed_with = self._resume_handle is not None
                config = self._build_config()

                # Fresh client on every reconnect — avoids stale HTTP session
                # state. v1alpha carries proactive audio; if it is rejected we
                # fall back to v1beta.
                client = genai.Client(
                    api_key=_get_api_key(),
                    http_options={"api_version": "v1alpha" if self._enhanced_live else "v1beta"},
                )

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session          = session
                    self.audio_in_queue   = asyncio.Queue()
                    self.out_queue        = asyncio.Queue(maxsize=200)
                    self._turn_done_event = asyncio.Event()
                    self._interrupted     = False

                    print("[LangVis] Connected.")
                    if _resumed_with:
                        self.ui.write_log("SYS: Reconnected — lesson restored.")

                    if self._wake_enabled:
                        self._ensure_wake_detector()
                        self._awake = False
                        self.ui.set_state("SLEEPING")
                        self.ui.write_log(
                            f"SYS: Tutor online — sleeping. Say '{WAKE_PHRASE}' to start.")
                    else:
                        self._awake = True
                        self.ui.set_state("LISTENING")
                        self.ui.write_log("SYS: Tutor online.")

                    self._reconnect_event.clear()  # ignore requests from before this session
                    tg.create_task(self._watch_reconnect())
                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())
                    tg.create_task(self._run_sleep_watch())

                    # The lesson opens once per launch. Skipped in wake-word
                    # mode: it comes up asleep, and greeting while "asleep"
                    # would defeat the point.
                    if not self._lesson_started and self._awake:
                        self._lesson_started = True
                        tg.create_task(self._start_lesson())

            except KeyboardInterrupt:
                raise
            except SystemExit:
                raise
            except BaseException as e:
                # TaskGroup wraps child exceptions in a BaseExceptionGroup,
                # which `except Exception` would miss — letting it escape the
                # loop and start asyncio shutdown mid-lesson.
                if _is_reconnect_signal(e):
                    print("[LangVis] Voluntary reconnect requested.")
                    if not _keep_context_of(e):
                        self._resume_handle = None
                    self._conn_backoff = 0
                    continue

                # A resumption handle the server will not accept — expired, or
                # belonging to a session it has dropped. Without this the dead
                # handle is replayed on every retry and the tutor never returns.
                if _resumed_with and (
                    "resum" in str(e).lower() or "handle" in str(e).lower()
                    or "INVALID_ARGUMENT" in str(e) or "NOT_FOUND" in str(e)
                ):
                    print("[LangVis] 🔗 Resumption handle rejected — fresh session")
                    self.ui.write_log("SYS: Could not restore the lesson — starting fresh.")
                    self._resume_handle = None
                    self._conn_backoff = 0
                    continue

                # The socket closing out from under us — usually a GoAway we did
                # not get ahead of. Expected traffic, not a bug: quiet retry.
                if type(e).__name__ in ("ConnectionClosedError", "ConnectionClosed",
                                        "ConnectionClosedOK"):
                    print(f"[LangVis] 🔌 Connection closed by server ({e}) — reconnecting")
                    self._conn_backoff = 3
                    continue

                err_str = str(e)
                print(f"[LangVis] Error ({type(e).__name__}): {e}")
                traceback.print_exc()

                # Proactive audio rejected by the server (preview API drift).
                if self._enhanced_live and (
                    "INVALID_ARGUMENT" in err_str or "proactiv" in err_str.lower()
                    or "Unknown name" in err_str or "unexpected keyword" in err_str
                ):
                    self._enhanced_live = False
                    self.ui.write_log("SYS: Proactive audio unavailable — reconnecting.")
                    continue

                if "API key not valid" in err_str or "1007" in err_str:
                    self.ui.write_log("ERR: API key invalid — please re-enter your key.")
                    self.ui.set_state("SLEEPING")
                    self.ui.prompt_reconfig()
                    while not self.ui._win._ready:
                        await asyncio.sleep(1)
                    print("[LangVis] New API key saved — reconnecting...")
                    self._conn_backoff = 3
                    continue

                if any(k in err_str for k in (
                    "TimeoutError", "timed out", "getaddrinfo", "CancelledError",
                    "ConnectionRefusedError", "OSError", "Cannot connect",
                )):
                    delay = min(getattr(self, "_conn_backoff", 3) * 2, 60)
                    self._conn_backoff = delay
                    self.ui.write_log(
                        f"NET: Connection failed — retrying in {delay}s. "
                        "(a VPN may be required)")
                else:
                    self._conn_backoff = 3
            finally:
                self.session = None
                if len(self._session_log) >= 3:
                    asyncio.create_task(self._save_session_summary())

            self.set_speaking(False)
            self.ui.set_state("SLEEPING")

            delay = getattr(self, "_conn_backoff", 3)
            print(f"[LangVis] Reconnecting in {delay}s...")
            await asyncio.sleep(delay)


def main():
    ui = LangVisUI("face.png")

    def runner():
        ui.wait_for_api_key()
        langvis = LangVisLive(ui)
        try:
            asyncio.run(langvis.run())
        except KeyboardInterrupt:
            print("\n🔴 Shutting down...")

    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()


if __name__ == "__main__":
    main()
