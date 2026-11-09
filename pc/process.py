#!/usr/bin/env python3
"""Convierte una canción en karaoke: quita la voz (Demucs), transcribe la letra con tiempos (Whisper)
y genera un VIDEO (karaoke.mp4) con la letra incrustada, reproducible en TV, celular, Chromecast o AirPlay.

Uso: process.py <carpeta> [idioma|auto] [titulo]
Entrada : <carpeta>/original.<ext>
Salida  : <carpeta>/instrumental.mp3, vocals.mp3, lyrics.json, karaoke.mp4
Imprime líneas "STAGE <nombre>" para que el servidor muestre el progreso.
"""
import json, os, shutil, subprocess, sys
from pathlib import Path


def stage(name):
    print("STAGE " + name, flush=True)


def build_lyrics(segments):
    """Convierte segmentos de faster-whisper en [{start,end,text,words:[{w,start,end}]}]."""
    out = []
    for seg in segments:
        text = (seg.text or "").strip()
        if not text:
            continue
        words = [
            {"w": w.word.strip(), "start": round(w.start, 2), "end": round(w.end, 2)}
            for w in (seg.words or []) if w.word.strip()
        ]
        out.append({"start": round(seg.start, 2), "end": round(seg.end, 2), "text": text, "words": words})
    return out


# ---------- Video con letra (ASS karaoke) ----------
def ass_time(t):
    t = max(0.0, t)
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def esc(s):
    return str(s).replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def line_text(seg, t0):
    """Texto con tags \\kf: cada palabra se rellena de blanco a rosa en el momento en que se canta."""
    words = seg.get("words") or []
    if not words:
        return "{\\kf%d}%s" % (max(1, int((seg["end"] - t0) * 100)), esc(seg["text"]))
    parts, cursor = [], t0
    for w in words:
        gap = w["start"] - cursor
        if gap > 0.02:
            parts.append("{\\k%d}" % int(gap * 100))
        dur = max(1, int(round((w["end"] - max(w["start"], cursor)) * 100)))
        parts.append("{\\kf%d}%s " % (dur, esc(w["w"])))
        cursor = max(cursor, w["end"])
    return "".join(parts).rstrip()


