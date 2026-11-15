#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <MAX30105.h>
#include "heartRate.h"
#include <TinyGPSPlus.h>
#include <math.h>

#include <PN532_I2C.h>
#include <PN532.h>
#include <WiFi.h>
#include <HTTPClient.h>
// ---------------- PIN CONFIGURATION ----------------
#define I2C_SDA       21
#define I2C_SCL       22
#define DS18B20_PIN    4
#define SOS_PIN       27
#define BUZZER_PIN    26

#define GSM_RX_PIN    32
#define GSM_TX_PIN    33

#define GPS_RX_PIN    16
#define GPS_TX_PIN    17

  const char* WIFI_SSID = "Dhiva";
const char* WIFI_PASSWORD = "12345678";
unsigned long lastApiPost = 0;
const unsigned long API_POST_INTERVAL = 2000;

const char* API_URL = "http://10.103.59.67:5000/api/health";

void connectWiFi() {

  Serial.println();
  Serial.println("Connecting to WiFi...");

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long startTime = millis();

  while (WiFi.status() != WL_CONNECTED &&
         millis() - startTime < 15000) {

    delay(500);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {

    Serial.println();
    Serial.println("WiFi Connected!");

    Serial.print("ESP32 IP Address: ");
    Serial.println(WiFi.localIP());

  } else {

    Serial.println();
    Serial.println("WiFi connection failed!");
  }
}
void sendHealthData() {

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi disconnected. Reconnecting...");
    WiFi.reconnect();
    return;
  }

  HTTPClient http;

  http.begin(API_URL);
  http.setTimeout(3000);
  http.addHeader("Content-Type", "application/json");

  String json = "{";

  json += "\"irValue\":" + String(irValue) + ",";
  json += "\"heartRate\":" + String(heartRate, 1) + ",";
  json += "\"averageHR\":" + String(averageHR, 1) + ",";

  json += "\"fingerDetected\":";
  json += fingerDetected ? "true," : "false,";

  json += "\"temperature\":";

  if (isnan(bodyTemp)) {
    json += "null,";
  } else {
    json += String(bodyTemp, 1) + ",";
  }

  json += "\"accelX\":" + String(accelX, 2) + ",";
  json += "\"accelY\":" + String(accelY, 2) + ",";

  json += "\"fallDetected\":";
  json += fallDetected ? "true," : "false,";

  json += "\"sosPressed\":";
  json += sosPressed ? "true," : "false,";

  json += "\"gpsFix\":";
  json += gpsFix ? "true," : "false,";

  json += "\"latitude\":" + String(gpsLat, 6) + ",";
  json += "\"longitude\":" + String(gpsLon, 6) + ",";

  json += "\"pn532OK\":";
  json += pn532OK ? "true," : "false,";

  json += "\"tabletState\":" + String((int)tabletState);

  json += "}";

  int httpResponseCode = http.POST(json);

  Serial.print("Health API HTTP response: ");
  Serial.println(httpResponseCode);

  if (httpResponseCode > 0) {
    Serial.println(http.getString());
  }

  http.end();
}
// ---------------- PHONE NUMBER ----------------
const char ALERT_PHONE[] = "+919176947554";

// ---------------- OBJECTS ----------------
LiquidCrystal_I2C lcd(0x27, 16, 2);

OneWire oneWire(DS18B20_PIN);
DallasTemperature tempSensor(&oneWire);

MAX30105 maxSensor;
TinyGPSPlus gps;

HardwareSerial GSM(1);
HardwareSerial GPSSerial(2);

// PN532
PN532_I2C pn532i2c(Wire);
PN532 nfc(pn532i2c);

bool pn532OK = false;

// ====================================================
// TEMPERATURE
// ====================================================

float bodyTemp = NAN;
const float TEMP_HIGH = 38.0;
bool tempAlertSent = false;
unsigned long lastTempRead = 0;

// ====================================================
// HEART RATE
// ====================================================

bool maxOK = false;
long irValue = 0;
float heartRate = 0;
float averageHR = 0;
bool fingerDetected = false;

const float HR_HIGH = 120.0;
const float HR_NORMAL_LOW = 50.0;
const float HR_NORMAL_HIGH = 100.0;

const unsigned long HR_TIMEOUT = 3000;

const byte RATE_SIZE = 6;
byte rates[RATE_SIZE] = {0};
byte rateIndex = 0;
byte rateCount = 0;

