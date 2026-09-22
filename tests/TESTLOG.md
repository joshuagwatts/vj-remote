# vj-remote TESTLOG

Date: 2026-09-20. Runner: `tests/run_tests.py` + `tests/screenshots.py`.

## Environment caveat (important)
This VM **blocks all UDP sends** (`EPERM` — same wall as the WebRTC lesson in
AGENTS.md). Real UDP delivery to a mock receiver could not be observed here.
The suite is split to stay honest about that:

- **Part A** — live server subprocess: HTTP/WebSocket layer end to end.
- **Part B** — `send_osc()` in-process with a stubbed UDP client, asserting
  the EXACT address strings, arg counts, types and values the phone UI sends.
  On Joshua's laptop the only difference is the real socket underneath.

## Part A results — 9/9 PASS
- server boots, `GET /api/status` → 200, payload has osc target + counters
- `GET /api/info` → LAN URL for the QR page
- WS `/ctl`: bad address → `{ok:false}` reply (no crash, no OSC sent)
- WS `/ctl`: bad arg type → `{ok:false}` reply
- `/api/status` error counter increments on bad messages
- `GET /setup` → 200, contains QR (SVG data URI) + LAN URL
- `GET /` → 200, serves the controller UI
- unknown path → 404

## Part B results — 11/11 PASS
- momentary press → `/composition/layers/1/clips/3/connect` + int `1`
- momentary release → same address + int `0`
- toggle bypass on/off → `/composition/layers/2/bypassed` + int `1` / int `0`
- slider sweep → 5 ordered **float** values 0.0→1.0 on
  `/composition/layers/1/video/opacity`
- XY drag → X float on `/composition/layers/1/video/effects/goo/speed`,
  Y float on `/composition/layers/1/speed`
- tap tempo → `/composition/tempocontroller/tempotap` + int `1`
- string args pass through as `str`
- validation rejects: address without leading `/`, unknown arg type,
  non-numeric int value

## Headless Chromium (CDP) — PASS, no page JS exceptions
- default layout renders: 14 cards (VJ Essentials preset + add card)
- edit mode engages: dashed cards, ◀ ✕ ▶ tools, toast, add-control card
- add sheet opens: type picker → binding picker → params → auto label
- `/setup` renders with QR image
- Screenshots: `tests/shot-default.png`, `shot-edit.png`, `shot-add.png`,
  `shot-setup.png` (visually inspected)

## Knob control (added 2026-09-20 night) — PASS
- `wireKnob` in `web/index.html`: vertical-drag interaction on the card
  (drag up = clockwise = increase; 180px drag = full 0→1 sweep), per-pointer
  capture so two knobs can turn at once, 270° dial (min 7:30, mid 12:00,
  max 4:30, gap at bottom), arc fill + needle + value readout, double-tap
  resets to the configured default and re-sends it.
- Sends **float** over the existing `/ctl` WS format (min→max mapped),
  BPM bindings show "NNN BPM" like sliders do.
- Add sheet offers **Knob** (4th type, "rotary") with the float/event binding
  picker; configure sheet has label / value range / **default value** /
  live OSC address preview.
- Headless CDP tests with REAL mouse events (`Input.dispatchMouseEvent`):
  drag up 180px → readout `100%` + WS float `1.0` on
  `/composition/layers/1/video/effects/goo/speed`; double-tap → `50%` +
  WS float `0.5`; screenshots `tests/shot-knob.png`, `shot-knob-add.png`,
  `shot-knob-cfg.png` (visually inspected — dial renders as a proper circle).
- FX Playground preset gained two knobs: "Goo speed" (def 0.5),
  "Trails" decay (def 0).

## Bugs found & fixed during testing
1. `qrcode` needs Pillow for PNG — switched QR to inline **SVG** data URI
   (no new dependency, sharper on phones).
2. `/setup` returned 500 for the same reason; also taught the test to catch
   HTTPError instead of retry-looping on it.
3. Chromium 152 blocks `about:blank → http://127.0.0.1` navigation — the
   screenshot harness now bootstraps through a `file://` page
   (same workaround as AGENTS.md).
4. Edit-mode tool row overlapped card labels — added top padding in edit mode.
5. Card sub-labels truncated mid-word — now show last two address segments
   (e.g. `clips/1/connect`, `video/opacity`).
6. **CSS class collision**: the new rotary-knob card (`.ctl.knob`) picked up
   the XY pad's pre-existing `.knob` thumb rule (`position:absolute;
   width:44px`), squishing the dial into a narrow strip. Renamed the XY
   thumb class to `.xydot` (variable `knob` → `dot` in `wireXY`).
7. Knob sweep started at 135° (min at 4:30, gap on the right) — moved the
   arc start to 225° so min sits at 7:30, mid at 12:00, max at 4:30,
   gap at the bottom, like a real DJ knob.

## NOT tested (needs Joshua's machine)
- Actual UDP packets arriving in **Resolume** (VM blocks UDP; untested
  against a real Arena install — effect-name spellings like "goo"/"hue rotate"
  must be confirmed via Resolume's Shortcuts → Edit OSC).
- Real phone: touch drag feel, wakeLock, vibrate, QR scan → page load.
- `pip install -r requirements.txt` on Windows (venv paths in README).
