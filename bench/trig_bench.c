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

void trig_bench_init(void) {
#if defined(__GNUC__) && defined(TRIG_PAD) && TRIG_PAD > 0
    /* Referencing the layout padding keeps the linker from discarding it. */
    gTrigBench.pad = (u32) (uintptr_t) gTrigPad;
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
 * read and restarted once a frame. On a console these do nothing (undefined
 * COP0 functions), but the benchmark is only meant for ares. */
static u32 tb_emux_detect(void) {
    register u32 r asm("$8") = 0;

    asm volatile(".word 0x42800060" : "+r"(r)); /* XDETECT $t0, code 1 */
    return r;
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
    tb_emux_log(line);
    tb_emux_exit();
}

#define TB_X_DMISS 0x21
#define TB_X_DWB 0x22
#define TB_X_IMISS 0x11

static s32 sEmux = -1;
static u32 sPrevDMiss, sPrevDWb, sPrevIMiss;

/* Cache events since the previous frame, added to the demo being measured. */
static void trig_bench_cache(void) {
    u32 dm, dw, im;
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
    tb_emux_prof(FALSE);
    if (!gTrigBench.done && gTrigBench.demo >= 0 && gCurrDemoInput != NULL && sFramesInDemo > TB_SKIP) {
        d = &gTrigBench.d[gTrigBench.demo];
        d->emux = 1;
        d->dMisses += dm - sPrevDMiss;
        d->dWrites += dw - sPrevDWb;
        d->iMisses += im - sPrevIMiss;
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
