**AI use:** I'm a mathematician: I designed the approximation (the polynomial forms, the fit, truncating c and f to 8 bits, the constants in one cache line) and directed the work. Claude (Anthropic's AI) wrote the code, assembly, benchmark and report. No art, models or music.

A folded polynomial joint sine / cosine kernel for the N64 (VR4300), more than 10x more accurate than Silas Lock's.

It uses a polynomial approximation of

    S(x) = x(a + x²(b + cx²))
    C(x) = 1 + x²(d + x²(e + fx²))

instead of Silas's

    C(x) = 1 + x²(a + bx²)
    S(x) = √(1 − C(x)²)

and makes it inexpensive with the use of brackets you can see; by truncating c and f to 8 bit so they fit on one line of assembly; and putting the remaining constants into one cache line.

## At a glance

Three versions of the kernel, against Silas's folded polynomial and SM64's own sine table. All figures are explained, with their method, in the sections below.

| | SM64 vanilla table | Silas | **S5C6 one cache line** | **S5C6 pure code** | **S5C6 one constant** |
|---|---|---|---|---|---|
| Files | (in the game) | [`bench/trig_kernels.s`](bench/trig_kernels.s) | [`kernel/sincos.s`](kernel/sincos.s), [`s5c6.s`](kernel/s5c6.s) + [`s5c6.c`](kernel/s5c6.c) | [`kernel/sincos_code.s`](kernel/sincos_code.s), [`s5c6_code.s`](kernel/s5c6_code.s) | [`kernel/sincos_one.s`](kernel/sincos_one.s), [`s5c6_one.s`](kernel/s5c6_one.s) |
| Max error | 1.4e-3 | 1.9e-4 | **1.45e-5** | **1.45e-5** | 2.3e-5 |
| Max \|s² + c² − 1\| | 7.6e-8 | 7.1e-8 | 1.7e-7 | 1.7e-7 | 4.1e-5 |
| Data | 20 KB | none | 16 B (one D-cache line) | none | none |
| Code: sincos | ~4 instructions inline per value | 156 B | 176 B | 200 B | 188 B |
| Cycles per sincos, warm (ares) | 51 (random angles) | 93 | **89.5** | 91.5 | **88.5** |
| µs/frame, sincos call sites, against the table (mean of 3 layouts) | 0 | −9 | −71 | −75 | −83 |
| µs/frame saved against Silas | | 0 | 62 | 66 | 73 |

