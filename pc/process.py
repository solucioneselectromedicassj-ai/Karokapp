#!/usr/bin/env python3
"""Convierte una canción en karaoke: quita la voz (Demucs), transcribe la letra con tiempos (Whisper)
y genera un VIDEO (karaoke.mp4) con la letra incrustada, reproducible en TV, celular, Chromecast o AirPlay.

Uso: process.py <carpeta> [idioma|auto] [titulo]
Entrada : <carpeta>/original.<ext>
Salida  : <carpeta>/instrumental.mp3, vocals.mp3, lyrics.json, karaoke.mp4
Imprime líneas "STAGE <nombre>" para que el servidor muestre el progreso.
"""
import difflib, json, os, re, shutil, subprocess, sys, unicodedata
import urllib.parse, urllib.request
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


# ---------- Letra correcta: limpiar, alinear con el audio y buscarla en línea ----------
SECTION = re.compile(r"^\W*(coro|estribillo|verso|puente|intro|outro|pre-?coro|pre-?estribillo|chorus|verse|bridge|pre-?chorus|hook|interludio|instrumental)\b[^\n]{0,30}$", re.I)


def clean_lyrics_text(text):
    """Acepta texto plano, LRC o SRT/VTT y devuelve solo las líneas de la letra."""
    lines = []
    for raw in str(text).replace("\r", "").split("\n"):
        t = raw.strip().lstrip("﻿")
        if not t or t.upper() == "WEBVTT" or re.fullmatch(r"\d+", t):            # vacías, cabecera VTT, números de SRT
            continue
        if re.search(r"\d{1,2}:\d{2}:\d{2}[.,]\d{1,3}\s*-->", t):                 # tiempos SRT/VTT
            continue
        if re.match(r"^\[(ti|ar|al|by|offset|length|re|ve|au):", t, re.I):          # metadatos LRC
            continue
        t = re.sub(r"\[\d{1,3}:\d{2}(?:[.:]\d{1,3})?\]|<\d{1,3}:\d{2}(?:[.:]\d{1,3})?>", "", t)   # [mm:ss.xx]
        t = re.sub(r"</?[a-zA-Z][^>]*>", "", t).strip()                             # <i>…</i>
        if not t or re.fullmatch(r"\[[^\]]*\]", t) or SECTION.match(t):             # [Coro], Verso 1:
            continue
        lines.append(re.sub(r"\s+", " ", t))
    return lines


def norm_word(w):
    w = unicodedata.normalize("NFD", str(w).lower())
    w = "".join(c for c in w if unicodedata.category(c) != "Mn")
    return re.sub(r"[^\w]", "", w)


def align_lyrics(lines, asr_words, duration=0.0):
    """Pone tiempos a la letra correcta usando las palabras que Whisper sí reconoció como puntos de apoyo.
    Devuelve (segmentos, proporción_de_palabras_reconocidas)."""
    U = []
    for i, line in enumerate(lines):
        for tok in line.split():
            n = norm_word(tok)
            if n:
                U.append({"w": tok, "n": n, "line": i, "start": None, "end": None})
    A = [a for a in asr_words if norm_word(a["w"])]
    if not U:
        return [], 0.0
    matched = 0
    if A:
        sm = difflib.SequenceMatcher(None, [u["n"] for u in U], [norm_word(a["w"]) for a in A], autojunk=False)
        for blk in sm.get_matching_blocks():
            for k in range(blk.size):
                u, a = U[blk.a + k], A[blk.b + k]
                u["start"], u["end"] = a["start"], a["end"]
                matched += 1
    ratio = matched / len(U)
    anchors = [i for i, u in enumerate(U) if u["start"] is not None]
    t_first = A[0]["start"] if A else 0.0
    t_last = A[-1]["end"] if A else (duration or len(U) * 0.4)
    if not anchors:                                      # sin puntos de apoyo: repartir parejo entre la primera y la última palabra oída
        step = max((t_last - t_first) / len(U), 0.1)
        for i, u in enumerate(U):
            u["start"], u["end"] = t_first + i * step, t_first + (i + 1) * step
    else:
        def fill(i0, i1, t0, t1):                        # reparte U[i0:i1] entre t0 y t1
            k = i1 - i0
            if k <= 0:
                return
            slot = max((t1 - t0) / k, 0.05)
            for j in range(k):
                U[i0 + j]["start"] = t0 + j * slot
                U[i0 + j]["end"] = t0 + (j + 1) * slot
        first, last = anchors[0], anchors[-1]
        fill(0, first, max(U[first]["start"] - 0.4 * first, 0.0), U[first]["start"])           # antes del primer apoyo
        for x, y in zip(anchors, anchors[1:]):
            fill(x + 1, y, U[x]["end"], U[y]["start"])                                            # entre apoyos
        tail_end = U[last]["end"] + 0.4 * (len(U) - 1 - last)
        if duration:
            tail_end = min(tail_end, max(duration - 0.2, U[last]["end"] + 0.05 * (len(U) - 1 - last)))
        fill(last + 1, len(U), U[last]["end"], tail_end)                                        # después del último apoyo
    prev = 0.0
    for u in U:                                          # tiempos que nunca retroceden
        u["start"] = max(u["start"], prev)
        u["end"] = max(u["end"], u["start"] + 0.05)
        prev = u["start"]
    segs = []
    for i, line in enumerate(lines):
        ws = [u for u in U if u["line"] == i]
        if ws:
            segs.append({"start": round(ws[0]["start"], 2), "end": round(ws[-1]["end"], 2), "text": line,
                         "words": [{"w": u["w"], "start": round(u["start"], 2), "end": round(u["end"], 2)} for u in ws]})
    return segs, ratio


