# S5C4, one data line.   S = x(S1 + x2(S3 + S5 x2))   C = 1 + x2(C2 + C4 x2)
# COEFFICIENTS: S1 S3 S5 C2 C4
# LINE: S1 S3 C2 ONE
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
    lui     $t3, S5 >> 16            # S5
.if S5 & 0xffff
    ori     $t3, $t3, S5 & 0xffff
.endif
    cvt.s.w $f0, $f0                 # x
    mtc1    $t3, $f4
    lui     $t4, C4 >> 16            # C4
.if C4 & 0xffff
    ori     $t4, $t4, C4 & 0xffff
.endif
    mul.s   $f2, $f0, $f0            # x2
    mtc1    $t4, $f12
    lwc1    $f6, %lo(trig_k+4)($t7)  # b
    lwc1    $f14, %lo(trig_k+8)($t7) # d
    mul.s   $f4, $f4, $f2
    lwc1    $f8, %lo(trig_k)($t7)    # a
    mul.s   $f12, $f12, $f2
    lwc1    $f10, %lo(trig_k+12)($t7) # 1.0
    add.s   $f4, $f4, $f6
    add.s   $f12, $f12, $f14
    mul.s   $f4, $f4, $f2
    andi    $t2, $t0, 0x4000         # cosine octants?
    mul.s   $f12, $f12, $f2
    andi    $t5, $t0, 0x8000         # negate?
    add.s   $f4, $f4, $f8
    add.s   $f12, $f12, $f10         # C
    mul.s   $f4, $f4, $f0            # S
    beqz    $t2, 1f
    mov.s   $f6, $f4                 # (delay slot, harmless when taken)
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
    andi    $t2, $t0, 0x4000         # cosine octants?
    lui     $t7, %hi(trig_k)
    cvt.s.w $f0, $f0                 # x
    andi    $t5, $t0, 0x8000         # negate?
    mul.s   $f2, $f0, $f0            # x2
    bnez    $t2, 2f
    lui     $t3, S5 >> 16            # S5 (delay slot, harmless in the cosine path)
.if S5 & 0xffff
    ori     $t3, $t3, S5 & 0xffff
.endif
    mtc1    $t3, $f4                 # sine: x * (a + x2*(b + c*x2))
    lwc1    $f6, %lo(trig_k+4)($t7)  # b
    lwc1    $f8, %lo(trig_k)($t7)    # a
    mul.s   $f4, $f4, $f2
    add.s   $f4, $f4, $f6
    mul.s   $f4, $f4, $f2
    add.s   $f4, $f4, $f8
    mul.s   $f0, $f4, $f0
1:  bnezl   $t5, 3f                  # negate: the delay slot runs only when taken
    neg.s   $f0, $f0
3:  jr      $ra
    nop
2:  lui     $t4, C4 >> 16            # cosine: 1 + x2*(C2 + C4*x2)
.if C4 & 0xffff
    ori     $t4, $t4, C4 & 0xffff
.endif
    mtc1    $t4, $f4
    lwc1    $f6, %lo(trig_k+8)($t7)  # d
    lwc1    $f8, %lo(trig_k+12)($t7) # 1.0
    mul.s   $f4, $f4, $f2
    add.s   $f4, $f4, $f6
    mul.s   $f4, $f4, $f2
    b       1b
    add.s   $f0, $f4, $f8            # (delay slot)
    .size   trig_sin, . - trig_sin
