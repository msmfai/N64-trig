# trig_sin, trig_sincos -- S5C4 sine/cosine kernel for the VR4300 (N64), pure code (no data).
#
# angle: binary angle in $a0 (0x10000 = one turn; bits 0-15 used).
# trig_sin: sine in $f0 (cosine: trig_sin(angle + 0x4000)).
# trig_sincos: sine in $f0, cosine in $f2.
#
# Fold: t = angle + 0x2000; x = (t & 0x3FFF) - 0x2000 (|x| <= 45 degrees). Bit 14
# of t selects the cosine polynomial, bit 15 of t negates. (Fold: Silas Lock.)
#
#   sin = x * (a + x2*(b + c*x2))
#   cos = 1 + x2*(d + e*x2)                    x2 = x*x, x in binary-angle units
#
# Coefficients: fit/hwsearch.py, "S5C4 top 8-bit, hardware caps" (searched in
# float32 under the gameplay precision caps). c and e have 8 significant bits
# (one lui); a, b and d are built with lui + ori, 1.0 with lui. No data.
# trig_sin loads the three constants of its polynomial into the same registers
# for the sine and the cosine and shares one tail; the cosine's last factor is
# 1.0, so both results are bit-identical to the separate polynomials.
#
# Leaf functions, no stack, caller-saved registers only. No multiplication
# directly after a multiplication, none in a branch delay slot (VR4300
# multiply erratum); one instruction between mtc1 or and the use.
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
    lui     $t3, 0x1a85              # c
    lui     $t4, 0x227d              # e
    cvt.s.w $f0, $f0                 # x
    mtc1    $t3, $f4
    lui     $t6, 0xaa24              # b
    mul.s   $f2, $f0, $f0            # x2
    mtc1    $t4, $f12
    ori     $t6, $t6, 0x49da
    mtc1    $t6, $f6
    lui     $t7, 0xb19d              # d
    mul.s   $f4, $f4, $f2
    ori     $t7, $t7, 0xdd5a
    mul.s   $f12, $f12, $f2
    mtc1    $t7, $f14
    lui     $t8, 0x38c9              # a
    add.s   $f4, $f4, $f6
    ori     $t8, $t8, 0x07e2
    add.s   $f12, $f12, $f14
    mtc1    $t8, $f8
    mul.s   $f4, $f4, $f2
    lui     $t9, 0x3f80              # 1.0
    mul.s   $f12, $f12, $f2
    mtc1    $t9, $f10
    andi    $t2, $t0, 0x4000         # cosine octants?
    add.s   $f4, $f4, $f8
    andi    $t5, $t0, 0x8000         # negate?
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
    andi    $t5, $t0, 0x8000         # negate?
    cvt.s.w $f0, $f0                 # x: the final factor of the sine
    lui     $t3, 0x1a85              # sine constants: c
    mul.s   $f2, $f0, $f0            # x2
    lui     $t6, 0xaa24
    ori     $t6, $t6, 0x49da         # b
    lui     $t8, 0x38c9
    beqz    $t2, 1f                  # sine octants: to the shared tail
    ori     $t8, $t8, 0x07e2         # a (delay slot)
    lui     $t3, 0x227d              # cosine constants: e
    lui     $t6, 0xb19d
    ori     $t6, $t6, 0xdd5a         # d
    lui     $t8, 0x3f80              # 1.0
    mtc1    $t8, $f0                 # the final factor of the cosine: 1.0 (exact)
1:  mtc1    $t3, $f4                 # shared tail: f * (k0 + x2*(k1 + k2*x2))
    mtc1    $t6, $f6
    mtc1    $t8, $f8
    mul.s   $f4, $f4, $f2
    add.s   $f4, $f4, $f6
    mul.s   $f4, $f4, $f2
    add.s   $f4, $f4, $f8
    mul.s   $f0, $f4, $f0
    bnezl   $t5, 2f                  # negate: the delay slot runs only when taken
    neg.s   $f0, $f0
2:  jr      $ra
    nop
    .size   trig_sin, . - trig_sin
