# 🎤 Karaoke Party

App de karaoke casera. Pegas enlaces de YouTube o subes canciones de tu teléfono o laptop: se descargan a `songs/`, se les quita la voz,
se escribe la letra y se genera un **video karaoke** (letra que se pinta palabra por palabra). Se organizan en **carpetas** y se reproducen en la TV.

## Cómo encaja todo
```
 Laptop (servidor: descarga + quita voz + letra)  ←Wi-Fi→  Teléfonos (eligen, agregan, reproducen)
                         │
                         └─ TV: por HDMI desde la laptop, o transmitiendo el video desde el teléfono
```
- **La app es la misma en laptop y teléfono**: es una página web. El procesamiento pesado (IA) corre en la computadora que ejecuta `node server.js`;
  el teléfono solo envía enlaces o archivos y reproduce. (Un teléfono no puede correr Demucs/Whisper de forma práctica.)
- **Bluetooth solo transmite audio, no video.** Úsalo para el sonido (parlante). El video a la TV va por Chromecast/AirPlay/HDMI (abajo).

## Instalar (una vez, en la laptop)
1. Instala **Node.js 18+**, **Python 3.9+** y **ffmpeg** (con soporte de subtítulos/libass, lo normal).
2. `git clone https://github.com/solucioneselectromedicassj-ai/Karokapp && cd Karokapp`
3. `pip install -r requirements.txt` (la 1ª vez descarga modelos de IA, 1–3 GB: hazlo con buen internet y con tiempo).
4. `node server.js` → muestra las direcciones. Abre la principal en el teléfono (mismo Wi-Fi) y toca "Añadir a la pantalla de inicio" para que se vea como app.

## Instalarla como app en el teléfono
La app se sirve por Wi-Fi local (`http://IP:3000`). Los navegadores solo ofrecen "Instalar app" con HTTPS, así que:
- **iPhone (Safari):** Compartir → **Añadir a pantalla de inicio**. Funciona sin HTTPS y se abre como app, con el icono.
- **Android (Chrome), prueba rápida:** abre `chrome://flags/#unsafely-treat-insecure-origin-as-secure`, activa la opción, escribe `http://IP-DE-LA-LAPTOP:3000`,
  reinicia Chrome y luego menú ⋮ → **Instalar app**. (Sin esto, "Añadir a pantalla de inicio" crea solo un acceso directo con el icono.)
- **Cualquiera, con HTTPS real:** un túnel como `cloudflared tunnel --url http://localhost:3000` da una dirección `https://…` temporal que sí se instala normal.
- Iconos en `public/`: `icon.svg`, `icon-192.png`, `icon-512.png`, `icon-maskable-512.png` (Android), `apple-touch-icon.png` (iPhone).

## Antes de la fiesta: armar las carpetas
En **➕ Agregar canciones** (desde laptop o teléfono):
1. Escribe el nombre de la **carpeta** (ej. "Cumple de Lissa") y el idioma.
2. Pega enlaces de YouTube (uno por línea) **o** sube archivos del dispositivo (puedes elegir varios).
3. Se procesa una canción a la vez. Con GPU ~1–2 min; sin GPU ~5–15 min. Cuando diga ✅ **Lista para la fiesta**, ya no necesita internet.
   Usa la **canción original con voz**.

## El día de la fiesta
1. En la pantalla principal elige una **carpeta** → **▶ Reproducir carpeta** (o **🔀 Aleatorio**), o toca **Cantar** en canciones sueltas.
   Cada niña puede poner su nombre y añadir canciones a la fila.
2. **Mostrar en la TV**, elige una opción:
   - **Laptop por HDMI a la TV**: abre `/tv` en la laptop y toca "Iniciar". (La más estable.)
   - **Desde el teléfono (Chromecast / Smart TV con Google Cast)**: abre `/tv` en el teléfono con Chrome, toca "Iniciar" y luego **📡 Transmitir a la TV**.
     Si no aparece la TV, usa el menú de Chrome → *Transmitir* (transmite toda la pestaña, sirve también para los videos de YouTube).
   - **iPhone (AirPlay)**: abre `/tv` en Safari y usa el mismo botón para elegir la TV.
   - **Cable USB-C/Lightning a HDMI** desde el teléfono con `/tv` abierto.
3. Sonido: el de la TV, o Bluetooth al parlante. Apaga la función "quitar voz" del parlante.

## Notas
- `songs/` **no se sube a GitHub** (audio con derechos de autor y archivos pesados): se genera en cada computadora. Uso personal.
- La letra transcrita puede tener errores; elige bien el idioma. `WHISPER_MODEL=medium node server.js` mejora la precisión (tiny, base, small, medium, large-v3).
- Cada canción lista incluye `karaoke.mp4`: también se puede copiar a una USB y reproducir en cualquier TV.
- La búsqueda de YouTube de la pantalla principal reproduce karaokes ya hechos, pero necesita internet durante la fiesta.
- Modo de prueba sin IA ni descargas: `FAKE_PROCESS=1 node server.js`.
