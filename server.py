#!/usr/bin/env python3
"""vj-remote bridge: serves the phone UI over HTTP and relays controls to Resolume as OSC.

Run:  python server.py [--http-port 8081] [--osc-host 127.0.0.1] [--osc-port 7000] [--no-browser]
Env:  VJREMOTE_HTTP_PORT, VJREMOTE_OSC_HOST, VJREMOTE_OSC_PORT

Double-clickable too: `pyinstaller vj-remote.spec` builds a one-file
vj-remote.exe — the console window it opens IS the "it's running" indicator,
so it stays visible (console=True) and opens the setup page on launch.

The phone opens http://<this-machine-lan-ip>:8081 (scan the QR on /setup).
The page sends JSON over WebSocket /ctl:
    {"address": "/composition/layers/1/video/opacity", "args": [{"type": "f", "value": 0.7}]}
and this bridge forwards it as OSC/UDP to Resolume (default 127.0.0.1:7000).
"""
import argparse
import base64
import io
import json
import mimetypes
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent

def resource_path(rel: str) -> Path:
    """Resolve a bundled resource.

    When frozen by PyInstaller, data files (the web/ UI) live under
    sys._MEIPASS; otherwise they sit next to this script.
    """
    base = getattr(sys, "_MEIPASS", HERE)
    return Path(base) / rel

WEB_DIR = resource_path("web")

# ---------------------------------------------------------------- config

def get_args():
    p = argparse.ArgumentParser(description="vj-remote: phone OSC controller bridge for Resolume")
    p.add_argument("--http-port", type=int, default=int(os.environ.get("VJREMOTE_HTTP_PORT", 8081)))
    p.add_argument("--osc-host", default=os.environ.get("VJREMOTE_OSC_HOST", "127.0.0.1"))
    p.add_argument("--osc-port", type=int, default=int(os.environ.get("VJREMOTE_OSC_PORT", 7000)))
    p.add_argument("--no-browser", action="store_true",
                   help="don't auto-open the setup page in a browser on launch")
    return p.parse_args()

ARGS = get_args()

# ---------------------------------------------------------------- state

stats = {
    "started_at": time.time(),
    "sends": 0,
    "errors": 0,
    "last_error": None,
    "udp_socket_ok": False,
    "udp_error": None,
}
ws_clients = set()
stats_lock = threading.Lock()

# ---------------------------------------------------------------- OSC

def make_osc_client():
    from pythonosc.udp_client import SimpleUDPClient
    client = SimpleUDPClient(ARGS.osc_host, ARGS.osc_port)
    return client

_osc_client = None

def osc_client():
    global _osc_client
    if _osc_client is None:
        _osc_client = make_osc_client()
        with stats_lock:
            try:
                # UDP can't confirm the far end, but we can confirm we have a working socket.
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.close()
                stats["udp_socket_ok"] = True
            except OSError as e:
                stats["udp_socket_ok"] = False
                stats["udp_error"] = str(e)
    return _osc_client

def coerce_args(args):
    """Validate + convert WS arg dicts to plain python values. Pure; unit-testable.

    [{"type":"i","value":1}] -> [1]   (int)
    [{"type":"f","value":0.7}] -> [0.7] (float)
    [{"type":"s","value":"x"}] -> ["x"]  (string)
    """
    values = []
    for a in args or []:
        t, v = a.get("type"), a.get("value")
        if t == "i":
            values.append(int(v))
        elif t == "f":
            values.append(float(v))
        elif t == "s":
            values.append(str(v))
        else:
            raise ValueError(f"bad arg type: {t!r} (want 'i', 'f' or 's')")
    return values

def send_osc(address, args):
    if not isinstance(address, str) or not address.startswith("/"):
        raise ValueError(f"bad OSC address: {address!r}")
    values = coerce_args(args)
    osc_client().send_message(address, values)
    with stats_lock:
        stats["sends"] += 1

# ---------------------------------------------------------------- helpers

