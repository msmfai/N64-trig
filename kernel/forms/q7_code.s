# Q7, pure code. Quadrant fold: t = a + 0x4000, x = (t & 0x7fff) - 0x4000 (|x| <= 90 degrees);
# sin = P(x), negated when bit 15 of t is set. cos(a) = sin(a + 0x4000).
#   P(x) = x(Q1 + x2(Q3 + x2(Q5 + Q7 x2)))
# COEFFICIENTS: Q1 Q3 Q5 Q7
# LINE:
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
    lui     $t7, Q7 >> 16
.if Q7 & 0xffff
    ori     $t7, $t7, Q7 & 0xffff
.endif
    cvt.s.w $f0, $f0                 # xs
    cvt.s.w $f12, $f12               # xc
    mtc1    $t7, $f6                 # Q7
    lui     $t8, Q5 >> 16
.if Q5 & 0xffff
    ori     $t8, $t8, Q5 & 0xffff
.endif
    mul.s   $f2, $f0, $f0            # xs2
    mtc1    $t8, $f8                 # Q5
    mul.s   $f14, $f12, $f12         # xc2
    lui     $t9, Q3 >> 16
.if Q3 & 0xffff
    ori     $t9, $t9, Q3 & 0xffff
.endif
    mul.s   $f4, $f6, $f2
    mtc1    $t9, $f10                # Q3
    mul.s   $f18, $f6, $f14
    add.s   $f4, $f4, $f8
    lui     $t7, Q1 >> 16
.if Q1 & 0xffff
    ori     $t7, $t7, Q1 & 0xffff
.endif
    add.s   $f18, $f18, $f8
    mul.s   $f4, $f4, $f2
    mtc1    $t7, $f16                # Q1
    mul.s   $f18, $f18, $f14
    add.s   $f4, $f4, $f10
    add.s   $f18, $f18, $f10
    mul.s   $f4, $f4, $f2
    andi    $t5, $t0, 0x8000         # negate the sine?
    mul.s   $f18, $f18, $f14
    add.s   $f4, $f4, $f16
    add.s   $f18, $f18, $f16
    mul.s   $f0, $f4, $f0            # sin
    andi    $t6, $t3, 0x8000         # negate the cosine?
    mul.s   $f2, $f18, $f12          # cos
    bnezl   $t5, 1f                  # the delay slot runs only when taken
    neg.s   $f0, $f0
1:  bnezl   $t6, 2f
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
    lui     $t3, Q7 >> 16
.if Q7 & 0xffff
    ori     $t3, $t3, Q7 & 0xffff
.endif
    cvt.s.w $f0, $f0                 # x
    mtc1    $t3, $f4                 # Q7
    lui     $t4, Q5 >> 16
.if Q5 & 0xffff
    ori     $t4, $t4, Q5 & 0xffff
.endif
    mul.s   $f2, $f0, $f0            # x2
    mtc1    $t4, $f6                 # Q5
    lui     $t6, Q3 >> 16
.if Q3 & 0xffff
    ori     $t6, $t6, Q3 & 0xffff
.endif
    mul.s   $f4, $f4, $f2
    mtc1    $t6, $f8                 # Q3
    lui     $t7, Q1 >> 16
.if Q1 & 0xffff
    ori     $t7, $t7, Q1 & 0xffff
.endif
    add.s   $f4, $f4, $f6
    mtc1    $t7, $f10                # Q1
    mul.s   $f4, $f4, $f2
    andi    $t5, $t0, 0x8000         # negate?
    add.s   $f4, $f4, $f8
    mul.s   $f4, $f4, $f2
    add.s   $f4, $f4, $f10
    mul.s   $f0, $f4, $f0
    bnezl   $t5, 1f
    neg.s   $f0, $f0
1:  jr      $ra
    nop
    .size   trig_sin, . - trig_sin
