"""
plugins/language_tutor.py - LangVis as a personal language tutor.

WHAT IT DOES
    LangVis is no longer a desktop assistant: it is a speaking teacher. This
    plugin is the teacher's brain, the live voice session is its mouth.

    1. observe(text) - every sentence the learner speaks is analysed in the
       background: scored on the CEFR scale, each mistake tied to a curriculum
       skill, each correct structure counted as evidence. Sentences said in the
       learner's own language are counted too - the words they were missing
       become vocabulary to recycle.
    2. From that evidence the course moves: a unit passes when its grammar
       skills are strong and enough has been said, a stage passes when the level
       is there. The course itself is grammar only.
    2b. Vocabulary is a live dictionary instead of a list: for every sentence
       the analyser proposes words and phrasal verbs from the learner's own
       topic, and each one ticks off after two uses of their own.
    3. format_for_prompt() - every session starts from a LESSON PLAN: the
       current unit, the learner's weakest skills with their real mistakes,
       reviews that are due, words to reuse, and how simply to speak.
    4. Mid-lesson, the tutor is told when something changes: a unit finished,
       the same mistake made three times (→ short focused drill), a correction
       it may have missed.
    5. run() - the learner can ask: my level, my plan, my weak points, check
       this sentence, give me a drill, next unit, pause corrections.

MODES
    English is active. Slovak exists as a mode but is disabled until its
    curriculum is written (see tutor/curriculum.py).
"""
from __future__ import annotations

import os
import queue
import sys
import threading
import time
from pathlib import Path

from tutor import analysis as an
from tutor import curriculum as cur
from tutor import progress as pg


PLUGIN = {
    "name": "language_tutor",
    "description": (
        "The learner's language course. It measures every sentence by itself - "
        "do NOT call it after every sentence. Call it when the learner ASKS: "
        "'what is my level', 'how am I doing' (action='report'); 'what are we "
        "learning', 'what is today's lesson', or after a [TUTOR_PROGRESS] note "
        "if you need the details (action='plan'); 'what are my mistakes', "
        "'what should I study' (action='weak_points'); 'is this sentence "
        "correct' (action='check' with `text`); 'give me exercises', 'test me' "
        "(action='practice', optional `topic`); 'next unit', 'skip this unit' "
        "(action='next_unit'); 'which words should I learn' (action='words'); "
        "'stop correcting me' (action='pause') / 'correct me again' "
        "(action='resume'); 'my level is A2' (action='set_level' with `level`); "
        "'my goal is B2' (action='set_goal' with `level`); 'switch to Slovak' / "
        "'switch to English' (action='set_mode' with `mode`); 'open my "
        "progress file' (action='open_log')."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": ("report | plan | weak_points | check | practice | "
                                "next_unit | words | pause | resume | set_level | "
                                "set_goal | set_mode | open_log. Default: report."),
            },
            "text": {"type": "STRING",
                     "description": "For check: the sentence to check."},
            "topic": {"type": "STRING",
                      "description": "For practice: a grammar topic they named. "
                                     "Omit to drill their weakest skill."},
            "level": {"type": "STRING",
                      "description": "A CEFR level: A1, A2, B1, B2, C1 or C2."},
            "mode": {"type": "STRING",
                     "description": "For set_mode: english or slovak."},
        },
        "required": [],
    },
}

PLUGIN_SETTINGS = {
    "namespace": "language_tutor",
    "title": "Language tutor",
    "fields": [
        {"key": "mode", "type": "choice", "label": "Language to learn",
         "options": ["English", "Slovak (coming soon)"], "default": "English"},
        {"key": "native_language", "type": "choice", "label": "My own language",
         "options": ["Azerbaijani", "Turkish", "Russian"], "default": "Azerbaijani"},
        {"key": "starting_level", "type": "choice",
         "label": "My level right now (until enough is measured)",
         "options": ["A1", "A2", "B1", "B2"], "default": "A2"},
        {"key": "goal_level", "type": "choice", "label": "Goal",
         "options": ["B1", "B2", "C1"], "default": "B2"},
        {"key": "pace", "type": "choice", "label": "How fast the tutor speaks",
         "options": ["slow", "normal"], "default": "slow"},
        {"key": "strictness", "type": "choice", "label": "How much to correct",
         "options": ["gentle", "normal", "strict"], "default": "normal"},
        {"key": "speak_every", "type": "choice",
         "label": "Second opinion from the analyser (the tutor already corrects you)",
         "options": ["never (log only)", "3min", "1min", "30s", "always"],
         "default": "never (log only)"},
        {"key": "min_words", "type": "choice", "label": "Ignore sentences shorter than",
         "options": ["2", "3", "4", "5"], "default": "3"},
        {"key": "correct_first", "type": "toggle",
         "label": "Correct my sentence BEFORE answering it",
         "default": True},
    ],
}


# ── Settings and paths ───────────────────────────────────────────────────────

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE = _base_dir()
_lock = threading.RLock()

