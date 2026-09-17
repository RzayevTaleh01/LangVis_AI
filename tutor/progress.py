"""
tutor/progress.py — everything the tutor knows about the learner.

One JSON file per language (english/level.json, later slovak/level.json) holds:

  samples / days / totals   how well they speak, measured sentence by sentence
  skills                    per-skill evidence: recent right/wrong uses, real
                            mistakes, when to review it next
  course                    where they are in the curriculum
  vocab                     words they had to say in their own language, until
                            they use them in the target language themselves

From that it derives the three things the lesson runs on: the LEVEL (how to
speak to them), the FOCUS (which skills are weakest and must be fixed), and
the PLAN (what this session teaches). progress.md is regenerated from the same
state on every update, so the human file can never drift from the numbers.
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from tutor import curriculum as cur

# ── Measurement constants ────────────────────────────────────────────────────

ROLLING_WINDOW = 25            # sentences in the rolling level
MIN_SAMPLES_FOR_MEASURED = 8   # before this, the stated level is believed
PRIOR_WEIGHT = 20              # the stated level counts as this many sentences…
PRIOR_FADE = 60                # …fading to nothing by this many measured ones
SUBSTANTIVE_WORDS = 5          # shorter sentences are practice, not evidence

# A word used once is luck; used twice in the learner's own sentences it is
# theirs. That second use is what ticks it off the unit's checklist.
LEXIS_CHECKED_USES = 2

SKILL_WINDOW = 12              # recent uses that decide a skill's mastery
REPEAT_ERRORS = 3              # errors in the last 8 uses that trigger a focus drill
FOCUS_NUDGE_GAP = 600          # seconds before the same skill can trigger again
PERSISTENCE_FACTOR = 4         # a unit also passes after 4× the practice at ≥55

MAX_SAMPLES = 600
MAX_DAYS = 180
MAX_DAY_FIXES = 30
MAX_EXAMPLES = 6
MAX_VOCAB = 300
RENDER_DAYS = 30

_BANDS = ((89, "C2"), (74, "C1"), (56, "B2"), (38, "B1"), (20, "A2"), (0, "A1"))
_BAND_MIDPOINT = {"A1": 10.0, "A2": 28.0, "B1": 46.0, "B2": 64.0,
                  "C1": 81.0, "C2": 94.0}


def band(score: float) -> str:
    for floor, name in _BANDS:
        if score >= floor:
            return name
    return "A1"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _today() -> str:
    return date.today().isoformat()


# ── Files ────────────────────────────────────────────────────────────────────

def data_dir(base: Path, lang: dict) -> Path:
    return base / lang["data_dir"]


def _empty_state() -> dict:
    return {
        "version": 2,
        "created": _now_iso(),
        "declared_level": "A2",
        "goal_level": "B2",
        "paused": False,
        "totals": {"utterances": 0, "target_utterances": 0, "native_utterances": 0,
                   "words": 0, "scored": 0},
        "samples": [],
        "days": {},
        "skills": {},
        "lexis": {},        # target word / phrasal -> {kind, unit, uses, last}
        "course": _empty_course(),
        "vocab": {},
        "last_spoken": 0.0,
    }


def _empty_course() -> dict:
    return {"stage": 0, "unit": 0, "unit_practice": 0, "unit_started": _now_iso(),
            "completed": [], "finished": False}


def load(path: Path) -> dict:
    if not path.exists():
        return _empty_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _empty_state()
    if not isinstance(data, dict):
        return _empty_state()
    state = _empty_state()
    state.update(data)
    if int(data.get("version", 1)) < 2:
        _migrate_v1(state)
    return state


def save(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state["samples"] = state.get("samples", [])[-MAX_SAMPLES:]
    days = state.get("days", {})
    if len(days) > MAX_DAYS:
        for key in sorted(days)[:len(days) - MAX_DAYS]:
            days.pop(key, None)
    vocab = state.get("vocab", {})
    if len(vocab) > MAX_VOCAB:
        for key, _ in sorted(vocab.items(), key=lambda kv: kv[1].get("last", ""))[
                :len(vocab) - MAX_VOCAB]:
            vocab.pop(key, None)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _migrate_v1(state: dict) -> None:
    """The english_coach file, before the course existed. Its measurements are
    kept whole; its free-text grammar topics become skill evidence, so the
    learner's real weak points are on the focus list from the first lesson."""
    totals = state.setdefault("totals", {})
    totals.setdefault("target_utterances", totals.get("english_utterances", 0))
    totals.setdefault("native_utterances", 0)
    totals.setdefault("scored", sum(
        1 for s in state.get("samples", [])
        if isinstance(s, dict) and int(s.get("words", 0)) >= SUBSTANTIVE_WORDS))

    skills = state.setdefault("skills", {})
    for topic, count in (state.get("topic_totals") or {}).items():
        sid = cur.LEGACY_TOPIC_MAP.get(str(topic).lower())
        if not sid:
            continue
        sk = _skill(skills, sid)
        sk["errors"] += int(count)
        sk["recent"] = ([0] * min(int(count), 4) + sk["recent"])[-SKILL_WINDOW:]

    for key in sorted(state.get("days", {})):
        for c in state["days"][key].get("corrections", []):
            sid = cur.LEGACY_TOPIC_MAP.get(str(c.get("rule", "")).lower())
            if sid:
                _add_example(_skill(skills, sid), c.get("wrong", ""), c.get("right", ""))

    # The learner asked for A2 → B2. A C1 target was the old default.
    if state.get("goal_level") in (None, "", "C1", "C2"):
        state["goal_level"] = "B2"
    state["course"] = state.get("course") or _empty_course()
    state["vocab"] = state.get("vocab") or {}
    state["lexis"] = state.get("lexis") or {}
    state["version"] = 2


