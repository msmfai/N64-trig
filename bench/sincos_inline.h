#ifndef SINCOS_INLINE_H
#define SINCOS_INLINE_H

/*
 * sincos_inline(angle, &s, &c): the S5C6 sincos kernel as GNU C inline
 * assembly for the VR4300 (N64). It gives the same values, bit for bit, as
 * kernel/sincos_code.s (default) or kernel/sincos_quantized.s (define
 * SINCOS_INLINE_QUANTIZED to 1 before this header).
 *
 * An experiment, not a recommended kernel: it was not faster than the call
 * (README: Experiments that were rejected).
 *
 * There is no call: no jal/jr, and no saved registers around a call. The
 * compiler selects the registers (3 integer, 6 float). Each use adds the
 * full kernel to the code (approximately 45 instructions), so use it only at
 * hot call sites. Same operation order and multiply spacing as the .s files:
 * no multiplication immediately after a multiplication, and no mul.s in a
 * branch delay slot (VR4300 multiply erratum).
 */

#ifndef SINCOS_INLINE_QUANTIZED
#define SINCOS_INLINE_QUANTIZED 0
#endif

#if SINCOS_INLINE_QUANTIZED
/* b, c, d, e, f: 8 significant bits, one lui. a: full precision. */
#define SCI_S5 "lui %[k], 0x1a94\n\t"
#define SCI_C6 "lui %[k], 0x932d\n\t"
#define SCI_S3 "lui %[k], 0xaa25\n\t"
#define SCI_C4 "lui %[k], 0x2286\n\t"
#define SCI_S1 "lui %[k], 0x38c9\n\tori %[k], %[k], 0x0f98\n\t"
#define SCI_C2 "lui %[k], 0xb19e\n\t"
#else
/* Pure code: c and f have 8 significant bits; a, b, d, e lui + ori. */
#define SCI_S5 "lui %[k], 0x1a97\n\t"
#define SCI_C6 "lui %[k], 0x925d\n\t"
#define SCI_S3 "lui %[k], 0xaa24\n\tori %[k], %[k], 0xfee4\n\t"
#define SCI_C4 "lui %[k], 0x2280\n\tori %[k], %[k], 0xc3c2\n\t"
#define SCI_S1 "lui %[k], 0x38c9\n\tori %[k], %[k], 0x0dd0\n\t"
#define SCI_C2 "lui %[k], 0xb19d\n\tori %[k], %[k], 0xe6b5\n\t"
#endif

static inline __attribute__((always_inline)) void sincos_inline(int angle, float *s, float *c) {
    int t, x, k;
    float fx, fx2, fs, fc, fa, fb;
    __asm__(
        ".set push\n\t.set noreorder\n\t.set noat\n\t"
        "addiu   %[t], %[a], 0x2000\n\t"
        "andi    %[x], %[t], 0x3fff\n\t"
        "addiu   %[x], %[x], -0x2000\n\t"     /* x: offset from nearest quarter turn */
        "mtc1    %[x], %[fx]\n\t"
        SCI_S5
        "cvt.s.w %[fx], %[fx]\n\t"
        "mtc1    %[k], %[fs]\n\t"
        SCI_C6
        "mul.s   %[fx2], %[fx], %[fx]\n\t"    /* x2 */
        "mtc1    %[k], %[fc]\n\t"
        SCI_S3
        "mtc1    %[k], %[fa]\n\t"
        SCI_C4
        "mtc1    %[k], %[fb]\n\t"
        "mul.s   %[fs], %[fs], %[fx2]\n\t"
        SCI_S1
        "mul.s   %[fc], %[fc], %[fx2]\n\t"
        "add.s   %[fs], %[fs], %[fa]\n\t"
        "add.s   %[fc], %[fc], %[fb]\n\t"
        "mtc1    %[k], %[fa]\n\t"              /* S1 */
        SCI_C2
        "mtc1    %[k], %[fb]\n\t"              /* C2 */
        "mul.s   %[fs], %[fs], %[fx2]\n\t"
        "andi    %[x], %[t], 0x4000\n\t"       /* set: odd octant */
        "mul.s   %[fc], %[fc], %[fx2]\n\t"
        "lui     %[k], 0x3f80\n\t"             /* 1.0 */
        "add.s   %[fs], %[fs], %[fa]\n\t"
        "add.s   %[fc], %[fc], %[fb]\n\t"
        "mtc1    %[k], %[fa]\n\t"
        "mul.s   %[fs], %[fs], %[fx]\n\t"      /* S = sine polynomial */
        "andi    %[k], %[t], 0x8000\n\t"       /* set: negate both */
        "mul.s   %[fc], %[fc], %[fx2]\n\t"
        "nop\n\t"
        "add.s   %[fc], %[fc], %[fa]\n\t"      /* C = cosine polynomial */
        "beqz    %[x], 1f\n\t"
        "nop\n\t"
        "mov.s   %[fb], %[fs]\n\t"             /* odd octant: sin = C, cos = -S */
        "mov.s   %[fs], %[fc]\n\t"
        "neg.s   %[fc], %[fb]\n\t"
        "1:\n\t"
        "beqz    %[k], 2f\n\t"
        "nop\n\t"
        "neg.s   %[fs], %[fs]\n\t"
        "neg.s   %[fc], %[fc]\n\t"
        "2:\n\t"
        ".set pop"
        : [t] "=&r"(t), [x] "=&r"(x), [k] "=&r"(k),
          [fx] "=&f"(fx), [fx2] "=&f"(fx2), [fs] "=&f"(fs), [fc] "=&f"(fc), [fa] "=&f"(fa), [fb] "=&f"(fb)
        : [a] "r"(angle));
    *s = fs;
    *c = fc;
}

#undef SCI_S5
#undef SCI_C6
#undef SCI_S3
#undef SCI_C4
#undef SCI_S1
#undef SCI_C2

#endif