# Values the old english_coach stored are honoured until the learner saves
# new ones — except its C1 goal, which was only a default.
_LEGACY_KEYS = {"starting_level", "pace", "strictness"}


def _setting(key: str, fallback):
    try:
        from memory.config_manager import get_plugin_setting
        value = get_plugin_setting("language_tutor", key)
        if value in (None, "") and key in _LEGACY_KEYS:
            value = get_plugin_setting("english_coach", key)
        if value not in (None, ""):
            return value
    except Exception:
        pass
    return fallback


def _mode_key() -> str:
    wanted = str(_setting("mode", "English")).lower().split()[0]
    lang = cur.LANGUAGES.get(wanted)
    return wanted if lang and lang["enabled"] else cur.DEFAULT_LANGUAGE


def _lang() -> dict:
    return cur.language(_mode_key())


def _native() -> str:
    return str(_setting("native_language", "Azerbaijani"))


def _paths(lang: dict) -> tuple[Path, Path]:
    d = pg.data_dir(BASE, lang)
    return d / "level.json", d / "progress.md"


def _load(lang: dict | None = None) -> dict:
    lang = lang or _lang()
    state = pg.load(_paths(lang)[0])
    if not state.get("declared_level"):
        state["declared_level"] = str(_setting("starting_level", "A2")).upper()
    return state


def _save(state: dict, lang: dict | None = None, render: bool = True) -> None:
    lang = lang or _lang()
    state_path, log_path = _paths(lang)
    pg.save(state_path, state)
    if render:
        try:
            pg.render_log(log_path, state, lang)
        except Exception as e:
            print(f"[Tutor] log render failed: {e}")


def _min_words() -> int:
    try:
        return max(2, int(str(_setting("min_words", 3))))
    except Exception:
        return 3


_THROTTLE = {"always": 0, "30s": 30, "1min": 60, "3min": 180, "never (log only)": -1}


# ── How the tutor speaks and teaches ─────────────────────────────────────────

_SPEECH_RULES = {
    "A1": "Very short sentences, 6 words or fewer. Present simple only. The most common words.",
    "A2": ("Short sentences, about 8 words, one idea each. Present, past and future "
           "simple only. Everyday words. No idioms. Very few phrasal verbs."),
    "B1": ("Sentences of about 12 words, two clauses at most. Present perfect and "
           "simple conditionals are fine. Common phrasal verbs are fine."),
    "B2": ("Normal sentences up to about 18 words. Any common tense, passive, "
           "relative clauses, ordinary idioms. Avoid rare words."),
    "C1": "Speak naturally with precise vocabulary.",
    "C2": "Speak exactly as to a native speaker.",
}


def _speech_level(state: dict, lang: dict) -> str:
    """How simply the tutor must speak: the LOWER of what has been measured and
    the band of the stage they are working through.

    Measuring one sentence at a time flatters a learner - a good sentence scores
    B1 long before they can hold a B1 conversation. The course knows better: it
    is where their grammar has actually been proved. So the input stays at the
    stage's level and rises as the stage does, which is the point of a course
    that runs from A2 to B2.
    """
    measured = pg.effective_level(state)[0]
    stage = pg.position(state, lang).get("stage")
    if not stage:
        return measured
    return min(measured, stage["band"], key=cur.band_index)


def _method_playbook(lang: dict, state: dict) -> str:
    """The techniques, spelled out as instructions.

    A model asked to "teach a lesson" improvises a quiz. Handed the actual
    methods - a substitution drill, a dictogloss, 4/3/2, an information gap -
    with the steps of each, it runs a lesson instead. The unit names its own
    techniques (see tutor/curriculum.py); these are standing ones that belong
    in every lesson whatever the unit is.
    """
    lines = ["HOW TO TEACH - the method, not just the topic:"]
    for mid in cur.STANDING_METHODS:
        m = cur.method(mid)
        lines.append(f"- {m['name']} — {m['how']}")
    lines += [
        "- Talk time: the learner speaks about 70% of the lesson. If you are "
        "talking more than they are, you are doing it wrong.",
        "- Comprehensible input: everything you say sits at their level plus one "
        "small step, never two.",
        "- One thing at a time: a drill trains ONE form. Mixing three is a test, "
        "and a test teaches nothing.",
        "- Silence is part of the method: after a question, wait. Do not fill the "
        "gap, do not rephrase immediately, do not answer for them.",
        "",
    ]
    return "\n".join(lines)


