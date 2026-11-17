#ifndef TRIG_BENCH_H
#define TRIG_BENCH_H

/*
 * In-game trig benchmark for SM64 (bench/). Copied to src/game/ of the
 * HackerSM64 tree.
 *
 * Workload: the game's own attract-mode demos (recorded inputs), which play
 * with no controller. For every demo frame the game loop reports the CPU time
 * of level_script_execute (game logic and display-list building: everything
 * that calls sins/coss). Results are shown on the title screen when the last
 * demo ends, and stay in gTrigBench for an emulator to read.
 *
 * Two builds only compare if they play the same game. `hash` folds Mario's
 * position on every measured frame: equal hashes mean identical gameplay.
 *
 * Timing follows HackerSM64's profiler (src/game/profiling.c there): CP0 Count
 * around the work, reported in microseconds, with the time the audio thread
 * takes while preempting the game thread subtracted. Here the scheduler
 * thread (3) is subtracted too. CPU time of the game logic for a frame is
 * `cycles - preempted`.
 */
#include <PR/ultratypes.h>

#define TB_MAGIC 0x54524947 /* "TRIG" */
#define TB_DEMOS 8

struct TrigBenchDemo {
    u32 level;     /* level number from the demo file */
    u32 frames;    /* measured frames */
    u64 cycles;    /* elapsed CPU clock cycles across level_script_execute */
    u32 maxCycles; /* slowest measured frame */
    u32 calls;     /* sins + coss calls over those frames (TRIG_COUNT builds) */
    u32 hash;      /* Mario's position, folded over the measured frames */
    u32 pad;
    u64 preempted; /* of `cycles`: spent in the scheduler and audio threads */
    u64 audio;     /* audio thread cycles over the whole of those frames (60 Hz) */
    /* ares only (HackerSM64 builds): cache events of the whole machine over
     * those frames, read from ares's own counters through its emux
     * extension (XPROFREAD; needs Homebrew Mode). emux is 1 when ares
     * answered, 0 on other emulators and on a console. */
    u32 dMisses;   /* D-cache line fills (ares charges 40 cycles each) */
    u32 dWrites;   /* dirty D-cache lines written back (40 cycles each) */
    u32 iMisses;   /* I-cache line fills (48 cycles each) */
    u32 emux;
};

struct TrigBench {
    u32 magic;
    u32 func;     /* TRIG_FUNC: whose values the game uses (0 vanilla table) */
    u32 use;      /* TRIG_USE: 0 table lookups, 1 calls */
    u32 counting; /* TRIG_COUNT: calls are counted, so timings are not clean */
    u32 done;
    s32 demo;     /* demo being measured, -1 between demos */
    u32 demosRun;
    u32 pad;
    struct TrigBenchDemo d[TB_DEMOS];
};

extern struct TrigBench gTrigBench;

/* CP0 Count ticks used by the scheduler thread (3) and the audio thread (4),
 * which both preempt the game thread. Updated by those threads. */
extern u32 gTrigBenchT3Ticks;
extern u32 gTrigBenchT4Ticks;

/* Once, after the engine segment is loaded: refill the sine table from
 * trig_sin when the build asks for table lookups of a polynomial's values. */
void trig_bench_init(void);
#if defined(__GNUC__) && defined(TRIG_DPAD) && TRIG_DPAD > 0
extern char gTrigDataPad[];
#endif
/* Title screen, once per frame. Returns TRUE when the benchmark has finished
 * (the results are then drawn and no further demo should start). */
s32 trig_bench_title(void);
/* A demo starts on this frame. isLast: it is the last one of the list. */
void trig_bench_demo_start(s32 level, s32 isLast);
/* Vanilla SM64. Game loop, once per frame: CP0 Count ticks elapsed across
 * level_script_execute, and how many of them threads 3 and 4 used. */
void trig_bench_frame(u32 ticks, u32 preemptedTicks);
/* HackerSM64 (TRIG_HSM64). Top of the game loop, before profiler_frame_setup:
 * records what the game's own profiler measured for the frame that just
 * ended. `cycles` is then its PROFILER_TIME_TOTAL (main thread, audio
 * preemption already excluded, so `preempted` stays 0) and `audio` its
 * rolling PROFILER_TIME_AUDIO average. */
void trig_bench_frame_profiler(void);

#endif
