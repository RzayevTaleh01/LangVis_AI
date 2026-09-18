# LangVis

**A speaking language course for the desktop.**
You talk, LangVis listens, corrects every sentence, remembers your mistakes
and takes you from **A2 to B2**.

> LangVis is not a chatbot or an assistant. It does not open apps, control
> your computer or search the web. It has one job: to make you speak better.

| | |
|---|---|
| **Languages** | English (active) · Slovak (planned) |
| **Course** | 6 stages × 4 units = 24 grammar units, A2.1 → B2.2 |
| **Voice** | real-time two-way audio through the Gemini Live API |
| **Level** | measured from your own speech, never guessed |
| **Platform** | Python + PyQt6 · Windows, macOS, Linux |

---

## Contents

- [Quick start](#quick-start)
- [The screen](#the-screen)
- [A lesson](#a-lesson)
- [The course](#the-course)
- [Teaching methods](#teaching-methods)
- [What it tracks](#what-it-tracks)
- [Project structure](#project-structure)
- [Extending LangVis](#extending-langvis)
- [Privacy](#privacy)

---

## Quick start

```bash
python setup.py   # installs the dependencies
python main.py    # starts LangVis
```

1. Paste a free [Gemini API key](https://aistudio.google.com/apikey) into the
   setup screen.
2. Open **⚙ → Tutor settings** and set your level, your own language, the pace
   and how strictly to correct.
3. Start talking. The lesson begins by itself.

**Optional:** **⚙ → Wake word** downloads a small local model, so the
microphone is only streamed after you say the wake phrase.

---

## The screen

```
┌ LangVis  [English ▾]        A2 · 48/100 → B2   14 today   Transcript  ⚙ ┐
├─────────────┬───────────────────────────────────────────────────────────┤
│ SYLLABUS    │  NOW TEACHING · UNIT 2 OF 24   Right now      ▓▓▓░ 41%    │
│ A2.1 …      │  present continuous · method: form contrast → substitution│
│  1 ✓ Me…    │                    ( the voice mark )                     │
│  2 ▶ Right… │                   Your turn — speak                       │
│  3 · Last…  │  YOU SAID     I am cook dinner and do the laundry now     │
│ A2.2 …      │  CORRECTED    I am cooking dinner and doing the laundry.  │
│  5 · Plans  │  TIP          am/is/are + verb-ing                        │
│             │  SAY IT BETTER  I am cooking while I tidy up the kitchen. │
│             │  WORDS TO USE  ✓cook  laundry 1/2  noisy  [tidy up] …     │
│             │  [type a sentence] [▸]  [Interrupt]  [Microphone on · F4] │
├─────────────┴───────────────────────────────────────────────────────────┤
│ WE ARE FIXING  word order 12/100 · prepositions 14/100                  │
└─────────────────────────────────────────────────────────────────────────┘
```

| Area | What it shows |
|---|---|
| **Syllabus** (left) | All stages and units in order. Click a unit to see its forms, rules, examples and methods. |
| **Coaching** (centre) | Your sentence as you say it, then the marked version: mistakes in red, the correction in green with the reason, a short **tip** and a **say it better** upgrade. |
| **Dictionary** (right) | Words and phrasal verbs taken from *your* topic, one step above your level. A word is learned after you use it twice yourself. |
| **Tutor face** | Drawn at runtime. The mouth follows the real audio level; the rim colour shows the state — green listening, terracotta speaking, mustard thinking, rose mic off. |
| **Transcript** | Closed by default. Open it from the header to read the conversation back. |

---

## A lesson

Every session follows the same five steps:

1. **Warm-up** — a greeting and one easy question.
2. **Review** — drills built from your own recent mistakes.
3. **Current unit** — the target grammar, guided questions, then a speaking task.
4. **Conversation** — free talk on the unit's theme, with corrections.
5. **Wrap-up** — one thing you did well, one thing to practise, the new words.

**Every sentence gets two checks:**

- **Is it right?** If not, the tutor gives the correct version, asks you to
  repeat it, and only then answers you.
- **Can it be better?** Even a correct sentence gets one upgrade — a stronger
  word, a phrasal verb, a longer structure.

A correct sentence gets no comment — the tutor just answers. You can turn
correction-first off in **⚙ → Tutor settings**.

When the same mistake happens three times, the tutor runs a short drill on it.
When a unit or stage is finished, the next one starts without restarting the
session.

---

## The course

| Stage | Title | Units |
|---|---|---|
| **A2.1** | Everyday forms | Present simple & questions · Present continuous · Past simple · Articles, prepositions & word order |
| **A2.2** | Talking beyond now | Future: going to & will · Comparatives & quantity · Modals: can, must, should · Linking a story together |
| **B1.1** | Perfect and past | Present perfect · Past continuous & used to · Perfect vs past simple · First conditional & possibility |
| **B1.2** | Longer sentences | Second conditional · Verb patterns: -ing or to · Relative clauses & word forms · Passive voice |
| **B2.1** | Precision in the past | Past perfect · Third conditional & wishes · Reported speech · Modals of deduction |
| **B2.2** | Range and control | Advanced passive · Future continuous & perfect · Discourse markers · Collocation & natural choice |

Focus by level: **accuracy** at A2, **fluency** at B1, **precision** at B2.

A unit is passed when you have spoken enough in it and its target forms are
strong. A stage is passed when your measured level reaches the stage goal.

---

## Teaching methods

Each unit names the methods it is practised with, and the tutor receives the
steps of each method with the lesson.

| Method | Purpose |
|---|---|
| Present, practise, produce | learn a new form and start using it |
| Substitution / transformation drills | make a form automatic |
| Form contrast | stop two forms mixing ("I work" / "I am working") |
| Dictogloss | hear grammar in real speech, then rebuild the text |
| Retelling | turn what you heard into what you can say |
| 4/3/2 fluency | tell one story in 2 min, 90 s, 60 s |
| Information gap | you must ask questions to find out |
| Role play | practise real situations |
| Pushed output | use the target form five times before moving on |
| Chunk push | learn three collocations and use them within two minutes |
| Shadowing | copy the tutor's rhythm |
| Backchaining | build a long sentence from the end |
| Native-language contrast | fix mistakes that come from your own language |
| Clarification request | notice and repair your own mistake |
| Recast and repeat | correct without stopping the conversation |
| Personalisation | examples rebuilt from your own life |
| Spaced review | revisit what you are about to forget |
| Can-do check | finish a unit by doing the task alone, once |

---

## What it tracks

Every sentence is analysed in the background by a small, fast model, so the
live conversation never waits.

| Tracked | Meaning |
|---|---|
| **Level** | rolling CEFR score over your recent sentences |
| **Skills** | ~40 grammar skills, each with mastery, real mistakes and a review date |
| **Focus** | the three weakest skills at your stage — what the tutor works on next |
| **Course** | current unit and stage, and how close each is to passing |
| **Dictionary** | offered words and how often you used them |
| **Missing words** | things you said in your own language, kept until you say them in the target language |
| **Fallbacks** | how often you switched to your own language |

Progress is saved per language, for example in `english/`:

- `level.json` — the raw numbers (source of truth)
- `progress.md` — a readable summary, regenerated from `level.json`

---

## Project structure

```
main.py                     Gemini Live session: audio in/out, tools, reconnects
ui.py                       interface: syllabus, tutor face, coaching, settings
setup.py                    installs dependencies
requirements.txt

core/
  prompt.txt                the tutor's core instructions
  plugin_loader.py          finds plugins: tools, observers, prompt blocks
  audio_devices.py          microphone and speaker selection
  wake_word.py              optional offline wake word
  selflog.py                keeps a log of LangVis's own output and errors

tutor/
  curriculum.py             skills, rules, stages, units, methods
  progress.py               learner state: level, skills, course, vocabulary
  analysis.py               per-sentence analysis and drill generation

plugins/
  language_tutor.py         the tutor: observe → measure → teach
  _template.py              starting point for a new plugin

memory/                     settings and what LangVis remembers about you
config/                     app icon and local API key
```

---

## Extending LangVis

### Plugins

Any file in `plugins/` with a `PLUGIN` dict and a `run()` function becomes a
tool the tutor can call. Start from `plugins/_template.py`. Optional hooks:

| Hook | Use |
|---|---|
| `observe(text, player)` | see every sentence |
| `format_for_prompt()` | add standing instructions to every session |
| `PLUGIN_SETTINGS` | show a settings form |
| `status_for_ui()` / `syllabus_for_ui()` | appear in the interface |
| `set_language(name)` | react to the language select |

### Adding a language (e.g. Slovak)

1. Write its skills, stages and model sentences in `tutor/curriculum.py`.
2. Add a word-level detector for it in `tutor/analysis.py`.
3. Set `LANGUAGES["slovak"]["enabled"] = True`.

The interface already lists Slovak — nothing else needs to change.

---

## Privacy

Your API key, settings, memory and all progress files (`english/`, `slovak/`)
stay on your computer and are git-ignored. Audio is sent only to the Gemini
API during a session.

No images are shipped: the tutor's face, icons and progress bars are drawn at
runtime, so the interface stays sharp at any screen scale.

---

## Author

**Taleh Rzayev** — design, code and curriculum.
