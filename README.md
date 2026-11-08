# 🎤 Karaoke Party

App de karaoke casera: pegas enlaces de YouTube, se descargan a `songs/`, se les quita la voz y se escribe la letra.
Las niñas eligen desde el teléfono y suena en la TV con la letra resaltada.

## Instalar (una vez, en la laptop de la fiesta)
1. Instala **Node.js 18+**, **Python 3.9+** y **ffmpeg**.
2. Descarga el proyecto: `git clone https://github.com/solucioneselectromedicassj-ai/Karokapp && cd Karokapp`
3. `pip install -r requirements.txt`  (la 1ª vez descarga modelos de IA, 1–3 GB: hazlo con buen internet y con tiempo).

## Antes de la fiesta: preparar las canciones
1. `node server.js`
2. Abre `http://localhost:3000/preparar`, pega los enlaces de YouTube (uno por línea) y elige el idioma.
3. Se descarga → quita la voz → escribe la letra, una canción a la vez. Con GPU ~1 min; sin GPU ~5–15 min por canción.
4. Cuando todas digan **✅ Lista para la fiesta**, ya no necesitas internet para cantarlas.
   Lo preparado queda guardado en `songs/` (no se vuelve a procesar).

## El día de la fiesta
1. `node server.js` → muestra las direcciones.
2. Laptop a la TV por HDMI → abre `/tv` y toca "Iniciar".
3. Teléfonos en el mismo Wi-Fi → abren la dirección principal, ponen su nombre y tocan **Cantar**.
   Pueden "Añadir a la pantalla de inicio" para que se vea como una app.
4. Apaga la función "quitar voz" del parlante.

## Notas
- `songs/` **no se sube a GitHub** (audio con derechos de autor y archivos pesados): se genera en cada computadora. Uso personal.
- La letra transcrita puede tener errores; elige bien el idioma. `WHISPER_MODEL=medium node server.js` mejora la precisión (tiny, base, small, medium, large-v3).
- Búsqueda directa en YouTube (pantalla principal): sirve para karaokes ya hechos, pero necesita internet durante la fiesta.
- Modo de prueba sin IA ni descargas: `FAKE_PROCESS=1 node server.js`.
