# Hand-written trig_sin kernels for the SM64 trig benchmark (GNU as, VR4300).
# Copied to src/game/trig_kernels.s; selected by TRIG_FUNC (see trig_impl.c):
#   4  Silas Lock's folded polynomial
#   5  S5C6 with BFSK's coefficients, every constant built in code
#   6  S5C6 with BFSK's coefficients, the two short ones and 1.0 built in code,
#      the four long ones loaded from one 16-byte-aligned line (gTrigK)
#   7  LUTX16: 16-segment table + quadratic (gTrigLutx16, 17 x 32 bytes)
#   8  S5C6 "one constant": only S1 at full precision (lui + ori), the other
#      five in 8 mantissa bits (one lui each); no data. Its own coefficients
#      (fit/fit_one.py), less accurate than BFSK.
#
# float trig_sin(int angle): angle in $a0 (any value; only bits 0-15 matter),
# result in $f0. With TRIG_SINCOS, also _Complex float trig_sincos(int angle):
# sine in $f0, cosine in $f2, bit-identical to two trig_sin calls (checked in
# the ROM, trig_bench.c). Leaf functions, no stack, only caller-saved registers.
#
# Fold (all kernels): t = angle + 0x2000; x = (t & 0x3FFF) - 0x2000 is the
# angle's offset from the nearest quarter turn, |x| <= 0x2000 (45 degrees).
# Bit 14 of t selects the cosine polynomial, bit 15 of t negates.
# Verified bit-identical to the C versions over all 65536 angles
# (bench/README.md).
#
# Hazards observed: at least one instruction between mtc1 and the first use
# of its register; no two mul.s back to back and no mul.s in a branch delay
# slot (the VR4300 multiply erratum that -mfix4300 / -r4300_mul work around).

    .set noreorder
    .set noat
    .text

#if TRIG_FUNC >= 4

    .global trig_sin
    .type   trig_sin, @function
    .balign 32
trig_sin:

#if TRIG_FUNC == 4
# Silas: c = 1 + x2*(K1 + K2*x2) on the folded x; s = sqrt(1 - c*c).
# K1 = 4*C1, K2 = 16*C2 of the original (it folds to 2x): exact rescalings.
    addiu   $t0, $a0, 0x2000
    andi    $t1, $t0, 0x3fff
    addiu   $t1, $t1, -0x2000
    mtc1    $t1, $f0
    lui     $t3, 0x227c              # K2 = 0x227c6b4e
    ori     $t3, $t3, 0x6b4e
    cvt.s.w $f0, $f0                 # x
    mtc1    $t3, $f4
    lui     $t4, 0xb19d              # K1 = 0xb19dd974
    ori     $t4, $t4, 0xd974
    mtc1    $t4, $f6
    lui     $t6, 0x3f80              # 1.0
    mul.s   $f2, $f0, $f0            # x2
    mtc1    $t6, $f8
    andi    $t2, $t0, 0x4000
    mul.s   $f4, $f4, $f2
    andi    $t5, $a0, 0x8000         # Silas negates on bit 15 of the angle
    add.s   $f4, $f4, $f6
    mul.s   $f4, $f4, $f2
    bnez    $t2, 1f                  # cosine octants: c is the result
    add.s   $f0, $f4, $f8            # c (delay slot)
    mul.s   $f2, $f0, $f0
    sub.s   $f2, $f8, $f2
    sqrt.s  $f0, $f2
1:  bnez    $t5, 2f
    nop
    jr      $ra
    nop
2:  jr      $ra
    neg.s   $f0, $f0

#elif TRIG_FUNC == 5 || TRIG_FUNC == 6 || TRIG_FUNC == 8
# S5C6 / BFSK: sin = x*(S1 + x2*(S3 + S5*x2)); cos = 1 + x2*(C2 + x2*(C4 + C6*x2)).
    addiu   $t0, $a0, 0x2000
    andi    $t1, $t0, 0x3fff
    addiu   $t1, $t1, -0x2000
    mtc1    $t1, $f0
    andi    $t2, $t0, 0x4000
#if TRIG_FUNC == 6
    lui     $t7, %hi(gTrigK)         # s1, s3, c2, c4: one 16-byte line
#endif
    cvt.s.w $f0, $f0                 # x
#if TRIG_FUNC == 6
    addiu   $t7, $t7, %lo(gTrigK)
#endif
    mul.s   $f2, $f0, $f0            # x2
    bnez    $t2, 1f
    andi    $t5, $t0, 0x8000         # negate (delay slot)
