// SHA-256 and HMAC-SHA256. mbedTLS on the ESP32; a small portable SHA-256 on the Nano and in native tests.
#pragma once

#include <stddef.h>
#include <stdint.h>

#if defined(ESP_PLATFORM)
#include "mbedtls/md.h"
#else
#include "sha256_portable.h"
#endif

// Incremental SHA-256, so events can be hashed while they are printed (the Nano has 2 KB of RAM).
class CcSha256 {
 public:
  CcSha256();
  ~CcSha256();
  void update(const void* data, size_t len);
  void finish(uint8_t out[32]);

 private:
#if defined(ESP_PLATFORM)
  mbedtls_md_context_t ctx_;
#else
  Sha256 h_;
#endif
};

void cc_sha256(const uint8_t* data, size_t len, uint8_t out[32]);
// key_len ≤ 64 (device keys are 32 bytes).
void cc_hmac_sha256(const uint8_t* key, size_t key_len, const uint8_t* data, size_t len, uint8_t out[32]);

// Lowercase hex. `out` must hold 2*len + 1 chars.
void cc_to_hex(const uint8_t* bytes, size_t len, char* out);
// Parses up to max_len bytes of hex; returns bytes written, or 0 on a bad char.
size_t cc_from_hex(const char* hex, uint8_t* out, size_t max_len);