unsigned long lastBeatTime = 0;
unsigned long lowIRSince = 0;

bool hrArmed = false;
bool hrAlertActive = false;

// ====================================================
// MPU6500
// ====================================================

const uint8_t MPU_ADDR = 0x68;
bool mpuOK = false;

float accelX = 0;
float accelY = 0;
float accelZ = 0;

float baselinePitch = 0;
float baselineRoll = 0;
bool baselineReady = false;

bool fallDetected = false;

unsigned long impactTime = 0;
unsigned long fallTime = 0;
unsigned long fallCooldownUntil = 0;
unsigned long uprightSince = 0;

const float IMPACT_THRESHOLD = 2.2;
const float ANGLE_CHANGE_THRESHOLD = 45.0;

const unsigned long FALL_CONFIRM_WINDOW = 1500;
const unsigned long FALL_COOLDOWN = 10000;
const unsigned long UPRIGHT_RESET_TIME = 5000;

// ====================================================
// SOS
// ====================================================

bool sosPressed = false;
bool previousSOS = false;
bool sosAlertSent = false;

// ====================================================
// GPS
// ====================================================

bool gpsFix = false;
double gpsLat = 0;
double gpsLon = 0;

// ====================================================
// BUZZER
// ====================================================

bool buzzerOn = false;

// ====================================================
// TABLET REMINDER
// ====================================================

// Authorized UID: BA A3 73 06
uint8_t authorizedUID[] = {
  0xBA, 0xA3, 0x73, 0x06
};

const uint8_t authorizedUIDLength = 4;

enum TabletState {
  TABLET_WAITING,
  TABLET_REMINDER_ACTIVE,
  TABLET_TAKEN,
  TABLET_MISSED
};

TabletState tabletState = TABLET_WAITING;

const unsigned long TABLET_REMINDER_DELAY = 120000UL;
const unsigned long TABLET_SCAN_DURATION = 15000UL;
const unsigned long TABLET_RESULT_DURATION = 4000UL;

unsigned long tabletNextReminder = 0;
unsigned long tabletScanStart = 0;
unsigned long tabletResultTime = 0;

// ====================================================
// LCD PAGE CONTROL
// ====================================================

byte lcdPage = 0;

unsigned long lastPageSwitch = 0;
unsigned long lastLCDUpdate = 0;

const unsigned long LCD_PAGE_INTERVAL = 3000;

// ====================================================
// GSM ALERT QUEUE
// ====================================================

enum AlertType {
  ALERT_NONE,
  ALERT_SOS,
  ALERT_FALL,
  ALERT_TEMP,
  ALERT_HEART,
  ALERT_TABLET
};

AlertType pendingAlert = ALERT_NONE;

bool fallAlertSent = false;

// ====================================================
// OTHER TIMERS
// ====================================================

unsigned long lastDebugPrint = 0;
unsigned long lastMPURead = 0;

// ====================================================
// MPU6500 LOW-LEVEL I2C
// ====================================================

bool mpuWrite(uint8_t reg, uint8_t value) {

  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);
  Wire.write(value);

  return Wire.endTransmission() == 0;
}

bool mpuReadBytes(
  uint8_t reg,
  uint8_t *buffer,
  uint8_t length
) {

  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);

  if (Wire.endTransmission(false) != 0) {
    return false;
  }

  uint8_t received =
    Wire.requestFrom(
      (uint8_t)MPU_ADDR,
      length,
      (uint8_t)true
    );

  if (received != length) {
    while (Wire.available()) {
      Wire.read();
    }

    return false;
  }

  for (uint8_t i = 0; i < length; i++) {
    buffer[i] = Wire.read();
  }

  return true;
}

bool initMPU6500() {

  uint8_t who = 0;

  if (!mpuReadBytes(0x75, &who, 1)) {
    Serial.println("MPU6500 I2C read failed");
    return false;
  }

  Serial.print("MPU WHO_AM_I = 0x");
  Serial.println(who, HEX);

  if (who != 0x70 &&
      who != 0x68 &&
      who != 0x69) {

    Serial.println("Unknown MPU device ID");
    return false;
  }

  mpuWrite(0x6B, 0x00);
  delay(100);

  mpuWrite(0x1A, 0x03);
  mpuWrite(0x19, 0x04);
  mpuWrite(0x1B, 0x00);
  mpuWrite(0x1C, 0x00);

  delay(100);

  Serial.println("MPU6500 ready");

  return true;
}

