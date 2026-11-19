# S7C6, pure code.   S = x(S1 + x2(S3 + x2(S5 + S7 x2)))   C = 1 + x2(C2 + x2(C4 + C6 x2))
# COEFFICIENTS: S1 S3 S5 S7 C2 C4 C6
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
    lui     $t3, S7 >> 16
.if S7 & 0xffff
    ori     $t3, $t3, S7 & 0xffff
.endif
    lui     $t4, C6 >> 16
.if C6 & 0xffff
    ori     $t4, $t4, C6 & 0xffff
.endif
    cvt.s.w $f0, $f0                 # x
    mtc1    $t3, $f4                 # S7
    mtc1    $t4, $f12                # C6
    mul.s   $f2, $f0, $f0            # x2
    lui     $t3, S5 >> 16
.if S5 & 0xffff
    ori     $t3, $t3, S5 & 0xffff
.endif
    lui     $t4, C4 >> 16
.if C4 & 0xffff
    ori     $t4, $t4, C4 & 0xffff
.endif
    mtc1    $t3, $f6                 # S5
    mul.s   $f4, $f4, $f2
    mtc1    $t4, $f14                # C4
    mul.s   $f12, $f12, $f2
    lui     $t3, S3 >> 16
.if S3 & 0xffff
    ori     $t3, $t3, S3 & 0xffff
.endif
    add.s   $f4, $f4, $f6
    lui     $t4, C2 >> 16
.if C2 & 0xffff
    ori     $t4, $t4, C2 & 0xffff
.endif
    add.s   $f12, $f12, $f14
    mtc1    $t3, $f8                 # S3
    mul.s   $f4, $f4, $f2
    mtc1    $t4, $f16                # C2
    mul.s   $f12, $f12, $f2
    lui     $t3, S1 >> 16
.if S1 & 0xffff
    ori     $t3, $t3, S1 & 0xffff
.endif
    add.s   $f4, $f4, $f8
    lui     $t9, 0x3f80
    add.s   $f12, $f12, $f16
    mtc1    $t3, $f18                # S1
    mul.s   $f4, $f4, $f2
    mtc1    $t9, $f10                # 1.0
    mul.s   $f12, $f12, $f2
    andi    $t2, $t0, 0x4000         # cosine octants?
    add.s   $f4, $f4, $f18
    andi    $t5, $t0, 0x8000         # negate?
    add.s   $f12, $f12, $f10         # C
    mul.s   $f4, $f4, $f0            # S
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
trig_sin:                            # shared tail: f * (k0 + x2(k1 + x2(k2 + x2 h)))
    addiu   $t0, $a0, 0x2000
    andi    $t1, $t0, 0x3fff
    addiu   $t1, $t1, -0x2000        # x
    mtc1    $t1, $f0
    andi    $t2, $t0, 0x4000         # cosine octants?
    andi    $t5, $t0, 0x8000         # negate?
    cvt.s.w $f0, $f0                 # x
    lui     $t3, S7 >> 16
.if S7 & 0xffff
    ori     $t3, $t3, S7 & 0xffff
.endif
    mul.s   $f2, $f0, $f0            # x2
    lui     $t4, S5 >> 16
.if S5 & 0xffff
    ori     $t4, $t4, S5 & 0xffff
.endif
    lui     $t6, S3 >> 16
.if S3 & 0xffff
    ori     $t6, $t6, S3 & 0xffff
.endif
    lui     $t8, S1 >> 16
    beqz    $t2, 1f
.if S1 & 0xffff
    ori     $t8, $t8, S1 & 0xffff    # (delay slot)
.else
    nop
.endif
    lui     $t3, C6 >> 16
.if C6 & 0xffff
    ori     $t3, $t3, C6 & 0xffff
.endif
    lui     $t4, C4 >> 16
.if C4 & 0xffff
    ori     $t4, $t4, C4 & 0xffff
.endif
    lui     $t6, C2 >> 16
.if C2 & 0xffff
    ori     $t6, $t6, C2 & 0xffff
.endif
    lui     $t8, 0x3f80              # 1.0
    mtc1    $t8, $f0                 # f = 1.0
1:  mtc1    $t3, $f4                 # h
    mtc1    $t4, $f6                 # k2
    mtc1    $t6, $f8                 # k1
    mul.s   $f4, $f4, $f2
    mtc1    $t8, $f10                # k0
    add.s   $f4, $f4, $f6
    mul.s   $f4, $f4, $f2
    add.s   $f4, $f4, $f8
    mul.s   $f4, $f4, $f2
    add.s   $f4, $f4, $f10
    mul.s   $f0, $f4, $f0
    bnezl   $t5, 3f
    neg.s   $f0, $f0
3:  jr      $ra
    nop
    .size   trig_sin, . - trig_sin