def format_for_prompt() -> str:
    """Standing instructions for the live session, rebuilt on every connect."""
    try:
        lang = _lang()
        with _lock:
            state = _load(lang)
        level = _speech_level(state, lang)
        plan = pg.lesson_plan(state, lang, _native())
    except Exception as e:
        print(f"[Tutor] prompt block failed: {e}")
        return ""

    name, native = lang["name"], _native()
    stretch = cur.BAND_ORDER[min(cur.band_index(level) + 1, len(cur.BAND_ORDER) - 1)]
    slow = str(_setting("pace", "slow")) == "slow"
    other = [l["name"] for k, l in cur.LANGUAGES.items() if k != _mode_key()]
    disabled = [l["name"] for l in cur.LANGUAGES.values() if not l["enabled"]]

    lines = [
        f"[TUTOR MODE — {name.upper()}]",
        f"You are a personal {name} speaking teacher and nothing else. The learner's "
        f"native language is {native}. Speak {name} in the lesson. Use {native} only "
        f"for a one-sentence explanation when they clearly do not understand twice, "
        f"or when they ask what a rule means — then go straight back to {name}.",
        (f"Other language modes: {', '.join(other)}. " if other else "")
        + (f"{', '.join(disabled)} mode is not available yet — if they ask for it, "
           f"say it is coming soon and continue in {name}." if disabled else ""),
        "",
        f"HOW TO SPEAK {name.upper()} (their level is {level}):",
        f"- {_SPEECH_RULES.get(level, _SPEECH_RULES['A2'])}",
        f"- Stretch one step towards {stretch} with one or two new words per turn, "
        f"and give the easy meaning right after: \"expensive — it costs a lot\".",
    ]
    if slow:
        lines.append("- SPEED: speak slowly and clearly, with a real pause at every "
                     "full stop. This never lapses, even in long answers.")
    lines += [
        "- Keep YOUR turns short: one to three sentences, then give the floor back "
        "with a question. The learner must talk more than you - about 70% of the time.",
        "- If they ask you to repeat, say the same thing again, slower and simpler.",
        "",
        "TWO JOBS ON EVERY SENTENCE THEY SAY - in this order:",
        "  1. IS IT RIGHT? If not, correct it (see below) before anything else.",
        "  2. HOW COULD IT BE BETTER? Even a correct sentence gets one upgrade: "
        "a stronger word, a natural phrasal verb, two clauses instead of one. "
        "Say the better version, have them say it, then carry on. Never let a "
        "correct-but-flat sentence pass without the upgrade - that is how they "
        "climb from A2 to B2.",
        "The learner may talk about ANYTHING they like. You do not need to steer "
        "them onto the unit's theme: take whatever they bring and feed this "
        "unit's grammar, words and phrasal verbs into it.",
        "",
        "THEIR DICTIONARY IS LIVE, NOT A LIST:",
        "- Every sentence they say, the analyser proposes a word or a phrasal "
        "verb from THEIR subject, one step above their level. The LESSON PLAN "
        "shows what is waiting: use those items in your own turns, in real "
        "sentences about what they are discussing, and then ask something they "
        "cannot answer without them.",
        "- Two uses of their own and the item is theirs; their screen ticks it "
        "off, so never read the list aloud and never keep score out loud.",
        "- One or two new items per turn. Give a word inside a sentence, never "
        "as a definition, and never one that is two levels above them.",
        "- When they use one correctly, three words of acknowledgement "
        "(\"good \u2014 'run late'\") and carry on.",
        "",
        "WHAT IS ON THEIR SCREEN (do not read it out):",
        "- their sentence with the wrong parts in red, the corrected sentence "
        "under it, a better version, and the grammar rule behind the mistake "
        "with two examples;",
        "- the checklist of this unit's words and phrasal verbs.",
        "So keep your spoken correction SHORT - the detail is already in front "
        "of them. Say the right sentence, have them repeat it, and move on; "
        "explain the rule aloud only if they ask or if the same mistake keeps "
        "coming back.",
        "",
        "HOW TO CORRECT:",
    ]
    if bool(_setting("correct_first", True)):
        lines += [
            "CORRECT FIRST, ANSWER SECOND. The learner asked for this and asked you "
            "to be strict about it. The order of every turn is fixed:",
            "  1. Their sentence has a mistake → FIRST the correction. Say the right "
            "version (\"You mean: I went there yesterday.\"), ask them to say it "
            "(\"Say it.\"), WAIT for their next turn, then one short word of approval "
            "- and ONLY THEN answer what they actually said or asked, in that same "
            "turn. Do not answer the content before the correction is done.",
            "  2. Their sentence is CORRECT → answer straight away, immediately, with "
            "no comment at all. No \"that was correct\", no praise, no repeating their "
            "sentence back. Silence about the grammar IS the reward.",
            "  2b. While the correction is owed, their question waits. Do not "
            "answer the content of a sentence that has a mistake in it - ask for "
            "the corrected version and wait for it. If they reply with something "
            "else, ask once more (\"Say it first: …\"); after that second attempt, "
            "accept it and answer them.",
            "  3. Never answer first and correct afterwards. Never lose the question "
            "either: hold on to what they asked while you correct, and they must never "
            "have to say it twice.",
            "  4. ONE mistake per turn - the most important one, and the FOCUS list or "
            "the current unit comes first. If their second attempt is still wrong, say "
            "the right version once more, accept it, answer them, and move on. Never "
            "drill the same sentence a third time.",
            "  5. EXCEPTION - answer first and correct after when they are upset or in "
            "a hurry, or when the sentence is urgent: stop, wait, repeat that, slower, "
            "I don't understand, help me.",
        ]
    else:
        lines += [
            "- When they make a mistake, correct ONE thing per turn - the most "
            "important one, and always one on the FOCUS list or the current unit.",
            "- Correct like a coach: say the right version, ask them to say it, then "
            "answer them. Never drill the same sentence a third time.",
        ]
    lines += [
        "- Smaller mistakes you are not correcting out loud: use the correct form "
        "naturally in your own reply (recast) instead of stopping the conversation.",
        f"- If they speak {native} because they do not know how to say something: give "
        f"them the simple {name} sentence, ask them to say it, then answer them.",
        "- No grammar lectures, no lists, no long praise. Explain a rule in one short "
        "sentence only when the same mistake keeps coming back.",
        "",
        "HOW A LESSON RUNS (follow the LESSON PLAN below; move through the layers "
        "naturally, do not announce them):",
        "  1. Warm-up - greet by name, one or two easy personal questions.",
        "  2. Review - make them use the FOCUS skills: short prompts built from their "
        "real mistakes (e.g. \"Tell me three things you did yesterday\").",
        "  3. Current unit - explain the target in one or two simple sentences "
        "with an example, then run the unit's own techniques in the order the "
        "LESSON PLAN lists them under HOW TO PRACTISE IT, then the speaking task.",
        "  4. Conversation - talk about the unit theme; keep pulling the target "
        "grammar and the words to recycle into their answers.",
        "  5. Wrap-up - only when they want to stop: one thing they did well, one to "
        "practise, and the new words.",
        "If they want to talk about something else, follow them - any topic is "
        "practice - but keep correcting and keep steering the grammar.",
        "",
        _method_playbook(lang, state),
        "NOTES FROM THE ANALYSER (these arrive as messages; never read the tag aloud):",
        "- [TUTOR_NOTE]: a mistake the analyser found. If you already corrected it, "
        "do not repeat it. Otherwise correct it in one short turn.",
        "- [TUTOR_FOCUS]: the same kind of mistake keeps happening. Finish the current "
        "exchange, then run a 2-minute mini-drill on it, then go back to the lesson.",
        "- [TUTOR_PROGRESS]: a unit or stage is finished. Congratulate in one "
        "sentence and start the next part of the plan.",
        "",
        plan,
    ]
    return "\n".join(lines)