void readMPU6500() {

  uint8_t data[6];

  if (!mpuReadBytes(0x3B, data, 6)) {
    return;
  }

  int16_t rawX =
    (int16_t)((data[0] << 8) | data[1]);

  int16_t rawY =
    (int16_t)((data[2] << 8) | data[3]);

  int16_t rawZ =
    (int16_t)((data[4] << 8) | data[5]);

  accelX = rawX / 16384.0;
  accelY = rawY / 16384.0;
  accelZ = rawZ / 16384.0;
}

// ====================================================
// GPS
// ====================================================

void updateGPS() {

  while (GPSSerial.available()) {
    gps.encode(GPSSerial.read());
  }

  if (gps.location.isValid() &&
      gps.location.age() < 5000) {

    gpsFix = true;

    gpsLat = gps.location.lat();
    gpsLon = gps.location.lng();

  } else {
    gpsFix = false;
  }
}

String getLocationText() {

  if (gpsFix) {

    return "Location: https://maps.google.com/?q=" +
      String(gpsLat, 6) + "," +
      String(gpsLon, 6);
  }

  return "GPS location not available";
}

// ====================================================
// GSM SMS
// ====================================================

void sendSMS(String message) {

  Serial.println();
  Serial.println("Sending SMS...");

  GSM.println("AT");
  delay(500);

  GSM.println("AT+CMGF=1");
  delay(500);

  GSM.println("AT+CSCS=\"GSM\"");
  delay(500);

  GSM.print("AT+CMGS=\"");
  GSM.print(ALERT_PHONE);
  GSM.println("\"");

  delay(1000);

  GSM.print(message);
  GSM.print("\r\n");

  delay(300);

  GSM.write(26);

  delay(5000);

  Serial.println("SMS command completed.");
}

void queueAlert(int alert) {

  AlertType newAlert = (AlertType)alert;

  if (pendingAlert == ALERT_NONE ||
      newAlert == ALERT_SOS ||
      (newAlert == ALERT_FALL &&
       pendingAlert != ALERT_SOS)) {

    pendingAlert = newAlert;
  }
}

void processPendingAlert() {

  if (pendingAlert == ALERT_NONE) {
    return;
  }

  // Do not block the 15-second RFID scanning period.
  if (tabletState == TABLET_REMINDER_ACTIVE) {
    return;
  }

  String message = "";
  String location = getLocationText();

  switch (pendingAlert) {

    case ALERT_SOS:

      message =
        "EMERGENCY: SOS button pressed. "
        "Elderly person needs assistance.\n";

      break;

    case ALERT_FALL:

      message =
        "FALL ALERT: Possible fall detected. "
        "Please check immediately.\n";

      break;

    case ALERT_TEMP:

      message =
        "TEMPERATURE ALERT: Temperature is high: " +
        String(bodyTemp, 1) + " C.\n";

      break;

    case ALERT_HEART:

      message =
        "HEART RATE ALERT: High heart rate detected: " +
        String(averageHR, 0) + " BPM.\n";

      break;

    case ALERT_TABLET:

      message =
        "TABLET MISSED ALERT: Authorized RFID card "
        "was not scanned within 15 seconds. TABLET NOT TAKEN "
        "Please check the elderly person.\n";

      break;

    default:

      pendingAlert = ALERT_NONE;
      return;
  }

  message += location;

  sendSMS(message);

  pendingAlert = ALERT_NONE;
}

// ====================================================
// TEMPERATURE
// ====================================================

void updateTemperature() {

  if (millis() - lastTempRead < 1000) {
    return;
  }

  lastTempRead = millis();

  tempSensor.requestTemperatures();

  float t = tempSensor.getTempCByIndex(0);

  if (t != DEVICE_DISCONNECTED_C &&
      t >= -55 && t <= 125) {

    bodyTemp = t;
  }

  if (!isnan(bodyTemp) &&
      bodyTemp >= TEMP_HIGH) {

    if (!tempAlertSent) {

      queueAlert(ALERT_TEMP);
      tempAlertSent = true;
    }

  } else {

    tempAlertSent = false;
  }
}

// ====================================================
// MAX30102 HEART RATE
// ====================================================

