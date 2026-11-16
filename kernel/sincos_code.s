# trig_sincos(angle): sine and cosine of a 16-bit binary angle (0x10000 = one
# turn) for the N64 VR4300. Sine in $f0, cosine in $f2. Uses $t0-$t7 and
# $f0-$f16 only (all caller-saved). Max error 1.45e-5.
# S(x) = x(a + x^2(b + cx^2)), C(x) = 1 + x^2(d + x^2(e + fx^2)), x in +-1/8 turn.
# All six constants are built in code: no data, 6 more instructions than sincos.s.

    .set noreorder
    .set noat
    .text
    .global trig_sincos
    .type   trig_sincos, @function
    .balign 32
trig_sincos:
    addiu   $t0, $a0, 0x2000
    andi    $t1, $t0, 0x3fff
    addiu   $t1, $t1, -0x2000        # x: offset from nearest quarter turn
    mtc1    $t1, $f0
    lui     $t3, 0x1a97              # S5 =  6.245213624775359e-23
    cvt.s.w $f0, $f0
    mtc1    $t3, $f4
    lui     $t3, 0x925d              # C6 = -6.973530402153744e-28
    mul.s   $f2, $f0, $f0            # x2
    mtc1    $t3, $f12
    lui     $t3, 0xaa24              # S3 = -1.4654559033280834e-13
    ori     $t3, $t3, 0xfee4
    mtc1    $t3, $f6
    lui     $t4, 0x2280              # C4 =  3.4901736165623554e-18
    ori     $t4, $t4, 0xc3c2
    mtc1    $t4, $f14
    lui     $t3, 0x38c9              # S1 =  9.586999658495188e-05
    ori     $t3, $t3, 0x0dd0
    mtc1    $t3, $f8
    lui     $t4, 0xb19d              # C2 = -4.595529734530146e-09
    ori     $t4, $t4, 0xe6b5
    mtc1    $t4, $f16
    mul.s   $f4, $f4, $f2
    lui     $t6, 0x3f80              # 1.0
    mul.s   $f12, $f12, $f2
    mtc1    $t6, $f10
    add.s   $f4, $f4, $f6
    add.s   $f12, $f12, $f14
    mul.s   $f4, $f4, $f2
    andi    $t2, $t0, 0x4000         # set: odd octant
    mul.s   $f12, $f12, $f2
    andi    $t5, $t0, 0x8000         # set: negate both
    add.s   $f4, $f4, $f8
    add.s   $f12, $f12, $f16
    mul.s   $f4, $f4, $f0            # S = sine polynomial
    nop
    mul.s   $f12, $f12, $f2
    nop
    add.s   $f12, $f12, $f10         # C = cosine polynomial
    beqz    $t2, 1f
    nop
    mov.s   $f6, $f4                 # odd octant: sin = C, cos = -S
    mov.s   $f4, $f12
    neg.s   $f12, $f6
1:  beqz    $t5, 2f
    mov.s   $f0, $f4
    neg.s   $f0, $f4
    neg.s   $f12, $f12
2:  jr      $ra
    mov.s   $f2, $f12                # sin in $f0, cos in $f2
    .size   trig_sincos, . - trig_sincos
