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
# with one lui; the other four are built with lui+ori, so the kernel reads no
# data at all (s5c6.s loads those four from one cache line instead; same
# results bit for bit). Coefficients: BFS_* in fit/coeffs.h, made by fit/fit.py.
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
    cvt.s.w $f0, $f0                 # x as float
    mul.s   $f2, $f0, $f0            # x2
    bnez    $t2, 1f
    andi    $t5, $t0, 0x8000         # negate? (delay slot)

# sine octants: x * (S1 + x2*(S3 + S5*x2))
    lui     $t3, 0x1a97              # S5 = 0x1a970000 (8 significant bits)
    mtc1    $t3, $f4
    lui     $t3, 0xaa24              # S3 = 0xaa24fee4
    ori     $t3, $t3, 0xfee4
    mtc1    $t3, $f6
    lui     $t4, 0x38c9              # S1 = 0x38c90dd0
    ori     $t4, $t4, 0x0dd0
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
1:  lui     $t3, 0x925d              # C6 = 0x925d0000 (8 significant bits)
    mtc1    $t3, $f4
    lui     $t3, 0x2280              # C4 = 0x2280c3c2
    ori     $t3, $t3, 0xc3c2
    mtc1    $t3, $f6
    lui     $t4, 0xb19d              # C2 = 0xb19de6b5
    ori     $t4, $t4, 0xe6b5
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

