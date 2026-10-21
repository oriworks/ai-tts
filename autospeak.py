# SPDX-License-Identifier: GPL-3.0-or-later
"""Stop hook: speak Claude's last response when auto voice mode is on.

Reads the hook JSON on stdin, takes the final text of the turn from the transcript,
strips markdown/code/tables/links and hands it to `speak` in the background.
"""

import json
import os
import re
import signal
import subprocess
import sys
import time

from speak import AUTO_FLAG, PID_FILE, language, load_config

SPEAK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "speak.py")
MAX_CHARS = 6000  # safety cap (~6 min of speech)

PUNCTUATION = {"→": ", ", "—": ", ", "–": ", "}
SYMBOLS = {  # spoken form of symbols, by voice language
    "pt": {"≈": " cerca de ", "~": " cerca de ", "%": " por cento", "&": " e ", "×": " vezes ", "+": " mais "},
    "en": {"≈": " about ", "~": " about ", "%": " percent", "&": " and ", "×": " times ", "+": " plus "},
}


def is_prompt(entry):
    """A real user message (not a tool result)."""
    content = entry.get("message", {}).get("content")
    if isinstance(content, str):
        return True
    return any(b.get("type") == "text" for b in content or [])


def says_something(command):
    """A `speak` call that reads text aloud, not one that only changes settings (--auto, --stop...)."""
    command = command.lstrip()
    if not command.startswith("speak"):
        return False
    return not re.match(r"speak\s+--(auto|stop|start|rate|list|use|download|help)\b", command)


def last_turn(transcript):
    """Return (final text of the last turn, whether the turn already called `speak`)."""
    entries = []
    with open(transcript) as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("type") in ("user", "assistant") and not d.get("isSidechain"):
                entries.append(d)
    texts, final_done, spoke = [], False, False
    for d in reversed(entries):
        if d["type"] == "user":
            if is_prompt(d):
                break
            final_done = True  # a tool result: everything before it is not the final answer
            continue
        for b in reversed(d["message"].get("content") or []):
            if b.get("type") == "tool_use":
                final_done = True
                if b.get("name") == "Bash" and says_something(b.get("input", {}).get("command", "")):
                    spoke = True
            elif b.get("type") == "text" and not final_done:
                texts.append(b["text"])
    return "\n\n".join(reversed(texts)), spoke


def inline_code(m):
    code = m.group(1)
    if " " in code or len(code) > 40:
        return ""
    return os.path.basename(code.rstrip("/")).lstrip("-~.")


def speakable(md, lang):
    t = re.sub(r"```.*?```", " ", md, flags=re.S)
    lines = []
    for line in t.splitlines():
        s = line.strip()
        if s.startswith("|") or re.fullmatch(r"[-=*_ ]{3,}", s):
            continue  # tables and rules
        s = re.sub(r"^(#{1,6}|>|[-*+]|\d+[.)])\s+", "", s)
        if s and not re.search(r"[.!?:;…]$", s):
            s += "."
        lines.append(s)
    t = " ".join(lines)
    t = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"`([^`]*)`", inline_code, t)
    t = re.sub(r"(\*\*|__|\*|_)(\S.*?\S|\S)\1", r"\2", t)
    t = re.sub(r"\S*/\S+", lambda m: os.path.basename(m.group(0).rstrip("/.,")), t)  # leftover paths
    for sym, word in (PUNCTUATION | SYMBOLS.get(lang, {})).items():
        t = t.replace(sym, word)
    t = re.sub(r"[^\w\s.,!?:;'\"()…-]", " ", t)  # emojis and other symbols
    t = re.sub(r"\(\s*\)", "", t)
    t = re.sub(r"\s+([.,!?:;])", r"\1", t)
    t = re.sub(r"([.,!?:;])[.,:;]+", r"\1", t)
    t = re.sub(r"\s+", " ", t).strip(" .,:;")
    if len(t) > MAX_CHARS:
        cut = max(t.rfind(p, 0, MAX_CHARS) for p in ".!?")
        t = t[: cut + 1] if cut > 0 else t[:MAX_CHARS]
    return t


def stop_previous():
    try:
        os.kill(int(open(PID_FILE).read()), signal.SIGTERM)
    except (OSError, ValueError):
        pass


def main():
    hook = json.load(sys.stdin)
    if not os.path.exists(AUTO_FLAG) or hook.get("stop_hook_active"):
        return
    text, spoke = "", False
    for _ in range(5):  # the final message can land in the transcript just after the hook fires
        text, spoke = last_turn(hook["transcript_path"])
        if text or spoke:
            break
        time.sleep(0.2)
    voice = load_config()["voice"]
    if not voice:
        return
    lang = language(voice).split("_")[0]
    text = speakable(hook.get("last_assistant_message") or text, lang) if not spoke else ""
    if not text:
        return
    stop_previous()
    proc = subprocess.Popen([sys.executable, SPEAK], stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True, text=True)
    proc.stdin.write(text)
    proc.stdin.close()


if __name__ == "__main__":
    main()