# ── The automatic half ───────────────────────────────────────────────────────

_queue: "queue.Queue" = queue.Queue(maxsize=16)
_worker = None
_worker_lock = threading.Lock()


def observe(text: str, player=None) -> None:
    """Called for EVERY learner utterance. Non-blocking, never raises."""
    try:
        if not text or not text.strip():
            return
        _ensure_worker()
        _queue.put_nowait((text.strip(), player))
    except queue.Full:
        pass
    except Exception as e:
        print(f"[Tutor] observe: {e}")


def _ensure_worker() -> None:
    global _worker
    with _worker_lock:
        if _worker and _worker.is_alive():
            return
        _worker = threading.Thread(target=_worker_loop, name="language-tutor", daemon=True)
        _worker.start()


def _worker_loop() -> None:
    while True:
        text, player = _queue.get()
        try:
            _handle(text, player)
        except Exception as e:
            print(f"[Tutor] {e}")


def _handle(text: str, player) -> None:
    lang = _lang()
    n = len(an.words(text))
    with _lock:
        state = _load(lang)
        paused = bool(state.get("paused"))
        level = pg.effective_level(state)[0]
        unit = pg.position(state, lang).get("unit") or {}

    is_target = an.looks_english(text) if _mode_key() == "english" else False

    if not paused and is_target and _min_words() <= n <= 120:
        with _lock:
            waiting = [i["text"] for i in pg.active_deck(_load(lang))]
        result = an.analyse(
            text, language_name=lang["name"], native_language=_native(), level=level,
            unit_title=unit.get("title", "stage review"),
            unit_skills=unit.get("skills", []), skills=lang["skills"],
            strictness=str(_setting("strictness", "normal")),
            live_dictionary=waiting)
        if result:
            with _lock:
                state = _load(lang)
                # The suggestions land first, so a word they used in this very
                # sentence gets credit for it straight away.
                pg.offer_lexis(state, result.get("suggest_words", []),
                               result.get("suggest_phrasals", []),
                               result.get("topic", ""))
                # What they used is decided locally, never by the model:
                # matching handles inflection and cannot invent a tick.
                used = an.used_items(text, pg.known_items(state))
                outcome = pg.record_target(state, lang, text, result, n,
                                           used_lexis=used)
                _save(state, lang)
            _set_coaching(build_card(text, result, lang, level))
            _log(player, f"{lang['name']}: {band_label(result['score'])}, "
                         f"{len(result['corrections'])} fix(es), "
                         f"{len(result['correct_uses'])} correct use(s)"
                         + (f", used {', '.join(used)}" if used else ""))
            if result.get("suggest_words") or result.get("suggest_phrasals"):
                _log(player, "new for you: " + ", ".join(
                    result.get("suggest_words", []) + result.get("suggest_phrasals", [])))
            for item in outcome.get("checked", []):
                _log(player, f"learned: {item}")
            _react(player, lang, text, result, outcome)
            return

    if not is_target and n >= 2:
        help_data = an.native_help(text, language_name=lang["name"],
                                   native_language=_native(), level=level)
        if help_data:
            with _lock:
                state = _load(lang)
                pg.record_native(state, help_data)
                _save(state, lang)
            _log(player, f"own language → {help_data.get('target_sentence', '')[:60]}")
            return

    with _lock:
        state = _load(lang)
        pg.record_heard(state)
        _save(state, lang, render=False)


