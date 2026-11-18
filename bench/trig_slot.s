# Fixed kernel slot (TRIG_FUNC 9). Copied to src/game/trig_slot.s.
#
# bench/slot.py writes a kernel into these bytes of a built ROM. The slot has
# the same size for every kernel, so all other code and data stay at the same
# addresses: two ROMs that differ only in the kernel differ only in the slot.
#
#   trig_slot + 0x000   trig_sincos   at most 0x180 bytes
#   trig_slot + 0x180   trig_sin      at most 0x180 bytes
#   trig_slot + 0x300   trig_k        16 bytes of data (one data-cache line)
#
# The placeholder kernel returns 0. The marker in trig_k lets slot.py find
# the slot in the ROM.
#if TRIG_FUNC == 9
    .set noreorder
    .set noat
    .text
    .balign 32
    .global trig_slot
trig_slot:
    .global trig_sincos
    .type   trig_sincos, @function
trig_sincos:
    mtc1    $zero, $f0
    jr      $ra
    mtc1    $zero, $f2
    .org    0x180
    .global trig_sin
    .type   trig_sin, @function
trig_sin:
    jr      $ra
    mtc1    $zero, $f0
    .org    0x300
    .global trig_k
trig_k:
    .ascii  "TRIG-SLOT-MARKER"
    .org    0x320
#endif
