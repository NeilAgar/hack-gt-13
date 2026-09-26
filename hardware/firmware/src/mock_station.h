// The FAKE nurse-call station for the demo: CALL button latches the call LED on, CANCEL turns it off.
//
// INDEPENDENCE RULE: this module must never share state with call_clock (or anything that times
// calls). The only coupling is OPTICAL: the LDR watches the LED this module drives. A witness has
// to be independent of the system it watches; if Call Clock read the button state directly it
// would be measuring what the call system *claims*, not what a resident can see on the wall.
// That is also why it runs unchanged on a real wall station, where there is no button to read.
#pragma once

#include <stdint.h>

namespace mock_station {
void begin();
void poll(uint32_t now_ms);  // reads buttons, drives the call LED and dome light
}  // namespace mock_station
