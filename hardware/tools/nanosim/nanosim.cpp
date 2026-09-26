// Runs the REAL Call Clock Nano firmware (firmware.elf) in simavr, with a simulated room:
//   - the mock CALL/CANCEL buttons are pressed on a script
//   - the firmware's own call-LED pin (D6) is fed back into the LDR input (A0), like the tape tube
//   - the PIR pin (D2) goes high when "someone walks in"
// Two modes:
//   nanosim firmware.elf out.txt                   scripted run, two power cycles (EEPROM carried over)
//   nanosim firmware.elf out.txt pty [eeprom.bin]  one boot with the UART on /tmp/simavr-uart0, for the bridge
// Build + run + verify: bash hardware/tools/nanosim/run.sh  (needs: apt install simavr libsimavr-dev libelf-dev)
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <simavr/avr_adc.h>
#include <simavr/avr_eeprom.h>
#include <simavr/avr_ioport.h>
#include <simavr/avr_uart.h>
#include <simavr/sim_avr.h>
#include <simavr/sim_elf.h>
extern "C" {
#include <simavr/parts/uart_pty.h>
}

static const double HZ = 16000000.0;
static avr_t* avr;
static elf_firmware_t fw;
static FILE* out;
static char line[1024];
static int line_len = 0;
static avr_irq_t *adc0, *uart_in;
static uint8_t ext_mask = 0, ext_value = 0;
enum { PIR = 2, CALL_BTN = 4, CANCEL_BTN = 5, CALL_LED = 6 };  // port D bits (Nano D2, D4, D5, D6)

static void uart_out(avr_irq_t*, uint32_t value, void*) {
  char c = (char)value;
  if (c == '\n') {
    line[line_len] = 0;
    fprintf(out, "%s\n", line);
    fflush(out);
    line_len = 0;
  } else if (c != '\r' && line_len < (int)sizeof(line) - 1) {
    line[line_len++] = c;
  }
}

// The optical link: the LDR sees the mock call LED.
static void led_changed(avr_irq_t*, uint32_t value, void*) { avr_raise_irq(adc0, value ? 3500 : 1000); }

// Drive a port-D input from outside (simavr's pull-up would otherwise win over a raised IRQ).
static void drive(int bit, int level) {
  ext_mask |= (1 << bit);
  if (level) ext_value |= (1 << bit); else ext_value &= ~(1 << bit);
  avr_ioport_external_t e = {.name = 'D', .mask = ext_mask, .value = ext_value};
  avr_ioctl(avr, AVR_IOCTL_IOPORT_SET_EXTERNAL('D'), &e);
  avr_raise_irq(avr_io_getirq(avr, AVR_IOCTL_IOPORT_GETIRQ('D'), bit), level);
}

static const char* pending = nullptr;
static avr_cycle_count_t next_byte_at = 0;

static void run_until(double seconds) {
  const avr_cycle_count_t target = (avr_cycle_count_t)(seconds * HZ);
  while (avr->cycle < target) {
    const int st = avr_run(avr);
    if (st == cpu_Done || st == cpu_Crashed) {
      fprintf(out, "SIM cpu stopped (state %d)\n", st);
      exit(1);
    }
    if (pending && avr->cycle >= next_byte_at) {  // ~1 byte per 100 µs, like 115200 baud
      avr_raise_irq(uart_in, (uint8_t)*pending++);
      if (!*pending) pending = nullptr;
      next_byte_at = avr->cycle + 1600;
    }
  }
}

static double now_s() { return avr->cycle / HZ; }

static void send(const char* s) {
  pending = s;
  next_byte_at = avr->cycle;
  run_until(now_s() + 0.02 + strlen(s) * 0.0001);
}

static void press(int bit, double at) {
  run_until(at);
  drive(bit, 0);
  run_until(at + 0.15);
  drive(bit, 1);
}

