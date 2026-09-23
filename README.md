# vj-remote — your phone as a Resolume control surface

No app to install, no OSC addresses to type, no TouchOSC headache.
Your phone opens a web page; big buttons, sliders, and an XY joystick pad
send real OSC signals straight to Resolume.

## Setup (2 minutes)

**The easy way — download and double-click.**

1. Grab **vj-remote.exe** from the
   [Releases page](https://github.com/joshuagwatts/vj-remote/releases)
   (under "Assets" on the newest release).
2. **Double-click it.** A window opens and a setup page pops up in your
   browser — it shows a big QR code and your controller's address.
3. In Resolume: **Preferences → OSC** → tick **Enable OSC input**
   (leave the port at 7000).
4. On your phone, on the **same Wi-Fi** as the laptop: scan the QR code.
   The controller loads — no app to install.

Leave the black window open while you perform — **closing it stops the
controller.** (If your browser didn't open on its own, the address is
printed in that window: go to `http://<that-address>/setup` on your phone.)

**Trouble downloading?** Windows may warn about an unknown publisher
(SmartScreen) because the app isn't signed — click **More info → Run anyway**.

### The other way — run from Python (Mac, or if you like terminals)

```
pip install -r requirements.txt
python server.py
```

Same result: a setup page opens with the QR code. Steps 3–4 above are
identical.

## Using it

- **Tap** clip buttons to fire clips, drag **sliders** for opacity/speed,
  drag the **XY pad** like a joystick (it can spring back to center), turn
  **knobs** by dragging up/down like a DJ rotary (double-tap resets
  to its default).
- Tap **✎** (top right) for edit mode:
  - **+ Add control** → pick *button / slider / XY pad / knob* → pick what it
    drives from the plain-English list ("Trigger clip", "Layer opacity",
    "Tap tempo"…) → done. The correct OSC address is filled in for you.
  - Tap any control to rename it, change what it drives, or tweak its
    behavior (momentary vs toggle, vertical vs horizontal, min/max,
    knob default value).
  - **◀ ▶** reorder, **✕** delete. Everything saves automatically.
  - **Layout…** menu up top: *VJ Essentials* and *FX Playground* starters,
    or start blank. Export/import your layout as a file from the bottom bar.
- The **dot** top-left is your connection: green = talking to the laptop,
  amber = reconnecting, red = a send failed (you'll feel a buzz too).

Tip: your phone screen won't sleep while the page is open
(it asks to keep the screen awake).

## If nothing happens when you tap

1. Is Resolume's **OSC input enabled** with port **7000**?
2. Same Wi-Fi on phone and laptop? (Venue Wi-Fi sometimes blocks
   phone→laptop traffic — your phone's **hotspot** is the reliable fallback:
   connect the laptop to the phone's hotspot instead.)
3. Windows Firewall: the first time you run vj-remote.exe, Windows asks
   to let it through — click **Allow**. (If you missed it: Windows
   Settings → Firewall → "Allow an app through firewall".)
4. In Resolume's OSC preferences there's a fold-out showing the **last
   messages received** — tap a button and watch for it there. If messages
   arrive there but nothing happens, the address is wrong for your
   composition: in Resolume go **Shortcuts → Edit OSC**, click the control,
   and copy the exact address into a "Custom address…" binding.

## For the curious

- The laptop runs a tiny bridge: it serves this page on
  port **8081** and forwards your taps as OSC over UDP to
  **127.0.0.1:7000** (Resolume on the same machine).
- The exe and `server.py` take the same flags:
  `vj-remote.exe --http-port 8081 --osc-host 127.0.0.1 --osc-port 7000 --no-browser`
  (`VJREMOTE_HTTP_PORT`, `VJREMOTE_OSC_HOST`, `VJREMOTE_OSC_PORT`).
  `--no-browser` stops it auto-opening the setup page.
- `GET /api/status` → bridge health, send/error counters, connected phones.
- Layouts live in the phone browser's local storage; export the JSON file
  to back them up or share them.
- The Windows exe is built automatically: `vj-remote.spec` + PyInstaller,
  built on every push by `.github/workflows/build.yml`. Pushing a tag
  like `v1.0` attaches the exe to a GitHub Release.
