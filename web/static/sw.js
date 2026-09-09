// Dockraft Service Worker for PWA
const CACHE_NAME = 'dockraft-v6';
const STATIC_ASSETS = [
  '/static/css/style.css',
  '/static/img/logo.png',
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

  // Network-first for HTML navigation, caching the page so the PWA works offline.
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const copy = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request.url, copy));
          }
          return networkResponse;
        })
        .catch(async () => {
          const cached = await caches.match(event.request.url);
          if (cached) return cached;
          // Fallback to the cached app shell for the root/login pages.
          const shell = await caches.match(url.origin + '/');
          if (shell) return shell;
          return caches.match(event.request);
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

