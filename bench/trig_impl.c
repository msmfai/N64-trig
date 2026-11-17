/*
 * Sine implementations for the SM64 in-game trig benchmark
 * (bench/). Copied to src/game/trig_impl.c of the HackerSM64 tree.
 *
 * TRIG_FUNC selects which sine this file provides as trig_sin:
 *   0  none (the game keeps its vanilla table; this file is then empty)
 *   1  Silas Lock's folded polynomial (github.com/AdamPrimer/folded-polynomial)
 *   2  BFSK: sine degree 5 + cosine degree 6, fitted jointly with the mean of
 *      s^2+c^2-1 pinned to zero, the 45-degree seam closed exactly, the two
 *      top coefficients in 8 mantissa bits (fit/fit.py)
 *   4-7  hand-written kernels in trig_kernels.s (GNU as): 4 Silas, 5 S5C6/BFSK
 *      with every constant in code, 6 S5C6/BFSK with four constants loaded
 *      from one line, 7 LUTX16, 8 S5C6 "one constant" (only S1 at full
 *      precision, every constant in code). This file then only provides their data.
 *
 * Whether sins()/coss() call it (TRIG_USE 1) or stay table lookups on a table
 * refilled from it (TRIG_USE 0) is decided in src/engine/math_util.h.
 * coss(x) is trig_sin(x + 0x4000), so one function serves both macros.
 *
 * It is compiled by the game's own compiler and flags. Pure ASCII, C89, so
 * it also builds with IDO in the vanilla decompilation.
 */
#if defined(__GNUC__)
#define TRIG_SQRTF(x) __builtin_sqrtf(x)
#define TRIG_ALIGN16 __attribute__((aligned(16)))
#else
float sqrtf(float value);
#pragma intrinsic(sqrtf)
#define TRIG_SQRTF(x) sqrtf(x)
#define TRIG_ALIGN16
#endif

/* Layout control for GNU-style builds (HackerSM64): TRIG_PAD bytes placed in
 * the code section ahead of trig_sin, moving it and the code linked after it.
 * (The vanilla SM64 patch pads in the linker script instead.) */
#if defined(__GNUC__) && defined(TRIG_PAD) && TRIG_PAD > 0
const char gTrigPad[TRIG_PAD] __attribute__((section(".text.trig_pad"), used)) = { 0 };
#endif

#if TRIG_FUNC != 0

#if TRIG_COUNT
unsigned int gTrigCalls;
#endif

#if TRIG_FUNC == 1

#define FOLDED_C1 -0.0000000011485057369884462f
#define FOLDED_C2 0.00000000000000000021380733869182293f

float trig_sin(int angle) {
    int a = (short)angle;
    int shifter = (a ^ (a << 1)) & 0xC000;
    float x = (float)(((a + shifter) << 17) >> 16);
    float x2 = x * x;
    float c = 1.0f + x2 * (FOLDED_C1 + FOLDED_C2 * x2);
    float s = (shifter & 0x4000) ? c : TRIG_SQRTF(1.0f - c * c);

    return (a < 0) ? -s : s;
}

#elif TRIG_FUNC == 2

/* BFS_* from fit/coeffs.h (fit/fit.py), copied in as trig_coeffs.h. */
#define BFS_S1 9.586999658495188e-05f
#define BFS_S3 -1.4654559033280834e-13f
#define BFS_S5 6.245213624775359e-23f
#define BFS_C2 -4.595529734530146e-09f
#define BFS_C4 3.4901736165623554e-18f
#define BFS_C6 -6.973530402153744e-28f

/* The four full-precision constants: one 16-byte data-cache line. With IDO this
 * is the first object in the file's .rodata, which the linker script aligns to
 * 16 bytes; GNU-style compilers are told directly. */
typedef struct {
    float s1, s3, c2, c4;
} TrigK;

const TrigK gTrigK TRIG_ALIGN16 = { BFS_S1, BFS_S3, BFS_C2, BFS_C4 };

#define KB ((const TrigK*)&gTrigK)

float trig_sin(int angle) {
    int a = (short)angle;
    int fold = (a ^ (a << 1)) & 0xC000;
    int xi = ((a + fold) << 17) >> 17;
    int xm = xi >> 31;
    float x = (float)((xi ^ xm) - xm);
    float x2 = x * x;
    float s;

    if (fold & 0x4000) {
        s = 1.0f + x2 * (KB->c2 + x2 * (KB->c4 + BFS_C6 * x2));
    } else {
        s = x * (KB->s1 + x2 * (KB->s3 + BFS_S5 * x2));
    }
    return (a < 0) ? -s : s;
}

#elif TRIG_FUNC >= 4 && TRIG_FUNC <= 8

/* trig_sin is in trig_kernels.s; its data lives here. */
#if TRIG_FUNC == 6
typedef struct {
    float s1, s3, c2, c4;
} TrigK;

const TrigK gTrigK TRIG_ALIGN16 = { 9.586999658495188e-05f, -1.4654559033280834e-13f,
                                    -4.595529734530146e-09f, 3.4901736165623554e-18f };
#elif TRIG_FUNC == 7
#include "trig_coeffs.h"
/* LUTX16_TABLE rows are written "{ { 8 floats } }" for a union like this one;
 * as a plain float[17][8] the inner braces make each row one scalar, so
 * every row but its first value would be zero. */
typedef union {
    float f[8];
    double align;
} TrigLutxNode;
#if defined(__GNUC__)
const TrigLutxNode gTrigLutx16[17] __attribute__((aligned(32))) = { LUTX16_TABLE };
#endif
#endif

#else
#error "unknown TRIG_FUNC"
#endif

#else

#if TRIG_COUNT
unsigned int gTrigCalls;
#endif

/* IDO rejects an empty translation unit. */
static int sTrigImplUnused;

#endif
