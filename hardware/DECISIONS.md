# Call Clock: decisions

Choices made while building Call Clock autonomously, one per row. See the summary at the bottom for
status and the exact morning commands.

| # | Decision | Why |
|---|---|---|
| 1 | `wait_s` is carried as integer **deciseconds** inside the firmware and printed as `%ld.%ld`; Python formats it from `round(x*10)`. | "floats with 1 decimal" must be byte-identical in C++ and Python; integer arithmetic removes any float-formatting drift between newlib and CPython. |
| 2 | `sig = HMAC_SHA256(key_bytes, hash_hex_ascii)`: the HMAC input is the 64-char lowercase hex string, not the 32 raw bytes. `hash = SHA256(prev_hash_hex_ascii + canonical)`. Keys are 32 random bytes, stored as 64 hex chars. | Spec says `HMAC(device_key, hash)`; hashing the hex text is simplest to reproduce in any language. |
| 3 | `seq` starts at **1**; the genesis `prev_hash` is 64 zeros. | "seq gap" detection is unambiguous: a device's first event must be seq 1 + genesis. |
| 4 | `ts` and `night` are **null** until the clock is set (bridge time sync or NTP). `ms` (ms since boot) is always present. | We can't know local night/day without a clock; guessing would bias the night-vs-day comparison. Null-night calls are left out of the night/day split. |
| 5 | Canonical key order: `call_id, ccn, device_id, event, ms, night, no_entry, prev_hash, seq, synthetic, ts, v, wait_s` (bytewise sort). The full line appends `hash` and `sig` at the end. | Keys sorted per spec; appending keeps the firmware's builder simple. |
| 6 | `cancel` and `timeout` carry `wait_s` (time until arrival, null if none) and `no_entry`. `call_on`/`entry` carry `no_entry: null`. | Matches the spec example. |
| 7 | After `timeout` the machine goes to `TIMED_OUT` and re-arms silently when the light goes off (no extra `cancel`). | Avoids a phantom second call when a light is stuck on for hours. |
| 8 | A call-light ON and an entry in the same tick produce `call_on` then `entry` with `wait_s: 0.0`. | Deterministic ordering; tested. |
| 9 | Native tests use a small vendored FIPS 180-4 SHA-256 (`sha256_portable.cpp`) + hand-rolled HMAC; the ESP32 build uses mbedTLS. Both are checked against the SHA-256 "abc" KAT, RFC 4231 case 2 and the cross-language vector. | mbedTLS isn't available on the native platform. |
| 10 | `LightClassifier` (EMA + adaptive baseline + hysteresis + FLASH + debounce) is pure C++ inside `light_sensor.cpp`, so its timing is unit-tested natively. | "Everything testable without hardware". |
| 11 | Adaptive baseline only follows the signal while the light is OFF (α = 0.001/sample ≈ 10 s). The first sample after boot seeds it: **boot with the call light off**. | Otherwise a long call would drag the baseline up and end the call early. |
| 12 | PlatformIO platform pinned to `espressif32@^6.9.0` (Arduino core 2.0.17). The code avoids APIs that changed in core 3.x (no `ledc*`, no `tone`), so a later move to pioarduino / core 3 should be painless. | Stable, most widely used; what the registry serves on the human's laptop. |
| 13 | Verified compiles of esp32dev, esp32-s3-devkitc-1 and 5 option variants (LD2410 UART + NeoPixel + buzzer + Wi-Fi, reed + non-demo + calibrate + no OLED, no entry sensor, LD2410 OUT + common-anode) in the build container. The PlatformIO registry was blocked there, so the identical packages were side-loaded from GitHub (platform v6.9.0, crosstool-NG esp-2021r2-patch5, arduino-esp32 2.0.17, the same library versions). On a normal laptop `pio run` just downloads them. | Spec milestone 2. |
| 14 | LD2410 UART: a ~30-line frame parser in `entry_sensor.cpp` (basic/engineering frames, "target state ≠ 0" = presence) instead of `ncmreynolds/ld2410`. | One less dependency; we only need presence. Untested on a real radar. |
| 15 | Rising edge on PIR/LD2410 OUT = entry; `INPUT_PULLDOWN` so an unplugged sensor never floats into fake entries. The level at boot is never an edge; edges are ignored during the 30 s PIR warm-up. | |
| 16 | Reed mode treats HIGH (door opened, magnet away) as the entry edge. A plain push button to GND on the same pin works as a manual "entry" for bench tests (needs the external 10k pull-up on GPIO35). | Handy fallback if the PIR misbehaves at the demo. |
| 17 | Discrete RGB LED is driven on/off per channel (amber shows as yellow). NeoPixel option available. Buzzer is an **active** buzzer (HIGH = beep). | Avoids the ledc API break between core 2 and 3. |
| 18 | Colours: waiting = green/amber/red by the thresholds; someone arrived = blue; cancelled with no one entering = magenta for 10 s. | |
| 19 | `clear YES` wipes `/log.jsonl` but keeps the chain head in `/head.txt`, so the server still sees one unbroken chain. `factory YES` wipes both (new chain from seq 1); you must also delete that device's rows server-side (easiest: delete `data/bedside.sqlite`). | Clearing the local log must not look like tampering, and must not be a way to rewrite history. |
| 20 | Macro renamed `PIN_NEOPIXEL` → `PIN_RGB_PIXEL`: the S3 Arduino variant already defines `PIN_NEOPIXEL`. Main toggles in config.h are wrapped in `#ifndef` so they can be overridden from `build_flags`. | |
| 21 | S3 pin block: LDR GPIO4 (ADC1), entry 5, reed 6 (internal pull-up), LD2410 UART1 RX18/TX17, buttons 7/15, call LED 16, dome 21, I2C 8/9, RGB 10/11/12, buzzer 13, on-board WS2812 on 48. Avoids strapping pins, USB 19/20 and the PSRAM range. | Untested on hardware. |