def band_label(score: float) -> str:
    return f"{pg.band(score)} ({score:.0f})"


def _react(player, lang: dict, text: str, result: dict, outcome: dict) -> None:
    """Decide what, if anything, the live tutor needs to hear about."""
    if player is None:
        return
    skills = lang["skills"]

    not_the_learner = (
        "This message is from the tutor system, NOT from the learner - they have "
        "said nothing since your last turn. Never answer it as if they had "
        "spoken, never praise a sentence they did not say, never repeat a "
        "question you already asked, and never end the lesson because of it."
    )

    if outcome["events"]:
        with _lock:
            state = _load(lang)
        _say(player,
             "[TUTOR_PROGRESS] " + not_the_learner + " " + " ".join(outcome["events"])
             + (f" {outcome['band_moved']}" if outcome["band_moved"] else "")
             + "\nCongratulate the learner in ONE short sentence, then continue with "
               "the updated plan below. Never read this tag aloud.\n\n"
             + pg.lesson_plan(state, lang, _native()),
             quiet_for=2.0)
        return

    if outcome["repeated"]:
        with _lock:
            state = _load(lang)
        parts = ["[TUTOR_FOCUS] " + not_the_learner,
                 "The learner keeps making the same kind of mistake."]
        for sid in outcome["repeated"]:
            name, _b, hint = skills[sid]
            ex = state["skills"].get(sid, {}).get("examples", [])[-3:]
            parts.append(f"Skill: {name} ({hint}). Their mistakes: "
                         + "; ".join(f"\"{e['wrong']}\" → \"{e['right']}\"" for e in ex))
        parts.append("When the current exchange is finished, run a 2-minute mini-drill: "
                     "the rule in one simple sentence, one example, then three short "
                     "prompts they must answer out loud using it. Then go back to the "
                     "lesson. Never read this tag aloud.")
        _say(player, "\n".join(parts), quiet_for=2.5)
        return

    if not (result["corrections"] or outcome["band_moved"]):
        return
    gap = _THROTTLE.get(str(_setting("speak_every", "never (log only)")), -1)
    if gap < 0:
        return
    # Only mistakes the course is working on — a target of the current unit or
    # one of the focus skills. Everything else is recorded and reviewed later
    # rather than spoken over the lesson.
    with _lock:
        state = _load(lang)
    wanted = {sid for sid, _ in pg.focus_skills(state, lang)}
    wanted |= set((pg.position(state, lang).get("unit") or {}).get("skills", []))
    result["corrections"] = [c for c in result["corrections"] if c["skill"] in wanted]
    if not (result["corrections"] or outcome["band_moved"]):
        return
    with _lock:
        state = _load(lang)
        now = time.monotonic()
        last = float(state.get("last_spoken") or 0)
        if gap and last and now - last < gap and not outcome["band_moved"]:
            return
        state["last_spoken"] = now
        _save(state, lang, render=False)

    parts = ["[TUTOR_NOTE] " + not_the_learner,
             "Analysis of a sentence the learner said earlier:",
             f'They said: "{text}"']
    for c in result["corrections"]:
        parts.append(f'Mistake: "{c.get("wrong", "")}" → "{c.get("right", "")}" '
                     f'({skills.get(c["skill"], (c["skill"],))[0]}: {c.get("why", "")})')
    if result.get("improved"):
        parts.append(f'Better version: "{result["improved"]}"')
    if outcome["band_moved"]:
        parts.append(f"Milestone: {outcome['band_moved']}")
    parts.append("If you ALREADY corrected this, do not correct it again - continue the "
                 "conversation exactly where it was, without repeating your last "
                 "question. If you did not, correct only the most important mistake "
                 "in one short turn (say it right, ask them to say it), then continue.")
    _say(player, "\n".join(parts), quiet_for=3.0)


def _say(player, instruction: str, quiet_for: float) -> None:
    fn = getattr(player, "request_say_when_idle", None)
    if callable(fn):
        try:
            fn(instruction, quiet_for=quiet_for, max_wait=90.0)
            return
        except Exception:
            pass
    fn = getattr(player, "request_say", None)
    if callable(fn):
        try:
            fn(instruction)
        except Exception:
            pass


