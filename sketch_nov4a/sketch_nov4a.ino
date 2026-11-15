/*
 * ======================================================================================
 * Smart Vehicle Lighting System - ESP32-CAM MJPEG Video Streamer
 * ======================================================================================
 * 
 * Target Hardware: AI-Thinker ESP32-CAM (OV2640 Camera Module)
 * 
 * Features:
 * - Streams continuous high-frame-rate MJPEG over HTTP on Port 81 (:81/stream)
 * - Serves single frame snapshots on Port 80 (/capture)
 * - Standard 640x480 VGA resolution matching Python config.yaml
 * - Status indicator LED & Serial diagnostics
 * 
 * How to Flash ("Dump") onto ESP32-CAM:
 * 1. Connect FTDI USB-to-TTL programmer to ESP32-CAM:
 *    - FTDI 5V  <---> ESP32-CAM 5V (or 3.3V)
 *    - FTDI GND <---> ESP32-CAM GND
 *    - FTDI RX  <---> ESP32-CAM U0T (GPIO 1)
 *    - FTDI TX  <---> ESP32-CAM U0R (GPIO 3)
 * 2. CRITICAL: Bridge GPIO 0 to GND with a jumper wire to enter Flashing/Bootloader mode.
 * 3. Press the RST button on the back of the ESP32-CAM.
 * 4. In Arduino IDE:
 *    - Board: "AI Thinker ESP32-CAM"
 *    - CPU Frequency: "240MHz (WiFi/BT)"
 *    - Flash Frequency: "80MHz"
 *    - Flash Mode: "QIO"
 *    - Partition Scheme: "Huge APP (3MB No OTA/1MB SPIFFS)"
 *    - Upload Speed: "115200" or "460800"
 *    - Port: Select your FTDI COM port
 * 5. Update your Wi-Fi SSID and Password below, then click Upload.
 * 6. After uploading finishes:
 *    - Remove the GPIO 0 to GND jumper.
 *    - Press the RST button once to boot into normal streaming mode.
 *    - Open Serial Monitor (115200 baud) to view the assigned IP address.
 * ======================================================================================
 */

#include "esp_camera.h"
#include <WiFi.h>
#include "esp_http_server.h"

// ----------------- WI-FI CREDENTIALS -----------------
// Change these to match your local Wi-Fi router or mobile hotspot
const char* ssid     = "Harish_047";
const char* password = "Harish@4000";

// ----------------- CAMERA PIN CONFIGURATION (AI-THINKER) -----------------
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27

#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

#define FLASH_LED_PIN      4   // Onboard bright flash LED (optional)
#define STATUS_LED_PIN    33   // Small red indicator LED (Active LOW)

// ----------------- SERVER HANDLERS -----------------
httpd_handle_t stream_httpd = NULL;
httpd_handle_t camera_httpd = NULL;

#define PART_BOUNDARY "123456789000000000000987654321"
static const char* _STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char* _STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
static const char* _STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

// MJPEG Stream Handler on :81/stream
static esp_err_t stream_handler(httpd_req_t *req) {
  camera_fb_t * fb = NULL;
  esp_err_t res = ESP_OK;
  size_t _jpg_buf_len = 0;
  uint8_t * _jpg_buf = NULL;
  char * part_buf[64];

  res = httpd_resp_set_type(req, _STREAM_CONTENT_TYPE);
  if (res != ESP_OK) return res;

  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");

  while (true) {
    fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("[ERROR] Camera frame capture failed");
      res = ESP_FAIL;
      break;
    }

    _jpg_buf_len = fb->len;
    _jpg_buf = fb->buf;

    if (res == ESP_OK) {
      res = httpd_resp_send_chunk(req, _STREAM_BOUNDARY, strlen(_STREAM_BOUNDARY));
    }
    if (res == ESP_OK) {
      size_t hlen = snprintf((char *)part_buf, 64, _STREAM_PART, _jpg_buf_len);
      res = httpd_resp_send_chunk(req, (const char *)part_buf, hlen);
    }
    if (res == ESP_OK) {
      res = httpd_resp_send_chunk(req, (const char *)_jpg_buf, _jpg_buf_len);
    }

    esp_camera_fb_return(fb);
    fb = NULL;
    _jpg_buf = NULL;

    if (res != ESP_OK) {
      break;
    }
  }
  return res;
}

// Single Snapshot Handler on :80/capture
static esp_err_t capture_handler(httpd_req_t *req) {
  camera_fb_t * fb = esp_camera_fb_get();
  if (!fb) {
    httpd_resp_send_500(req);
    return ESP_FAIL;
  }

  httpd_resp_set_type(req, "image/jpeg");
  httpd_resp_set_hdr(req, "Content-Disposition", "inline; filename=capture.jpg");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");

  esp_err_t res = httpd_resp_send(req, (const char *)fb->buf, fb->len);
  esp_camera_fb_return(fb);
  return res;
}