# ── Level ────────────────────────────────────────────────────────────────────

def scoring_samples(state: dict, window: int = ROLLING_WINDOW) -> list:
    samples = [s for s in state.get("samples", []) if isinstance(s, dict)]
    substantive = [s for s in samples if int(s.get("words", 0)) >= SUBSTANTIVE_WORDS]
    return (substantive or samples)[-window:]


def effective_level(state: dict) -> tuple[str, float, bool]:
    """(band, score, measured?) — the stated level is a prior worth
    PRIOR_WEIGHT sentences that fades as real evidence accumulates."""
    scoring = scoring_samples(state)
    declared = state.get("declared_level") or "A2"
    prior = _BAND_MIDPOINT.get(declared, 28.0)
    n = len(scoring)
    if not n:
        return declared, prior, False
    fade = max(0.0, 1.0 - int(state.get("totals", {}).get("scored", 0)) / PRIOR_FADE)
    weight = PRIOR_WEIGHT * fade
    mean = sum(float(s.get("score", 0)) for s in scoring) / n
    blended = (prior * weight + mean * n) / (weight + n)
    return band(blended), blended, n >= MIN_SAMPLES_FOR_MEASURED


def _day(state: dict, key: str | None = None) -> dict:
    day = state.setdefault("days", {}).setdefault(key or _today(), {})
    for field, default in (("all_utterances", 0), ("english_utterances", 0),
                           ("native_utterances", 0), ("words", 0),
                           ("score_sum", 0.0), ("score_n", 0), ("best", 0),
                           ("topics", {}), ("corrections", []), ("notes", [])):
        day.setdefault(field, default if not isinstance(default, (dict, list))
                       else type(default)())
    return day


def day_mean(day: dict) -> float:
    n = day.get("score_n") or 0
    return (day.get("score_sum", 0.0) / n) if n else 0.0


def trend(state: dict, days_back: int = 7) -> tuple[float, str]:
    scored = [(k, v) for k, v in sorted(state.get("days", {}).items())
              if (v.get("score_n") or 0) > 0]
    if len(scored) < 2:
        return 0.0, "—"
    latest_key, latest = scored[-1]
    cutoff = (date.fromisoformat(latest_key) - timedelta(days=days_back)).isoformat()
    older = [p for p in scored[:-1] if p[0] <= cutoff] or [scored[0]]
    delta = day_mean(latest) - day_mean(older[-1][1])
    return delta, ("▲" if delta > 1 else "▼" if delta < -1 else "▬")


# ── Skills ───────────────────────────────────────────────────────────────────

def _skill(skills: dict, sid: str) -> dict:
    sk = skills.setdefault(sid, {})
    sk.setdefault("correct", 0)
    sk.setdefault("errors", 0)
    sk.setdefault("recent", [])
    sk.setdefault("examples", [])
    sk.setdefault("last_seen", "")
    sk.setdefault("next_review", "")
    sk.setdefault("nudged", 0.0)
    return sk


def _add_example(sk: dict, wrong: str, right: str) -> None:
    wrong, right = str(wrong or "")[:140], str(right or "")[:140]
    if not right or any(e.get("wrong") == wrong for e in sk["examples"]):
        return
    sk["examples"] = (sk["examples"] + [{"wrong": wrong, "right": right}])[-MAX_EXAMPLES:]


