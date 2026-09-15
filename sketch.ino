#include <DHT.h>
#include <SPI.h>
#include <LoRa.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// Initialize LCD (I2C address 0x27, 16 columns, 2 rows)
LiquidCrystal_I2C lcd(0x27, 16, 2);

// ---- Pin definitions ----
#define DHTPIN 4
#define DHTTYPE DHT22
DHT dht(DHTPIN, DHTTYPE);

#define SOIL_PIN 34
#define TDS_PIN 35
#define RELAY_PIN 26

#define LORA_SS 5
#define LORA_RST 14
#define LORA_DIO0 2

// ---- Thresholds ----
const int MOISTURE_THRESHOLD = 40;   // % below this = dry -> pump ON
const int TDS_THRESHOLD = 700;       // ppm above this = abnormal -> alert

bool loraReady = false;

void setup() {
  Serial.begin(115200);
  delay(500);

  // Initialize LCD Screen
  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("System Loading...");

  dht.begin();
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, LOW);

  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);

  // Bypassed for Wokwi simulation to prevent boot loops
  LoRa.begin(433E6); 
  Serial.println("LoRa bypassed for simulation -- Node+Gateway loopback forced ready");
  loraReady = true; 
  
  lcd.clear();
}

void loop() {
  // ============ NODE SIDE: read sensors ============
  int soilRaw = analogRead(SOIL_PIN);
  int tdsRaw = analogRead(TDS_PIN);
  float temp = dht.readTemperature();
  float hum = dht.readHumidity();

  int moisturePercent = map(soilRaw, 0, 4095, 0, 100);
  int tdsPpm = map(tdsRaw, 0, 4095, 0, 1200);

  Serial.println("---- NODE: Sensor Reading ----");
  Serial.print("Moisture: "); Serial.print(moisturePercent); Serial.print("% | ");
  Serial.print("TDS: "); Serial.print(tdsPpm); Serial.print("ppm | ");
  Serial.print("Temp: "); Serial.print(temp); Serial.print("C | ");
  Serial.print("Hum: "); Serial.print(hum); Serial.println("%");

  // ---- Irrigation decision ----
  if (moisturePercent < MOISTURE_THRESHOLD) {
    digitalWrite(RELAY_PIN, HIGH);
    Serial.println(">> Soil dry -- pump ON");
  } else {
    digitalWrite(RELAY_PIN, LOW);
  }

  // ---- Nutrient check ----
  bool tdsAbnormal = tdsPpm > TDS_THRESHOLD;
  if (tdsAbnormal) {
    Serial.println(">> TDS abnormal -- alert flagged");
  }

  // ============ DISPLAY SIDE: Update LCD Screen ============
  lcd.clear();
  if (tdsAbnormal) {
    lcd.setCursor(0, 0);
    lcd.print("ALERT: HIGH TDS!");
    lcd.setCursor(0, 1);
    lcd.print("TDS: " + String(tdsPpm) + " ppm");
  } else {
    lcd.setCursor(0, 0);
    lcd.print("M:" + String(moisturePercent) + "% TDS:" + String(tdsPpm));
    lcd.setCursor(0, 1);
    lcd.print("T:" + String(temp, 1) + "C H:" + String(hum, 1) + "%");
  }

  // ============ NODE SIDE: send LoRa packet ============
  if (loraReady) {
    String payload = "NODE1," + String(moisturePercent) + "," +
                      String(tdsPpm) + "," + String(temp) + "," +
                      String(hum) + "," + (tdsAbnormal ? "ALERT" : "OK");

    LoRa.beginPacket();
    LoRa.print(payload);
    LoRa.endPacket();
    Serial.print(">> Packet sent to gateway: ");
    Serial.println(payload);
  }

  delay(200); // brief pause before checking for the "received" packet

  // ============ GATEWAY SIDE: try to receive ============
  Serial.println("---- GATEWAY: Listening ----");
  int packetSize = LoRa.parsePacket();
  if (packetSize) {
    String received = "";
    while (LoRa.available()) {
      received += (char)LoRa.read();
    }
    Serial.print(">> Gateway received: ");
    Serial.println(received);
    Serial.print(">> Signal RSSI: ");
    Serial.println(LoRa.packetRssi());
  } else {
    Serial.println(">> No packet received this cycle.");
  }

  Serial.println();
  delay(3000);
}