**Which one?** The cache-line and pure-code versions return the same values bit for bit; the one-constant version has its own coefficients and is less accurate (see [The three versions](#the-three-versions)). On ares all three cost the same within code-layout noise. None has been run on a console.

## The three versions

Same fold and polynomials; they differ only in how the six coefficients get into registers.

| | One cache line | Pure code | One constant |
|---|---|---|---|
| c, f and 1.0 | `lui` each | `lui` each | `lui` each |
| a, b, d, e | read from `trig_k`, one 16-byte data-cache line | `lui` + `ori` each | b, d, e: `lui` each; a: `lui` + `ori` |
| Coefficients | fit/fit.py (joint fit) | the same | fit/fit_one.py (own fit) |
| Accuracy | best | same as cache line | max error 1.6x, \|s²+c²−1\| 240x worse |
| Instructions executed per sincos | 39–44 | 45–50 | 42–47 |

**Why there are three:**
- The cache-line version runs the fewest instructions, but only if its line is already in the data cache. If the game has evicted it, the call waits for RAM.
- The pure-code version can never miss on data. It costs 24 more bytes of instruction cache instead, and is one self-contained file with no `.rodata` to place or align.
- The one-constant version is pure code too, but only one coefficient needs `lui` + `ori`. It is 3 instructions shorter than the pure-code version and still reads no data. The price is accuracy: with 8-bit b, d and e the joint fit is lost. Its errors are still far below the vanilla table's, but its s² + c² − 1 is large enough that a rotation applied to its own result every frame (for example SM64's `apply_platform_displacement`, which undoes the last frame's rotation with a transpose) drifts measurably within minutes (about half a unit a minute for an object 1,000 units from the platform's centre); see the drift row below.
- On ares the three are tied: the gaps are smaller than the ±3% that code layout alone moves results. ares charges a flat cost per cache miss and doesn't model RAM contention, so it can't say which wins on a console. That needs a hardware measurement.

## Accuracy

Over all 65,536 binary angles, sine and cosine, evaluated in float32 exactly as each method's code does it, against float64 sin and cos. Reproduce: `python3 fit/accuracy.py`.

| | SM64 vanilla table | Silas | S5C6 one cache line / pure code | S5C6 one constant |
|---|---|---|---|---|
| max error | 1.44e-03 | 1.92e-04 | 1.45e-05 | 2.28e-05 |
| mean \|error\| | 4.58e-04 | 1.41e-05 | 4.97e-06 | 9.48e-06 |
| RMS error | 5.97e-04 | 1.73e-05 | 6.63e-06 | 1.18e-05 |
| max \|s²+c²−1\| | 7.55e-08 | 7.09e-08 | 1.72e-07 | 4.14e-05 |
| mean \|s²+c²−1\| | 2.96e-08 | 1.73e-08 | 3.66e-08 | 1.80e-05 |
| mean s²+c²−1 (drift) | −4.5e-09 | +2.6e-10 | +1.8e-09 | +2.9e-07 |
| max direction error (1/65536 turn) | 15.00 | 2.00 | 0.19 | 0.23 |
| exact at 0°, 90°, 180°, 270° | yes | yes | yes | yes |
| sin(−a) = −sin(a), cos(−a) = cos(a), exactly | no | yes | yes | no |
| sine never decreases from 0° to 90° | yes | yes | yes | yes |
| distinct sine values per turn | 2,049 | 32,757 | 32,763 | 32,765 |

- **Max / mean / RMS error:** of the returned sine and cosine values. The table's error is mostly its 4,096 steps per turn (an angle is rounded down to a multiple of 16).
- **s² + c² − 1:** how far a rotation matrix built from the pair scales lengths (by about half this). Silas computes the sine from the cosine, so its pair is as consistent as float32 allows; the joint fit keeps S5C6 within about 1.5 float32 rounding steps. One float32 step near 1.0 is 1.2e-7. The N64's display-list matrices (16.16 fixed point) round rotation entries to 1.5e-5, far coarser than any of these except the one-constant version's 4e-5.
- **Drift:** the average of s² + c² − 1. It matters only for a rotation applied again and again to its own result. At 30 frames a second, growing 1% takes about 4 days for S5C6 and 38 minutes for the one-constant version, if every frame used a different angle; SM64 and MM rebuild their matrices from the angle each frame, so ordinary objects never drift.
- **Direction error:** how far the angle the (cos, sin) pair points at is from the true one.
- **Silas** returns a sine of exactly 0 within 2 steps of 0° and 180° (1 − c² rounds to 0 there, so its square root is 0). Those are its largest errors: 1.9e-4 at 2 steps (2/65536 of a turn).
- **Odd/even exactly:** the one-constant polynomials don't meet exactly at 45°, so sin(−a) and −sin(a) can differ in the last bits near ±45°.

## Size and instructions

From the assembled kernels (`python3 bench/footprint.py --binutils DIR --clang DIR`, which also checks that each `kernel/` file is instruction for instruction the code in the benchmark ROMs). Executed counts: min / mean / max over all 65,536 angles, from running each function's control flow for every angle.

| | function | code bytes | 32-byte I-cache lines | data | instructions executed | mul.s executed | sqrt.s |
|---|---|---|---|---|---|---|---|
| SM64 vanilla table | `sins()` / `coss()` macros | inline | | 20 KB (5,120 floats); 1 D-cache line per lookup | ~4 | 0 | 0 |
| Silas | `trig_sin` | 120 | 4 | none | 25 / 26.5 / 28 | 3–4 | 0–1 |
| | `trig_sincos` | 156 | 5 | none | 35 / 37.0 / 39 | 4 | 1 |
| S5C6 one cache line | `trig_sin` | 168 | 6 | 16 B, 1 line | 24 / 25.5 / 27 | 4 | 0 |
| | `trig_sincos` | 176 | 6 | 16 B, 1 line | 39 / 41.5 / 44 | 7 | 0 |
| S5C6 pure code | `trig_sin` | 192 | 6 | none | 26 / 27.5 / 29 | 4 | 0 |
| | `trig_sincos` | 200 | 7 | none | 45 / 47.5 / 50 | 7 | 0 |
| S5C6 one constant | `trig_sin` | 180 | 6 | none | 25 / 26.0 / 27 | 4 | 0 |
| | `trig_sincos` | 188 | 6 | none | 42 / 44.5 / 47 | 7 | 0 |

- **Calling convention:** all kernels are leaf functions with no stack. Angle in `$a0` (only the low 16 bits are used). `trig_sin` returns the sine in `$f0`; `trig_sincos` returns sine in `$f0` and cosine in `$f2` (GNU C `_Complex float`), so nothing goes through memory.
- **Registers written:** caller-saved only: `$t0`–`$t7` (Silas `trig_sincos` also `$t9`), `$f0`–`$f16` (even). The cache-line versions use `$t7` for the line's address instead of `$t4`.
- **VR4300 multiply erratum:** no kernel has a multiply directly after a `mul.s` or a `mul.s` in a branch delay slot.
- **One function serves both sins and coss:** cos(a) is `trig_sin(a + 0x4000)`, bit-identical to a dedicated cosine.

## Speed

Measured in [ares](https://ares-emu.net) v148 on [HackerSM64](https://github.com/HackerN64/HackerSM64) (commit 3be00d2f, clang 21, `-Os`). Reproduce: `python3 bench/summary.py` prints every table here from `bench/results/`.

### Cycles per call

Timed inside the ROM over 65,536 angles with interrupts off, after a warm-up pass (warm caches), the loop's own cost subtracted. In order: angles 0, 1, 2, …; random: a pseudo-random angle each call. CPU cycles at 93.75 MHz.

| | sin, in order | sin, random | sin + cos as two calls, random | sincos, random |
|---|---|---|---|---|
| SM64 vanilla table (inline) | 5.5 | 24.5 | 50.9 | 50.9 (two lookups) |
| Silas | 65.5 | 65.5 | 132.0 | 93.0 |
| S5C6 one cache line | 54.5 | 54.5 | 110.0 | 89.5 |
| S5C6 pure code | 54.5 | 54.5 | 110.0 | 91.5 |
| S5C6 one constant | 53.0 | 53.0 | 107.0 | 88.5 |

- **The table is cheap only while its lines are cached.** In order, consecutive angles share a 16-byte line; at random angles most lookups miss the data cache (20 KB table, 8 KB cache), which ares charges 40 cycles. The kernels cost the same in any order.
- **sincos saves 18–39 cycles per pair** against two calls: one fold, interleaved polynomials, one call.
- **Not shown here:** the cache-line version's cost when its own line has been evicted (one data-cache miss, 40 cycles on ares), and instruction-cache misses on the kernels' 4–7 lines. The in-game figures below include both as they happen.
- ares's CPU timing is approximate (fixed costs per instruction, no pipeline model), so treat these as relative.

### In the game

The seven SM64 attract-mode demos (4,304 measured frames, about 440 sine and cosine calls per frame), timed by HackerSM64's own profiler: game-thread CPU microseconds per frame, audio excluded. Each kernel was built at three code layouts (0, 1024 or 4096 bytes of padding before the kernel), because where code sits moves every result by about ±3%. Read the means.

Baseline, the vanilla table:

| | layout 0 | layout 1024 | layout 4096 | mean |
|---|---|---|---|---|
| vanilla table, µs/frame | 12,433 | 12,471 | 11,967 | **12,290** |

**sin and cos of one angle from one `sincoss()` call**, at the 13 functions that make 98% of sin/cos pairs ([`bench/hsm64-sincos.patch`](bench/hsm64-sincos.patch)); µs/frame against the vanilla table built from the same source:

| | layout 0 | layout 1024 | layout 4096 | mean |
|---|---|---|---|---|
| Silas | −276 | −213 | +461 | **−9** |
| S5C6 one cache line | −322 | −288 | +396 | **−71** |
| S5C6 pure code | −297 | −285 | +356 | **−75** |
| S5C6 one constant | −331 | −290 | +374 | **−83** |

µs/frame saved against Silas, both as `sincoss()`:

| | layout 0 | layout 1024 | layout 4096 | mean |
|---|---|---|---|---|
| S5C6 one cache line | 46 | 75 | 66 | **62** |
| S5C6 pure code | 21 | 72 | 105 | **66** |
| S5C6 one constant | 55 | 77 | 88 | **73** |

**Separate `sins()` / `coss()` calls** (the game's call sites unchanged), µs/frame against the vanilla table:

| | layout 0 | layout 1024 | layout 4096 | mean |
|---|---|---|---|---|
| Silas | +81 | −257 | +400 | **+75** |
| S5C6 one cache line | +253 | −325 | +303 | **+77** |
| S5C6 pure code | +273 | −319 | +321 | **+92** |
| S5C6 one constant | +261 | −328 | +310 | **+81** |

The same calls against a table refilled at boot with the kernel's own values, which plays the identical game (checked every frame): Silas +36, cache line −17, pure code −29, one constant −69 µs/frame (means; per layout in `bench/summary.py`).

Cache misses per frame with `sincoss()`, against the vanilla table, mean of the 3 layouts (whole machine; ares charges 40 cycles per data-cache miss or write-back and 48 per instruction-cache miss):

| | data-cache misses | write-backs | instruction-cache misses |
|---|---|---|---|
| Silas | −188 | −14 | −358 |
| S5C6 one cache line | −150 | −15 | −484 |
| S5C6 pure code | −196 | −17 | −516 |
| S5C6 one constant | −201 | −6 | −485 |

- **Why calls can beat a table:** a call executes more instructions than a lookup, but saves the table's data-cache misses, and a call site is smaller than an inline lookup, which saves instruction-cache misses.
- **The differences between the three S5C6 versions (62 to 73 µs against Silas) are within the layout spread** (the same kernel varies by up to 84 µs across layouts).
- **Gameplay:** every value changes the game slightly, so the kernel builds and the vanilla table don't play exactly the same demo; Mario stays within 0.06 units of the vanilla run in every demo (checked for the cache-line version), and the table-refill comparison above is the exact-same-game control.

## Checks

| | |
|---|---|
| sincos equal to two calls? | Bit-identical for all 65,536 angles, every kernel, checked inside each ROM. |
| `kernel/` files the same as the benchmarked code? | Yes, instruction for instruction (`bench/footprint.py --elf-dir`). |
| Built with IDO? | The cache-line version in vanilla decomp SM64 (IDO 5.3, GNU as for the kernel): 559 call sites, all 65,536 sines and cosines checked in the ROM, 4,800 frames run. Not repeated for the other two. |
| Denormals, NaN, infinity? | None in any intermediate for any angle. |
| Negative zero? | sin(0x8000) and cos(0x4000) return −0.0 (table: +0.0). Nothing in SM64 divides by them. |
| atan2s(cos, sin) round trip? | Cache-line version: same as the table on its 4,096 angles (max 5); better on all 65,536 (max 5 against 20). |
| Real console? | **Not tested.** Help is appreciated: `bench/build.py --hardware` builds never run the ares-only instructions and show results on the title screen. |

## Using it

- **Sine and cosine together:** assemble `kernel/sincos.s` (plus nothing else), `sincos_code.s` or `sincos_one.s`, and include [`kernel/sincos.h`](kernel/sincos.h): `sincoss(angle, s, c)`.
- **Sine or cosine alone, and sincos:** `kernel/s5c6.s` (with [`s5c6.c`](kernel/s5c6.c) for the 16-byte constant line), `s5c6_code.s` or `s5c6_one.s`, with [`kernel/s5c6.h`](kernel/s5c6.h): `sins(a)`, `coss(a)` and `sincoss(a, s, c)` macros for SM64-style code.
- GNU as syntax (o32). The cache-line version needs `trig_k` 16-byte aligned (`s5c6.c` does it with `aligned(16)`; `sincos.s` with `.balign 16`).

## Reproduce

```sh
python3 fit/accuracy.py [--markdown]                 # accuracy table (numpy)
python3 fit/fit.py                                   # S5C6 coefficients -> fit/coeffs.h
python3 fit/fit_one.py [--table]                     # one-constant coefficients; --table: 0-6 full-precision coefficients
python3 bench/footprint.py --binutils DIR --clang DIR [--elf-dir work/HackerSM64-sincos]
python3 bench/build.py --baserom sm64.us.z64 --clang BIN --binutils BIN [--pad N] [--variants kernels sincos] [--cycles] [--hardware]
python3 bench/run.py [--variants kernels sincos] [--suffix=-padN | --suffix=-cyc]
python3 bench/summary.py                             # every speed table above, from bench/results/
```

- `bench/hsm64-bench.patch` adds the benchmark to HackerSM64; `bench/hsm64-sincos.patch` converts the 13 call sites to `sincoss()`.
- `--cycles` builds add the cycles-per-call timer (`TRIG_CYCLES`); they are separate builds because the timer's code moves the layout.
- ares is deterministic: a ROM gives the same cycles on every run, so results saved at different times combine. Rebuilt control ROMs matched the saved results exactly.

## Limits

- **ares, not a console.** Its CPU timing is approximate: flat cache-miss costs, no pipeline model, no memory contention with the RCP, and the RDP is not timed.
- **clang, not GCC.** HackerSM64's default compiler is GCC, which was not tested.
- **One game.** The in-game figures are SM64's attract demos on HackerSM64; another engine calls sine and cosine differently.

Full report (method, the call-site analysis, LUTX16, glossary): https://msmfai.github.io/N64-trig/

Fold: Silas Lock. MIT. No ROMs included; the SM64 table in `fit/accuracy.py` is regenerated from its formula, not copied.
