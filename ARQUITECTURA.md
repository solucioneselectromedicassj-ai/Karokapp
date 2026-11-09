# Resumen técnico (para pasar a Claude Code)

**Objetivo:** karaoke casero para el cumpleaños de Lissa. Una PC prepara canciones; una app instalada en los teléfonos de la casa las reproduce desde una carpeta de Google Drive y las transmite a la TV.

## Arquitectura
- `pc/` — Node (sin dependencias npm) + Python. `server.js` (HTTP + SSE), `process.py` (Demucs → faster-whisper → ASS karaoke → `karaoke.mp4` con ffmpeg), UI en `pc/public` (`/` fila local, `/preparar` agregar/gestionar, `/tv` reproductor).
  - Trabajo interno en `pc/songs/<id>/` (original, stems, lyrics.json, karaoke.mp4, meta.json).
  - **Publicación:** al quedar lista, `publish()` copia `karaoke.mp4` a `LIBRARY_DIR/<carpeta>/<título>.mp4` (LIBRARY_DIR = carpeta sincronizada con Drive). Mover/borrar en la UI mueve/borra el archivo publicado.
- `player/` — PWA estática (un `index.html`, `sw.js`, manifest, iconos). Sin backend. Lee la carpeta de Drive con **Drive API v3 + clave de API** (carpeta compartida "cualquiera con el enlace"): `files.list` (raíz → subcarpetas = "carpetas", `.mp4` = canciones) y `files/{id}?alt=media&key=` como `src` del `<video>`. Fila en `localStorage`. Transmitir con Remote Playback API (Cast) / AirPlay. Config (`key`, `folder`) en `localStorage`, importable por `/#k=…&f=…`.
- `vercel.json` (raíz) — publica solo `player/` como sitio estático (framework null, outputDirectory `player`). Antes el repo tenía Python en la raíz y Vercel fallaba con PYTHON_ENTRYPOINT_NOT_FOUND.
- `tools/mock-drive.js` — simula Drive (`node tools/mock-drive.js <biblioteca> 3201`, clave `TESTKEY`; id raíz `ROOTFOLDER_ID_0001`). Config de prueba: `/#k=TESTKEY&f=ROOTFOLDER_ID_0001&api=<url-api-codificada>`.

## Decisiones
- El teléfono NO procesa (Demucs/Whisper no son prácticos allí): solo reproduce. Bluetooth no lleva video; video por Cast/AirPlay/HDMI.
- Clave de API restringida solo a "Drive API" (sin restricción por referrer, porque Chromecast no envía Referer).
- `FAKE_PROCESS=1` en la PC: sin IA ni descargas (tono + letra falsa; video en VP9 para el Chromium de pruebas; en real es H.264/AAC).

## Probado vs. no probado
- Probado (con simulaciones): cola, publicación/mover/borrar en la biblioteca, app contra Drive simulado (config por enlace, carpetas, aleatorio, auto-avance, persistencia), render del video con letra, instalación del service worker.
- **No probado** (bloqueado en el entorno de desarrollo): descarga real de YouTube (`yt-dlp`), Demucs/Whisper reales, Drive API real con clave real, deploy en Vercel, Chromecast/AirPlay reales, instalación en un teléfono real.

## Pendiente / ideas
- Probar el flujo real extremo a extremo con una canción y ajustar tiempos de la letra si Whisper se desfasa.
- Modo sin internet: guardar los videos de una carpeta en el teléfono (Cache Storage/IndexedDB) — ojo: Cast necesita la URL de Drive, no un blob.
- Alternativa más privada que la carpeta pública: OAuth de Drive limitado a los correos de la familia.
- Opción de pegar la letra correcta y alinearla en vez de transcribir.
