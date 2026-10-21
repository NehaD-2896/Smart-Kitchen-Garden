# Smart Kitchen Garden — Dashboard & Firmware

Flask dashboard + ESP32/Wokwi firmware for the LoRa-Based Smart Kitchen
Garden Monitoring and Automated Irrigation System (4 sensor nodes: soil
moisture, TDS, temperature).

<<<<<<< HEAD
## Folder contents

```
app.py                     Flask server: login, dashboard, API, irrigation logic, email alerts/simulation
templates/
    login.html              Login page
    dashboard.html          Live dashboard UI (charts, thresholds, alerts)
    inbox.html              Simulated email inbox (every TDS alert logged as a full email)
requirements.txt           Python dependencies
simulate_nodes.py          Sends fake sensor data for 4 nodes (test without hardware)
firmware/wokwi_sensor_node/
    wokwi_sensor_node.ino  ESP32 firmware for ONE node (soil, TDS, temp, relay, WiFi link)
    diagram.json            Wokwi circuit layout
    wokwi.toml              Wokwi project config
=======
Per the review note, since the LoRa hardware isn't fully assembled yet,
each simulated ESP32 node sends its readings straight to the dashboard
over WiFi/HTTP (instead of LoRa → gateway). Swapping in real LoRa later
only changes how the reading gets to the server — the dashboard, DB,
irrigation logic, and alert logic all stay the same.

## Folder contents

```
app.py                     Flask server: API + dashboard + irrigation logic + email alerts
templates/dashboard.html   Live dashboard UI (auto-refreshing charts, thresholds, alerts)
requirements.txt           Python dependencies
simulate_nodes.py          Sends fake sensor data for 4 nodes (test without hardware)
firmware/wokwi_sensor_node/
    wokwi_sensor_node.ino  ESP32 firmware for ONE node (soil, TDS, temp, relay)
    diagram.json           Wokwi circuit layout (sensors + relay + pump LED)
    wokwi.toml             Wokwi project config
>>>>>>> origin/main
```

## 1. Run the dashboard

```bash
pip install -r requirements.txt
python app.py
```

<<<<<<< HEAD
Open **http://localhost:5000** — you'll land on the login page first.

**Default login:** `admin` / `admin123`
Change these before any real demo/deployment:
```bash
export ADMIN_USERNAME=youruser
export ADMIN_PASSWORD=yourpassword
export SECRET_KEY=some-long-random-string
```

## 2. Test it without any hardware

```bash
python simulate_nodes.py
```
Posts random readings for all 4 nodes every 5 seconds (this endpoint,
`/api/data`, is intentionally NOT behind login since real hardware can't
authenticate). Log into the dashboard in your browser to watch it update.

## 3. Simulated email inbox

Go to the **📧 Inbox** link (top-right of the dashboard) to see every TDS
alert logged as a full email — From/To/Subject/Body — tagged either
`SIMULATED ONLY` or `REAL EMAIL SENT` depending on whether SMTP is
configured (see below). This lets you demo the alert flow without needing
live email credentials during a review.

## 4. Enable real email sending (optional)
=======
Open **http://localhost:5000** — you'll see 4 empty node cards until data
starts arriving.

## 2. Test it without any hardware

In a second terminal:

```bash
pip install requests
python simulate_nodes.py
```

This posts random readings for all 4 nodes every 5 seconds so you can see
the dashboard update live, irrigation tags flip on/off, and alerts appear
when TDS goes out of range.

## 3. Test it with Wokwi (simulated ESP32)

1. Create a new **ESP32** project on [wokwi.com](https://wokwi.com), or
   open this project's `firmware/wokwi_sensor_node` folder with the
   [Wokwi VS Code extension](https://marketplace.visualstudio.com/items?itemName=wokwi.wokwi-vscode).
2. Copy `wokwi_sensor_node.ino` in as the sketch and `diagram.json` as the
   wiring diagram.
3. Since Wokwi's cloud simulator can't reach `localhost` on your machine,
   expose your local Flask server with a tunnel, e.g.:
   ```bash
   ngrok http 5000
   ```
4. Paste the resulting `https://xxxx.ngrok-free.app/api/data` URL into
   `SERVER_URL` in the `.ino` file.
5. Run the simulation. Drag the potentiometers to change simulated soil
   moisture / TDS values and watch the dashboard + relay LED react.
6. Duplicate the sketch 3 more times (`node2`, `node3`, `node4`) with a
   different `NODE_ID` each, to simulate all 4 pods together.

## 4. Enable real email alerts

Set these environment variables before running `app.py` (use a Gmail
**App Password**, not your normal password):
>>>>>>> origin/main

```bash
export SMTP_SERVER=smtp.gmail.com
export SMTP_PORT=465
export SMTP_USER=youraccount@gmail.com
export SMTP_PASSWORD=your_app_password
export ALERT_RECIPIENT=whoever_should_get_alerts@example.com
```
<<<<<<< HEAD
10-minute cooldown per node prevents alert spam either way.

## 5. Test with Wokwi (simulated ESP32)

1. Open `firmware/wokwi_sensor_node/wokwi_sensor_node.ino` in a new Wokwi
   ESP32 project, with `diagram.json` as the wiring.
2. Tunnel your local server so Wokwi's cloud simulator can reach it:
   ```bash
   ngrok http 5000
   ```
3. Set `SERVER_URL` in the `.ino` file to your ngrok URL + `/api/data`.
4. Run the simulation — adjust the potentiometers and watch the dashboard
   and relay react.
5. Duplicate the project for `node2`/`node3`/`node4` (just change `NODE_ID`).

## Notes

- Readings are stored in `kitchen_garden.db` (SQLite), auto-created on
  first run.
- Irrigation decision happens server-side; the node actuates its relay
  based on the `irrigate` field in the response.
- When real LoRa hardware is ready, only the **gateway** code changes: it
  parses each node's LoRa packet into the same JSON shape and POSTs it to
  `/api/data`, same as the Wokwi firmware does now.
=======

An alert email is sent whenever a node's TDS reading goes above
`tds_max` or below `tds_min`, with a 10-minute cooldown per node so you
don't get spammed.

## 5. Adjust thresholds

Use the **Configurable Thresholds** panel at the bottom of the dashboard
to change, per node:
- **Min Soil Moisture (%)** — below this, irrigation turns ON
- **Min / Max TDS (ppm)** — outside this range, an email alert fires

Changes apply immediately to the next reading received — no restart
needed.

## Notes / next steps for the report

- Irrigation decision happens server-side (in `/api/data`); the node
  actuates its own relay based on the `irrigate` field in the response.
- All readings are stored in a local SQLite file (`kitchen_garden.db`),
  auto-created on first run — no separate database server needed for
  this stage of the project.
- The `/api/history/<node_id>` endpoint returns the last 50 readings
  per node, which is what feeds the live charts.
- When you move to real LoRa hardware, only the **gateway** code changes:
  it should receive each node's LoRa packet, parse it into the same
  JSON shape used here, and POST it to `/api/data` exactly like the
  Wokwi firmware does.
>>>>>>> origin/main