def _log(player, message: str) -> None:
    try:
        if player and hasattr(player, "write_log"):
            player.write_log(f"SYS: {message}")
        else:
            print(f"[Tutor] {message}")
    except Exception:
        pass


# ── The coaching card ────────────────────────────────────────────────────────
# The panel in the middle of the window is this dict, refreshed every time the
# learner says something: their sentence with the wrong parts flagged, the fix,
# a better version, the grammar tip behind the mistake, and the checklist of
# words this unit is installing. It is held in memory only — it is about the
# sentence they just said, not about their history.

_coaching: dict = {}
_coaching_lock = threading.Lock()


def _set_coaching(card: dict) -> None:
    with _coaching_lock:
        _coaching.clear()
        _coaching.update(card)
        _coaching["stamp"] = time.time()


def coaching_for_ui() -> dict:
    """The latest correction card, plus the live checklist."""
    try:
        lang = _lang()
        with _lock:
            state = _load(lang)
        unit = pg.position(state, lang).get("unit") or {}
        with _coaching_lock:
            card = dict(_coaching)
        card["dictionary"] = pg.dictionary(state)
        card["unit_title"] = unit.get("title", "")
        return card
    except Exception as e:
        print(f"[Tutor] coaching: {e}")
        return {}


def build_card(text: str, result: dict, lang: dict, level: str) -> dict:
    """Turn one analysis into the card. Pure, so it is easy to reason about."""
    corrected = result.get("corrected") or text
    said_tokens, fixed_tokens = an.diff_tokens(text, corrected)
    clean = not result["corrections"]
    fixes = [{"wrong": c.get("wrong", ""), "right": c.get("right", ""),
              "skill": lang["skills"].get(c["skill"], (c["skill"],))[0],
              "why": c.get("why", "")} for c in result["corrections"]]
    tip = {}
    if result["corrections"]:
        tip = cur.skill_tip(result["corrections"][0]["skill"], lang["skills"])
    return {
        "said": text,
        "said_tokens": said_tokens,
        "corrected": "" if clean else corrected,
        "fixed_tokens": [] if clean else fixed_tokens,
        "fixes": fixes,
        "clean": clean,
        "praise": result.get("praise", ""),
        "improved": result.get("improved", ""),
        "improved_uses": result.get("improved_uses", []),
        "tip": tip,
        "score": round(float(result.get("score", 0))),
        "level": pg.band(float(result.get("score", 0))),
        "spoken_level": level,
    }


# ── UI status ────────────────────────────────────────────────────────────────

_status_cache: dict = {"key": None, "value": {}}


def status_for_ui() -> dict:
    """Polled once a second by the lesson panel; re-reads only on change."""
    try:
        lang = _lang()
        path = _paths(lang)[0]
        mtime = path.stat().st_mtime if path.exists() else 0
        key = (lang["name"], mtime, time.strftime("%Y-%m-%d"))
        if _status_cache["key"] != key:
            with _lock:
                state = _load(lang)
            value = pg.ui_status(state, lang)
            value["mode"] = lang["name"]
            value["speak"] = _speech_level(state, lang)
            value["modes"] = [{"name": l["name"], "enabled": l["enabled"],
                               "active": l["name"] == lang["name"]}
                              for l in cur.LANGUAGES.values()]
            _status_cache.update(key=key, value=value)
        return _status_cache["value"]
    except Exception as e:
        print(f"[Tutor] status: {e}")
        return {}


_syllabus_cache: dict = {"key": None, "value": []}


def syllabus_for_ui() -> list:
    """The whole course in order, for the syllabus panel. Same caching as the
    status: re-read only when the learner's file has actually changed."""
    try:
        lang = _lang()
        path = _paths(lang)[0]
        mtime = path.stat().st_mtime if path.exists() else 0
        key = (lang["name"], mtime)
        if _syllabus_cache["key"] != key:
            with _lock:
                state = _load(lang)
            _syllabus_cache.update(key=key, value=pg.syllabus(state, lang))
        return _syllabus_cache["value"]
    except Exception as e:
        print(f"[Tutor] syllabus: {e}")
        return []


# ── The asked-for half ───────────────────────────────────────────────────────

def run(parameters: dict, player=None, session_memory=None) -> str:
    action = str(parameters.get("action") or "report").strip().lower()
    try:
        if action in ("plan", "lesson", "lesson_plan"):
            return _plan()
        if action in ("weak_points", "weak", "mistakes"):
            return _weak_points()
        if action in ("check", "correct"):
            return _check(parameters.get("text", ""))
        if action in ("practice", "drill", "exercise", "test"):
            return _practice(parameters.get("topic", ""), player)
        if action in ("next_unit", "skip", "skip_unit"):
            return _next_unit()
        if action in ("words", "vocab", "vocabulary"):
            return _words()
        if action in ("pause", "stop"):
            return _set_paused(True)
        if action in ("resume", "start"):
            return _set_paused(False)
        if action in ("set_level", "level"):
            return _set_level(parameters.get("level", ""))
        if action in ("set_goal", "goal"):
            return _set_goal(parameters.get("level", ""))
        if action in ("set_mode", "mode", "language"):
            return _set_mode(parameters.get("mode", ""))
        if action in ("open_log", "open", "log"):
            return _open_log()
        return _report()
    except Exception as e:
        return f"The tutor failed: {e}"


