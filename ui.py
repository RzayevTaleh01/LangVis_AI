from __future__ import annotations

import json
import math
import os
import platform
import random
import subprocess
import sys
import threading
import time
from pathlib import Path


if platform.system() == "Windows":
    _WIN_HIDE: dict = {"creationflags": subprocess.CREATE_NO_WINDOW}
else:
    _WIN_HIDE: dict = {}

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush, QColor, QConicalGradient, QFont, QKeySequence, QLinearGradient,
    QFontMetrics, QPainter, QPainterPath, QPainterPathStroker, QPen,
    QPixmap, QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit,
    QMainWindow, QPushButton, QScrollArea, QSizePolicy, QSplitter,
    QTextEdit, QVBoxLayout, QWidget,
)

# ── Which Mark this is ───────────────────────────────────────────────────────
# One constant, read by the window title, the header badge and the PROTOCOL
# panel. It used to be typed separately in each of those places, and they drifted:
# Mark 52 and 53 shipped showing "PROTOCOL XLIX" — the number from Mark 49 — and
# Mark 55 shipped titled "MARK 54". Deriving the protocol from the name means a
# release bump is this one line.
APP_VERSION  = "v1.0"
APP_PROTOCOL = APP_VERSION.split()[-1]

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR   = _base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"


def _read_full_config() -> dict:
    """Read api_keys.json config dict. Returns {} on any error."""
    try:
        return json.loads(API_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


_DEFAULT_W, _DEFAULT_H = 1260, 820
_MIN_W,     _MIN_H     = 1040, 640
_LEFT_W  = 262
_RIGHT_W = 392

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"


class C:
    """The LangVis palette: paper, ink and forest.

    A language course is read like a book, so the app is built on warm paper
    with dark ink; the brand colour is a deep forest green (the course, the
    learner's own sentences, everything on track) and the tutor's own voice is
    terracotta. Meaning never rests on colour alone — every state is also a
    word on screen — but the colours are consistent: green is the course,
    terracotta is the tutor talking, mustard is thinking, brick is a mistake.

    The keys listed in _HUE_LINKED are re-derived from the accent colour in the
    picker, so the whole app can be recoloured and still read as paper and ink.
    Two names read backwards for historical reasons and are kept because saved
    settings and stylesheets depend on them: WHITE is the STRONGEST ink, and
    DARK is the chrome the panels sit on.
    """
    BG        = "#f6f1e7"   # warm paper: the page
    PANEL     = "#fffdf9"   # cards, bubbles, inputs
    PANEL2    = "#f2ece0"   # inset areas
    BORDER    = "#e0d5c2"
    BORDER_B  = "#c2b195"   # hover, focus, stronger edges
    BORDER_A  = "#ebe3d5"
    PRI       = "#12695a"   # the brand: deep forest green
    PRI_DIM   = "#6f9c92"
    PRI_GHO   = "#e2efec"   # brand tint fill
    ACC       = "#c75a2b"   # the tutor is speaking (terracotta)
    ACC2      = "#c98a0a"   # thinking (mustard)
    GREEN     = "#4a8a3f"   # finished, strong, right (leaf)
    GREEN_D   = "#3a6e32"
    GREEN_GHO = "#e8f0e2"
    RED       = "#b23a3a"   # a mistake (brick)
    MUTED_C   = "#b23a3a"   # mic off
    MUTED_GHO = "#f7e6e2"
    TEXT      = "#4a4438"   # body ink
    TEXT_DIM  = "#948b78"
    TEXT_MED  = "#6d6556"
    WHITE     = "#23201a"   # strongest ink
    DARK      = "#fffdf9"   # chrome the panels sit on
    BAR_BG    = "#e7dfd0"


# One friendly sans for the whole app. A language tutor is read, not monitored,
# so the terminal typeface the old HUD used is gone.
_UI_FONT = ("Segoe UI" if _OS == "Windows"
            else "SF Pro Text" if _OS == "Darwin" else "DejaVu Sans")


def font(size: int, bold: bool = False) -> QFont:
    f = QFont(_UI_FONT, size)
    if bold:
        f.setWeight(QFont.Weight.DemiBold)
    return f


# ── Shared, reusable styling ────────────────────────────────────────────────
# Rounded, roomy, low-contrast: the visual language of the whole app in four
# strings, so a new panel looks like the rest without copying a stylesheet.

def card_style(radius: int = 12, pad: int = 0) -> str:
    """A card: a fill and one light edge, never a heavy outline."""
    return (f"background: {C.PANEL}; border: 1px solid {C.BORDER_A};"
            f"border-radius: {radius}px;" + (f"padding: {pad}px;" if pad else ""))


def pill_style(ink: str, fill: str, radius: int = 13) -> str:
    """A pill carries meaning with its fill, so it never also carries a border."""
    return (f"color: {ink}; background: {fill}; border: none;"
            f"border-radius: {radius}px; padding: 5px 12px;")


def btn_primary(radius: int = 10) -> str:
    return f"""
        QPushButton {{
            background: {C.PRI}; color: #ffffff; border: none;
            border-radius: {radius}px; padding: 0 14px; text-align: left;
        }}
        QPushButton:hover {{ background: {C.WHITE}; }}
        QPushButton:disabled {{ background: {C.BORDER_B}; color: {C.PANEL}; }}
    """


def btn_soft(radius: int = 10) -> str:
    return f"""
        QPushButton {{
            background: {C.PANEL}; color: {C.TEXT}; border: 1px solid {C.BORDER};
            border-radius: {radius}px; padding: 0 14px; text-align: left;
        }}
        QPushButton:hover {{ background: {C.PRI_GHO}; border-color: {C.BORDER_B};
                             color: {C.PRI}; }}
    """


def btn_tone(text_col: str, fill: str, border: str, radius: int = 10) -> str:
    return f"""
        QPushButton {{
            background: {fill}; color: {text_col}; border: 1px solid {border};
            border-radius: {radius}px; padding: 0 14px; text-align: left;
        }}
        QPushButton:hover {{ border-color: {text_col}; }}
    """


def combo_style(radius: int = 10, accent: bool = False) -> str:
    """Every drop-down in the app, styled once.

    The arrow is deliberately left to Qt: overriding ::drop-down without
    supplying an image removes the arrow altogether, which is how a select ends
    up looking like a plain box nobody knows they can open. Only the box, the
    popup and the row height are ours.
    """
    return f"""
        QComboBox {{
            background: {C.PANEL}; color: {C.PRI if accent else C.TEXT};
            border: 1px solid {C.BORDER}; border-radius: {radius}px;
            padding: 3px 8px 3px 12px;
        }}
        QComboBox:hover  {{ border-color: {C.BORDER_B}; }}
        QComboBox:focus  {{ border-color: {C.PRI}; }}
        QComboBox:disabled {{ color: {C.TEXT_DIM}; background: {C.PANEL2}; }}
        QComboBox QAbstractItemView {{
            background: {C.PANEL}; color: {C.TEXT};
            border: 1px solid {C.BORDER}; padding: 4px; outline: none;
            selection-background-color: {C.PRI_GHO}; selection-color: {C.PRI};
        }}
        QComboBox QAbstractItemView::item {{ min-height: 28px; padding: 4px 8px; }}
        QComboBox QAbstractItemView::item:disabled {{ color: {C.TEXT_DIM}; }}
    """


def scrollbar_style() -> str:
    return f"""
        QScrollBar:vertical {{ background: transparent; width: 9px; border: none;
                               margin: 4px 2px 4px 0; }}
        QScrollBar::handle:vertical {{ background: {C.BORDER_B}; border-radius: 4px;
                                       min-height: 28px; }}
        QScrollBar::handle:vertical:hover {{ background: {C.PRI_DIM}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
    """


# Keys tied to the accent colour — status colours (ACC, GREEN, RED…) stay fixed
_HUE_LINKED = (
    "BG", "PANEL", "PANEL2", "BORDER", "BORDER_B", "BORDER_A",
    "PRI", "PRI_DIM", "PRI_GHO", "TEXT", "TEXT_DIM", "TEXT_MED",
    "WHITE", "DARK", "BAR_BG",
)
_PALETTE_DEFAULTS: dict[str, str] = {k: getattr(C, k) for k in _HUE_LINKED}

DEFAULT_UI_COLOR = _PALETTE_DEFAULTS["PRI"].lower()


def apply_ui_accent(accent_hex: str) -> bool:
    """
    Re-derives the whole teal-family palette from the chosen accent colour
    (hue shift — brightness/saturation ratios are preserved, design stays intact).
    Painted elements (HUD, waveform, metrics) pick up the new colour on the next
    frame; stylesheet-based panels pick it up when they are rebuilt.
    """
    import colorsys

    accent_hex = (accent_hex or "").strip().lower()
    if not (accent_hex.startswith("#") and len(accent_hex) == 7):
        return False
    try:
        int(accent_hex[1:], 16)
    except ValueError:
        return False

    def _hsv(h: str) -> tuple[float, float, float]:
        r = int(h[1:3], 16) / 255
        g = int(h[3:5], 16) / 255
        b = int(h[5:7], 16) / 255
        return colorsys.rgb_to_hsv(r, g, b)

    base_h            = _hsv(_PALETTE_DEFAULTS["PRI"])[0]
    acc_h, acc_s, _av = _hsv(accent_hex)
    dh   = acc_h - base_h
    grey = acc_s < 0.08   # near-grey accent → the whole theme is desaturated

    for key, hex0 in _PALETTE_DEFAULTS.items():
        h, s, v = _hsv(hex0)
        if grey:
            s *= 0.15
        r, g, b = colorsys.hsv_to_rgb((h + dh) % 1.0, s, v)
        setattr(C, key, "#{:02x}{:02x}{:02x}".format(
            int(r * 255 + 0.5), int(g * 255 + 0.5), int(b * 255 + 0.5)))
    return True


def current_palette() -> dict[str, str]:
    """A snapshot of the accent-linked colours currently on class C."""
    return {k: getattr(C, k) for k in _HUE_LINKED}


def retheme_all_widgets(old: dict[str, str], new: dict[str, str]) -> None:
    """
    LIVE full theme change. Replaces the old palette colours with the new ones
    in EVERY widget's stylesheet across the app and repaints them. This way the
    colour change applies INSTANTLY across the whole interface — panels, buttons,
    borders included — not just the painted elements. No restart needed.
    """
    mapping = {old[k].lower(): new[k].lower()
               for k in old if old[k].lower() != new.get(k, old[k]).lower()}
    if not mapping:
        return
    app = QApplication.instance()
    if app is None:
        return
    for w in app.allWidgets():
        try:
            ss = w.styleSheet()
            if ss:
                s2 = ss
                for o, n in mapping.items():
                    if o in s2:
                        s2 = s2.replace(o, n)
                if s2 != ss:
                    w.setStyleSheet(s2)
            w.update()
        except Exception:
            pass


def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h); c.setAlpha(a); return c


class VoiceVector(QWidget):
    """The voice of the app, drawn as one vector mark.

    Everything here is a path, not an image: a speech bubble with a microphone
    inside it and sound waves on both sides. The waves are what the learner
    watches — they open out with the real audio level, lean towards the tutor's
    terracotta while it speaks and towards the brand green while it listens, and
    fold away to a slashed microphone when the mic is off. One glance answers
    the only question that matters mid-sentence: is it hearing me?

    The public attributes are unchanged from the widget this replaces (`state`,
    `speaking`, `muted`, `set_audio_level`) because the live session drives them.
    """

    def __init__(self, face_path: str = "", assistant_name: str = "LangVis", parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMinimumSize(300, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.muted    = False
        self.speaking = False
        self.state    = "INITIALISING"
        self._assistant_name = assistant_name

        self._tick    = 0
        self._breathe = 0.0
        self._wave    = 0.0        # 0..1, waves travelling outwards
        self._live_amp = 0.0       # written from the audio threads
        self._amp_disp = 0.0

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(33)

    # -- state in -------------------------------------------------------------

    def set_audio_level(self, level: float) -> None:
        """Thread-safe entry point for the audio threads: keeps the louder of
        the new and current level so gaps between chunks do not flicker."""
        try:
            lv = float(level)
        except (TypeError, ValueError):
            return
        self._live_amp = max(self._live_amp, min(1.0, max(0.0, lv)))

    def _step(self):
        self._tick += 1
        self._live_amp *= 0.82
        self._amp_disp += (self._live_amp - self._amp_disp) * 0.4
        self._breathe = math.sin(self._tick * (0.10 if self.speaking else 0.05))
        self._wave = (self._wave + (0.03 if self.speaking else 0.014)) % 1.0
        if self.speaking or self._amp_disp > 0.02 or self._tick % 3 == 0:
            self.update()

    def _tone(self) -> str:
        if self.muted:
            return C.MUTED_C
        if self.speaking:
            return C.ACC
        if self.state in ("THINKING", "PROCESSING"):
            return C.ACC2
        if self.state == "SLEEPING":
            return C.TEXT_MED
        return C.PRI

    def _status(self) -> tuple[str, str]:
        if self.muted:
            return "Microphone off", "Press F4 to switch it back on"
        if self.speaking:
            return f"{self._assistant_name} is speaking", "Press Esc to cut in"
        if self.state in ("THINKING", "PROCESSING"):
            return "Thinking…", "One moment"
        if self.state == "LISTENING":
            return "Your turn — speak", "Say a full sentence, not one word"
        if self.state == "SLEEPING":
            return "Sleeping", "Say the wake phrase to begin"
        return "Getting ready…", ""

    # -- the vector -----------------------------------------------------------

    def _bubble_path(self, cx: float, cy: float, w: float, h: float) -> QPainterPath:
        """A speech bubble: rounded box plus a tail on the bottom left."""
        path = QPainterPath()
        r = h * 0.34
        box = QRectF(cx - w / 2, cy - h / 2, w, h)
        path.addRoundedRect(box, r, r)
        tail = QPainterPath()
        bx = box.left() + w * 0.26
        by = box.bottom() - 1
        tail.moveTo(bx, by)
        tail.lineTo(bx + h * 0.10, by + h * 0.26)
        tail.lineTo(bx + h * 0.30, by)
        tail.closeSubpath()
        return path.united(tail)

    def _mic_path(self, cx: float, cy: float, r: float) -> QPainterPath:
        """A microphone: capsule, cradle arc and stand — all one path."""
        path = QPainterPath()
        cap_w, cap_h = r * 0.74, r * 1.18
        path.addRoundedRect(QRectF(cx - cap_w / 2, cy - cap_h * 0.72, cap_w, cap_h),
                            cap_w / 2, cap_w / 2)
        cradle = QRectF(cx - r * 0.66, cy - r * 0.46, r * 1.32, r * 1.32)
        arc = QPainterPath()
        arc.arcMoveTo(cradle, 200)
        arc.arcTo(cradle, 200, 140)
        stroked = QPainterPathStroker()
        stroked.setWidth(max(2.0, r * 0.15))
        stroked.setCapStyle(Qt.PenCapStyle.RoundCap)
        path = path.united(stroked.createStroke(arc))
        stem = QPainterPath()
        stem.moveTo(cx, cy + r * 0.62)
        stem.lineTo(cx, cy + r * 0.92)
        base = QPainterPath()
        base.moveTo(cx - r * 0.34, cy + r * 0.95)
        base.lineTo(cx + r * 0.34, cy + r * 0.95)
        return path.united(stroked.createStroke(stem)).united(stroked.createStroke(base))

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), qcol(C.BG))

        W, H = self.width(), self.height()
        amp = self._amp_disp
        tone = self._tone()
        span = min(W * 0.62, H * 0.92, 470)
        cx = W / 2
        cy = H * 0.44
        bw = span * 0.52
        bh = bw * 0.72

        # sound waves: three arcs each side, opening out with the level
        reach = span * 0.30
        for i in range(3):
            phase = (self._wave + i / 3.0) % 1.0
            grow = 0.55 + phase * 0.75
            live = amp if not self.muted else 0.0
            alpha = int(max(0, (1.0 - phase) * (70 + live * 165)))
            if self.muted:
                alpha = 26
            rr = reach * grow
            pen = QPen(qcol(tone, alpha), max(2.0, span * 0.018))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            for side in (-1, 1):
                box = QRectF(cx + side * (bw * 0.52) - rr, cy - rr, rr * 2, rr * 2)
                start = 320 if side == 1 else 140
                p.drawArc(box, int(start * 16), int(80 * 16))

        # the bubble
        breathe = 1.0 + self._breathe * 0.012 + amp * 0.05
        bubble = self._bubble_path(cx, cy, bw * breathe, bh * breathe)
        p.setBrush(QBrush(qcol(C.PANEL)))
        p.setPen(QPen(qcol(tone, 235), max(2.0, span * 0.02)))
        p.drawPath(bubble)

        # the microphone inside it
        mic_r = bh * 0.33
        p.setBrush(QBrush(qcol(tone, 255)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(self._mic_path(cx, cy - bh * 0.02, mic_r))

        if self.muted:
            pen = QPen(qcol(C.MUTED_C), max(2.5, span * 0.022))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            d = mic_r * 1.5
            p.drawLine(QPointF(cx - d, cy + d * 0.8), QPointF(cx + d, cy - d * 0.8))

        # a dot of the live level, sitting in the bubble's own corner
        if not self.muted and amp > 0.04:
            rr = max(3.0, span * 0.016) * (1 + amp)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(qcol(tone, 200)))
            p.drawEllipse(QPointF(cx + bw * 0.34, cy - bh * 0.30), rr, rr)

        # what is happening, in words
        head, hint = self._status()
        y = cy + bh * 0.95
        p.setPen(QPen(qcol(tone), 1))
        p.setFont(font(15, True))
        p.drawText(QRectF(0, y, W, 26), Qt.AlignmentFlag.AlignCenter, head)
        if hint:
            p.setPen(QPen(qcol(C.TEXT_DIM), 1))
            p.setFont(font(10))
            p.drawText(QRectF(0, y + 24, W, 20), Qt.AlignmentFlag.AlignCenter, hint)
        p.end()


class SoftBar(QWidget):
    """A rounded progress bar with a caption — unit progress, skill mastery.

    Painted rather than a QProgressBar because the caption, the value and the
    colour belong together: one widget, one line of layout, and the colour says
    whether a number is a problem (brick), on its way (mustard) or done (leaf).
    """

    def __init__(self, label: str = "", colour: str = "", parent=None):
        super().__init__(parent)
        self._label  = label
        self._colour = colour           # "" -> derive from the value
        self._value  = 0.0
        self._text   = ""
        self.setFixedHeight(28 if label else 16)

    def set_value(self, pct: float, text: str = "", label: str | None = None):
        v = max(0.0, min(100.0, float(pct)))
        if label is not None:
            self._label = label
        if v == self._value and text == self._text:
            return
        self._value, self._text = v, text
        self.update()

    def _bar_colour(self) -> str:
        if self._colour:
            return self._colour
        if self._value < 40:
            return C.RED
        if self._value < 70:
            return C.ACC2
        return C.GREEN

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        col = self._bar_colour()

        top = 0
        if self._label:
            p.setFont(font(10))
            p.setPen(QPen(qcol(C.TEXT), 1))
            p.drawText(QRectF(0, 0, W * 0.74, 15),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       self._label)
            if self._text:
                p.setFont(font(10, True))
                p.setPen(QPen(qcol(col), 1))
                p.drawText(QRectF(W * 0.5, 0, W * 0.5, 15),
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                           self._text)
            top = 17
        bar_h = 5.0
        y = top + (H - top - bar_h) / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(qcol(C.BAR_BG)))
        p.drawRoundedRect(QRectF(0, y, W, bar_h), 2.5, 2.5)
        fill = W * self._value / 100.0
        if fill > 0:
            p.setBrush(QBrush(qcol(col)))
            p.drawRoundedRect(QRectF(0, y, max(fill, bar_h), bar_h), 2.5, 2.5)
        p.end()


