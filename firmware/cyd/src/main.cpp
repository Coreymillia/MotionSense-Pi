#include <Arduino.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <SPI.h>
#include <WiFi.h>
#include <WiFiManager.h>
#include <ArduinoJson.h>
#include <Arduino_GFX_Library.h>
#include <JPEGDEC.h>
#include <XPT2046_Touchscreen.h>

#define GFX_BL 21
#define XPT2046_IRQ 36
#define XPT2046_CS 33
#define XPT2046_CLK 25
#define XPT2046_MOSI 32
#define XPT2046_MISO 39
#define CYD_BOOT_BUTTON_GPIO 0

namespace {

constexpr int SCREEN_W = 320;
constexpr int SCREEN_H = 240;
constexpr int HEADER_H = 24;
constexpr int IMAGE_X = 8;
constexpr int IMAGE_Y = HEADER_H + 6;
constexpr int IMAGE_W = 304;
constexpr int IMAGE_H = 172;
constexpr int FOOTER_Y = 206;
constexpr int BUTTON_H = 28;
constexpr unsigned long STATUS_REFRESH_MS = 5000;
constexpr size_t MAX_PREVIEW_BYTES = 65536;
constexpr int PREVIEW_QUALITY = 60;

constexpr uint16_t C_BG = 0x0000;
constexpr uint16_t C_PANEL = 0x1082;
constexpr uint16_t C_DIM = 0x528A;
constexpr uint16_t C_WHITE = 0xFFFF;
constexpr uint16_t C_GREEN = 0x07E0;
constexpr uint16_t C_RED = 0xF800;
constexpr uint16_t C_BLUE = 0x039F;
constexpr uint16_t C_CYAN = 0x07FF;
constexpr uint16_t C_ORANGE = 0xFD20;
constexpr uint16_t C_YELLOW = 0xFFE0;

Arduino_DataBus *bus = new Arduino_HWSPI(2, 15, 14, 13, 12);
Arduino_GFX *gfx = new Arduino_ILI9341(bus, GFX_NOT_DEFINED, 1);
SPIClass touchSPI(VSPI);
XPT2046_Touchscreen ts(XPT2046_CS, XPT2046_IRQ);
Preferences prefs;
WiFiManager wifiManager;
WiFiManagerParameter piUrlParam("pi_url", "MotionSense Pi URL", "", 96);
JPEGDEC jpeg;
bool shouldSaveConfig = false;

struct TouchButton {
    const char *label;
    int x;
    int y;
    int w;
    int h;
    uint16_t bg;
};

struct CameraSource {
    String sourceId;
    String label;
    bool available = false;
    bool selected = false;
};

struct MotionEvent {
    String detectedAt;
    String snapshotUrl;
    float score = 0.0f;
};

struct AppState {
    bool wifiOnline = false;
    bool apiOnline = false;
    String piBaseUrl;
    String host;
    String activeSourceLabel;
    String activeSourceId;
    String latestSnapshotUrl;
    String latestSnapshotModifiedAt;
    bool snapshotAvailable = false;
    std::vector<CameraSource> sources;
    std::vector<MotionEvent> events;
    int eventIndex = -1;
    String statusMessage = "Booting...";
    String statusDetail;
    unsigned long statusUntil = 0;
    unsigned long lastStatusFetchMs = 0;
    bool screenDirty = true;
    bool imageDirty = true;
    bool touchWasDown = false;
} state;

TouchButton btnPrev = {"PREV", 8, FOOTER_Y, 56, BUTTON_H, 0x0018};
TouchButton btnLive = {"LIVE", 70, FOOTER_Y, 56, BUTTON_H, 0x0210};
TouchButton btnNext = {"NEXT", 132, FOOTER_Y, 56, BUTTON_H, 0x4208};
TouchButton btnCam = {"CAM", 194, FOOTER_Y, 56, BUTTON_H, 0x6000};
TouchButton btnWifi = {"WIFI", 256, FOOTER_Y, 56, BUTTON_H, 0x4208};

void setMessage(const String &message, unsigned long ms = 2200, const String &detail = "") {
    state.statusMessage = message;
    state.statusDetail = detail;
    state.statusUntil = millis() + ms;
    state.screenDirty = true;
}

bool pointInButton(const TouchButton &button, int tx, int ty) {
    return tx >= button.x && tx <= (button.x + button.w) &&
           ty >= button.y && ty <= (button.y + button.h);
}

void mapTouch(uint16_t rx, uint16_t ry, int &sx, int &sy) {
    sx = constrain(map(rx, 200, 3900, 0, SCREEN_W), 0, SCREEN_W - 1);
    sy = constrain(map(ry, 240, 3900, 0, SCREEN_H), 0, SCREEN_H - 1);
}

String normalizeBaseUrl(const char *raw) {
    String value = String(raw ? raw : "");
    value.trim();
    if (!value.length()) {
        return "";
    }
    if (!value.startsWith("http://") && !value.startsWith("https://")) {
        value = "http://" + value;
    }
    int schemeIndex = value.indexOf("://");
    int hostStart = schemeIndex >= 0 ? schemeIndex + 3 : 0;
    int pathStart = value.indexOf('/', hostStart);
    String hostPort = pathStart >= 0 ? value.substring(hostStart, pathStart) : value.substring(hostStart);
    if (!hostPort.length()) {
        return "";
    }

    if (hostPort.indexOf(':') < 0) {
        hostPort += ":8080";
    }

    return value.substring(0, hostStart) + hostPort;
}

bool splitBaseUrl(const String &baseUrl, String &host, uint16_t &port) {
    if (!baseUrl.length()) {
        return false;
    }

    int schemeIndex = baseUrl.indexOf("://");
    int hostStart = schemeIndex >= 0 ? schemeIndex + 3 : 0;
    int hostEnd = baseUrl.indexOf('/', hostStart);
    if (hostEnd < 0) {
        hostEnd = baseUrl.length();
    }

    String hostPort = baseUrl.substring(hostStart, hostEnd);
    if (!hostPort.length()) {
        return false;
    }

    int colonIndex = hostPort.lastIndexOf(':');
    if (colonIndex >= 0) {
        host = hostPort.substring(0, colonIndex);
        port = static_cast<uint16_t>(hostPort.substring(colonIndex + 1).toInt());
        return host.length() > 0 && port > 0;
    }

    host = hostPort;
    port = baseUrl.startsWith("https://") ? 443 : 80;
    return true;
}

void loadConfig() {
    prefs.begin("motionsense", true);
    state.piBaseUrl = prefs.getString("pi_url", "");
    prefs.end();
    state.piBaseUrl = normalizeBaseUrl(state.piBaseUrl.c_str());
    Serial.printf("[CFG] loaded pi_url='%s'\n", state.piBaseUrl.c_str());
    if (state.piBaseUrl.length()) {
        piUrlParam.setValue(state.piBaseUrl.c_str(), 96);
    }
}

void saveConfig() {
    state.piBaseUrl = normalizeBaseUrl(piUrlParam.getValue());
    piUrlParam.setValue(state.piBaseUrl.c_str(), 96);
    prefs.begin("motionsense", false);
    prefs.putString("pi_url", state.piBaseUrl);
    prefs.end();
    Serial.printf("[CFG] saved pi_url='%s'\n", state.piBaseUrl.c_str());
}

void markConfigForSave() {
    shouldSaveConfig = true;
    Serial.println("[CFG] portal requested config save");
}

void drawButton(const TouchButton &button) {
    gfx->fillRoundRect(button.x, button.y, button.w, button.h, 6, button.bg);
    gfx->drawRoundRect(button.x, button.y, button.w, button.h, 6, C_WHITE);
    gfx->setTextColor(C_WHITE, button.bg);
    gfx->setTextSize(1);
    int tx = button.x + (button.w - (strlen(button.label) * 6)) / 2;
    gfx->setCursor(tx, button.y + 10);
    gfx->print(button.label);
}

void drawWrapped(const String &text, int x, int y, int maxChars, uint16_t fg, uint16_t bg, int maxLines = 2) {
    gfx->setTextColor(fg, bg);
    gfx->setTextSize(1);
    if (!text.length()) {
        gfx->setCursor(x, y);
        gfx->print("-");
        return;
    }

    int pos = 0;
    for (int line = 0; line < maxLines && pos < text.length(); line++) {
        int take = min(maxChars, static_cast<int>(text.length()) - pos);
        if (take > 0 && pos + take < text.length()) {
            int split = take;
            while (split > 12 && text[pos + split] != ' ') {
                split--;
            }
            if (split > 12) {
                take = split;
            }
        }
        String slice = text.substring(pos, pos + take);
        slice.trim();
        gfx->setCursor(x, y + line * 11);
        gfx->print(slice);
        pos += take;
    }
}

void drawHeader() {
    gfx->fillRect(0, 0, SCREEN_W, HEADER_H, C_BLUE);
    gfx->setTextColor(C_WHITE, C_BLUE);
    gfx->setTextSize(1);
    gfx->setCursor(8, 8);
    gfx->print("MotionSense CYD");
    gfx->setCursor(124, 8);
    gfx->print(state.activeSourceLabel.length() ? state.activeSourceLabel : "No camera");
    gfx->fillCircle(304, 12, 4, state.apiOnline ? C_GREEN : C_RED);
    gfx->drawCircle(304, 12, 4, C_WHITE);
}

void drawFooter() {
    drawButton(btnPrev);
    drawButton(btnLive);
    drawButton(btnNext);
    drawButton(btnCam);
    drawButton(btnWifi);

    gfx->fillRect(0, SCREEN_H - 6, SCREEN_W, 6, C_BG);
    gfx->setTextColor(C_DIM, C_BG);
    gfx->setTextSize(1);
    gfx->setCursor(8, SCREEN_H - 12);
    if (state.statusUntil > millis()) {
        gfx->print(state.statusMessage);
    } else if (state.piBaseUrl.length()) {
        gfx->print(state.piBaseUrl);
    } else {
        gfx->print("Configure MotionSense Pi URL via WiFi portal");
    }
}

void clearImageArea(const String &title, const String &subtitle) {
    gfx->fillRoundRect(IMAGE_X, IMAGE_Y, IMAGE_W, IMAGE_H, 8, C_PANEL);
    gfx->drawRoundRect(IMAGE_X, IMAGE_Y, IMAGE_W, IMAGE_H, 8, C_DIM);
    gfx->setTextColor(C_CYAN, C_PANEL);
    gfx->setTextSize(1);
    gfx->setCursor(IMAGE_X + 10, IMAGE_Y + 12);
    gfx->print(title);
    gfx->setTextColor(C_WHITE, C_PANEL);
    drawWrapped(subtitle, IMAGE_X + 10, IMAGE_Y + 30, 40, C_WHITE, C_PANEL, 4);
}

void drawStatusText() {
    gfx->fillRect(IMAGE_X, IMAGE_Y + IMAGE_H + 2, IMAGE_W, 18, C_BG);
    gfx->setTextColor(C_WHITE, C_BG);
    gfx->setTextSize(1);
    gfx->setCursor(IMAGE_X, IMAGE_Y + IMAGE_H + 8);

    if (state.eventIndex >= 0 && state.eventIndex < static_cast<int>(state.events.size())) {
        gfx->print("Event ");
        gfx->print(state.eventIndex + 1);
        gfx->print("/");
        gfx->print(state.events.size());
        gfx->print("  score ");
        gfx->print(state.events[state.eventIndex].score, 1);
    } else {
        gfx->print("Live snapshot");
    }
}

int jpegDrawCallback(JPEGDRAW *draw) {
    gfx->draw16bitRGBBitmap(draw->x, draw->y, reinterpret_cast<uint16_t *>(draw->pPixels), draw->iWidth, draw->iHeight);
    return 1;
}

bool drawJpegFromBuffer(const uint8_t *buffer, size_t length) {
    if (!jpeg.openRAM(const_cast<uint8_t *>(buffer), length, jpegDrawCallback)) {
        return false;
    }

    int scale = 0;
    int width = jpeg.getWidth();
    int height = jpeg.getHeight();
    if (width <= IMAGE_W && height <= IMAGE_H) {
        scale = 0;
    } else if ((width / 2) <= IMAGE_W && (height / 2) <= IMAGE_H) {
        scale = JPEG_SCALE_HALF;
    } else if ((width / 4) <= IMAGE_W && (height / 4) <= IMAGE_H) {
        scale = JPEG_SCALE_QUARTER;
    }

    jpeg.setPixelType(RGB565_LITTLE_ENDIAN);

    int scaledWidth = width;
    int scaledHeight = height;
    if (scale == JPEG_SCALE_HALF) {
        scaledWidth /= 2;
        scaledHeight /= 2;
    } else if (scale == JPEG_SCALE_QUARTER) {
        scaledWidth /= 4;
        scaledHeight /= 4;
    } else if (scale == JPEG_SCALE_EIGHTH) {
        scaledWidth /= 8;
        scaledHeight /= 8;
    }

    int originX = IMAGE_X + max((IMAGE_W - scaledWidth) / 2, 0);
    int originY = IMAGE_Y + max((IMAGE_H - scaledHeight) / 2, 0);

    gfx->fillRoundRect(IMAGE_X, IMAGE_Y, IMAGE_W, IMAGE_H, 8, C_PANEL);
    gfx->drawRoundRect(IMAGE_X, IMAGE_Y, IMAGE_W, IMAGE_H, 8, C_DIM);
    jpeg.decode(originX, originY, scale);
    jpeg.close();
    return true;
}

String absoluteUrl(const String &path) {
    if (path.startsWith("http://") || path.startsWith("https://")) {
        return path;
    }
    if (!state.piBaseUrl.length()) {
        return "";
    }
    return state.piBaseUrl + path;
}

String previewUrl(const String &url) {
    String preview = url;
    preview += url.indexOf('?') >= 0 ? "&" : "?";
    preview += "live=1";
    preview += "&";
    preview += "max_w=" + String(IMAGE_W);
    preview += "&max_h=" + String(IMAGE_H);
    preview += "&quality=" + String(PREVIEW_QUALITY);
    return preview;
}

bool fetchBinary(const String &url, std::vector<uint8_t> &buffer, size_t maxBytes = MAX_PREVIEW_BYTES) {
    HTTPClient http;
    http.setTimeout(8000);
    if (!http.begin(url)) {
        return false;
    }
    int httpCode = http.GET();
    if (httpCode != HTTP_CODE_OK) {
        http.end();
        return false;
    }

    WiFiClient *stream = http.getStreamPtr();
    int total = http.getSize();
    if (total > 0 && static_cast<size_t>(total) > maxBytes) {
        Serial.printf("[IMG] payload too large: %d bytes\n", total);
        http.end();
        return false;
    }
    if (total > 0) {
        buffer.reserve(total);
    }

    uint8_t chunk[1024];
    while (http.connected() && (total > 0 || total == -1)) {
        size_t available = stream->available();
        if (!available) {
            delay(1);
            continue;
        }
        int read = stream->readBytes(chunk, min(available, sizeof(chunk)));
        if (read <= 0) {
            break;
        }
        if (buffer.size() + static_cast<size_t>(read) > maxBytes) {
            Serial.printf("[IMG] buffer exceeded %u bytes\n", static_cast<unsigned>(maxBytes));
            http.end();
            return false;
        }
        buffer.insert(buffer.end(), chunk, chunk + read);
        if (total > 0) {
            total -= read;
        }
    }
    http.end();
    return !buffer.empty();
}

bool fetchStatus() {
    if (!state.piBaseUrl.length()) {
        setMessage("Set Pi URL in WiFi portal");
        state.apiOnline = false;
        state.screenDirty = true;
        return false;
    }

    state.wifiOnline = WiFi.status() == WL_CONNECTED;
    if (!state.wifiOnline) {
        state.apiOnline = false;
        setMessage("WiFi offline", 4000, "Reconnect in portal");
        Serial.println("[WIFI] not connected");
        return false;
    }

    String host;
    uint16_t port = 0;
    if (!splitBaseUrl(state.piBaseUrl, host, port)) {
        state.apiOnline = false;
        setMessage("Bad Pi URL");
        Serial.printf("[API] could not parse base URL: %s\n", state.piBaseUrl.c_str());
        return false;
    }

    WiFiClient probe;
    probe.setTimeout(3000);
    Serial.printf(
        "[WIFI] ssid=%s ip=%s gateway=%s rssi=%d\n",
        WiFi.SSID().c_str(),
        WiFi.localIP().toString().c_str(),
        WiFi.gatewayIP().toString().c_str(),
        WiFi.RSSI()
    );
    if (!probe.connect(host.c_str(), port)) {
        state.apiOnline = false;
        setMessage("TCP connect failed", 4000, host + ":" + String(port));
        Serial.printf("[API] TCP connect failed to %s:%u\n", host.c_str(), port);
        probe.stop();
        return false;
    }
    probe.stop();

    WiFiClient client;
    HTTPClient http;
    http.setTimeout(5000);
    http.setReuse(false);
    String url = state.piBaseUrl + "/api/status";
    Serial.printf("[API] GET %s\n", url.c_str());
    if (!http.begin(client, url)) {
        state.apiOnline = false;
        setMessage("Bad Pi URL");
        Serial.println("[API] http.begin failed");
        return false;
    }

    int httpCode = http.GET();
    if (httpCode != HTTP_CODE_OK) {
        http.end();
        state.apiOnline = false;
        setMessage("HTTP " + String(httpCode), 4000, url);
        Serial.printf("[API] GET failed with code %d\n", httpCode);
        return false;
    }

    JsonDocument doc;
    DeserializationError error = deserializeJson(doc, http.getString());
    http.end();
    if (error) {
        state.apiOnline = false;
        setMessage("Bad status JSON", 4000, error.c_str());
        Serial.printf("[API] JSON parse failed: %s\n", error.c_str());
        return false;
    }

    const String previousSourceId = state.activeSourceId;
    const String previousSnapshotUrl = state.latestSnapshotUrl;
    const String previousSnapshotModifiedAt = state.latestSnapshotModifiedAt;

    state.apiOnline = true;
    state.statusDetail = "";
    state.host = doc["host"] | "";
    state.snapshotAvailable = doc["snapshot"]["exists"] | false;
    state.latestSnapshotUrl = doc["snapshot"]["url"] | "";
    state.latestSnapshotModifiedAt = doc["snapshot"]["modified_at"] | "";
    state.activeSourceId = doc["camera"]["active_source_id"] | "";
    state.activeSourceLabel = doc["camera"]["active_source_name"] | "";

    state.sources.clear();
    for (JsonObject source : doc["camera"]["sources"].as<JsonArray>()) {
        CameraSource item;
        item.sourceId = source["source_id"] | "";
        item.label = source["label"] | "";
        item.available = source["available"] | false;
        item.selected = source["selected"] | false;
        state.sources.push_back(item);
    }

    int previousEventCount = state.events.size();
    state.events.clear();
    for (JsonObject event : doc["motion_events"].as<JsonArray>()) {
        MotionEvent item;
        item.detectedAt = event["detected_at"] | "";
        item.snapshotUrl = event["snapshot_url"] | "";
        item.score = event["score"] | 0.0f;
        state.events.push_back(item);
    }

    if (state.eventIndex >= static_cast<int>(state.events.size())) {
        state.eventIndex = state.events.empty() ? -1 : 0;
    }
    if (
        previousEventCount != static_cast<int>(state.events.size()) ||
        previousSourceId != state.activeSourceId ||
        previousSnapshotUrl != state.latestSnapshotUrl ||
        previousSnapshotModifiedAt != state.latestSnapshotModifiedAt
    ) {
        state.imageDirty = true;
    }

    state.screenDirty = true;
    return true;
}

bool postJson(const String &path, const String &body, String &responseBody) {
    if (!state.piBaseUrl.length()) {
        return false;
    }
    HTTPClient http;
    http.setTimeout(5000);
    if (!http.begin(state.piBaseUrl + path)) {
        return false;
    }
    http.addHeader("Content-Type", "application/json");
    int httpCode = http.POST(body);
    responseBody = http.getString();
    http.end();
    return httpCode >= 200 && httpCode < 300;
}

void drawFrame() {
    gfx->fillScreen(C_BG);
    drawHeader();
    drawFooter();
    drawStatusText();
    state.screenDirty = false;
    state.imageDirty = true;
}

void renderCurrentImage() {
    if (!state.apiOnline) {
        String subtitle = state.statusDetail.length()
            ? state.statusMessage + " - " + state.statusDetail
            : "Check WiFi, Pi URL, or server availability.";
        clearImageArea("MotionSense Pi offline", subtitle);
        drawStatusText();
        state.imageDirty = false;
        return;
    }

    String url;
    if (state.eventIndex >= 0 && state.eventIndex < static_cast<int>(state.events.size())) {
        url = absoluteUrl(state.events[state.eventIndex].snapshotUrl);
    } else if (state.snapshotAvailable) {
        url = absoluteUrl(state.latestSnapshotUrl);
    }

    if (!url.length()) {
        clearImageArea("No image available", "Take a snapshot or wait for a motion event.");
        drawStatusText();
        state.imageDirty = false;
        return;
    }

    const String imageUrl = previewUrl(url);
    Serial.printf("[IMG] GET %s heap=%u\n", imageUrl.c_str(), ESP.getFreeHeap());
    std::vector<uint8_t> buffer;
    if (!fetchBinary(imageUrl, buffer) || !drawJpegFromBuffer(buffer.data(), buffer.size())) {
        clearImageArea("Image load failed", url);
    } else {
        Serial.printf("[IMG] rendered %u bytes heap=%u\n", static_cast<unsigned>(buffer.size()), ESP.getFreeHeap());
    }
    drawStatusText();
    state.imageDirty = false;
}

void cycleCameraSource() {
    if (state.sources.empty()) {
        setMessage("No sources");
        return;
    }

    int currentIndex = 0;
    for (size_t i = 0; i < state.sources.size(); i++) {
        if (state.sources[i].selected) {
            currentIndex = static_cast<int>(i);
            break;
        }
    }

    for (size_t step = 1; step <= state.sources.size(); step++) {
        const CameraSource &candidate = state.sources[(currentIndex + step) % state.sources.size()];
        if (!candidate.available) {
            continue;
        }

        String response;
        String body = "{\"source_id\":\"" + candidate.sourceId + "\"}";
        if (postJson("/api/camera/source", body, response)) {
            setMessage("Camera switched");
            state.eventIndex = -1;
            state.imageDirty = true;
            state.screenDirty = true;
            fetchStatus();
        } else {
            setMessage("Camera switch failed");
        }
        return;
    }
}

void resetPortal() {
    setMessage("Resetting portal...");
    prefs.begin("motionsense", false);
    prefs.clear();
    prefs.end();
    wifiManager.resetSettings();
    delay(300);
    ESP.restart();
}

void handleTouch(int tx, int ty) {
    if (pointInButton(btnPrev, tx, ty)) {
        if (!state.events.empty()) {
            if (state.eventIndex < 0) {
                state.eventIndex = static_cast<int>(state.events.size()) - 1;
            } else if (state.eventIndex > 0) {
                state.eventIndex--;
            }
            state.imageDirty = true;
            state.screenDirty = true;
        }
    } else if (pointInButton(btnLive, tx, ty)) {
        state.eventIndex = -1;
        state.imageDirty = true;
        state.screenDirty = true;
    } else if (pointInButton(btnNext, tx, ty)) {
        if (!state.events.empty()) {
            if (state.eventIndex < 0) {
                state.eventIndex = 0;
            } else if (state.eventIndex < static_cast<int>(state.events.size()) - 1) {
                state.eventIndex++;
            } else {
                state.eventIndex = -1;
            }
            state.imageDirty = true;
            state.screenDirty = true;
        }
    } else if (pointInButton(btnCam, tx, ty)) {
        cycleCameraSource();
    } else if (pointInButton(btnWifi, tx, ty)) {
        resetPortal();
    }
}

void connectWifi() {
    WiFi.mode(WIFI_STA);
    WiFi.setSleep(false);
    wifiManager.setHostname("motionsense-cyd");
    wifiManager.setConfigPortalTimeout(180);
    wifiManager.setConnectTimeout(20);
    wifiManager.setSaveConfigCallback(markConfigForSave);
    wifiManager.addParameter(&piUrlParam);

    if (!wifiManager.autoConnect("MotionSense-CYD")) {
        ESP.restart();
    }

    Serial.printf("[CFG] portal pi_url='%s'\n", piUrlParam.getValue());
    if (shouldSaveConfig) {
        saveConfig();
        shouldSaveConfig = false;
    } else if (!state.piBaseUrl.length()) {
        saveConfig();
    } else {
        piUrlParam.setValue(state.piBaseUrl.c_str(), 96);
        Serial.println("[CFG] keeping existing saved pi_url");
    }
    unsigned long waitStarted = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - waitStarted < 10000) {
        delay(100);
    }
    state.wifiOnline = WiFi.status() == WL_CONNECTED;
    Serial.printf(
        "[WIFI] connected=%s ssid=%s ip=%s gateway=%s rssi=%d\n",
        state.wifiOnline ? "true" : "false",
        WiFi.SSID().c_str(),
        WiFi.localIP().toString().c_str(),
        WiFi.gatewayIP().toString().c_str(),
        WiFi.RSSI()
    );
}

