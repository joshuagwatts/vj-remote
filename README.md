# vj-remote — your phone as a Resolume control surface

No app to install, no OSC addresses to type, no TouchOSC headache.
Your phone opens a web page; big buttons, sliders, and an XY joystick pad
send real OSC signals straight to Resolume.

## The 3-step setup (do this once)

**Step 1 — Tell Resolume to listen.**
Open Resolume → **Preferences → OSC** → tick **Enable OSC input**.
Leave the port at **7000**. That's it on Resolume's side.

**Step 2 — Start the bridge on your VJ laptop.**
Open a terminal in this folder and run:

```
python -m venv .venv
.venv\Scripts\activate        (Windows)
# source .venv/bin/activate   (Mac/Linux)
pip install -r requirements.txt
python server.py
```

You'll see a web address printed, something like
`http://192.168.1.42:8081/`.

**Step 3 — Connect your phone.**
On your phone's browser go to `http://<that-address>/setup`
(or just open the printed address and tap the ⛶ button).
**Scan the QR code** with your phone camera. The controller loads —
phone and laptop just need to be on the **same Wi-Fi**.

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

1. Is Resolume's **OSC input enabled** (Step 1) with port **7000**?
2. Same Wi-Fi on phone and laptop? (Venue Wi-Fi sometimes blocks
   phone→laptop traffic — your phone's **hotspot** is the reliable fallback:
   connect the laptop to the phone's hotspot instead.)
3. Windows Firewall: allow Python through when it asks on first run.
4. In Resolume's OSC preferences there's a fold-out showing the **last
   messages received** — tap a button and watch for it there. If messages
   arrive there but nothing happens, the address is wrong for your
   composition: in Resolume go **Shortcuts → Edit OSC**, click the control,
   and copy the exact address into a "Custom address…" binding.

## For the curious

- The laptop runs a tiny bridge (`server.py`): it serves this page on
  port **8081** and forwards your taps as OSC over UDP to
  **127.0.0.1:7000** (Resolume on the same machine).
- Override with flags or env vars:
  `python server.py --http-port 8081 --osc-host 127.0.0.1 --osc-port 7000`
  (`VJREMOTE_HTTP_PORT`, `VJREMOTE_OSC_HOST`, `VJREMOTE_OSC_PORT`).
- `GET /api/status` → bridge health, send/error counters, connected phones.
- Layouts live in the phone browser's local storage; export the JSON file
  to back them up or share them.