static void new_chip(const uint8_t* eeprom) {
  avr = avr_make_mcu_by_name("atmega328p");
  avr_init(avr);
  avr->frequency = (uint32_t)HZ;
  avr_load_firmware(avr, &fw);
  avr->log = 0;
  uint32_t f = 0;
  avr_ioctl(avr, AVR_IOCTL_UART_GET_FLAGS('0'), &f);
  f &= ~AVR_UART_FLAG_STDIO;
  avr_ioctl(avr, AVR_IOCTL_UART_SET_FLAGS('0'), &f);
  avr_irq_register_notify(avr_io_getirq(avr, AVR_IOCTL_UART_GETIRQ('0'), UART_IRQ_OUTPUT), uart_out, nullptr);
  uart_in = avr_io_getirq(avr, AVR_IOCTL_UART_GETIRQ('0'), UART_IRQ_INPUT);
  adc0 = avr_io_getirq(avr, AVR_IOCTL_ADC_GETIRQ, ADC_IRQ_ADC0);
  avr_irq_register_notify(avr_io_getirq(avr, AVR_IOCTL_IOPORT_GETIRQ('D'), CALL_LED), led_changed, nullptr);
  if (eeprom) {
    avr_eeprom_desc_t d = {.ee = (uint8_t*)eeprom, .offset = 0, .size = 1024};
    avr_ioctl(avr, AVR_IOCTL_EEPROM_SET, &d);
  }
  ext_mask = ext_value = 0;
  run_until(0.001);
  drive(PIR, 0);
  drive(CALL_BTN, 1);
  drive(CANCEL_BTN, 1);
  avr_raise_irq(adc0, 1000);  // call light off at boot
}

static void save_eeprom(uint8_t* buf) {
  avr_eeprom_desc_t d = {.ee = buf, .offset = 0, .size = 1024};
  avr_ioctl(avr, AVR_IOCTL_EEPROM_GET, &d);
  if (d.ee != buf) memcpy(buf, d.ee, 1024);
}

// Call 1: someone arrives 21.4 s after the light comes on. Call 2: cancelled with no one entering.
static void two_calls(double t0) {
  press(CALL_BTN, t0 + 31.0);           // after the 30 s PIR warm-up
  run_until(t0 + 31.0 + 0.3 + 21.4);    // the light counts as ON after 300 ms
  drive(PIR, 1);
  run_until(t0 + 55.0);
  drive(PIR, 0);
  press(CANCEL_BTN, t0 + 58.0);
  press(CALL_BTN, t0 + 64.0);
  press(CANCEL_BTN, t0 + 76.0);
  run_until(t0 + 80.0);
}

int main(int argc, char** argv) {
  if (argc < 3 || elf_read_firmware(argv[1], &fw)) {
    fprintf(stderr, "usage: nanosim firmware.elf out.txt [pty [eeprom.bin]]\n");
    return 2;
  }
  out = fopen(argv[2], "w");
  static uint8_t ee[1024];

  if (argc > 3 && strcmp(argv[3], "pty") == 0) {
    const char* ee_path = argc > 4 ? argv[4] : nullptr;
    FILE* ef = ee_path ? fopen(ee_path, "rb") : nullptr;
    const bool have_ee = ef && fread(ee, 1, sizeof(ee), ef) == sizeof(ee);
    if (ef) fclose(ef);
    new_chip(have_ee ? ee : nullptr);
    static uart_pty_t pty;
    uart_pty_init(avr, &pty);
    uart_pty_connect(&pty, '0');
    fprintf(out, "SIM uart on /tmp/simavr-uart0\n");
    fflush(out);
    sleep(4);  // let the bridge open the port before the chip "boots"
    two_calls(0.0);
    sleep(3);
    if (ee_path) {
      save_eeprom(ee);
      FILE* wf = fopen(ee_path, "wb");
      fwrite(ee, 1, sizeof(ee), wf);
      fclose(wf);
    }
    return 0;
  }

  for (int boot = 1; boot <= 2; boot++) {
    new_chip(boot == 1 ? nullptr : ee);  // a power cycle: a fresh chip, only the EEPROM survives
    fprintf(out, "SIM boot %d\n", boot);
    run_until(2.0);
    send("{\"cmd\":\"time\",\"epoch\":1790449402,\"tz_offset\":-14400}\n");
    two_calls(0.0);
    send("dump\n");
    run_until(now_s() + 8.0);
    send("status\n");
    run_until(now_s() + 1.0);
    save_eeprom(ee);
  }
  return 0;
}