# sine octants
#if TRIG_FUNC == 8
    lui     $t3, 0x1a94              # S5 = 0x1a940000
    mtc1    $t3, $f4
    lui     $t3, 0xaa25              # S3 = 0xaa250000
    mtc1    $t3, $f6
    lui     $t4, 0x38c9              # S1 = 0x38c90f98
    ori     $t4, $t4, 0x0f98
    mtc1    $t4, $f8
#else
    lui     $t3, 0x1a97              # S5 = 0x1a970000
    mtc1    $t3, $f4
#endif
#if TRIG_FUNC == 8
#elif TRIG_FUNC == 5
    lui     $t3, 0xaa24              # S3 = 0xaa24fee4
    ori     $t3, $t3, 0xfee4
    mtc1    $t3, $f6
    lui     $t4, 0x38c9              # S1 = 0x38c90dd0
    ori     $t4, $t4, 0x0dd0
    mtc1    $t4, $f8
#else
    lwc1    $f6, 4($t7)              # S3
    lwc1    $f8, 0($t7)              # S1
#endif
    mul.s   $f4, $f4, $f2
    add.s   $f4, $f4, $f6
    mul.s   $f4, $f4, $f2
    add.s   $f4, $f4, $f8
    mul.s   $f0, $f4, $f0
    bnez    $t5, 3f
    nop
    jr      $ra
    nop
# cosine octants
1:
#if TRIG_FUNC == 8
    lui     $t3, 0x932d              # C6 = 0x932d0000
    mtc1    $t3, $f4
    lui     $t3, 0x2286              # C4 = 0x22860000
    mtc1    $t3, $f6
    lui     $t4, 0xb19e              # C2 = 0xb19e0000
    mtc1    $t4, $f8
#else
    lui     $t3, 0x925d              # C6 = 0x925d0000
    mtc1    $t3, $f4
#endif
#if TRIG_FUNC == 8
#elif TRIG_FUNC == 5
    lui     $t3, 0x2280              # C4 = 0x2280c3c2
    ori     $t3, $t3, 0xc3c2
    mtc1    $t3, $f6
    lui     $t4, 0xb19d              # C2 = 0xb19de6b5
    ori     $t4, $t4, 0xe6b5
    mtc1    $t4, $f8
#else
    lwc1    $f6, 12($t7)             # C4
    lwc1    $f8, 8($t7)              # C2
#endif
    lui     $t6, 0x3f80              # 1.0
    mul.s   $f4, $f4, $f2
    mtc1    $t6, $f10
    add.s   $f4, $f4, $f6
    mul.s   $f4, $f4, $f2
    add.s   $f4, $f4, $f8
    mul.s   $f4, $f4, $f2
    add.s   $f0, $f4, $f10
    bnez    $t5, 3f
    nop
    jr      $ra
    nop
3:  jr      $ra
    neg.s   $f0, $f0

#elif TRIG_FUNC == 7
# LUTX16: node i = (|x| + 256) >> 9, d = |x| - i*512, node = 32 bytes:
#   sine line   S, C*M, S*K*M^2 -> s = S + (d*CM - d2*SKM2)
#   cosine line C, S*M, C*K*M^2 -> c = C - (d*SM + d2*CKM2)
# The sine value is odd in x: negate when x < 0 differs from bit 15 of t.
    addiu   $t0, $a0, 0x2000
    andi    $t1, $t0, 0x3fff
    addiu   $t1, $t1, -0x2000        # x
    sra     $t7, $t1, 31             # 0 or -1
    xor     $t1, $t1, $t7
    subu    $t1, $t1, $t7            # |x|
    addiu   $t8, $t1, 256
    sra     $t8, $t8, 9              # i
    sll     $t9, $t8, 9
    subu    $t9, $t1, $t9            # d
    mtc1    $t9, $f0
    sll     $t8, $t8, 5
    lui     $t3, %hi(gTrigLutx16)
    addiu   $t3, $t3, %lo(gTrigLutx16)
    cvt.s.w $f0, $f0                 # d
    addu    $t3, $t3, $t8            # node
    andi    $t2, $t0, 0x4000
    srl     $t5, $t0, 15
    andi    $t5, $t5, 1              # negate (cosine octants)
    mul.s   $f2, $f0, $f0            # d2
    bnez    $t2, 1f
    andi    $t7, $t7, 1              # x < 0 (delay slot)
# sine octants
    lwc1    $f6, 4($t3)
    lwc1    $f8, 8($t3)
    lwc1    $f4, 0($t3)
    mul.s   $f6, $f0, $f6            # d*CM
    nop
    mul.s   $f8, $f2, $f8            # d2*SKM2
    xor     $t5, $t5, $t7
    sub.s   $f6, $f6, $f8
    add.s   $f0, $f4, $f6
    bnez    $t5, 3f
    nop
    jr      $ra
    nop
