#include "crypto.h"

#include <string.h>

#if defined(CALLCLOCK_NATIVE)
#include "sha256_portable.h"

void cc_sha256(const uint8_t* data, size_t len, uint8_t out[32]) {
  Sha256 h;
  h.update(data, len);
  h.final(out);
}

void cc_hmac_sha256(const uint8_t* key, size_t key_len, const uint8_t* data, size_t len, uint8_t out[32]) {
  uint8_t k[64] = {0};
  if (key_len > 64) {
    cc_sha256(key, key_len, k);
  } else {
    memcpy(k, key, key_len);
  }
  uint8_t ipad[64], opad[64];
  for (int i = 0; i < 64; i++) {
    ipad[i] = k[i] ^ 0x36;
    opad[i] = k[i] ^ 0x5c;
  }
  uint8_t inner[32];
  Sha256 hi;
  hi.update(ipad, 64);
  hi.update(data, len);
  hi.final(inner);
  Sha256 ho;
  ho.update(opad, 64);
  ho.update(inner, 32);
  ho.final(out);
}
#else
#include "mbedtls/md.h"

void cc_sha256(const uint8_t* data, size_t len, uint8_t out[32]) {
  mbedtls_md(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), data, len, out);
}

void cc_hmac_sha256(const uint8_t* key, size_t key_len, const uint8_t* data, size_t len, uint8_t out[32]) {
  mbedtls_md_hmac(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), key, key_len, data, len, out);
}
#endif

void cc_to_hex(const uint8_t* bytes, size_t len, char* out) {
  static const char* digits = "0123456789abcdef";
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
