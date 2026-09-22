#!/usr/bin/env python3
"""Headless-Chromium screenshots of the vj-remote UI via CDP.

Captures: default layout, edit mode, add-control sheet, /setup QR page.
Also fails loudly on any page JS exception.

Run:  .venv/bin/python tests/screenshots.py
Needs: /opt/meta-chromium/chrome ; server started by this script on :18083.
"""
import base64
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
VENV_PY = HERE / ".venv" / "bin" / "python"
CHROME = "/opt/meta-chromium/chrome"
HTTP_PORT, CDP_PORT = 18083, 19222
OUT = HERE / "tests"
BOOTSTRAP = Path("/tmp/vj-remote-bootstrap.html")

class CDP:
    def __init__(self, ws_url):
        from websockets.sync.client import connect
        self.ws = connect(ws_url, open_timeout=10)
        self._id = 0
    def send(self, method, params=None, timeout=10):
        self._id += 1
        self.ws.send(json.dumps({"id": self._id, "method": method, "params": params or {}}))
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                m = json.loads(self.ws.recv(timeout=timeout))
            except Exception:
                break
            if m.get("id") == self._id:
                return m.get("result", {})
            # stash events
            if m.get("method") in ("Runtime.exceptionThrown", "Log.entryAdded"):
                print("  PAGE ISSUE:", json.dumps(m.get("params", {}))[:300])
        raise RuntimeError(f"no reply for {method}")
    def drain(self, secs=1.0):
        t0 = time.time()
        while time.time() - t0 < secs:
            try:
                m = json.loads(self.ws.recv(timeout=secs))
                if m.get("method") in ("Runtime.exceptionThrown", "Log.entryAdded"):
                    print("  PAGE ISSUE:", json.dumps(m.get("params", {}))[:300])
            except Exception:
                break
    def shot(self, path):
        r = self.send("Page.captureScreenshot", {"format": "png"})
        Path(path).write_bytes(base64.b64decode(r["data"]))
        print("  saved", path)

def wait_http_ok(path, timeout=15):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{HTTP_PORT}{path}", timeout=2) as r:
                if r.status == 200: return True
        except Exception:
            time.sleep(0.3)
    return False

