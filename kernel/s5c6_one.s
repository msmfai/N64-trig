# float trig_sin(int angle)  -- S5C6 "one constant" sine/cosine for the VR4300 (N64)
#
# Same fold, polynomials and code shape as s5c6_code.s, with its own
# coefficients: only S1 is full precision (lui + ori); S3, S5, C2, C4 and C6
# have 8 significant bits (low 16 bits zero), so each is one lui. No data.
# Fewer instructions than s5c6_code.s, but less accurate (README: max error
# 2.3e-5, max |s^2+c^2-1| 4.1e-5, sine not exactly odd at 45 degrees).
# Coefficients: the best value-error fit with that constraint, fit/fit_one.py.
#
# angle: SM64/MM binary angle in $a0 (0x10000 = one turn; only bits 0-15 used)
# result: sine in $f0.  For cosine call trig_sin(angle + 0x4000).
#
#   sin = x * (S1 + x2*(S3 + S5*x2))
#   cos = 1 + x2*(C2 + x2*(C4 + C6*x2))        x2 = x*x, x in binary-angle units
#
# GNU as syntax (o32). Leaf function, no stack, caller-saved registers only.
# Hazards respected: one instruction between mtc1 and use, no back-to-back
# mul.s, no mul.s in a branch delay slot (VR4300 multiply erratum).

    .set noreorder
    .set noat
    .text
    .global trig_sin
    .type   trig_sin, @function
    .balign 32
trig_sin:
    addiu   $t0, $a0, 0x2000
    andi    $t1, $t0, 0x3fff
    addiu   $t1, $t1, -0x2000        # x
    mtc1    $t1, $f0
    andi    $t2, $t0, 0x4000         # cosine octants?
    cvt.s.w $f0, $f0                 # x as float
    mul.s   $f2, $f0, $f0            # x2
    bnez    $t2, 1f
    andi    $t5, $t0, 0x8000         # negate? (delay slot)

# sine octants: x * (S1 + x2*(S3 + S5*x2))
    lui     $t3, 0x1a94              # S5 = 0x1a940000 (8 significant bits)
    mtc1    $t3, $f4
    lui     $t3, 0xaa25              # S3 = 0xaa250000 (8 significant bits)
    mtc1    $t3, $f6
    lui     $t4, 0x38c9              # S1 = 0x38c90f98 (the one full-precision constant)
    ori     $t4, $t4, 0x0f98
    mtc1    $t4, $f8
    mul.s   $f4, $f4, $f2
    add.s   $f4, $f4, $f6
    mul.s   $f4, $f4, $f2
    add.s   $f4, $f4, $f8
    mul.s   $f0, $f4, $f0
    bnez    $t5, 3f
    nop
    jr      $ra
    nop

# cosine octants: 1 + x2*(C2 + x2*(C4 + C6*x2))
1:  lui     $t3, 0x932d              # C6 = 0x932d0000 (8 significant bits)
    mtc1    $t3, $f4
    lui     $t3, 0x2286              # C4 = 0x22860000 (8 significant bits)
    mtc1    $t3, $f6
    lui     $t4, 0xb19e              # C2 = 0xb19e0000 (8 significant bits)
    mtc1    $t4, $f8
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
    neg.s   $f0, $f0                 # (delay slot)

    .size   trig_sin, . - trig_sin

# _Complex float trig_sincos(int angle)  -- sine and cosine of one angle
#
# result: sine in $f0, cosine in $f2 (GNU C returns _Complex float there:
# __real__ is the sine, __imag__ the cosine). Each is bit-identical to
# trig_sin(angle) and trig_sin(angle + 0x4000). One fold, both polynomials
# interleaved. cos(a) = sin(a + 0x4000) has the same x with bit 14 flipped
# (and bit 15 flipped when bit 14 was set), so:
#   even octants: sin =  S, cos = C        odd octants: sin = C, cos = -S
#   both negated when bit 15 of t is set.

    .global trig_sincos
    .type   trig_sincos, @function
    .balign 32
trig_sincos:
# S5C6: S and C both; even octants sin = S, cos = C; odd sin = C, cos = -S;
# both negate on bit 15 of t.
    addiu   $t0, $a0, 0x2000
    andi    $t1, $t0, 0x3fff
    addiu   $t1, $t1, -0x2000
    mtc1    $t1, $f0
    lui     $t3, 0x1a94              # S5
    cvt.s.w $f0, $f0                 # x
    mtc1    $t3, $f4
    lui     $t3, 0x932d              # C6
    mul.s   $f2, $f0, $f0            # x2
    mtc1    $t3, $f12
    lui     $t3, 0xaa25              # S3
    mtc1    $t3, $f6
    lui     $t4, 0x2286              # C4
    mtc1    $t4, $f14
    lui     $t3, 0x38c9              # S1 (full precision)
    ori     $t3, $t3, 0x0f98
    mtc1    $t3, $f8
    lui     $t4, 0xb19e              # C2
    mtc1    $t4, $f16
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

    .size   trig_sincos, . - trig_sincos
