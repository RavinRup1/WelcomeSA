/* Welcome SA service worker - offline shell, fresh data when online */
const CACHE = "welcome-sa-v1";
const SHELL = ["./", "index.html", "manifest.webmanifest"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (url.origin !== location.origin) return;
  if (url.pathname.includes("/data/")) {
    e.respondWith(fetch(e.request).then(r => {
      const c = r.clone(); caches.open(CACHE).then(cc => cc.put(e.request, c)); return r;
    }).catch(() => caches.match(e.request)));
    return;
  }
  e.respondWith(caches.match(e.request).then(hit => {
    const net = fetch(e.request).then(r => {
      if (r.ok) { const c = r.clone(); caches.open(CACHE).then(cc => cc.put(e.request, c)); }
      return r;
    }).catch(() => hit);
    return hit || net;
  }));
});
