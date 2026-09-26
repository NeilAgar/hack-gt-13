// Minimal FIPS 180-4 SHA-256 for the native unit-test build only (the ESP32 uses mbedTLS).
#pragma once

#include <stddef.h>
#include <stdint.h>

class Sha256 {
 public:
  Sha256();
  void update(const uint8_t* data, size_t len);
  void final(uint8_t out[32]);

 private:
  void block(const uint8_t* p);
  uint32_t h_[8];
  uint8_t buf_[64];
  size_t buf_len_ = 0;
  uint64_t total_ = 0;
};
