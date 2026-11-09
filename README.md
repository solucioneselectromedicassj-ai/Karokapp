# 🎤 Karaoke Party

Karaoke casero. Las canciones se **preparan en una PC** (descarga de YouTube o archivos propios → se quita la voz → se escribe la letra → video karaoke) y quedan en una **carpeta de Google Drive**. La **app del teléfono** (instalable) lee esa carpeta y reproduce, y puede transmitir a la TV.

```
 PC (pc/)  ──guarda──▶  Carpeta de Google Drive  ◀──lee──  App del teléfono (player/, en Vercel)
 procesa canciones        Cumple de Lissa/…mp4                 elige carpeta · reproduce · 📡 a la TV
```

| Carpeta | Qué es |
|---|---|
| `pc/` | Estación de la PC: descarga, quita voz, transcribe, genera el video y lo copia a la carpeta de Drive. Ver `pc/README.md`. |
| `player/` | App instalable (página estática) que lee la carpeta de Drive y reproduce. Es lo que publica Vercel (`vercel.json`). |
| `tools/mock-drive.js` | Simula la API de Drive para probar la app sin Google. |

## Atajo para Windows (la PC que prepara las canciones)
1. Descarga el proyecto (GitHub → Code → Download ZIP) y descomprímelo.
2. Doble clic en **`instalar.bat`**: instala Node.js, Python y ffmpeg con winget. Instala también **Google Drive para escritorio** (https://www.google.com/drive/download/) e inicia sesión.
3. Cierra la ventana y doble clic en **`iniciar.bat`**: la primera vez instala los componentes de IA (tarda y descarga varios GB), después detecta tu Drive, usa `Mi unidad\Karaoke\canciones` como biblioteca y abre `http://localhost:3000/preparar`.
4. En esa página: escribe la **carpeta** (ej. "Cumple de Lissa"), pega los enlaces de YouTube (uno por línea) y toca **Descargar y convertir en karaoke**.
   Cuando diga "Lista para la fiesta", el video aparece en Drive; en la app del teléfono toca ⟳.

## Puesta en marcha (una vez)

### 1. PC: preparar canciones y llenar la carpeta de Drive
1. Instala **Google Drive para escritorio** y crea una carpeta, por ejemplo `Mi unidad/Karaoke`.
2. Sigue `pc/README.md` (Node, Python, ffmpeg) y arranca apuntando a esa carpeta:
   - Windows: `set LIBRARY_DIR=G:\Mi unidad\Karaoke` y luego `node server.js`
   - Mac/Linux: `LIBRARY_DIR="$HOME/Google Drive/Karaoke" node server.js`
3. En `http://localhost:3000/preparar` pega enlaces de YouTube o sube archivos, eligiendo la **carpeta** (ej. "Cumple de Lissa").
   Cada canción lista aparece sola como `Karaoke/Cumple de Lissa/<canción>.mp4`, y Drive la sube.

### 2. Compartir la carpeta y crear la clave
1. En drive.google.com: clic derecho en `Karaoke` → Compartir → **“Cualquier persona con el enlace” → Lector**. Copia el enlace.
2. En [console.cloud.google.com](https://console.cloud.google.com/): crea un proyecto → *APIs y servicios* → **habilita “Google Drive API”**.
3. *Credenciales* → Crear credenciales → **Clave de API**. En “Restricciones de API” elige solo **Google Drive API**.
   (No pongas restricción por sitio web: Chromecast no envía esa cabecera y la transmisión fallaría.)

### 3. App del teléfono (Vercel + instalar)
- Vercel publica `player/` automáticamente con cada push a `main` (por `vercel.json`; no hace falta configurar nada).
  Abre la dirección de tu proyecto en Vercel (`https://….vercel.app`) en el teléfono.
- Primera vez: pega el enlace de la carpeta y la clave de API. Luego ⚙️ → **Copiar enlace de configuración** y mándalo por WhatsApp:
  quien lo abra queda configurado con un toque.
- **Instalar:** Android/Chrome → botón 📲 o menú ⋮ → *Instalar app*. iPhone/Safari → Compartir → *Añadir a pantalla de inicio*.

## Uso diario
Abrir la app → elegir **carpeta** → **▶ Reproducir carpeta** (o 🔀) o **Cantar** en una canción → **📡 Transmitir a la TV** (Chromecast / Smart TV con Google Cast; AirPlay en iPhone).
Si agregaste canciones nuevas desde la PC, toca ⟳ para actualizar la lista.

## Notas
- **Derechos de autor / privacidad:** la carpeta compartida contiene música; úsala solo en casa y no difundas el enlace ni la clave. Cualquiera que tenga el enlace de la carpeta y la clave puede escuchar.
- Bluetooth solo manda audio, no video: el video va por Chromecast/AirPlay/HDMI y el sonido sale por la TV o el parlante.
- Pasar contexto a otra sesión de Claude Code: `ARQUITECTURA.md`.