def guess_artist_title(title):
    t = re.sub(r"[\(\[][^\)\]]*[\)\]]", " ", str(title))
    t = re.sub(r"\b(official|video|oficial|lyrics?|letra|audio|videoclip|clip|hd|4k)\b", " ", t, flags=re.I)
    parts = re.split(r"\s[-–—|]\s", t.strip(), maxsplit=1)
    artist, track = (parts[0], parts[1]) if len(parts) == 2 else ("", parts[0])
    return re.sub(r"\s+", " ", artist).strip(" -"), re.sub(r"\s+", " ", track).strip(" -")


def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "KaraokeParty/1.0 (uso personal)"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_lrclib(title, duration=0.0):
    """Busca la letra en LRCLIB (gratis, sin clave). Devuelve el texto o None."""
    base = os.environ.get("LRCLIB_BASE", "https://lrclib.net")
    artist, track = guess_artist_title(title)
    queries = []
    if track:
        queries.append({"track_name": track, **({"artist_name": artist} if artist else {})})
    queries.append({"q": f"{artist} {track}".strip() or str(title)})
    for q in queries:
        try:
            data = http_json(base + "/api/search?" + urllib.parse.urlencode(q))
        except Exception:
            continue
        best, best_score = None, None
        for c in data if isinstance(data, list) else []:
            text = c.get("plainLyrics") or c.get("syncedLyrics")
            if c.get("instrumental") or not text:
                continue
            dd = abs(float(c.get("duration") or 0) - duration) if duration and c.get("duration") else 0
            if duration and dd > 25:
                continue
            sim = difflib.SequenceMatcher(None, norm_word(c.get("trackName", "")), norm_word(track or title)).ratio()
            if sim < 0.6:
                continue
            score = (round(sim, 1), -dd)
            if best_score is None or score > best_score:
                best, best_score = text, score
        if best:
            return best
    return None


def choose_lyrics(folder, title, duration, asr_lyrics):
    """Prioridad: letra pegada por ti > letra encontrada en LRCLIB > lo que escuchó Whisper."""
    asr_words = [w for seg in asr_lyrics for w in seg.get("words", [])]
    manual = folder / "lyrics.txt"
    text, source = None, "whisper"
    if manual.exists() and manual.read_text(encoding="utf-8", errors="replace").strip():
        text, source = manual.read_text(encoding="utf-8", errors="replace"), "manual"
    elif os.environ.get("LRCLIB", "1") != "0":
        stage("searching_lyrics")
        found = fetch_lrclib(title, duration)
        if found:
            text, source = found, "lrclib"
    if text:
        lines = clean_lyrics_text(text)
        if lines:
            segs, ratio = align_lyrics(lines, asr_words, duration)
            if segs and (source == "manual" or ratio >= 0.35):     # la letra de internet solo se acepta si coincide con el audio
                print(f"INFO lyrics={source} ratio={ratio:.2f}", flush=True)
                return segs, source
    print("INFO lyrics=whisper ratio=0.00", flush=True)
    return asr_lyrics, "whisper"


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


def load_audio_16k(path):
    """Decodifica el audio con ffmpeg a mono 16 kHz (float32). Evita 'av.open(metadata_errors=...)' de faster-whisper,
    que falla con las versiones nuevas de PyAV."""
    import numpy as np
    r = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                       capture_output=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg no pudo leer el audio: " + r.stderr.decode(errors="replace").strip()[-200:])
    return np.frombuffer(r.stdout, dtype=np.float32)


