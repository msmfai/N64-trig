/*
 * In-game trig benchmark for SM64: see trig_bench.h. This file lives in the
 * main segment (src/game); the title screen's own statics are reloaded with
 * the menu segment each time the title returns, so state must not live there.
 */
#include <ultra64.h>

#include "sm64.h"
#include "engine/math_util.h"
#include "game_init.h"
#include "level_update.h"
#include "print.h"
#ifdef TRIG_HSM64
#include "profiling.h"
#endif
#include "trig_bench.h"

#ifdef TRIG_HSM64
static void trig_bench_emux_done(void);
static void trig_bench_emux_progress(s32 demo);
static void tb_emux_log(const char *text);
#if TRIG_SITES
/* Per call site (return address): calls, and calls whose angle is the previous
 * call's +-0x4000 (the second half of a sin/cos pair). */
#define TB_SITES 1024
static u32 sSiteAddr[TB_SITES], sSiteCalls[TB_SITES], sSitePairs[TB_SITES];
static s32 sSiteLast = -1;
f32 trig_site(s32 a) {
    u32 ra = (u32) __builtin_return_address(0);
    u32 i = (ra >> 2) & (TB_SITES - 1);
    s32 d = (a - sSiteLast) & 0xFFFF;
    while (sSiteAddr[i] != 0 && sSiteAddr[i] != ra) {
        i = (i + 1) & (TB_SITES - 1);
    }
    sSiteAddr[i] = ra;
    sSiteCalls[i]++;
    if (sSiteLast >= 0 && (d == 0x4000 || d == 0xC000)) {
        sSitePairs[i]++;
        sSiteLast = -1;
    } else {
        sSiteLast = a;
    }
    return trig_sin(a);
}
static char *tb_hex(char *p, u32 v) {
    s32 i;
    for (i = 28; i >= 0; i -= 4) {
        *p++ = "0123456789abcdef"[(v >> i) & 15];
    }
    *p++ = ' ';
    return p;
}
static void tb_sites_report(void) {
    static char line[48];
    u32 i;
    char *p;
    for (i = 0; i < TB_SITES; i++) {
        if (sSiteAddr[i] != 0) {
            p = line;
            *p++ = 'S'; *p++ = 'I'; *p++ = 'T'; *p++ = 'E'; *p++ = ' ';
            p = tb_hex(p, sSiteAddr[i]);
            p = tb_hex(p, sSiteCalls[i]);
            p = tb_hex(p, sSitePairs[i]);
            p[-1] = '\n';
            *p = 0;
            tb_emux_log(line);
        }
    }
}
#endif
#endif

/* Frames ignored at the start of each demo: level load and fade-in. */
#define TB_SKIP 30

struct TrigBench gTrigBench = { TB_MAGIC, TRIG_FUNC, TRIG_USE, TRIG_COUNT, 0, -1, 0, 0 };
u32 gTrigBenchT3Ticks;
u32 gTrigBenchT4Ticks;

/* CPU clock cycles to microseconds (93.75 MHz), as OS_CYCLES_TO_USEC does for Count ticks. */
#define TB_USEC(cycles) ((s32) (((cycles) * 4) / 375))

static s32 sFramesInDemo;
static s32 sLastDemo;
#ifndef TRIG_HSM64
static u32 sPrevT4;
#endif
#if TRIG_COUNT
static u32 sPrevCalls;
#endif

/* The HUD font has digits and most capitals (no J, Q, V, X or Z). */
#if TRIG_FUNC == 0
#define TB_NAME "TABLE"
#elif TRIG_FUNC == 1 || TRIG_FUNC == 4
#define TB_FAMILY "SILAS"
#elif TRIG_FUNC == 7
#define TB_FAMILY "LUT16"
#elif TRIG_FUNC == 8
#define TB_FAMILY "ONE"
#else
#define TB_FAMILY "BFSK"
#endif
#ifndef TB_NAME
#if TRIG_USE == 0
#define TB_NAME "TABLE OF " TB_FAMILY
#else
#define TB_NAME TB_FAMILY
#endif
#endif