def mastery(sk: dict | None) -> int | None:
    """0–100 from the recent window, errors counting double. None = no evidence."""
    recent = (sk or {}).get("recent") or []
    if not recent:
        return None
    c = sum(recent)
    e = len(recent) - c
    return round(100 * (c + 1) / (c + 2 * e + 2))


def skill_status(sk: dict | None) -> str:
    m = mastery(sk)
    if m is None:
        return "new"
    if m < 50:
        return "weak"
    if m >= cur.SKILL_PASS and sk.get("correct", 0) >= cur.SKILL_MIN_CORRECT:
        return "strong"
    return "learning"


def _schedule_review(sk: dict) -> None:
    status = skill_status(sk)
    streak = 0
    for outcome in reversed(sk["recent"]):
        if outcome != 1:
            break
        streak += 1
    days = {"weak": 1, "learning": 2}.get(status, min(30, 3 * (1 + streak)))
    if sk["recent"] and sk["recent"][-1] == 0:
        days = 0
    sk["next_review"] = (date.today() + timedelta(days=days)).isoformat()


def _use(skills: dict, sid: str, ok: bool) -> dict:
    sk = _skill(skills, sid)
    sk["correct" if ok else "errors"] += 1
    sk["recent"] = (sk["recent"] + [1 if ok else 0])[-SKILL_WINDOW:]
    sk["last_seen"] = _now_iso()
    _schedule_review(sk)
    return sk


# ── Course position ──────────────────────────────────────────────────────────

def position(state: dict, lang: dict) -> dict:
    """Where the learner is: stage, unit (None in consolidation), numbers."""
    course = state.setdefault("course", _empty_course())
    stages = lang["stages"]
    if not stages:
        return {"stage": None, "unit": None, "finished": False}
    si = min(int(course.get("stage", 0)), len(stages) - 1)
    stage = stages[si]
    ui = int(course.get("unit", 0))
    unit = stage["units"][ui] if ui < len(stage["units"]) else None
    return {
        "stage_index": si, "unit_index": ui, "stage": stage, "unit": unit,
        "finished": bool(course.get("finished")),
        "number": cur.unit_number(lang, si, min(ui, len(stage["units"]) - 1)),
        "total": cur.total_units(lang),
        "practice": int(course.get("unit_practice", 0)),
    }


def unit_progress(state: dict, lang: dict) -> tuple[int, list[str]]:
    """(0–100, what is still missing) for the current unit."""
    pos = position(state, lang)
    unit = pos.get("unit")
    if pos.get("finished"):
        return 100, []
    if unit is None:
        stage = pos["stage"]
        score = effective_level(state)[1]
        need = stage["exit_score"]
        missing = [] if score >= need else [f"overall level {score:.0f}/{need}"]
        return min(100, round(100 * score / need)), missing
    missing = []
    parts = [min(1.0, pos["practice"] / cur.UNIT_MIN_PRACTICE)]
    if pos["practice"] < cur.UNIT_MIN_PRACTICE:
        missing.append(f"{cur.UNIT_MIN_PRACTICE - pos['practice']} more sentences")
    lexis = lexis_checklist(state, unit)
    parts.append(min(1.0, lexis["words_done"] / max(1, lexis["words_needed"])))
    parts.append(min(1.0, lexis["phrasals_done"] / max(1, lexis["phrasals_needed"])))
    if lexis["words_done"] < lexis["words_needed"]:
        missing.append(f"use {lexis['words_needed'] - lexis['words_done']} more "
                       f"new words")
    if lexis["phrasals_done"] < lexis["phrasals_needed"]:
        missing.append(f"use {lexis['phrasals_needed'] - lexis['phrasals_done']} "
                       f"more phrasal verb(s)")
    for sid in unit["skills"]:
        sk = state.get("skills", {}).get(sid)
        m = mastery(sk) or 0
        correct = (sk or {}).get("correct", 0)
        parts.append(min(1.0, m / cur.SKILL_PASS) * 0.5
                     + min(1.0, correct / cur.SKILL_MIN_CORRECT) * 0.5)
        if skill_status(sk) != "strong":
            name = lang["skills"].get(sid, (sid,))[0]
            missing.append(f"{name}: mastery {m}/{cur.SKILL_PASS}, "
                           f"correct uses {correct}/{cur.SKILL_MIN_CORRECT}")
    return round(100 * sum(parts) / len(parts)), missing


