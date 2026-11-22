import json
import os
import socket
import threading
import urllib.request
import webview

APP_NAME = "ytm-alice remote"
CONFIG_DIR = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "ytm-alice-remote")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
DEFAULT_PORT = 24721


def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(url):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"server_url": url}, f, ensure_ascii=False)


def normalize(raw):
    if raw is None:
        return None
    value = raw.strip()
    if not value or " " in value:
        return None
    if "://" not in value:
        value = "http://" + value
    try:
        # minimal parse
        from urllib.parse import urlparse
        u = urlparse(value)
    except Exception:
        return None
    scheme = (u.scheme or "").lower()
    host = u.hostname
    if scheme not in ("http", "https") or not host:
        return None
    port = u.port
    result = f"{scheme}://{host}"
    if port is not None:
        result += f":{port}"
    elif scheme == "http":
        result += f":{DEFAULT_PORT}"
    path = u.path or ""
    if path and path != "/":
        result += path
    while result.endswith("/"):
        result = result[:-1]
    return result


def check(base):
    try:
        with urllib.request.urlopen(base + "/api/info", timeout=4) as r:
            if r.status != 200:
                return None
            body = r.read(4096).decode("utf-8", "replace")
            if '"version"' not in body:
                return None
            # extract version
            import re
            m = re.search(r'"version"\s*:\s*"([^"]*)"', body)
            v = m.group(1) if m else ""
            return v if v else "РІРµСЂСЃРёСЏ РЅРµРёР·РІРµСЃС‚РЅР°"
    except Exception:
        return None


def fetch_panel_html(url):
    """Fetch the panel HTML and force UTF-8 decoding; inject a <base> tag so
    relative URLs and fetch() resolve against the station."""
    try:
        req = urllib.request.Request(url, headers={"Accept": "text/html"})
        with urllib.request.urlopen(req, timeout=8) as r:
            raw = r.read()
        html = raw.decode("utf-8")
        base_tag = '<base href="' + url.rstrip("/") + '/">'
        if "<head>" in html:
            html = html.replace("<head>", "<head>" + base_tag, 1)
        elif "<head " in html:
            import re
            html = re.sub(r"(<head[^>]*>)", r"\1" + base_tag, html, count=1)
        else:
            html = base_tag + html
        return html
    except Exception as e:
        print("fetch_panel_html error:", e)
        return None

def discover():
    targets = ["http://alice.lan:24721", "http://alice.local:24721"]
    seen = set(targets)
    # local subnets
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
    except Exception:
        local_ip = None
    # enumerate all IPv4 addresses of host
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            addr = info[4][0]
            if "." in addr and not addr.startswith("127."):
                ips.add(addr)
    except Exception:
        pass
    if local_ip and not local_ip.startswith("127."):
        ips.add(local_ip)
    for ip in ips:
        parts = ip.split(".")
        if len(parts) != 4:
            continue
        prefix = ".".join(parts[:3]) + "."
        own = int(parts[3]) if parts[3].isdigit() else -1
        for last in range(1, 255):
            if last == own:
                continue
            url = f"http://{prefix}{last}:24721"
            if url not in seen:
                seen.add(url)
                targets.append(url)
    # probe in parallel
    found = []
    lock = threading.Lock()

    def probe(u):
        nonlocal found
        if check(u) is not None:
            with lock:
                found.append(u)

    # limit concurrency
    sem = threading.Semaphore(32)
    threads = []

    def worker(u):
        with sem:
            probe(u)

    for u in targets:
        t = threading.Thread(target=worker, args=(u,), daemon=True)
        threads.append(t)
        t.start()
    for t in threads:
        t.join(timeout=1.5)
    return found


