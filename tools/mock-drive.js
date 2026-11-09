// Servidor de pruebas: imita la API de Google Drive v3 (listar carpetas, descargar con Range) y sirve la app de player/.
// Uso: node tools/mock-drive.js <carpeta-biblioteca> [puerto]     (clave de prueba: TESTKEY)
const http = require('http'), fs = require('fs'), path = require('path');
const LIB = path.resolve(process.argv[2] || 'pc/biblioteca'), PORT = +process.argv[3] || 3200, PLAYER = path.join(__dirname, '..', 'player');
const enc = p => Buffer.from(p).toString('hex'), dec = h => path.join(LIB, Buffer.from(h, 'hex').toString());
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.png': 'image/png', '.svg': 'image/svg+xml', '.webmanifest': 'application/manifest+json' };
const send = (res, code, obj) => { res.writeHead(code, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }); res.end(JSON.stringify(obj)); };

http.createServer((req, res) => {
  const u = new URL(req.url, 'http://x'), p = u.pathname;
  if (p.startsWith('/drive/v3/files')) {
    if (u.searchParams.get('key') !== 'TESTKEY') return send(res, 400, { error: 'API key not valid' });
    const m = p.match(/^\/drive\/v3\/files\/(\w+)$/);
    if (m && u.searchParams.get('alt') === 'media') {              // descarga con Range
      const f = dec(m[1]); if (!fs.existsSync(f)) return send(res, 404, {});
      const size = fs.statSync(f).size, r = /bytes=(\d*)-(\d*)/.exec(req.headers.range || '');
      const h = { 'Content-Type': 'video/mp4', 'Accept-Ranges': 'bytes', 'Access-Control-Allow-Origin': '*' };
      if (r) { const a = +r[1] || 0, b = r[2] ? +r[2] : size - 1; res.writeHead(206, { ...h, 'Content-Range': `bytes ${a}-${b}/${size}`, 'Content-Length': b - a + 1 }); return fs.createReadStream(f, { start: a, end: b }).pipe(res); }
      res.writeHead(200, { ...h, 'Content-Length': size }); return fs.createReadStream(f).pipe(res);
    }
    const parent = (u.searchParams.get('q') || '').match(/'(\w+)' in parents/);   // listar
    if (!parent) return send(res, 400, {});
    if (parent[1] === 'NOPE_FOLDER_ID_0001') return send(res, 404, {});
    const dir = parent[1] === 'ROOTFOLDER_ID_0001' ? LIB : dec(parent[1]);
    if (!fs.existsSync(dir)) return send(res, 404, {});
    const rel = parent[1] === 'ROOTFOLDER_ID_0001' ? '' : Buffer.from(parent[1], 'hex').toString();
    const files = fs.readdirSync(dir, { withFileTypes: true }).map(d => ({ id: enc(path.join(rel, d.name)), name: d.name,
      mimeType: d.isDirectory() ? 'application/vnd.google-apps.folder' : 'video/mp4' }));
    return send(res, 200, { files });
  }
  const f = path.join(PLAYER, p === '/' ? 'index.html' : p.slice(1));
  fs.readFile(f, (e, d) => { if (e) { res.writeHead(404); return res.end(); } res.writeHead(200, { 'Content-Type': MIME[path.extname(f)] || 'application/octet-stream' }); res.end(d); });
}).listen(PORT, () => console.log('mock drive en http://localhost:' + PORT));
