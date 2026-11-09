// Karaoke Party - servidor sin dependencias npm (solo Node 18+).
// Canciones de YouTube (búsqueda con yt-dlp) + canciones propias subidas y convertidas a karaoke (process.py).
const http = require('http');
const fs = require('fs');
const path = require('path');
const os = require('os');
const crypto = require('crypto');
const { execFile, spawn } = require('child_process');

const PORT = process.env.PORT || 3000;
const PUBLIC = path.join(__dirname, 'public');
const SONGS = path.join(__dirname, 'songs');            // trabajo interno (original, voces, etc.)
// Biblioteca para la app del teléfono: Carpeta/Canción.mp4. Apúntala a una carpeta sincronizada con Google Drive:
//   LIBRARY_DIR="G:\\Mi unidad\\Karaoke" node server.js
const LIBRARY_DIR = path.resolve(process.env.LIBRARY_DIR || path.join(__dirname, 'biblioteca'));
const MOCK = process.env.MOCK_SEARCH === '1';
const PYTHON = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const MAX_UPLOAD = 150 * 1024 * 1024;
const AUDIO_EXT = new Set(['.mp3', '.wav', '.m4a', '.flac', '.ogg', '.aac', '.opus', '.mp4', '.webm']);
fs.mkdirSync(SONGS, { recursive: true });
fs.mkdirSync(LIBRARY_DIR, { recursive: true });

let queue = [];                 // [{qid, kind:'yt'|'local', id|lid, title, thumb, singer}]
let nextQid = 1;
const library = new Map();      // lid -> {lid,title,lang,status:'queued'|'processing'|'ready'|'error',stage,error}
const jobs = [];                // lids esperando procesamiento
let working = false;
const clients = new Set();      // conexiones SSE

// ---------- Estado ----------
const playable = it => it.kind === 'yt' || library.get(it.lid)?.status === 'ready';
function state() {
  const q = queue.map(it => it.kind === 'local'
    ? { ...it, status: library.get(it.lid)?.status || 'error', stage: library.get(it.lid)?.stage || '' }
    : it);
  const cur = queue.find(playable);
  const folders = [...new Set([...library.values()].map(x => x.folder || 'General'))].sort((a, b) => a.localeCompare(b));
  return { queue: q, current: cur ? cur.qid : null, library: [...library.values()].reverse(), folders };
}
const broadcast = () => {
  const data = `data: ${JSON.stringify(state())}\n\n`;
  clients.forEach(res => res.write(data));
};

// ---------- Búsqueda en YouTube ----------
const YT_URL = /(?:youtu\.be\/|youtube\.com\/(?:watch\?(?:.*&)?v=|shorts\/|embed\/|live\/))([\w-]{11})/i;

async function fromLink(id) {
  let title = 'Video de YouTube', channel = '';
  try {
    const r = await fetch(`https://www.youtube.com/oembed?format=json&url=${encodeURIComponent('https://www.youtube.com/watch?v=' + id)}`);
    if (r.ok) { const j = await r.json(); title = j.title; channel = j.author_name; }
  } catch {}
  return [{ id, title, channel, duration: 0, thumb: `https://i.ytimg.com/vi/${id}/mqdefault.jpg` }];
}