# cosine octants
1:  lwc1    $f6, 20($t3)
    lwc1    $f8, 24($t3)
    lwc1    $f4, 16($t3)
    mul.s   $f6, $f0, $f6            # d*SM
    nop
    mul.s   $f8, $f2, $f8            # d2*CKM2
    add.s   $f6, $f6, $f8
    sub.s   $f0, $f4, $f6
    bnez    $t5, 3f
    nop
    jr      $ra
    nop
3:  jr      $ra
    neg.s   $f0, $f0

#else
#error "unknown TRIG_FUNC for trig_kernels.s"
#endif

    .size   trig_sin, . - trig_sin

#if TRIG_SINCOS
# _Complex float trig_sincos(int angle): sine in $f0, cosine in $f2, each
# bit-identical to trig_sin(angle) and trig_sin(angle + 0x4000). One fold;
# both halves computed. cos(a) = sin(a + 0x4000): the same x, bit 14 flipped,
# bit 15 flipped when bit 14 was set.
    .global trig_sincos
    .type   trig_sincos, @function
    .balign 32
trig_sincos:

#if TRIG_FUNC == 4
# Silas: c from the polynomial, s = sqrt(1 - c*c). Even octants (bit 14 of t
# clear): sin = s, cos = c; odd: sin = c, cos = s. Sine negates on bit 15 of
# the angle, cosine on bit 15 of angle + 0x4000.
    addiu   $t0, $a0, 0x2000
    andi    $t1, $t0, 0x3fff
    addiu   $t1, $t1, -0x2000
    mtc1    $t1, $f0
    lui     $t3, 0x227c              # K2
    ori     $t3, $t3, 0x6b4e
    cvt.s.w $f0, $f0                 # x
    mtc1    $t3, $f4
    lui     $t4, 0xb19d              # K1
    ori     $t4, $t4, 0xd974
    mtc1    $t4, $f6
    lui     $t6, 0x3f80              # 1.0
    mul.s   $f2, $f0, $f0            # x2
    mtc1    $t6, $f8
    andi    $t2, $t0, 0x4000
    mul.s   $f4, $f4, $f2
    addiu   $t9, $a0, 0x4000
    add.s   $f4, $f4, $f6
    andi    $t5, $a0, 0x8000         # sine negates
    mul.s   $f4, $f4, $f2
    andi    $t9, $t9, 0x8000         # cosine negates
    add.s   $f10, $f4, $f8           # c
    nop
    mul.s   $f2, $f10, $f10
    sub.s   $f2, $f8, $f2
    sqrt.s  $f12, $f2                # s
    mov.s   $f0, $f12
    beqz    $t2, 1f
    mov.s   $f2, $f10
    mov.s   $f0, $f10
    mov.s   $f2, $f12
1:  beqz    $t5, 2f
    nop
    neg.s   $f0, $f0
2:  beqz    $t9, 3f
    nop
    neg.s   $f2, $f2
3:  jr      $ra
    nop

#elif TRIG_FUNC == 5 || TRIG_FUNC == 6 || TRIG_FUNC == 8
# S5C6: S and C both; even octants sin = S, cos = C; odd sin = C, cos = -S;
# both negate on bit 15 of t.
    addiu   $t0, $a0, 0x2000
    andi    $t1, $t0, 0x3fff
    addiu   $t1, $t1, -0x2000
    mtc1    $t1, $f0
#if TRIG_FUNC == 6
    lui     $t7, %hi(gTrigK)
#endif
#if TRIG_FUNC == 8
    lui     $t3, 0x1a94              # S5
#else
    lui     $t3, 0x1a97              # S5
#endif
    cvt.s.w $f0, $f0                 # x
#if TRIG_FUNC == 6
    addiu   $t7, $t7, %lo(gTrigK)
#endif
    mtc1    $t3, $f4
#if TRIG_FUNC == 8
    lui     $t3, 0x932d              # C6
#else
    lui     $t3, 0x925d              # C6
#endif
    mul.s   $f2, $f0, $f0            # x2
    mtc1    $t3, $f12
#if TRIG_FUNC == 8
    lui     $t3, 0xaa25              # S3
    mtc1    $t3, $f6
    lui     $t4, 0x2286              # C4
    mtc1    $t4, $f14
    lui     $t3, 0x38c9              # S1
    ori     $t3, $t3, 0x0f98
    mtc1    $t3, $f8
    lui     $t4, 0xb19e              # C2
    mtc1    $t4, $f16