def get_lan_ip():
    """Best-effort LAN IP. The UDP 'connect' sends no traffic, it just resolves the route."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()

def make_qr_data_uri(url):
    """QR as an inline SVG data URI (crisp at any size, no Pillow needed)."""
    try:
        import qrcode
        import qrcode.image.svg
    except ImportError:
        return None
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(image_factory=qrcode.image.svg.SvgImage)
    buf = io.BytesIO()
    img.save(buf)
    return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

def status_payload():
    with stats_lock:
        s = dict(stats)
    return {
        "ok": True,
        "service": "vj-remote",
        "http_port": ARGS.http_port,
        "osc_host": ARGS.osc_host,
        "osc_port": ARGS.osc_port,
        "udp_socket_ok": s["udp_socket_ok"],
        "udp_error": s["udp_error"],
        "sends": s["sends"],
        "errors": s["errors"],
        "last_error": s["last_error"],
        "ws_clients": len(ws_clients),
        "uptime_s": round(time.time() - s["started_at"], 1),
        "note": "UDP is fire-and-forget: this confirms the bridge can send, not that "
                "Resolume is listening. In Resolume: Preferences > OSC > enable input "
                "(port 7000), then watch the 'last messages' fold-out while you tap a control.",
    }

def info_payload():
    lan_ip = get_lan_ip()
    return {
        "ok": True,
        "lan_ip": lan_ip,
        "url": f"http://{lan_ip}:{ARGS.http_port}/",
        "osc_host": ARGS.osc_host,
        "osc_port": ARGS.osc_port,
    }

# ---------------------------------------------------------------- HTTP (via websockets process_request)

def _resp(status, body: bytes, ctype="text/plain; charset=utf-8"):
    from websockets.datastructures import Headers
    from websockets.http11 import Response
    reason = {200: "OK", 404: "Not Found", 500: "Internal Server Error"}.get(status, "OK")
    return Response(status, reason, Headers([("Content-Type", ctype),
                                             ("Cache-Control", "no-store")]), body)

def render_setup_page():
    info = info_payload()
    qr = make_qr_data_uri(info["url"])
    tpl = (WEB_DIR / "setup.html").read_text(encoding="utf-8")
    if qr:
        qr_html = f'<img class="qr" src="{qr}" alt="QR code to open the controller">'
    else:
        qr_html = ('<p class="warn">QR library not installed (pip install qrcode). '
                   'Type the address below into your phone browser instead.</p>')
    return (tpl.replace("{{LAN_IP}}", info["lan_ip"])
               .replace("{{URL}}", info["url"])
               .replace("{{QR}}", qr_html)
               .replace("{{OSC_HOST}}", str(ARGS.osc_host))
               .replace("{{OSC_PORT}}", str(ARGS.osc_port)))

def process_request(connection, request):
    path = request.path.split("?", 1)[0]
    try:
        if path == "/api/status":
            return _resp(200, json.dumps(status_payload()).encode(), "application/json")
        if path == "/api/info":
            return _resp(200, json.dumps(info_payload()).encode(), "application/json")
        if path == "/setup":
            return _resp(200, render_setup_page().encode("utf-8"), "text/html; charset=utf-8")
        if path == "/ctl":
            return None  # let the WebSocket handshake through
        rel = path.lstrip("/") or "index.html"
        target = (WEB_DIR / rel).resolve()
        if WEB_DIR.resolve() not in target.parents and target != (WEB_DIR / "index.html").resolve():
            return _resp(404, b"not found")
        if not target.is_file():
            return _resp(404, b"not found")
        ctype, _ = mimetypes.guess_type(str(target))
        return _resp(200, target.read_bytes(), ctype or "application/octet-stream")
    except Exception as e:  # never break the server on a bad request
        return _resp(500, f"error: {e}".encode())

# ---------------------------------------------------------------- WebSocket /ctl

async def ctl_handler(conn):
    ws_clients.add(conn)
    try:
        async for raw in conn:
            try:
                msg = json.loads(raw)
                send_osc(msg["address"], msg.get("args", []))
            except Exception as e:
                with stats_lock:
                    stats["errors"] += 1
                    stats["last_error"] = f"{type(e).__name__}: {e}"
                try:
                    await conn.send(json.dumps({"ok": False, "error": str(e)}))
                except Exception:
                    pass
    finally:
        ws_clients.discard(conn)

# ---------------------------------------------------------------- main

def print_banner(info):
    bar = "=" * 60
    print(bar)
    print("  vj-remote — your phone as a Resolume control surface")
    print(bar)
    print(f"  Phone page:   {info['url']}")
    print(f"  Setup + QR:   http://{info['lan_ip']}:{ARGS.http_port}/setup")
    print(f"  OSC target:   {ARGS.osc_host}:{ARGS.osc_port}")
    print()
    print("  1. Resolume > Preferences > OSC > enable input (port 7000)")
    print("  2. Phone + laptop on the SAME Wi-Fi; scan the QR on the setup page")
    print("  3. LEAVE THIS WINDOW OPEN — closing it stops the controller")
    print(bar)
    print()

async def main():
    from websockets.asyncio.server import serve
    info = info_payload()
    print_banner(info)
    if not ARGS.no_browser:
        # Open the setup page in a thread so it never blocks the event loop.
        # The server socket is bound by the time this runs.
        threading.Thread(
            target=webbrowser.open,
            args=(f"http://{info['lan_ip']}:{ARGS.http_port}/setup",),
            daemon=True,
        ).start()
    async with serve(ctl_handler, "0.0.0.0", ARGS.http_port, process_request=process_request):
        await asyncio.Future()  # forever

if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nstopped.")
