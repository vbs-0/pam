/* PAM service worker: the app opens with no network, and the last data you looked at stays readable.
   - app files: cache-first (they are fingerprinted, a new build gets new names)
   - page navigations: network, falling back to the cached shell
   - GET /api/v1/me/*, /categories, /auth/me: network first, last good answer kept for offline
   Everything cached is wiped on sign out (message "clear"). Writes are never cached here; the page queues them. */
const SHELL = "pam-shell-v1";
const DATA = "pam-data-v1";

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(["/", "/manifest.webmanifest", "/icon-192.png", "/favicon.png"])).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((ks) => Promise.all(ks.filter((k) => ![SHELL, DATA].includes(k)).map((k) => caches.delete(k)))).then(() => self.clients.claim()),
  );
});

self.addEventListener("message", (e) => {
  if (e.data === "clear") e.waitUntil(caches.delete(DATA));
});

const isData = (u) => u.pathname.startsWith("/api/v1/me/") || u.pathname === "/api/v1/categories" || u.pathname === "/api/v1/auth/me";

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;

  if (isData(url)) {
    e.respondWith(
      fetch(req).then((res) => {
        if (res.ok) { const copy = res.clone(); caches.open(DATA).then((c) => c.put(req, copy)); }
        return res;
      }).catch(() => caches.open(DATA).then((c) => c.match(req)).then((hit) => hit || new Response(JSON.stringify({ detail: "You are offline and this has not been opened before." }), { status: 503, headers: { "Content-Type": "application/json" } }))),
    );
    return;
  }
  if (url.pathname.startsWith("/api/")) return;

  if (req.mode === "navigate") {
    e.respondWith(fetch(req).catch(() => caches.match("/")));
    return;
  }
  if (url.pathname.startsWith("/assets/") || /\.(png|svg|webmanifest|woff2?)$/.test(url.pathname)) {
    e.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((res) => {
        if (res.ok) { const copy = res.clone(); caches.open(SHELL).then((c) => c.put(req, copy)); }
        return res;
      })),
    );
  }
});