def _unit_passed(state: dict, lang: dict, unit: dict) -> bool:
    practice = int(state["course"].get("unit_practice", 0))
    skills = state.get("skills", {})
    lexis = lexis_checklist(state, unit)
    lexis_ok = (lexis["words_done"] >= lexis["words_needed"]
                and lexis["phrasals_done"] >= lexis["phrasals_needed"])
    grammar_ok = all(skill_status(skills.get(sid)) == "strong"
                     for sid in unit["skills"])
    if practice >= cur.UNIT_MIN_PRACTICE and grammar_ok and lexis_ok:
        return True
    # Persistence: a skill or a word the analyser rarely sees should not trap
    # the learner in one unit forever. Plenty of practice at a decent mastery,
    # with at least half the vocabulary used, passes.
    return (practice >= cur.UNIT_MIN_PRACTICE * PERSISTENCE_FACTOR
            and all((mastery(skills.get(sid)) or 0) >= 55 for sid in unit["skills"])
            and lexis["words_done"] * 2 >= lexis["words_needed"])


def advance(state: dict, lang: dict, force: bool = False) -> list[str]:
    """Move through the course as far as the evidence allows. Returns events."""
    events: list[str] = []
    course = state.setdefault("course", _empty_course())
    stages = lang["stages"]
    for _ in range(len(stages) * 6):
        if course.get("finished") or not stages:
            break
        si = course["stage"]
        stage = stages[si]
        ui = course["unit"]
        if ui < len(stage["units"]):
            unit = stage["units"][ui]
            if not (force or _unit_passed(state, lang, unit)):
                break
            force = False
            course["completed"].append(unit["id"])
            course["unit"] = ui + 1
            course["unit_practice"] = 0
            course["unit_started"] = _now_iso()
            if ui + 1 < len(stage["units"]):
                nxt = stage["units"][ui + 1]
                events.append(f"Unit {unit['title']!r} complete. Next unit: "
                              f"{nxt['title']!r}.")
            else:
                events.append(f"Unit {unit['title']!r} complete — every unit of "
                              f"stage {stage['id']} is done. Now: stage review.")
            continue
        if effective_level(state)[1] < stage["exit_score"]:
            break
        if si + 1 >= len(stages):
            course["finished"] = True
            events.append(f"Stage {stage['id']} passed — the whole course "
                          f"(up to {stage['band']}) is complete!")
            break
        course["stage"] = si + 1
        course["unit"] = 0
        course["unit_practice"] = 0
        course["unit_started"] = _now_iso()
        events.append(f"Stage {stage['id']} passed! New stage: "
                      f"{stages[si + 1]['id']} {stages[si + 1]['title']!r}.")
    for e in events:
        note = f"{datetime.now():%H:%M} {e}"
        _day(state)["notes"].append(note)
    return events


# ── Recording ────────────────────────────────────────────────────────────────

def record_target(state: dict, lang: dict, text: str, analysis: dict,
                  n_words: int, used_lexis: list | None = None,
                  lexis_kinds: dict | None = None) -> dict:
    """Fold one analysed target-language sentence into the state."""
    skills = state.setdefault("skills", {})
    day = _day(state)
    before = band(effective_level(state)[1]) if state.get("samples") else ""

    state["samples"].append({"ts": _now_iso(), "score": round(analysis["score"], 1),
                             "level": band(analysis["score"]), "words": n_words})
    totals = state.setdefault("totals", {})
    for key, inc in (("utterances", 1), ("target_utterances", 1), ("words", n_words)):
        totals[key] = totals.get(key, 0) + inc
    substantive = n_words >= SUBSTANTIVE_WORDS
    if substantive:
        totals["scored"] = totals.get("scored", 0) + 1
        state["course"]["unit_practice"] = state["course"].get("unit_practice", 0) + 1

    day["all_utterances"] += 1
    day["english_utterances"] += 1
    day["words"] += n_words
    day["score_sum"] += analysis["score"]
    day["score_n"] += 1
    day["best"] = max(day.get("best", 0), round(analysis["score"]))

    repeated: list[str] = []
    now = time.time()
    for c in analysis["corrections"]:
        sid = c["skill"]
        sk = _use(skills, sid, ok=False)
        _add_example(sk, c.get("wrong"), c.get("right"))
        name = lang["skills"].get(sid, (sid,))[0]
        day["topics"][name] = day["topics"].get(name, 0) + 1
        day["corrections"].append({"wrong": str(c.get("wrong", ""))[:160],
                                   "right": str(c.get("right", ""))[:160],
                                   "rule": name, "why": str(c.get("why", ""))[:90]})
        if (sk["recent"][-8:].count(0) >= REPEAT_ERRORS
                and now - float(sk.get("nudged", 0)) > FOCUS_NUDGE_GAP
                and sid not in repeated):
            sk["nudged"] = now
            repeated.append(sid)
    day["corrections"] = day["corrections"][-MAX_DAY_FIXES:]

    for sid in analysis["correct_uses"]:
        _use(skills, sid, ok=True)

    lowered = f" {text.lower()} "
    for key, item in state.setdefault("vocab", {}).items():
        if f" {key} " in lowered:
            item["used"] = item.get("used", 0) + 1
    for w in analysis.get("native_words", []):
        add_vocab(state, w.get("target", ""), w.get("native", ""))

    newly_checked = record_lexis(state, used_lexis or [], lexis_kinds or {})

    events = advance(state, lang)
    after = band(effective_level(state)[1])
    band_moved = ""
    if before and after != before:
        up = cur.band_index(after) > cur.band_index(before)
        band_moved = f"Level {'moved up' if up else 'slipped'}: {before} → {after}."
        day["notes"].append(band_moved)

    return {"score": analysis["score"], "level": after, "band_moved": band_moved,
            "events": events, "repeated": repeated, "checked": newly_checked}


