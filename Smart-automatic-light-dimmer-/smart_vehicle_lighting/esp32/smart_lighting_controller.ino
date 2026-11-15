/*
 * Smart Vehicle Lighting System - ESP32 DevKit Controller
 * 
 * Hardware Connections:
 * - Relay Module Control: GPIO 26 (Active LOW: LOW = Low Beam, HIGH = Normal/High Beam)
 * - 16x2 I2C LCD:         SDA = GPIO 21, SCL = GPIO 22, Address = 0x27 (or 0x3F)
 * - Serial Communication: USB UART @ 115200 baud
 *
 * NOTE: 
 * - LDR and Ultrasonic sensors are NOT used.
 * - All light intensity analysis, distance estimation, and obstacle detection 
 *   are performed in real time by the AI vision pipeline on host PC.
 * - The ESP32 receives commands ("CMD:LOW", "CMD:NORMAL") and display updates
 *   ("DISP:L=<val>,D=<dist>,B=<beam>") over USB serial.
 * - No automatic periodic switching. Beam state changes ONLY upon verified commands.
 */

#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// ---------------- PIN ASSIGNMENTS ----------------
#define RELAY_PIN     26
#define I2C_SDA_PIN   21
#define I2C_SCL_PIN   22

// ---------------- HARDWARE POLARITY ----------------
// Relay polarity (Active-LOW relay module)
#define RELAY_LOW_BEAM     LOW
#define RELAY_NORMAL_BEAM  HIGH

// ---------------- TIMING & THRESHOLDS ----------------
const unsigned long SERIAL_TIMEOUT_MS = 3500;   // Watchdog timeout
const unsigned long LCD_INTERVAL_MS    = 200;   // Refresh LCD every 200ms

// ---------------- OBJECTS & STATE ----------------
LiquidCrystal_I2C lcd(0x27, 16, 2);

enum BeamState {
  STATE_NORMAL_BEAM = 0,
  STATE_LOW_BEAM    = 1
};

BeamState currentBeam = STATE_NORMAL_BEAM;
bool isHostConnected = false;
unsigned long lastSerialRxTime = 0;
unsigned long lastLcdUpdateTime = 0;

// LCD Display cache
int displayLightIntensity = 0;
String displayDistance = "--m";
String currentBeamStr = "NORMAL";

String serialRxBuffer = "";

// ---------------- RELAY CONTROL ----------------
void applyBeamState(BeamState state) {
  currentBeam = state;
  if (state == STATE_LOW_BEAM) {
    digitalWrite(RELAY_PIN, RELAY_LOW_BEAM);
    currentBeamStr = "LOW";
  } else {
    digitalWrite(RELAY_PIN, RELAY_NORMAL_BEAM);
    currentBeamStr = "NORMAL";
  }
}

// ---------------- LCD DISPLAY ----------------
void updateLCD() {
  lcd.setCursor(0, 0);
  if (isHostConnected) {
    lcd.print("LIGHT:");
    if (displayLightIntensity < 10) lcd.print("  ");
    else if (displayLightIntensity < 100) lcd.print(" ");
    lcd.print(displayLightIntensity);
    lcd.print(" [AI-ON]");
  } else {
    lcd.print("STANDBY [NO PC] ");
  }

  lcd.setCursor(0, 1);
  lcd.print("D:");
  lcd.print(displayDistance);
  // Pad distance
  for (int i = displayDistance.length(); i < 5; i++) lcd.print(" ");

  lcd.print("B:");
  if (currentBeam == STATE_LOW_BEAM) {
    lcd.print("LOW   ");
  } else {
    lcd.print("NORMAL");
  }
}

// ---------------- SERIAL COMMAND PROCESSING ----------------
void processSerialCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;

  lastSerialRxTime = millis();
  isHostConnected = true;

  String cmdUpper = cmd;
  cmdUpper.toUpperCase();

  // 1. Direct Beam Switching Commands
  if (cmdUpper == "CMD:LOW" || cmdUpper == "LOW" || cmdUpper == "SET:LOW") {
    applyBeamState(STATE_LOW_BEAM);
    Serial.println("ACK:LOW");
  } 
  else if (cmdUpper == "CMD:NORMAL" || cmdUpper == "NORMAL" || cmdUpper == "SET:NORMAL" || cmdUpper == "NORM") {
    applyBeamState(STATE_NORMAL_BEAM);
    Serial.println("ACK:NORMAL");
  }
  else if (cmdUpper == "PING") {
    Serial.println("PONG");
  }
  else if (cmdUpper == "STATUS") {
    Serial.print("STATUS:BEAM=");
    Serial.print(currentBeam == STATE_LOW_BEAM ? "LOW" : "NORMAL");
    Serial.println(",AI=CONNECTED");
  }
  // 2. Telemetry Display Payload from Python: "DISP:L=<0-255>,D=<dist>,B=<LOW|NORMAL>"
  else if (cmdUpper.startsWith("DISP:")) {
    String payload = cmd.substring(5);
    int p1 = payload.indexOf("L=");
    int p2 = payload.indexOf(",D=");
    int p3 = payload.indexOf(",B=");

    if (p1 != -1 && p2 != -1) {
      displayLightIntensity = payload.substring(p1 + 2, p2).toInt();
    }
    if (p2 != -1 && p3 != -1) {
      displayDistance = payload.substring(p2 + 3, p3);
    }
    if (p3 != -1) {
      String b = payload.substring(p3 + 3);
      b.trim();
      b.toUpperCase();
      if (b == "LOW" && currentBeam != STATE_LOW_BEAM) {
        applyBeamState(STATE_LOW_BEAM);
      } else if (b == "NORMAL" && currentBeam != STATE_NORMAL_BEAM) {
        applyBeamState(STATE_NORMAL_BEAM);
      }
    }
  }
  else {
    Serial.print("ERR:UNKNOWN_CMD:");
    Serial.println(cmd);
  }
}

// ---------------- SETUP ----------------
void setup() {
  Serial.begin(115200);

  pinMode(RELAY_PIN, OUTPUT);

  // Default initial state: Normal Beam
  applyBeamState(STATE_NORMAL_BEAM);

  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  lcd.init();
  lcd.backlight();

  lcd.setCursor(0, 0);
  lcd.print("AI LIGHT SYSTEM");
  lcd.setCursor(0, 1);
  lcd.print("READY (NO LDR)  ");
  delay(1200);
  lcd.clear();

  Serial.println("SYSTEM:READY Smart Vehicle Lighting Controller v3.0 (Pure Vision)");
  lastSerialRxTime = 0;
}

// ---------------- MAIN LOOP ----------------
void loop() {
  unsigned long now = millis();

  // 1. Non-blocking Serial Reception
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (serialRxBuffer.length() > 0) {
        processSerialCommand(serialRxBuffer);
        serialRxBuffer = "";
      }
    } else {
      if (serialRxBuffer.length() < 64) {
        serialRxBuffer += c;
      }
    }
  }

  // 2. Watchdog Check
  if (lastSerialRxTime > 0 && (now - lastSerialRxTime > SERIAL_TIMEOUT_MS)) {
    isHostConnected = false;
    // When PC disconnects, maintain stable Normal Beam safely (no 2s toggling)
    applyBeamState(STATE_NORMAL_BEAM);
    displayDistance = "--m";
  }

  // 3. Periodic LCD Update
  if (now - lastLcdUpdateTime >= LCD_INTERVAL_MS) {
    lastLcdUpdateTime = now;
    updateLCD();
  }

  delay(5);
}