#elif TRIG_FUNC == 5
    lui     $t3, 0xaa24              # S3
    ori     $t3, $t3, 0xfee4
    mtc1    $t3, $f6
    lui     $t4, 0x2280              # C4
    ori     $t4, $t4, 0xc3c2
    mtc1    $t4, $f14
    lui     $t3, 0x38c9              # S1
    ori     $t3, $t3, 0x0dd0
    mtc1    $t3, $f8
    lui     $t4, 0xb19d              # C2
    ori     $t4, $t4, 0xe6b5
    mtc1    $t4, $f16
#else
    lwc1    $f6, 4($t7)              # S3
    lwc1    $f14, 12($t7)            # C4
    lwc1    $f8, 0($t7)              # S1
    lwc1    $f16, 8($t7)             # C2
#endif
    mul.s   $f4, $f4, $f2
    lui     $t6, 0x3f80              # 1.0
    mul.s   $f12, $f12, $f2
    mtc1    $t6, $f10
    add.s   $f4, $f4, $f6
    add.s   $f12, $f12, $f14
    mul.s   $f4, $f4, $f2
    andi    $t2, $t0, 0x4000
    mul.s   $f12, $f12, $f2
    andi    $t5, $t0, 0x8000
    add.s   $f4, $f4, $f8
    add.s   $f12, $f12, $f16
    mul.s   $f4, $f4, $f0            # S
    nop
    mul.s   $f12, $f12, $f2
    nop
    add.s   $f12, $f12, $f10         # C
    beqz    $t2, 1f
    nop
    mov.s   $f6, $f4
    mov.s   $f4, $f12
    neg.s   $f12, $f6
1:  beqz    $t5, 2f
    mov.s   $f0, $f4
    neg.s   $f0, $f4
    neg.s   $f12, $f12
2:  jr      $ra
    mov.s   $f2, $f12

#elif TRIG_FUNC == 7
# LUTX16: both lines of the node. Even octants: sin = the sine line, negated
# on bit 15 ^ (x < 0); cos = the cosine line, negated on bit 15. Odd: sin =
# the cosine line, negated on bit 15; cos = the sine line, negated on
# !bit 15 ^ (x < 0).
    addiu   $t0, $a0, 0x2000
    andi    $t1, $t0, 0x3fff
    addiu   $t1, $t1, -0x2000        # x
    sra     $t7, $t1, 31
    xor     $t1, $t1, $t7
    subu    $t1, $t1, $t7            # |x|
    addiu   $t8, $t1, 256
    sra     $t8, $t8, 9              # i
    sll     $t9, $t8, 9
    subu    $t9, $t1, $t9            # d
    mtc1    $t9, $f0
    sll     $t8, $t8, 5
    lui     $t3, %hi(gTrigLutx16)
    addiu   $t3, $t3, %lo(gTrigLutx16)
    cvt.s.w $f0, $f0                 # d
    addu    $t3, $t3, $t8            # node
    lwc1    $f6, 4($t3)              # CM
    lwc1    $f14, 20($t3)            # SM
    mul.s   $f2, $f0, $f0            # d2
    lwc1    $f8, 8($t3)              # SKM2
    mul.s   $f6, $f0, $f6
    lwc1    $f16, 24($t3)            # CKM2
    mul.s   $f14, $f0, $f14
    lwc1    $f4, 0($t3)              # S
    mul.s   $f8, $f2, $f8
    lwc1    $f12, 16($t3)            # C
    mul.s   $f16, $f2, $f16
    andi    $t2, $t0, 0x4000
    sub.s   $f6, $f6, $f8
    srl     $t5, $t0, 15
    add.s   $f14, $f14, $f16
    andi    $t5, $t5, 1              # bit 15
    add.s   $f4, $f4, $f6            # sine line
    andi    $t7, $t7, 1              # x < 0
    sub.s   $f12, $f12, $f14         # cosine line
    xor     $t6, $t5, $t7
    xori    $t9, $t6, 1
    mov.s   $f0, $f4
    mov.s   $f2, $f12
    move    $t8, $t6
    beqz    $t2, 1f
    move    $t4, $t5
    mov.s   $f0, $f12
    mov.s   $f2, $f4
    move    $t8, $t5
    move    $t4, $t9
1:  beqz    $t8, 2f
    nop
    neg.s   $f0, $f0
2:  beqz    $t4, 3f
    nop
    neg.s   $f2, $f2
3:  jr      $ra
    nop
#endif

    .size   trig_sincos, . - trig_sincos
#endif

#endif