void resetHeartRate() {

  heartRate = 0;
  averageHR = 0;

  rateCount = 0;
  rateIndex = 0;

  lastBeatTime = 0;

  hrArmed = false;
  hrAlertActive = false;

  for (byte i = 0; i < RATE_SIZE; i++) {
    rates[i] = 0;
  }
}

void updateHeartRate() {

  if (!maxOK) {
    return;
  }

  maxSensor.check();

  while (maxSensor.available()) {

    long sampleIR = maxSensor.getFIFOIR();

    maxSensor.nextSample();

    irValue = sampleIR;

    unsigned long now = millis();

    if (sampleIR < 30000) {

      if (lowIRSince == 0) {
        lowIRSince = now;
      }

      if (now - lowIRSince >= 1000) {

        fingerDetected = false;

        resetHeartRate();
      }

      continue;
    }

    lowIRSince = 0;
    fingerDetected = true;

    if (checkForBeat(sampleIR)) {

      unsigned long beatTime = now;

      if (lastBeatTime != 0) {

        unsigned long interval =
          beatTime - lastBeatTime;

        if (interval >= 300 &&
            interval <= 1500) {

          float candidate =
            60000.0 / interval;

          if (candidate >= 40.0 &&
              candidate <= 200.0) {

            heartRate = candidate;

            rates[rateIndex] =
              (byte)roundf(candidate);

            rateIndex =
              (rateIndex + 1) % RATE_SIZE;

            if (rateCount < RATE_SIZE) {
              rateCount++;
            }

            float total = 0;

            for (byte i = 0; i < rateCount; i++) {
              total += rates[i];
            }

            averageHR = total / rateCount;
          }
        }
      }

      lastBeatTime = beatTime;
    }
  }

  if (lastBeatTime != 0 &&
      millis() - lastBeatTime > HR_TIMEOUT) {

    resetHeartRate();
  }

  if (rateCount >= 3 &&
      averageHR >= HR_NORMAL_LOW &&
      averageHR <= HR_NORMAL_HIGH) {

    hrArmed = true;
    hrAlertActive = false;
  }

  if (hrArmed &&
      !hrAlertActive &&
      rateCount >= 3 &&
      averageHR > HR_HIGH) {

    hrArmed = false;
    hrAlertActive = true;

    queueAlert(ALERT_HEART);
  }
}

// ====================================================
// FALL DETECTION
// ====================================================

float calculatePitch() {

  return atan2f(
    accelX,
    sqrtf(accelY * accelY + accelZ * accelZ)
  ) * 180.0 / PI;
}

float calculateRoll() {

  return atan2f(accelY, accelZ) *
    180.0 / PI;
}

void updateFallDetection() {

  if (!mpuOK ||
      millis() - lastMPURead < 50) {

    return;
  }

  lastMPURead = millis();

  readMPU6500();

  float magnitude = sqrtf(
    accelX * accelX +
    accelY * accelY +
    accelZ * accelZ
  );

  float pitch = calculatePitch();
  float roll = calculateRoll();

  if (!baselineReady) {

    baselinePitch = pitch;
    baselineRoll = roll;

    baselineReady = true;

    return;
  }

  unsigned long now = millis();

  if (magnitude >= IMPACT_THRESHOLD &&
      now >= fallCooldownUntil) {

    impactTime = now;
  }

  if (impactTime != 0 &&
      now - impactTime <= FALL_CONFIRM_WINDOW) {

    float pitchChange =
      fabsf(pitch - baselinePitch);

    float rollChange =
      fabsf(roll - baselineRoll);

    if (pitchChange > ANGLE_CHANGE_THRESHOLD ||
        rollChange > ANGLE_CHANGE_THRESHOLD) {

      fallDetected = true;

      fallTime = now;
      fallCooldownUntil = now + FALL_COOLDOWN;

      uprightSince = 0;
      impactTime = 0;

      if (!fallAlertSent) {

        queueAlert(ALERT_FALL);
        fallAlertSent = true;
      }
    }
  }

  if (impactTime != 0 &&
      now - impactTime > FALL_CONFIRM_WINDOW) {

    impactTime = 0;
  }

  float pitchChange =
    fabsf(pitch - baselinePitch);

  float rollChange =
    fabsf(roll - baselineRoll);

  bool nearBaseline =
    pitchChange < 20.0 &&
    rollChange < 20.0;

  if (fallDetected && nearBaseline) {

    if (uprightSince == 0) {
      uprightSince = now;
    }

    if (now - uprightSince >= UPRIGHT_RESET_TIME) {

      fallDetected = false;
      fallAlertSent = false;

      uprightSince = 0;

      baselinePitch = pitch;
      baselineRoll = roll;
    }

  } else {

    uprightSince = 0;
  }
}

