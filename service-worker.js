/* Lopes Tracker offline shell. Notifications are delivered separately by Telegram. */
const SHELL_CACHE = 'lopes-tracker-shell-v2';
const DATA_CACHE = 'lopes-tracker-data-v1';
const ASSETS = [
  './', './index.html', './assets/app.js', './assets/styles.css',
  './manifest.webmanifest', './icons/icon-192.png',
  './icons/icon-512.png', './icons/apple-touch-icon.png'
];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(SHELL_CACHE).then(cache => cache.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(Promise.all([
    caches.keys().then(keys => Promise.all(keys.filter(key =>
      key.startsWith('lopes-tracker-') && key !== SHELL_CACHE && key !== DATA_CACHE
    ).map(key => caches.delete(key)))),
    self.clients.claim()
  ]));
});
self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.endsWith('/data/results.json') || url.pathname.endsWith('/players.json')) {
    // Always prefer live stats; cache only one canonical URL to avoid accumulating ?t= timestamps.
    const key = new Request(url.origin + url.pathname);
    event.respondWith(fetch(request).then(response => {
      if (response.ok) {
        const copy = response.clone();
        event.waitUntil(caches.open(DATA_CACHE).then(cache => cache.put(key, copy)));
      }
      return response;
    }).catch(async () => await caches.match(key) || Response.error()));
    return;
  }
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).catch(async () => await caches.match('./index.html') || Response.error()));
    return;
  }
  event.respondWith(caches.match(request).then(cached => cached || fetch(request)));
});
