# S7C6, one data line.   S = x(S1 + x2(S3 + x2(S5 + S7 x2)))   C = 1 + x2(C2 + x2(C4 + C6 x2))
# COEFFICIENTS: S1 S3 S5 S7 C2 C4 C6
# LINE: S1 S3 C2 C4
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
    lui     $t3, S7 >> 16
.if S7 & 0xffff
    ori     $t3, $t3, S7 & 0xffff
.endif
    cvt.s.w $f0, $f0                 # x
    mtc1    $t3, $f4                 # S7
    lui     $t4, C6 >> 16
.if C6 & 0xffff
    ori     $t4, $t4, C6 & 0xffff
.endif
    mul.s   $f2, $f0, $f0            # x2
    mtc1    $t4, $f12                # C6
    lui     $t3, S5 >> 16
.if S5 & 0xffff
    ori     $t3, $t3, S5 & 0xffff
.endif
    mtc1    $t3, $f6                 # S5
    mul.s   $f4, $f4, $f2
    lwc1    $f14, %lo(trig_k+12)($t7) # C4
    mul.s   $f12, $f12, $f2
    lwc1    $f8, %lo(trig_k+4)($t7)  # S3
    add.s   $f4, $f4, $f6
    lwc1    $f16, %lo(trig_k+8)($t7) # C2
    add.s   $f12, $f12, $f14
    lwc1    $f18, %lo(trig_k)($t7)   # S1
    mul.s   $f4, $f4, $f2
    lui     $t9, 0x3f80
    mul.s   $f12, $f12, $f2
    mtc1    $t9, $f10                # 1.0
    add.s   $f4, $f4, $f8
    andi    $t2, $t0, 0x4000         # cosine octants?
    add.s   $f12, $f12, $f16
    mul.s   $f4, $f4, $f2
    andi    $t5, $t0, 0x8000         # negate?
    mul.s   $f12, $f12, $f2
    add.s   $f4, $f4, $f18
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
    lui     $t3, S7 >> 16                 # (delay slot: the lui)
.if S7 & 0xffff
    ori     $t3, $t3, S7 & 0xffff
.endif
    mtc1    $t3, $f4                 # S7
    lui     $t4, S5 >> 16
.if S5 & 0xffff
    ori     $t4, $t4, S5 & 0xffff
.endif
    mtc1    $t4, $f6                 # S5
    mul.s   $f4, $f4, $f2
    lwc1    $f8, %lo(trig_k+4)($t7)  # S3
    add.s   $f4, $f4, $f6
    lwc1    $f10, %lo(trig_k)($t7)   # S1
    mul.s   $f4, $f4, $f2
    add.s   $f4, $f4, $f8
    mul.s   $f4, $f4, $f2
    add.s   $f4, $f4, $f10
    mul.s   $f0, $f4, $f0
1:  bnezl   $t5, 3f
    neg.s   $f0, $f0
3:  jr      $ra
    nop
2:  lui     $t4, C6 >> 16
.if C6 & 0xffff
    ori     $t4, $t4, C6 & 0xffff
.endif
    mtc1    $t4, $f4                 # C6
    lwc1    $f6, %lo(trig_k+12)($t7) # C4
    lui     $t9, 0x3f80
    mul.s   $f4, $f4, $f2
    lwc1    $f8, %lo(trig_k+8)($t7)  # C2
    add.s   $f4, $f4, $f6
    mtc1    $t9, $f10                # 1.0
    mul.s   $f4, $f4, $f2
    add.s   $f4, $f4, $f8
    mul.s   $f4, $f4, $f2
    b       1b
    add.s   $f0, $f4, $f10           # (delay slot)
    .size   trig_sin, . - trig_sin