def record_native(state: dict, help_data: dict) -> None:
    totals = state.setdefault("totals", {})
    totals["utterances"] = totals.get("utterances", 0) + 1
    totals["native_utterances"] = totals.get("native_utterances", 0) + 1
    day = _day(state)
    day["all_utterances"] += 1
    day["native_utterances"] += 1
    for w in help_data.get("words", []):
        add_vocab(state, w.get("target", ""), w.get("native", ""))


def record_heard(state: dict) -> None:
    totals = state.setdefault("totals", {})
    totals["utterances"] = totals.get("utterances", 0) + 1
    _day(state)["all_utterances"] += 1


def record_lexis(state: dict, used: list, kinds: dict) -> list:
    """Count the target words and phrasal verbs this sentence used.

    Returns the items that crossed into "checked" on this sentence, so the
    tutor can acknowledge them once and move on.
    """
    lexis = state.setdefault("lexis", {})
    newly = []
    for item in used:
        entry = lexis.setdefault(item, {"kind": kinds.get(item, "word"),
                                        "uses": 0, "first": _today()})
        before = entry["uses"]
        entry["uses"] = before + 1
        entry["last"] = _now_iso()
        entry["kind"] = kinds.get(item, entry.get("kind", "word"))
        if before < LEXIS_CHECKED_USES <= entry["uses"]:
            newly.append(item)
    return newly


def lexis_checklist(state: dict, unit: dict | None) -> dict:
    """The unit's words and phrasal verbs, each with how often it has been used
    and whether it counts as learned. This is what the checklist draws."""
    lexis = state.get("lexis", {})

    def rows(items: list) -> list:
        out = []
        for item in items or []:
            uses = int(lexis.get(item, {}).get("uses", 0))
            out.append({"text": item, "uses": uses,
                        "checked": uses >= LEXIS_CHECKED_USES})
        return out

    words_rows = rows((unit or {}).get("words", []))
    phrasal_rows = rows((unit or {}).get("phrasals", []))
    return {
        "words": words_rows,
        "phrasals": phrasal_rows,
        "words_done": sum(1 for r in words_rows if r["checked"]),
        "phrasals_done": sum(1 for r in phrasal_rows if r["checked"]),
        "words_needed": cur.UNIT_WORDS_NEEDED,
        "phrasals_needed": cur.UNIT_PHRASALS_NEEDED,
    }


def add_vocab(state: dict, target: str, native: str) -> None:
    key = str(target or "").strip().lower()
    if not key or len(key) > 40:
        return
    item = state.setdefault("vocab", {}).setdefault(
        key, {"native": "", "count": 0, "used": 0, "first": _today()})
    item["native"] = str(native or item.get("native", ""))[:40]
    item["count"] = item.get("count", 0) + 1
    item["last"] = _now_iso()


# ── What to work on ──────────────────────────────────────────────────────────

def focus_skills(state: dict, lang: dict, limit: int = 3) -> list[tuple[str, dict]]:
    """The weakest skills worth fixing now: ones that have gone wrong recently,
    at or below the learner's stage, with the current unit's targets first."""
    pos = position(state, lang)
    if pos.get("stage") is None:
        return []
    in_scope = set(cur.skills_up_to(lang, pos["stage_index"]))
    unit_targets = set((pos.get("unit") or {}).get("skills", []))
    stage_band = cur.band_index(pos["stage"]["band"])
    ranked = []
    for sid, sk in state.get("skills", {}).items():
        if sid not in lang["skills"]:
            continue
        status = skill_status(sk)
        errors = sk.get("recent", []).count(0)
        if status in ("new", "strong") or not errors:
            continue
        skill_band = cur.band_index(lang["skills"][sid][1])
        if sid not in in_scope and sid not in unit_targets and skill_band > stage_band:
            continue            # beyond their level: logged, not drilled
        m = mastery(sk) or 0
        priority = (100 - m) * (1 + errors / 4) + (25 if sid in unit_targets else 0)
        ranked.append((priority, sid, sk))
    ranked.sort(key=lambda r: r[0], reverse=True)
    return [(sid, sk) for _, sid, sk in ranked[:limit]]


