# SPDX-License-Identifier: GPL-3.0-or-later
"""Speak text with Piper and play it through sounddevice.

Text is split into chunks; the next chunk is synthesised while the current one plays.
Synthesis goes through a per-voice daemon that keeps the Piper model loaded and
exits after --idle seconds without requests.
"""

import argparse
import json
import os
import queue
import re
import signal
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
import urllib.parse
import urllib.request
import wave

ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.expanduser("~/.config/speak")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.toml")
VOICES_DIR = os.path.expanduser("~/.local/share/speak/voices")
VOICES_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
RUN_DIR = os.path.expanduser("~/.cache/speak")
AUTO_FLAG = os.path.join(RUN_DIR, "auto")  # present: autospeak.py speaks every response
PID_FILE = os.path.join(RUN_DIR, "player.pid")
DEFAULTS = {
    "voice": "",  # no default: the user picks and downloads a voice (speak --list, speak --use NAME)
    "rate": 1.15,  # Piper length_scale: > 1 is slower
    "pronunciations": os.path.join(CONFIG_DIR, "pronunciations.txt"),
}
DEFAULT_RATE = DEFAULTS["rate"]
PAUSES = {",": 0.15, ":": 0.3, ";": 0.3, ".": 0.45, "!": 0.5, "?": 0.5}  # seconds of silence after each mark


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_FILE, "rb") as f:
            cfg.update(tomllib.load(f))
    except FileNotFoundError:
        pass
    return cfg