def _plan() -> str:
    lang = _lang()
    with _lock:
        state = _load(lang)
    return (pg.lesson_plan(state, lang, _native())
            + "\nContinue teaching from this plan. Do not read it out.")


def _report() -> str:
    lang = _lang()
    with _lock:
        state = _load(lang)
    s = pg.ui_status(state, lang)
    delta, arrow = pg.trend(state)
    totals = state.get("totals", {})
    lines = [
        f"{lang['name']} level: {s['level']} ({s['score']}/100)"
        + ("" if s["measured"] else ", still mostly their own estimate") + f". Goal {s['goal']}.",
        f"Course: stage {s['stage']}, unit {s['unit_no']} of {s['unit_total']} "
        f"\"{s['unit_title']}\", {s['unit_progress']}% done.",
        f"Last 7 days: {arrow} {delta:+.1f} points.",
        f"Practice so far: {totals.get('target_utterances', 0)} sentences; "
        f"{s['sentences_today']} today.",
    ]
    if s["focus"]:
        lines.append("Weakest now: " + ", ".join(
            f"{f['name']} ({f['mastery']}/100)" for f in s["focus"]) + ".")
    lines.append("Tell them this in two or three short, simple sentences, at their level.")
    return "\n".join(lines)


def _weak_points() -> str:
    lang = _lang()
    with _lock:
        state = _load(lang)
    focus = pg.focus_skills(state, lang, limit=5)
    if not focus:
        return "No repeated weak points yet - not enough has been measured."
    lines = ["Weak points, worst first:"]
    for i, (sid, sk) in enumerate(focus, 1):
        name, _b, hint = lang["skills"][sid]
        ex = sk.get("examples", [])[-1:]
        lines.append(f"{i}. {name} ({hint}) — mastery {pg.mastery(sk)}/100"
                     + (f', e.g. "{ex[0]["wrong"]}" → "{ex[0]["right"]}"' if ex else ""))
    lines.append("Name the top two simply and offer a short drill on the first one.")
    return "\n".join(lines)