async function scrapeSearch(term) {
  const r = await fetch('https://www.youtube.com/results?search_query=' + encodeURIComponent(term), {
    headers: { 'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'es' }
  });
  const m = (await r.text()).match(/var ytInitialData = (\{.*?\});<\/script>/s);
  if (!m) throw new Error('sin datos');
  const out = [];
  (function walk(o) {
    if (!o || typeof o !== 'object' || out.length >= 10) return;
    if (o.videoRenderer && o.videoRenderer.videoId) {
      const v = o.videoRenderer;
      out.push({ id: v.videoId, title: v.title?.runs?.[0]?.text || '', channel: v.ownerText?.runs?.[0]?.text || '',
                 duration: 0, thumb: `https://i.ytimg.com/vi/${v.videoId}/mqdefault.jpg` });
    }
    Object.values(o).forEach(walk);
  })(JSON.parse(m[1]));
  return out;
}

function search(q) {
  const link = q.match(YT_URL);
  if (link) return fromLink(link[1]);
  return new Promise((resolve, reject) => {
    if (MOCK) {
      return resolve([1, 2, 3, 4].map(i => ({
        id: 'dQw4w9WgXcQ', title: `${q} (karaoke) #${i}`, channel: 'Canal de prueba',
        duration: 180 + i, thumb: 'https://i.ytimg.com/vi/dQw4w9WgXcQ/mqdefault.jpg'
      })));
    }
    const term = /karaoke/i.test(q) ? q : `${q} karaoke`;
    ytdlp([`ytsearch10:${term}`, '--flat-playlist', '--dump-json', '--no-warnings'],
      { timeout: 30000, maxBuffer: 10 * 1024 * 1024 }, (err, stdout) => {
        if (err && !stdout) return scrapeSearch(term).then(resolve, () => reject(err));
        resolve(stdout.split('\n').filter(Boolean).map(l => {
          try {
            const j = JSON.parse(l);
            return { id: j.id, title: j.title, channel: j.channel || j.uploader || '',
                     duration: j.duration || 0, thumb: `https://i.ytimg.com/vi/${j.id}/mqdefault.jpg` };
          } catch { return null; }
        }).filter(Boolean));
      });
  });
}

// ---------- Canciones propias: procesamiento en segundo plano (una a la vez) ----------
const saveMeta = s => fs.writeFileSync(path.join(SONGS, s.lid, 'meta.json'), JSON.stringify(s));

const FAKE = process.env.FAKE_PROCESS === '1';
// yt-dlp se ejecuta como "python -m yt_dlp": en Windows, el Control Inteligente de Aplicaciones bloquea el
// yt-dlp.exe sin firma que crea pip, pero no a Python. Si no funciona, se intenta el ejecutable "yt-dlp".
// --js-runtimes: yt-dlp necesita un motor de JavaScript para YouTube; se usa el mismo Node que corre este servidor.
function ytdlp(args, opts, cb) {
  const full = ['--js-runtimes', 'node:' + process.execPath, ...args];
  execFile(PYTHON, ['-m', 'yt_dlp', ...full], opts, (err, so, se) => {
    const missing = err && (err.code === 'ENOENT' || /No module named yt_dlp/.test(String(se)));
    const blocked = err && ['EACCES', 'EPERM', 'UNKNOWN'].includes(err.code);
    if (missing || blocked) return execFile('yt-dlp', full, opts, cb);
    cb(err, so, se);
  });
}
const noYtdlp = (err, errOut) => err && (err.code === 'ENOENT' || /No module named yt_dlp/.test(String(errOut)));
const safeName = t => String(t).replace(/[\\/:*?"<>|\u0000-\u001f]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 100) || 'cancion';

// Copia karaoke.mp4 a LIBRARY_DIR/<carpeta>/<título>.mp4 (lo que lee la app del teléfono desde Drive)
function unpublish(s) {
  if (!s.published) return;
  const f = path.resolve(LIBRARY_DIR, s.published);
  if (f.startsWith(LIBRARY_DIR + path.sep)) {
    fs.rmSync(f, { force: true });
    try { fs.rmdirSync(path.dirname(f)); } catch {}      // quita la carpeta si quedó vacía
  }
  s.published = '';
}
function publish(s) {
  try {
    const src = path.join(SONGS, s.lid, 'karaoke.mp4');
    if (!fs.existsSync(src)) return;
    unpublish(s);
    const dir = path.join(LIBRARY_DIR, safeName(s.folder));
    fs.mkdirSync(dir, { recursive: true });
    let n = 1, dest;
    do { dest = path.join(dir, safeName(s.title) + (n > 1 ? ` (${n})` : '') + '.mp4'); n++; } while (fs.existsSync(dest));
    fs.copyFileSync(src, dest);
    s.published = path.relative(LIBRARY_DIR, dest);
    saveMeta(s);
  } catch (e) { console.error('No se pudo publicar en la biblioteca:', e.message); }
}
const lastLine = t => String(t || '').trim().split('\n').filter(Boolean).pop() || '';
const originalFile = lid => fs.readdirSync(path.join(SONGS, lid)).find(f => /^original\.[a-z0-9]+$/i.test(f) && !f.endsWith('.json') && !f.endsWith('.part'));

// Descarga el audio de YouTube a songs/<lid>/original.mp3
function download(s) {
  const dir = path.join(SONGS, s.lid);
  return new Promise((resolve, reject) => {
    if (FAKE) {   // modo de prueba: genera un tono en vez de descargar
      return execFile('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'lavfi', '-i', 'sine=frequency=330:duration=10', path.join(dir, 'original.mp3')],
        err => err ? reject(new Error('ffmpeg no está instalado')) : resolve());
    }
    ytdlp(['--no-playlist', '-x', '--audio-format', 'mp3', '--audio-quality', '0', '--write-info-json', '--no-warnings',
      '-o', path.join(dir, 'original.%(ext)s'), 'https://www.youtube.com/watch?v=' + s.yt],
      { timeout: 10 * 60 * 1000, maxBuffer: 10 * 1024 * 1024 }, (err, out, errOut) => {
        if (err) console.error(`\n[descarga fallida: ${s.title}]\n${errOut || err.message}\n`);
        if (err) return reject(new Error(noYtdlp(err, errOut)
          ? 'yt-dlp no está instalado (pip install yt-dlp)' : lastLine(errOut) || err.message));
        const info = path.join(dir, 'original.info.json');
        try { const j = JSON.parse(fs.readFileSync(info, 'utf8')); if (j.title) s.title = j.title.slice(0, 120); } catch {}
        fs.rmSync(info, { force: true });
        resolve();
      });
  });
}

function runNext() {
  if (working) return;
  const lid = jobs.shift();
  const s = lid && library.get(lid);
  if (!s) return;
  working = true;
  console.log(`\n>> Procesando: ${s.title}`);
  const finish = (ok, msg) => {
    if (!working) return;
    console.log(ok ? `>> Lista: ${s.title}\n` : `>> ERROR en "${s.title}": ${msg}\n`);
    working = false;
    s.status = ok ? 'ready' : 'error'; s.stage = ''; s.error = ok ? '' : msg;
    if (ok) publish(s);
    saveMeta(s); broadcast(); runNext();
  };
  const convert = () => {
    s.status = 'processing'; s.stage = 'starting'; broadcast();
    let errTail = '';
    const child = spawn(PYTHON, [path.join(__dirname, 'process.py'), path.join(SONGS, lid), s.lang || 'auto', s.title || '']);
    child.stdout.on('data', d => {
      const m = String(d).match(/STAGE (\w+)/g);
      if (m) { s.stage = m[m.length - 1].slice(6); broadcast(); }
    });
    child.stderr.on('data', d => { process.stderr.write(d); errTail = (errTail + d).slice(-4000); });   // se muestra completo en la ventana
    child.on('error', e => finish(false, `No se pudo ejecutar ${PYTHON}: ${e.message}`));
    child.on('close', code => {
      const ok = code === 0 && fs.existsSync(path.join(SONGS, lid, 'karaoke.mp4'));
      finish(ok, lastLine(errTail) || `Falló (código ${code})`);
    });
  };
  if (s.yt && !originalFile(lid)) {
    s.status = 'downloading'; s.stage = ''; broadcast();
    download(s).then(() => { saveMeta(s); convert(); }, e => finish(false, e.message));
  } else convert();
}

// Crea una entrada (sin archivo aún) y la pone en la cola de trabajo
const cleanFolder = f => String(f || '').replace(/[\u0000-\u001f<>]/g, '').trim().slice(0, 40) || 'General';
function addSong({ title, lang, yt, folder }) {
  const lid = 's' + crypto.randomBytes(5).toString('hex');
  fs.mkdirSync(path.join(SONGS, lid));
  const s = { lid, title: String(title).slice(0, 120), lang: LANGS.includes(lang) ? lang : 'auto', yt: yt || '', folder: cleanFolder(folder), status: 'queued', stage: '', error: '' };
  library.set(lid, s); saveMeta(s); jobs.push(lid);
  return s;
}
const LANGS = ['es', 'en', 'pt', 'fr', 'it', 'ko', 'auto'];

// Importa enlaces de YouTube: descarga + convierte a karaoke
async function importLinks(urls, lang, folder) {
  const out = [];
  for (const raw of urls.slice(0, 30)) {
    const m = String(raw).match(YT_URL);
    if (!m) { out.push({ url: raw, error: 'Enlace de YouTube no válido' }); continue; }
    const dup = [...library.values()].find(x => x.yt === m[1] && x.status !== 'error');
    if (dup) { out.push({ url: raw, lid: dup.lid, title: dup.title, duplicate: true }); continue; }
    const info = (await fromLink(m[1]))[0];
    const s = addSong({ title: info.title, lang, yt: m[1], folder });
    out.push({ url: raw, lid: s.lid, title: s.title });
  }
  broadcast(); runNext();
  return out;
}

function loadLibrary() {
  for (const lid of fs.readdirSync(SONGS)) {
    try {
      const s = JSON.parse(fs.readFileSync(path.join(SONGS, lid, 'meta.json'), 'utf8'));
      const ok = fs.existsSync(path.join(SONGS, lid, 'karaoke.mp4'));
      s.folder = s.folder || 'General';
      const wasError = s.status === 'error';
      s.status = ok ? 'ready' : wasError ? 'error' : 'queued'; s.stage = '';
      library.set(lid, s);
      if (s.status === 'queued') jobs.push(lid);
      if (ok && !s.published) publish(s);
    } catch {}
  }
  runNext();
}

// ---------- HTTP ----------
const readBody = req => new Promise(resolve => {
  let b = '';
  req.on('data', c => { b += c; if (b.length > 1e5) req.destroy(); });
  req.on('end', () => { try { resolve(JSON.parse(b || '{}')); } catch { resolve({}); } });
});
const json = (res, code, obj) => { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(obj)); };
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json',
               '.mp3': 'audio/mpeg', '.mp4': 'video/mp4', '.png': 'image/png', '.webmanifest': 'application/manifest+json', '.svg': 'image/svg+xml' };

function sendFile(req, res, full) {
  fs.stat(full, (err, st) => {
    if (err || !st.isFile()) { res.writeHead(404); return res.end('No encontrado'); }
    const type = MIME[path.extname(full)] || 'application/octet-stream';
    const m = /bytes=(\d*)-(\d*)/.exec(req.headers.range || '');
    if (m) {  // Range: necesario para adelantar/retroceder el audio
      const start = m[1] ? +m[1] : Math.max(0, st.size - +m[2]);
      const end = m[1] && m[2] ? Math.min(+m[2], st.size - 1) : st.size - 1;
      if (start > end || start >= st.size) { res.writeHead(416, { 'Content-Range': `bytes */${st.size}` }); return res.end(); }
      res.writeHead(206, { 'Content-Type': type, 'Accept-Ranges': 'bytes', 'Content-Length': end - start + 1,
                           'Content-Range': `bytes ${start}-${end}/${st.size}` });
      return fs.createReadStream(full, { start, end }).pipe(res);
    }
    res.writeHead(200, { 'Content-Type': type, 'Accept-Ranges': 'bytes', 'Content-Length': st.size });
    fs.createReadStream(full).pipe(res);
  });
}

function handleUpload(req, res, url) {
  const name = (url.searchParams.get('name') || 'cancion').slice(0, 150);
  const ext = path.extname(name).toLowerCase();
  if (!AUDIO_EXT.has(ext)) return json(res, 400, { error: 'Formato no soportado (usa mp3, wav, m4a, flac, ogg…)' });
  if (+req.headers['content-length'] > MAX_UPLOAD) return json(res, 413, { error: 'Archivo muy grande (máx. 150 MB)' });
  const s = addSong({ title: path.basename(name, ext).replace(/[_]+/g, ' '), lang: url.searchParams.get('lang'), folder: url.searchParams.get('folder') });
  jobs.splice(jobs.indexOf(s.lid), 1);            // aún no hay archivo: se encola al terminar la subida
  const dir = path.join(SONGS, s.lid);
  const out = fs.createWriteStream(path.join(dir, 'original' + ext));
  let size = 0, aborted = false;
  const drop = () => { library.delete(s.lid); fs.rmSync(dir, { recursive: true, force: true }); };
  req.on('data', c => {
    size += c.length;
    if (size > MAX_UPLOAD && !aborted) { aborted = true; req.destroy(); out.destroy(); drop(); }
  });
  req.pipe(out);
  out.on('finish', () => {
    if (aborted) return;
    jobs.push(s.lid); broadcast(); runNext();
    json(res, 200, s);
  });
  req.on('error', drop);
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://x');
  const p = url.pathname;

  if (p === '/events') {
    res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', Connection: 'keep-alive' });
    res.write(`data: ${JSON.stringify(state())}\n\n`);
    clients.add(res);
    req.on('close', () => clients.delete(res));
    return;
  }
  if (p === '/api/state') return json(res, 200, state());
  if (p === '/api/config') return json(res, 200, { libraryDir: LIBRARY_DIR });

  if (p === '/api/search') {
    const q = (url.searchParams.get('q') || '').trim().slice(0, 200);
    if (!q) return json(res, 200, []);
    try { return json(res, 200, await search(q)); }
    catch { return json(res, 500, { error: 'No se pudo buscar. Revisa la conexión a internet.' }); }
  }

  if (req.method === 'POST' && p === '/api/upload') return handleUpload(req, res, url);

  if (req.method === 'POST' && p === '/api/import') {
    const b = await readBody(req);
    const urls = (Array.isArray(b.urls) ? b.urls : String(b.urls || '').split(/\s+/)).filter(Boolean);
    if (!urls.length) return json(res, 400, { error: 'Pega al menos un enlace' });
    return json(res, 200, await importLinks(urls, b.lang, b.folder));
  }
  if (req.method === 'POST' && p === '/api/library/retry') {
    const s = library.get((await readBody(req)).lid);
    if (!s || s.status !== 'error') return json(res, 400, { error: 'No se puede reintentar' });
    s.status = 'queued'; s.error = ''; saveMeta(s); jobs.push(s.lid); broadcast(); runNext();
    return json(res, 200, s);
  }
  if (req.method === 'POST' && p === '/api/library/move') {
    const b = await readBody(req);
    const s = library.get(b.lid);
    if (!s) return json(res, 404, { error: 'No encontrada' });
    s.folder = cleanFolder(b.folder); saveMeta(s);
    if (s.status === 'ready') publish(s);
    broadcast();
    return json(res, 200, s);
  }
  // Pone en la fila todas las canciones de una carpeta (opcionalmente en orden aleatorio)
  if (req.method === 'POST' && p === '/api/queue-folder') {
    const b = await readBody(req);
    let songs = [...library.values()].filter(x => (b.folder === '*' || x.folder === b.folder) && x.status !== 'error');
    if (b.shuffle) for (let i = songs.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [songs[i], songs[j]] = [songs[j], songs[i]]; }
    const singer = String(b.singer || 'Fiesta').slice(0, 30);
    songs.forEach(x => queue.push({ qid: nextQid++, kind: 'local', lid: x.lid, title: x.title, thumb: '', singer }));
    broadcast();
    return json(res, 200, { added: songs.length });
  }
  if (req.method === 'POST' && p === '/api/library/delete') {
    const s = library.get((await readBody(req)).lid);
    if (!s) return json(res, 404, { error: 'No encontrada' });
    if (s.status === 'processing' || s.status === 'downloading') return json(res, 409, { error: 'Espera a que termine de procesarse' });
    unpublish(s);
    library.delete(s.lid); jobs.splice(0, jobs.length, ...jobs.filter(x => x !== s.lid));
    queue = queue.filter(q => q.lid !== s.lid);
    fs.rmSync(path.join(SONGS, s.lid), { recursive: true, force: true });
    broadcast();
    return json(res, 200, { ok: true });
  }

  if (req.method === 'POST' && p === '/api/queue') {
    const b = await readBody(req);
    const singer = String(b.singer || 'Alguien').slice(0, 30);
    if (b.lid) {
      const s = library.get(b.lid);
      if (!s) return json(res, 400, { error: 'canción no encontrada' });
      queue.push({ qid: nextQid++, kind: 'local', lid: s.lid, title: s.title, thumb: '', singer });
    } else {
      if (!/^[\w-]{11}$/.test(b.id || '')) return json(res, 400, { error: 'id inválido' });
      queue.push({ qid: nextQid++, kind: 'yt', id: b.id, title: String(b.title || '').slice(0, 150), thumb: String(b.thumb || ''), singer });
    }
    broadcast();
    return json(res, 200, state());
  }
  // Pasar a la siguiente: solo si qid es la que suena (evita dobles saltos si hay varias pantallas)
  if (req.method === 'POST' && p === '/api/next') {
    const b = await readBody(req);
    const cur = state().current;
    if (cur != null && (!b.qid || b.qid === cur)) { queue = queue.filter(s => s.qid !== cur); broadcast(); }
    return json(res, 200, state());
  }
  if (req.method === 'POST' && p === '/api/remove') {
    const b = await readBody(req);
    queue = queue.filter(s => s.qid !== b.qid);
    broadcast();
    return json(res, 200, state());
  }

  // Archivos de canciones propias
  const mm = p.match(/^\/media\/(s[0-9a-f]{10})\/(karaoke\.mp4|instrumental\.mp3|lyrics\.json)$/);
  if (mm) return sendFile(req, res, path.join(SONGS, mm[1], mm[2]));

  // Estáticos
  const file = p === '/' ? 'index.html' : p === '/tv' ? 'tv.html' : p === '/preparar' ? 'preparar.html' : p.slice(1);
  const full = path.join(PUBLIC, path.normalize(file));
  if (!full.startsWith(PUBLIC)) { res.writeHead(403); return res.end(); }
  sendFile(req, res, full);
});

server.listen(PORT, '0.0.0.0', () => {
  const ips = Object.values(os.networkInterfaces()).flat().filter(i => i.family === 'IPv4' && !i.internal).map(i => i.address);
  console.log('\n🎤 Karaoke Party listo\n');
  console.log(`  📁 Biblioteca para la app del teléfono: ${LIBRARY_DIR}\n`);
  ips.forEach(ip => {
    console.log(`  Teléfonos (elegir canciones):  http://${ip}:${PORT}`);
    console.log(`  TV / laptop (reproductor):     http://${ip}:${PORT}/tv`);
    console.log(`  Preparar canciones (YouTube):  http://${ip}:${PORT}/preparar\n`);
  });
  loadLibrary();
});
