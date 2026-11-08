#!/usr/bin/env python3
"""Convierte una canción en karaoke: quita la voz (Demucs) y transcribe la letra con tiempos (Whisper).

Uso: process.py <carpeta> [idioma|auto]
Entrada : <carpeta>/original.<ext>
Salida  : <carpeta>/instrumental.mp3, vocals.mp3, lyrics.json
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


def to_mp3(src, dst):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-b:a", "192k", str(dst)], check=True)


def fake(folder, src):
    """Modo de prueba (FAKE_PROCESS=1): sin IA, solo para probar el flujo."""
    stage("separating"); to_mp3(src, folder / "instrumental.mp3")
    shutil.copy(folder / "instrumental.mp3", folder / "vocals.mp3")
    stage("transcribing")
    words = "esta es una letra de prueba para el karaoke de lissa".split()
    ws = [{"w": w, "start": i * 0.6, "end": i * 0.6 + 0.5} for i, w in enumerate(words)]
    lyrics = [
        {"start": 0, "end": 3.0, "text": " ".join(words[:5]), "words": ws[:5]},
        {"start": 3.0, "end": 6.6, "text": " ".join(words[5:]), "words": ws[5:]},
    ]
    (folder / "lyrics.json").write_text(json.dumps(lyrics, ensure_ascii=False))


def main():
    folder = Path(sys.argv[1])
    lang = sys.argv[2] if len(sys.argv) > 2 else "auto"
    src = next(f for f in sorted(folder.glob("original.*")) if f.suffix.lower() != ".json")

    if os.environ.get("FAKE_PROCESS") == "1":
        return fake(folder, src)

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
    (folder / "lyrics.json").write_text(json.dumps(build_lyrics(list(segments)), ensure_ascii=False))

    shutil.rmtree(sep, ignore_errors=True)
    stage("done")


if __name__ == "__main__":
    main()
