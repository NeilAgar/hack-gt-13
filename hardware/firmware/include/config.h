// Call Clock configuration. EVERY pin, threshold and ID lives here.
//
// Call Clock is a camera-free, mic-free witness: it times how long a resident waits after the
// nurse-call light turns on, and whether anyone came through the doorway. It measures
// "time until someone arrived", never "time to help".
//
// Wiring cheat-sheet (ESP32 DevKit v1 / WROOM-32) is in hardware/README.md.
#pragma once

#include <stdint.h>

// ───────────────────────────── Identity ─────────────────────────────
// Unique per physical device. Must have a matching key in hardware/keys/devices.json on the server.
#define DEVICE_ID "cc-01"
// CMS Certification Number of the facility this device is installed in (6 chars, keep leading zeros).
// 115999 is the SYNTHETIC fixture facility used for the demo.
#define CCN "115999"
// 32-byte HMAC-SHA256 key as 64 hex chars. Must equal devices.json["cc-01"] on the server.
// This default is the PUBLIC demo key from hardware/keys/devices.example.json. Generate your own with:
//   python3 -c "import secrets; print(secrets.token_hex(32))"
// Tamper-EVIDENT, not tamper-proof: the key sits in flash. Real deployments need secure boot +
// flash encryption + a secure element (e.g. ATECC608) so the key cannot be read back out.
#define HMAC_KEY_HEX "3c1f0e7a9b2d4c6e8f0a1b3c5d7e9f1a2b4c6d8e0f1a3b5c7d9e1f2a4b6c8d0e"

// ───────────────────────────── Time ─────────────────────────────────
// POSIX TZ string for America/New_York (Georgia). Used for ts offsets and the night flag.
#define TZ_STRING "EST5EDT,M3.2.0,M11.1.0"
// Night window in local hours: [NIGHT_START_HOUR, 24) ∪ [0, NIGHT_END_HOUR).
#define NIGHT_START_HOUR 23
#define NIGHT_END_HOUR 7

// ───────────────────────────── Demo vs real thresholds ──────────────
// DEMO_MODE shortens the wait-colour thresholds so a live demo changes colour within seconds.
#define DEMO_MODE 1
#if DEMO_MODE
#define WAIT_AMBER_S 15   // green below this many seconds of waiting
#define WAIT_RED_S 30     // amber below this, red at or above
#else
#define WAIT_AMBER_S (5 * 60)
#define WAIT_RED_S (10 * 60)
#endif
// Safety valve: a call that stays on longer than this emits a "timeout" event and stops timing.
#define MAX_CALL_S (2UL * 60UL * 60UL)

// ───────────────────────────── Light sensing (LDR) ──────────────────
// LDR from 3V3 to the pin, 10k from the pin to GND. More light → higher reading (0..4095).
// Tape the LDR over the in-room call station's "reassurance" LED and block ambient light.
#define LIGHT_SAMPLE_HZ 100        // ADC samples per second
#define LIGHT_EMA_ALPHA 0.30f      // smoothing of the raw reading (0..1, higher = faster)
#define LIGHT_BASELINE_ALPHA 0.001f// adaptive "dark" baseline, updated only while OFF (~10 s at 100 Hz)
#define LIGHT_DELTA 300            // adaptive mode: ON when smoothed > baseline + LIGHT_DELTA
// Fixed-threshold mode (recommended once calibrated): set to the MIDPOINT of the raw OFF and ON
// readings you see with `cal on`. 0 = use the adaptive baseline + LIGHT_DELTA instead.
#define LDR_THRESHOLD 0
// Hysteresis in raw counts around the threshold. Rule of thumb: 10% of (raw_on - raw_off).
#define LDR_HYSTERESIS 60
#define LIGHT_ON_HOLD_MS 300       // light must look ON for this long before we believe it
#define LIGHT_OFF_HOLD_MS 2000     // and OFF for this long (bridges the gaps of a flashing light)
#define FLASH_WINDOW_MS 2000       // ≥ FLASH_MIN_TRANSITIONS lit/unlit flips in this window = FLASH
#define FLASH_MIN_TRANSITIONS 3
// Print "DBG raw=… baseline=… state=…" every 2 s from boot. Also toggled at runtime by `cal on|off`.
#define CALIBRATE 0
#define CALIBRATE_PRINT_MS 2000

// ───────────────────────────── Entry sensing ────────────────────────
// Which doorway sensor is fitted. Only its edges count; the device never records images or audio.
#define ENTRY_PIR 0          // HC-SR501 PIR, digital OUT (default)
#define ENTRY_LD2410_OUT 1   // HLK-LD2410C mmWave radar, digital OUT pin
#define ENTRY_LD2410_UART 2  // HLK-LD2410C over UART (basic reporting frames, 256000 baud)
#define ENTRY_REED 3         // magnetic reed switch on the door (or any push button to GND)
#define ENTRY_NONE 4         // no entry sensor: every call ends "no entry" (bench test only)
#define ENTRY_SENSOR ENTRY_PIR
#define ENTRY_REFRACTORY_MS 5000   // ignore further entry edges for 5 s after one fires
#define PIR_WARMUP_MS 30000        // HC-SR501 needs ~30 s after power-up before its output is sane

