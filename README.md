# LangVis — a speaking language course

LangVis is a voice-first language tutor for the desktop. You talk, it teaches:
it listens to every sentence you say, measures it, corrects it, remembers what
you get wrong, and runs a real course that carries you from **A2 to B2**.

It is not a chatbot and not an assistant — it does not open apps, control your
computer or search the web. It has one job: making you speak better.

- **Course:** 6 stages × 4 units = **24 units**, A2.1 → B2.2, all visible on screen
- **Languages:** **English** (active) · **Slovak** (in the select, course not written yet)
- **Voice:** real-time two-way audio through Google's Gemini Live API
- **Level:** measured from your own speech, never guessed

## What you see

```
┌ LangVis  [English ▾]        A2 · 48/100 → B2   14 today   Transcript  ⚙ ┐
├─────────────┬───────────────────────────────────────────────────────────┤
│ SYLLABUS    │  NOW TEACHING · UNIT 2 OF 24   Right now      ▓▓▓░ 41%    │
│ A2.1 …      │  present continuous · method: form contrast → substitution│
│  1 ✓ Me…    │                    ( the voice mark )                     │
│  2 ▶ Right… │                   Your turn — speak                       │
│  3 · Last…  │  YOU SAID     I am ̲c̲o̲o̲k̲ dinner and ̲d̲o̲ the laundry now     │
│ A2.2 …      │  CORRECTED    I am cooking dinner and doing the laundry.  │
│  5 · Plans  │               I am cook → I am cooking  present continuous│
│             │  TIP · PRESENT CONTINUOUS  am/is/are + verb-ing           │
│             │               • I am working right now.                   │
│             │  SAY IT BETTER  I am cooking while I tidy up the kitchen.  │
│             │               uses: tidy up                               │
│             │  WORDS TO USE  ✓cook  laundry 1/2  noisy  [tidy up] …     │
│             │  [type a sentence] [▸]  [Interrupt]  [Microphone on · F4]  │
├─────────────┴───────────────────────────────────────────────────────────┤
│ WE ARE FIXING  word order 12/100 · prepositions 14/100                   │
└─────────────────────────────────────────────────────────────────────────┘
```

- **Syllabus (left):** every stage and all 24 units in order — finished ones
  ticked, the current one marked. Click any unit for its grammar, its words and
  phrasal verbs, its model sentences, its methods and the speaking task.
- **The coaching (centre)** is the biggest thing on screen, because it is the
  lesson: your sentence with the wrong parts in **red**, the **corrected**
  version with the repairs in green and the reason beside them, the **tip** —
  the rule behind that mistake with two examples — and **say it better**: the
  same meaning one level up, using a word the unit is installing.
- **Words to use:** the unit's vocabulary and phrasal verbs, ticked off when
  *you* use them twice in your own sentences (hearing them does not count).
- **The voice mark:** a drawn speech bubble with a microphone and sound waves
  that open out with your voice — green while it listens, terracotta while the
  tutor speaks, slashed when the mic is off.
- **Transcript (right):** closed by default. Open it from the header when you
  want to read back what was said.

## How a lesson works

Every session runs in layers, from the plan the tutor builds before it says
hello:

1. **Warm-up** — a greeting and one easy question.
2. **Review** — the skills you keep getting wrong, drilled with prompts built
   from *your own* mistakes.
3. **Current unit** — the target grammar in one or two simple sentences, then
   guided questions that force you to use it, then the speaking task.
4. **Conversation** — free talk on the unit's theme, with corrections.
5. **Wrap-up** — one thing you did well, one to practise, the new words.

## How it teaches (not just what)

Every unit names the techniques it is practised with, and the tutor is handed
the steps of each one with the lesson — so a unit is a method, not a topic:

| Technique | What it is for |
|---|---|
| **Present, practise, produce** | meet a new form and get it into your own mouth |
| **Substitution / transformation drills** | make a form automatic; switch between two forms |
| **Form contrast** | stop two forms blurring into one ("I work" / "I am working") |
| **Dictogloss** | hear the grammar in real speech, then rebuild the text aloud |
| **Retelling** | turn what you heard into what you can say |
| **4/3/2 fluency** | tell the same story in 2 min, 90 s, 60 s — speed, no interruptions |
| **Information gap** | you have to ask questions to find out; you do the talking |
| **Role play** | use the language where you will actually need it |
| **Pushed output** | produce the target form five times before the topic moves on |
| **Chunk push** | three collocations, then all three used within two minutes |
| **Shadowing** | copy the tutor's rhythm, not just the words |
| **Backchaining** | build a long sentence from the end backwards |
| **Native-language contrast** | kill the mistakes that come from Azerbaijani word order |
| **Clarification request** | you notice and repair your own mistake — the strongest correction |
| **Recast and repeat** | the fix that does not break the conversation |
| **Personalisation** | every example rebuilt with your own life, because that is what sticks |
| **Spaced review** | every lesson opens on what is about to be forgotten |
| **Can-do check** | the unit is finished when you can perform it unaided, once |

