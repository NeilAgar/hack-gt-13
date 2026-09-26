#include "timefmt.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// Days since 1970-01-01 → civil date (Howard Hinnant's algorithm).
static void civil_from_days(int32_t z, int32_t* y, unsigned* m, unsigned* d) {
  z += 719468;
  const int32_t era = (z >= 0 ? z : z - 146096) / 146097;
  const uint32_t doe = (uint32_t)(z - era * 146097);
  const uint32_t yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
  const uint32_t doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
  const uint32_t mp = (5 * doy + 2) / 153;
  *d = doy - (153 * mp + 2) / 5 + 1;
  *m = mp < 10 ? mp + 3 : mp - 9;
  *y = (int32_t)yoe + era * 400 + (*m <= 2);
}

void cc_format_iso(uint32_t epoch_utc, int32_t offset_s, char* out) {
  // 32-bit math is enough: epochs we accept are > 1.6e9, far above any offset.
  const uint32_t local = epoch_utc + (uint32_t)offset_s;
  const int32_t days = (int32_t)(local / 86400UL);
  const int32_t secs = (int32_t)(local % 86400UL);
  int32_t y;
  unsigned mo, d;
  civil_from_days(days, &y, &mo, &d);
  const char sign = offset_s < 0 ? '-' : '+';
  const int32_t off = offset_s < 0 ? -offset_s : offset_s;
  snprintf(out, 26, "%04ld-%02u-%02uT%02ld:%02ld:%02ld%c%02ld:%02ld", (long)y, mo, d, (long)(secs / 3600),
           (long)(secs / 60 % 60), (long)(secs % 60), sign, (long)(off / 3600), (long)(off / 60 % 60));
}

int cc_local_hour(uint32_t epoch_utc, int32_t offset_s) {
  return (int)(((epoch_utc + (uint32_t)offset_s) % 86400UL) / 3600UL);
}

// Finds "key": and returns a pointer to the value after it, or null.
static const char* find_value(const char* line, const char* key) {
  const char* p = strstr(line, key);
  if (!p) return nullptr;
  p += strlen(key);
  while (*p == ' ') p++;
  if (*p != ':') return nullptr;
  p++;
  while (*p == ' ') p++;
  return p;
}

bool cc_parse_time_cmd(const char* line, uint32_t* epoch, int32_t* offset_s) {
  if (!strstr(line, "\"cmd\"") || !strstr(line, "\"time\"")) return false;
  const char* p = find_value(line, "\"epoch\"");
  if (!p || *p < '0' || *p > '9') return false;
  char* end;
  const unsigned long e = strtoul(p, &end, 10);  // unsigned: 32-bit on AVR, good until 2106
  if (end == p || e < 1600000000UL) return false;
  *epoch = (uint32_t)e;
  p = find_value(line, "\"tz_offset\"");
  if (p) {
    const long off = strtol(p, &end, 10);
    if (end != p && off >= -14L * 3600 && off <= 14L * 3600) *offset_s = (int32_t)off;
  }
  return true;
}
