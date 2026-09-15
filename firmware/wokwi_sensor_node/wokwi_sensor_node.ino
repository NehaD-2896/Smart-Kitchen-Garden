/*
  LoRa-Based Smart Kitchen Garden — Sensor Node Firmware (Wokwi simulation)
  ---------------------------------------------------------------------------
  Simulates ONE plant-pod node: reads soil moisture, TDS, and temperature,
  then sends them to the Flask dashboard over WiFi/HTTP (per the review
  decision to simulate the WSN with direct WiFi rather than a real LoRa
  radio in Wokwi). The server's response tells this node whether to switch
  its relay (water pump) ON or OFF.

  In the real deployment this same sensor-read + relay logic runs on each
  ESP32 node, but instead of calling the server directly it would send the
  reading over LoRa (SX1278/SX1276) to the gateway, and the gateway would
  forward it to the Flask server via WiFi.

  --- Wokwi wiring (matches the proposal's circuit diagram) ---
    Soil Moisture Sensor (analog) -> GPIO34
    TDS Sensor (analog)           -> GPIO35
    DHT22 (digital, 1-wire)       -> GPIO4
    Relay IN (drives water pump)  -> GPIO26

  --- Libraries needed (install via Arduino Library Manager, or they are
      already bundled in the Wokwi project's libraries.txt) ---
    - DHT sensor library (Adafruit)
    - ArduinoJson
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <DHT.h>

// ---------------- CONFIG: change these per node ----------------
const char* NODE_ID = "node1";          // node1 / node2 / node3 / node4
const char* WIFI_SSID = "Wokwi-GUEST";  // Wokwi's built-in simulated WiFi
const char* WIFI_PASSWORD = "";         // Wokwi-GUEST has no password

// Replace with your Flask server's public URL (e.g. an ngrok tunnel,
// since the Wokwi simulator runs in the cloud and cannot reach
// "localhost" on your machine).
const char* SERVER_URL = "https://YOUR-NGROK-OR-SERVER-URL/api/data";

const unsigned long SEND_INTERVAL_MS = 5000;  // send every 5 seconds
// -----------------------------------------------------------------

#define SOIL_PIN   34
#define TDS_PIN    35
#define DHT_PIN    4
#define RELAY_PIN  26

#define DHTTYPE DHT22
DHT dht(DHT_PIN, DHTTYPE);

unsigned long lastSendTime = 0;

void connectWiFi() {
  Serial.print("Connecting to WiFi");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(400);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected. IP: " + WiFi.localIP().toString());
}

// Convert raw ADC (0-4095) soil moisture reading into a 0-100% value.
// Calibrate DRY_VALUE / WET_VALUE against your actual sensor in air vs water.
float readSoilMoisturePercent() {
  const int DRY_VALUE = 3000;  // ADC reading in dry air
  const int WET_VALUE = 1200;  // ADC reading fully submerged in water
  int raw = analogRead(SOIL_PIN);
  float percent = 100.0 * (DRY_VALUE - raw) / (DRY_VALUE - WET_VALUE);
  if (percent < 0) percent = 0;
  if (percent > 100) percent = 100;
  return percent;
}

// Convert raw ADC TDS reading into an approximate ppm value.
// Basic linear approximation for simulation purposes; replace with the
// Gravity TDS sensor's official compensation formula for real hardware.
float readTDSppm() {
  int raw = analogRead(TDS_PIN);
  float voltage = raw * (3.3 / 4095.0);
  float ppm = (voltage / 3.3) * 1000.0;  // simple 0-1000ppm scaling
  return ppm;
}

void setRelay(bool on) {
  digitalWrite(RELAY_PIN, on ? HIGH : LOW);
  Serial.println(on ? "[RELAY] Pump ON (irrigating)" : "[RELAY] Pump OFF");
}

void sendReading(float moisture, float tds, float temperature) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi not connected, skipping send.");
    return;
  }

  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");

  StaticJsonDocument<200> doc;
  doc["node_id"] = NODE_ID;
  doc["soil_moisture"] = moisture;
  doc["tds"] = tds;
  doc["temperature"] = temperature;

  String payload;
  serializeJson(doc, payload);

  int httpCode = http.POST(payload);

  if (httpCode == 200) {
    String response = http.getString();
    StaticJsonDocument<100> respDoc;
    DeserializationError err = deserializeJson(respDoc, response);
    if (!err) {
      bool irrigate = respDoc["irrigate"] | false;
      setRelay(irrigate);
    }
  } else {
    Serial.printf("HTTP POST failed, code: %d\n", httpCode);
  }

  http.end();
}

void setup() {
  Serial.begin(115200);
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, LOW);
  dht.begin();
  connectWiFi();
}

void loop() {
  if (millis() - lastSendTime >= SEND_INTERVAL_MS) {
    lastSendTime = millis();

    float moisture = readSoilMoisturePercent();
    float tds = readTDSppm();
    float temperature = dht.readTemperature();

    if (isnan(temperature)) {
      Serial.println("Failed to read from DHT22, using fallback value.");
      temperature = 25.0;
    }

    Serial.printf("[%s] Moisture: %.1f%%  TDS: %.1fppm  Temp: %.1fC\n",
                  NODE_ID, moisture, tds, temperature);

    sendReading(moisture, tds, temperature);
  }
}