def _check(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return "Ask the learner to say the sentence they want checked."
    lang = _lang()
    with _lock:
        state = _load(lang)
    unit = pg.position(state, lang).get("unit") or {}
    result = an.analyse(text, language_name=lang["name"], native_language=_native(),
                        level=pg.effective_level(state)[0],
                        unit_title=unit.get("title", ""), unit_skills=unit.get("skills", []),
                        skills=lang["skills"], strictness="strict")
    if not result:
        return f'"{text}" did not read as {lang["name"]}.'
    if not result["corrections"]:
        return f'"{text}" is correct ({band_label(result["score"])}). Confirm it briefly.'
    lines = [f'Checked: "{text}" — {band_label(result["score"])}.']
    for c in result["corrections"]:
        lines.append(f'"{c.get("wrong", "")}" → "{c.get("right", "")}" ({c.get("why", "")})')
    if result.get("improved"):
        lines.append(f'Better: "{result["improved"]}"')
    lines.append("Say the correct sentence, have them repeat it, give the rule in a few words.")
    return "\n".join(lines)


def _practice(topic: str, player=None) -> str:
    lang = _lang()
    with _lock:
        state = _load(lang)
    topic = (topic or "").strip().lower()
    sid = None
    if topic:
        for key, (name, _b, _h) in lang["skills"].items():
            if topic in name.lower() or name.lower() in topic or topic.replace(" ", "_") == key:
                sid = key
                break
    if sid is None:
        focus = pg.focus_skills(state, lang, limit=1)
        unit = pg.position(state, lang).get("unit") or {}
        sid = focus[0][0] if focus else (unit.get("skills") or ["past_simple"])[0]
    name, _b, hint = lang["skills"][sid]
    mistakes = [f'"{e["wrong"]}" → "{e["right"]}"'
                for e in state.get("skills", {}).get(sid, {}).get("examples", [])]
    # Build it as one of the unit's real techniques, not as a quiz: the same
    # five minutes spent on a substitution drill and on a multiple-choice test
    # do not teach the same amount.
    unit = pg.position(state, lang).get("unit") or {}
    methods = cur.methods_of(unit) or [cur.method("substitution")]
    technique = methods[0]
    text = an.drill(language_name=lang["name"], native_language=_native(),
                    level=pg.effective_level(state)[0], skill_name=topic or name,
                    hint=hint, mistakes=mistakes,
                    technique=f"{technique['name']}: {technique['how']}")
    if not text:
        return "The drill came back empty - try again."
    try:
        if player and hasattr(player, "show_content"):
            player.show_content(f"Drill — {name}", text)
    except Exception:
        pass
    return (f"Drill on {name} — technique: {technique['name']} ({technique['how']})\n"
            f"{text}\n\nRun it exactly as that technique says. "
            "Give the rule and example, then the prompts ONE "
            "at a time, waiting for each answer and correcting it. Do not read the "
            "answers out. The drill is also on the learner's screen.")


def _next_unit() -> str:
    lang = _lang()
    with _lock:
        state = _load(lang)
        pos = pg.position(state, lang)
        if pos.get("finished"):
            return "The course is already complete."
        if pos.get("unit") is None:
            return ("All units of this stage are done. The stage passes when the level "
                    "reaches the stage goal - keep talking; nothing to skip.")
        events = pg.advance(state, lang, force=True)
        _save(state, lang)
        plan = pg.lesson_plan(state, lang, _native())
    return (" ".join(events) + " The skipped unit's skills stay on the review list.\n\n"
            + plan + "\nStart the new unit now.")


def _words() -> str:
    lang = _lang()
    with _lock:
        state = _load(lang)
    book = pg.dictionary(state)
    missing = pg.words_to_reuse(state, limit=6)
    lines = [f"Their dictionary: {book['words']} words and {book['phrasals']} "
             f"phrasal verbs learned, {book['learning']} half-way."]
    if book["active"]:
        lines.append("Waiting to be used (from their own topics): "
                     + ", ".join(f"{i['text']} ({i['kind']})" for i in book["active"]))
    if book["recent"]:
        lines.append("Recently learned: "
                     + ", ".join(r["text"] for r in book["recent"]))
    if missing:
        lines.append("Words they needed in their own language: "
                     + ", ".join(f"{k} ({v.get('native', '')})" for k, v in missing))
    lines.append("Name two or three of the waiting ones and put them into a "
                 "question they have to answer with them.")
    return "\n".join(lines)


def _set_paused(paused: bool) -> str:
    lang = _lang()
    with _lock:
        state = _load(lang)
        state["paused"] = paused
        _save(state, lang, render=False)
    return ("Analysis paused: sentences are not measured until resumed. Keep "
            "teaching normally." if paused else "Analysis is back on.")


def _set_level(level: str) -> str:
    level = str(level or "").strip().upper()
    if level not in cur.BAND_ORDER:
        return "Not a CEFR level. Ask for A1, A2, B1, B2, C1 or C2."
    lang = _lang()
    with _lock:
        state = _load(lang)
        state["declared_level"] = level
        _save(state, lang)
    _save_setting({"starting_level": level})
    return f"Stated level set to {level}. It counts until enough speech is measured."


def _set_goal(level: str) -> str:
    level = str(level or "").strip().upper()
    if level not in cur.BAND_ORDER:
        return "Not a CEFR level. Ask for B1, B2 or C1."
    lang = _lang()
    with _lock:
        state = _load(lang)
        state["goal_level"] = level
        _save(state, lang)
    _save_setting({"goal_level": level})
    return f"Goal set to {level}."


def set_language(name: str) -> tuple[bool, str]:
    """Switch course from the UI's language select. Returns (ok, message).

    A mode whose curriculum is not written yet is refused here rather than
    half-applied, so the select can say so and stay on the language that works.
    """
    key = str(name or "").strip().lower().split()[0]
    lang = cur.LANGUAGES.get(key)
    if not lang:
        return False, f"There is no {name} course."
    if not lang["enabled"]:
        return False, f"The {lang['name']} course is not ready yet."
    if key == _mode_key():
        return True, f"Already learning {lang['name']}."
    _save_setting({"mode": lang["name"]})
    return True, f"Switched to {lang['name']}."


def _set_mode(mode: str) -> str:
    key = str(mode or "").strip().lower().split()[0] if str(mode or "").strip() else ""
    lang = cur.LANGUAGES.get(key)
    if not lang:
        return "Unknown mode. Available: English. Slovak is coming soon."
    if not lang["enabled"]:
        return (f"{lang['name']} mode is not available yet — it is coming soon. "
                f"Tell the learner simply, and continue in {_lang()['name']}.")
    _save_setting({"mode": lang["name"]})
    return f"Mode is {lang['name']}."


def _save_setting(values: dict) -> None:
    try:
        from memory.config_manager import save_plugin_config
        save_plugin_config("language_tutor", values)
    except Exception:
        pass


def _open_log() -> str:
    lang = _lang()
    state_path, log_path = _paths(lang)
    with _lock:
        if not log_path.exists():
            pg.render_log(log_path, _load(lang), lang)
    try:
        os.startfile(str(log_path))       # noqa: S606 — Windows shell open
        return f"Opened the progress file ({log_path.name})."
    except Exception:
        return f"The progress file is at {log_path}."
