# Q7, one data line. Quadrant fold: t = a + 0x4000, x = (t & 0x7fff) - 0x4000 (|x| <= 90 degrees);
# sin = P(x), negated when bit 15 of t is set. cos(a) = sin(a + 0x4000).
#   P(x) = x(Q1 + x2(Q3 + x2(Q5 + Q7 x2)))
# COEFFICIENTS: Q1 Q3 Q5 Q7
# LINE: Q1 Q3 Q5 Q7
    .set noreorder
    .set noat
    .text
    .global trig_sincos
    .type   trig_sincos, @function
    .balign 32
trig_sincos:
    addiu   $t0, $a0, 0x4000         # sine: t
    addiu   $t3, $t0, 0x4000         # cosine: t + 0x4000
    andi    $t1, $t0, 0x7fff
    andi    $t4, $t3, 0x7fff
    addiu   $t1, $t1, -0x4000        # xs
    addiu   $t4, $t4, -0x4000        # xc
    mtc1    $t1, $f0
    mtc1    $t4, $f12
    lui     $t7, %hi(trig_k)
    cvt.s.w $f0, $f0                 # xs
    cvt.s.w $f12, $f12               # xc
    lwc1    $f6, %lo(trig_k+12)($t7) # Q7
    lwc1    $f8, %lo(trig_k+8)($t7)  # Q5
    mul.s   $f2, $f0, $f0            # xs2
    andi    $t5, $t0, 0x8000         # negate the sine?
    mul.s   $f14, $f12, $f12         # xc2
    andi    $t6, $t3, 0x8000         # negate the cosine?
    mul.s   $f4, $f6, $f2
    lwc1    $f10, %lo(trig_k+4)($t7) # Q3
    mul.s   $f18, $f6, $f14
    add.s   $f4, $f4, $f8
    add.s   $f18, $f18, $f8
    mul.s   $f4, $f4, $f2
    lwc1    $f16, %lo(trig_k)($t7)   # Q1
    mul.s   $f18, $f18, $f14
    add.s   $f4, $f4, $f10
    add.s   $f18, $f18, $f10
    mul.s   $f4, $f4, $f2
    nop                              # no multiplication directly after a multiplication
    mul.s   $f18, $f18, $f14
    add.s   $f4, $f4, $f16
    add.s   $f18, $f18, $f16
    mul.s   $f0, $f4, $f0            # sin
    bnezl   $t5, 1f                  # the delay slot runs only when taken
    neg.s   $f0, $f0
1:  mul.s   $f2, $f18, $f12          # cos
    bnezl   $t6, 2f
    neg.s   $f2, $f2
2:  jr      $ra
    nop
    .size   trig_sincos, . - trig_sincos

    .global trig_sin
    .type   trig_sin, @function
    .balign 32
trig_sin:
    addiu   $t0, $a0, 0x4000
    andi    $t1, $t0, 0x7fff
    addiu   $t1, $t1, -0x4000        # x
    mtc1    $t1, $f0
    lui     $t7, %hi(trig_k)
    lwc1    $f4, %lo(trig_k+12)($t7) # Q7
    cvt.s.w $f0, $f0                 # x
    lwc1    $f6, %lo(trig_k+8)($t7)  # Q5
    lwc1    $f8, %lo(trig_k+4)($t7)  # Q3
    mul.s   $f2, $f0, $f0            # x2
    lwc1    $f10, %lo(trig_k)($t7)   # Q1
    mul.s   $f4, $f4, $f2
    andi    $t5, $t0, 0x8000         # negate?
    add.s   $f4, $f4, $f6
    mul.s   $f4, $f4, $f2
    add.s   $f4, $f4, $f8
    mul.s   $f4, $f4, $f2
    add.s   $f4, $f4, $f10
    mul.s   $f0, $f4, $f0
    bnezl   $t5, 1f
    neg.s   $f0, $f0
1:  jr      $ra
    nop
    .size   trig_sin, . - trig_sin
