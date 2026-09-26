// Minimal FIPS 180-4 SHA-256 for the Nano and the native tests (the ESP32 uses mbedTLS).
// 16-word rolling message schedule keeps the stack small on AVR.
#pragma once

#include <stddef.h>
#include <stdint.h>

class Sha256 {
 public:
  Sha256();
  void reset();  // start over without a temporary (stack matters on the Nano)
  void update(const uint8_t* data, size_t len);
  void final(uint8_t out[32]);

 private:
  void block(const uint8_t* p);
  uint32_t h_[8];
  uint8_t buf_[64];
  size_t buf_len_ = 0;
  uint64_t total_ = 0;
};