Each stage also has an emphasis: accuracy at A2, fluency and complexity at B1,
precision and naturalness at B2 — forms first, speed second, polish last.

**Two jobs on every sentence you say.** First: is it right? If not, you get the
correction before anything else. Second: how could it be better? Even a correct
sentence gets one upgrade — a stronger word, a natural phrasal verb, two clauses
instead of one. You can talk about whatever you like; the tutor feeds the unit's
grammar, words and phrasal verbs into your own topic rather than dragging you
onto its own.

**Corrections come first.** If your sentence has a mistake, the tutor says the
right version, has you repeat it, and *then* answers what you actually said. If
your sentence is correct it answers straight away, with no comment — that
silence is the reward. You can switch this off in ⚙ → Tutor settings.

## What it tracks

Everything you say in the target language is analysed in the background (a
small, cheap model per sentence — the live conversation is never blocked):

| Tracked | Meaning |
|---|---|
| **Level** | a rolling CEFR score over your last sentences, weighted against the level you stated until enough is measured |
| **Skills** | ~40 curriculum skills (past simple, articles, prepositions, conditionals…), each with mastery, your real mistakes and a review date |
| **Focus** | the three weakest skills at or below your stage — what the tutor attacks next |
| **Course** | a unit passes when you have spoken enough in it, its target skills are strong *and* you have used five of its words and two of its phrasal verbs; a stage passes when your level reaches the stage goal |
| **Words and phrasal verbs** | 192 words and 72 phrasal verbs across the course, 8 + 3 per unit; each ticks off after two uses of your own |
| **Words you were missing** | anything you had to say in your own language, kept until you use the target-language word yourself |
| **Fallbacks** | how often you switched to your own language — the honest fluency number |

When the same mistake happens three times, the tutor is told mid-lesson and
runs a two-minute drill on it. When a unit or stage is finished it congratulates
you and starts the next one, without restarting the session.

Two files per language, in `english/`:

- `progress.md` — the human one: level, unit, focus skills, mistakes, day by day
- `level.json` — the raw numbers (source of truth; the markdown is regenerated)

Both are local and git-ignored. They are your speech.

## Install

```bash
python setup.py
python main.py
```

Paste a free [Gemini API key](https://aistudio.google.com/apikey) into the setup
screen. Then open ⚙ → **Tutor settings** and set your level, your own language,
the pace and how strictly to correct.

Optional: ⚙ → **Wake word** downloads a small local model so the mic is only
streamed after you say the wake phrase.

## Project structure

```
main.py                    the Gemini Live session: audio in/out, tools, reconnects
ui.py                      the interface — syllabus, voice mark, conversation, settings
core/prompt.txt            the tutor's core protocol (identity, how to correct)
core/plugin_loader.py      plugin discovery: tools, observers, prompt blocks
core/wake_word.py          optional offline wake-word detection
core/audio_devices.py      microphone / speaker selection
tutor/curriculum.py        skills, stages, units, model sentences — what is taught
tutor/progress.py          the learner's state: level, skills, course, vocabulary
tutor/analysis.py          per-sentence analysis and drill generation
plugins/language_tutor.py  the tutor itself: observe → measure → teach
memory/                    what LangVis remembers about you, and your settings
```

## Extending it

The plugin contract is how the tutor plugs in: a file in `plugins/` with a
`PLUGIN` dict and `run()` becomes a tool the tutor can call; add
`observe(text, player)` to see every sentence, `format_for_prompt()` for
standing instructions in every session, `PLUGIN_SETTINGS` for a settings form,
`status_for_ui()` / `syllabus_for_ui()` to appear in the interface, and
`set_language(name)` to answer the language select.

Adding **Slovak** means writing its skills, stages and model sentences in
`tutor/curriculum.py`, a word-level detector for it in `tutor/analysis.py`, and
flipping `LANGUAGES["slovak"]["enabled"]` to `True`. The select already lists
it; nothing in the interface needs to change.
