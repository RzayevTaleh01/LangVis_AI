"""
tutor/analysis.py — reading what the learner said.

Two kinds of utterance reach here:

  * one in the target language — measured on the CEFR scale, every mistake
    tied to a skill id from the curriculum, every structure used correctly
    recorded as evidence for that skill;
  * one in the learner's own language — a sign they could not say it in the
    target language. The words they were missing become vocabulary to reuse.

Language detection is local and cheap because it runs on every utterance; the
model gets the final word (it returns is_target_language) before anything is
recorded.
"""
from __future__ import annotations

import json
import re
import sys
import threading
from pathlib import Path

ANALYSIS_MODEL = "gemini-flash-lite-latest"   # per utterance: frequent, cheap
LESSON_MODEL   = "gemini-flash-latest"        # drills and one-off checks


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


API_CONFIG = _base_dir() / "config" / "api_keys.json"


# ── Is this English? ─────────────────────────────────────────────────────────

_AZ_TR_CHARS = set("əğıöüçşİĞÖÜÇŞƏ")

_EN_FUNCTION = {
    "the", "a", "an", "is", "are", "am", "was", "were", "be", "been", "being",
    "i", "you", "he", "she", "it", "we", "they", "me", "my", "your", "his",
    "her", "our", "their", "this", "that", "these", "those", "there",
    "to", "of", "and", "or", "but", "in", "on", "at", "for", "with", "from",
    "about", "into", "over", "after", "before", "because", "if", "when",
    "do", "does", "did", "have", "has", "had", "can", "could", "will",
    "would", "should", "must", "want", "need", "like", "know", "think",
    "what", "how", "why", "where", "who", "not", "no", "yes", "please",
    "let", "get", "go", "make", "take", "give", "tell", "show", "open",
    "close", "play", "find", "help", "very", "some", "any", "all", "more",
}

# Azerbaijani and Turkish words that survive transcription without their
# special letters, which would otherwise read as unknown-but-latin.
_NON_EN_WORDS = {
    "men", "sen", "bir", "ve", "ucun", "bu", "ne", "nece", "salam",
    "yaz", "et", "ac", "var", "yox", "olar", "deyil", "kimi", "ile",
    "ki", "amma", "cox", "yaxsi", "pis", "indi", "sonra",
    "gel", "ol", "ele", "mene", "sene", "bize", "onlar", "hansi",
    "niye", "harada", "zaman", "gun", "saat", "tesekkur", "lutfen",
    "ben", "ama", "icin", "nasil", "evet", "hayir", "tamam", "sey",
}

_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


def words(text: str) -> list[str]:
    return _WORD_RE.findall((text or "").lower())


def looks_english(text: str) -> bool:
    toks = words(text)
    if len(toks) < 2:
        return False
    if any(ch in _AZ_TR_CHARS for ch in (text or "").lower()):
        return False
    if any(t in _NON_EN_WORDS for t in toks):
        return False
    hits = sum(1 for t in toks if t in _EN_FUNCTION)
    ratio = hits / len(toks)
    return ratio >= 0.20 or (len(toks) >= 6 and ratio >= 0.15 and hits >= 2)


# ── Did they actually use it? ────────────────────────────────────────────────
# The checklist must tick when the LEARNER says the word, not when the tutor
# does, and it has to survive inflection: "commuting" is "commute", "gave up"
# is "give up", "picked me up" is "pick up". Matching is local and instant —
# asking a model whether a word appeared would cost a round trip per sentence
# and still argue about "gave" versus "give".

_IRREGULAR = {
    "be": ("am", "is", "are", "was", "were", "been", "being"),
    "get": ("got", "gotten"), "go": ("went", "gone", "goes"),
    "wake": ("woke", "woken"), "eat": ("ate", "eaten"), "take": ("took", "taken"),
    "give": ("gave", "given"), "keep": ("kept",), "run": ("ran",),
    "find": ("found",), "grow": ("grew", "grown"), "bring": ("brought",),
    "catch": ("caught",), "think": ("thought",), "stand": ("stood",),
    "come": ("came",), "make": ("made",), "deal": ("dealt",),
    "stick": ("stuck",), "hang": ("hung",), "pay": ("paid",),
    "put": ("put",), "cut": ("cut",), "set": ("set",), "hold": ("held",),
}

# How far after the verb a particle may sit: "pick it up", "put the meeting off".
_PARTICLE_WINDOW = 4


def _token_is(token: str, base: str) -> bool:
    """True if `token` is any ordinary inflection of `base`."""
    if token == base or token in _IRREGULAR.get(base, ()):
        return True
    if len(base) >= 4:
        stem = base[:-1] if base.endswith("e") else base
        if token.startswith(stem) and len(token) - len(stem) <= 4:
            return True
    return False


