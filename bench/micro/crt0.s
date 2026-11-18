# Entry of the timing ROM (bench/micro). libdragon's IPL3 (compatibility
# build, ipl3_compat.z64) copies 1 MiB of ROM from 0x1000 to 0x80000400 and
# jumps here. No OS: interrupts off, coprocessor 1 usable.
    .set noreorder
    .set noat
    .section .text.start, "ax"
    .global _start
_start:
    lui     $sp, 0x803F
    ori     $sp, $sp, 0xFC00
    la      $t0, __bss_start
    la      $t1, __bss_end
1:  beq     $t0, $t1, 2f
    nop
    sw      $zero, 0($t0)
    b       1b
    addiu   $t0, $t0, 4
2:  lui     $t0, 0xA480             # boot done: SI idle, then 8 to the PIF RAM control word
3:  lw      $t1, 0x18($t0)          # (without it the PIF holds the CPU in NMI after a while)
    andi    $t1, $t1, 3
    bnez    $t1, 3b
    nop
    lui     $t0, 0xBFC0
    addiu   $t1, $zero, 8
    sw      $t1, 0x7FC($t0)
    lui     $t0, 0x3000             # Status: CU0 | CU1, FR = 0, interrupts off
    mtc0    $t0, $12
    nop
    lui     $t0, 0x0100             # FCSR: flush denormals, no exceptions enabled
    ctc1    $t0, $31
    nop
    jal     main
    nop
4:  b       4b
    nop

    .text
    .global read_count
read_count:                         # CP0 Count: one tick per two CPU cycles
    mfc0    $v0, $9
    jr      $ra
    nop

    .global null_sin
null_sin:                           # the empty function the timings subtract
    jr      $ra
    mtc1    $zero, $f0

    .global null_sincos
null_sincos:
    mtc1    $zero, $f0
    jr      $ra
    mtc1    $zero, $f2

    .global emux_log
emux_log:                           # ares emux XLOG $t0, code 0 (Homebrew Mode only)
    move    $t0, $a0
    .word   0x42800025
    jr      $ra
    nop

    .global emux_exit
emux_exit:                          # ares emux XIOCTL exit
    .word   0x4200006c
    jr      $ra
    nop