// ====================================================
// SOS BUTTON
// ====================================================

void updateSOSButton() {

  bool pressed =
    (digitalRead(SOS_PIN) == LOW);

  sosPressed = pressed;

  if (pressed &&
      !previousSOS &&
      !sosAlertSent) {

    queueAlert(ALERT_SOS);

    sosAlertSent = true;
  }

  if (!pressed) {
    sosAlertSent = false;
  }

  previousSOS = pressed;
}

// ====================================================
// PN532 RFID TABLET REMINDER
// ====================================================

bool isAuthorizedCard(
  uint8_t *uid,
  uint8_t uidLength
) {

  if (uidLength != authorizedUIDLength) {
    return false;
  }

  for (uint8_t i = 0; i < authorizedUIDLength; i++) {

    if (uid[i] != authorizedUID[i]) {
      return false;
    }
  }

  return true;
}

void startTabletReminder() {

  tabletState = TABLET_REMINDER_ACTIVE;

  tabletScanStart = millis();

  Serial.println();
  Serial.println("TABLET REMINDER STARTED");

  Serial.println("Waiting for authorized RFID card...");
}

void updateTabletReminder() {

  unsigned long now = millis();

  // --------------------------------
  // START REMINDER AT COUNTDOWN ZERO
  // --------------------------------

  if (tabletState == TABLET_WAITING &&
      now >= tabletNextReminder) {

    if (pn532OK) {

      startTabletReminder();

    } else {

      tabletState = TABLET_MISSED;

      tabletResultTime = now;

      queueAlert(ALERT_TABLET);

      Serial.println("PN532 NOT AVAILABLE");
      Serial.println("TABLET REMINDER MISSED");
    }

    return;
  }

  // --------------------------------
  // RFID SCANNING
  // --------------------------------

  if (tabletState == TABLET_REMINDER_ACTIVE) {

    uint8_t uid[7];
    uint8_t uidLength = 0;

    bool cardFound = nfc.readPassiveTargetID(
      PN532_MIFARE_ISO14443A,
      uid,
      &uidLength,
      50
    );

    if (cardFound) {

      Serial.print("CARD UID: ");

      for (uint8_t i = 0; i < uidLength; i++) {

        if (uid[i] < 0x10) {
          Serial.print("0");
        }

        Serial.print(uid[i], HEX);
        Serial.print(" ");
      }

      Serial.println();

      if (isAuthorizedCard(uid, uidLength)) {

        tabletState = TABLET_TAKEN;

        tabletResultTime = now;

        Serial.println("AUTHORIZED CARD");
        Serial.println("TABLET TAKEN");
      } else {

        Serial.println("UNAUTHORIZED CARD");
        Serial.println("SCAN AUTHORIZED CARD");
      }
    }

    // --------------------------------
    // 15-SECOND TIMEOUT
    // --------------------------------

    if (tabletState == TABLET_REMINDER_ACTIVE &&
        now - tabletScanStart >= TABLET_SCAN_DURATION) {

      tabletState = TABLET_MISSED;

      tabletResultTime = now;

      queueAlert(ALERT_TABLET);

      Serial.println("TABLET MISSED");
    }

    return;
  }

  // --------------------------------
  // AFTER RESULT, START NEW 2-MINUTE
  // COUNTDOWN
  // --------------------------------

  if ((tabletState == TABLET_TAKEN ||
       tabletState == TABLET_MISSED) &&

      now - tabletResultTime >= TABLET_RESULT_DURATION) {

    tabletState = TABLET_WAITING;

    tabletNextReminder =
      now + TABLET_REMINDER_DELAY;

    Serial.println("NEXT TABLET REMINDER IN 2 MINUTES");
  }
}

// ====================================================
// BUZZER
// ====================================================

void updateBuzzer() {

  bool tempHigh =
    !isnan(bodyTemp) &&
    bodyTemp >= TEMP_HIGH;

  bool heartHigh =
    rateCount >= 3 &&
    averageHR > HR_HIGH;

  bool tabletBuzzer =
    tabletState == TABLET_REMINDER_ACTIVE;

  buzzerOn =
    sosPressed ||
    fallDetected ||
    tempHigh ||
    heartHigh ||
    tabletBuzzer;

  digitalWrite(
    BUZZER_PIN,
    buzzerOn ? HIGH : LOW
  );
}

