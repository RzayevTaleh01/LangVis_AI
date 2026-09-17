"""
core/selflog.py — the assistant's own record of what it printed.

WHY THIS EXISTS
    Everything LangVis knows about its own failures went to stdout. If it was
    launched from a terminal the traceback scrolled past; if it was launched by
    double-clicking, it went nowhere at all. Either way the one participant who
    could not see it was LangVis: the model heard "something went wrong" from
    the user and had nothing to look at.

    So a crash could happen twice in a row and the second time the assistant
    was as surprised as the first.

    This tees stdout and stderr — every print, every traceback — into two
    places: a real file on disk, and a ring buffer in memory the model can be
    handed on request. Nothing at the call sites changes; installing the tee is
    the whole integration.

WHY A RING BUFFER AND A FILE
    The buffer is what the model reads: bounded, instant, no disk seek in the
    middle of a conversation. The file is what survives a crash, so "what
    happened before it died" is still answerable after a restart.
"""
from __future__ import annotations

import io
import re
import sys
import threading
from collections import deque
from datetime import datetime
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


LOG_DIR = _base_dir() / "logs"
LOG_PATH = LOG_DIR / "langvis.log"

# Enough to hold a long traceback plus the run-up to it, without letting a
# chatty loop push the interesting part out in a second.
RING_SIZE = 800
# Rotate rather than grow forever; one previous file is enough to answer
# "what happened just before the restart".
MAX_LOG_BYTES = 4 * 1024 * 1024

_ring: deque = deque(maxlen=RING_SIZE)
_lock = threading.Lock()
_installed = False

# A line worth showing when asked "what went wrong". Deliberately broad — a
# missed error is worse than one extra line of context.
_ERROR_RE = re.compile(
    r"traceback|exception|error|❌|⚠️|failed|refus|denied|cannot |could not |"
    r"timed out|timeout|closed|1008|1011|crash",
    re.IGNORECASE,
)
# Lines that match the pattern but are routine and would drown the signal.
#
# "📤" is the tool-result line main.py prints. Excluding it matters for more
# than tidiness: self_check returns error text, main.py echoes that result to
# stdout, and the echo would be captured as a fresh error for the next
# self_check to report. Tool outcomes belong to the conversation and the
# journal; this log is for LangVis's own faults.
_NOISE_RE = re.compile(
    r"DeprecationWarning|ResourceWarning|automatic function calling|"
    r"does not appear to be open|nothing to close|is not running|"
    r"📤|\[self_check\]|error line\(s\) recorded",
    re.IGNORECASE,
)


class _Tee(io.TextIOBase):
    """Passes writes through to the real stream, keeping a copy."""

    def __init__(self, stream, level: str):
        self._stream = stream
        self._level = level
        self._partial = ""

    def write(self, text) -> int:
        try:
            self._stream.write(text)
        except Exception:
            pass
        try:
            self._capture(text)
        except Exception:
            pass
        return len(text)

    def flush(self) -> None:
        try:
            self._stream.flush()
        except Exception:
            pass

    def isatty(self) -> bool:
        try:
            return self._stream.isatty()
        except Exception:
            return False

    def _capture(self, text: str) -> None:
        # print() arrives in pieces; only whole lines are worth storing.
        self._partial += text
        if "\n" not in self._partial:
            return
        *lines, self._partial = self._partial.split("\n")
        stamp = datetime.now().strftime("%H:%M:%S")
        with _lock:
            for line in lines:
                if not line.strip():
                    continue
                _ring.append((stamp, self._level, line.rstrip()))
            _write_file(lines, stamp, self._level)


def _write_file(lines, stamp: str, level: str) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > MAX_LOG_BYTES:
            LOG_PATH.replace(LOG_PATH.with_suffix(".log.1"))
        day = datetime.now().strftime("%Y-%m-%d")
        with open(LOG_PATH, "a", encoding="utf-8", errors="replace") as fh:
            for line in lines:
                if line.strip():
                    fh.write(f"{day} {stamp} [{level}] {line.rstrip()}\n")
    except Exception:
        pass


def install() -> None:
    """Tee stdout and stderr. Safe to call twice."""
    global _installed
    if _installed:
        return
    sys.stdout = _Tee(sys.stdout, "out")
    sys.stderr = _Tee(sys.stderr, "err")
    _installed = True
    print(f"[SelfLog] recording to {LOG_PATH}")


# ── Reading it back ──────────────────────────────────────────────────────────

def tail(limit: int = 60) -> list[str]:
    with _lock:
        rows = list(_ring)[-limit:]
    return [f"{t} {line}" for t, _, line in rows]


def errors(limit: int = 40) -> list[str]:
    """Error lines with the traceback body that follows them.

    A traceback's first line matches the pattern and the rest does not, so
    matching alone would hand the model "Traceback (most recent call last):"
    and nothing else. Indented continuation lines are pulled in with it.
    """
    with _lock:
        rows = list(_ring)
    out: list[str] = []
    carry = 0
    for stamp, _, line in rows:
        hit = bool(_ERROR_RE.search(line)) and not _NOISE_RE.search(line)
        if hit:
            carry = 12                      # keep the frames under this line
            out.append(f"{stamp} {line}")
        elif carry and (line.startswith((" ", "\t", "|", "+")) or line.startswith("  ")):
            carry -= 1
            out.append(f"{stamp} {line}")
        else:
            carry = 0
    return out[-limit:]


def error_count() -> int:
    with _lock:
        rows = list(_ring)
    return sum(1 for _, _, line in rows
               if _ERROR_RE.search(line) and not _NOISE_RE.search(line))


def file_tail(limit: int = 120) -> list[str]:
    """The last lines from disk — survives a restart, unlike the ring."""
    try:
        text = LOG_PATH.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    return text.splitlines()[-limit:]