#if defined(__GNUC__) && defined(TRIG_PAD) && TRIG_PAD > 0
extern const char gTrigPad[];
#endif

/* The sample switches of this build (bench/sample.py reads them from the ELF
 * to check that the build used them). */
#ifndef TRIG_PAD
#define TRIG_PAD 0
#endif
#ifndef TRIG_DPAD
#define TRIG_DPAD 0
#endif
#ifndef TRIG_HEAPPAD
#define TRIG_HEAPPAD 0
#endif
#ifndef TRIG_SEED
#define TRIG_SEED 0
#endif
const u32 gTrigConfig[4] __attribute__((used)) = { TRIG_PAD, TRIG_DPAD, TRIG_HEAPPAD, TRIG_SEED };

void trig_bench_init(void) {
    /* Referencing gTrigConfig keeps the linker from discarding it. */
    (void) *(volatile const u32 *) gTrigConfig;
#if defined(__GNUC__) && defined(TRIG_PAD) && TRIG_PAD > 0
    /* Referencing the layout padding keeps the linker from discarding it. */
    gTrigBench.pad = (u32) (uintptr_t) gTrigPad;
#endif
#if defined(__GNUC__) && defined(TRIG_DPAD) && TRIG_DPAD > 0
    gTrigDataPad[0] = 1;
#endif
#if defined(TRIG_SEED) && TRIG_SEED > 0
    /* Game condition (bench/sample.py): start the game's random generator
     * TRIG_SEED steps later, so objects make different random choices. */
    {
        s32 n;
        for (n = 0; n < TRIG_SEED; n++) {
            random_u16();
        }
    }
#endif
#if TRIG_FUNC != 0 && TRIG_USE == 0
    /* gSineTable (0x400 entries) runs on into gCosineTable (0x1000): entry k
     * of the pair is the sine of table step k, for k up to 0x13FF. */
    s32 k;

    for (k = 0; k < 0x1400; k++) {
        gSineTable[k] = trig_sin(k << 4);
    }
#endif
}

static void trig_bench_draw(void) {
    u64 total = 0;
    u32 frames = 0;
    u32 calls = 0;
    s32 y = 208;
    s32 i;

    /* Game-logic CPU time per frame in microseconds, per demo and overall. */
    print_text(16, y, TB_NAME);
    for (i = 0; i < TB_DEMOS; i++) {
        struct TrigBenchDemo *d = &gTrigBench.d[i];

        if (d->frames == 0) {
            continue;
        }
        y -= 18;
        print_text_fmt_int(16, y, "%d", i + 1);
        print_text_fmt_int(48, y, "%d", TB_USEC((d->cycles - d->preempted) / d->frames));
        total += d->cycles - d->preempted;
        frames += d->frames;
        calls += d->calls;
    }
    if (frames != 0) {
        y -= 18;
        print_text(16, y, "ALL");
        print_text_fmt_int(64, y, "%d", TB_USEC(total / frames));
#if TRIG_COUNT
        y -= 18;
        print_text(16, y, "CALLS");
        print_text_fmt_int(96, y, "%d", (s32) (calls / frames));
#endif
    }
}

s32 trig_bench_title(void) {
    if (gTrigBench.demo >= 0) {
        /* Back on the title screen: the demo that was running is over. */
        gTrigBench.demo = -1;
        gTrigBench.demosRun++;
        if (sLastDemo) {
            gTrigBench.done = TRUE;
        }
    }
    if (gTrigBench.done) {
        trig_bench_draw();
#ifdef TRIG_HSM64
        trig_bench_emux_done();
#endif
    }
    return gTrigBench.done;
}

void trig_bench_demo_start(s32 level, s32 isLast) {
    s32 index = gTrigBench.demosRun;

    if (gTrigBench.done || index >= TB_DEMOS) {
        return;
    }
    gTrigBench.demo = index;
    gTrigBench.d[index].level = level;
    sFramesInDemo = 0;
    sLastDemo = isLast;
#ifdef TRIG_HSM64
    trig_bench_emux_progress(index);
#endif
}