// ====================================================
// LCD DISPLAY - TWO PAGES
// ====================================================

void updateLCD() {

  unsigned long now = millis();

  if (now - lastLCDUpdate < 250) {
    return;
  }

  lastLCDUpdate = now;

  // --------------------------------
  // ACTIVE TABLET REMINDER SCREEN
  // --------------------------------

  if (tabletState == TABLET_REMINDER_ACTIVE) {

    unsigned long elapsed =
      now - tabletScanStart;

    int remaining =
      (elapsed >= TABLET_SCAN_DURATION)
      ? 0
      : (int)((TABLET_SCAN_DURATION - elapsed + 999) / 1000);

    char scanLine[17];

    snprintf(
      scanLine,
      sizeof(scanLine),
      "SCAN LEFT: %02ds",
      remaining
    );

    lcd.setCursor(0, 0);
    lcd.print("TAKE TABLET     ");

    lcd.setCursor(0, 1);
    lcd.print(scanLine);

    return;
  }

  // --------------------------------
  // TABLET TAKEN RESULT
  // --------------------------------

  if (tabletState == TABLET_TAKEN &&
      now - tabletResultTime < TABLET_RESULT_DURATION) {

    lcd.setCursor(0, 0);
    lcd.print("TABLET TAKEN    ");

    lcd.setCursor(0, 1);
    lcd.print("CARD ACCEPTED   ");

    return;
  }

  // --------------------------------
  // TABLET MISSED RESULT
  // --------------------------------

  if (tabletState == TABLET_MISSED &&
      now - tabletResultTime < TABLET_RESULT_DURATION) {

    lcd.setCursor(0, 0);
    lcd.print("TABLET MISSED   ");

    lcd.setCursor(0, 1);
    lcd.print("CARETAKER ALERT ");

    return;
  }

  // --------------------------------
  // AUTOMATIC PAGE SWITCH
  // --------------------------------

  if (now - lastPageSwitch >= LCD_PAGE_INTERVAL) {

    lastPageSwitch = now;

    lcdPage = !lcdPage;
  }

  // --------------------------------
  // PAGE 1: HEALTH DATA
  // --------------------------------

  if (lcdPage == 0) {

    char line1[17];
    char line2[17];

    int tempInt =
      isnan(bodyTemp)
      ? 0
      : (int)roundf(bodyTemp);

    int bpmInt = (int)roundf(averageHR);

    snprintf(
      line1,
      sizeof(line1),
      "T%d X%+.1f Y%+.1f",
      tempInt,
      accelX,
      accelY
    );

    snprintf(
      line2,
      sizeof(line2),
      "HR:%03d S:%c F:%c",
      bpmInt,
      sosPressed ? 'Y' : 'N',
      fallDetected ? 'Y' : 'N'
    );

    lcd.setCursor(0, 0);
    lcd.print("                ");

    lcd.setCursor(0, 0);
    lcd.print(line1);

    lcd.setCursor(0, 1);
    lcd.print("                ");

    lcd.setCursor(0, 1);
    lcd.print(line2);
  }

  // --------------------------------
  // PAGE 2: REPEATING TABLET COUNTDOWN
  // --------------------------------

  else {

    lcd.setCursor(0, 0);
    lcd.print("TABLET REMINDER ");

    if (tabletState == TABLET_WAITING) {

      unsigned long remaining =
        (now >= tabletNextReminder)
        ? 0
        : tabletNextReminder - now;

      unsigned int totalSeconds =
        (remaining + 999) / 1000;

      unsigned int minutes =
        totalSeconds / 60;

      unsigned int seconds =
        totalSeconds % 60;

      char countdown[17];

      snprintf(
        countdown,
        sizeof(countdown),
        "IN: %02u:%02u",
        minutes,
        seconds
      );

      lcd.setCursor(0, 1);
      lcd.print("                ");

      lcd.setCursor(0, 1);
      lcd.print(countdown);

    } else if (tabletState == TABLET_TAKEN) {

      lcd.setCursor(0, 1);
      lcd.print("TABLET: TAKEN   ");

    } else if (tabletState == TABLET_MISSED) {

      lcd.setCursor(0, 1);
      lcd.print("TABLET: MISSED  ");
    }
  }
}

