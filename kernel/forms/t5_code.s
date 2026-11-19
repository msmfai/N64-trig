# T5, pure code. Octant fold (as kernel/s5c4_line.s); u = x(T1 + x2(T3 + T5 x2)) (u is near tan(x/2));
# d = 1/(1 + u2); S = 2u d, C = (1 - u2) d. One division gives both values.
# COEFFICIENTS: T1 T3 T5
# LINE:
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
    lui     $t3, T5 >> 16
.if T5 & 0xffff
    ori     $t3, $t3, T5 & 0xffff
.endif
    cvt.s.w $f0, $f0                 # x
    mtc1    $t3, $f4                 # T5
    lui     $t4, T3 >> 16
.if T3 & 0xffff
    ori     $t4, $t4, T3 & 0xffff
.endif
    mul.s   $f2, $f0, $f0            # x2
    mtc1    $t4, $f6                 # T3
    lui     $t6, T1 >> 16
.if T1 & 0xffff
    ori     $t6, $t6, T1 & 0xffff
.endif
    mul.s   $f4, $f4, $f2
    mtc1    $t6, $f8                 # T1
    add.s   $f4, $f4, $f6
    lui     $t9, 0x3f80
    mul.s   $f4, $f4, $f2
    mtc1    $t9, $f10                # 1.0
    add.s   $f4, $f4, $f8
    andi    $t2, $t0, 0x4000         # cosine octants?
    mul.s   $f4, $f4, $f0            # u
    andi    $t5, $t0, 0x8000         # negate?
    add.s   $f12, $f4, $f4           # 2u
    mul.s   $f6, $f4, $f4            # u2
    add.s   $f14, $f10, $f6          # 1 + u2
    sub.s   $f16, $f10, $f6          # 1 - u2
    div.s   $f14, $f10, $f14         # d
    mul.s   $f4, $f12, $f14          # S
    nop                              # no multiplication directly after a multiplication
    mul.s   $f12, $f16, $f14         # C
    beqz    $t2, 1f
    mov.s   $f6, $f4                 # (delay slot)
    mov.s   $f4, $f12                # odd octant: sin = C, cos = -S
    neg.s   $f12, $f6
1:  beqz    $t5, 2f
    mov.s   $f0, $f4                 # (delay slot)
    neg.s   $f0, $f4
    neg.s   $f12, $f12
2:  jr      $ra
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
    lui     $t3, T5 >> 16
.if T5 & 0xffff
    ori     $t3, $t3, T5 & 0xffff
.endif
    cvt.s.w $f0, $f0                 # x
    mtc1    $t3, $f4                 # T5
    lui     $t4, T3 >> 16
.if T3 & 0xffff
    ori     $t4, $t4, T3 & 0xffff
.endif
    mul.s   $f2, $f0, $f0            # x2
    mtc1    $t4, $f6                 # T3
    lui     $t6, T1 >> 16
.if T1 & 0xffff
    ori     $t6, $t6, T1 & 0xffff
.endif
    mul.s   $f4, $f4, $f2
    mtc1    $t6, $f8                 # T1
    add.s   $f4, $f4, $f6
    lui     $t9, 0x3f80
    mul.s   $f4, $f4, $f2
    mtc1    $t9, $f10                # 1.0
    add.s   $f4, $f4, $f8
    andi    $t2, $t0, 0x4000         # cosine octants?
    mul.s   $f4, $f4, $f0            # u
    andi    $t5, $t0, 0x8000         # negate?
    add.s   $f12, $f4, $f4           # 2u
    mul.s   $f6, $f4, $f4            # u2
    add.s   $f14, $f10, $f6          # 1 + u2
    bnezl   $t2, 1f                  # cosine octants: numerator 1 - u2
    sub.s   $f12, $f10, $f6
1:  div.s   $f14, $f10, $f14         # d
    mul.s   $f0, $f12, $f14
    bnezl   $t5, 2f
    neg.s   $f0, $f0
2:  jr      $ra
    nop
    .size   trig_sin, . - trig_sin