/* One measured frame: Count ticks of main-thread time, of which
 * preemptedTicks went to other threads, and audioTicks of audio-thread time. */
static void trig_bench_record(u32 ticks, u32 preemptedTicks, u32 audioTicks) {
    struct TrigBenchDemo *d;
    u32 cycles;
    u32 h;
    s32 i;
#if TRIG_COUNT
    u32 calls = gTrigCalls - sPrevCalls;

    sPrevCalls = gTrigCalls;
#endif
    if (gTrigBench.done || gTrigBench.demo < 0 || gCurrDemoInput == NULL) {
        return;
    }
    if (++sFramesInDemo <= TB_SKIP) {
        return;
    }
    d = &gTrigBench.d[gTrigBench.demo];
    cycles = ticks * 2; /* Count runs at half the CPU clock */
    d->frames++;
    d->cycles += cycles;
    d->preempted += preemptedTicks * 2;
    d->audio += audioTicks * 2;
    if (cycles > d->maxCycles) {
        d->maxCycles = cycles;
    }
#if TRIG_COUNT
    d->calls += calls;
#endif
    h = d->hash;
    for (i = 0; i < 3; i++) {
        h = ((h << 5) | (h >> 27)) ^ *(u32 *) &gMarioState->pos[i];
    }
    d->hash = h;
}

#ifdef TRIG_HSM64

/* ares emux (ares/n64/cpu/emux.cpp, v148): COP0 encodings that only ares
 * decodes, as .word. XDETECT puts a nonzero mask in $t0 when ares runs with
 * Homebrew Mode; elsewhere $t0 keeps its 0. XPROF starts ($t0 = slot, code 1)
 * or stops (code 2) a profile slot, which accumulates ares's counters while
 * started; XPROFREAD reads counter $t1 of slot $t0 into $t1. Slot -1 would
 * read the global counters directly, but v148 compares it unsigned against
 * the slot count and returns 0, so slot 0 is kept started and is stopped,
 * read and restarted once a frame. They have not been run on a console, so
 * a hardware build (TRIG_EMUX=0) never executes any of them: detection then
 * reports no ares and every other emux call is skipped. Results are on the
 * title screen either way. */
#ifndef TRIG_EMUX
#define TRIG_EMUX 1
#endif
static u32 tb_emux_detect(void) {
#if TRIG_EMUX
    register u32 r asm("$8") = 0;

    asm volatile(".word 0x42800060" : "+r"(r)); /* XDETECT $t0, code 1 */
    return r;
#else
    return 0;
#endif
}

static void tb_emux_prof(s32 stop) {
    register u32 slot asm("$8") = 0;

    if (stop) {
        asm volatile(".word 0x428000a8" : : "r"(slot) : "memory"); /* XPROF $t0, code 2 */
    } else {
        asm volatile(".word 0x42800068" : : "r"(slot) : "memory"); /* XPROF $t0, code 1 */
    }
}

static u32 tb_emux_counter(u32 code) {
    register u32 slot asm("$8") = 0;
    register u32 r asm("$9") = code;

    asm volatile(".word 0x42848029\n\tsll %0, %0, 0" : "+r"(r) : "r"(slot)); /* XPROFREAD $t0, $t1 */
    return r;
}

/* XLOG $t0, code 0: print the NUL-terminated string at $t0 on ares's terminal. */
static void tb_emux_log(const char *text) {
    register const char *p asm("$8") = text;

    asm volatile(".word 0x42800025" : : "r"(p) : "memory");
}

/* XIOCTL code 1: ask ares to quit. code 2: fast-forward on. */
static void tb_emux_exit(void) {
    asm volatile(".word 0x4200006c" : : : "memory");
}

static void tb_emux_fast(void) {
    asm volatile(".word 0x420000ac" : : : "memory");
}

