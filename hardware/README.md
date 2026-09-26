# Call Clock: quickstart

A camera-free, mic-free witness in the room. An LDR watches the call light and a PIR watches the doorway.
It logs **time until someone arrived** (not time to help), plus calls **cancelled with no one entering**, as a
hash-chained, HMAC-signed log. **Tamper-evident, not tamper-proof:** the key lives in flash.

**Setup (once):** `pip install platformio -r hardware/bridge/requirements.txt -r api/requirements.txt` and `cd web && npm ci`

## 1. Wire it (ESP32 DevKit v1, all pins in `firmware/include/config.h`)
| Part | Connect |
|---|---|
| LDR + 10k | 3V3 → LDR → **GPIO34** → 10k → GND. Tape the LDR over the call LED; block room light |
| PIR HC-SR501 | VCC → **VIN (5V)**, GND → GND, OUT → **GPIO13**. Jumper on **H**, both pots fully counter-clockwise |
| Mock station | CALL button **GPIO25**→GND, CANCEL **GPIO26**→GND, call LED **GPIO27** → 220 Ω → GND |
| OLED SSD1306 | SDA **21**, SCL **22**, 3V3, GND |
| RGB LED (common cathode) | R **18**, G **19**, B **23**, each via 220 Ω; common leg → GND |

## 2. Flash
```bash
cd hardware/firmware && pio run -t upload && pio device monitor     # Ctrl-C to leave the monitor
```
Boot with the call LED **off**. The OLED shows "PIR warming up 30s", then idle stats.

## 3. Calibrate the LDR (2 min)
In the monitor type `cal on`. Note `raw=` with the LED off, press CALL, note `raw=` with it on.
In `config.h` set `LDR_THRESHOLD` = midpoint and `LDR_HYSTERESIS` = 10% of the gap; re-flash; `cal off`.
(If on − off is well over 400, the default adaptive mode already works and you can skip this.)

## 4. Run everything (3 terminals, from the repo root)
```bash
make api                                                      # API on :8000
python hardware/bridge/serial_bridge.py --port auto            # CLOSE pio monitor first: the port is exclusive
make web                                                      # then open http://localhost:3000/live
```
## 5. Demo
Press **CALL** → big green timer (amber at 15 s, red at 30 s). Walk past the PIR → "Someone arrived after 0:21".
Press **CANCEL**. Press CALL then CANCEL without entering → red "Cancelled — no one entered".
**Tamper demo:** `bash hardware/tools/tamper_demo.sh hardware/logs/cc-01.jsonl` (✅ original, ❌ after editing one wait).
Server-side check: `python hardware/tools/verify_log.py --api http://localhost:8000 --device cc-01`.

## No hardware? / extras
```bash
python hardware/sim/simulate_device.py --script demo       # 21 s arrival, 45 s arrival, no-entry cancel (synthetic)
python hardware/sim/simulate_device.py                     # keys: c call, e entry, x cancel
python hardware/sim/seed_synthetic_history.py --ccn 115999 --days 30   # history for the bedside panel (synthetic)
python -m pytest hardware/tests api/tests/test_bedside.py && (cd hardware/firmware && pio test -e native)
```

## Arduino Nano instead of an ESP32
Same events, same bridge and API; no OLED, Wi-Fi or filesystem (the last 57 events live in EEPROM and `dump` still works).
Flash with `pio run -e nano -t upload` (most clones: `-e nano-oldboot`). Pins: LDR **A0** (5V → LDR → A0 → 10k → GND),
PIR **D2**, CALL **D4**, CANCEL **D5**, call LED **D6**, RGB **D9/D10/D11**. `status` shows `ram_never_used` (keep it > 150).
No board at all? `bash hardware/tools/nanosim/run.sh` runs the Nano firmware in a simulator (needs `simavr`).

## If something's off
- **No events:** in the monitor, `cal on` shows `state=`; it must go ON when the LED lights. Re-seat the LDR, shade it.
- **Entries don't register:** wait out the 30 s warm-up; `cal on` shows `entry=1` on motion. Bench fallback: set
  `ENTRY_SENSOR ENTRY_REED` and use a button on GPIO35 to GND with a 10k pull-up to 3V3.
- **`ts: null` in events:** the clock isn't set yet; the bridge sets it on connect (restart the bridge).
- **"log altered" after re-flashing with `factory YES` or a fresh key:** delete `data/bedside.sqlite` and restart the API.
- **Bridge can't open the port:** close `pio device monitor`. **OLED blank:** check it's at 0x3C, SDA 21 / SCL 22.
- Real deployments: use your own key in `keys/devices.json` + `HMAC_KEY_HEX` (the committed ones are public demo keys).
