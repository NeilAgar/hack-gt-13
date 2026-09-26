// SHA-256 and HMAC-SHA256. mbedTLS on the ESP32; a small portable SHA-256 for native unit tests.
#pragma once

#include <stddef.h>
#include <stdint.h>

void cc_sha256(const uint8_t* data, size_t len, uint8_t out[32]);
void cc_hmac_sha256(const uint8_t* key, size_t key_len, const uint8_t* data, size_t len, uint8_t out[32]);

// Lowercase hex. `out` must hold 2*len + 1 chars.
void cc_to_hex(const uint8_t* bytes, size_t len, char* out);
// Parses exactly 2*max_len hex chars (or fewer); returns bytes written, or 0 on a bad char.
size_t cc_from_hex(const char* hex, uint8_t* out, size_t max_len);
