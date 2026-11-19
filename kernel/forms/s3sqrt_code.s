# S3+sqrt, pure code.   S = x(S1 + S3 x2)   C = sqrt(1 - S2)
# COEFFICIENTS: S1 S3
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
    lui     $t4, S1 >> 16
.if S1 & 0xffff
    ori     $t4, $t4, S1 & 0xffff
.endif
    mul.s   $f2, $f0, $f0            # x2
    mtc1    $t4, $f6                 # S1
    lui     $t9, 0x3f80
    mul.s   $f4, $f4, $f2
    mtc1    $t9, $f10                # 1.0
    andi    $t2, $t0, 0x4000         # cosine octants?
    add.s   $f4, $f4, $f6
    mul.s   $f4, $f4, $f0            # S
    andi    $t5, $t0, 0x8000         # negate?
    mul.s   $f12, $f4, $f4
    sub.s   $f12, $f10, $f12
    sqrt.s  $f12, $f12               # C = sqrt(1 - S2)
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
    lui     $t3, S3 >> 16
.if S3 & 0xffff
    ori     $t3, $t3, S3 & 0xffff
.endif
    cvt.s.w $f0, $f0                 # x
    mtc1    $t3, $f4                 # S3
    lui     $t4, S1 >> 16
.if S1 & 0xffff
    ori     $t4, $t4, S1 & 0xffff
.endif
    mul.s   $f2, $f0, $f0            # x2
    mtc1    $t4, $f6                 # S1
    andi    $t2, $t0, 0x4000         # cosine octants?
    mul.s   $f4, $f4, $f2
    lui     $t9, 0x3f80
    add.s   $f4, $f4, $f6
    mtc1    $t9, $f10                # 1.0
    mul.s   $f0, $f4, $f0            # S
    beqz    $t2, 1f                  # sine octants: the result is S
    andi    $t5, $t0, 0x8000         # negate? (delay slot)
    mul.s   $f4, $f0, $f0
    sub.s   $f4, $f10, $f4
    sqrt.s  $f0, $f4                 # C = sqrt(1 - S2)
1:  bnezl   $t5, 2f
    neg.s   $f0, $f0
2:  jr      $ra
    nop
    .size   trig_sin, . - trig_sin
