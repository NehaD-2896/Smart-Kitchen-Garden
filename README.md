# Smart Kitchen Garden — Dashboard & Firmware

Flask dashboard + ESP32/Wokwi firmware for the LoRa-Based Smart Kitchen
Garden Monitoring and Automated Irrigation System (4 sensor nodes: soil
moisture, TDS, temperature).

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
```

## 1. Run the dashboard

```bash
pip install -r requirements.txt
python app.py
```

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

```bash
export SMTP_SERVER=smtp.gmail.com
export SMTP_PORT=465
export SMTP_USER=youraccount@gmail.com
export SMTP_PASSWORD=your_app_password
export ALERT_RECIPIENT=whoever_should_get_alerts@example.com
```
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