#if TRIG_CYCLES
/* Cycles per call, warm cache, interrupts off. Each form runs over 65536
 * angles in order and in a pseudo-random order, twice (the second pass is
 * reported); loops with the same bookkeeping but no trig are timed to
 * subtract. One line: TRIGCYCLES and ten hex totals in CPU cycles. */
extern u32 __osDisableInt(void);
extern void __osRestoreInt(u32);
volatile f32 gTrigSink;
volatile u32 gTrigSinkI;
volatile f32 gTrigOne = 1.0f;

#define TB_N 0x10000
#define TB_LOOP(OUT, RND, ...)                                                 \
    do {                                                                       \
        u32 i_, r_ = 12345, x_ = 0, t0_;                                       \
        s32 a;                                                                 \
        f32 acc = 0.0f, acc2 = 0.0f, one = gTrigOne;                           \
        t0_ = osGetCount();                                                    \
        for (i_ = 0; i_ < TB_N; i_++) {                                        \
            r_ = r_ * 0x41C64E6Du + 12345u;                                    \
            a = (RND) ? (s32) (r_ >> 16) : (s32) i_;                           \
            x_ ^= (u32) a;                                                     \
            __VA_ARGS__                                                        \
        }                                                                      \
        OUT = (osGetCount() - t0_) * 2;                                        \
        gTrigSink = acc + acc2;                                                \
        gTrigSinkI = x_;                                                       \
        (void) one;                                                            \
    } while (0)

static void tb_cycles_report(void) {
    static char line[16 + 10 * 9 + 2];
    u32 t[10];
    u32 mask, pass, k;
    s32 rnd;
    char *p = line;
    const char *tag = "TRIGCYCLES";

    mask = __osDisableInt();
    for (pass = 0; pass < 2; pass++) {
        for (rnd = 0; rnd < 2; rnd++) {
            u32 *o = &t[5 * rnd];
            TB_LOOP(o[0], rnd, acc += one;);
            TB_LOOP(o[1], rnd, acc += sins(a););
            TB_LOOP(o[2], rnd, acc += one; acc2 += one;);
            TB_LOOP(o[3], rnd, acc += sins(a); acc2 += coss(a););
            TB_LOOP(o[4], rnd, { f32 s_, c_; sincoss(a, s_, c_); acc += s_; acc2 += c_; });
        }
    }
    __osRestoreInt(mask);
    while (*tag != '\0') {
        *p++ = *tag++;
    }
    for (k = 0; k < 10; k++) {
        s32 b;
        *p++ = ' ';
        for (b = 28; b >= 0; b -= 4) {
            *p++ = "0123456789abcdef"[(t[k] >> b) & 15];
        }
    }
    *p++ = '\n';
    *p = '\0';
    tb_emux_log(line);
}
#endif

/* The whole of gTrigBench as one line of hex on ares's terminal, then quit:
 * a runner needs nothing but ares's output (tools: bench/run.py). */
static void tb_emux_report(void) {
    static char line[16 + 2 * sizeof(gTrigBench) + 2];
    static const char hex[] = "0123456789abcdef";
    const u8 *b = (const u8 *) &gTrigBench;
    char *p = line;
    u32 i;
    const char *tag = "TRIGBENCH ";

    while (*tag != '\0') {
        *p++ = *tag++;
    }
    for (i = 0; i < sizeof(gTrigBench); i++) {
        *p++ = hex[b[i] >> 4];
        *p++ = hex[b[i] & 15];
    }
    *p++ = '\n';
    *p = '\0';
#if TRIG_SITES
    tb_sites_report();
#endif
#if TRIG_SINCOS && TRIG_USE && TRIG_FUNC != 0
    {
        static char sl[] = "TRIGSINCOS bad 00000000\n";
        u32 a, bad = 0;
        s32 k;
        for (a = 0; a < 0x10000; a++) {
            _Complex float sc = trig_sincos(a);
            f32 s1 = __real__ sc, c1 = __imag__ sc;
            f32 s0 = trig_sin(a), c0 = trig_sin(a + 0x4000);
            if (*(u32 *) &s1 != *(u32 *) &s0 || *(u32 *) &c1 != *(u32 *) &c0) {
                bad++;
            }
        }
        for (k = 0; k < 8; k++) {
            sl[15 + k] = "0123456789abcdef"[(bad >> (28 - 4 * k)) & 15];
        }
        tb_emux_log(sl);
    }
#endif
#if TRIG_CYCLES
    tb_cycles_report();
#endif
    tb_emux_log(line);
    tb_emux_exit();
}