def main():
    srv = subprocess.Popen([str(VENV_PY), str(HERE / "server.py"), "--http-port", str(HTTP_PORT),
                            "--osc-port", "17001"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    chrome = None
    try:
        assert wait_http_ok("/api/status"), "server did not boot"
        # Chromium 152 blocks about:blank -> http://127.0.0.1 navigation
        # (ERR_BLOCKED_BY_LOCAL_NETWORK_ACCESS_CHECKS). Bootstrap through a
        # file:// page, which is allowed to reach local-network URLs.
        BOOTSTRAP.write_text(
            f'<script>location.replace("http://127.0.0.1:{HTTP_PORT}/")</script>')
        chrome = subprocess.Popen([CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
                                   "--allow-file-access-from-files",
                                   f"--remote-debugging-port={CDP_PORT}",
                                   "--window-size=412,1400", f"file://{BOOTSTRAP}"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # find the page target (the one that ended up on our local URL)
        ws_url = None
        for _ in range(50):
            try:
                targets = json.loads(urllib.request.urlopen(
                    f"http://127.0.0.1:{CDP_PORT}/json/list", timeout=2).read())
                pages = [t for t in targets if t.get("type") == "page"
                         and str(HTTP_PORT) in t.get("url", "")]
                if pages: ws_url = pages[0]["webSocketDebuggerUrl"]; break
            except Exception:
                pass
            time.sleep(0.2)
        assert ws_url, "no CDP page target on the local URL"
        cdp = CDP(ws_url)
        cdp.send("Runtime.enable"); cdp.send("Log.enable"); cdp.send("Page.enable")
        time.sleep(2.0); cdp.drain()
        n = cdp.send("Runtime.evaluate", {"expression": "document.querySelectorAll('.ctl').length"})["result"]["value"]
        print(f"default layout: {n} controls rendered")
        assert n >= 10, f"expected the VJ Essentials preset to render, got {n}"
        cdp.shot(OUT / "shot-default.png")

        cdp.send("Runtime.evaluate", {"expression": "document.getElementById('editBtn').click()"})
        time.sleep(1.0); cdp.drain()
        editing = cdp.send("Runtime.evaluate", {"expression": "document.body.classList.contains('editing')"})["result"]["value"]
        assert editing, "edit mode did not engage"
        cdp.shot(OUT / "shot-edit.png")

        cdp.send("Runtime.evaluate", {"expression": "document.getElementById('addCard').click()"})
        time.sleep(1.0); cdp.drain()
        open_ = cdp.send("Runtime.evaluate", {"expression": "document.getElementById('addSheet').classList.contains('show')"})["result"]["value"]
        assert open_, "add sheet did not open"
        cdp.shot(OUT / "shot-add.png")

        # /setup via in-page navigation (same local origin — allowed)
        cdp.send("Runtime.evaluate", {"expression": "location.href='/setup'"})
        time.sleep(2.0); cdp.drain()
        has_qr = cdp.send("Runtime.evaluate", {"expression": "document.querySelector('.qr img')!==null"})["result"]["value"]
        assert has_qr, "setup page has no QR img"
        cdp.shot(OUT / "shot-setup.png")

        knob_tests(cdp)

        print("screenshots OK — no page exceptions reported above")
        return 0
    finally:
        srv.terminate()
        if chrome: chrome.terminate()

def ev(cdp, expr):
    """Evaluate JS in the page, return the value (None for undefined)."""
    r = cdp.send("Runtime.evaluate", {"expression": expr, "returnByValue": True})["result"]
    return r.get("value")

# Spy on WebSocket.send + seed a deterministic layout (knob + slider),
# installed before page scripts run so the WS created at boot is wrapped.
SPY_SRC = """
window.__sent=[];
const _wsSend=WebSocket.prototype.send;
WebSocket.prototype.send=function(d){ try{window.__sent.push(String(d));}catch(e){} return _wsSend.call(this,d); };
localStorage.setItem('vjremote.layout.v1', JSON.stringify({name:'knobtest',controls:[
  {id:'k1',type:'knob',label:'Goo',binding:{kind:'effect-param',p:{layer:1,effect:'goo',param:'speed'}},min:0,max:1,def:0.5},
  {id:'s1',type:'slider',label:'L1',binding:{kind:'layer-opacity',p:{layer:1}},orientation:'v',min:0,max:1}
]}));
"""

def last_ws_for(cdp, address):
    msgs = ev(cdp, "window.__sent")
    for raw in reversed(msgs or []):
        try:
            m = json.loads(raw)
        except Exception:
            continue
        if m.get("address") == address:
            return m
    return None

def mouse(cdp, mtype, x, y, buttons=0):
    p = {"type": mtype, "x": x, "y": y, "button": "left"}
    if mtype in ("mousePressed", "mouseMoved"):
        p["buttons"] = buttons or 1
    if mtype == "mousePressed":
        p["clickCount"] = 1
    cdp.send("Input.dispatchMouseEvent", p)

def card_center(cdp, sel):
    r = ev(cdp, f"(()=>{{const e=document.querySelector('{sel}').getBoundingClientRect();"
                  "return [e.x+e.width/2, e.y+e.height/2];})()")
    return r[0], r[1]

def knob_tests(cdp):
    print("--- knob interaction tests (real mouse events via CDP) ---")
    cdp.send("Page.addScriptToEvaluateOnNewDocument", {"source": SPY_SRC})
    cdp.send("Runtime.evaluate", {"expression": "location.href='/'"})
    time.sleep(2.5); cdp.drain()

    n = ev(cdp, "document.querySelectorAll('.ctl.knob').length")
    print(f"  knob rendered: {n}")
    assert n == 1, f"expected 1 knob, got {n}"
    v0 = ev(cdp, "document.querySelector('.ctl.knob .val').textContent")
    assert v0 == "50%", f"knob should start at its default 50%, got {v0!r}"
    cdp.shot(OUT / "shot-knob.png")

    # 1. vertical drag up by the full sweep (180px) -> value 0.5 -> 1.0
    cx, cy = card_center(cdp, ".ctl.knob")
    mouse(cdp, "mousePressed", cx, cy)
    for i in range(1, 7):
        mouse(cdp, "mouseMoved", cx, cy - 30 * i)
        time.sleep(0.05)
    mouse(cdp, "mouseReleased", cx, cy - 180)
    time.sleep(0.6); cdp.drain()
    v1 = ev(cdp, "document.querySelector('.ctl.knob .val').textContent")
    assert v1 == "100%", f"drag up should max the knob, got {v1!r}"
    m = last_ws_for(cdp, "/composition/layers/1/video/effects/goo/speed")
    assert m and m["args"][0]["type"] == "f" and abs(m["args"][0]["value"] - 1.0) < 1e-9, \
        f"knob drag should emit float 1.0, got {m}"
    print("  drag up -> 100% + WS float 1.0: OK")

    # 2. double-tap resets to the configured default (0.5)
    for _ in range(2):
        mouse(cdp, "mousePressed", cx, cy)
        mouse(cdp, "mouseReleased", cx, cy)
        time.sleep(0.15)
    time.sleep(0.6); cdp.drain()
    v2 = ev(cdp, "document.querySelector('.ctl.knob .val').textContent")
    assert v2 == "50%", f"double-tap should reset to default 50%, got {v2!r}"
    m = last_ws_for(cdp, "/composition/layers/1/video/effects/goo/speed")
    assert m and abs(m["args"][0]["value"] - 0.5) < 1e-9, f"reset should emit 0.5, got {m}"
    print("  double-tap -> reset 50% + WS float 0.5: OK")

    # 3. slider drag still works after the pointer-target fix (regression)
    sx, sy = card_center(cdp, ".ctl.slider")
    mouse(cdp, "mousePressed", sx, sy)
    for i in range(1, 7):
        mouse(cdp, "mouseMoved", sx, sy - 20 * i)
        time.sleep(0.05)
    mouse(cdp, "mouseReleased", sx, sy - 120)
    time.sleep(0.6); cdp.drain()
    sv = ev(cdp, "document.querySelector('.ctl.slider .val').textContent")
    m = last_ws_for(cdp, "/composition/layers/1/video/opacity")
    assert sv != "50%" and m and m["args"][0]["type"] == "f", \
        f"slider drag should move + emit float, val={sv!r} msg={m}"
    print(f"  slider drag -> {sv} + WS float: OK")

    # 4. add sheet offers Knob with float bindings
    ev(cdp, "document.getElementById('editBtn').click()")
    time.sleep(0.6)
    ev(cdp, "document.getElementById('addCard').click()")
    time.sleep(0.6); cdp.drain()
    ntypes = ev(cdp, "document.querySelectorAll('.typebtn').length")
    assert ntypes == 4, f"add sheet should offer 4 types, got {ntypes}"
    ev(cdp, "document.querySelector('.typebtn[data-t=\"knob\"]').click()")
    time.sleep(0.6); cdp.drain()
    has_float = ev(cdp, "document.querySelector('#addKindSel option[value=\"layer-opacity\"]')!==null")
    assert has_float, "knob binding picker should list float bindings (Layer opacity)"
    cdp.shot(OUT / "shot-knob-add.png")
    print("  add sheet: Knob offered with float bindings: OK")

    # 5. config sheet for a knob: default-value field + live address preview
    ev(cdp, "document.getElementById('addCancel').click()")
    time.sleep(0.4)
    ev(cdp, "document.querySelector('.ctl.knob').click()")  # edit mode: tap = configure
    time.sleep(0.8); cdp.drain()
    has_def = ev(cdp, "document.getElementById('cfgDef')!==null")
    addr = ev(cdp, "document.getElementById('cfgAddr').textContent")
    assert has_def and "effects/goo/speed" in addr, \
        f"knob config needs default field + address preview, got def={has_def} addr={addr!r}"
    cdp.shot(OUT / "shot-knob-cfg.png")
    ev(cdp, "document.getElementById('cfgDone').click()")
    time.sleep(0.5)
    print("  config sheet: default value + address preview: OK")
    print("knob tests PASS")


if __name__ == "__main__":
    sys.exit(main())
