# N64-trig

A fast, accurate sine/cosine kernel for the N64's VR4300 (S5C6), and an
in-game benchmark that measures it, Silas Lock's folded polynomial and a
16-segment table against Super Mario 64's sine table, in HackerSM64 on ares.

Results summary: https://msmfai.github.io/N64-trig/

**Status: emulator results only.** Nothing here has been measured on a
console yet. Read "What ares can't tell you" before quoting a number.

## The kernel

`kernel/s5c6.s` (+ `s5c6.c`, `s5c6.h`): `float trig_sin(int angle)` for
16-bit binary angles (0x10000 = one turn). Cosine is `trig_sin(angle + 0x4000)`;
the add is exact, so cosine costs one call and is bit-identical to a
dedicated cosine routine.

- **Fold.** The angle is folded to an offset of at most 45° from the nearest
  quarter turn; one bit picks the sine or cosine polynomial, one bit the sign.
  Folding idea: Silas Lock.
- **Polynomials.** Odd degree 5 for sine, even degree 6 for cosine, fitted
  jointly so that the mean of sin² + cos² − 1 over all 65536 angles is zero
  (rotations don't grow or shrink vectors on average), and so the two meet
  exactly at 45°.
- **Constants.** The two highest-order coefficients have only 8 significant
  bits, so each is built in the code with one `lui`; the other four sit in one
  16-byte, 16-byte-aligned cache line. A call touches at most one data line.
- **Hazards.** Leaf function, no stack. One instruction between `mtc1` and use,
  no back-to-back `mul.s` and no `mul.s` in a delay slot (VR4300 erratum).

| | S5C6 | Silas (folded) | SM64 table |
|---|---|---|---|
| Max error, all 65536 angles | 1.45e-5 | 1.9e-4 | 1.4e-3 (4096 steps) |
| Max \|sin² + cos² − 1\| | 1.7e-7 | 7.1e-8 | |
| Instructions, sine / cosine octants | 24 / 27 | 28 / 25 (sine has a `sqrt.s`) | 1 load |
| Data | 16 B (one line) | 0 (all in code) | 20 KB (1280 lines) |
| Small angles | exact sign and slope | sine is 0 at angles 1 and 2 | |

`fit/fit.py` (numpy, about 35 s) regenerates every coefficient in
`fit/coeffs.h`; S5C6 is `BFS_*` there (`BFSK` in the benchmark), LUTX16 is
`LUTX16_TABLE`. The script also fits the families that lost (plain LUT,
rational, CORDIC, power-of-two coefficients).

## The benchmark

`bench/` patches [HackerSM64](https://github.com/HackerN64/HackerSM64) (pinned
commit) so the title screen plays SM64's seven attract-mode demos and records
HackerSM64's own profiler figure for every frame: game-thread CPU time, audio
preemption excluded (`PROFILER_TIME_TOTAL`).

Each method is built twice:

- **table build** (`t…`): `sins`/`coss` stay SM64's table lookups, but the
  table is refilled at boot from the kernel, with angles cut to the table's
  4096 steps;
- **call build**: every `sins`/`coss` calls the kernel on those same angles.

The two compute bit-identical values, so they play the same game; a hash of
Mario's position over every measured frame proves it. The difference between
them is the cost of calling the kernel instead of reading the table, on real
gameplay with real cache pressure (about 440 calls per frame).

On ares the ROM also reads ares's own cache counters (emux extension, Homebrew
Mode): D-cache misses, write-backs and I-cache misses per frame. From those,
`run.py` works out the miss cost at which table and kernel would tie.

```sh
python3 bench/build.py --baserom sm64.us.z64 --variants kernels   # HackerSM64's toolchain
python3 bench/build.py --baserom sm64.us.z64 --variants kernels \
    --clang /path/to/clang/bin --binutils /path/to/mips-binutils/bin   # as published
python3 bench/run.py --variants kernels
python3 bench/build.py --variants kernels --pad 1024    # layout control, then
python3 bench/run.py --variants kernels --suffix=-pad1024
```

