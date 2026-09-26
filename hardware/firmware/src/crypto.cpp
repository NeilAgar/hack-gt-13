#include "crypto.h"

#include <string.h>

#if defined(ESP_PLATFORM)
CcSha256::CcSha256() {
  mbedtls_md_init(&ctx_);
  mbedtls_md_setup(&ctx_, mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), 0);
  mbedtls_md_starts(&ctx_);
}
CcSha256::~CcSha256() { mbedtls_md_free(&ctx_); }
void CcSha256::update(const void* data, size_t len) { mbedtls_md_update(&ctx_, (const unsigned char*)data, len); }
void CcSha256::finish(uint8_t out[32]) { mbedtls_md_finish(&ctx_, out); }

void cc_hmac_sha256(const uint8_t* key, size_t key_len, const uint8_t* data, size_t len, uint8_t out[32]) {
  mbedtls_md_hmac(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), key, key_len, data, len, out);
}
#else
CcSha256::CcSha256() {}
CcSha256::~CcSha256() {}
void CcSha256::update(const void* data, size_t len) { h_.update((const uint8_t*)data, len); }
void CcSha256::finish(uint8_t out[32]) { h_.final(out); }

void cc_hmac_sha256(const uint8_t* key, size_t key_len, const uint8_t* data, size_t len, uint8_t out[32]) {
  // Device keys are 32 bytes. HMAC would hash keys longer than 64 bytes first; we don't support that.
  if (key_len > 64) key_len = 64;
  uint8_t pad[64];  // one buffer for ipad then opad, one SHA object: RAM matters on the Nano
  for (uint8_t i = 0; i < 64; i++) pad[i] = (i < key_len ? key[i] : 0) ^ 0x36;
  Sha256 h;
  h.update(pad, 64);
  h.update(data, len);
  h.final(out);  // inner hash, parked in `out`
  for (uint8_t i = 0; i < 64; i++) pad[i] = (i < key_len ? key[i] : 0) ^ 0x5c;
  h.reset();
  h.update(pad, 64);
  h.update(out, 32);
  h.final(out);
}
#endif

void cc_sha256(const uint8_t* data, size_t len, uint8_t out[32]) {
  CcSha256 h;
  h.update(data, len);
  h.finish(out);
}

void cc_to_hex(const uint8_t* bytes, size_t len, char* out) {
  static const char digits[] = "0123456789abcdef";
  for (size_t i = 0; i < len; i++) {
    out[2 * i] = digits[bytes[i] >> 4];
    out[2 * i + 1] = digits[bytes[i] & 0x0f];
  }
  out[2 * len] = '\0';
}

static int hexval(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

size_t cc_from_hex(const char* hex, uint8_t* out, size_t max_len) {
  size_t n = 0;
  while (n < max_len && hex[2 * n] && hex[2 * n + 1]) {
    int hi = hexval(hex[2 * n]), lo = hexval(hex[2 * n + 1]);
    if (hi < 0 || lo < 0) return 0;
    out[n++] = (uint8_t)((hi << 4) | lo);
  }
  return n;
}