// ====================================================
// SERIAL DEBUG
// ====================================================

void printDebug() {

  if (millis() - lastDebugPrint < 2000) {
    return;
  }

  lastDebugPrint = millis();

  Serial.print("IR=");
  Serial.print(irValue);

  Serial.print(" BPM=");
  Serial.print(heartRate, 1);

  Serial.print(" AvgHR=");
  Serial.print(averageHR, 1);

  Serial.print(" Finger=");
  Serial.print(fingerDetected);

  Serial.print(" Temp=");

  if (isnan(bodyTemp)) {
    Serial.print("NAN");
  } else {
    Serial.print(bodyTemp, 1);
  }

  Serial.print(" X=");
  Serial.print(accelX, 2);

  Serial.print(" Y=");
  Serial.print(accelY, 2);

  Serial.print(" Fall=");
  Serial.print(fallDetected);

  Serial.print(" SOS=");
  Serial.print(sosPressed);

  Serial.print(" GPS=");
  Serial.print(gpsFix);

  Serial.print(" PN532=");
  Serial.print(pn532OK);

  Serial.print(" TabletState=");
  Serial.println((int)tabletState);
}

// ====================================================
// SETUP
// ====================================================

void setup() {

  Serial.begin(115200);

  delay(500);

  pinMode(SOS_PIN, INPUT_PULLUP);

  pinMode(BUZZER_PIN, OUTPUT);

  digitalWrite(BUZZER_PIN, LOW);

  // I2C
  Wire.begin(I2C_SDA, I2C_SCL);

  Wire.setClock(100000);

  // LCD
  lcd.init();
  lcd.backlight();

  lcd.setCursor(0, 0);
  lcd.print("Elderly Health");

  lcd.setCursor(0, 1);
  lcd.print("Starting...");

  delay(1500);

  // DS18B20
  tempSensor.begin();

  tempSensor.setResolution(10);

  // MAX30102
  maxOK = maxSensor.begin(Wire, I2C_SPEED_FAST);

  if (maxOK) {

    maxSensor.setup();

    maxSensor.setPulseAmplitudeRed(0x0A);
    maxSensor.setPulseAmplitudeIR(0x1F);
    maxSensor.setPulseAmplitudeGreen(0);

    Serial.println("MAX30102 ready");

  } else {

    Serial.println("MAX30102 NOT FOUND");
  }

  // MPU6500
  mpuOK = initMPU6500();

  // PN532
  Serial.println("Starting PN532...");

  nfc.begin();

  uint32_t version = nfc.getFirmwareVersion();

  if (version) {

    pn532OK = true;

    Serial.println("PN532 FOUND!");

    Serial.print("PN532 firmware version: ");

    Serial.print((version >> 16) & 0xFF);

    Serial.print(".");

    Serial.println((version >> 8) & 0xFF);

    nfc.SAMConfig();

    Serial.println("PN532 ready");

  } else {

    pn532OK = false;

    Serial.println("PN532 NOT FOUND!");
  }

  // GSM UART
  GSM.begin(
    9600,
    SERIAL_8N1,
    GSM_RX_PIN,
    GSM_TX_PIN
  );

  // GPS UART
  GPSSerial.begin(
    9600,
    SERIAL_8N1,
    GPS_RX_PIN,
    GPS_TX_PIN
  );

  delay(1000);

  GSM.println("AT");
  delay(300);

  GSM.println("ATE0");
  delay(300);

  GSM.println("AT+CMGF=1");
  delay(300);

  tempSensor.requestTemperatures();

  // FIRST TABLET COUNTDOWN STARTS HERE
  tabletNextReminder =
    millis() + TABLET_REMINDER_DELAY;

  lcd.clear();

  Serial.println();
  Serial.println("SYSTEM STARTED");

  Serial.println("Serial Monitor: 115200");

  Serial.println("First tablet reminder in 2 minutes.");

  Serial.println("Next reminders repeat every 2 minutes after each result.");
}

// ====================================================
// MAIN LOOP
// ====================================================

void loop() {

  updateGPS();

  updateTemperature();

  updateHeartRate();

  updateFallDetection();

  updateSOSButton();

  updateTabletReminder();

  updateBuzzer();

  updateLCD();

  processPendingAlert();

  printDebug();

  if (millis() - lastApiPost >= API_POST_INTERVAL) {

    lastApiPost = millis();

    sendHealthData();
  }
}