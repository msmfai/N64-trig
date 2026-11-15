# float trig_sin(int angle)  -- S5C6 sine/cosine kernel for the VR4300 (N64)
#
# angle: SM64/MM binary angle in $a0 (0x10000 = one turn; only bits 0-15 used)
# result: sine in $f0.  For cosine call trig_sin(angle + 0x4000): the add is
#         exact, so cosine is bit-identical to a dedicated cosine routine.
#
# Fold: t = angle + 0x2000; x = (t & 0x3FFF) - 0x2000 is the offset from the
# nearest quarter turn (|x| <= 0x2000 = 45 degrees). Bit 14 of t selects the
# cosine polynomial, bit 15 of t negates the result. (Folding idea: Silas Lock.)
#
#   sin = x * (S1 + x2*(S3 + S5*x2))
#   cos = 1 + x2*(C2 + x2*(C4 + C6*x2))        x2 = x*x, x in binary-angle units
#
# Sine and cosine are fitted jointly: the average of sin^2 + cos^2 - 1 over all
# angles is pinned to zero (so bone chains don't grow or shrink), and the two
# polynomials agree exactly at 45 degrees (sine is exactly odd).
# S5 and C6 have only 8 significant bits (low 16 bits zero), so each is built
# with one lui; the other four are loaded from one 16-byte cache line (trig_k,
# in s5c6.c). Coefficients: BFS_* in fit/coeffs.h, made by fit/fit.py.
#
# GNU as syntax (o32). Assemble as a .s file; mips-linux-gnu-gcc -c works.
#
# Leaf function, no stack, caller-saved registers only. Hazards respected:
# one instruction between mtc1 and use, no back-to-back mul.s, no mul.s in a
# branch delay slot (VR4300 multiply erratum).

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
    lui     $t7, %hi(trig_k)
    cvt.s.w $f0, $f0                 # x as float
    addiu   $t7, $t7, %lo(trig_k)
    mul.s   $f2, $f0, $f0            # x2
    bnez    $t2, 1f
    andi    $t5, $t0, 0x8000         # negate? (delay slot)

# sine octants: x * (S1 + x2*(S3 + S5*x2))
    lui     $t3, 0x1a97              # S5 = 0x1a970000 (8 significant bits)
    mtc1    $t3, $f4
    lwc1    $f6, 4($t7)              # S3
    lwc1    $f8, 0($t7)              # S1
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
1:  lui     $t3, 0x925d              # C6 = 0x925d0000 (8 significant bits)
    mtc1    $t3, $f4
    lwc1    $f6, 12($t7)             # C4
    lwc1    $f8, 8($t7)              # C2
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
    lui     $t7, %hi(trig_k)
    lui     $t3, 0x1a97              # S5
    cvt.s.w $f0, $f0                 # x
    addiu   $t7, $t7, %lo(trig_k)
    mtc1    $t3, $f4
    lui     $t3, 0x925d              # C6
    mul.s   $f2, $f0, $f0            # x2
    mtc1    $t3, $f12
    lwc1    $f6, 4($t7)              # S3
    lwc1    $f14, 12($t7)            # C4
    lwc1    $f8, 0($t7)              # S1
    lwc1    $f16, 8($t7)             # C2
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
