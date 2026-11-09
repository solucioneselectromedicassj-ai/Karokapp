// Service worker mínimo: permite que el navegador ofrezca "Instalar app". No guarda nada en caché
// (la app necesita el servidor de la laptop para funcionar).
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => {});