void startCameraServer() {
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();

  // 1. Port 80 for single snapshots
  config.server_port = 80;
  config.ctrl_port = 32768;
  httpd_uri_t capture_uri = {
    .uri       = "/capture",
    .method    = HTTP_GET,
    .handler   = capture_handler,
    .user_ctx  = NULL
  };
  if (httpd_start(&camera_httpd, &config) == ESP_OK) {
    httpd_register_uri_handler(camera_httpd, &capture_uri);
  }

  // 2. Port 81 for high-speed continuous MJPEG stream
  config.server_port = 81;
  config.ctrl_port = 32769;
  httpd_uri_t stream_uri = {
    .uri       = "/stream",
    .method    = HTTP_GET,
    .handler   = stream_handler,
    .user_ctx  = NULL
  };
  if (httpd_start(&stream_httpd, &config) == ESP_OK) {
    httpd_register_uri_handler(stream_httpd, &stream_uri);
  }
}

void setup() {
  Serial.begin(115200);
  Serial.println("\n\n==========================================");
  Serial.println("ESP32-CAM Smart Lighting Video Streamer");
  Serial.println("==========================================");

  pinMode(STATUS_LED_PIN, OUTPUT);
  digitalWrite(STATUS_LED_PIN, LOW); // LED ON while initializing

  // Configure Camera Parameters
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0       = Y2_GPIO_NUM;
  config.pin_d1       = Y3_GPIO_NUM;
  config.pin_d2       = Y4_GPIO_NUM;
  config.pin_d3       = Y5_GPIO_NUM;
  config.pin_d4       = Y6_GPIO_NUM;
  config.pin_d5       = Y7_GPIO_NUM;
  config.pin_d6       = Y8_GPIO_NUM;
  config.pin_d7       = Y9_GPIO_NUM;
  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  // Frame resolution: VGA (640x480) matching Python system
  if (psramFound()) {
    config.frame_size = FRAMESIZE_VGA;
    config.jpeg_quality = 12; // 0-63, lower means higher quality
    config.fb_count = 2;
    config.grab_mode = CAMERA_GRAB_LATEST;
    Serial.println("[OK] PSRAM detected; dual buffering enabled");
  } else {
    config.frame_size = FRAMESIZE_CIF;
    config.jpeg_quality = 14;
    config.fb_count = 1;
    Serial.println("[WARN] No PSRAM found; fallback resolution applied");
  }

  // Camera Initialization
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[FATAL] Camera init failed with error 0x%x\n", err);
    digitalWrite(STATUS_LED_PIN, HIGH);
    return;
  }
  Serial.println("[OK] OV2640 camera initialized successfully");

  // Sensor fine-tuning for night road conditions
  sensor_t * s = esp_camera_sensor_get();
  if (s != NULL) {
    s->set_brightness(s, 1);     // -2 to 2 (slight boost for nighttime)
    s->set_contrast(s, 1);       // -2 to 2
    s->set_saturation(s, 0);     // -2 to 2
    s->set_whitebal(s, 1);       // 0 = disable , 1 = enable
    s->set_awb_gain(s, 1);       // 0 = disable , 1 = enable
    s->set_wb_mode(s, 0);        // 0 to 4 - 0: Auto
    s->set_exposure_ctrl(s, 1);  // 0 = disable , 1 = enable
    s->set_aec2(s, 0);           // 0 = disable , 1 = enable
    s->set_gain_ctrl(s, 1);      // 0 = disable , 1 = enable
    s->set_agc_gain(s, 0);       // 0 to 30
    s->set_gainceiling(s, (gainceiling_t)2);  // 0 to 6
  }

  // Wi-Fi Connection
  Serial.printf("Connecting to Wi-Fi '%s'...", ssid);
  WiFi.begin(ssid, password);
  WiFi.setSleep(false);

  int wifi_retries = 0;
  while (WiFi.status() != WL_CONNECTED && wifi_retries < 40) {
    delay(500);
    Serial.print(".");
    wifi_retries++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[SUCCESS] Wi-Fi Connected!");
    Serial.print("Assigned IP Address: ");
    Serial.println(WiFi.localIP());
    Serial.println("\nUse these URLs in smart_vehicle_lighting/config/config.yaml:");
    Serial.printf("  stream_url:  http://%s:81/stream\n", WiFi.localIP().toString().c_str());
    Serial.printf("  capture_url: http://%s/capture\n\n", WiFi.localIP().toString().c_str());

    startCameraServer();
    digitalWrite(STATUS_LED_PIN, HIGH); // LED OFF when ready
  } else {
    Serial.println("\n[ERROR] Failed to connect to Wi-Fi. Check SSID/Password.");
  }
}

void loop() {
  // Streaming server handles frames asynchronously via FreeRTOS tasks
  delay(1000);
}