def due_reviews(state: dict, lang: dict, limit: int = 2) -> list[str]:
    today = _today()
    focus = {sid for sid, _ in focus_skills(state, lang)}
    due = [sid for sid, sk in state.get("skills", {}).items()
           if sid in lang["skills"] and sid not in focus
           and skill_status(sk) != "new" and sk.get("next_review", "") <= today]
    due.sort(key=lambda sid: state["skills"][sid].get("next_review", ""))
    return due[:limit]


def words_to_reuse(state: dict, limit: int = 6) -> list[tuple[str, dict]]:
    items = [(k, v) for k, v in state.get("vocab", {}).items() if v.get("used", 0) < 2]
    items.sort(key=lambda kv: kv[1].get("last", ""), reverse=True)
    return items[:limit]


# ── The lesson plan ──────────────────────────────────────────────────────────

def lesson_plan(state: dict, lang: dict, native_language: str) -> str:
    """The plan the tutor teaches from — injected into the session prompt and
    returned by the tool when the plan changes mid-lesson."""
    level, score, measured = effective_level(state)
    pos = position(state, lang)
    skills = lang["skills"]
    lines = [f"[LESSON PLAN — {lang['name'].upper()}]",
             f"Course: A2 → {state.get('goal_level', 'B2')}. Learner's native language: "
             f"{native_language}.",
             f"Measured level: {level} ({score:.0f}/100"
             + (")" if measured else ", still mostly their own estimate)") + "."]

    if pos.get("finished"):
        lines.append("The course is COMPLETE. Keep them at B2: free conversation on "
                     "demanding topics, precise corrections, natural collocations.")
    else:
        stage = pos["stage"]
        # The measured number is one sentence at a time and always flatters the
        # learner; the stage is where their grammar has actually been proved. So
        # the language they HEAR follows the stage, and rises with it.
        speak = min(level, stage["band"], key=cur.band_index)
        lines.append(f"Speak to them at {speak} — the level of this stage — even if the "
                     f"measured number above is higher.")
        unit = pos.get("unit")
        progress, missing = unit_progress(state, lang)
        lines.append(f"Stage {stage['id']} \"{stage['title']}\" (level {stage['band']}).")
        if unit:
            lines += [
                f"CURRENT UNIT {pos['number']}/{pos['total']}: \"{unit['title']}\" — "
                f"{progress}% done.",
                "  Target grammar: " + "; ".join(
                    f"{skills[s][0]} ({skills[s][2]})" for s in unit["skills"]),
                f"  Theme / vocabulary: {unit['theme']}.",
                "  Model sentences to get them producing (use these patterns, not "
                "these exact words): " + " | ".join(unit.get("examples", [])),
                f"  Speaking task: {unit['task']}",
                f"  Goal: the learner can {unit['can_do']}.",
                f"  Stage emphasis: {cur.STAGE_EMPHASIS.get(stage['id'], '')}.",
            ]
            lexis = lexis_checklist(state, unit)
            todo_w = [r["text"] for r in lexis["words"] if not r["checked"]]
            todo_p = [r["text"] for r in lexis["phrasals"] if not r["checked"]]
            done_w = [r["text"] for r in lexis["words"] if r["checked"]]
            lines += [
                "  WORDS to install this unit (feed them into whatever the "
                "learner talks about, then make them use each one twice): "
                + (", ".join(todo_w) if todo_w else "all done"),
                "  PHRASAL VERBS to install: "
                + (", ".join(todo_p) if todo_p else "all done"),
            ]
            if done_w:
                lines.append("  Already theirs (reuse, do not re-teach): "
                             + ", ".join(done_w))
            methods = cur.methods_of(unit)
            if methods:
                lines.append("  HOW TO PRACTISE IT — run these techniques in this "
                             "order, not a quiz:")
                for m in methods:
                    lines.append(f"    · {m['name']} ({m['goal']}): {m['how']}")
        else:
            lines += [
                f"STAGE REVIEW: every unit of {stage['id']} is done. The stage "
                f"passes when the overall level reaches {stage['exit_score']}/100 "
                f"(now {score:.0f}). Hold free conversations at {stage['band']} "
                f"level on the themes of this stage and push the focus skills below.",
            ]
        if missing:
            lines.append("  Still missing: " + "; ".join(missing[:4]) + ".")

    focus = focus_skills(state, lang)
    if focus:
        lines.append("FOCUS — their real repeated weak points. Fix these first:")
        for i, (sid, sk) in enumerate(focus, 1):
            name, _b, hint = skills[sid]
            ex = sk.get("examples", [])[-2:]
            shown = "; ".join(f"\"{e['wrong']}\" → \"{e['right']}\"" for e in ex)
            lines.append(f"  {i}. {name} ({hint}) — mastery {mastery(sk)}/100, "
                         f"{sk.get('errors', 0)} mistakes so far."
                         + (f" Their mistakes: {shown}" if shown else ""))
    reviews = due_reviews(state, lang)
    if reviews:
        lines.append("REVIEW due today (use once or twice in conversation): "
                     + ", ".join(skills[s][0] for s in reviews) + ".")
    vocab = words_to_reuse(state)
    if vocab:
        lines.append("WORDS to recycle (they needed these in "
                     f"{native_language}; make them use them): "
                     + ", ".join(f"{k} ({v.get('native', '')})" for k, v in vocab) + ".")
    lines.append("")
    return "\n".join(lines)