def guide_level():
    try:
        return min(max(float(os.environ.get("GUIDE_LEVEL", "0.3")), 0.05), 1.0)
    except ValueError:
        return 0.3


def make_guide(folder, level=None):
    """karaoke_guia.mp4: el mismo video, pero con la voz original mezclada a bajo volumen (voz guía) para seguir la melodía.
    No vuelve a dibujar el video (lo copia): tarda segundos."""
    level = guide_level() if level is None else level
    src, vocals = folder / "karaoke.mp4", folder / "vocals.mp3"
    if not (src.exists() and vocals.exists()):
        return False
    audio = ["-c:a", "libopus"] if os.environ.get("FAKE_PROCESS") == "1" else ["-c:a", "aac", "-b:a", "192k"]
    mix = f"[0:a][1:a]amix=inputs=2:weights=1 {level:.2f}:normalize=0:duration=first[a]"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", "karaoke.mp4", "-i", "vocals.mp3", "-filter_complex", mix,
           "-map", "0:v", "-map", "[a]", "-c:v", "copy", *audio, "-movflags", "+faststart", "karaoke_guia.mp4"]
    r = subprocess.run(cmd, cwd=folder, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("No se pudo crear la version con voz guia: " + (r.stderr.strip().splitlines() or [""])[-1])
    print(f"INFO guide level={level:.2f}", flush=True)
    return True


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
    (folder / "asr.json").write_text(json.dumps(lyrics, ensure_ascii=False))
    lyrics, _ = choose_lyrics(folder, title, media_duration(folder / "instrumental.mp3"), lyrics)
    (folder / "lyrics.json").write_text(json.dumps(lyrics, ensure_ascii=False))
    stage("rendering"); make_video(folder, lyrics, title); make_guide(folder)


def main():
    folder = Path(sys.argv[1])
    lang = sys.argv[2] if len(sys.argv) > 2 else "auto"
    title = sys.argv[3] if len(sys.argv) > 3 else ""
    mode = sys.argv[4] if len(sys.argv) > 4 else "full"

    if mode == "guide":           # rehacer solo la versión con voz guía (por ejemplo, tras cambiar el volumen)
        stage("rendering")
        if not make_guide(folder):
            raise RuntimeError("Falta el video o la voz separada de esta canción")
        return stage("done")

    if mode == "lyrics":          # rehacer solo la letra y el video (sin volver a separar la voz ni a transcribir)
        asr_file = folder / "asr.json" if (folder / "asr.json").exists() else folder / "lyrics.json"
        asr = json.loads(asr_file.read_text(encoding="utf-8"))
        if not (folder / "instrumental.mp3").exists():
            raise RuntimeError("Falta la pista instrumental: procesa la canción completa otra vez")
        if not (folder / "asr.json").exists():
            (folder / "asr.json").write_text(json.dumps(asr, ensure_ascii=False))
        lyrics, _ = choose_lyrics(folder, title, media_duration(folder / "instrumental.mp3"), asr)
        (folder / "lyrics.json").write_text(json.dumps(lyrics, ensure_ascii=False))
        stage("rendering"); make_video(folder, lyrics, title); make_guide(folder)
        return stage("done")

    src = next(f for f in sorted(folder.glob("original.*")) if f.suffix.lower() != ".json")

    if os.environ.get("FAKE_PROCESS") == "1":
        return fake(folder, src, title)

    # 1) Quitar la voz
    stage("separating")
    sep = folder / "sep"
    vocals_wav = next(iter(sep.glob("*/*/vocals.wav")), None)
    novocals_wav = next(iter(sep.glob("*/*/no_vocals.wav")), None)
    if not (vocals_wav and novocals_wav):      # si ya se separó antes (reintento), no se repite: tarda mucho
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
    segments, _ = model.transcribe(load_audio_16k(vocals_wav), language=None if lang == "auto" else lang,
                                   word_timestamps=True, vad_filter=True)
    asr = build_lyrics(list(segments))
    (folder / "asr.json").write_text(json.dumps(asr, ensure_ascii=False))          # lo que oyó Whisper (con tiempos)
    lyrics, _ = choose_lyrics(folder, title, media_duration(folder / "instrumental.mp3"), asr)
    (folder / "lyrics.json").write_text(json.dumps(lyrics, ensure_ascii=False))

    # 3) Video con letra
    stage("rendering")
    make_video(folder, lyrics, title)
    make_guide(folder)

    shutil.rmtree(sep, ignore_errors=True)
    stage("done")


if __name__ == "__main__":
    main()