def used_items(text: str, items: list[str]) -> list[str]:
    """Which of `items` (single words or multi-word phrases) this sentence used."""
    toks = words(text)
    if not toks:
        return []
    found = []
    for item in items:
        parts = [w for w in words(item) if w]
        if not parts:
            continue
        if len(parts) == 1:
            if any(_token_is(t, parts[0]) for t in toks):
                found.append(item)
            continue
        # A phrase: find the head word, then the rest in order close behind it
        # (the object may sit inside a separable phrasal verb).
        head, rest = parts[0], parts[1:]
        heads = [i for i, t in enumerate(toks) if _token_is(t, head)]
        for start in heads:
            at, ok = start, True
            for part in rest:
                window = toks[at + 1: at + 2 + _PARTICLE_WINDOW]
                hit = next((j for j, t in enumerate(window) if _token_is(t, part)), None)
                if hit is None:
                    ok = False
                    break
                at = at + 1 + hit
            if ok:
                found.append(item)
                break
    return found


# ── Talking to the model ─────────────────────────────────────────────────────

_client = None
_client_lock = threading.Lock()


def gemini(prompt: str, model: str = ANALYSIS_MODEL) -> str:
    global _client
    with _client_lock:
        if _client is None:
            from google import genai
            key = json.loads(API_CONFIG.read_text(encoding="utf-8"))["gemini_api_key"]
            _client = genai.Client(api_key=key)
        client = _client
    resp = client.models.generate_content(model=model, contents=prompt)
    return (getattr(resp, "text", "") or "").strip()