SETUP_HTML = r"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ytm-alice</title>
<style>
  :root { --bg:#0B0B0F; --card:#191920; --stroke:#26262F; --accent:#FF574A; --text:#F4F4F6; --muted:#9A9AA6; --dim:#6E6E7A; }
  * { box-sizing:border-box; }
  body { margin:0; font-family: -apple-system, Segoe UI, Roboto, sans-serif; background:linear-gradient(180deg,#15151C,#0B0B0F); color:var(--text); min-height:100vh; display:flex; align-items:center; justify-content:center; padding:24px; }
  .wrap { width:100%; max-width:440px; }
  .logo { width:84px; height:84px; margin:0 auto 14px; display:block; }
  h1 { text-align:center; font-size:28px; margin:0; }
  .sub { text-align:center; color:var(--muted); margin:2px 0 24px; }
  .card { background:var(--card); border:1px solid var(--stroke); border-radius:22px; padding:20px; }
  label { display:block; font-size:11px; letter-spacing:.08em; color:var(--muted); text-transform:uppercase; margin-bottom:10px; }
  input { width:100%; padding:14px; font-size:16px; font-family:monospace; color:var(--text); background:#111116; border:1px solid #2B2B35; border-radius:12px; outline:none; }
  input:focus { border-color:var(--accent); }
  .help { font-size:12px; color:var(--dim); margin:8px 0 18px; line-height:1.4; }
  button { width:100%; padding:14px; font-size:16px; font-weight:700; color:#fff; background:var(--accent); border:none; border-radius:14px; cursor:pointer; margin-top:8px; }
  button.ghost { background:transparent; border:1px solid var(--stroke); font-weight:500; }
  button:disabled { opacity:.6; cursor:wait; }
  .status { margin-top:16px; font-size:13px; color:var(--muted); min-height:18px; }
  .spinner { display:inline-block; width:14px; height:14px; border:2px solid #333; border-top-color:var(--accent); border-radius:50%; animation:spin .8s linear infinite; vertical-align:middle; margin-right:8px; }
  @keyframes spin { to { transform:rotate(360deg); } }
  .footer { font-size:12px; color:var(--dim); text-align:center; margin-top:22px; line-height:1.5; }
</style>
</head>
<body>
<div class="wrap">
  <svg class="logo" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M20 5C15.8 5 9.6 12.5 5.7 20.1C2.2 27 4.2 32.2 11.7 34.2C16.7 35.5 23.3 35.5 28.3 34.2C35.8 32.2 37.8 27 34.3 20.1C30.4 12.5 24.2 5 20 5Z" stroke="#ff574a" stroke-width="3.2" stroke-linejoin="round"/>
  </svg>
  <h1>ytm-alice</h1>
  <div class="sub">Пульт для Яндекс Станции</div>
  <div class="card">
    <label>Адрес Станции</label>
    <input id="addr" type="text" placeholder="192.168.1.50:24721" autocomplete="off">
    <div class="help">IP-адрес колонки, имя alice.lan или полный адрес панели</div>
    <button id="connect" onclick="doConnect()">Подключиться</button>
    <button id="find" class="ghost" onclick="doFind()">Найти Станцию в сети</button>
    <div class="status" id="status"></div>
  </div>
  <div class="footer">Музыка играет на колонке. Приложение открывает веб-панель ytm-alice: поиск, очередь, лайки, плейлисты и настройки.</div>
</div>
<script>
  const status = document.getElementById('status');
  const addr = document.getElementById('addr');
  const connectBtn = document.getElementById('connect');
  const findBtn = document.getElementById('find');

  function doConnect() {
    connectBtn.disabled = true; findBtn.disabled = true;
    status.innerHTML = '<span class="spinner"></span>Проверяем подключение…';
    window.pywebview.api.connect(addr.value);
  }
  function onConnectResult(r) {
    connectBtn.disabled = false; findBtn.disabled = false;
    if (r.ok) { status.textContent = 'Подключено: ytm-alice ' + (r.version || ''); if (r.url) addr.value = r.url.replace(/^https?:\/\//,''); }
    else { status.textContent = r.message || 'Ошибка'; }
  }
  function doFind() {
    connectBtn.disabled = true; findBtn.disabled = true;
    status.innerHTML = '<span class="spinner"></span>Ищем Станцию в локальной сети… (до 15 сек)';
    window.pywebview.api.find();
  }
  function onFindResult(r) {
    connectBtn.disabled = false; findBtn.disabled = false;
    if (r.ok) { status.textContent = 'Найдено: ' + (r.found || 1) + '. Подключаемся…'; if (r.url) addr.value = r.url.replace(/^https?:\/\//,''); }
    else { status.textContent = r.message || 'Не найдено'; }
  }
  addr.addEventListener('keydown', (e) => { if (e.key === 'Enter') doConnect(); });

  // WebView2 may only be navigated from the UI thread. The Python side checks
  // the station in a background thread and defers navigation to this poll.
  setInterval(() => {
    try {
      if (window.pywebview && window.pywebview.api && window.pywebview.api.poll) {
        window.pywebview.api.poll();
      }
    } catch (e) {}
  }, 250);
</script>
</body>
</html>
"""


class Api:
    def __init__(self, window):
        self.window = window
        self._pending_nav = None

    def get_saved(self):
        return load_config().get("server_url", "")

    def _schedule_navigation(self, url):
        """Defer navigation to the UI thread (WebView2 COM is thread-bound)."""
        self._pending_nav = url

    def poll(self):
        """Called by the setup page on the UI thread.

        The network check runs in a background thread. Calling window.load_url()
        from that thread makes WebView2 hang, so the actual navigation happens
        here instead. Loading from the station URL also keeps the correct Origin
        for panel commands; the panel is served with charset=utf-8.
        """
        url = self._pending_nav
        if not url:
            return {"navigated": False}
        self._pending_nav = None
        try:
            self.window.load_url(url)
        except Exception as e:
            print("load_url error:", e)
        return {"navigated": True}

    def connect(self, address):
        def worker():
            url = normalize(address)
            if not url:
                self.window.evaluate_js("onConnectResult(" + __import__("json").dumps({"ok": False, "message": "Неверный адрес. Пример: 192.168.1.50:24721"}, ensure_ascii=False) + ")")
                return
            version = check(url)
            if version is None:
                self.window.evaluate_js("onConnectResult(" + __import__("json").dumps({"ok": False, "message": "Не удалось подключиться. Проверьте адрес и сеть."}, ensure_ascii=False) + ")")
                return
            save_config(url)
            self._schedule_navigation(url)
            self.window.evaluate_js("onConnectResult(" + __import__("json").dumps({"ok": True, "version": version, "url": url}, ensure_ascii=False) + ")")

        __import__("threading").Thread(target=worker, daemon=True).start()
        return {"ok": True, "pending": True}

    def find(self):
        def worker():
            urls = discover()
            if not urls:
                self.window.evaluate_js("onFindResult(" + __import__("json").dumps({"ok": False, "message": "Станция не найдена. Введите адрес вручную."}, ensure_ascii=False) + ")")
                return
            url = normalize(urls[0])
            if not url:
                self.window.evaluate_js("onFindResult(" + __import__("json").dumps({"ok": False, "message": "Не удалось подключиться."}, ensure_ascii=False) + ")")
                return
            version = check(url)
            if version is None:
                self.window.evaluate_js("onFindResult(" + __import__("json").dumps({"ok": False, "message": "Не удалось подключиться."}, ensure_ascii=False) + ")")
                return
            save_config(url)
            self._schedule_navigation(url)
            self.window.evaluate_js("onFindResult(" + __import__("json").dumps({"ok": True, "version": version, "url": url, "found": len(urls)}, ensure_ascii=False) + ")")

        __import__("threading").Thread(target=worker, daemon=True).start()
        return {"ok": True, "pending": True}

    def change_address(self):
        self.window.load_html(SETUP_HTML)
        return True


def main():
    saved = load_config().get("server_url")
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
    if not os.path.isfile(icon_path):
        icon_path = None
    api = Api(None)
    window = webview.create_window(
        APP_NAME,
        url=saved if saved else None,
        html=None if saved else SETUP_HTML,
        width=1100,
        height=760,
        min_size=(720, 520),
        text_select=True,
        js_api=api,
    )
    api.window = window

    menu = [
        webview.Menu("File", [
            webview.menu.MenuAction("Change station address", api.change_address),
            webview.menu.MenuAction("Exit", lambda: window.destroy()),
        ]),
        webview.Menu("Help", [
            webview.menu.MenuAction("About", lambda: window.evaluate_js(
                "alert('ytm-alice remote 1.0.0\\n\\n\u041f\u0443\u043b\u044c\u0442 \u0434\u043b\u044f ytm-alice.\\n\u041c\u0443\u0437\u044b\u043a\u0430 \u0438\u0433\u0440\u0430\u0435\u0442 \u043d\u0430 \u043a\u043e\u043b\u043e\u043d\u043a\u0435.');"
            )),
        ]),
    ]
    webview.start(debug=False, menu=menu)


def write_crash_log(text):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(os.path.join(CONFIG_DIR, "crash.log"), "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        write_crash_log(traceback.format_exc())
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                "Ошибка запуска. Подробности в %APPDATA%\\ytm-alice-remote\\crash.log",
                "ytm-alice remote",
                0x10,
            )
        except Exception:
            pass
        raise