bool shouldResetFromBootButtonWindow() {
    pinMode(CYD_BOOT_BUTTON_GPIO, INPUT_PULLUP);
    unsigned long windowStarted = millis();
    bool pressed = false;

    gfx->fillRect(0, 140, SCREEN_W, 32, C_BG);
    gfx->setTextColor(C_YELLOW, C_BG);
    gfx->setTextSize(1);
    gfx->setCursor(24, 148);
    gfx->print("Hold BOOT now to reset WiFi + Pi URL");

    while (millis() - windowStarted < 3000) {
        if (digitalRead(CYD_BOOT_BUTTON_GPIO) == LOW) {
            pressed = true;
        }
        delay(20);
    }

    return pressed;
}

void clearPortalSettings() {
    prefs.begin("motionsense", false);
    prefs.clear();
    prefs.end();
    wifiManager.resetSettings();
    state.piBaseUrl = "";
    piUrlParam.setValue("", 96);
}

}  // namespace

void setup() {
    Serial.begin(115200);
    pinMode(GFX_BL, OUTPUT);
    digitalWrite(GFX_BL, HIGH);

    gfx->begin();
    gfx->invertDisplay(true);
    gfx->fillScreen(C_BG);
    gfx->setTextColor(C_CYAN, C_BG);
    gfx->setTextSize(2);
    gfx->setCursor(36, 96);
    gfx->print("MotionSense CYD");
    gfx->setTextSize(1);
    gfx->setCursor(56, 118);
    gfx->print("Starting WiFi portal...");

    touchSPI.begin(XPT2046_CLK, XPT2046_MISO, XPT2046_MOSI, XPT2046_CS);
    ts.begin(touchSPI);
    ts.setRotation(1);

    loadConfig();
    if (shouldResetFromBootButtonWindow()) {
        gfx->fillRect(0, 176, SCREEN_W, 20, C_BG);
        gfx->setTextColor(C_CYAN, C_BG);
        gfx->setCursor(54, 182);
        gfx->print("Clearing saved settings...");
        clearPortalSettings();
        delay(400);
    }
    connectWifi();
    fetchStatus();
    drawFrame();
}

void loop() {
    unsigned long now = millis();

    if (now - state.lastStatusFetchMs >= STATUS_REFRESH_MS) {
        state.lastStatusFetchMs = now;
        fetchStatus();
    }

    bool touched = ts.tirqTouched() && ts.touched();
    if (touched && !state.touchWasDown) {
        TS_Point point = ts.getPoint();
        int sx;
        int sy;
        mapTouch(point.x, point.y, sx, sy);
        handleTouch(sx, sy);
    }
    state.touchWasDown = touched;

    if (state.screenDirty) {
        drawFrame();
    }
    if (state.imageDirty) {
        renderCurrentImage();
    }

    delay(20);
}
