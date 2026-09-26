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
| 22 | One Python implementation of the format (`hardware/eventlog.py`) is shared by the API, simulator, seeder, bridge and verifier (`hardware/` is a package so `api/` can import it). | Two implementations (C++ + Python) is already one too many; the shared test vector keeps them equal. |
| 23 | The simulator's events are `synthetic:true` and come from device `sim-dev`. It resumes the chain from the API (`GET /api/bedside/events`), else the local log, so re-runs never break the chain. | Simulated events are not bedside measurements. |
| 24 | Seeder: one device per CCN (`sim-01`, `sim-02`, `sim-03`), Poisson(9) calls/day with an hourly profile, lognormal waits (σ 0.75) with medians 240 s day / 660 s night, 8 % no-entry cancels, one call at a time per room, no events in the future. Deterministic per (`--seed`, `--end`). | Spec §5. |
| 25 | `verify_log.py` on a FILE accepts a log that starts mid-chain (a device whose local log was `clear`ed) and says so; via `--api` the full chain from seq 1 is required. | Matches decision 19. |
| 26 | Bridge: on connect it sends the time sync, then `dump` (backfill; server is idempotent), re-syncs time hourly, forwards typed lines to the device, keeps `hardware/logs/<device>.jsonl` de-duplicated by seq, and uploads strictly in order with 1→30 s backoff. | |
| 27 | Demo keys (`cc-01`, `sim-dev`, `sim-01..03`) are committed in `keys/devices.example.json` and used as a fallback when `devices.json` doesn't exist. | Makes the demo run out of the box; flagged as public in the file, README and here. |
| 28 | API: `bedside_store.py` stores every event with `verified` + `reason`; stats use **verified events only** and report `n_unverified` (extra field) next to `verified_all`, so an altered wait can never move the median. | "Stored but flagged, never silently dropped", and a tampered number must not reach families. |
| 29 | Same `(device_id, seq)` + same content → `duplicate: true`, no change. Same seq, different content → `accepted: false`, reason `conflict: …`, kept in a `conflicts` table. | Idempotent retries, while a rewrite attempt stays visible. |
| 30 | An event whose predecessor hasn't arrived is stored as `seq gap`; when the missing event arrives, successors are re-verified automatically. | Bridge retries / backfill can arrive out of order. |
| 31 | `POST /api/bedside` with one event returns `{accepted: bool, verified, reason, duplicate}`; with a list it returns `{accepted: <count>, verified: <all>, reason: <first failure>, results: [...]}`. | Spec gives one shape; a count is more useful for batches. |
| 32 | `p_over_10m` and `synthetic_share` are fractions 0–1 (like `p_next_60d`), not percent units. `p_over_10m` is among calls where someone arrived; no-entry calls are counted separately in `n_no_entry`. A call counts only if its `call_on` verified. Night/day split uses the `call_on`'s `night`. | Keeps the contract's `p_` convention. |
| 33 | `by_days_since_inspection` buckets: 0-7, 8-30, 31-90, 91+ days since the most recent **past** standard survey (from `data/processed/surveys.parquet`); null when the file or the facility's surveys are missing. Never uses predicted timing. | Guardrail: no predicted inspection timing in public endpoints. |
| 34 | Extra endpoint `GET /api/bedside/events?device_id=` returns a device's raw signed events, used by `verify_log.py --api` (verifies client-side with its own keys) and by the simulator to resume its chain. | Server-side `/verify` alone would mean trusting the server. |
| 35 | SSE `/api/bedside/stream?ccn=&backlog=10`: on connect sends the last N events (`backlog: true`) so a reloaded page can rebuild the current call, then every new event; a `ping` every 10 s. Every message carries `server_now_ms` so the client can correct its clock. In-process broker (single uvicorn worker). | Drives the live timer. |
| 36 | Web: `BedsidePanel` is a client component that reuses the app's existing CSS classes (the app has no Tailwind). It asks for `include_synthetic=true` and shows a "Synthetic demo data (x% of calls)" chip whenever `synthetic_share > 0`; shares are never rounded to 100 %/0 %. Types and helpers are exported from `BedsidePanel.tsx` so the spec's two files are the only new web files. | |
| 37 | `/live` timer anchor: the server's receive time of `call_on` (ms precision) for live events; the device `ts` when the event reached the server > 5 s late (backlog, backfill). Client clock is corrected with `server_now_ms` on every message and ping, and ticks every 100 ms. | Spec: "server event timestamp plus a client clock". Device `ts` has 1 s resolution, receive time is sharper for live events. |
| 38 | `/live` is a fixed full-screen overlay (the root layout's header/footer stay underneath) so no shared layout file changes; stacks to one column under 720 px. | New files only. |

## Summary (end of the overnight build)

**Done and tested here (no hardware):**
- Firmware: pure state machine, light classifier (EMA, adaptive baseline, hysteresis, FLASH, 300 ms / 2 s debounce),
  hash chain + HMAC. `pio test -e native`: **12/12 pass**, including the cross-language vector.
- Firmware **compiles** for `esp32dev` and `esp32-s3-devkitc-1`, plus 5 option variants (LD2410 UART / OUT, reed,
  no sensor, NeoPixel, buzzer, Wi-Fi, common-anode, no OLED, non-demo thresholds). esp32dev: RAM 7.9 %, flash 31 %.
- Python: `hardware/tests` **12/12 pass** (same vector, tamper cases, tamper_demo.sh end to end).
- API: `api/tests/test_bedside.py` **11/11 pass**; the existing API suite still passes (50 total).
  uvicorn + `simulate_device.py --script demo` gives the right stats (median 33.0 s from 21 s + 45 s, 1 no-entry),
  SSE pushes each event, `verify_log.py --api` ✅.
- Bridge tested against a fake device on a pseudo-terminal: time sync, `dump` backfill, EVT forwarding,
  local log, server chain ✅.
- Web: `npx tsc --noEmit` and `npm test` pass. `/live` rendered in headless Chromium against the simulator:
  green → amber → "Someone arrived after 0:21" → "0:45" → red "Cancelled — no one entered"; state survives a reload;
  no horizontal scroll at 390 px. `BedsidePanel` rendered against 30 days of seeded synthetic history.

**Not tested on real hardware (check in the morning):**
- ADC readings / thresholds of the actual LDR + LED pair (calibrate, README §3).
- HC-SR501 behaviour (warm-up, retrigger jumper, false triggers from the mock LED's light? keep the PIR aimed at the door).
- OLED at 0x3C, RGB polarity, LittleFS on first boot (formats automatically), `dump` over a real USB-UART.
- The CP210x/CH340 auto-detect on your laptop; the S3 pin block; LD2410 frames; Wi-Fi/NTP path (off by default).
- `docs/`, `web/` mounting and the Makefile target are requests to the owners (see `docs/REQUESTS.md`), not done.

**Morning commands (repo root):**
```bash
git checkout h/call-clock
pip install platformio -r hardware/bridge/requirements.txt -r api/requirements.txt && (cd web && npm ci)
cd hardware/firmware && pio test -e native && pio run -t upload && pio device monitor   # `cal on`, calibrate, Ctrl-C
cd ../.. && make api                                   # terminal 1
python hardware/bridge/serial_bridge.py --port auto    # terminal 2
make web                                               # terminal 3 → http://localhost:3000/live
bash hardware/tools/tamper_demo.sh hardware/logs/cc-01.jsonl
```

## Arduino Nano (ATmega328) build

| # | Decision | Why |
|---|---|---|
| 39 | New PlatformIO envs `nano` (new bootloader) and `nano-oldboot` (most clones), with `src/main_nano.cpp`. They share the state machine, light classifier, SHA-256 and canonical-JSON code with the ESP32 build, and produce **byte-identical** event lines (a native test compares the Nano and ESP32 output for the same event). | One format, one verifier, one API. |
| 40 | Cut on the Nano: Wi-Fi/NTP, timezone rules, the OLED and the flash filesystem. `config.h` `#error`s if OLED, Wi-Fi or LD2410 UART mode is enabled for AVR. | 2 KB RAM / 32 KB flash / 1 KB EEPROM / one UART. The OLED's 1 KB frame buffer alone would take half the RAM. |
| 41 | **Compact EEPROM ring:** 17 bytes per event (type, no_entry, call-id nonce + counter, ms, wait, UTC epoch, UTC offset in 15-min steps). 45-byte header (magic, version, identity check, boot counter, ring start/count, `tail_seq`, `tail_prev`) → **57 events** on 1 KB. Everything else is fixed or derivable, so `dump` rebuilds the exact signed lines. When full, the oldest record is evicted and its hash becomes `tail_prev`, so the chain never breaks. | The user chose this over no local log: `dump`/backfill keep working. |
| 42 | The identity check (FNV-1a of device id + CCN + key) re-formats the EEPROM when any of them changes; a record that doesn't decode truncates the ring there at boot (the server then shows a seq gap). No CRC per record. | A torn write during a power cut can only lose the last event, and it shows as a gap rather than a forged event. |
| 43 | Streaming signing: events are hashed **while** they are printed (`cc_stream_event`), never built in a 640-byte buffer. JSON keys, the SHA-256 constants, the genesis hash and the key hex live in flash (`PROGMEM`). HMAC uses one 64-byte pad buffer and one SHA object. Result: **875 B static RAM, 22.7 KB flash**; the worst stack path (`dump`) is ~835 B. The ESP32 build uses the same streaming code (mbedTLS underneath). | The first Nano build needed ~1.15 KB of stack with only ~800 B free. |
| 44 | `status` reports `ram_never_used` (free RAM painted with a marker at boot). In simavr it stays at **274 bytes** after two calls, a `dump` and a reboot. Under ~150 on real hardware means the budget is too tight. | Measured, not guessed. |
| 45 | Time: the bridge's time sync now also sends `tz_offset` (seconds east of UTC, from the laptop). The Nano keeps `epoch + millis()` with that fixed offset; `ts` and `night` come out exactly as on the ESP32. The ESP32 ignores the field and keeps its TZ rules. | No timezone library on the Nano. A DST change mid-session would be off by an hour until the next sync. |
| 46 | The call-id prefix on the Nano is a **boot counter** kept in EEPROM (`0001-…`, `0002-…`), not a random number. | Guaranteed unique across reboots; the Nano has no hardware RNG. |
| 47 | Nano pins: LDR A0, PIR D2, reed D3 (internal pull-up), CALL D4, CANCEL D5, call LED D6, dome D7, NeoPixel D8, RGB D9/D10/D11, buzzer D12. D0/D1 are left for USB serial. 10-bit ADC at 5 V: `LIGHT_DELTA` 75 and `LDR_HYSTERESIS` 15 (a quarter of the ESP32's). No internal pull-down on AVR: add 100k from D2 to GND if the PIR may be unplugged. | |
| 48 | Bridge: waits for the board's `DBG boot` line before sending the time and `dump` (the Nano replays its EEPROM at boot and has a 64-byte receive buffer), recognises FTDI (genuine Nano), re-syncs the clock every 10 min instead of hourly (clone Nanos use a ceramic resonator, up to ~0.5 % off), and **reconnects on its own** after a USB unplug, re-syncing and backfilling with `dump`. | Found while testing against the simulated Nano; the old bridge crashed on unplug. |
| 49 | `hardware/tools/nanosim/`: runs the real Nano `firmware.elf` in simavr with a simulated room (buttons pressed on a script, the call-LED pin fed back into the LDR input, the PIR pin pulsed), through a power cycle. `run.sh` asserts that all events verify and that the EEPROM dump matches the live lines byte for byte. The `pty` mode exposes the UART for the real bridge; it was used to test time sync, backfill and reconnect end to end. | The only way to test the Nano build without a board. Needs `apt install simavr libsimavr-dev libelf-dev`. |
| 50 | The API now recreates `data/bedside.sqlite` if it is deleted while running (it used to return 500 until restarted). | "Delete the DB to reset the demo" is in the troubleshooting advice. |