# ── The syllabus, as the learner sees it ─────────────────────────────────────

def syllabus(state: dict, lang: dict) -> list[dict]:
    """The whole course in order, each unit marked done / current / to come.

    A learner who cannot see the road does not believe there is one. This is
    the same data the tutor teaches from — stages, units, target grammar, the
    model sentences and the speaking task — with their own position in it.
    """
    pos = position(state, lang)
    completed = set((state.get("course") or {}).get("completed", []))
    here = pos.get("number", 0)
    names = lang["skills"]
    out: list[dict] = []
    n = 0
    for si, stage in enumerate(lang["stages"]):
        units = []
        for ui, unit in enumerate(stage["units"]):
            n += 1
            if unit["id"] in completed:
                status = "done"
            elif si == pos.get("stage_index") and ui == pos.get("unit_index"):
                status = "current"
            elif n < here:
                status = "done"
            else:
                status = "todo"
            progress, missing = ((unit_progress(state, lang)) if status == "current"
                                 else (100 if status == "done" else 0, []))
            units.append({
                "id": unit["id"], "number": n, "title": unit["title"],
                "status": status, "progress": progress, "missing": missing,
                "skills": [names[s][0] for s in unit["skills"] if s in names],
                "hints": [names[s][2] for s in unit["skills"] if s in names],
                "theme": unit["theme"], "task": unit["task"],
                "can_do": unit["can_do"], "examples": list(unit.get("examples", [])),
                "methods": cur.methods_of(unit),
                "lexis": lexis_checklist(state, unit),
            })
        in_review = (si == pos.get("stage_index")
                     and pos.get("unit") is None and not pos.get("finished"))
        stage_status = ("current" if si == pos.get("stage_index") else
                        "done" if si < (pos.get("stage_index") or 0) else "todo")
        out.append({
            "id": stage["id"], "title": stage["title"], "band": stage["band"],
            "exit_score": stage["exit_score"], "status": stage_status,
            "emphasis": cur.STAGE_EMPHASIS.get(stage["id"], ""),
            "review": in_review, "units": units,
        })
    return out


# ── UI snapshot ──────────────────────────────────────────────────────────────

def ui_status(state: dict, lang: dict) -> dict:
    level, score, measured = effective_level(state)
    pos = position(state, lang)
    progress, _ = unit_progress(state, lang) if lang["stages"] else (0, [])
    unit = pos.get("unit")
    return {
        "level": level, "score": round(score), "measured": measured,
        "goal": state.get("goal_level", "B2"),
        "stage": (pos.get("stage") or {}).get("id", "—"),
        "unit_no": pos.get("number", 0), "unit_total": pos.get("total", 0),
        "unit_title": ("Course complete" if pos.get("finished") else
                       unit["title"] if unit else "Stage review"),
        "unit_progress": progress,
        "focus": [{"name": lang["skills"][sid][0], "mastery": mastery(sk) or 0}
                  for sid, sk in focus_skills(state, lang)],
        "sentences_today": _day(state).get("english_utterances", 0),
        "lexis": lexis_checklist(state, unit),
        "paused": bool(state.get("paused")),
    }


