#include "display.h"

#include <Arduino.h>
#include <Wire.h>

#include "config.h"

#if OLED_ENABLED
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
static Adafruit_SSD1306 oled(OLED_WIDTH, OLED_HEIGHT, &Wire, -1);
static bool oled_ok = false;
#endif

#if USE_NEOPIXEL
#include <Adafruit_NeoPixel.h>
static Adafruit_NeoPixel pixel(1, PIN_RGB_PIXEL, NEO_GRB + NEO_KHZ800);
#endif

namespace display {
namespace {

uint32_t last_chirp_ms = 0;
uint32_t chirp_until_ms = 0;

enum class Colour { OFF, GREEN, AMBER, RED, BLUE, MAGENTA };

void set_colour(Colour c) {
  uint8_t r = 0, g = 0, b = 0;
  switch (c) {
    case Colour::OFF: break;
    case Colour::GREEN: g = 255; break;
    case Colour::AMBER: r = 255; g = 120; break;
    case Colour::RED: r = 255; break;
    case Colour::BLUE: b = 255; break;
    case Colour::MAGENTA: r = 255; b = 255; break;
  }
#if USE_NEOPIXEL
  pixel.setPixelColor(0, pixel.Color(r / 4, g / 4, b / 4));  // quarter brightness is plenty
  pixel.show();
#elif RGB_ENABLED
  // Discrete common-cathode LED: on/off per channel (amber shows as yellow; that's fine).
  const bool inv = RGB_COMMON_ANODE;
  digitalWrite(PIN_RGB_R, (r > 0) != inv ? HIGH : LOW);
  digitalWrite(PIN_RGB_G, (g > 0) != inv ? HIGH : LOW);
  digitalWrite(PIN_RGB_B, (b > 0) != inv ? HIGH : LOW);
#else
  (void)r; (void)g; (void)b;
#endif
}

Colour wait_colour(uint32_t elapsed_ms) {
  if (elapsed_ms < (uint32_t)WAIT_AMBER_S * 1000u) return Colour::GREEN;
  if (elapsed_ms < (uint32_t)WAIT_RED_S * 1000u) return Colour::AMBER;
  return Colour::RED;
}

#if OLED_ENABLED
uint32_t next_draw_ms = 0;

void fmt_mmss(uint32_t ms, char* out, size_t cap) {
  uint32_t s = ms / 1000;
  snprintf(out, cap, "%lu:%02lu", (unsigned long)(s / 60), (unsigned long)(s % 60));
}

void draw(const View& v) {
  if (!oled_ok) return;
  char buf[24];
  oled.clearDisplay();
  oled.setTextColor(SSD1306_WHITE);
  oled.setTextSize(1);
  oled.setCursor(0, 0);
  oled.printf("%s  %s%s", DEVICE_ID, CCN, v.clock_set ? "" : "  no clock");
  oled.drawFastHLine(0, 10, OLED_WIDTH, SSD1306_WHITE);

  if (v.state == CallState::CALLING || v.state == CallState::TIMED_OUT) {
    oled.setCursor(0, 16);
    oled.print(v.state == CallState::TIMED_OUT ? "TIMED OUT" : "WAITING");
    oled.setTextSize(3);
    oled.setCursor(0, 32);
    fmt_mmss(v.elapsed_ms, buf, sizeof(buf));
    oled.print(buf);
  } else if (v.state == CallState::ATTENDED) {
    oled.setCursor(0, 16);
    oled.print("ARRIVED after");
    oled.setTextSize(3);
    oled.setCursor(0, 30);
    fmt_mmss((uint32_t)v.last_wait_ds * 100u, buf, sizeof(buf));
    oled.print(buf);
    oled.setTextSize(1);
    oled.setCursor(0, 56);
    oled.print("light still on");
  } else if (v.have_result && v.result_age_ms < 60000) {
    if (v.result_no_entry) {
      oled.setTextSize(2);
      oled.setCursor(0, 18);
      oled.print("NO ENTRY");
      oled.setTextSize(1);
      oled.setCursor(0, 42);
      oled.print("- cancelled");
    } else {
      oled.setCursor(0, 16);
      oled.print("ARRIVED after");
      oled.setTextSize(3);
      oled.setCursor(0, 32);
      fmt_mmss((uint32_t)v.last_wait_ds * 100u, buf, sizeof(buf));
      oled.print(buf);
    }
  } else if (v.warmup_s > 0) {
    oled.setCursor(0, 20);
    oled.print("PIR warming up");
    oled.setTextSize(2);
    oled.setCursor(0, 36);
    oled.printf("%lus", (unsigned long)v.warmup_s);
  } else {
    oled.setCursor(0, 18);
    oled.printf("Calls today: %lu", (unsigned long)v.calls_today);
    oled.setCursor(0, 32);
    if (v.median_wait_ds >= 0) {
      fmt_mmss((uint32_t)v.median_wait_ds * 100u, buf, sizeof(buf));
      oled.printf("Median wait: %s", buf);
    } else {
      oled.print("Median wait: -");
    }
    oled.setCursor(0, 50);
    oled.print(v.light == LightState::OFF ? "idle, light off" : "light seen...");
  }
  oled.display();
}
#endif

}  // namespace

void begin() {
#if RGB_ENABLED && !USE_NEOPIXEL
  pinMode(PIN_RGB_R, OUTPUT);
  pinMode(PIN_RGB_G, OUTPUT);
  pinMode(PIN_RGB_B, OUTPUT);
#endif
#if USE_NEOPIXEL
  pixel.begin();
#endif
  set_colour(Colour::OFF);
#if BUZZER_ENABLED
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);
#endif
#if OLED_ENABLED
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
  oled_ok = oled.begin(SSD1306_SWITCHCAPVCC, OLED_I2C_ADDR);
  if (oled_ok) {
    oled.clearDisplay();
    oled.setTextColor(SSD1306_WHITE);
    oled.setTextSize(2);
    oled.setCursor(0, 0);
    oled.print("Call Clock");
    oled.setTextSize(1);
    oled.setCursor(0, 24);
    oled.print("no camera, no mic");
    oled.display();
  } else {
    Serial.println("DBG oled not found at 0x3C (check SDA/SCL); continuing without it");
  }
#endif
}

void update(const View& v, uint32_t now_ms) {
  switch (v.state) {
    case CallState::CALLING: set_colour(wait_colour(v.elapsed_ms)); break;
    case CallState::TIMED_OUT: set_colour(Colour::RED); break;
    case CallState::ATTENDED: set_colour(Colour::BLUE); break;
    case CallState::IDLE:
      set_colour(v.have_result && v.result_no_entry && v.result_age_ms < 10000 ? Colour::MAGENTA : Colour::OFF);
      break;
  }

#if BUZZER_ENABLED
  if (v.state == CallState::CALLING && v.elapsed_ms >= BUZZER_CHIRP_EVERY_MS &&
      now_ms - last_chirp_ms >= BUZZER_CHIRP_EVERY_MS) {
    last_chirp_ms = now_ms;
    chirp_until_ms = now_ms + BUZZER_CHIRP_MS;
  }
  digitalWrite(PIN_BUZZER, (int32_t)(chirp_until_ms - now_ms) > 0 ? HIGH : LOW);
#else
  (void)last_chirp_ms;
  (void)chirp_until_ms;
#endif

#if OLED_ENABLED
  if ((int32_t)(now_ms - next_draw_ms) >= 0) {
    next_draw_ms = now_ms + 200;
    draw(v);
  }
#endif
}

}  // namespace display