class ChatView(QScrollArea):
    """The lesson as a conversation: bubbles, not a log.

    What scrolled past as terminal lines is exactly what a learner needs to
    re-read — what they said, how it should have been said, what they were
    asked. Their own sentences sit on the right in the brand colour, the
    tutor's on the left on paper, and the app's own remarks shrink to a small
    line that competes with neither.

    `append_log()` keeps its old name and the old "You:" / "LangVis:" / "SYS:"
    prefixes, and is thread-safe through a signal: the audio threads call it.
    """

    _sig = pyqtSignal(str)
    MAX_ROWS = 220

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ai_name_lc = "langvis"     # updated when the tutor is renamed
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(
            f"QScrollArea {{ background: {C.PANEL}; border: 1px solid "
            f"{C.BORDER_A}; border-radius: 12px; }}" + scrollbar_style())

        self._inner = QWidget()
        self._inner.setStyleSheet(f"background: {C.PANEL};")
        self._lay = QVBoxLayout(self._inner)
        self._lay.setContentsMargins(12, 12, 12, 12)
        self._lay.setSpacing(8)
        self._lay.addStretch(1)
        self.setWidget(self._inner)

        self._rows: list[QWidget] = []
        self._placeholder = QLabel("Your lesson appears here.\n"
                                   "Start talking — the tutor is listening.")
        self._placeholder.setFont(font(10))
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet(
            f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        self._lay.insertWidget(0, self._placeholder, 1)
        self._sig.connect(self._add)

    def append_log(self, text: str):
        self._sig.emit(text)

    def _classify(self, text: str) -> tuple[str, str]:
        low = text.lower()
        if low.startswith("you:"):
            return "you", text[4:].strip()
        if low.startswith(f"{self._ai_name_lc}:") or low.startswith("langvis:"):
            return "ai", text.split(":", 1)[1].strip()
        if low.startswith("err") or low.startswith("net"):
            return "err", text.split(":", 1)[-1].strip()
        return "sys", text.split(":", 1)[-1].strip()

    def _add(self, raw: str):
        text = (raw or "").strip()
        if not text:
            return
        kind, body = self._classify(text)
        if not body:
            return
        self._placeholder.hide()

        row = QWidget()
        row.setStyleSheet(f"background: {C.PANEL};")
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        bubble = QLabel(body)
        bubble.setWordWrap(True)
        bubble.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bubble.setMaximumWidth(self._bubble_width())

        if kind == "you":
            bubble.setFont(font(11))
            bubble.setStyleSheet(
                f"background: {C.PRI}; color: {C.PANEL}; border: none;"
                f"border-radius: 12px; border-bottom-right-radius: 3px;"
                f"padding: 8px 11px;")
            h.addStretch(1)
            h.addWidget(bubble)
        elif kind == "ai":
            bubble.setFont(font(11))
            bubble.setStyleSheet(
                f"background: {C.PANEL2}; color: {C.WHITE}; border: none;"
                f"border-radius: 12px; border-bottom-left-radius: 3px;"
                f"padding: 8px 11px;")
            h.addWidget(bubble)
            h.addStretch(1)
        else:
            bubble.setFont(font(9))
            bubble.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if kind == "err":
                bubble.setStyleSheet(pill_style(C.RED, C.MUTED_GHO, 9))
            else:
                bubble.setStyleSheet(
                    f"color: {C.TEXT_DIM}; background: transparent; border: none;"
                    f"padding: 2px 6px;")
            h.addStretch(1)
            h.addWidget(bubble)
            h.addStretch(1)

        self._lay.insertWidget(self._lay.count() - 1, row)
        self._rows.append(row)
        while len(self._rows) > self.MAX_ROWS:
            old = self._rows.pop(0)
            self._lay.removeWidget(old)
            old.deleteLater()
        QTimer.singleShot(0, self._to_bottom)
        QTimer.singleShot(60, self._to_bottom)

    def _bubble_width(self) -> int:
        return max(180, int((self.width() or 320) * 0.82))

    def _to_bottom(self):
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        width = self._bubble_width()
        for row in self._rows:
            for child in row.findChildren(QLabel):
                child.setMaximumWidth(width)


class SetupOverlay(QWidget):
    done = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            SetupOverlay {{
                background: rgba(255, 255, 255, 246);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)

        detected = {"darwin": "mac", "windows": "windows"}.get(
            _OS.lower(), "linux"
        )
        self._sel_os = detected

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 22, 30, 22)
        layout.setSpacing(8)

        def _lbl(txt, font_size=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont(_UI_FONT, font_size,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        layout.addWidget(_lbl("◈  INITIALISATION REQUIRED", 13, True))
        layout.addWidget(_lbl("Configure J.A.R.V.I.S. before first boot.", 9, color=C.PRI_DIM))
        layout.addSpacing(6)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};"); layout.addWidget(sep)
        layout.addSpacing(4)

        layout.addWidget(_lbl("GEMINI API KEY", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText("AIza…")
        self._key_input.setFont(QFont(_UI_FONT, 12))
        self._key_input.setFixedHeight(32)
        self._key_input.setStyleSheet(f"""
            QLineEdit {{
                background: {C.PANEL}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 9px; padding: 4px 8px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        layout.addWidget(self._key_input)
        layout.addSpacing(12)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER};"); layout.addWidget(sep2)
        layout.addSpacing(4)

        layout.addWidget(_lbl("OPERATING SYSTEM", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        det_name = {"windows": "Windows", "mac": "macOS", "linux": "Linux"}[detected]
        layout.addWidget(_lbl(f"Auto-detected: {det_name}", 8, color=C.ACC2,
                               align=Qt.AlignmentFlag.AlignLeft))

        os_row = QHBoxLayout(); os_row.setSpacing(6)
        self._os_btns: dict[str, QPushButton] = {}
        for key, label in [("windows","⊞  Windows"),("mac","  macOS"),("linux","🐧  Linux")]:
            btn = QPushButton(label)
            btn.setFont(QFont(_UI_FONT, 11, QFont.Weight.Bold))
            btn.setFixedHeight(32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, k=key: self._sel(k))
            os_row.addWidget(btn)
            self._os_btns[key] = btn
        layout.addLayout(os_row)
        self._sel(detected)
        layout.addSpacing(12)

        init_btn = QPushButton("▸  INITIALISE SYSTEMS")
        init_btn.setFont(QFont(_UI_FONT, 12, QFont.Weight.Bold))
        init_btn.setFixedHeight(36)
        init_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        init_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 9px;
            }}
            QPushButton:hover {{
                background: {C.PRI_GHO}; border: 1px solid {C.PRI};
            }}
        """)
        init_btn.clicked.connect(self._submit)
        layout.addWidget(init_btn)

    def _sel(self, key: str):
        self._sel_os = key
        pal = {"windows": (C.PRI, C.PRI_GHO), "mac": (C.ACC2, "#fbf2d6"),
                "linux": (C.GREEN, C.GREEN_GHO)}
        for k, btn in self._os_btns.items():
            if k == key:
                fg, bg = pal[k]
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {fg}; color: {bg};
                        border: none; border-radius: 9px; font-weight: bold;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {C.PANEL}; color: {C.TEXT_DIM};
                        border: 1px solid {C.BORDER}; border-radius: 9px;
                    }}
                    QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
                """)

    def _submit(self):
        key = self._key_input.text().strip()
        if not key:
            self._key_input.setStyleSheet(
                self._key_input.styleSheet() +
                f" QLineEdit {{ border: 1px solid {C.RED}; }}"
            )
            return
        self.done.emit(key, self._sel_os)


class HueWheel(QWidget):
    """
    Circular colour picker. The user drags the handle (small white circle)
    around the wheel to choose from ALL hues. The filled circle in the centre
    is a live preview of the selected colour.
    """

    hue_picked    = pyqtSignal(str)   # while dragging (live)
    hue_committed = pyqtSignal(str)   # when the handle is released

    _RING = 16   # ring thickness (px)

    def __init__(self, initial_hex: str = DEFAULT_UI_COLOR, parent=None):
        super().__init__(parent)
        self.setFixedSize(148, 148)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hue  = 0.53
        self._drag = False
        self.set_color(initial_hex)

    # ── API ──────────────────────────────────────────────────────────────────
    def color(self) -> str:
        return QColor.fromHsvF(self._hue, 1.0, 1.0).name()

    def set_color(self, hex_str: str):
        c = QColor((hex_str or "").strip())
        if c.isValid() and c.hsvHueF() >= 0:
            self._hue = c.hsvHueF()
            self.update()

    # ── geometry helpers ─────────────────────────────────────────────────────
    def _ring_rect(self) -> QRectF:
        m = self._RING / 2 + 3
        return QRectF(self.rect()).adjusted(m, m, -m, -m)

    def _hue_from_pos(self, pos: QPointF) -> float:
        c  = QRectF(self.rect()).center()
        dx = pos.x() - c.x()
        dy = c.y() - pos.y()          # screen y goes down — flip to math axis
        ang = math.atan2(dy, dx)      # [-π, π], counter-clockwise
        return (ang / (2 * math.pi)) % 1.0

    # ── drawing ──────────────────────────────────────────────────────────────
    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect   = self._ring_rect()
        center = rect.center()

        grad = QConicalGradient(center, 0)
        for i in range(0, 361, 20):
            grad.setColorAt(i / 360.0, QColor.fromHsvF((i % 360) / 360.0, 1.0, 1.0))
        p.setPen(QPen(QBrush(grad), self._RING))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(rect)

        # centre preview circle
        preview = QColor.fromHsvF(self._hue, 1.0, 1.0)
        inner   = rect.adjusted(30, 30, -30, -30)
        p.setPen(QPen(qcol(C.BORDER_B), 1))
        p.setBrush(QBrush(preview))
        p.drawEllipse(inner)

        # draggable handle
        r   = rect.width() / 2
        ang = self._hue * 2 * math.pi
        hx  = center.x() + r * math.cos(ang)
        hy  = center.y() - r * math.sin(ang)
        p.setPen(QPen(qcol(C.WHITE), 2))
        p.setBrush(QBrush(qcol(C.PANEL)))
        p.drawEllipse(QPointF(hx, hy), 7.5, 7.5)
        p.end()

    # ── fare ─────────────────────────────────────────────────────────────────
    def mousePressEvent(self, e):
        self._drag = True
        self._hue  = self._hue_from_pos(e.position())
        self.update()
        self.hue_picked.emit(self.color())

    def mouseMoveEvent(self, e):
        if self._drag:
            self._hue = self._hue_from_pos(e.position())
            self.update()
            self.hue_picked.emit(self.color())

    def mouseReleaseEvent(self, e):
        if self._drag:
            self._drag = False
            self.hue_committed.emit(self.color())


class CustomizeOverlay(QWidget):
    """Floating overlay — change assistant name, user name, UI colour and voice."""

    saved = pyqtSignal(str, str, str, str)   # assistant_name, user_name, ui_color, voice
    _OW, _OH = 400, 588

    def __init__(self, assistant_name="LangVis", user_name="",
                 ui_color=DEFAULT_UI_COLOR, voice="", parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            CustomizeOverlay {{
                background: rgba(255, 255, 255, 246);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(8)

        def _lbl(txt, fs=9, bold=False, color=C.PRI, align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt); w.setAlignment(align)
            w.setFont(QFont(_UI_FONT, fs,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        _fs = (f"QLineEdit {{ background: {C.PANEL}; color: {C.TEXT}; "
               f"border: 1px solid {C.BORDER}; border-radius: 9px; padding: 5px 10px; }}"
               f"QLineEdit:focus {{ border: 1px solid {C.PRI}; }}")

        lay.addWidget(_lbl("⚙  CUSTOMISE ASSISTANT", 12, True))
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        lay.addWidget(_lbl("ASSISTANT NAME", 8, color=C.TEXT_DIM,
                            align=Qt.AlignmentFlag.AlignLeft))
        self._name_input = QLineEdit(assistant_name)
        self._name_input.setFont(QFont(_UI_FONT, 12))
        self._name_input.setFixedHeight(32)
        self._name_input.setStyleSheet(_fs)
        lay.addWidget(self._name_input)

        lay.addSpacing(4)
        lay.addWidget(_lbl("YOUR NAME  (leave blank for default sir / efendim)", 8,
                            color=C.TEXT_DIM, align=Qt.AlignmentFlag.AlignLeft))
        self._user_input = QLineEdit(user_name)
        self._user_input.setPlaceholderText("e.g.  Tony   (leave blank for auto)")
        self._user_input.setFont(QFont(_UI_FONT, 12))
        self._user_input.setFixedHeight(32)
        self._user_input.setStyleSheet(_fs)
        lay.addWidget(self._user_input)

        # ── Assistant voice — Gemini prebuilt voices ─────────────────────────
        # Names are language-neutral proper nouns, so the row reads the same in
        # every locale. Selecting one and applying rebuilds the Live session.
        from memory.config_manager import AVAILABLE_VOICES, DEFAULT_VOICE
        lay.addSpacing(4)
        lay.addWidget(_lbl("ASSISTANT VOICE", 8, color=C.TEXT_DIM,
                            align=Qt.AlignmentFlag.AlignLeft))
        self._sel_voice   = (voice or DEFAULT_VOICE)
        if self._sel_voice not in AVAILABLE_VOICES:
            self._sel_voice = DEFAULT_VOICE
        self._voice_btns: dict[str, QPushButton] = {}
        voice_row = QHBoxLayout(); voice_row.setSpacing(4)
        for _v in AVAILABLE_VOICES:
            b = QPushButton(_v)
            b.setCheckable(True)
            b.setFixedHeight(28)
            b.setFont(QFont(_UI_FONT, 10, QFont.Weight.Bold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, name=_v: self._on_voice_pick(name))
            self._voice_btns[_v] = b
            voice_row.addWidget(b)
        lay.addLayout(voice_row)
        self._refresh_voice_btns()

        # ── UI colour — colour wheel ─────────────────────────────────────────
        lay.addSpacing(4)
        clr_hdr = QHBoxLayout()
        clr_hdr.addWidget(_lbl("UI COLOUR  —  drag the handle", 8,
                               color=C.TEXT_DIM, align=Qt.AlignmentFlag.AlignLeft))
        clr_hdr.addStretch()
        df_btn = QPushButton("DEFAULT")
        df_btn.setFixedSize(64, 20)
        df_btn.setFont(QFont(_UI_FONT, 9, QFont.Weight.Bold))
        df_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        df_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 9px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        df_btn.clicked.connect(lambda: self._set_color(DEFAULT_UI_COLOR))
        clr_hdr.addWidget(df_btn)
        lay.addLayout(clr_hdr)

        self._initial_color = (ui_color or DEFAULT_UI_COLOR).strip().lower()
        self._sel_color     = self._initial_color
        self.on_preview     = None   # callable(hex) — live preview; MainWindow wires it

        self._wheel = HueWheel(self._sel_color)
        wheel_row = QHBoxLayout()
        wheel_row.addStretch(); wheel_row.addWidget(self._wheel); wheel_row.addStretch()
        lay.addLayout(wheel_row)
        self._wheel.hue_picked.connect(self._on_wheel_pick)
        self._wheel.hue_committed.connect(self._on_wheel_commit)

        self._hex_input = QLineEdit(self._sel_color)
        self._hex_input.setPlaceholderText(f"{DEFAULT_UI_COLOR}   (custom hex colour)")
        self._hex_input.setFont(QFont(_UI_FONT, 12))
        self._hex_input.setFixedHeight(28)
        self._hex_input.setStyleSheet(_fs)
        self._hex_input.textEdited.connect(self._on_hex_edited)
        lay.addWidget(self._hex_input)

        lay.addSpacing(6)
        btn_row = QHBoxLayout(); btn_row.setSpacing(8)

        save_btn = QPushButton("▸  APPLY CHANGES")
        save_btn.setFixedHeight(34)
        save_btn.setFont(QFont(_UI_FONT, 11, QFont.Weight.Bold))
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 9px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
        """)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        cancel_btn = QPushButton("CANCEL")
        cancel_btn.setFixedHeight(34)
        cancel_btn.setFont(QFont(_UI_FONT, 11))
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 9px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        cancel_btn.clicked.connect(self._cancel)
        btn_row.addWidget(cancel_btn)
        lay.addLayout(btn_row)

    # ── voice selection ──────────────────────────────────────────────────────
    def _on_voice_pick(self, name: str):
        self._sel_voice = name
        self._refresh_voice_btns()

    def _refresh_voice_btns(self):
        """Highlight the selected voice pill; dim the rest."""
        for name, b in self._voice_btns.items():
            on = (name == self._sel_voice)
            b.setChecked(on)
            if on:
                b.setStyleSheet(f"""
                    QPushButton {{ background: {C.PRI_GHO}; color: {C.PRI};
                        border: 1px solid {C.PRI}; border-radius: 9px; }}
                """)
            else:
                b.setStyleSheet(f"""
                    QPushButton {{ background: transparent; color: {C.TEXT_MED};
                        border: 1px solid {C.BORDER}; border-radius: 9px; }}
                    QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
                """)

    # ── colour flow ──────────────────────────────────────────────────────────
    def _set_color(self, hx: str, update_wheel: bool = True, preview: bool = True):
        """Updates the selected colour; hex box + wheel stay in sync, theme is live-previewed."""
        self._sel_color = hx.strip().lower()
        self._hex_input.blockSignals(True)
        self._hex_input.setText(self._sel_color)
        self._hex_input.blockSignals(False)
        if update_wheel:
            self._wheel.set_color(self._sel_color)
        if preview and self.on_preview:
            self.on_preview(self._sel_color)

    def _on_wheel_pick(self, hx: str):
        # While dragging: update the hex box, don't apply the theme yet
        self._sel_color = hx
        self._hex_input.blockSignals(True)
        self._hex_input.setText(hx)
        self._hex_input.blockSignals(False)

    def _on_wheel_commit(self, hx: str):
        # Handle released → live-preview the whole interface
        self._set_color(hx, update_wheel=False)

    def _on_hex_edited(self, text: str):
        t = text.strip().lower()
        if t.startswith("#") and len(t) == 7:
            try:
                int(t[1:], 16)
            except ValueError:
                return
            self._set_color(t, update_wheel=True, preview=True)

    def _cancel(self):
        # If a preview was applied, revert to the colour from launch
        if self.on_preview and self._sel_color != self._initial_color:
            self.on_preview(self._initial_color)
        self.hide()

    def _save(self):
        name = self._name_input.text().strip() or "LangVis"
        user = self._user_input.text().strip()
        self.saved.emit(name, user, self._sel_color or DEFAULT_UI_COLOR, self._sel_voice)
        self.hide()


class _HudOverlay(QWidget):
    """Base for the floating panels placed by hand over the HUD.

    They are children of the central widget but sit in no layout, so Qt never
    invalidates the region they occupy when they hide or shrink: the HUD keeps
    painting around them and their last frame stays on screen as a ghost. Any
    overlay positioned with _centre_overlay needs this."""

    def hideEvent(self, e):
        p = self.parentWidget()
        if p is not None:
            # Repaint exactly what we were covering, before we stop covering it.
            p.update(self.geometry())
        super().hideEvent(e)

    def closeEvent(self, e):
        p = self.parentWidget()
        if p is not None:
            p.update(self.geometry())
        super().closeEvent(e)


class AudioDeviceOverlay(_HudOverlay):
    """Choose which microphone LangVis listens to and which speakers it uses.

    Both audio streams used to open with no `device=` at all, so they always
    took the OS default — which on Windows moves by itself the moment a headset
    is plugged in. 'LangVis can't hear me' is usually 'LangVis is listening to the
    webcam'."""

    picked = pyqtSignal()      # emitted after Apply, when something changed
    _OW = 460

    def __init__(self, parent=None):
        super().__init__(parent)
        from core.audio_devices import list_devices, DEFAULT_LABEL
        from memory.config_manager import get_input_device, get_output_device

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            AudioDeviceOverlay {{
                background: rgba(255, 255, 255, 246);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._OW)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(6)

        hdr = QLabel("🎧  AUDIO DEVICES")
        hdr.setFont(QFont(_UI_FONT, 13, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        lay.addWidget(hdr)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        _combo_css = combo_style(10)

        def _row(label: str, kind: str, current: str) -> QComboBox:
            cap = QLabel(label)
            cap.setFont(QFont(_UI_FONT, 10))
            cap.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            lay.addWidget(cap)

            box = QComboBox()
            box.setFont(QFont(_UI_FONT, 11))
            box.setFixedHeight(34)
            box.setStyleSheet(_combo_css)
            # The list is served from a cache warmed on a background thread at
            # startup, so opening this panel never blocks the Qt thread on the
            # host audio API.
            box.addItem(DEFAULT_LABEL, "")
            for name in list_devices(kind):
                box.addItem(name, name)
            idx = box.findData(current) if current else 0
            box.setCurrentIndex(idx if idx >= 0 else 0)
            if current and idx < 0:
                # Saved device is not plugged in right now. Show it rather than
                # silently resetting the user's choice to default.
                box.addItem(f"{current}  (not connected)", current)
                box.setCurrentIndex(box.count() - 1)
            lay.addWidget(box)
            return box

        self._in_box  = _row("MICROPHONE — what LangVis hears you with",
                             "input", get_input_device())
        lay.addSpacing(4)
        self._out_box = _row("SPEAKERS — what LangVis talks through",
                             "output", get_output_device())

        note = QLabel("Applying reconnects the session. Your conversation is kept.")
        note.setWordWrap(True)
        note.setFont(QFont(_UI_FONT, 9))
        note.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addSpacing(6)
        lay.addWidget(note)

        row = QHBoxLayout(); row.setSpacing(8)
        ok = QPushButton("▸  APPLY")
        ok.setFixedHeight(32)
        ok.setFont(QFont(_UI_FONT, 11, QFont.Weight.Bold))
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 9px; }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border-color: {C.PRI}; }}
        """)
        ok.clicked.connect(self._apply)
        row.addWidget(ok)

        cancel = QPushButton("CLOSE")
        cancel.setFixedHeight(32)
        cancel.setFont(QFont(_UI_FONT, 11))
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 9px; }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        cancel.clicked.connect(self.hide)
        row.addWidget(cancel)
        lay.addLayout(row)

    def _apply(self):
        from memory.config_manager import (
            get_input_device, get_output_device,
            save_input_device, save_output_device,
        )
        new_in  = self._in_box.currentData()  or ""
        new_out = self._out_box.currentData() or ""
        changed = (new_in != get_input_device()) or (new_out != get_output_device())
        save_input_device(new_in)
        save_output_device(new_out)
        self.hide()
        # Only rebuild the session if something actually moved — a no-op Apply
        # should not cost a reconnect.
        if changed:
            self.picked.emit()


class MemoryOverlay(_HudOverlay):
    """Everything LangVis has stored about you, and when it learned it.

    Memory used to be a 2200-character store that deleted its oldest entries
    when full and mentioned it only on stdout. The cap is gone; this panel is
    the other half of that change — a memory you cannot inspect is a memory you
    cannot trust, and 'delete' has to be something the person can do."""

    _OW = 520

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            MemoryOverlay {{
                background: rgba(255, 255, 255, 247);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._OW)

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(20, 16, 20, 16)
        self._lay.setSpacing(5)
        self._rebuild()

    def _clear_layout(self):
        """Take every item out of the layout and detach it from the widget tree
        in this call.

        deleteLater() on its own is not enough: it queues destruction for the
        next event-loop pass, and until then the old rows are still children of
        this widget and still paint — which is what drew half of the previous
        panel over the new one. setParent(None) removes them from the tree now;
        deleteLater() then frees them safely."""
        while self._lay.count():
            item = self._lay.takeAt(0)
            w = item.widget()
            if w is not None:
                # hide() stops it painting in this frame; deleteLater() frees it
                # safely afterwards. setParent(None) would also stop the paint,
                # but it turns the widget into a top-level window for the moment
                # between the two calls, which is not something to leave lying
                # around inside a click handler.
                w.hide()
                w.deleteLater()
                continue
            sub = item.layout()
            if sub is not None:
                while sub.count():
                    si = sub.takeAt(0)
                    sw = si.widget()
                    if sw is not None:
                        sw.hide()
                        sw.deleteLater()
                sub.deleteLater()

    def _settle(self, before):
        """Size the panel to its content, re-centre it, and repaint what the old
        size covered.

        The re-size has to happen here rather than at the end of _rebuild
        because Qt has not polished the freshly-created children at that point,
        so the size hint it would read is the empty-layout one. Measured: a
        first adjustSize() returned 32 px for a panel whose content needed 155,
        and a second call — after the same widgets had been through the event
        loop — returned 155. So this runs twice: once now, once on the next
        turn, from _rebuild.

        The re-centre and the repaint are needed because the overlay is placed
        by hand and is in no layout: shrinking it leaves it off-centre and
        leaves its former pixels on screen, since nothing tells the parent that
        region changed. The repaint has to cover the union of the old and new
        rectangles."""
        self._lay.invalidate()
        self._lay.activate()
        self.updateGeometry()
        self.adjustSize()

        p = self.parentWidget()
        if p is None:
            self.update()
            return
        self.move(max(0, (p.width()  - self.width())  // 2),
                  max(0, (p.height() - self.height()) // 2))
        p.update(before.united(self.geometry()))
        self.update()

    def _rebuild(self):
        before = self.geometry()
        self._clear_layout()

        from memory.memory_manager import all_entries_for_ui

        hdr = QLabel("🧠  WHAT LangVis REMEMBERS")
        hdr.setFont(QFont(_UI_FONT, 13, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        self._lay.addWidget(hdr)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        self._lay.addWidget(sep)

        rows = all_entries_for_ui()

        cap = QLabel(f"{len(rows)} stored facts — newest first. "
                     f"Nothing here is sent anywhere; it lives in "
                     f"memory/long_term.json on this machine.")
        cap.setWordWrap(True)
        cap.setFont(QFont(_UI_FONT, 9))
        cap.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._lay.addWidget(cap)

        if not rows:
            empty = QLabel("Nothing stored yet.")
            empty.setFont(QFont(_UI_FONT, 11))
            empty.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
            self._lay.addWidget(empty)
        else:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFixedHeight(min(420, 34 * len(rows) + 10))
            scroll.setStyleSheet(
                f"QScrollArea {{ border: 1px solid {C.BORDER}; border-radius: 9px; "
                f"background: transparent; }}"
            )
            inner = QWidget()
            ilay  = QVBoxLayout(inner)
            ilay.setContentsMargins(6, 6, 6, 6)
            ilay.setSpacing(3)

            for r in rows:
                line = QHBoxLayout(); line.setSpacing(6)
                txt = QLabel(f"<b>{r['key'].replace('_', ' ')}</b> "
                             f"<span style='color:{C.TEXT_MED}'>— {r['value']}</span>")
                txt.setWordWrap(True)
                txt.setFont(QFont(_UI_FONT, 10))
                txt.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
                line.addWidget(txt, 1)

                meta = QLabel(f"{r['category'][:4]} · {r['updated'] or '—'}")
                meta.setFont(QFont(_UI_FONT, 9))
                meta.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
                line.addWidget(meta)

                rm = QPushButton("✕")
                rm.setFixedSize(20, 20)
                rm.setFont(QFont(_UI_FONT, 10, QFont.Weight.Bold))
                rm.setCursor(Qt.CursorShape.PointingHandCursor)
                rm.setToolTip("Forget this")
                rm.setStyleSheet(f"""
                    QPushButton {{ background: transparent; color: {C.TEXT_DIM};
                        border: 1px solid {C.BORDER}; border-radius: 9px; }}
                    QPushButton:hover {{ color: {C.RED}; border-color: {C.RED}; }}
                """)
                rm.clicked.connect(
                    lambda _=False, c=r["category"], k=r["key"]: self._forget(c, k))
                line.addWidget(rm)

                holder = QWidget()
                holder.setLayout(line)
                ilay.addWidget(holder)

            ilay.addStretch()
            scroll.setWidget(inner)
            self._lay.addWidget(scroll)

        close = QPushButton("CLOSE")
        close.setFixedHeight(30)
        close.setFont(QFont(_UI_FONT, 11))
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 9px; }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        close.clicked.connect(self.hide)
        self._lay.addWidget(close)

        self._settle(before)
        # …and again once Qt has polished the new children, because the size
        # hint is not final until then. Harmless when the first pass already
        # got it right: _settle is idempotent.
        QTimer.singleShot(0, lambda g=before: self._settle(g))

    def _forget(self, category: str, key: str):
        from memory.memory_manager import forget
        forget(key, category)
        # Rebuild on the NEXT event-loop turn, not inside this click handler.
        # The rebuild destroys the very ✕ button that emitted this signal, and
        # Qt is entitled to touch the sender after a slot returns; tearing it
        # down mid-emission is how a widget ends up half-alive on screen.
        QTimer.singleShot(0, self._rebuild)


class PluginSettingsOverlay(QWidget):
    """Floating overlay — renders per-plugin settings forms.

    Fully generic: it iterates the settings schemas a plugin declared via its
    PLUGIN_SETTINGS constant (delivered by PluginRegistry.settings_schemas) and
    builds a form for each. It knows NOTHING about any specific plugin, so the
    core stays clean and plugins remain pure drop-in — install a plugin that
    declares fields (e.g. the 3D-printer suite) and its section appears here;
    install none and this panel simply says there's nothing to configure.
    """

    _test_done = pyqtSignal(str, bool, str)   # namespace, ok, message
    _OW = 460

    def __init__(self, sections: list[dict], parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            PluginSettingsOverlay {{
                background: rgba(255, 255, 255, 246);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self._sections = sections or []
        self._widgets: dict[tuple, object] = {}    # (namespace, key) -> input widget
        self._types:   dict[tuple, str]    = {}     # (namespace, key) -> field type
        self._status_labels: dict[str, QLabel] = {} # namespace -> status QLabel
        self._test_done.connect(self._on_test_done)

        self._fs = (f"QLineEdit {{ background: {C.PANEL}; color: {C.TEXT}; "
                    f"border: 1px solid {C.BORDER}; border-radius: 9px; padding: 5px 10px; }}"
                    f"QLineEdit:focus {{ border: 1px solid {C.PRI}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 16, 22, 16)
        root.setSpacing(8)

        root.addWidget(self._lbl("⚙  PLUGIN SETTINGS", 12, True))
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        root.addWidget(sep)

        if not self._sections:
            root.addWidget(self._lbl(
                "No configurable plugins are installed.\nDrop a plugin that needs "
                "settings (like the 3D-printer suite) into the plugins folder and "
                "it will show up here.", 9, color=C.TEXT_DIM))
        else:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setStyleSheet("QScrollArea { background: transparent; }")
            inner = QWidget()
            inner.setStyleSheet("background: transparent;")
            form = QVBoxLayout(inner)
            form.setContentsMargins(0, 0, 6, 0)
            form.setSpacing(6)
            for sec in self._sections:
                self._build_section(form, sec)
            form.addStretch(1)
            scroll.setWidget(inner)
            root.addWidget(scroll, 1)

        # ── bottom buttons ───────────────────────────────────────────────────
        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        if self._sections:
            save_btn = QPushButton("▸  SAVE")
            save_btn.setFixedHeight(34)
            save_btn.setFont(QFont(_UI_FONT, 11, QFont.Weight.Bold))
            save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            save_btn.setStyleSheet(f"""
                QPushButton {{ background: transparent; color: {C.PRI};
                    border: 1px solid {C.PRI_DIM}; border-radius: 9px; }}
                QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
            """)
            save_btn.clicked.connect(self._save_all)
            btn_row.addWidget(save_btn)

        close_btn = QPushButton("CLOSE")
        close_btn.setFixedHeight(34)
        close_btn.setFont(QFont(_UI_FONT, 11))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 9px; }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        close_btn.clicked.connect(self.hide)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

    # ── helpers ───────────────────────────────────────────────────────────────
    def _lbl(self, txt, fs=9, bold=False, color=C.PRI,
             align=Qt.AlignmentFlag.AlignLeft):
        w = QLabel(txt); w.setAlignment(align); w.setWordWrap(True)
        w.setFont(QFont(_UI_FONT, fs,
                        QFont.Weight.Bold if bold else QFont.Weight.Normal))
        w.setStyleSheet(f"color: {color}; background: transparent;")
        return w

    def _build_section(self, form: QVBoxLayout, sec: dict):
        ns     = sec.get("namespace") or sec.get("plugin") or "plugin"
        title  = sec.get("title") or ns
        fields = sec.get("fields") or []
        values = sec.get("values") or {}

        form.addSpacing(4)
        form.addWidget(self._lbl(title, 10, True, C.PRI))

        for field in fields:
            if not isinstance(field, dict) or not field.get("key"):
                continue
            key   = field["key"]
            ftype = (field.get("type") or "text").lower()
            label = field.get("label") or key
            default = field.get("default")
            stored  = values.get(key, default)

            form.addWidget(self._lbl(label.upper(), 8, color=C.TEXT_DIM))

            if ftype == "choice":
                w = QComboBox()
                w.addItems([str(o) for o in field.get("options", [])])
                w.setFont(QFont(_UI_FONT, 11))
                w.setFixedHeight(34)
                w.setStyleSheet(combo_style(10))
                if stored is not None:
                    w.setCurrentText(str(stored))
            elif ftype == "toggle":
                w = QPushButton()
                w.setCheckable(True)
                w.setChecked(bool(stored))
                w.setFixedHeight(28)
                w.setFont(QFont(_UI_FONT, 10, QFont.Weight.Bold))
                w.setCursor(Qt.CursorShape.PointingHandCursor)
                self._style_toggle(w)
                w.toggled.connect(lambda _=False, b=w: self._style_toggle(b))
            else:  # text / password
                w = QLineEdit("" if stored is None else str(stored))
                w.setFont(QFont(_UI_FONT, 12))
                w.setFixedHeight(34)
                w.setStyleSheet(self._fs)
                if field.get("placeholder"):
                    w.setPlaceholderText(str(field["placeholder"]))
                if ftype == "password":
                    w.setEchoMode(QLineEdit.EchoMode.Password)

            self._widgets[(ns, key)] = w
            self._types[(ns, key)]   = ftype
            form.addWidget(w)

        # optional test/connect action button + status line
        action = sec.get("action")
        if isinstance(action, dict) and callable(action.get("run")):
            form.addSpacing(2)
            ab = QPushButton(str(action.get("label") or "TEST"))
            ab.setFixedHeight(30)
            ab.setFont(QFont(_UI_FONT, 10, QFont.Weight.Bold))
            ab.setCursor(Qt.CursorShape.PointingHandCursor)
            ab.setStyleSheet(f"""
                QPushButton {{ background: {C.PRI_GHO}; color: {C.PRI};
                    border: 1px solid {C.PRI_DIM}; border-radius: 9px; }}
                QPushButton:hover {{ background: {C.PRI_GHO}; border-color: {C.PRI}; }}
            """)
            ab.clicked.connect(lambda _=False, n=ns: self._run_action(n))
            form.addWidget(ab)

        status = self._lbl("", 8, color=C.TEXT_DIM)
        self._status_labels[ns] = status
        form.addWidget(status)

        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {C.BORDER}; margin: 4px 0;")
        form.addWidget(line)

    def _style_toggle(self, btn: QPushButton):
        on = btn.isChecked()
        btn.setText("ON" if on else "OFF")
        if on:
            btn.setStyleSheet(btn_tone(C.PRI, C.PRI_GHO, C.PRI, 9).replace(
                "text-align: left;", "text-align: center;"))
        else:
            btn.setStyleSheet(btn_soft(9).replace(
                "text-align: left;", "text-align: center;"))

    # ── data ──────────────────────────────────────────────────────────────────
    def _gather(self, ns: str) -> dict:
        out = {}
        for (n, key), w in self._widgets.items():
            if n != ns:
                continue
            t = self._types.get((n, key), "text")
            if t == "choice":
                out[key] = w.currentText()
            elif t == "toggle":
                out[key] = w.isChecked()
            else:
                out[key] = w.text().strip()
        return out

    def _save_ns(self, ns: str):
        from memory.config_manager import save_plugin_config
        save_plugin_config(ns, self._gather(ns))

    def _save_all(self):
        for sec in self._sections:
            ns = sec.get("namespace") or sec.get("plugin")
            if ns:
                self._save_ns(ns)
                lbl = self._status_labels.get(ns)
                if lbl:
                    lbl.setText("Saved ✓")
                    lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")

    def _run_action(self, ns: str):
        sec = next((s for s in self._sections
                    if (s.get("namespace") or s.get("plugin")) == ns), None)
        if not sec:
            return
        run_fn = (sec.get("action") or {}).get("run")
        if not callable(run_fn):
            return
        self._save_ns(ns)                 # persist what the user typed before testing
        values = self._gather(ns)
        lbl = self._status_labels.get(ns)
        if lbl:
            lbl.setText("Testing…")
            lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")

        def worker():
            try:
                res = run_fn(values)
                if isinstance(res, tuple) and len(res) == 2:
                    ok, msg = bool(res[0]), str(res[1])
                else:
                    ok, msg = bool(res), str(res)
            except Exception as e:
                ok, msg = False, str(e)
            self._test_done.emit(ns, ok, msg)

        threading.Thread(target=worker, daemon=True).start()

    def _on_test_done(self, ns: str, ok: bool, msg: str):
        lbl = self._status_labels.get(ns)
        if not lbl:
            return
        lbl.setText(msg)
        color = C.PRI if ok else C.RED
        lbl.setStyleSheet(f"color: {color}; background: transparent;")


class AssistantPanel(QScrollArea):
    """The middle of the window: what you just said, and what to do about it.

    The transcript is closed by default, which leaves this the largest thing on
    screen — so it is where the actual teaching is shown rather than a status
    readout. Four blocks, in the order a learner reads them:

        YOU SAID     their sentence, the wrong parts in red
        CORRECTED    the same sentence fixed, the repairs in green
        SAY IT BETTER  one level up, using a word the unit is installing
        TIP          the rule behind the mistake, with two examples

    When the sentence was already right, the first two collapse into one green
    line and only "say it better" remains: nothing is invented to fill space.

    Polled once a second from the Qt thread; the card itself is built by the
    tutor plugin (see build_card) and held in memory.
    """

    POLL_MS = 900

    def __init__(self, parent=None):
        super().__init__(parent)
        self.get_coaching = None          # set by LangVisUI; () -> dict
        self._stamp = None

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(f"QScrollArea {{ background: {C.BG}; border: none; }}"
                           + scrollbar_style())

        inner = QWidget()
        inner.setStyleSheet(f"background: {C.BG};")
        self._lay = QVBoxLayout(inner)
        self._lay.setContentsMargins(0, 0, 4, 0)
        self._lay.setSpacing(10)
        self.setWidget(inner)

        # ── waiting state ────────────────────────────────────────────────────
        self._idle = QLabel("Say something in English.\nYour sentence, the fix and "
                            "the rule behind it appear here.")
        self._idle.setFont(font(11))
        self._idle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._idle.setWordWrap(True)
        self._idle.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._lay.addWidget(self._idle)

        # ── the sentence, then the fix ───────────────────────────────────────
        self._said_card, self._said_cap, self._said_body = self._card(
            "YOU SAID", C.TEXT_DIM)
        self._fix_card, self._fix_cap, self._fix_body = self._card(
            "CORRECTED", C.GREEN)
        self._notes = QLabel("")
        self._notes.setFont(font(10))
        self._notes.setWordWrap(True)
        self._notes.setTextFormat(Qt.TextFormat.RichText)
        self._notes.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self._fix_card.layout().addWidget(self._notes)

        # ── the rule behind the mistake ──────────────────────────────────────
        self._tip_card, self._tip_cap, self._tip_body = self._card(
            "TIP", C.ACC, fill=C.PANEL)
        self._tip_card.setStyleSheet(
            f"QWidget#Card {{ background: {C.PANEL}; border: 1px solid {C.BORDER_A};"
            f" border-left: 3px solid {C.ACC}; border-radius: 12px; }}")
        self._tip_examples = QLabel("")
        self._tip_examples.setFont(font(10))
        self._tip_examples.setWordWrap(True)
        self._tip_examples.setTextFormat(Qt.TextFormat.RichText)
        self._tip_examples.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self._tip_card.layout().addWidget(self._tip_examples)

        # ── a better version, one level up ───────────────────────────────────
        self._better_card, self._better_cap, self._better_body = self._card(
            "SAY IT BETTER", C.PRI, fill=C.PRI_GHO)
        self._better_uses = QLabel("")
        self._better_uses.setFont(font(9))
        self._better_uses.setWordWrap(True)
        self._better_uses.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        self._better_card.layout().addWidget(self._better_uses)

        self._lay.addStretch(1)

        for card in (self._said_card, self._fix_card, self._better_card,
                     self._tip_card):
            card.hide()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(self.POLL_MS)

    # ── one card ─────────────────────────────────────────────────────────────

    def _card(self, caption: str, ink: str, fill: str = "") -> tuple:
        card = QWidget()
        card.setObjectName("Card")
        card.setStyleSheet(
            f"QWidget#Card {{ background: {fill or C.PANEL}; border: 1px solid "
            f"{C.BORDER_A}; border-radius: 12px; }}")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 10, 14, 12)
        lay.setSpacing(5)

        cap = QLabel(caption)
        cap.setFont(font(9, True))
        cap.setStyleSheet(f"color: {ink}; background: transparent; border: none;"
                          f"letter-spacing: 1px;")
        lay.addWidget(cap)

        body = QLabel("")
        body.setFont(font(14))
        body.setWordWrap(True)
        body.setTextFormat(Qt.TextFormat.RichText)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setStyleSheet(f"color: {C.WHITE}; background: transparent; border: none;")
        lay.addWidget(body)

        self._lay.insertWidget(self._lay.count(), card)
        return card, cap, body

    # ── rendering ────────────────────────────────────────────────────────────

    @staticmethod
    def _tokens_html(tokens: list, key: str, ink: str, plain: str,
                     underline: bool = False) -> str:
        import html as _html
        out = []
        for t in tokens:
            text = _html.escape(str(t.get("text", "")))
            if t.get(key):
                deco = "underline" if underline else "none"
                out.append(f'<span style="color:{ink}; font-weight:700; '
                           f'text-decoration:{deco};">{text}</span>')
            else:
                out.append(f'<span style="color:{plain};">{text}</span>')
        return " ".join(out)

    def _refresh(self):
        # A readout must never be able to take the window down.
        try:
            card = self.get_coaching() if callable(self.get_coaching) else {}
        except Exception:
            card = {}
        if not card or not card.get("said"):
            return
        if card.get("stamp") == self._stamp:
            return
        self._stamp = card.get("stamp")
        self._idle.hide()
        QTimer.singleShot(0, lambda: self.verticalScrollBar().setValue(0))

        import html as _html
        clean = bool(card.get("clean"))

        # YOU SAID — red on the parts that need work
        self._said_body.setText(self._tokens_html(
            card.get("said_tokens", []), "bad", C.RED, C.WHITE, underline=True))
        self._said_cap.setText("YOU SAID" if not clean else "YOU SAID — correct")
        self._said_cap.setStyleSheet(
            f"color: {C.GREEN if clean else C.TEXT_DIM}; background: transparent;"
            f"border: none; letter-spacing: 1px;")
        self._said_card.show()

        # CORRECTED — green on the repairs, with the reason under it
        if clean:
            self._fix_card.hide()
        else:
            self._fix_body.setText(self._tokens_html(
                card.get("fixed_tokens", []), "fixed", C.GREEN, C.WHITE))
            notes = []
            for fix in card.get("fixes", []):
                wrong = _html.escape(fix.get("wrong", ""))
                right = _html.escape(fix.get("right", ""))
                why = _html.escape(fix.get("why", ""))
                skill = _html.escape(fix.get("skill", ""))
                notes.append(
                    f'<span style="color:{C.RED};">{wrong}</span> '
                    f'→ <span style="color:{C.GREEN};">{right}</span>'
                    f'<span style="color:{C.TEXT_DIM};"> &nbsp;{skill}'
                    + (f": {why}" if why else "") + "</span>")
            self._notes.setText("<br>".join(notes))
            self._notes.setVisible(bool(notes))
            self._fix_card.show()

        # SAY IT BETTER — the improvement, and which target words it used
        better = card.get("improved", "")
        if better:
            self._better_body.setText(
                f'<span style="color:{C.WHITE};">{_html.escape(better)}</span>')
            uses = card.get("improved_uses", [])
            self._better_uses.setText(
                ("uses: " + ", ".join(uses)) if uses else "")
            self._better_uses.setVisible(bool(uses))
            self._better_cap.setText(
                "SAY IT BETTER" if not clean else "CORRECT — NOW SAY IT BETTER")
            self._better_card.show()
        else:
            self._better_card.hide()

        # TIP — the rule behind the first mistake
        tip = card.get("tip") or {}
        if tip.get("rule"):
            self._tip_cap.setText(f"TIP · {tip.get('title', '').upper()}")
            self._tip_body.setFont(font(11))
            self._tip_body.setText(
                f'<span style="color:{C.WHITE};">{_html.escape(tip["rule"])}</span>')
            self._tip_examples.setText("<br>".join(
                f'<span style="color:{C.PRI};">•</span> '
                f'<i>{_html.escape(ex)}</i>' for ex in tip.get("examples", [])))
            self._tip_card.show()
        else:
            self._tip_card.hide()


class ChecklistStrip(QWidget):
    """The unit's words and phrasal verbs, ticked off as they are used.

    The tutor keeps feeding these into the conversation; this is the learner's
    side of that bargain — what is still owed, and what is already theirs. An
    item ticks after two uses in their own sentences, never on hearing it.
    """

    POLL_MS = 1200

    def __init__(self, parent=None):
        super().__init__(parent)
        self.get_coaching = None
        self._signature = None
        self.setStyleSheet(f"background: {C.PANEL}; border: 1px solid {C.BORDER_A};"
                           f"border-radius: 12px;")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(14, 10, 14, 11)
        self._lay.setSpacing(7)

        head = QHBoxLayout()
        self._cap = QLabel("WORDS TO USE")
        self._cap.setFont(font(9, True))
        self._cap.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;"
                                f"border: none; letter-spacing: 1px;")
        head.addWidget(self._cap)
        head.addStretch()
        self._count = QLabel("")
        self._count.setFont(font(9, True))
        self._count.setStyleSheet(f"color: {C.PRI}; background: transparent;"
                                  f"border: none;")
        head.addWidget(self._count)
        self._lay.addLayout(head)

        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(6)
        self._grid.setVerticalSpacing(5)
        self._lay.addLayout(self._grid)
        self._chips: list[QLabel] = []

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(self.POLL_MS)
        self._refresh()

    def _chip(self, index: int) -> QLabel:
        while len(self._chips) <= index:
            lbl = QLabel()
            lbl.setFont(font(10))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._grid.addWidget(lbl, len(self._chips) // 4, len(self._chips) % 4)
            self._chips.append(lbl)
        return self._chips[index]

    def _refresh(self):
        try:
            card = self.get_coaching() if callable(self.get_coaching) else {}
            lex = (card or {}).get("checklist") or {}
        except Exception:
            lex = {}
        rows = [(r, "word") for r in lex.get("words", [])] + \
               [(r, "phrasal") for r in lex.get("phrasals", [])]
        sig = [(r["text"], r["checked"], r["uses"]) for r, _ in rows]
        if sig == self._signature:
            return
        self._signature = sig

        self._count.setText(
            f"{lex.get('words_done', 0)}/{lex.get('words_needed', 0)} words  ·  "
            f"{lex.get('phrasals_done', 0)}/{lex.get('phrasals_needed', 0)} phrasals"
            if rows else "")

        for i, (row, kind) in enumerate(rows):
            chip = self._chip(i)
            mark = "✓ " if row["checked"] else ""
            trail = "" if row["checked"] else (f"  {row['uses']}/2" if row["uses"] else "")
            chip.setText(f"{mark}{row['text']}{trail}")
            if row["checked"]:
                chip.setStyleSheet(pill_style(C.GREEN, C.GREEN_GHO, 10))
            elif kind == "phrasal":
                chip.setStyleSheet(pill_style(C.PRI, C.PRI_GHO, 10))
            else:
                chip.setStyleSheet(pill_style(C.TEXT_MED, C.PANEL2, 10))
            chip.show()
        for i in range(len(rows), len(self._chips)):
            self._chips[i].hide()


class UnitRow(QWidget):
    """One unit in the syllabus: its number, its title and its state.

    Two lines, never three: the number and title, then the grammar it teaches,
    cut off with an ellipsis rather than wrapped. The methods and the sentences
    live in the sheet that opens on click — a list that tries to say everything
    stops being a list you can scan.
    """

    clicked = pyqtSignal(dict)
    _HEIGHT = 46

    def __init__(self, unit: dict, width: int, parent=None):
        super().__init__(parent)
        self._unit = unit
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(self._HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        status = unit.get("status", "todo")
        if status == "done":
            fill, edge, ink, sub = C.GREEN_GHO, C.GREEN_GHO, C.TEXT_MED, C.TEXT_DIM
        elif status == "current":
            fill, edge, ink, sub = C.PRI_GHO, C.PRI, C.WHITE, C.PRI
        else:
            fill, edge, ink, sub = C.PANEL, C.BORDER_A, C.TEXT, C.TEXT_DIM
        # A row's state is the colour of its left bar; the rest of the outline
        # stays as quiet as the cards around it.
        self.setStyleSheet(
            f"UnitRow {{ background: {fill}; border: 1px solid {edge};"
            f" border-left: 3px solid {edge if status != 'todo' else C.BORDER_A};"
            f" border-radius: 9px; }}"
            f"UnitRow:hover {{ border-color: {C.BORDER_B}; }}")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(9, 5, 9, 5)
        lay.setSpacing(8)

        num = QLabel("✓" if status == "done" else f"{unit['number']}")
        num.setFont(font(10, True))
        num.setFixedWidth(16)
        num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        num.setStyleSheet(
            f"color: {C.GREEN if status == 'done' else sub};"
            f"background: transparent; border: none;")
        lay.addWidget(num)

        col = QVBoxLayout()
        col.setSpacing(1)
        col.setContentsMargins(0, 0, 0, 0)
        text_w = max(80, width - 90)

        title = QLabel(self._elide(unit["title"], font(11, status == "current"), text_w))
        title.setFont(font(11, status == "current"))
        title.setStyleSheet(f"color: {ink}; background: transparent; border: none;")
        col.addWidget(title)

        grammar = QLabel(self._elide(", ".join(unit.get("skills", [])), font(9), text_w))
        grammar.setFont(font(9))
        grammar.setStyleSheet(f"color: {sub}; background: transparent; border: none;")
        col.addWidget(grammar)
        lay.addLayout(col, stretch=1)

        if status == "current":
            pct = QLabel(f"{int(unit.get('progress', 0))}%")
            pct.setFont(font(9, True))
            pct.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none;")
            lay.addWidget(pct, alignment=Qt.AlignmentFlag.AlignVCenter)

    @staticmethod
    def _elide(text: str, f: QFont, width: int) -> str:
        return QFontMetrics(f).elidedText(text, Qt.TextElideMode.ElideRight, width)

    def mousePressEvent(self, e):
        self.clicked.emit(self._unit)


class SyllabusPanel(QScrollArea):
    """The whole course, in order, with the learner's place in it.

    A learner who cannot see the road does not believe there is one — so every
    stage and all twenty-four units are listed, finished ones ticked, the
    current one marked, and each row opens the unit's sentences and methods.

    Polled once a second from the Qt thread: the numbers live in a plugin that
    knows nothing about Qt, and it only re-reads its file when it changes.
    """

    POLL_MS = 1500
    unit_opened = pyqtSignal(dict)
    refresh_now = pyqtSignal()          # thread-safe "rebuild me"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.get_syllabus = None      # set by LangVisUI; () -> list[dict]
        self._signature = None

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(f"QScrollArea {{ background: {C.DARK}; border: none; }}"
                           + scrollbar_style())

        self._inner = QWidget()
        self._inner.setStyleSheet(f"background: {C.DARK};")
        self._lay = QVBoxLayout(self._inner)
        # The right margin is the scrollbar's lane: without it the bar sits on
        # top of the rows and the percentages disappear behind it.
        self._lay.setContentsMargins(0, 0, 12, 10)
        self._lay.setSpacing(5)
        self._lay.addStretch(1)
        self.setWidget(self._inner)

        self.refresh_now.connect(self._rebuild)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(self.POLL_MS)
        self._refresh()

    def _rebuild(self):
        """Slot: forget what was on screen and draw the list again."""
        self._signature = None
        self._refresh()

    # ── little builders ──────────────────────────────────────────────────────

    def _stage_header(self, stage: dict) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(2, 8, 4, 2)
        lay.setSpacing(2)

        row = QHBoxLayout()
        row.setSpacing(7)
        done = stage["status"] == "done"
        ink = C.GREEN if done else (C.WHITE if stage["status"] == "current" else C.TEXT_DIM)
        name = QLabel(f"{stage['id']}  {stage['title']}")
        name.setFont(font(10, True))
        name.setStyleSheet(f"color: {ink}; background: transparent;")
        row.addWidget(name)
        row.addStretch()
        band = QLabel(stage["band"])
        band.setFont(font(9, True))
        band.setStyleSheet(
            f"color: {ink}; background: {C.GREEN_GHO if done else C.PANEL2};"
            f"border-radius: 7px; padding: 1px 7px;")
        row.addWidget(band)
        lay.addLayout(row)

        if stage.get("emphasis"):
            short = stage["emphasis"].split("—")[0].strip()
            note = QLabel(f"trains {short}")
            note.setFont(font(9))
            note.setToolTip(stage["emphasis"])
            note.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            lay.addWidget(note)
        return w

    def _refresh(self):
        try:
            data = self.get_syllabus() if callable(self.get_syllabus) else []
        except Exception:
            data = []
        # Rebuilding twenty-four rows every second would fight the scroll
        # position, so it only happens when something actually moved.
        sig = [(s["id"], s.get("review"), tuple((u["number"], u["status"],
                int(u.get("progress", 0))) for u in s["units"])) for s in data]
        if sig == self._signature:
            return
        self._signature = sig

        while self._lay.count() > 1:
            item = self._lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        if not data:
            waiting = QLabel("Waiting for the tutor…")
            waiting.setFont(font(10))
            waiting.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            self._lay.insertWidget(0, waiting)
            return

        width = _LEFT_W - 52      # panel width less margins and scrollbar
        current = None
        at = 0
        for stage in data:
            self._lay.insertWidget(at, self._stage_header(stage)); at += 1

            if stage.get("review"):
                note = QLabel(f"Stage review — reach {stage['exit_score']}/100 "
                              f"to move on")
                note.setFont(font(9))
                note.setWordWrap(True)
                note.setStyleSheet(
                    f"color: {C.ACC}; background: {C.PANEL}; border: 1px solid "
                    f"{C.BORDER}; border-left: 3px solid {C.ACC};"
                    f"border-radius: 8px; padding: 6px 8px;")
                self._lay.insertWidget(at, note); at += 1

            for unit in stage["units"]:
                row = UnitRow(unit, width)
                row.clicked.connect(self.unit_opened.emit)
                self._lay.insertWidget(at, row); at += 1
                if unit.get("status") == "current":
                    current = row

        # Twenty-four units do not fit on screen, and the one that matters is
        # the one being taught — so the list opens scrolled to it.
        if current is not None:
            QTimer.singleShot(0, lambda w=current: self.ensureWidgetVisible(w, 0, 60))


class UnitSheet(_HudOverlay):
    """One unit, opened from the syllabus: what it teaches and what to say."""

    _OW = 520

    def __init__(self, unit: dict, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            UnitSheet {{
                background: {C.PANEL};
                border: 1px solid {C.BORDER_B};
                border-radius: 16px;
            }}
        """)
        self.setFixedWidth(self._OW)
        # A unit carries its sentences AND its three techniques, which is more
        # than fits on a laptop screen — so the sheet scrolls instead of being
        # cut off at the bottom, and never grows past the window.
        self.setMaximumHeight(max(360, (parent.height() if parent else 760) - 70))
        # …and it opens at a readable size rather than at the scroll area's own
        # (tiny) size hint.
        self.setMinimumHeight(min(self.maximumHeight(), 620))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: {C.PANEL}; border: none;"
            f" border-radius: 16px; }}" + scrollbar_style())
        inner = QWidget()
        inner.setStyleSheet(f"background: {C.PANEL};")
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        lay = QVBoxLayout(inner)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(9)

        top = QHBoxLayout()
        kicker = QLabel(f"UNIT {unit['number']} OF 24  ·  "
                        + {"done": "FINISHED", "current": "IN PROGRESS"}.get(
                            unit.get("status"), "TO COME"))
        kicker.setFont(font(9, True))
        kicker.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;"
                             f"letter-spacing: 1px;")
        top.addWidget(kicker)
        top.addStretch()
        close = QPushButton("Close")
        close.setFont(font(9))
        close.setFixedHeight(26)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setStyleSheet(btn_soft(8))
        close.clicked.connect(self._dismiss)
        top.addWidget(close)
        lay.addLayout(top)

        title = QLabel(unit["title"])
        title.setFont(font(18, True))
        title.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        lay.addWidget(title)

        def _row(caption: str, value: str, colour: str = ""):
            cap = QLabel(caption)
            cap.setFont(font(9, True))
            cap.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;"
                              f"letter-spacing: 1px;")
            lay.addWidget(cap)
            val = QLabel(value)
            val.setFont(font(11))
            val.setWordWrap(True)
            val.setStyleSheet(f"color: {colour or C.TEXT}; background: transparent;")
            lay.addWidget(val)

        grammar = "; ".join(f"{s} ({h})" for s, h in
                            zip(unit.get("skills", []), unit.get("hints", [])))
        _row("GRAMMAR", grammar or "—", C.PRI)
        _row("THEME", unit.get("theme", ""))

        cap = QLabel("SAY IT LIKE THIS")
        cap.setFont(font(9, True))
        cap.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;"
                          f"letter-spacing: 1px;")
        lay.addWidget(cap)
        for sentence in unit.get("examples", []):
            s = QLabel(f"“{sentence}”")
            s.setFont(font(12))
            s.setWordWrap(True)
            s.setStyleSheet(
                f"color: {C.WHITE}; background: {C.PRI_GHO}; border: none;"
                f"border-radius: 9px; padding: 7px 10px;")
            lay.addWidget(s)

        methods = unit.get("methods", [])
        if methods:
            cap = QLabel("HOW WE PRACTISE IT")
            cap.setFont(font(9, True))
            cap.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;"
                              f"letter-spacing: 1px;")
            lay.addWidget(cap)
            for i, m in enumerate(methods, 1):
                card = QLabel(f"{i}. {m['name']} — {m['goal']}\n{m['how']}")
                card.setFont(font(10))
                card.setWordWrap(True)
                card.setStyleSheet(
                    f"color: {C.TEXT}; background: {C.PANEL2}; border: none;"
                    f"border-left: 3px solid {C.ACC}; border-radius: 8px;"
                    f"padding: 7px 10px;")
                lay.addWidget(card)

        _row("YOUR TASK", unit.get("task", ""))
        _row("WHEN IT IS DONE", f"You can {unit.get('can_do', '')}.")
        if unit.get("missing"):
            _row("STILL MISSING", "; ".join(unit["missing"]), C.ACC)

        lay.addStretch()

    def _dismiss(self):
        self.hide()
        self.deleteLater()