# ── The markdown log ─────────────────────────────────────────────────────────

def _cell(value) -> str:
    return str(value or "").replace("|", "/").replace("\n", " ").strip()


def render_log(path: Path, state: dict, lang: dict) -> None:
    level, score, measured = effective_level(state)
    pos = position(state, lang)
    delta, arrow = trend(state)
    totals = state.get("totals", {})
    progress, missing = unit_progress(state, lang)
    unit = pos.get("unit")

    out = [f"# {lang['name']} progress", "",
           "_Written by LangVis. Regenerated on every update — edits by hand are "
           "overwritten; `level.json` holds the raw numbers._", "",
           "## Where you are", "",
           f"- **Level:** **{level}** ({score:.0f}/100)"
           + ("" if measured else " — still mostly your own estimate"),
           f"- **Goal:** {state.get('goal_level', 'B2')}",
           f"- **Stage:** {(pos.get('stage') or {}).get('id', '—')} "
           f"{(pos.get('stage') or {}).get('title', '')}",
           f"- **Unit:** {pos.get('number')}/{pos.get('total')} — "
           + ("course complete" if pos.get("finished") else
              f"{unit['title']} ({progress}%)" if unit else f"stage review ({progress}%)"),
           f"- **Last 7 days:** {arrow} {delta:+.1f} points",
           f"- **Practised:** {totals.get('target_utterances', 0)} sentences, "
           f"{totals.get('words', 0)} words; fell back to your own language "
           f"{totals.get('native_utterances', 0)} times"]
    if unit:
        lexis = lexis_checklist(state, unit)
        out += ["", f"**Words used {lexis['words_done']}/{lexis['words_needed']}, "
                    f"phrasal verbs {lexis['phrasals_done']}/"
                    f"{lexis['phrasals_needed']}**", ""]
        for row in lexis["words"] + lexis["phrasals"]:
            mark = "x" if row["checked"] else " "
            out.append(f"- [{mark}] {row['text']}"
                       + (f" ({row['uses']}\u00d7)" if row["uses"] else ""))
        methods = cur.methods_of(unit)
        if methods:
            out += ["", "**Practised with:** "
                    + ", ".join(m["name"] for m in methods)]
    if missing:
        out += ["", "**To finish this unit:** " + "; ".join(missing)]

    focus = focus_skills(state, lang, limit=5)
    if focus:
        out += ["", "## Focus now", ""]
        for sid, sk in focus:
            out.append(f"- **{lang['skills'][sid][0]}** — mastery {mastery(sk)}/100, "
                       f"{sk.get('errors', 0)} mistakes")
            for e in sk.get("examples", [])[-2:]:
                out.append(f"  - ~~{_cell(e.get('wrong'))}~~ → {_cell(e.get('right'))}")

    rows = [(sid, sk) for sid, sk in state.get("skills", {}).items() if sid in lang["skills"]]
    if rows:
        rows.sort(key=lambda r: (mastery(r[1]) or 0))
        out += ["", "## Skills", "", "| Skill | Level | Mastery | Right | Wrong | Status |",
                "| --- | --- | --- | --- | --- | --- |"]
        for sid, sk in rows:
            name, b, _ = lang["skills"][sid]
            out.append(f"| {name} | {b} | {mastery(sk) or 0} | {sk.get('correct', 0)} "
                       f"| {sk.get('errors', 0)} | {skill_status(sk)} |")

    vocab = words_to_reuse(state, limit=20)
    if vocab:
        out += ["", "## Words to use", ""]
        out += [f"- **{k}** — {v.get('native', '')}" for k, v in vocab]

    out += ["", "## Daily record", ""]
    days = sorted(state.get("days", {}).items(), reverse=True)[:RENDER_DAYS]
    for key, day in days:
        if not (day.get("score_n") or day.get("native_utterances")):
            continue
        mean = day_mean(day)
        out += [f"### {key} — {band(mean)} ({mean:.0f}/100)", "",
                f"- {day.get('english_utterances', 0)} sentences, "
                f"{day.get('words', 0)} words, best {day.get('best', 0)}/100, "
                f"own language {day.get('native_utterances', 0)} times."]
        out += [f"- {n}" for n in day.get("notes", [])]
        corrections = day.get("corrections", [])
        if corrections:
            out += ["", "| You said | Better | Skill |", "| --- | --- | --- |"]
            out += [f"| {_cell(c.get('wrong'))} | {_cell(c.get('right'))} "
                    f"| {_cell(c.get('rule'))} |" for c in corrections]
        out += [""]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
