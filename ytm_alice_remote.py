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
        with open(CONFIG_PATH, encoding="utf-8") as f:
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
            return v if v else "версия неизвестна"
    except Exception:
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

  async function doConnect() {
    connectBtn.disabled = true; findBtn.disabled = true;
    status.innerHTML = '<span class="spinner"></span>Проверяем подключение…';
    try {
      const r = await window.pywebview.api.connect(addr.value);
      if (r.ok) { status.textContent = 'Подключено: ytm-alice ' + (r.version || ''); }
      else { status.textContent = r.message; }
    } catch (e) { status.textContent = 'Ошибка: ' + e; }
    connectBtn.disabled = false; findBtn.disabled = false;
  }
  async function doFind() {
    connectBtn.disabled = true; findBtn.disabled = true;
    status.innerHTML = '<span class="spinner"></span>Ищем Станцию в локальной сети…';
    try {
      const r = await window.pywebview.api.find();
      if (r.ok) { status.textContent = 'Найдено, подключаемся…'; addr.value = r.url.replace(/^https?:\/\//,''); }
      else { status.textContent = r.message; }
    } catch (e) { status.textContent = 'Ошибка: ' + e; }
    connectBtn.disabled = false; findBtn.disabled = false;
  }
  window.addEventListener('pywebviewready', async () => {
    const saved = await window.pywebview.api.get_saved();
    if (saved) addr.value = saved.replace(/^https?:\/\//,'');
  });
  addr.addEventListener('keydown', (e) => { if (e.key === 'Enter') doConnect(); });
</script>
</body>
</html>
"""


class Api:
    def __init__(self, window):
        self.window = window

    def get_saved(self):
        return load_config().get("server_url", "")

    def connect(self, address):
        url = normalize(address)
        if not url:
            return {"ok": False, "message": "Неверный адрес. Пример: 192.168.1.50:24721"}
        version = check(url)
        if version is None:
            return {"ok": False, "message": "Не удалось подключиться. Проверьте адрес и сеть."}
        save_config(url)
        self.window.load_url(url)
        return {"ok": True, "version": version, "url": url}

    def find(self):
        urls = discover()
        if not urls:
            return {"ok": False, "message": "Станция не найдена. Введите адрес вручную."}
        url = normalize(urls[0])
        if not url:
            return {"ok": False, "message": "Не удалось подключиться."}
        version = check(url)
        if version is None:
            return {"ok": False, "message": "Не удалось подключиться."}
        save_config(url)
        self.window.load_url(url)
        return {"ok": True, "version": version, "url": url, "found": len(urls)}

    def change_address(self):
        self.window.load_html(SETUP_HTML)
        return True


def main():
    saved = load_config().get("server_url")
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
    if not os.path.isfile(icon_path):
        icon_path = None
    window = webview.create_window(
        APP_NAME,
        width=1100,
        height=760,
        min_size=(720, 520),
        text_select=True,
    )
    api = Api(window)
    window.js_api = api
    if saved:
        window.load_url(saved)
    else:
        window.load_html(SETUP_HTML)

    menu = [
        webview.Menu("\u0424\u0430\u0439\u043b", [
            webview.MenuItem("\u0421\u043c\u0435\u043d\u0438\u0442\u044c \u0430\u0434\u0440\u0435\u0441 \u0421\u0442\u0430\u043d\u0446\u0438\u0438", api.change_address),
            webview.MenuItem("\u0412\u044b\u0445\u043e\u0434", lambda: window.destroy()),
        ]),
        webview.Menu("\u0421\u043f\u0440\u0430\u0432\u043a\u0430", [
            webview.MenuItem("\u041e \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0438", lambda: window.evaluate_js(
                "alert('ytm-alice remote 1.0.0\\n\\n\u041f\u0443\u043b\u044c\u0442 \u0434\u043b\u044f ytm-alice.\\n\u041c\u0443\u0437\u044b\u043a\u0430 \u0438\u0433\u0440\u0430\u0435\u0442 \u043d\u0430 \u043a\u043e\u043b\u043e\u043d\u043a\u0435.');"
            )),
        ]),
    ]
    webview.start(debug=False, menu=menu, icon=icon_path)


if __name__ == "__main__":
    main()