class MainWindow(QMainWindow):
    _log_sig        = pyqtSignal(str)
    _state_sig      = pyqtSignal(str)
    _content_sig    = pyqtSignal(str, str)   # (title, text) — thread-safe content display
    _reconfig_sig   = pyqtSignal()           # trigger setup overlay from any thread
    _wake_dl_sig    = pyqtSignal(bool, str)  # wake-word install finished (ok, message)

    def __init__(self, face_path: str):
        super().__init__()
        self._face_path = face_path

        # Load customization from config
        _cfg = _read_full_config()
        self._assistant_name: str = (_cfg.get("assistant_name") or "LangVis").strip()

        # Apply the saved UI colour BEFORE panels/stylesheets are built
        _ui_color = (_cfg.get("ui_color") or "").strip()
        if _ui_color and _ui_color.lower() != DEFAULT_UI_COLOR:
            apply_ui_accent(_ui_color)

        self.setWindowTitle(f"{self._assistant_name} — language tutor")
        self.setMinimumSize(_MIN_W, _MIN_H)
        self.resize(_DEFAULT_W, _DEFAULT_H)

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            (screen.width()  - _DEFAULT_W) // 2,
            (screen.height() - _DEFAULT_H) // 2,
        )

        self.on_text_command   = None
        self.on_interrupt      = None   # callable: () -> None — stop the tutor mid-speech
        self.on_voice_change   = None   # callable: () -> None — rebuild session with new voice
        self.on_audio_device_change = None  # callable: () -> None — reopen audio streams
        self.on_language_change = None  # callable: (name: str) -> None — switch course
        self.get_plugin_settings = None # callable: () -> list[dict] settings schemas
        self.get_lesson_status = None   # callable: () -> dict — level, unit, focus
        self.get_syllabus      = None   # callable: () -> list[dict] — the whole course
        self.get_coaching      = None   # callable: () -> dict — the correction card
        self.on_wake_toggle    = None   # callable: (enable: bool) -> str
        self.on_wake_manual    = None   # callable: () -> None — manual sleep/wake
        self.wake_get_state    = None   # callable: () -> dict {enabled, awake, ready}
        self._muted            = False
        self._customize_overlay: CustomizeOverlay | None = None

        central = QWidget()
        central.setStyleSheet(f"background: {C.BG};")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        # Three columns, in the order a lesson is used: where the course is
        # going, what is being said right now, and what was said.
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self._left_panel = self._build_left_panel()
        body.addWidget(self._left_panel, stretch=0)
        body.addWidget(self._build_centre(face_path), stretch=5)
        self._right_panel = self._build_right_panel()
        body.addWidget(self._right_panel, stretch=0)

        root.addLayout(body, stretch=1)
        root.addWidget(self._build_footer())

        # Open by default: the learner reads back what they said. The header
        # button folds the whole column away when the coaching needs the room.
        self._transcript_btn.setChecked(True)
        self._toggle_transcript(True)

        # Quick-access drawer (floating overlay, built after the central layout)
        self._quick_drawer = self._build_quick_drawer()
        self._update_autostart_btn(self._check_autostart())

        self._clock_tmr = QTimer(self)
        self._clock_tmr.timeout.connect(self._tick_clock)
        self._clock_tmr.start(1000)
        self._tick_clock()

        self._log_sig.connect(self._log.append_log)
        self._state_sig.connect(self._apply_state)
        self._content_sig.connect(self._show_content)
        self._reconfig_sig.connect(self._show_setup)
        self._wake_dl_sig.connect(self._on_wake_install_done)

        self._overlay: SetupOverlay | None = None
        self._ready = self._check_config()
        if not self._ready:
            self._show_setup()

        sc_mute = QShortcut(QKeySequence("F4"), self)
        sc_mute.activated.connect(self._toggle_mute)
        sc_full = QShortcut(QKeySequence("F11"), self)
        sc_full.activated.connect(self._toggle_fullscreen)
        sc_intr = QShortcut(QKeySequence("Escape"), self)
        sc_intr.activated.connect(self._do_interrupt)

    @staticmethod
    def _build_langvis_icon(out_path: Path) -> bool:
        """
        Render a LangVis arc-reactor icon at 4× resolution and downsample
        for crisp results at all sizes. Saves a multi-res .ico to out_path.
        Returns True on success.
        """
        try:
            import math
            import PIL.Image
            import PIL.ImageDraw
            import PIL.ImageFilter
        except ImportError:
            return False

        CYAN   = (0, 212, 255)
        DIM    = (0, 100, 140)
        DARK   = (0, 6, 10)
        GLOW   = (0, 160, 200)
        WHITE  = (220, 240, 255)

        def _render(sz: int) -> PIL.Image.Image:
            S  = sz * 4                     # draw at 4× then downscale
            img = PIL.Image.new("RGBA", (S, S), (0, 0, 0, 0))
            d   = PIL.ImageDraw.Draw(img)
            cx = cy = S // 2

            # ── filled background circle ──────────────────────────────────
            R = S // 2 - 2
            d.ellipse([cx-R, cy-R, cx+R, cy+R], fill=(*DARK, 255))

            # ── outer border ring ─────────────────────────────────────────
            lw = max(2, S // 40)
            d.ellipse([cx-R, cy-R, cx+R, cy+R],
                      outline=(*CYAN, 220), width=lw)

            # ── mid decorative ring ───────────────────────────────────────
            R2 = int(R * 0.72)
            d.ellipse([cx-R2, cy-R2, cx+R2, cy+R2],
                      outline=(*DIM, 180), width=max(1, lw // 2))

            # ── 6 radial spokes (hex bolt) ────────────────────────────────
            R_inner = int(R * 0.30)
            R_outer = int(R * 0.62)
            spoke_w = max(1, S // 80)
            for i in range(6):
                angle = math.radians(i * 60 - 30)
                x1 = cx + int(R_inner * math.cos(angle))
                y1 = cy + int(R_inner * math.sin(angle))
                x2 = cx + int(R_outer * math.cos(angle))
                y2 = cy + int(R_outer * math.sin(angle))
                d.line([x1, y1, x2, y2], fill=(*GLOW, 200), width=spoke_w)

            # ── 6 tick marks on outer ring ────────────────────────────────
            for i in range(6):
                angle = math.radians(i * 60)
                for dr in range(lw * 2):
                    rx = (R - lw - dr)
                    d.point(
                        [cx + int(rx * math.cos(angle)),
                         cy + int(rx * math.sin(angle))],
                        fill=(*WHITE, 220),
                    )

            # ── inner glowing ring ────────────────────────────────────────
            Ri = int(R * 0.26)
            d.ellipse([cx-Ri, cy-Ri, cx+Ri, cy+Ri],
                      outline=(*CYAN, 255), width=max(2, lw))

            # ── bright glow soft blur applied before core ─────────────────
            # (draw a slightly larger cyan circle on a separate layer)
            glow_layer = PIL.Image.new("RGBA", (S, S), (0, 0, 0, 0))
            gd = PIL.ImageDraw.Draw(glow_layer)
            Rc = int(R * 0.13)
            gd.ellipse([cx-Rc*2, cy-Rc*2, cx+Rc*2, cy+Rc*2],
                       fill=(*CYAN, 110))
            glow_layer = glow_layer.filter(PIL.ImageFilter.GaussianBlur(S // 14))
            img = PIL.Image.alpha_composite(img, glow_layer)
            d   = PIL.ImageDraw.Draw(img)

            # ── core dot ──────────────────────────────────────────────────
            d.ellipse([cx-Rc, cy-Rc, cx+Rc, cy+Rc], fill=(*WHITE, 255))

            # ── downscale to target size ──────────────────────────────────
            return img.resize((sz, sz), PIL.Image.LANCZOS)

        try:
            sizes  = [256, 128, 64, 48, 32, 16]
            frames = [_render(s) for s in sizes]
            frames[0].save(
                out_path,
                format="ICO",
                append_images=frames[1:],
                sizes=[(s, s) for s in sizes],
            )
            return True
        except Exception as e:
            print(f"[Shortcut] ⚠️  Icon generation failed: {e}")
            return False

    @staticmethod
    def _create_lnk_windows(lnk: str, target: str, args: str,
                             work_dir: str, icon_loc: str) -> None:
        """
        Create a Windows .lnk shortcut WITHOUT launching PowerShell or cmd.
        Tries win32com (pywin32) first; falls back to wscript.exe + VBScript.
        wscript.exe is a GUI-mode host — it never opens a console window.
        """
        # ── Option 1: pywin32 (pure Python COM, zero subprocess) ──────────
        try:
            from win32com.client import Dispatch   # type: ignore
            sh = Dispatch("WScript.Shell")
            sc = sh.CreateShortCut(lnk)
            sc.TargetPath       = target
            sc.Arguments        = f'"{args}"'
            sc.WorkingDirectory = work_dir
            sc.Description      = "LangVis AI Assistant"
            sc.IconLocation     = icon_loc
            sc.save()
            return
        except ImportError:
            pass

        # ── Option 2: wscript.exe + VBScript (always available on Windows,
        #    GUI-mode executable — never opens a console window) ────────────
        vbs = "\n".join([
            'Set ws = CreateObject("WScript.Shell")',
            f'Set sc = ws.CreateShortcut("{lnk}")',
            f'sc.TargetPath = "{target}"',
            f'sc.Arguments = Chr(34) & "{args}" & Chr(34)',
            f'sc.WorkingDirectory = "{work_dir}"',
            'sc.Description = "LangVis AI Assistant"',
            f'sc.IconLocation = "{icon_loc}"',
            'sc.Save',
        ])
        import tempfile
        fd, tmp = tempfile.mkstemp(suffix=".vbs")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(vbs)
            proc = subprocess.Popen(
                ["wscript.exe", "/nologo", tmp],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
            )
            proc.wait(timeout=10)
        finally:
            try:
                os.unlink(tmp)
            except Exception:
                pass

    @staticmethod
    def _get_desktop_dir() -> Path:
        """
        Resolve the user's REAL desktop directory instead of assuming
        ~/Desktop, which breaks when:
          • OneDrive "Known Folder Move" relocates the desktop
            (C:/Users/x/OneDrive/Desktop) — very common on Win 10/11;
          • the XDG desktop is localized on Linux (~/Masaüstü,
            ~/Schreibtisch, ~/Bureau, …).
        Falls back to ~/Desktop only as a last resort.
        """
        home = Path.home()
        _os = platform.system()

        if _os == "Windows":
            # ── 1) SHGetKnownFolderPath(FOLDERID_Desktop) — the canonical
            #       answer; follows OneDrive redirection. No dependencies. ──
            try:
                import ctypes
                from ctypes import wintypes

                class _GUID(ctypes.Structure):
                    _fields_ = [("Data1", wintypes.DWORD),
                                ("Data2", wintypes.WORD),
                                ("Data3", wintypes.WORD),
                                ("Data4", ctypes.c_ubyte * 8)]

                # FOLDERID_Desktop {B4BFCC3A-DB2C-424C-B029-7FE99A87C641}
                fid = _GUID(0xB4BFCC3A, 0xDB2C, 0x424C,
                            (ctypes.c_ubyte * 8)(0xB0, 0x29, 0x7F, 0xE9,
                                                 0x9A, 0x87, 0xC6, 0x41))
                buf = ctypes.c_wchar_p()
                if ctypes.windll.shell32.SHGetKnownFolderPath(
                        ctypes.byref(fid), 0, None, ctypes.byref(buf)) == 0:
                    p = Path(buf.value)
                    ctypes.windll.ole32.CoTaskMemFree(buf)
                    if p.is_dir():
                        return p
            except Exception:
                pass

            # ── 2) Registry: User Shell Folders (may contain %VARS%) ──────
            try:
                import winreg
                with winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER,
                        r"Software\Microsoft\Windows\CurrentVersion"
                        r"\Explorer\User Shell Folders") as key:
                    val, _t = winreg.QueryValueEx(key, "Desktop")
                p = Path(os.path.expandvars(val))
                if p.is_dir():
                    return p
            except Exception:
                pass

        elif _os == "Linux":
            # ── xdg-user-dir honours localized names (~/Masaüstü, …) ──────
            try:
                out = subprocess.run(["xdg-user-dir", "DESKTOP"],
                                     capture_output=True, text=True, timeout=5)
                p = Path(out.stdout.strip())
                if out.stdout.strip() and p != home and p.is_dir():
                    return p
            except Exception:
                pass
            try:
                cfg = home / ".config" / "user-dirs.dirs"
                for line in cfg.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("XDG_DESKTOP_DIR"):
                        val = line.split("=", 1)[1].strip().strip('"')
                        p = Path(val.replace("$HOME", str(home)))
                        if p != home and p.is_dir():
                            return p
            except Exception:
                pass

        # macOS: ~/Desktop is always the real path (localization is
        # display-only). Everything else lands here as a last resort.
        return home / "Desktop"

    def _create_desktop_shortcut(self):
        """
        Create a desktop shortcut on Windows / macOS / Linux.
        Never opens a terminal, console, or PowerShell window on any platform.
        """
        import stat as _stat
        script  = Path(__file__).resolve().parent / "main.py"
        python  = Path(sys.executable)
        desktop = self._get_desktop_dir()

        # Arc-reactor icon (.ico — also exported as .png for Linux/macOS)
        ico_path = Path(__file__).resolve().parent / "config" / "langvis.ico"
        if not ico_path.exists():
            self._build_langvis_icon(ico_path)

        try:
            _os = platform.system()

            # ── Windows ───────────────────────────────────────────────────────
            if _os == "Windows":
                pythonw  = python.parent / "pythonw.exe"
                target   = str(pythonw if pythonw.exists() else python)
                lnk      = str(desktop / "LangVis.lnk")
                icon_loc = str(ico_path) if ico_path.exists() else f"{target},0"
                self._create_lnk_windows(lnk, target, str(script),
                                         str(script.parent), icon_loc)

            # ── macOS — proper .app bundle (no Terminal window) ───────────────
            elif _os == "Darwin":
                app     = desktop / "LangVis.app"
                mac_dir = app / "Contents" / "MacOS"
                res_dir = app / "Contents" / "Resources"
                mac_dir.mkdir(parents=True, exist_ok=True)
                res_dir.mkdir(exist_ok=True)

                # Launcher executable (bash — runs as background process,
                # macOS does NOT open Terminal for executables inside .app bundles)
                launcher = mac_dir / "LangVis"
                launcher.write_text(
                    "#!/usr/bin/env bash\n"
                    f'cd "{script.parent}"\n'
                    f'exec "{python}" "{script}"\n'
                )
                launcher.chmod(launcher.stat().st_mode
                               | _stat.S_IEXEC | _stat.S_IXGRP | _stat.S_IXOTH)

                # Minimal Info.plist (required for .app recognition)
                (app / "Contents" / "Info.plist").write_text(
                    '<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                    '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                    '<plist version="1.0"><dict>\n'
                    '  <key>CFBundleExecutable</key><string>LangVis</string>\n'
                    '  <key>CFBundleIdentifier</key>'
                    '<string>com.langvis.assistant</string>\n'
                    '  <key>CFBundleName</key><string>LangVis</string>\n'
                    '  <key>CFBundlePackageType</key><string>APPL</string>\n'
                    '  <key>CFBundleVersion</key><string>1.0</string>\n'
                    '</dict></plist>\n'
                )

                # Optional: copy icon as .icns (skip silently if Pillow is missing)
                try:
                    import PIL.Image
                    icns = res_dir / "AppIcon.icns"
                    PIL.Image.open(ico_path).save(icns, format="ICNS")
                    # Inject icon reference into plist
                    plist = app / "Contents" / "Info.plist"
                    txt = plist.read_text()
                    plist.write_text(
                        txt.replace(
                            '</dict></plist>',
                            '  <key>CFBundleIconFile</key>'
                            '<string>AppIcon</string>\n</dict></plist>\n',
                        )
                    )
                except Exception:
                    pass  # icon is optional

            # ── Linux — .desktop file (Terminal=false, no console) ────────────
            else:
                # Export .ico → .png for better desktop integration
                png_path = ico_path.with_suffix(".png")
                if not png_path.exists() and ico_path.exists():
                    try:
                        import PIL.Image
                        PIL.Image.open(ico_path).resize(
                            (256, 256), PIL.Image.LANCZOS
                        ).save(png_path, format="PNG")
                    except Exception:
                        png_path = ico_path  # fallback to .ico

                icon_line = f"Icon={png_path}\n" if png_path.exists() else ""
                desk = desktop / "LangVis.desktop"
                desk.write_text(
                    "[Desktop Entry]\n"
                    "Name=LangVis\n"
                    f"Exec={python} {script}\n"
                    f"Path={script.parent}\n"
                    "Type=Application\n"
                    "Terminal=false\n"
                    "Categories=Utility;\n"
                    + icon_line
                )
                desk.chmod(desk.stat().st_mode | 0o755)

            self._log.append_log("SYS: Desktop shortcut created.")
        except Exception as e:
            self._log.append_log(f"ERR: Shortcut failed — {e}")

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cw = self.centralWidget()
        if self._overlay and self._overlay.isVisible():
            ow, oh = 460, 390
            self._overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        if self._customize_overlay and self._customize_overlay.isVisible():
            ow, oh = CustomizeOverlay._OW, CustomizeOverlay._OH
            self._customize_overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        # The header is the first thing to overflow on a small screen: drop the
        # least important things first rather than letting it clip.
        if hasattr(self, "_today_pill"):
            w = self.width()
            self._today_pill.setVisible(w >= 1150)
            self._sub_lbl.setVisible(w >= 1000)
            self._lang_select.setMinimumWidth(200 if w >= 1100 else 140)

        # Quick drawer — reposition if open
        if hasattr(self, '_quick_drawer') and self._quick_drawer.isVisible():
            self._position_quick_drawer()

    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(64)
        w.setStyleSheet(f"background: {C.DARK}; border-bottom: 1px solid {C.BORDER};")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(16, 9, 16, 9)
        lay.setSpacing(14)

        # The mark: the brand's initial in a rounded tile. Drawn, not shipped,
        # so renaming the tutor renames the logo too.
        self._mark = QLabel((self._assistant_name or "L")[:1].upper())
        self._mark.setFixedSize(34, 34)
        self._mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._mark.setFont(font(15, True))
        self._mark.setStyleSheet(
            f"color: {C.PANEL}; background: {C.PRI}; border-radius: 10px;")
        lay.addWidget(self._mark)

        name_col = QVBoxLayout()
        name_col.setSpacing(0)
        self._title_lbl = QLabel(self._assistant_name)
        self._title_lbl.setFont(font(15, True))
        self._title_lbl.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        name_col.addWidget(self._title_lbl)
        self._sub_lbl = QLabel("speaking course")
        self._sub_lbl.setFont(font(9))
        self._sub_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        name_col.addWidget(self._sub_lbl)
        lay.addLayout(name_col)

        lay.addSpacing(6)

        # The language select. Slovak is listed and visibly not ready, rather
        # than hidden: the learner asked for it, so it belongs on screen.
        self._lang_select = QComboBox()
        self._lang_select.setFixedHeight(34)
        self._lang_select.setMinimumWidth(190)
        self._lang_select.setFont(font(11, True))
        self._lang_select.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lang_select.setStyleSheet(combo_style(10, accent=True))
        self._lang_select.currentIndexChanged.connect(self._on_language_picked)
        lay.addWidget(self._lang_select)

        lay.addStretch()

        self._level_pill = QLabel("")
        self._level_pill.setFont(font(11, True))
        self._level_pill.setFixedHeight(30)
        self._level_pill.setStyleSheet(pill_style(C.PRI, C.PRI_GHO))
        lay.addWidget(self._level_pill)

        self._today_pill = QLabel("")
        self._today_pill.setFont(font(10))
        self._today_pill.setFixedHeight(30)
        self._today_pill.setStyleSheet(pill_style(C.TEXT_MED, C.PANEL2))
        lay.addWidget(self._today_pill)

        # Folds the right-hand column (words and conversation) away when the
        # coaching in the middle wants the whole window.
        self._transcript_btn = QPushButton("Conversation")
        self._transcript_btn.setFixedHeight(30)
        self._transcript_btn.setCheckable(True)
        self._transcript_btn.setFont(font(10, True))
        self._transcript_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._transcript_btn.setStyleSheet(btn_soft(10))
        self._transcript_btn.clicked.connect(
            lambda: self._toggle_transcript(self._transcript_btn.isChecked()))
        lay.addWidget(self._transcript_btn)

        self._drawer_btn = QPushButton("⚙")
        self._drawer_btn.setFixedSize(34, 34)
        self._drawer_btn.setFont(font(14))
        self._drawer_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._drawer_btn.setToolTip("Settings")
        self._drawer_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL2}; color: {C.TEXT_MED};
                border: none; border-radius: 10px;
            }}
            QPushButton:hover {{ color: {C.PRI}; background: {C.PRI_GHO}; }}
            QPushButton:checked {{ color: {C.PANEL}; background: {C.PRI}; }}
        """)
        self._drawer_btn.setCheckable(True)
        self._drawer_btn.clicked.connect(self._toggle_drawer)
        lay.addWidget(self._drawer_btn)
        return w

    # -- the language select ---------------------------------------------------

    def _fill_language_select(self) -> None:
        """Rebuild the list from whatever the tutor reports. A course that is
        not written yet stays in the list, greyed and unselectable, because the
        learner is waiting for it."""
        try:
            modes = (self.get_lesson_status() or {}).get("modes") or []
        except Exception:
            modes = []
        if not modes:
            modes = [{"name": "English", "enabled": True, "active": True}]
        sig = [(m["name"], m.get("enabled"), m.get("active")) for m in modes]
        if sig == getattr(self, "_lang_sig", None):
            return
        self._lang_sig = sig
        self._lang_filling = True
        self._lang_select.clear()
        for i, m in enumerate(modes):
            label = m["name"] if m.get("enabled") else f"{m['name']} — coming soon"
            self._lang_select.addItem(label, m["name"])
            if not m.get("enabled"):
                model = self._lang_select.model()
                model.item(i).setEnabled(False)
            if m.get("active"):
                self._lang_select.setCurrentIndex(i)
        self._lang_filling = False

    def _on_language_picked(self, index: int):
        if getattr(self, "_lang_filling", False) or index < 0:
            return
        name = self._lang_select.itemData(index)
        if not name or not self.on_language_change:
            return
        try:
            self.on_language_change(str(name))
        except Exception as e:
            self._log.append_log(f"ERR: could not switch language — {e}")

    # -- the syllabus column ---------------------------------------------------

    def _build_left_panel(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(_LEFT_W)
        w.setStyleSheet(f"background: {C.DARK}; border-right: 1px solid {C.BORDER};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(14, 12, 10, 10)
        lay.setSpacing(6)

        head = QHBoxLayout()
        title = QLabel("Syllabus")
        title.setFont(font(12, True))
        title.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        head.addWidget(title)
        head.addStretch()
        self._syllabus_count = QLabel("")
        self._syllabus_count.setFont(font(9))
        self._syllabus_count.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        head.addWidget(self._syllabus_count)
        lay.addLayout(head)

        hint = QLabel("24 units · click one for its sentences and method")
        hint.setWordWrap(True)
        hint.setFont(font(9))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addWidget(hint)

        self._syllabus = SyllabusPanel()
        self._syllabus.unit_opened.connect(self._open_unit_sheet)
        lay.addWidget(self._syllabus, stretch=1)
        return w

    def _open_unit_sheet(self, unit: dict):
        sheet = UnitSheet(unit, parent=self.centralWidget())
        self._centre_overlay(sheet)
        self._unit_sheet = sheet     # keep a reference so it is not collected

    # -- the speaking column ---------------------------------------------------

    def _build_centre(self, face_path: str) -> QWidget:
        """The room the lesson happens in. The unit is one line at the top —
        it is context, not content — and everything below it is the coaching on
        the sentence just spoken."""
        w = QWidget()
        w.setStyleSheet(f"background: {C.BG};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(18, 12, 18, 14)
        lay.setSpacing(10)

        # One line: where we are, what it trains, how far in. The methods and
        # the sentences are one click away in the unit sheet.
        strip = QWidget()
        strip.setObjectName("UnitStrip")
        strip.setStyleSheet(f"QWidget#UnitStrip {{ {card_style(10)} }}")
        strip.setCursor(Qt.CursorShape.PointingHandCursor)
        strip.setToolTip("Click for this unit's sentences, words and methods")
        sl = QVBoxLayout(strip)
        sl.setContentsMargins(12, 7, 12, 8)
        sl.setSpacing(4)

        row = QHBoxLayout()
        row.setSpacing(9)
        self._unit_kicker = QLabel("")
        self._unit_kicker.setFont(font(9, True))
        self._unit_kicker.setStyleSheet(
            f"color: {C.TEXT_DIM}; background: transparent; letter-spacing: 1px;")
        row.addWidget(self._unit_kicker)
        self._unit_title = QLabel("")
        self._unit_title.setFont(font(12, True))
        self._unit_title.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        row.addWidget(self._unit_title)
        self._unit_grammar = QLabel("")
        self._unit_grammar.setFont(font(10))
        self._unit_grammar.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        row.addWidget(self._unit_grammar)
        row.addStretch()
        self._unit_pct = QLabel("")
        self._unit_pct.setFont(font(10, True))
        self._unit_pct.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        row.addWidget(self._unit_pct)
        sl.addLayout(row)

        self._unit_bar = SoftBar(colour=C.PRI)
        self._unit_bar.setFixedHeight(8)
        sl.addWidget(self._unit_bar)
        strip.mousePressEvent = lambda _e: self._open_current_unit()
        lay.addWidget(strip)

        # Whose turn it is.
        self.hud = VoiceVector(face_path, self._assistant_name)
        self.hud.setFixedHeight(180)
        lay.addWidget(self.hud)

        # The teaching itself.
        self._assistant = AssistantPanel()
        lay.addWidget(self._assistant, stretch=1)

        self._content_panel = self._build_content_panel()
        lay.addWidget(self._content_panel)

        # The controls live here, not in the transcript column, so hiding the
        # transcript never takes the microphone with it.
        lay.addLayout(self._build_controls())
        return w

    def _build_controls(self) -> QHBoxLayout:
        row = self._build_input_row()
        self._interrupt_btn = QPushButton("Interrupt")
        self._interrupt_btn.setFixedHeight(36)
        self._interrupt_btn.setFont(font(11, True))
        self._interrupt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._interrupt_btn.setStyleSheet(
            btn_tone(C.RED, C.MUTED_GHO, C.MUTED_GHO, 11).replace(
                "text-align: left;", "text-align: center;"))
        self._interrupt_btn.clicked.connect(self._do_interrupt)
        row.addWidget(self._interrupt_btn)

        self._mute_btn = QPushButton()
        self._mute_btn.setFixedHeight(36)
        self._mute_btn.setFont(font(11, True))
        self._mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mute_btn.clicked.connect(self._toggle_mute)
        self._style_mute_btn()
        row.addWidget(self._mute_btn)
        return row

    def _open_current_unit(self):
        try:
            for stage in (self.get_syllabus() or []):
                for unit in stage["units"]:
                    if unit.get("status") == "current":
                        self._open_unit_sheet(unit)
                        return
        except Exception:
            pass

    # -- the conversation column ----------------------------------------------

    def _build_right_panel(self) -> QWidget:
        """What the unit is installing, and what has actually been said. Both
        belong on the same side: the checklist is the promise, the transcript is
        the evidence."""
        w = QWidget()
        w.setFixedWidth(_RIGHT_W)
        w.setStyleSheet(f"background: {C.DARK}; border-left: 1px solid {C.BORDER};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)

        self._checklist = ChecklistStrip()
        lay.addWidget(self._checklist)

        hdr = QHBoxLayout()
        title = QLabel("Conversation")
        title.setFont(font(12, True))
        title.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        hdr.addWidget(title)
        hdr.addStretch()
        note = QLabel("you \u00b7 tutor")
        note.setFont(font(9))
        note.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        hdr.addWidget(note)
        lay.addLayout(hdr)

        self._log = ChatView()
        lay.addWidget(self._log, stretch=1)
        return w

    def _toggle_transcript(self, show: bool):
        """Fold the right column away (conversation and checklist together) when
        the coaching in the middle needs the whole window."""
        self._right_panel.setVisible(bool(show))
        if hasattr(self, "_transcript_btn"):
            self._transcript_btn.setChecked(bool(show))
            self._transcript_btn.setStyleSheet(
                btn_tone(C.PRI, C.PRI_GHO, C.PRI_GHO, 10) if show else btn_soft(10))

    def _build_input_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        self._input = QLineEdit()
        self._input.setPlaceholderText("…or type your sentence")
        self._input.setFont(font(11))
        self._input.setFixedHeight(36)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: {C.PANEL}; color: {C.WHITE};
                border: 1px solid {C.BORDER}; border-radius: 11px; padding: 4px 12px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        self._input.returnPressed.connect(self._send)
        row.addWidget(self._input)

        send = QPushButton("➤")
        send.setFixedSize(36, 36)
        send.setFont(font(12, True))
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.setStyleSheet(f"""
            QPushButton {{
                background: {C.PRI}; color: {C.PANEL}; border: none;
                border-radius: 11px;
            }}
            QPushButton:hover {{ background: {C.WHITE}; }}
        """)
        send.clicked.connect(self._send)
        row.addWidget(send)
        return row

    # -- the drill card --------------------------------------------------------

    def _build_content_panel(self) -> QWidget:
        w = QWidget()
        w.setObjectName("ContentPanel")
        w.setStyleSheet(f"QWidget#ContentPanel {{ {card_style(12)} }}")
        w.setMaximumHeight(240)
        w.hide()

        lay = QVBoxLayout(w)
        lay.setContentsMargins(14, 10, 14, 12)
        lay.setSpacing(7)

        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        self._content_title_lbl = QLabel("Exercise")
        self._content_title_lbl.setFont(font(11, True))
        self._content_title_lbl.setStyleSheet(f"color: {C.ACC}; background: transparent;")
        hdr.addWidget(self._content_title_lbl)
        hdr.addStretch()
        self._content_ts_lbl = QLabel("")
        self._content_ts_lbl.setFont(font(9))
        self._content_ts_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        hdr.addWidget(self._content_ts_lbl)
        dismiss = QPushButton("Close")
        dismiss.setFont(font(9))
        dismiss.setFixedHeight(24)
        dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss.setStyleSheet(btn_soft(8).replace("padding: 0 14px;", "padding: 0 10px;"))
        dismiss.clicked.connect(w.hide)
        hdr.addWidget(dismiss)
        lay.addLayout(hdr)

        self._content_display = QTextEdit()
        self._content_display.setReadOnly(True)
        self._content_display.setFont(font(11))
        self._content_display.setMinimumHeight(60)
        self._content_display.setStyleSheet(f"""
            QTextEdit {{
                background: {C.PANEL2}; color: {C.WHITE};
                border: none; border-radius: 10px; padding: 9px 11px;
                selection-background-color: {C.PRI_GHO};
            }}
        """ + scrollbar_style())
        lay.addWidget(self._content_display)
        return w

    def _show_content(self, title: str, text: str):
        """Slot — runs on the Qt main thread."""
        self._content_title_lbl.setText(title[:60])
        self._content_ts_lbl.setText(time.strftime("%H:%M"))
        self._content_display.setPlainText(text)
        self._content_display.moveCursor(
            self._content_display.textCursor().MoveOperation.Start)
        self._content_panel.show()

    # -- the footer ------------------------------------------------------------

    def _build_footer(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(40)
        w.setStyleSheet(f"background: {C.DARK}; border-top: 1px solid {C.BORDER};")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(10)

        cap = QLabel("WE ARE FIXING")
        cap.setFont(font(9, True))
        cap.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;"
                          f"letter-spacing: 1px;")
        lay.addWidget(cap)

        self._focus_chips = []
        for _ in range(3):
            chip = QLabel("")
            chip.setFont(font(10))
            chip.setFixedHeight(24)
            chip.setStyleSheet(pill_style(C.RED, C.MUTED_GHO, 12))
            chip.hide()
            lay.addWidget(chip)
            self._focus_chips.append(chip)

        self._focus_none = QLabel("nothing repeated yet")
        self._focus_none.setFont(font(10))
        self._focus_none.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addWidget(self._focus_none)

        lay.addStretch()

        hints = QLabel("F4 mute  ·  Esc interrupt  ·  F11 fullscreen")
        hints.setFont(font(9))
        hints.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addWidget(hints)
        return w

    # -- the one-second poll ---------------------------------------------------

    def _tick_clock(self):
        """Everything that changes by itself: the level, today's count, the unit
        strip, its sentences and the weak-point chips. One timer, one read of
        the tutor's cached status — the widgets never talk to the plugin."""
        try:
            s = self.get_lesson_status() or {}
        except Exception:
            s = {}

        self._fill_language_select()

        if s:
            level, goal = s.get("level", "—"), s.get("goal", "")
            self._level_pill.setText(
                f"{level}  ·  {s.get('score', 0)}/100  →  {goal}")
            spoken = s.get("speak")
            self._level_pill.setToolTip(
                f"Spoken to at {spoken} — the level of your current stage."
                if spoken and spoken != level else "")
            n = int(s.get("sentences_today", 0))
            self._today_pill.setText(
                "nothing spoken today" if not n
                else f"{n} sentence{'s' if n != 1 else ''} today")
            self._syllabus_count.setText(
                f"unit {s.get('unit_no', 0)}/{s.get('unit_total', 0)}")

            focus = s.get("focus") or []
            self._focus_none.setVisible(not focus)
            for i, chip in enumerate(self._focus_chips):
                if i < len(focus):
                    f = focus[i]
                    chip.setText(f"{f.get('name', '')}  {int(f.get('mastery', 0))}/100")
                    chip.show()
                else:
                    chip.hide()

        unit = None
        try:
            for stage in (self.get_syllabus() or []):
                for u in stage["units"]:
                    if u.get("status") == "current":
                        unit = u
                        break
                if unit:
                    break
        except Exception:
            unit = None

        if unit:
            self._unit_kicker.setText(f"UNIT {unit['number']}/24")
            self._unit_title.setText(unit["title"])
            self._unit_grammar.setText("· " + ", ".join(unit.get("skills", [])))
            prog = int(unit.get("progress", 0))
            self._unit_pct.setText(f"{prog}%")
            self._unit_bar.set_value(prog, "")
            methods = [m["name"] for m in unit.get("methods", [])]
            if methods:
                self._unit_kicker.parentWidget().setToolTip(
                    "Method: " + " → ".join(methods)
                    + "  ·  click for sentences, words and details")
        elif s:
            self._unit_kicker.setText("STAGE REVIEW")
            self._unit_title.setText(str(s.get("unit_title", "")))
            self._unit_grammar.setText("· free conversation at your level")
            prog = int(s.get("unit_progress", 0))
            self._unit_pct.setText(f"{prog}%")
            self._unit_bar.set_value(prog, "")

    def _build_quick_drawer(self) -> QWidget:
        """Floating panel shown when the header's gear is toggled."""
        w = QWidget(self.centralWidget())
        w.setObjectName("QuickDrawer")
        w.setStyleSheet(f"""
            QWidget#QuickDrawer {{
                background: {C.PANEL};
                border: 1px solid {C.BORDER};
                border-radius: 14px;
            }}
        """)
        w.hide()

        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(7)

        hdr = QLabel("Settings")
        hdr.setFont(font(12, True))
        hdr.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        lay.addWidget(hdr)

        settings_btn = QPushButton("Tutor settings")
        settings_btn.setFixedHeight(38)
        settings_btn.setFont(font(11, True))
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.setStyleSheet(btn_primary(12))
        settings_btn.clicked.connect(self._open_plugin_settings)
        lay.addWidget(settings_btn)

        for text, slot in (("Name, voice & colour", self._open_customize),
                           ("Audio devices",        self._open_audio_devices),
                           ("What LangVis remembers", self._open_memory_panel),
                           ("Fullscreen  ·  F11", self._toggle_fullscreen),
                           ("Create desktop shortcut", self._create_desktop_shortcut)):
            b = QPushButton(text)
            b.setFixedHeight(32)
            b.setFont(font(10))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(btn_soft(10))
            b.clicked.connect(slot)
            lay.addWidget(b)

        self._autostart_btn = QPushButton("Start with Windows")
        self._autostart_btn.setFixedHeight(32)
        self._autostart_btn.setFont(font(10))
        self._autostart_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._autostart_btn.clicked.connect(self._toggle_autostart)
        lay.addWidget(self._autostart_btn)

        # Wake word: the mic stays local until the phrase is heard, so it is
        # opt-in and the button doubles as the download.
        self._wake_btn = QPushButton("Wake word")
        self._wake_btn.setFixedHeight(32)
        self._wake_btn.setFont(font(10))
        self._wake_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._wake_btn.setStyleSheet(btn_soft(10))
        self._wake_btn.clicked.connect(self._toggle_wake_word)
        lay.addWidget(self._wake_btn)

        self._wake_sleep_btn = QPushButton()
        self._wake_sleep_btn.setFixedHeight(32)
        self._wake_sleep_btn.setFont(font(10))
        self._wake_sleep_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._wake_sleep_btn.setStyleSheet(btn_soft(10))
        self._wake_sleep_btn.clicked.connect(self._tap_wake_manual)
        lay.addWidget(self._wake_sleep_btn)
        self._wake_sleep_btn.hide()

        w.adjustSize()
        return w

    def _toggle_drawer(self, checked: bool):
        if checked:
            self._refresh_wake_btns()   # resolve wake state on open (lazy)
            self._position_quick_drawer()
            self._quick_drawer.show()
            self._quick_drawer.raise_()
        else:
            self._quick_drawer.hide()

    def _position_quick_drawer(self):
        if not hasattr(self, '_quick_drawer'):
            return
        _W = 248
        self._quick_drawer.setFixedWidth(_W)
        self._quick_drawer.adjustSize()
        self._quick_drawer.setGeometry(14, 64, _W, self._quick_drawer.sizeHint().height())

    def _check_autostart(self) -> bool:
        """Returns True if auto-start is currently registered on this OS."""
        try:
            if _OS == "Windows":
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
                try:
                    winreg.QueryValueEx(key, "LangVis_AI")
                    return True
                except FileNotFoundError:
                    return False
                finally:
                    winreg.CloseKey(key)
            elif _OS == "Darwin":
                return (Path.home() / "Library" / "LaunchAgents"
                        / "com.langvis.assistant.plist").exists()
            else:
                return (Path.home() / ".config" / "autostart" / "langvis.desktop").exists()
        except Exception:
            return False

    def _toggle_autostart(self):
        currently_on = self._check_autostart()
        try:
            script = str(Path(__file__).resolve().parent / "main.py")
            if _OS == "Windows":
                import winreg
                reg = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_ALL_ACCESS)
                if currently_on:
                    winreg.DeleteValue(reg, "LangVis_AI")
                else:
                    pythonw = Path(sys.executable).parent / "pythonw.exe"
                    exe = str(pythonw if pythonw.exists() else sys.executable)
                    winreg.SetValueEx(reg, "LangVis_AI", 0, winreg.REG_SZ,
                                      f'"{exe}" "{script}"')
                winreg.CloseKey(reg)
            elif _OS == "Darwin":
                plist_dir = Path.home() / "Library" / "LaunchAgents"
                plist_dir.mkdir(parents=True, exist_ok=True)
                plist = plist_dir / "com.langvis.assistant.plist"
                if currently_on:
                    plist.unlink(missing_ok=True)
                else:
                    plist.write_text(
                        '<?xml version="1.0" encoding="UTF-8"?>\n'
                        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                        '<plist version="1.0"><dict>\n'
                        '  <key>Label</key><string>com.langvis.assistant</string>\n'
                        '  <key>ProgramArguments</key><array>\n'
                        f'    <string>{sys.executable}</string>\n'
                        f'    <string>{script}</string>\n'
                        '  </array>\n'
                        '  <key>RunAtLoad</key><true/>\n'
                        '</dict></plist>\n'
                    )
            else:
                desk_dir = Path.home() / ".config" / "autostart"
                desk_dir.mkdir(parents=True, exist_ok=True)
                desk = desk_dir / "langvis.desktop"
                if currently_on:
                    desk.unlink(missing_ok=True)
                else:
                    desk.write_text(
                        "[Desktop Entry]\n"
                        f"Name={self._assistant_name}\n"
                        f"Exec={sys.executable} {script}\n"
                        "Type=Application\nTerminal=false\n"
                        "X-GNOME-Autostart-enabled=true\n"
                    )
            enabled = not currently_on
            self._update_autostart_btn(enabled)
            self._log.append_log(
                f"SYS: Auto-start {'enabled' if enabled else 'disabled'}.")
        except Exception as e:
            self._log.append_log(f"ERR: Auto-start failed — {e}")

    def _update_autostart_btn(self, enabled: bool):
        if not hasattr(self, '_autostart_btn'):
            return
        self._autostart_btn.setText(
            "Start with Windows  ·  on" if enabled else "Start with Windows")
        self._autostart_btn.setStyleSheet(
            btn_tone(C.GREEN, C.GREEN_GHO, C.GREEN_GHO, 10) if enabled else btn_soft(10))

    def _wake_state(self) -> dict:
        """Combined state for the two wake-word buttons. Readiness is a cheap,
        deterministic on-disk check now (see core.wake_word.is_ready), so there
        is nothing to cache — the button never flickers to a stale value."""
        if self.wake_get_state:
            try:
                s = self.wake_get_state()
                return {"ready": bool(s.get("ready")),
                        "enabled": bool(s.get("enabled")),
                        "awake": bool(s.get("awake"))}
            except Exception:
                pass
        # Before LangVisLive has wired its callback (drawer built at startup).
        ready, enabled = False, False
        try:
            from core.wake_word import is_ready
            from memory.config_manager import get_wake_word_enabled
            ready, enabled = is_ready(), get_wake_word_enabled()
        except Exception:
            pass
        return {"ready": ready, "enabled": enabled, "awake": True}

    def _refresh_wake_btns(self):
        if not hasattr(self, '_wake_btn'):
            return
        st = self._wake_state()
        on, off = btn_tone(C.GREEN, C.GREEN_GHO, C.GREEN_GHO, 10), btn_soft(10)
        self._wake_btn.setEnabled(True)
        if not st["ready"]:
            self._wake_btn.setText("Wake word  ·  download")
            self._wake_btn.setStyleSheet(off)
            self._wake_sleep_btn.hide()
        elif st["enabled"]:
            self._wake_btn.setText("Wake word  ·  on")
            self._wake_btn.setStyleSheet(on)
            self._wake_sleep_btn.show()
            self._wake_sleep_btn.setText(
                "Sleep now" if st["awake"] else "Wake now")
            self._wake_sleep_btn.setStyleSheet(off)
        else:
            self._wake_btn.setText("Wake word  ·  off")
            self._wake_btn.setStyleSheet(off)
            self._wake_sleep_btn.hide()

    def _toggle_wake_word(self):
        st = self._wake_state()
        if not st["ready"]:
            # First time: download openwakeword + model in a worker thread.
            self._wake_btn.setText("⬇  DOWNLOADING… (one-time)")
            self._wake_btn.setEnabled(False)
            def _work():
                try:
                    from core.wake_word import install_and_download
                    ok, msg = install_and_download(
                        logger=lambda m: self._log_sig.emit(f"SYS: {m}"))
                except Exception as e:
                    ok, msg = False, str(e)
                if ok and self.on_wake_toggle:
                    try:
                        self.on_wake_toggle(True)   # auto-enable after a successful download
                    except Exception:
                        pass
                self._wake_dl_sig.emit(ok, msg)
            threading.Thread(target=_work, daemon=True).start()
            return
        # Already downloaded → just flip enabled/disabled through LangVisLive.
        if self.on_wake_toggle:
            try:
                self.on_wake_toggle(not st["enabled"])
            except Exception:
                pass
        self._refresh_wake_btns()

    def _on_wake_install_done(self, ok: bool, msg: str):
        self._log_sig.emit(f"SYS: {'Wake word ready.' if ok else 'Wake word setup failed: ' + msg}")
        self._refresh_wake_btns()

    def _tap_wake_manual(self):
        if self.on_wake_manual:
            try:
                self.on_wake_manual()
            except Exception:
                pass
        self._refresh_wake_btns()

    # ── Customization ────────────────────────────────────────────────────────────

    def _open_customize(self):
        cfg = _read_full_config()
        if self._customize_overlay:
            self._customize_overlay.hide()
        cw = self.centralWidget()
        ov = CustomizeOverlay(
            cfg.get("assistant_name", "LangVis") or "LangVis",
            cfg.get("user_name", ""),
            cfg.get("ui_color", "") or DEFAULT_UI_COLOR,
            cfg.get("voice_name", ""),
            parent=cw,
        )
        ow, oh = CustomizeOverlay._OW, CustomizeOverlay._OH
        oh = min(oh, cw.height() - 16)
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.on_preview = self._preview_ui_color
        ov.saved.connect(self._apply_name_update)
        ov.show()
        self._customize_overlay = ov

    def _preview_ui_color(self, hex_color: str):
        """Live preview — paints the whole interface the new colour (does NOT write to config)."""
        old = current_palette()
        if apply_ui_accent(hex_color):
            retheme_all_widgets(old, current_palette())

    def _apply_name_update(self, name: str, user_name: str, ui_color: str = "",
                           voice: str = ""):
        """Update all name/theme-dependent UI elements and persist to config."""
        self._assistant_name = name.strip() or "LangVis"
        self.setWindowTitle(f"{self._assistant_name} — language tutor")
        self._title_lbl.setText(self._assistant_name)
        self._log._ai_name_lc = self._assistant_name.lower()
        self.hud._assistant_name = self._assistant_name

        color_changed = False
        if ui_color:
            old = current_palette()
            if apply_ui_accent(ui_color):
                # Live-paint the whole interface (panels, buttons, borders, HUD)
                retheme_all_widgets(old, current_palette())
                color_changed = old["PRI"] != C.PRI

        # Voice change → persist and, if it actually changed, rebuild the Live
        # session so the new voice takes effect (it's fixed at connect time).
        voice_changed = False
        if voice:
            from memory.config_manager import get_voice, save_voice
            if voice != get_voice():
                save_voice(voice)
                voice_changed = True

        try:
            data = _read_full_config()
            data["assistant_name"] = self._assistant_name
            data["user_name"] = user_name.strip()
            if ui_color:
                data["ui_color"] = ui_color.strip().lower()
            API_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")
            self._log.append_log(f"SYS: Identity updated — {display}")
            if color_changed:
                self._log.append_log(f"SYS: UI colour applied — {ui_color}")
            if voice_changed:
                self._log.append_log(f"SYS: Voice set — {voice}")
        except Exception as e:
            self._log.append_log(f"ERR: Config save failed — {e}")

        if voice_changed and self.on_voice_change:
            self.on_voice_change()

    def _centre_overlay(self, ov) -> None:
        """Place a floating overlay in the middle of the HUD and show it."""
        cw = self.centralWidget()
        ov.adjustSize()
        ov.setGeometry(
            max(0, (cw.width()  - ov.width())  // 2),
            max(0, (cw.height() - ov.height()) // 2),
            ov.width(), ov.height(),
        )
        ov.show()
        ov.raise_()

    # ── Audio devices ────────────────────────────────────────────────────────

    def _open_audio_devices(self):
        ov = AudioDeviceOverlay(parent=self.centralWidget())
        ov.picked.connect(self._on_audio_devices_applied)
        self._centre_overlay(ov)
        self._audio_overlay = ov            # keep a reference so it isn't GC'd

    def _on_audio_devices_applied(self):
        self._log.append_log("SYS: Audio devices updated.")
        if self.on_audio_device_change:
            self.on_audio_device_change()

    # ── Memory panel ─────────────────────────────────────────────────────────

    def _open_memory_panel(self):
        ov = MemoryOverlay(parent=self.centralWidget())
        self._centre_overlay(ov)
        self._memory_overlay = ov

    # ── Irreversible-action confirmation ─────────────────────────────────────

    def _open_plugin_settings(self):
        sections = self.get_plugin_settings() if self.get_plugin_settings else []
        cw = self.centralWidget()
        ov = PluginSettingsOverlay(sections, parent=cw)
        ow = PluginSettingsOverlay._OW
        oh = min(560, cw.height() - 16)
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.show()
        ov.raise_()
        self._plugin_settings_overlay = ov   # keep a reference so it isn't GC'd

    # ── Clipboard intelligence ───────────────────────────────────────────────────

    def _do_interrupt(self):
        if self.on_interrupt:
            self.on_interrupt()

    def _toggle_mute(self):
        self._muted = not self._muted
        self.hud.muted = self._muted
        self._style_mute_btn()
        if self._muted:
            self._apply_state("MUTED")
            self._log.append_log("SYS: Microphone muted.")
        else:
            self._apply_state("LISTENING")
            self._log.append_log("SYS: Microphone active.")

    def _style_mute_btn(self):
        if self._muted:
            self._mute_btn.setText("Microphone off  ·  F4")
            self._mute_btn.setStyleSheet(
                btn_tone(C.RED, C.MUTED_GHO, C.MUTED_GHO, 12).replace(
                    "text-align: left;", "text-align: center;"))
        else:
            self._mute_btn.setText("Microphone on  ·  F4")
            self._mute_btn.setStyleSheet(
                btn_tone(C.GREEN, C.GREEN_GHO, C.GREEN_GHO, 12).replace(
                    "text-align: left;", "text-align: center;"))

    def _send(self):
        txt = self._input.text().strip()
        if not txt: return
        self._input.clear()
        self._log.append_log(f"You: {txt}")
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(txt,), daemon=True).start()

    def _apply_state(self, state: str):
        self.hud.state    = state
        self.hud.speaking = (state == "SPEAKING")

    def _check_config(self) -> bool:
        if not API_FILE.exists(): return False
        try:
            d = json.loads(API_FILE.read_text(encoding="utf-8"))
            return bool(d.get("gemini_api_key")) and bool(d.get("os_system"))
        except Exception:
            return False

    def _show_setup(self):
        ov = SetupOverlay(self.centralWidget())
        cw = self.centralWidget()
        ow, oh = 460, 390
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.done.connect(self._on_setup_done)
        ov.show()
        self._overlay = ov

    def _on_setup_done(self, key: str, os_name: str):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        API_FILE.write_text(
            json.dumps({"gemini_api_key": key, "os_system": os_name}, indent=4),
            encoding="utf-8",
        )
        self._ready = True
        if self._overlay:
            self._overlay.hide()
            self._overlay = None
        self._apply_state("LISTENING")
        self._assistant_name = _read_full_config().get("assistant_name", "LangVis") or "LangVis"
        self._log.append_log(f"SYS: Initialised. OS={os_name.upper()}. {self._assistant_name} online.")


class _RootShim:
    def __init__(self, app: QApplication):
        self._app = app
    def mainloop(self):
        self._app.exec()
    def protocol(self, *_):
        pass


class LangVisUI:
    def __init__(self, face_path: str, size=None):
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setStyle("Fusion")
        self._app.setFont(font(10))
        self._win = MainWindow(face_path)
        self.root = _RootShim(self._app)
        self._win.show()

    @property
    def muted(self) -> bool:
        return self._win._muted

    @muted.setter
    def muted(self, v: bool):
        if v != self._win._muted:
            self._win._toggle_mute()

    @property
    def on_text_command(self):
        return self._win.on_text_command

    @on_text_command.setter
    def on_text_command(self, cb):
        self._win.on_text_command = cb

    @property
    def on_interrupt(self):
        return self._win.on_interrupt

    @on_interrupt.setter
    def on_interrupt(self, cb):
        self._win.on_interrupt = cb

    @property
    def on_voice_change(self):
        return self._win.on_voice_change

    @on_voice_change.setter
    def on_voice_change(self, cb):
        self._win.on_voice_change = cb

    @property
    def on_audio_device_change(self):
        return self._win.on_audio_device_change

    @on_audio_device_change.setter
    def on_audio_device_change(self, cb):
        self._win.on_audio_device_change = cb

    @property
    def get_plugin_settings(self):
        return self._win.get_plugin_settings

    @get_plugin_settings.setter
    def get_plugin_settings(self, cb):
        self._win.get_plugin_settings = cb

    @property
    def get_lesson_status(self):
        return self._win.get_lesson_status

    @get_lesson_status.setter
    def get_lesson_status(self, cb):
        self._win.get_lesson_status = cb

    @property
    def get_syllabus(self):
        return self._win.get_syllabus

    @get_syllabus.setter
    def get_syllabus(self, cb):
        self._win.get_syllabus = cb
        # The syllabus panel polls this directly, so it needs the callable too —
        # wiring only the window would leave the list permanently empty.
        try:
            panel = self._win._syllabus
            panel.get_syllabus = cb
            # Fill it now rather than on the next poll — through a signal,
            # because this setter is called from the session thread and the rows
            # must be built by the thread that owns them.
            panel.refresh_now.emit()
        except Exception:
            pass

    @property
    def get_coaching(self):
        return self._win.get_coaching

    @get_coaching.setter
    def get_coaching(self, cb):
        self._win.get_coaching = cb
        # The two panels poll it directly, so they need the callable as well.
        for panel in ("_assistant", "_checklist"):
            try:
                getattr(self._win, panel).get_coaching = cb
            except Exception:
                pass

    @property
    def on_language_change(self):
        return self._win.on_language_change

    @on_language_change.setter
    def on_language_change(self, cb):
        self._win.on_language_change = cb

    @property
    def on_wake_toggle(self):
        return self._win.on_wake_toggle

    @on_wake_toggle.setter
    def on_wake_toggle(self, cb):
        self._win.on_wake_toggle = cb

    @property
    def on_wake_manual(self):
        return self._win.on_wake_manual

    @on_wake_manual.setter
    def on_wake_manual(self, cb):
        self._win.on_wake_manual = cb

    @property
    def wake_get_state(self):
        return self._win.wake_get_state

    @wake_get_state.setter
    def wake_get_state(self, cb):
        self._win.wake_get_state = cb

    def set_audio_level(self, level: float) -> None:
        """Thread-safe: feed a 0.0–1.0 live audio level to the HUD waveform.
        Called from the audio threads; a plain float store is atomic under the
        GIL, so no signal/lock is needed for this cosmetic value."""
        try:
            self._win.hud.set_audio_level(level)
        except Exception:
            pass

    def set_state(self, state: str):
        self._win._state_sig.emit(state)

    def write_log(self, text: str):
        self._win._log_sig.emit(text)

    def wait_for_api_key(self):
        while not self._win._ready:
            time.sleep(0.1)

    def show_content(self, title: str, text: str):
        """Thread-safe: display content in the panel below the HUD."""
        self._win._content_sig.emit(title[:48], text[:4000])

    def prompt_reconfig(self):
        """Thread-safe: show the API key setup overlay (e.g. after an auth error)."""
        self._win._ready = False
        self._win._reconfig_sig.emit()

    @property
    def assistant_name(self) -> str:
        return self._win._assistant_name

    def start_speaking(self):
        self.set_state("SPEAKING")

    def stop_speaking(self):
        if not self.muted:
            self.set_state("LISTENING")