def build_ass(lyrics, title, duration):
    head = """[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cur,Arial,66,&H00A34FFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,4,0,5,60,60,40,1
Style: Next,Arial,40,&H00D6A7B9,&H00D6A7B9,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,60,60,80,1
Style: Title,Arial,32,&H00F5DCE6,&H00F5DCE6,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,8,60,60,28,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    if title:
        ev.append("Dialogue: 0,%s,%s,Title,,0,0,0,,%s" % (ass_time(0), ass_time(duration), esc(title)))
    LEAD = 1.5
    for i, seg in enumerate(lyrics):
        prev_end = lyrics[i - 1]["end"] if i else 0.0
        t0 = max(seg["start"] - LEAD, prev_end, 0.0)
        if i + 1 < len(lyrics):
            nxt = lyrics[i + 1]
            next_t0 = max(nxt["start"] - LEAD, seg["end"])
            end = min(seg["end"] + 0.4, next_t0)
        else:
            nxt, end = None, seg["end"] + 0.6
        end = max(end, seg["end"])
        ev.append("Dialogue: 1,%s,%s,Cur,,0,0,0,,%s" % (ass_time(t0), ass_time(end), line_text(seg, t0)))
        if nxt:
            ev.append("Dialogue: 0,%s,%s,Next,,0,0,0,,%s" % (ass_time(t0), ass_time(end), esc(nxt["text"])))
    return head + "\n".join(ev) + "\n"


def media_duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def make_video(folder, lyrics, title):
    """karaoke.mp4: fondo morado + letra karaoke + pista instrumental (H.264/AAC: compatible con TVs y Cast)."""
    duration = media_duration(folder / "instrumental.mp3")
    (folder / "karaoke.ass").write_text(build_ass(lyrics, title, duration), encoding="utf-8")
    if os.environ.get("FAKE_PROCESS") == "1":   # solo pruebas: el Chromium de pruebas no decodifica H.264
        codec = ["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-c:a", "libopus"]
    else:
        codec = ["-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-b:a", "192k"]
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0x2a1450:s=1280x720:r=15",
           "-i", "instrumental.mp3", "-vf", "ass=karaoke.ass", *codec, "-shortest", "-movflags", "+faststart", "karaoke.mp4"]
    r = subprocess.run(cmd, cwd=folder, capture_output=True, text=True)   # cwd: evita problemas de rutas en el filtro
    if r.returncode != 0:
        raise RuntimeError("No se pudo crear el video (¿ffmpeg sin soporte de subtítulos/libass?): " + (r.stderr.strip().splitlines() or [""])[-1])
    (folder / "karaoke.ass").unlink(missing_ok=True)


def to_mp3(src, dst):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-b:a", "192k", str(dst)], check=True)


def fake(folder, src, title):
    """Modo de prueba (FAKE_PROCESS=1): sin IA, solo para probar el flujo."""
    stage("separating"); to_mp3(src, folder / "instrumental.mp3")
    shutil.copy(folder / "instrumental.mp3", folder / "vocals.mp3")
    stage("transcribing")
    words = "esta es una letra de prueba para el karaoke de lissa".split()
    ws = [{"w": w, "start": i * 0.6, "end": i * 0.6 + 0.5} for i, w in enumerate(words)]
    lyrics = [
        {"start": 0.5, "end": 3.0, "text": " ".join(words[:5]), "words": ws[:5]},
        {"start": 3.5, "end": 6.6, "text": " ".join(words[5:]), "words": ws[5:]},
    ]
    (folder / "lyrics.json").write_text(json.dumps(lyrics, ensure_ascii=False))
    stage("rendering"); make_video(folder, lyrics, title)


def main():
    folder = Path(sys.argv[1])
    lang = sys.argv[2] if len(sys.argv) > 2 else "auto"
    title = sys.argv[3] if len(sys.argv) > 3 else ""
    src = next(f for f in sorted(folder.glob("original.*")) if f.suffix.lower() != ".json")

    if os.environ.get("FAKE_PROCESS") == "1":
        return fake(folder, src, title)

    # 1) Quitar la voz
    stage("separating")
    sep = folder / "sep"
    subprocess.run([sys.executable, "-m", "demucs", "--two-stems=vocals", "-n", "htdemucs",
                    "-o", str(sep), str(src)], check=True)
    vocals_wav = next(sep.glob("*/*/vocals.wav"))
    novocals_wav = next(sep.glob("*/*/no_vocals.wav"))
    to_mp3(novocals_wav, folder / "instrumental.mp3")
    to_mp3(vocals_wav, folder / "vocals.mp3")

    # 2) Transcribir la voz aislada (rinde mucho mejor que la mezcla completa)
    stage("transcribing")
    from faster_whisper import WhisperModel
    try:
        import torch
        gpu = torch.cuda.is_available()
    except Exception:
        gpu = False
    model_name = os.environ.get("WHISPER_MODEL", "large-v3" if gpu else "small")
    model = WhisperModel(model_name, device="cuda" if gpu else "cpu",
                         compute_type="float16" if gpu else "int8")
    segments, _ = model.transcribe(str(vocals_wav), language=None if lang == "auto" else lang,
                                   word_timestamps=True, vad_filter=True)
    lyrics = build_lyrics(list(segments))
    (folder / "lyrics.json").write_text(json.dumps(lyrics, ensure_ascii=False))

    # 3) Video con letra
    stage("rendering")
    make_video(folder, lyrics, title)

    shutil.rmtree(sep, ignore_errors=True)
    stage("done")


if __name__ == "__main__":
    main()