#define TB_X_DMISS 0x21
#define TB_X_DWB 0x22
#define TB_X_IMISS 0x11
#define TB_BUS_N 6
static const u32 sBusCodes[TB_BUS_N] = { 0x300, 0x310, 0x320, 0x330, 0x340, 0x370 };
static u32 sPrevBus[TB_BUS_N];

static s32 sEmux = -1;
static u32 sPrevDMiss, sPrevDWb, sPrevIMiss;

/* Cache events since the previous frame, added to the demo being measured. */
static void trig_bench_cache(void) {
    u32 dm, dw, im;
    u32 bus[TB_BUS_N];
    s32 k;
    struct TrigBenchDemo *d;

    if (sEmux < 0) {
        sEmux = tb_emux_detect() != 0;
        if (sEmux) {
            tb_emux_prof(FALSE);
            tb_emux_fast();
        }
        return;
    }
    if (!sEmux) {
        return;
    }
    tb_emux_prof(TRUE);
    dm = tb_emux_counter(TB_X_DMISS);
    dw = tb_emux_counter(TB_X_DWB);
    im = tb_emux_counter(TB_X_IMISS);
    for (k = 0; k < TB_BUS_N; k++) {
        bus[k] = tb_emux_counter(sBusCodes[k]);
    }
    tb_emux_prof(FALSE);
    if (!gTrigBench.done && gTrigBench.demo >= 0 && gCurrDemoInput != NULL && sFramesInDemo > TB_SKIP) {
        d = &gTrigBench.d[gTrigBench.demo];
        d->emux = 1;
        d->dMisses += dm - sPrevDMiss;
        d->dWrites += dw - sPrevDWb;
        d->iMisses += im - sPrevIMiss;
        d->busTotal += bus[0] - sPrevBus[0];
        d->busICache += bus[1] - sPrevBus[1];
        d->busDCache += bus[2] - sPrevBus[2];
        d->busUncached += bus[3] - sPrevBus[3];
        d->busSpDma += bus[4] - sPrevBus[4];
        d->busDpDraw += bus[5] - sPrevBus[5];
    }
    for (k = 0; k < TB_BUS_N; k++) {
        sPrevBus[k] = bus[k];
    }
    sPrevDMiss = dm;
    sPrevDWb = dw;
    sPrevIMiss = im;
}

/* A demo starts: one progress line on ares's terminal. */
static void trig_bench_emux_progress(s32 demo) {
    static char line[] = "TRIGBENCH demo 0\n";

    if (sEmux > 0) {
        line[15] = '0' + demo;
        tb_emux_log(line);
    }
}

/* Benchmark finished: on ares, report and quit (once). */
static void trig_bench_emux_done(void) {
    static s32 sReported;

    if (sEmux > 0 && !sReported) {
        sReported = TRUE;
        tb_emux_report();
    }
}

extern int profile_buffer_index;

void trig_bench_frame_profiler(void) {
    if (profile_buffer_index < 0) {
        return; /* no frame has ended yet */
    }
    trig_bench_record(all_profiling_data[PROFILER_TIME_TOTAL].counts[profile_buffer_index], 0,
                      all_profiling_data[PROFILER_TIME_AUDIO].total / PROFILING_BUFFER_SIZE);
    /* After the record, so sFramesInDemo already counts this frame. */
    trig_bench_cache();
}

#else

void trig_bench_frame(u32 ticks, u32 preemptedTicks) {
    u32 audioTicks = gTrigBenchT4Ticks - sPrevT4;

    sPrevT4 = gTrigBenchT4Ticks;
    trig_bench_record(ticks, preemptedTicks, audioTicks);
}

#endif
