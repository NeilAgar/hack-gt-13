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
