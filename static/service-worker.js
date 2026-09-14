const CACHE_NAME = 'novapay-v2';
const ASSETS = [
  '/',
  '/static/css/main.css',
  '/static/css/animations.css',
  '/static/css/auth.css',
  '/static/css/admin.css',
  '/static/js/main.js',
  '/static/js/admin.js',
  '/static/js/animations.js',
  '/static/js/monitoring.js',
  '/static/assets/logo.svg',
  '/static/assets/card-chip.svg'
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS);
    })
  );
});

self.addEventListener('fetch', (e) => {
  e.respondWith(
    caches.match(e.request).then((cachedResponse) => {
      return cachedResponse || fetch(e.request);
    })
  );
});
