# trig_sincos(angle): sine and cosine of a 16-bit binary angle (0x10000 = one
# turn) for the N64 VR4300. Sine in $f0, cosine in $f2. Uses $t0-$t7 and
# $f0-$f16 only (all caller-saved). Max error 2.3e-5.
# S(x) = x(a + x^2(b + cx^2)), C(x) = 1 + x^2(d + x^2(e + fx^2)), x in +-1/8 turn.
# "Quantized": only a (S1) is full precision (lui + ori); b, c, d, e, f have
# 8 significant bits, one lui each. No data, 3 fewer instructions than
# sincos_code.s, 3 more than sincos.s, and less accurate than both (its own
# coefficients, fit/fit_quantized.py). The three versions: README.md.

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
    lui     $t3, 0x1a94              # S5 =  6.121136532892405e-23
    cvt.s.w $f0, $f0
    mtc1    $t3, $f4
    lui     $t3, 0x932d              # C6 = -2.1835669856517607e-27
    mul.s   $f2, $f0, $f0            # x2
    mtc1    $t3, $f12
    lui     $t3, 0xaa25              # S3 = -1.4654943925052066e-13
    mtc1    $t3, $f6
    lui     $t4, 0x2286              # C4 =  3.63207727782644e-18
    mtc1    $t4, $f14
    lui     $t3, 0x38c9              # S1 =  9.587331442162395e-05 (full precision)
    ori     $t3, $t3, 0x0f98
    mtc1    $t3, $f8
    lui     $t4, 0xb19e              # C2 = -4.598405212163925e-09
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