def save_setting(key, value):
    """Set one top-level `key = value` line in config.toml, keeping the rest of the file."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    try:
        text = open(CONFIG_FILE, encoding="utf-8").read()
    except FileNotFoundError:
        text = ""
    line = f"{key} = {json.dumps(value, ensure_ascii=False)}"
    text, n = re.subn(rf"(?m)^(# ?)?{key}\s*=.*$", lambda m: line, text, count=1)  # also fills a commented-out example
    if not n:
        text = text.rstrip("\n") + ("\n" if text else "") + line + "\n"
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write(text)


def language(voice):
    """pt_PT-tugão-medium -> pt_PT"""
    return voice.split("-", 1)[0]


def download(voice):
    """Fetch a voice from the rhasspy/piper-voices repository into VOICES_DIR."""
    try:
        locale, name, quality = voice.split("-")
    except ValueError:
        sys.exit(f"speak: voice names look like pt_PT-tugão-medium, got {voice!r}")
    os.makedirs(VOICES_DIR, exist_ok=True)
    for ext in (".onnx", ".onnx.json"):
        url = "/".join([VOICES_URL, locale.split("_")[0], locale, name, quality, voice + ext])
        dest = os.path.join(VOICES_DIR, voice + ext)
        if os.path.exists(dest):
            continue
        print(f"speak: downloading {voice}{ext}", file=sys.stderr)
        try:
            urllib.request.urlretrieve(urllib.parse.quote(url, safe=":/"), dest + ".part")
        except OSError as e:
            sys.exit(f"speak: could not download {url}: {e}")
        os.replace(dest + ".part", dest)
    return os.path.join(VOICES_DIR, voice + ".onnx")


def list_voices(lang):
    """Print the voices in the rhasspy/piper-voices catalogue, optionally only those whose code starts with lang."""
    try:
        with urllib.request.urlopen(f"{VOICES_URL}/voices.json") as r:
            catalogue = json.load(r)
    except OSError as e:
        sys.exit(f"speak: could not fetch the voice list: {e}")
    installed = {f[:-5] for f in os.listdir(VOICES_DIR) if f.endswith(".onnx")} if os.path.isdir(VOICES_DIR) else set()
    for name, info in sorted(catalogue.items()):
        if name.lower().startswith(lang.lower()):
            locale, voice, quality = name.split("-")
            card = "/".join(["https://huggingface.co/rhasspy/piper-voices/blob/main", locale.split("_")[0], locale, voice, quality, "MODEL_CARD"])
            print(f"{'*' if name in installed else ' '} {name:40} {info['language']['name_english']} ({info['language']['country_english']})  {urllib.parse.quote(card, safe=':/')}")


def pronounce(text, voice):
    """Replace terms listed in the pronunciation file (whole words, case-insensitive, longest first).

    Uses the file named in config.toml, or pronunciations/<language>.txt from this repository.
    """
    lines = []
    for path in (os.path.expanduser(load_config()["pronunciations"]),
                 os.path.join(ROOT, "pronunciations", f"{language(voice)}.txt")):
        try:
            lines = open(path, encoding="utf-8").read().splitlines()
            break
        except FileNotFoundError:
            continue
    table = {}
    for line in lines:
        term, sep, spoken = line.partition("=")
        if sep and not line.lstrip().startswith("#") and term.strip():
            table[term.strip().lower()] = spoken.strip()
    if not table:
        return text
    pattern = "|".join(re.escape(t) for t in sorted(table, key=len, reverse=True))
    return re.sub(rf"(?<![\w-])({pattern})(?![\w-])", lambda m: table[m.group(1).lower()], text, flags=re.I)


def split_chunks(text, max_chars):
    sentences = re.split(r"(?<=[.!?…])\s+", " ".join(text.split()))
    chunks, cur = [], ""
    for s in sentences:
        if cur and len(cur) + len(s) + 1 > max_chars:
            chunks.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        chunks.append(cur)
    return chunks


def socket_path(voice):
    path = os.path.join(RUN_DIR, f"{voice}.sock")
    if len(os.fsencode(path)) > 100:  # AF_UNIX paths are limited to ~108 bytes
        path = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir(), f"speak-{os.getuid()}-{voice}.sock")
    return path


def get_rate():
    try:
        return float(load_config()["rate"])
    except (tomllib.TOMLDecodeError, TypeError, ValueError):
        return DEFAULT_RATE


def request(voice, text, output, rate=DEFAULT_RATE):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.connect(socket_path(voice))
        sock.sendall((json.dumps({"text": text, "output": output, "rate": rate}) + "\n").encode())
        reply = json.loads(sock.makefile().readline() or '{"error": "daemon closed the connection"}')
    if "error" in reply:
        raise RuntimeError(reply["error"])
    return reply


def daemon_alive(voice):
    try:
        request(voice, "", os.devnull)
    except (FileNotFoundError, ConnectionRefusedError):
        return False
    except RuntimeError:
        pass  # empty text is rejected, but the daemon answered
    return True


def voice_model(voice):
    path = os.path.join(VOICES_DIR, f"{voice}.onnx")
    if not os.path.exists(path):
        sys.exit(f"speak: voice {voice} is not installed, run: speak --download {voice}")
    return path


def ensure_daemon(args):
    if daemon_alive(args.voice):
        return
    if not args.voice:
        sys.exit("speak: no voice configured. List voices with `speak --list [LANG]`, "
                 "check the licence in its MODEL_CARD, then run `speak --use NAME`")
    voice_model(args.voice)
    os.makedirs(RUN_DIR, exist_ok=True)
    with open(os.path.join(RUN_DIR, f"{args.voice}.log"), "ab") as log:
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "--daemon", "--voice", args.voice,
                          "--idle", str(args.idle)],
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    for _ in range(80):
        time.sleep(0.25)
        if daemon_alive(args.voice):
            return
    sys.exit(f"speak: daemon did not start, see {RUN_DIR}/{args.voice}.log")


def synth_with_pauses(voice, text, config):
    """Synthesise clause by clause, adding silence after punctuation. Returns int16 PCM bytes."""
    import numpy as np

    text = re.sub(r"\s*\(\s*", ", ", text)
    text = re.sub(r"\s*\)", ",", text).replace("…", ".")
    text = re.sub(r",\s*([,.!?;:])", r"\1", text)
    rate = voice.config.sample_rate
    pieces = []
    for sentence in voice.phonemize(text):  # phonemised whole, so intonation keeps its context
        clause = []
        for i, ph in enumerate(sentence):
            clause.append(ph)
            if ph in PAUSES or i == len(sentence) - 1:
                while clause and not clause[0].strip():
                    clause.pop(0)
                if any(p.strip() and p not in PAUSES for p in clause):
                    pieces.append(voice.phoneme_ids_to_audio(voice.phonemes_to_ids(clause), config))
                pieces.append(np.zeros(int(PAUSES.get(ph, PAUSES["."]) * rate), np.float32))
                clause = []
    audio = np.concatenate(pieces) if pieces else np.zeros(1, np.float32)
    peak = np.max(np.abs(audio))
    if peak > 1e-8:
        audio = audio / peak
    return (np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes()


def run_daemon(args):
    from piper import PiperVoice, SynthesisConfig

    voice = PiperVoice.load(voice_model(args.voice))
    lock = threading.Lock()
    last_used = [time.monotonic()]

    def synth(text, output, rate):
        with lock:
            last_used[0] = time.monotonic()
            try:
                pcm = synth_with_pauses(voice, text, SynthesisConfig(length_scale=rate))
                with wave.open(output, "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(voice.config.sample_rate)
                    w.writeframes(pcm)
            except Exception as e:
                return {"error": str(e)}
            return {"output": output}

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            req = json.loads(self.rfile.readline())
            reply = synth(req["text"], req["output"], req.get("rate", DEFAULT_RATE)) if req["text"].strip() else {"error": "no text"}
            self.wfile.write((json.dumps(reply) + "\n").encode())

    path = socket_path(args.voice)
    if os.path.exists(path):
        os.unlink(path)
    server = socketserver.ThreadingUnixStreamServer(path, Handler)

    def watchdog():
        while time.monotonic() - last_used[0] < args.idle:
            time.sleep(5)
        server.shutdown()

    threading.Thread(target=watchdog, daemon=True).start()
    try:
        server.serve_forever()
    finally:
        os.unlink(path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("text", nargs="*", help="text to speak (default: stdin)")
    p.add_argument("--voice", default=load_config()["voice"], help=f"Piper voice in {VOICES_DIR} (default from {CONFIG_FILE})")
    p.add_argument("--chunk-chars", type=int, default=200)
    p.add_argument("--out", help="also save the full audio to this WAV file")
    p.add_argument("--idle", type=int, default=1800, help="daemon exits after this many idle seconds")
    p.add_argument("--start", action="store_true", help="only start the daemon (if needed) and exit")
    p.add_argument("--auto", choices=["on", "off", "status"], help="speak every response automatically")
    p.add_argument("--stop", action="store_true", help="stop the speech that is playing")
    p.add_argument("--rate", type=float, help=f"save the speech pace (Piper length_scale, > 1 is slower, default {DEFAULT_RATE})")
    p.add_argument("--list", nargs="?", const="", metavar="LANG", help="list Piper voices (e.g. pt, en_GB); * marks installed ones")
    p.add_argument("--use", metavar="VOICE", help="download a voice if needed and make it the default")
    p.add_argument("--download", metavar="VOICE", help="download a Piper voice, e.g. en_US-lessac-medium")
    p.add_argument("--daemon", action="store_true", help=argparse.SUPPRESS)
    args = p.parse_args()
    if args.list is not None:
        return list_voices(args.list)
    if args.download:
        return print(download(args.download))
    if args.use:
        download(args.use)
        save_setting("voice", args.use)
        return print("voice:", args.use)
    if args.daemon:
        return run_daemon(args)
    if args.start:
        return ensure_daemon(args) if args.voice else None
    if args.auto:
        os.makedirs(RUN_DIR, exist_ok=True)
        if args.auto == "on":
            open(AUTO_FLAG, "w").close()
        elif args.auto == "off" and os.path.exists(AUTO_FLAG):
            os.unlink(AUTO_FLAG)
        return print("auto voice:", "on" if os.path.exists(AUTO_FLAG) else "off")
    if args.rate:
        save_setting("rate", args.rate)
        if not args.text:
            return print("rate:", args.rate)
    if args.stop:
        try:
            os.kill(int(open(PID_FILE).read()), signal.SIGTERM)
        except (OSError, ValueError):
            pass
        return

    text = " ".join(args.text) if args.text else sys.stdin.read()
    if not text.strip():
        sys.exit("speak: no text")
    ensure_daemon(args)
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    import soundfile as sf
    try:
        import sounddevice as sd
    except OSError:
        sd = None  # PortAudio missing: only write the WAV
    out = args.out or (None if sd else os.path.join(RUN_DIR, "last.wav"))

    with tempfile.TemporaryDirectory(prefix="speak-") as tmp:
        ready = queue.Queue(maxsize=2)

        def producer():
            try:
                for i, chunk in enumerate(split_chunks(pronounce(text, args.voice), args.chunk_chars)):
                    path = os.path.join(tmp, f"{i:03d}.wav")
                    request(args.voice, chunk, path, get_rate())
                    ready.put(path)
            except Exception as e:
                ready.put(e)
            ready.put(None)

        threading.Thread(target=producer, daemon=True).start()

        parts, rate = [], None
        while (path := ready.get()) is not None:
            if isinstance(path, Exception):
                sys.exit(f"speak: {path}")
            audio, rate = sf.read(path, dtype="float32")
            parts.append(audio)
            if sd:
                sd.play(audio, rate)
                sd.wait()

    if out:
        import numpy as np
        sf.write(out, np.concatenate(parts), rate)
        print(out)


if __name__ == "__main__":
    main()
