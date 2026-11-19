# C2+sqrt, one data line.   C = 1 + C2 x2   S = sqrt(1 - C2), with the sign of x
# COEFFICIENTS: C2
# LINE: C2 ONE
    .set noreorder
    .set noat
    .text
    .global trig_sincos
    .type   trig_sincos, @function
    .balign 32
trig_sincos:
    addiu   $t0, $a0, 0x2000
    andi    $t1, $t0, 0x3fff
    addiu   $t1, $t1, -0x2000        # x
    mtc1    $t1, $f0
    lui     $t7, %hi(trig_k)
    lwc1    $f12, %lo(trig_k)($t7)   # C2
    cvt.s.w $f0, $f0                 # x
    lwc1    $f10, %lo(trig_k+4)($t7) # 1.0
    andi    $t2, $t0, 0x4000         # cosine octants?
    mul.s   $f2, $f0, $f0            # x2
    andi    $t5, $t0, 0x8000         # negate?
    mul.s   $f12, $f12, $f2
    add.s   $f12, $f12, $f10         # C
    mul.s   $f4, $f12, $f12
    sub.s   $f4, $f10, $f4
    sqrt.s  $f4, $f4                 # S = sqrt(1 - C2)
    bltzl   $t1, 1f                  # x < 0: S < 0 (the delay slot runs only when taken)
    neg.s   $f4, $f4
1:  beqz    $t2, 2f
    mov.s   $f6, $f4                 # (delay slot)
    mov.s   $f4, $f12                # odd octant: sin = C, cos = -S
    neg.s   $f12, $f6
2:  beqz    $t5, 3f
    mov.s   $f0, $f4                 # (delay slot)
    neg.s   $f0, $f4
    neg.s   $f12, $f12
3:  jr      $ra
    mov.s   $f2, $f12                # (delay slot)
    .size   trig_sincos, . - trig_sincos

    .global trig_sin
    .type   trig_sin, @function
    .balign 32
trig_sin:
    addiu   $t0, $a0, 0x2000
    andi    $t1, $t0, 0x3fff
    addiu   $t1, $t1, -0x2000        # x
    mtc1    $t1, $f0
    lui     $t7, %hi(trig_k)
    lwc1    $f12, %lo(trig_k)($t7)   # C2
    cvt.s.w $f0, $f0                 # x
    lwc1    $f10, %lo(trig_k+4)($t7) # 1.0
    andi    $t2, $t0, 0x4000         # cosine octants?
    mul.s   $f2, $f0, $f0            # x2
    andi    $t5, $t0, 0x8000         # negate?
    mul.s   $f12, $f12, $f2
    bnez    $t2, 1f                  # cosine octants: the result is C
    add.s   $f0, $f12, $f10          # C (delay slot)
    mul.s   $f4, $f0, $f0
    sub.s   $f4, $f10, $f4
    sqrt.s  $f0, $f4                 # S = sqrt(1 - C2)
    bltzl   $t1, 1f                  # x < 0: S < 0
    neg.s   $f0, $f0
1:  bnezl   $t5, 2f
    neg.s   $f0, $f0
2:  jr      $ra
    nop
    .size   trig_sin, . - trig_sin
