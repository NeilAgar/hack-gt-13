// Wall-clock helpers with no time library and no timezone rules (for the Nano).
// The bridge sends {"cmd":"time","epoch":<UTC seconds>,"tz_offset":<seconds east of UTC>}; the Nano
// keeps epoch + millis() and applies that fixed offset. Pure C++, tested natively.
#pragma once

#include <stdint.h>

// "2026-09-26T15:03:22-04:00" (same shape as Python's isoformat()). `out` needs 26 bytes.
void cc_format_iso(uint32_t epoch_utc, int32_t offset_s, char* out);
// Local hour 0..23.
int cc_local_hour(uint32_t epoch_utc, int32_t offset_s);
// Parses the bridge's time command. Returns false if it isn't one. `offset_s` is left alone when absent.
bool cc_parse_time_cmd(const char* line, uint32_t* epoch, int32_t* offset_s);