def parse_json(raw: str) -> dict:
    """Tolerant: models wrap JSON in fences or add a sentence before it."""
    text = (raw or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        data = json.loads(text[start:end + 1])
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


# ── Scoring rules ────────────────────────────────────────────────────────────

# You cannot demonstrate B2 in four words. A short utterance with nothing wrong
# in it is an absence of evidence, so the score it can contribute is capped by
# how much language it actually contained.
_LENGTH_CEILINGS = ((4, 40.0), (7, 55.0), (12, 70.0), (19, 85.0))


def length_ceiling(word_count: int) -> float:
    for limit, ceiling in _LENGTH_CEILINGS:
        if word_count <= limit:
            return ceiling
    return 100.0


_STRICTNESS_RULES = {
    "gentle": ("Report only mistakes a listener would notice or that change the "
               "meaning. Let small slips go."),
    "normal": ("Report real grammar and word-choice mistakes. Ignore hesitations "
               "and self-corrections."),
    "strict": ("Report every grammar, word-choice and word-order mistake, "
               "including small ones."),
}


def _skill_catalogue(skills: dict) -> str:
    return "\n".join(f"  {sid}: {name} ({band})"
                     for sid, (name, band, _hint) in skills.items())


def analysis_prompt(text: str, *, language_name: str, native_language: str,
                    level: str, unit_title: str, unit_skills: list[str],
                    skills: dict, strictness: str,
                    target_words: list | None = None,
                    target_phrasals: list | None = None) -> str:
    targets = ", ".join(unit_skills) or "none"
    lexis = ""
    if target_words or target_phrasals:
        lexis = ("\nWORDS this unit is installing: " + ", ".join(target_words or [])
                 + "\nPHRASAL VERBS: " + ", ".join(target_phrasals or []) + "\n")
    return f"""You are a {language_name} teacher analysing ONE sentence spoken aloud by
a learner. Their native language is {native_language}. Their level is about {level}.
The lesson right now is "{unit_title}", practising: {targets}.{lexis}

THE UTTERANCE (automatic speech-to-text transcript):
\"\"\"{text}\"\"\"

HOW TO READ IT:
- It is a transcript. Ignore punctuation, capitalisation, "um", repeated words
  and obvious speech-to-text errors on names.
- Judge grammar, word choice, word order and naturalness.
- {_STRICTNESS_RULES.get(strictness, _STRICTNESS_RULES['normal'])}
- Never invent a mistake. Correct language gets an empty corrections list.

SKILL IDS (use ONLY these ids in "skill" and "correct_uses"):
{_skill_catalogue(skills)}

Return ONLY a JSON object:
{{
  "is_target_language": true,
  "score": 0-100,
  "corrections": [
    {{"wrong": "exact phrase they said", "right": "corrected phrase",
      "skill": "skill id", "why": "max 10 simple words"}}
  ],
  "correct_uses": ["skill ids this sentence used CORRECTLY"],
  "corrected": "their whole sentence, fixed, keeping their own words and meaning",
  "improved": "the same meaning said one level better, using a target word or phrasal verb where it fits naturally",
  "improved_uses": ["the target words or phrasal verbs your improved version used"],
  "praise": "if the sentence was already correct: three words on what was good, otherwise empty",
  "native_words": [{{"native": "word in {native_language}", "target": "{language_name} word"}}],
  "upgrades": [{{"simple": "plain word they used", "better": "stronger word one level up"}}]
}}

RULES:
- "score": how good THIS sentence is on the CEFR scale
  (A1 under 20, A2 20-37, B1 38-55, B2 56-73, C1 74-88, C2 89+).
- "corrections": at most 3, most important first.
- "correct_uses": only structures clearly present AND correct. A sentence in
  the past with a right past verb counts for past_simple; "I like it" does not
  count for anything advanced. Pay special attention to the lesson targets.
- "native_words": {native_language} words mixed into the sentence, with the
  {language_name} word they needed. Empty if none.
- "upgrades": at most 1, empty when the wording is fine.
- "is_target_language": false if the sentence is not mainly {language_name}.
"""


def analyse(text: str, **ctx) -> dict:
    """Analyse one target-language utterance. {} when unusable."""
    skills = ctx["skills"]
    data = parse_json(gemini(analysis_prompt(text, **ctx)))
    if not data or not data.get("is_target_language", True):
        return {}
    try:
        score = float(data.get("score", 0))
    except Exception:
        score = 0.0
    score = max(0.0, min(100.0, score))
    data["raw_score"] = score
    data["score"] = min(score, length_ceiling(len(words(text))))

    corrections = []
    for c in data.get("corrections") or []:
        if not isinstance(c, dict) or not c.get("right"):
            continue
        sid = str(c.get("skill", "")).strip()
        c["skill"] = sid if sid in skills else "word_choice"
        corrections.append(c)
    data["corrections"] = corrections[:3]

    wrong_skills = {c["skill"] for c in data["corrections"]}
    data["correct_uses"] = [s for s in dict.fromkeys(data.get("correct_uses") or [])
                            if s in skills and s not in wrong_skills][:5]
    data["native_words"] = [w for w in (data.get("native_words") or [])
                            if isinstance(w, dict) and w.get("target")][:5]
    data["upgrades"] = [u for u in (data.get("upgrades") or [])
                        if isinstance(u, dict) and u.get("better")][:1]
    for key in ("corrected", "improved", "praise"):
        data[key] = str(data.get(key) or "").strip()
    data["improved_uses"] = [str(x) for x in (data.get("improved_uses") or [])][:3]
    if not data["corrected"]:
        data["corrected"] = text.strip()
    return data


# ── The correction, word by word ─────────────────────────────────────────────

def diff_tokens(said: str, corrected: str) -> tuple[list[dict], list[dict]]:
    """Two token lists for the correction card: what they said with the wrong
    parts flagged, and the fixed sentence with the repairs flagged.

    Computed locally with difflib rather than asked for: a model marking up its
    own correction drifts between quotation styles and loses words, and the
    learner reads this while the sentence is still in their head.
    """
    import difflib
    a = (said or "").split()
    b = (corrected or "").split()
    left = [{"text": w, "bad": False} for w in a]
    right = [{"text": w, "fixed": False} for w in b]
    if not a or not b:
        return left, right
    strip = " .,!?;:\u201c\u201d\"'"
    matcher = difflib.SequenceMatcher(
        a=[w.lower().strip(strip) for w in a],
        b=[w.lower().strip(strip) for w in b])
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        for i in range(i1, i2):
            left[i]["bad"] = True
        for j in range(j1, j2):
            right[j]["fixed"] = True
    return left, right


def native_help(text: str, *, language_name: str, native_language: str,
                level: str) -> dict:
    """The learner fell back to their own language. Find what they wanted to
    say, at their level, and the words they were missing."""
    prompt = f"""A {level} learner of {language_name} said this in {native_language}
(speech-to-text transcript):
\"\"\"{text}\"\"\"

Return ONLY JSON:
{{
  "is_native": true,
  "target_sentence": "the same meaning in simple {language_name} at {level} level",
  "words": [{{"native": "key {native_language} word", "target": "{language_name} word"}}]
}}
- "words": at most 4 useful content words, not function words.
- "is_native": false if the text is not {native_language} or is only noise.
"""
    data = parse_json(gemini(prompt))
    if not data or not data.get("is_native", True):
        return {}
    data["words"] = [w for w in (data.get("words") or [])
                     if isinstance(w, dict) and w.get("target")][:4]
    return data


def drill(*, language_name: str, native_language: str, level: str,
          skill_name: str, hint: str, mistakes: list[str],
          technique: str = "") -> str:
    """One spoken exercise, built as a named teaching technique.

    Without `technique` a model writes a quiz — five unrelated gap-fills. Given
    the steps of a substitution drill, a dictogloss or a 4/3/2, it writes that
    instead, which is what the unit is supposed to be practised with.
    """
    examples = ("Mistakes this learner really made:\n" + "\n".join(mistakes[:5])
                if mistakes else "No stored mistakes for this skill yet.")
    method = (f"\nRUN IT AS THIS TECHNIQUE — the prompts must fit it:\n{technique}\n"
              if technique else "")
    prompt = f"""Write a short SPOKEN {language_name} drill for a {level} learner
(native language: {native_language}) on "{skill_name}" ({hint}).
{method}
{examples}

Give exactly, as plain sentences with no markdown:
1. The rule in one simple sentence (max 15 words).
2. One example sentence.
3. Five short prompts the learner answers OUT LOUD, from easy to harder, in the
   shape the technique above calls for. Build some from the real mistakes.
4. The answers, after the prompts.
Under 150 words."""
    return gemini(prompt, model=LESSON_MODEL)
