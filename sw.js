// Service worker mínimo — Garmin-plus PWA
// Estrategia: red-first con caché de respaldo (app 100% local, datos frescos importan).
const CACHE = 'garmin-plus-v6';
const CORE = ['./', './index.html', './manifest.json', './icon-192.png', './icon-512.png', './apple-touch-icon.png'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(CORE)));
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET') return;
  // Datos y APIs de mapas: siempre red (frescura), sin caché agresiva.
  if (url.pathname.endsWith('data.json') || url.pathname.endsWith('coach_insights.json')
      || url.hostname.includes('openstreetmap') || url.hostname.includes('unpkg')
      || url.hostname.includes('jsdelivr')) {
    e.respondWith(
      fetch(e.request).then((r) => {
        const clone = r.clone();
        caches.open(CACHE).then((c) => c.put(e.request, clone));
        return r;
      }).catch(() => caches.match(e.request))
    );
    return;
  }
  // Shell: red-first con fallback caché (funciona offline en el iPhone).
  e.respondWith(
    fetch(e.request).then((r) => {
      const clone = r.clone();
      caches.open(CACHE).then((c) => c.put(e.request, clone));
      return r;
    }).catch(() => caches.match(e.request).then((hit) => hit || caches.match('./index.html')))
  );
});
