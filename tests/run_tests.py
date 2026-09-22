#!/usr/bin/env python3
"""Tests for vj-remote.

This VM blocks all UDP sends (EPERM), so real UDP delivery can't be observed
here. The suite is split accordingly:

  Part A (subprocess): the HTTP/WebSocket layer end to end — /api/status,
      /api/info, /setup (QR), / (UI), WS message validation + error replies.
  Part B (in-process): OSC serialization — send_osc() with a stubbed UDP
      client, asserting the EXACT address, arg count, types and values the
      phone UI's messages produce (this is the part Resolume will receive).

Run:  .venv/bin/python tests/run_tests.py
"""
import json
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
VENV_PY = HERE / ".venv" / "bin" / "python"
HTTP_PORT, OSC_PORT = 18081, 17001

results = []
def check(name, cond, detail=""):
    results.append(bool(cond))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))

def wait_http(path, timeout=12):
    url = f"http://127.0.0.1:{HTTP_PORT}{path}"
    t0 = time.time()
    last = (None, None)
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            last = (e.code, e.read())
            time.sleep(0.3)
        except Exception:
            time.sleep(0.2)
    return last

# ================= Part A: HTTP/WebSocket layer =================
def part_a():
    print("--- Part A: HTTP/WebSocket layer (live server) ---")
    proc = subprocess.Popen(
        [str(VENV_PY), str(HERE / "server.py"),
         "--http-port", str(HTTP_PORT), "--osc-host", "127.0.0.1",
         "--osc-port", str(OSC_PORT)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        status, body = wait_http("/api/status")
        check("server boots, /api/status 200", status == 200, f"status={status}")
        if status != 200:
            print(proc.stdout.read()); return
        info = json.loads(body)
        check("status payload: osc target + counters",
              info.get("ok") and info["osc_port"] == OSC_PORT and info["sends"] == 0, str(info))

        status, body = wait_http("/api/info")
        info = json.loads(body or b"{}")
        check("/api/info has LAN url", status == 200 and info.get("url", "").startswith("http://"),
              str(info)[:120])

        from websockets.sync.client import connect as ws_connect
        with ws_connect(f"ws://127.0.0.1:{HTTP_PORT}/ctl") as ws:
            # malformed: bad address -> {ok:false}, error counted, server stays up
            ws.send(json.dumps({"address": "nope", "args": []}))
            reply = json.loads(ws.recv(timeout=5))
            check("bad address -> {ok:false} reply", reply.get("ok") is False, str(reply))
            # malformed: bad arg type
            ws.send(json.dumps({"address": "/composition/x", "args": [{"type": "z", "value": 1}]}))
            reply = json.loads(ws.recv(timeout=5))
            check("bad arg type -> {ok:false} reply", reply.get("ok") is False, str(reply))

        status, body = wait_http("/api/status")
        check("error counter incremented", json.loads(body)["errors"] >= 2, body[:120].decode(errors="replace"))

        status, body = wait_http("/setup")
        check("/setup 200 with QR + URL", status == 200 and b"data:image/svg+xml;base64" in body
              and bytes(info.get("url", ""), "utf-8") in body, f"status={status}")

        status, body = wait_http("/")
        check("/ serves the UI", status == 200 and b'id="grid"' in body and b"vj-remote" in body,
              f"status={status}")

        status, _ = wait_http("/nonexistent")
        check("unknown path -> 404", status == 404, f"status={status}")
    finally:
        proc.terminate()
        try: proc.wait(timeout=5)
        except Exception: proc.kill()

# ================= Part B: OSC serialization =================
def part_b():
    print("--- Part B: OSC serialization (stubbed UDP client) ---")
    sys.path.insert(0, str(HERE))
    import server as S

    class FakeClient:
        def __init__(self): self.sent = []
        def send_message(self, address, values): self.sent.append((address, list(values)))
    fake = FakeClient()
    S._osc_client = fake  # bypass real UDP socket (blocked on this VM)

    def sent_once(address, args):
        fake.sent.clear()
        S.send_osc(address, args)
        assert len(fake.sent) == 1, f"expected 1 OSC msg, got {fake.sent}"
        return fake.sent[0]

    # 1. momentary button press/release -> int 1 / int 0
    a, v = sent_once("/composition/layers/1/clips/3/connect", [{"type": "i", "value": 1}])
    check("momentary press -> address + int 1",
          a == "/composition/layers/1/clips/3/connect" and v == [1] and type(v[0]) is int, f"{a} {v}")
    a, v = sent_once("/composition/layers/1/clips/3/connect", [{"type": "i", "value": 0}])
    check("momentary release -> int 0", v == [0] and type(v[0]) is int, f"{v}")

    # 2. toggle on/off -> int 1 / int 0
    a, v = sent_once("/composition/layers/2/bypassed", [{"type": "i", "value": 1}])
    check("toggle bypass on -> int 1", a == "/composition/layers/2/bypassed" and v == [1], f"{a} {v}")
    a, v = sent_once("/composition/layers/2/bypassed", [{"type": "i", "value": 0}])
    check("toggle bypass off -> int 0", v == [0], f"{v}")

    # 3. slider sweep 0->1 -> ordered floats
    fake.sent.clear()
    for x in (0.0, 0.25, 0.5, 0.75, 1.0):
        S.send_osc("/composition/layers/1/video/opacity", [{"type": "f", "value": x}])
    got = [s[1][0] for s in fake.sent]
    check("slider sweep -> 5 ordered floats",
          len(got) == 5 and all(type(x) is float for x in got)
          and all(abs(g - w) < 1e-9 for g, w in zip(got, (0.0, 0.25, 0.5, 0.75, 1.0))), str(got))

    # 4. XY drag -> two addresses, two floats
    ax, vx = sent_once("/composition/layers/1/video/effects/goo/speed", [{"type": "f", "value": 0.3}])
    ay, vy = sent_once("/composition/layers/1/speed", [{"type": "f", "value": 0.8}])
    check("XY -> X and Y on own addresses, floats",
          ax == "/composition/layers/1/video/effects/goo/speed" and abs(vx[0] - 0.3) < 1e-9
          and ay == "/composition/layers/1/speed" and abs(vy[0] - 0.8) < 1e-9, f"{ax} {vx} / {ay} {vy}")

    # 5. tap tempo -> int 1
    a, v = sent_once("/composition/tempocontroller/tempotap", [{"type": "i", "value": 1}])
    check("tap tempo -> int 1", a == "/composition/tempocontroller/tempotap" and v == [1], f"{a} {v}")

    # 6. string args pass through as str
    a, v = sent_once("/composition/layers/1/video/source/textgenerator/text/params/lines",
                     [{"type": "s", "value": "hello"}])
    check("string arg -> str", v == ["hello"] and type(v[0]) is str, f"{v}")

    # 7. validation rejects junk
    for bad_addr, bad_args, why in [("nope", [], "missing leading /"),
                                    ("/ok", [{"type": "z", "value": 1}], "bad arg type"),
                                    ("/ok", [{"type": "i", "value": "abc"}], "non-numeric int")]:
        try:
            S.send_osc(bad_addr, bad_args)
            check(f"rejects {why}", False, "no exception raised")
        except (ValueError, TypeError):
            check(f"rejects {why}", True)

def main():
    part_a()
    part_b()
    n = len(results)
    print(f"\n{n - sum(results)} failed, {sum(results)}/{n} passed")
    return 0 if all(results) else 1

if __name__ == "__main__":
    sys.exit(main())
