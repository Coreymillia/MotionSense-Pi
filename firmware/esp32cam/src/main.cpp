#include <Arduino.h>
#include <WebServer.h>
#include <WiFi.h>
#include <WiFiManager.h>
#include "esp_camera.h"

#define PWDN_GPIO_NUM 32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 0
#define SIOD_GPIO_NUM 26
#define SIOC_GPIO_NUM 27
#define Y9_GPIO_NUM 35
#define Y8_GPIO_NUM 34
#define Y7_GPIO_NUM 39
#define Y6_GPIO_NUM 36
#define Y5_GPIO_NUM 21
#define Y4_GPIO_NUM 19
#define Y3_GPIO_NUM 18
#define Y2_GPIO_NUM 5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM 23
#define PCLK_GPIO_NUM 22
#define WIFI_RESET_GPIO_NUM 13

namespace {

WebServer server(80);
WiFiManager wifiManager;
uint32_t captureCount = 0;
String deviceName;

String makeDeviceName() {
    uint64_t chipId = ESP.getEfuseMac();
    char suffix[7];
    snprintf(suffix, sizeof(suffix), "%06llX", chipId & 0xFFFFFF);
    return String("motionsense-cam-") + suffix;
}

String makeSetupSsid() {
    return deviceName + "-setup";
}

bool shouldResetWifiOnBoot() {
    pinMode(WIFI_RESET_GPIO_NUM, INPUT_PULLUP);
    delay(20);
    return digitalRead(WIFI_RESET_GPIO_NUM) == LOW;
}

bool initCamera() {
    camera_config_t cfg = {};
    cfg.ledc_channel = LEDC_CHANNEL_0;
    cfg.ledc_timer = LEDC_TIMER_0;
    cfg.pin_d0 = Y2_GPIO_NUM;
    cfg.pin_d1 = Y3_GPIO_NUM;
    cfg.pin_d2 = Y4_GPIO_NUM;
    cfg.pin_d3 = Y5_GPIO_NUM;
    cfg.pin_d4 = Y6_GPIO_NUM;
    cfg.pin_d5 = Y7_GPIO_NUM;
    cfg.pin_d6 = Y8_GPIO_NUM;
    cfg.pin_d7 = Y9_GPIO_NUM;
    cfg.pin_xclk = XCLK_GPIO_NUM;
    cfg.pin_pclk = PCLK_GPIO_NUM;
    cfg.pin_vsync = VSYNC_GPIO_NUM;
    cfg.pin_href = HREF_GPIO_NUM;
    cfg.pin_sccb_sda = SIOD_GPIO_NUM;
    cfg.pin_sccb_scl = SIOC_GPIO_NUM;
    cfg.pin_pwdn = PWDN_GPIO_NUM;
    cfg.pin_reset = RESET_GPIO_NUM;
    cfg.xclk_freq_hz = 20000000;
    cfg.pixel_format = PIXFORMAT_JPEG;
    cfg.frame_size = psramFound() ? FRAMESIZE_VGA : FRAMESIZE_QVGA;
    cfg.jpeg_quality = psramFound() ? 10 : 12;
    cfg.fb_count = psramFound() ? 2 : 1;
    cfg.grab_mode = psramFound() ? CAMERA_GRAB_LATEST : CAMERA_GRAB_WHEN_EMPTY;

    esp_err_t err = esp_camera_init(&cfg);
    if (err != ESP_OK) {
        Serial.printf("[CAM] Camera init failed: 0x%x\n", err);
        return false;
    }

    sensor_t *sensor = esp_camera_sensor_get();
    sensor->set_vflip(sensor, 1);
    sensor->set_hmirror(sensor, 0);
    sensor->set_brightness(sensor, 1);
    sensor->set_saturation(sensor, -1);
    return true;
}

void handleStatus() {
    String json = "{";
    json += "\"type\":\"cam\",";
    json += "\"count\":" + String(captureCount) + ",";
    json += "\"ip\":\"" + WiFi.localIP().toString() + "\",";
    json += "\"ssid\":\"" + WiFi.SSID() + "\",";
    json += "\"hostname\":\"" + deviceName + "\"";
    json += "}";
    server.send(200, "application/json", json);
}

void handleLatestJpeg() {
    camera_fb_t *frame = esp_camera_fb_get();
    if (frame == nullptr) {
        server.send(500, "text/plain", "Camera capture failed");
        return;
    }

    captureCount++;
    server.sendHeader("Content-Type", "image/jpeg");
    server.sendHeader("Content-Length", String(frame->len));
    server.sendHeader("Cache-Control", "no-cache, no-store, must-revalidate");
    server.sendHeader("Pragma", "no-cache");
    server.sendHeader("Expires", "0");
    server.send_P(200, "image/jpeg", reinterpret_cast<const char *>(frame->buf), frame->len);
    Serial.printf("[CAM] Frame #%u served (%u bytes)\n", captureCount, frame->len);
    esp_camera_fb_return(frame);
}

void handleRoot() {
    String html;
    html += "<!doctype html><html><head><meta charset='utf-8'><title>MotionSense ESP32-CAM</title></head><body>";
    html += "<h2>MotionSense ESP32-CAM</h2>";
    html += "<p><strong>Hostname:</strong> " + deviceName + "</p>";
    html += "<p><strong>IP:</strong> " + WiFi.localIP().toString() + "</p>";
    html += "<p><strong>WiFi:</strong> " + WiFi.SSID() + "</p>";
    html += "<p><a href='/latest.jpg'>Latest JPEG</a> | <a href='/status'>Status JSON</a> | <a href='/wifi/reset'>Reset WiFi</a></p>";
    html += "<img id='frame' src='/latest.jpg' style='max-width:100%;height:auto'>";
    html += "<script>setInterval(()=>{document.getElementById('frame').src='/latest.jpg?'+Date.now()},1500)</script>";
    html += "</body></html>";
    server.send(200, "text/html", html);
}

void handleWifiReset() {
    server.send(200, "text/plain", "Clearing WiFi settings and rebooting.");
    delay(250);
    wifiManager.resetSettings();
    ESP.restart();
}

void connectWifi() {
    wifiManager.setHostname(deviceName.c_str());
    wifiManager.setConfigPortalTimeout(180);
    wifiManager.setConnectTimeout(20);
    wifiManager.setAPClientCheck(true);
    wifiManager.setShowInfoUpdate(false);

    String setupSsid = makeSetupSsid();
    Serial.printf("[NET] Starting WiFiManager with AP '%s'\n", setupSsid.c_str());

    bool connected = wifiManager.autoConnect(setupSsid.c_str());
    if (!connected) {
        Serial.println("[NET] WiFi setup failed or timed out. Rebooting.");
        delay(1000);
        ESP.restart();
    }

    Serial.print("[NET] Connected to ");
    Serial.println(WiFi.SSID());
    Serial.print("[NET] IP address: ");
    Serial.println(WiFi.localIP());
}

void configureHttp() {
    server.on("/", HTTP_GET, handleRoot);
    server.on("/status", HTTP_GET, handleStatus);
    server.on("/latest.jpg", HTTP_GET, handleLatestJpeg);
    server.on("/wifi/reset", HTTP_GET, handleWifiReset);
    server.begin();
    Serial.println("[HTTP] Server started");
}

}  // namespace

void setup() {
    Serial.begin(115200);
    delay(250);
    deviceName = makeDeviceName();

    Serial.println();
    Serial.println("[BOOT] MotionSense ESP32-CAM starting");
    Serial.printf("[BOOT] Device name: %s\n", deviceName.c_str());
    Serial.printf("[BOOT] Hold GPIO%d to GND during boot to clear WiFi.\n", WIFI_RESET_GPIO_NUM);

    if (!initCamera()) {
        Serial.println("[BOOT] Camera init failed. Halting.");
        while (true) {
            delay(1000);
        }
    }

    if (shouldResetWifiOnBoot()) {
        Serial.printf("[BOOT] GPIO%d held LOW. Clearing saved WiFi settings.\n", WIFI_RESET_GPIO_NUM);
        wifiManager.resetSettings();
        delay(250);
    }

    connectWifi();
    configureHttp();
}

void loop() {
    if (WiFi.status() != WL_CONNECTED) {
        static unsigned long lastReconnectAt = 0;
        if (millis() - lastReconnectAt >= 5000) {
            lastReconnectAt = millis();
            Serial.println("[NET] WiFi lost. Attempting reconnect.");
            WiFi.reconnect();
        }
    }

    server.handleClient();
}
