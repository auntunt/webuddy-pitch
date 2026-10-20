/* 称重单采集页的离线外壳:信号差、甚至没网的时候,页面照样能打开、能拍照,照片进手机上的待传箱。
   只缓存页面和样式,不缓存任何接口和图片(台账数据不留在手机上)。页面先走网络,网络不通才用缓存,所以升级后不会卡在旧版。 */
const BASE_PATH = "__WB_BASE_PATH__";
const CACHE_PREFIX = "weighbill-shell:" + BASE_PATH + ":";
const CACHE = CACHE_PREFIX + "v3";
const SHELL = [BASE_PATH + "/static/app.css"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith(CACHE_PREFIX) && k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;                                  // 上传等一律不管
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  const isPage = req.mode === "navigate" && (url.pathname === BASE_PATH + "/" || url.pathname.startsWith(BASE_PATH + "/c/"));
  const isShell = url.pathname.startsWith(BASE_PATH + "/static/") && !url.pathname.endsWith("sw.js");
  if (!isPage && !isShell) return;                                   // 接口、图片、台账页:不缓存
  e.respondWith(
    fetch(req).then(res => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(req, copy)); }
      return res;
    }).catch(() => caches.match(req).then(hit => hit || caches.match(BASE_PATH + "/static/app.css").then(() =>
      new Response("<meta charset=utf-8><p style='font:16px sans-serif;padding:20px'>没有网络,而且这台手机还没打开过采集页。有信号时先打开一次,以后没网也能拍。</p>",
                   {headers: {"Content-Type": "text/html; charset=utf-8"}}))))
  );
});