`run.py` needs ares v148 or later and starts one headless ares per ROM with
its own settings file (your ares settings are untouched). The ROM
fast-forwards, prints its results to ares's terminal and quits; a run of eight
ROMs takes about five minutes. Times are emulated time, so a busy host does not
change them. You supply the US base ROM; never distribute it or the built ROMs.

Variants: `asilas`, `abfsk` (S5C6 with every constant built in code),
`abfskl` (S5C6 as in `kernel/`, four constants loaded), `alutx` (LUTX16:
16-segment table with a quadratic correction, 544 bytes), each with its table
build; `c` builds the C versions instead.

## Results (ares v148, HackerSM64 at the pinned commit, clang 21)

All seven demos, 4304 measured frames, identical gameplay in every pair, at
three code layouts (`--pad 0`, `1024`, `4096`). Raw data: `bench/results/`.

**Call build minus table build, µs of game-thread time per frame** (the table
build takes about 12,000-12,600 µs):

| Kernel | pad 0 | pad 1024 | pad 4096 | mean |
|---|---|---|---|---|
| Silas | +61 | −186 | +234 | +36 |
| S5C6, constants in code | +110 | −396 | +199 | −29 |
| S5C6, `kernel/` (4 loaded) | +107 | −378 | +221 | −17 |
| LUTX16 | +124 | −417 | +211 | −27 |

**Extra instruction work of the calls, cycles per frame** (measured time,
game + audio threads, minus every cache miss at ares's price):

| Kernel | pad 0 | pad 1024 | pad 4096 |
|---|---|---|---|
| Silas | 31,600 | 32,700 | 30,600 |
| S5C6, constants in code | 28,300 | 28,000 | 27,200 |
| S5C6, `kernel/` | 27,800 | 28,500 | 28,400 |
| LUTX16 | 29,300 | 27,700 | 31,400 |

What this says:

- **In ares, kernel and table are a tie.** The difference swings from −3% to
  +2% with code layout, and averages near zero for every kernel. A single
  build pair can show either one winning.
- **Layout is bigger than the method.** The swing comes from the I-cache:
  the call builds take 40-1190 fewer I-cache misses per frame than their
  table builds (an inline table lookup is more code at each of the game's call
  sites than a `jal`), and how much fewer depends on where everything lands.
- **The stable ranking is instruction cost.** With misses taken out, S5C6
  costs about 28,000 cycles per frame (about 63 per call), Silas about 31,600:
  S5C6 is roughly 10% cheaper, at every layout. Silas pays for its `sqrt.s`.
- **The table's own data misses are modest:** 15-260 extra D-cache misses per
  frame against the call builds, depending on layout. Whether that matters on
  a console depends on what a miss costs there under load (below).

## What ares can't tell you

- ares charges a flat 40 cycles per D-cache line fill (and per write-back) and
  48 per I-cache fill. On a console a fill competes with the RSP and RDP for
  RDRAM, so during heavy rendering it can cost more. Dearer misses favour
  whichever build misses less, and here that is the call build in every
  pair and layout (counting both caches at ares's prices), so a console can only move the result toward the kernels; by how
  much is a console measurement. `run.py` prints, per pair, the miss cost at
  which the two would tie, but it is as layout-dependent as the misses.
- ares does not model the CPU pipeline or the early completion of multiplies
  by simple values, so instruction costs are approximate too.
- Code layout moves every result by about as much as the effect being
  measured, which is why the results above are averaged over three layouts.
- One ares quirk the bench works around: v148 returns 0 for XPROFREAD of the
  global profile slot (-1), so the ROM keeps slot 0 running and stops, reads
  and restarts it once a frame.

## Credits and notes

- The fold is Silas Lock's (folded polynomial). The Silas kernel here is a
  hand-written transcription of it for comparison.
- HackerSM64 does not accept AI-generated code. Nothing here is offered to it;
  the patch only makes a local benchmark build. This repository was written
  with AI assistance (Claude), and every result in it was produced by the
  scripts in it.
- MIT licence (`LICENSE`), for the code in this repository only. Super Mario 64
  is Nintendo's.
