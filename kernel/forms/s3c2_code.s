# S3C2, pure code.   S = x(S1 + S3 x2)   C = 1 + C2 x2
# COEFFICIENTS: S1 S3 C2
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
    lui     $t3, S3 >> 16
.if S3 & 0xffff
    ori     $t3, $t3, S3 & 0xffff
.endif
    cvt.s.w $f0, $f0                 # x
    mtc1    $t3, $f4                 # S3
    lui     $t4, C2 >> 16
.if C2 & 0xffff
    ori     $t4, $t4, C2 & 0xffff
.endif
    mul.s   $f2, $f0, $f0            # x2
    mtc1    $t4, $f12                # C2
    lui     $t6, S1 >> 16
.if S1 & 0xffff
    ori     $t6, $t6, S1 & 0xffff
.endif
    mtc1    $t6, $f6                 # S1
    mul.s   $f4, $f4, $f2
    lui     $t9, 0x3f80
    mul.s   $f12, $f12, $f2
    mtc1    $t9, $f10                # 1.0
    add.s   $f4, $f4, $f6
    andi    $t2, $t0, 0x4000         # cosine octants?
    add.s   $f12, $f12, $f10         # C
    mul.s   $f4, $f4, $f0            # S
    andi    $t5, $t0, 0x8000         # negate?
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
trig_sin:                            # shared tail: f * (k0 + k1 x2); sine (S1, S3, f = x), cosine (1, C2, f = 1)
    addiu   $t0, $a0, 0x2000
    andi    $t1, $t0, 0x3fff
    addiu   $t1, $t1, -0x2000        # x
    mtc1    $t1, $f0
    andi    $t2, $t0, 0x4000         # cosine octants?
    andi    $t5, $t0, 0x8000         # negate?
    cvt.s.w $f0, $f0                 # x
    lui     $t3, S3 >> 16
.if S3 & 0xffff
    ori     $t3, $t3, S3 & 0xffff
.endif
    mul.s   $f2, $f0, $f0            # x2
    lui     $t8, S1 >> 16
    beqz    $t2, 1f
.if S1 & 0xffff
    ori     $t8, $t8, S1 & 0xffff    # (delay slot)
.else
    nop
.endif
    lui     $t3, C2 >> 16
.if C2 & 0xffff
    ori     $t3, $t3, C2 & 0xffff
.endif
    lui     $t8, 0x3f80              # 1.0
    mtc1    $t8, $f0                 # f = 1.0
1:  mtc1    $t3, $f4
    mtc1    $t8, $f8
    mul.s   $f4, $f4, $f2
    add.s   $f4, $f4, $f8
    mul.s   $f0, $f4, $f0
    bnezl   $t5, 2f
    neg.s   $f0, $f0
2:  jr      $ra
    nop
    .size   trig_sin, . - trig_sin