// ───────────────────────────── Output devices ───────────────────────
#define OLED_ENABLED 1
#define OLED_I2C_ADDR 0x3C
#define OLED_WIDTH 128
#define OLED_HEIGHT 64
#define RGB_ENABLED 1
#define RGB_COMMON_ANODE 0   // 1 if your RGB LED's common leg goes to 3V3 (logic inverted)
#define USE_NEOPIXEL 0       // 1 = single WS2812 on PIN_NEOPIXEL instead of the discrete RGB LED
#define BUZZER_ENABLED 0     // ACTIVE buzzer (beeps when driven HIGH); chirps every 10 s while waiting
#define BUZZER_CHIRP_EVERY_MS 10000
#define BUZZER_CHIRP_MS 60

// ───────────────────────────── Networking (optional) ────────────────
// Default OFF: the USB serial bridge (hardware/bridge/serial_bridge.py) is the primary uplink.
#define WIFI_ENABLED 0
#define WIFI_SSID "your-ssid"
#define WIFI_PASS "your-password"
#define API_URL "http://192.168.1.10:8000/api/bedside"
#define NTP_SERVER "pool.ntp.org"

// ───────────────────────────── Serial ───────────────────────────────
#define SERIAL_BAUD 115200

// ───────────────────────────── Pins ─────────────────────────────────
#if defined(CONFIG_IDF_TARGET_ESP32S3)
// ESP32-S3-DevKitC-1. Avoid 0/3/45/46 (strapping), 19/20 (USB D-/D+), 26–37 (flash/PSRAM on N8R8/N16R8).
#define PIN_LDR 4              // ADC1_CH3. ADC1 only: ADC2 stops working when Wi-Fi is on
#define PIN_ENTRY 5            // PIR / LD2410 OUT (3.3 V logic output)
#define PIN_REED 6             // reed switch to GND; internal pull-up is available on the S3
#define PIN_LD2410_RX 18       // ESP RX  ← LD2410 TX  (UART1)
#define PIN_LD2410_TX 17       // ESP TX  → LD2410 RX
#define PIN_MOCK_CALL_BTN 7    // mock station CALL button to GND (INPUT_PULLUP)
#define PIN_MOCK_CANCEL_BTN 15 // mock station CANCEL button to GND (INPUT_PULLUP)
#define PIN_MOCK_CALL_LED 16   // mock call LED via 220 Ω: this is what the LDR watches
#define PIN_DOME_LIGHT 21      // optional dome light (MOSFET gate), mirrors the call LED
#define PIN_I2C_SDA 8          // OLED SDA
#define PIN_I2C_SCL 9          // OLED SCL
#define PIN_RGB_R 10           // RGB red   via 220 Ω
#define PIN_RGB_G 11           // RGB green via 220 Ω
#define PIN_RGB_B 12           // RGB blue  via 220 Ω
#define PIN_NEOPIXEL 48        // on-board WS2812 of the DevKitC-1 (some revisions use 38)
#define PIN_BUZZER 13          // active buzzer (+) ; (-) to GND
#define REED_INTERNAL_PULLUP 1
#else
// ESP32 DevKit v1 (WROOM-32). Avoid 0/2/5/12/15 (boot strapping) and 6–11 (flash).
#define PIN_LDR 34             // ADC1_CH6, input-only. ADC1 only: ADC2 stops working when Wi-Fi is on
#define PIN_ENTRY 13           // HC-SR501 OUT (sensor powered from VIN/5V; its output is 3.3 V-safe) or LD2410 OUT
#define PIN_REED 35            // reed switch to GND. INPUT-ONLY pin with NO internal pull-up:
                               // fit an EXTERNAL 10k pull-up from GPIO35 to 3V3
#define PIN_LD2410_RX 16       // ESP RX2 ← LD2410 TX (UART2, 256000 baud)
#define PIN_LD2410_TX 17       // ESP TX2 → LD2410 RX
#define PIN_MOCK_CALL_BTN 25   // mock station CALL button to GND (INPUT_PULLUP)
#define PIN_MOCK_CANCEL_BTN 26 // mock station CANCEL button to GND (INPUT_PULLUP)
#define PIN_MOCK_CALL_LED 27   // mock call LED via 220 Ω: this is what the LDR watches
#define PIN_DOME_LIGHT 32      // optional dome light (MOSFET gate / LED strip), mirrors the call LED.
                               // Not 14/5/0/2/12/15: those glitch or strap at boot
#define PIN_I2C_SDA 21         // OLED SDA
#define PIN_I2C_SCL 22         // OLED SCL
#define PIN_RGB_R 18           // RGB red   via 220 Ω
#define PIN_RGB_G 19           // RGB green via 220 Ω
#define PIN_RGB_B 23           // RGB blue  via 220 Ω
#define PIN_NEOPIXEL 4         // WS2812 data (only if USE_NEOPIXEL)
#define PIN_BUZZER 33          // active buzzer (+) ; (-) to GND
#define REED_INTERNAL_PULLUP 0
#endif

#define LD2410_BAUD 256000
