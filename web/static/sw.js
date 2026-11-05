// Dockraft Service Worker for PWA
const CACHE_NAME = 'dockraft-v10';
const STATIC_ASSETS = [
  '/static/css/style.css',
  '/static/img/dockraft_logo.png',
  '/static/js/i18n.js'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.warn('[SW] Cache prefetch error:', err);
      });
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Never intercept or cache API requests, WebSockets or non-GET actions
  if (
    url.pathname.startsWith('/api') ||
    url.pathname.startsWith('/ws') ||
    event.request.method !== 'GET'
  ) {
    return;
  }

  // Network-only for authenticated HTML navigation (never cache SSR state or CSP nonces).
  if (event.request.mode === 'navigate') {
    if (url.pathname === '/logout') {
      caches.open(CACHE_NAME).then((cache) => {
        cache.delete(url.origin + '/');
      });
    }
    event.respondWith(
      fetch(event.request).catch(async () => {
        if (url.pathname.startsWith('/login')) {
          const cachedLogin = await caches.match(event.request.url);
          if (cachedLogin) return cachedLogin;
        }
        return new Response(
          '<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Dockraft — Sin conexión</title></head><body style="background:#0d1117;color:#e6edf3;font-family:sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;text-align:center;"><div><h2>Sin conexión con el servidor Dockraft</h2><p style="color:#8b949e;">Comprueba tu conexión de red e inténtalo de nuevo.</p></div></body></html>',
          { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
        );
      })
    );
    return;
  }

  // Network-first for JavaScript files and versioned assets to guarantee fresh UI logic
  if (url.pathname.endsWith('.js') || url.search) {
    event.respondWith(
      fetch(event.request).then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200) {
          const copy = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        }
        return networkResponse;
      }).catch(() => caches.match(event.request))
    );
    return;
  }

  // Stale-while-revalidate for images, icons, and non-versioned static assets
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then((cachedResponse) => {
        const fetchPromise = fetch(event.request).then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const copy = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
          }
          return networkResponse;
        }).catch(() => cachedResponse);
        return cachedResponse || fetchPromise;
      })
    );
  }
});

