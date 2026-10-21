---
name: speech
description: Read the agent's last response aloud with the local Piper voice (`speak` command), and turn automatic voice mode on or off. Use when the user types /speech, asks the agent to say, speak or read its answer out loud ("fala", "lê em voz alta", "diz isso", "read it aloud"), or to enable/disable/stop the voice ("desativa a voz", "liga a voz", "cala-te", "para de falar", "stop talking"), to change the voice or its pace, or to fix how a word is pronounced.
---

# speech

Speech goes through the local `speak` command (Piper TTS, runs offline). Settings live in `~/.config/speak/config.toml`.

## Automatic voice mode

If the agent has an end-of-turn hook that pipes its reply to `speak` (the installer sets this up for Claude Code), every response is spoken while the mode is on.

- Turn it off ("desativa a voz", "/speech off"): `speak --auto off` and `speak --stop`.
- Turn it on ("liga a voz", "/speech on"): `speak --auto on`.
- Stop the current speech only ("cala-te", "para"): `speak --stop`.
- Check: `speak --auto status`.
- Speech pace ("fala mais devagar/depressa"): `speak --rate X` saves Piper's length_scale (default 1.15; higher is slower, the effect is about 40% of the number, e.g. 1.5 is about 20% slower than 1.0). Then speak a short sample.
- Change voice or language: `speak --list [LANG]` shows the catalogue with each voice's MODEL_CARD link; `speak --use NAME` downloads it and makes it the default. Choosing a voice and checking its licence is the user's decision: show the options and the MODEL_CARD link, never pick or download one on your own. Then speak a short sample.
- If `speak` says no voice is configured, tell the user and offer the same steps.

## Pronunciations

Terms are respelled from `~/.config/speak/pronunciations.txt` (`term = how to say it`, a respelling in the voice's language or IPA in `[[ ]]`) before synthesis. When the user says a word sounds wrong or how to say it ("diz X como Y", "X está mal pronunciado"), add or fix the line there and confirm by speaking a short sentence with the word (`speak "..."`). Changes apply immediately.

Reply in one short line after toggling. For anything else, read the last response aloud as below.

## Read the last response aloud

Speak the previous response (or the text given as arguments: $ARGUMENTS) through `speak`.

### 1. Rewrite it as speakable text

Write the script you would say out loud, in the language of the configured voice (`voice` in the config, e.g. `pt_PT-...` is European Portuguese):

- Drop code blocks, tables, diagrams, ASCII art, URLs, long file paths, command lines, emojis and all markdown syntax.
- Describe instead of reading: "criei um script que toca o áudio" rather than reading code; summarise a table or long list in one or two sentences.
- Write units, symbols and abbreviations the way they are spoken ("três gigabytes", "por exemplo"); plain numbers are read correctly.
- Plain sentences ending in punctuation; no brackets, no `<`, `>` or `[...]` (they are read as markup or spoken literally).
- Keep it short: roughly 60 to 150 words.

### 2. Speak it

Run it in the background so the conversation is not blocked (use your shell tool's background option, or append `&`):

```bash
speak <<'TXT'
...the speakable text...
TXT
```

### 3. Reply

Answer in one short line (e.g. "A falar…"). Do not repeat the spoken text in the chat.
