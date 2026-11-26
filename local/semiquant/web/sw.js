/* Service worker for the published dashboard (installable app).
 * App files (versioned with ?v=build): cache first, so the app opens instantly.
 * Pages and data/*.json: network first, so you always get the newest published numbers,
 * falling back to the last copy when offline. Never touches /api/ (local edition). */
const BUILD = '__BUILD__';
const SHELL = 'sq-shell-' + BUILD;
const DATA = 'sq-data';

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) {
      if (key.startsWith('sq-shell-') && key !== SHELL) await caches.delete(key);
    }
    await self.clients.claim();
  })());
});

function withoutQuery(request) {
  const url = new URL(request.url);
  url.search = '';
  return url.toString();
}

async function networkFirst(request, cacheName) {
  const key = withoutQuery(request);
  try {
    const response = await fetch(request);
    if (response.ok) (await caches.open(cacheName)).put(key, response.clone());
    return response;
  } catch (err) {
    const hit = await caches.match(key);
    if (hit) return hit;
    throw err;
  }
}

async function cacheFirst(request) {
  const hit = await caches.match(request);
  if (hit) return hit;
  const response = await fetch(request);
  if (response.ok) (await caches.open(SHELL)).put(request, response.clone());
  return response;
}

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || url.pathname.includes('/api/')) return;
  if (request.mode === 'navigate') {
    event.respondWith(networkFirst(request, SHELL));
  } else if (url.pathname.includes('/data/')) {
    event.respondWith(networkFirst(request, DATA));
  } else {
    event.respondWith(cacheFirst(request));
  }
});
