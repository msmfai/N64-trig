# N64-trig: S5C6 sine and cosine for the N64

> [!NOTE]
> - **AI use:** I am a mathematician. I designed the approximation: the polynomial forms, the fit, the 8-bit coefficients c and f, and the constants in one cache line. I directed the work. Claude (the AI from Anthropic) wrote the code, the assembly, the benchmark and the report. The project contains no art, models or music.
> - **Source of the figures:** This documentation is generated from the experiment logs. All figures come from the benchmark results in [`bench/results/`](bench/results/) and from the scripts in [`fit/`](fit/) and [`bench/`](bench/). Refer to [Reproduce](#reproduce).
> - **Style guide:** This documentation uses ASD-STE100 Simplified Technical English.

S5C6 is a sine and cosine kernel for the N64 CPU (VR4300). This repository compares it with the kernel from Silas Lock.

## Summary

<!-- gen:summary-table -->
| | Silas | S5C6 (one cache line) |
|---|---|---|
| Max error | 1.92e-4 | 1.45e-5 |
| CPU cycles for one sine and one cosine (exact) | 93.0 | 89.5 |
| CPU cycles for one sine (exact) | 65.5 | 54.5 |
| Memory traffic in the game, bytes per frame | 544,239 ± 3,223 | 546,155 ± 3,367 (+1,916 ± 1,543) |
| CPU time in the game, µs per frame | 12,299 ± 59 | 12,321 ± 62 (+22 ± 28) |
<!-- /gen:summary-table -->

Accuracy: exact values over all 65,536 angles (experiment 1). Cycles: exact values from a timing loop (experiment 2). In-game values: mean ± 95 % confidence interval over the samples (experiments 3 and 4). In brackets: difference from Silas.

## Criteria

This repository compares sine and cosine kernels by three criteria:

1. **Memory traffic.** The bytes that the CPU moves over the RDRAM bus. The CPU shares this bus with the RCP.
2. **Instructions and CPU cycles.**
3. **Accuracy.** The error of the sine and the cosine, and how well the sine and the cosine agree (s² + c² − 1).

The baseline is the kernel from Silas Lock: a 4th-order cosine polynomial, with the sine from a square root. The SM64 sine table is not part of the comparison.

Each experiment below measures one of the three criteria:

| Criterion | Experiment |
|---|---|
| 3. Accuracy | [1. Accuracy](#1-accuracy) |
| 2. Instructions and cycles | [2. Cost for each call](#2-cost-for-each-call) and [4. CPU time in the game](#4-cpu-time-in-the-game) |
| 1. Memory traffic | [3. Memory traffic in the game](#3-memory-traffic-in-the-game) |

## Terms

| Term | Meaning |
|---|---|
| Angle | An SM64 or MM binary angle. 0x10000 is one turn. The kernels use only the low 16 bits. |
| Fold | The method that changes the angle to x, the offset from the nearest quarter turn. x is 45° or less. A polynomial in x, with a sign, gives the sine or the cosine of all angles. Silas Lock designed this method. |
| S5C6 | This kernel. The sine polynomial goes to x⁵. The cosine polynomial goes to x⁶. |
| Silas | The kernel from Silas Lock: a 4th-order cosine polynomial, and the sine from a square root. |
| `trig_sin` | A kernel function that returns one value. For the cosine, call `trig_sin(angle + 0x4000)`. |
| `trig_sincos` | A kernel function that returns the sine and the cosine of one angle. In C, `sincoss(angle, s, c)` calls it. |
| s² + c² − 1 | A measure of how well a sine and a cosine agree. A rotation made from them changes lengths by approximately half of this value. |
| Memory traffic | The bytes that the CPU moves over the RDRAM bus: instruction-cache fills, data-cache fills and write-backs, and uncached accesses. The emulator counts them on the bus. |
| Sample | One random draw of the test conditions: the positions of code and data in memory, and the random seed of the game. Refer to [Method in the game](#method-in-the-game). |
| ± | The half-width of the 95 % confidence interval of the mean (Student's t). |

## How S5C6 works

S5C6 calculates two polynomials:

    S(x) = x(a + x²(b + cx²))
    C(x) = 1 + x²(d + x²(e + fx²))

Silas calculates one polynomial. It calculates the other value with a square root:

    C(x) = 1 + x²(a + bx²)
    S(x) = √(1 − C(x)²)

Three design decisions reduce the cost of S5C6:

- The nested form above (Horner form) needs only one multiplication and one addition for each coefficient. There is no square root.
- The coefficients c and f have only 8 significant bits. One `lui` instruction loads each of them.
- The four other coefficients are in one 16-byte data-cache line.

## Versions

There are three versions of S5C6. All versions use the same fold and the same polynomial forms. They load the six coefficients into registers in different ways:

- **One cache line:** four coefficients come from one 16-byte data-cache line.
- **Pure code:** all coefficients are in the instructions. There is no data.
- **Quantized:** all coefficients are in the instructions, and five of the six are quantized to 8 significant bits. Each 8-bit coefficient needs only one `lui` instruction.

| | One cache line | Pure code | Quantized |
|---|---|---|---|
| Files | [`kernel/sincos.s`](kernel/sincos.s), [`kernel/s5c6.s`](kernel/s5c6.s) | [`kernel/sincos_code.s`](kernel/sincos_code.s), [`kernel/s5c6_code.s`](kernel/s5c6_code.s) | [`kernel/sincos_quantized.s`](kernel/sincos_quantized.s), [`kernel/s5c6_quantized.s`](kernel/s5c6_quantized.s) |
| Load of c, f and 1.0 | One `lui` each | One `lui` each | One `lui` each |
| Load of a, b, d and e | Read from one 16-byte data-cache line | `lui` + `ori` each | a: `lui` + `ori`. b, d and e: one `lui` each. |
| Data | 16 B | None | None |
| Max error | 1.45e-5 | 1.45e-5 (the same values, bit for bit) | 2.3e-5 |
| Max \|s² + c² − 1\| | 1.7e-7 | 1.7e-7 | 4.1e-5 |
| CPU cycles for one sine and one cosine | 89.5 | 91.5 | 88.5 |

### Properties of the versions

- **One cache line** executes the fewest instructions when its constant line is in the data cache. When the line is not in the data cache, the call reads it from RDRAM.
- **Pure code** reads no data. It uses 24 more bytes of instruction cache than the one-cache-line version.
- **Quantized** is pure code with 3 fewer instructions. Its coefficients b, d and e are quantized to 8 bits, so this version has its own coefficients ([`fit/fit_quantized.py`](fit/fit_quantized.py)). These coefficients are not fitted jointly. Its maximum of s² + c² − 1 is 240 times that of the other versions.

## Use

### To get the sine and the cosine of one angle

1. Assemble one of the `kernel/sincos*.s` files.
2. Include [`kernel/sincos.h`](kernel/sincos.h).
3. Call `sincoss(angle, s, c)`. It sets `s` to the sine and `c` to the cosine.

### To replace the SM64 functions

1. Assemble one of the `kernel/s5c6*.s` files.
2. For `kernel/s5c6.s` (one cache line) only: also compile [`kernel/s5c6.c`](kernel/s5c6.c). This file contains the constant line (16 bytes, 16-byte aligned).
3. Include [`kernel/s5c6.h`](kernel/s5c6.h). It gives the SM64 functions `sins(a)` and `coss(a)`, and `sincoss(a, s, c)`.

### Calling convention

| Item | Value |
|---|---|
| Input | The angle in `$a0`. |
| `trig_sin` output | `$f0`. |
| `trig_sincos` output | The sine in `$f0` and the cosine in `$f2` (GNU C `_Complex float`). No value goes through memory. |
| Stack | Not used. All functions are leaf functions. |
| Registers changed | Only caller-saved registers: `$t0`–`$t7`, and the even registers `$f0`–`$f16`. |
| Syntax | GNU as, o32 ABI. |
| VR4300 multiply erratum | No kernel has a multiplication immediately after `mul.s`. No kernel has `mul.s` in a branch delay slot. |

## 1. Accuracy

`fit/accuracy.py` calculates the sine and the cosine of all 65,536 angles with each kernel. It uses float32 and the same operation order as the code of the kernel. The reference is float64. The values are exact, because the script calculates all angles.

| | Silas | S5C6 (one cache line, pure code) | S5C6 quantized |
|---|---|---|---|
| Max error | 1.92e-04 | 1.45e-05 | 2.28e-05 |
| Mean \|error\| | 1.41e-05 | 4.97e-06 | 9.48e-06 |
| RMS error | 1.73e-05 | 6.63e-06 | 1.18e-05 |
| Max \|s²+c²−1\| | 7.09e-08 | 1.72e-07 | 4.14e-05 |
| Mean \|s²+c²−1\| | 1.73e-08 | 3.66e-08 | 1.80e-05 |
| Mean s²+c²−1 (drift) | +2.6e-10 | +1.8e-09 | +2.9e-07 |
| Max direction error (1/65536 turn) | 2.00 | 0.19 | 0.23 |
| Exact at 0°, 90°, 180° and 270° | Yes | Yes | Yes |
| sin(−a) = −sin(a) and cos(−a) = cos(a), exactly | Yes | Yes | No |
| Sine does not decrease from 0° to 90° | Yes | Yes | Yes |
| \|sin\| and \|cos\| never above 1 | Yes | Yes | Yes |
| Different sine values in one turn | 32,757 | 32,763 | 32,765 |

- **Direction error:** The difference between the direction of the (cos, sin) pair and the true angle, in units of 1/65536 turn.
- **s² + c² − 1:** A rotation made from a sine s and a cosine c changes lengths by the factor √(s² + c²). One float32 rounding step near 1.0 is 1.2e-7. The display-list matrices of the N64 (16.16 fixed point) round rotation values to steps of 1.5e-5.
- **Drift:** The mean of s² + c² − 1 over all angles.
- **Silas at 0° and 180°:** Within 2 steps of 0° and 180°, 1 − c² rounds to 0, and the sine of Silas is exactly 0.
- **Quantized version at ±45°:** Its two polynomials do not meet exactly at 45°. Near ±45°, the last bits of sin(−a) and −sin(a) can be different.

## 2. Cost for each call

### Size

`bench/footprint.py` measures the assembled kernels. It also checks that each `kernel/` file is the same as the benchmarked code, instruction for instruction. "Bytes to load when not in the cache" is the instruction-cache lines of the function (32 bytes each) and its data.

| | Function | Code bytes | 32-byte I-cache lines | Data | Bytes to load when not in the cache | Instructions executed (min / mean / max) | `mul.s` | `sqrt.s` |
|---|---|---|---|---|---|---|---|---|
| Silas | `trig_sin` | 120 | 4 | None | 128 | 25 / 26.5 / 28 | 3–4 | 0–1 |
| | `trig_sincos` | 156 | 5 | None | 160 | 35 / 37.0 / 39 | 4 | 1 |
| S5C6 one cache line | `trig_sin` | 168 | 6 | 16 B | 208 | 24 / 25.5 / 27 | 4 | 0 |
| | `trig_sincos` | 176 | 6 | 16 B | 208 | 39 / 41.5 / 44 | 7 | 0 |
| S5C6 pure code | `trig_sin` | 192 | 6 | None | 192 | 26 / 27.5 / 29 | 4 | 0 |
| | `trig_sincos` | 200 | 7 | None | 224 | 45 / 47.5 / 50 | 7 | 0 |
| S5C6 quantized | `trig_sin` | 180 | 6 | None | 192 | 25 / 26.0 / 27 | 4 | 0 |
| | `trig_sincos` | 188 | 6 | None | 192 | 42 / 44.5 / 47 | 7 | 0 |

### Cycles for each call

A timer in the ROM measures 65,536 calls in [ares](https://ares-emu.net) v148:

- Interrupts are off.
- A first pass fills the caches. Thus, the caches are warm.
- The cost of the timing loop is subtracted.
- "In order" means the angles 0, 1, 2, …. "Random" means a pseudo-random angle for each call.
- The unit is CPU cycles (93.75 MHz).
- The values are exact. ares is deterministic, and each loop measures all 65,536 calls.

| | sin, in order | sin, random | sin + cos as two calls, random | sincos, random |
|---|---|---|---|---|
| Silas | 65.5 | 65.5 | 132.0 | 93.0 |
| S5C6 one cache line | 54.5 | 54.5 | 110.0 | 89.5 |
| S5C6 pure code | 54.5 | 54.5 | 110.0 | 91.5 |
| S5C6 quantized | 53.0 | 53.0 | 107.0 | 88.5 |

- The loop runs with warm caches. Experiments 3 and 4 include the cost of cache misses.

## Method in the game

Experiments 3 and 4 use the same runs.

<!-- gen:method -->
| Item | Value |
|---|---|
| Game | [HackerSM64](https://github.com/HackerN64/HackerSM64), commit 3be00d2f, clang 21, `-Os` |
| Emulator | [Ares 64](https://github.com/HailToDodongo/ares-64) (commit b4ead632f), headless, CPU interpreter: it fetches every instruction through the modelled caches ([`bench/ares64.js`](bench/ares64.js)) |
| Input | The seven attract-mode demos of SM64: 4,304 measured frames, with approximately 456 sine and cosine calls per frame |
| Builds | Two for each kernel. **`sincoss()`:** [`bench/hsm64-sincos.patch`](bench/hsm64-sincos.patch) changes 13 functions to get the sine and the cosine of one angle from one `trig_sincos` call. These 13 functions make 98 % of the sine and cosine pairs. **Separate calls:** the game calls `sins()` and `coss()`, and each is one `trig_sin` call. |
| Test conditions | 57 samples. Each sample is one random draw of the four conditions below ([`bench/sample.py`](bench/sample.py)). All builds of a sample use the same draw. |
| Result | The mean of the 57 samples ± the 95 % confidence interval (Student's t). In brackets: the difference from Silas in the same sample, with its own confidence interval. |

**Test conditions:** The position of code and data in memory decides which of them collide in the caches. These collisions change each result by chance, by up to approximately ±3 %. Each sample draws the positions and the game state at random, from the full period of each cache:

| Condition | Draw | Effect |
|---|---|---|
| Code shift | 0 to 16 KB of padding before the kernel, in 32-byte steps | Instruction-cache collisions (16 KB cache, 32-byte lines) |
| Data shift | 0 to 8 KB of `.bss` padding, in 16-byte steps | Data-cache collisions of the static data (8 KB cache, 16-byte lines) |
| Heap shift | 0 to 8 KB added to the start of the main pool, in 16-byte steps | Data-cache collisions of all data that the game allocates at run time |
| Game seed | 0 to 65,113 steps of the random generator of the game, at boot | The random choices of the objects. The demos give the same input. |

All four conditions are uniform and independent. Each sample has its own random generator, so the samples are independent. New samples are added over time. The tables include all finished samples.
<!-- /gen:method -->

## 3. Memory traffic in the game

Bytes per frame that the CPU moves over the RDRAM bus, counted by the emulator on the bus.

<!-- gen:traffic -->
| | `sincoss()` at the 13 changed call sites | Separate `sins()` and `coss()` calls |
|---|---|---|
| Silas | 544,239 ± 3,223 | 552,482 ± 3,789 |
| S5C6 one cache line | 546,155 ± 3,367 (+1,916 ± 1,543) | 554,442 ± 3,936 (+1,961 ± 1,768) |
| S5C6 pure code | 546,343 ± 3,522 (+2,104 ± 1,876) | 553,698 ± 4,183 (+1,216 ± 1,811) |
| S5C6 quantized | 545,613 ± 3,504 (+1,374 ± 1,520) | 553,586 ± 4,152 (+1,104 ± 1,805) |
<!-- /gen:traffic -->

## 4. CPU time in the game

Game-thread CPU time from the HackerSM64 profiler, in µs per frame. Audio is not included.

<!-- gen:cputime -->
| | `sincoss()` at the 13 changed call sites | Separate `sins()` and `coss()` calls |
|---|---|---|
| Silas | 12,299 ± 59 | 12,553 ± 72 |
| S5C6 one cache line | 12,321 ± 62 (+22 ± 28) | 12,537 ± 74 (−16 ± 35) |
| S5C6 pure code | 12,318 ± 65 (+19 ± 34) | 12,515 ± 78 (−38 ± 34) |
| S5C6 quantized | 12,304 ± 65 (+5 ± 27) | 12,506 ± 78 (−46 ± 34) |
<!-- /gen:cputime -->

## Checks

| Check | Result |
|---|---|
| Is `trig_sincos` equal to two `trig_sin` calls? | Yes, bit for bit, for all 65,536 angles and all kernels. Each ROM does this check. |
| Are the `kernel/` files the same as the benchmarked code? | Yes, instruction for instruction (`bench/footprint.py --elf-dir`). |
| Gameplay | With each kernel, Mario stays within 0.06 units of the run with the SM64 table in all demos. |
| Denormals, NaN or infinity? | None in any intermediate value, for all angles and all kernels. |
| Negative zero? | sin(0x8000) and cos(0x4000) return −0.0. No code in SM64 divides by these values. |
| Built with IDO? | One-cache-line version only. Built in the vanilla SM64 decompilation (IDO 5.3, GNU as for the kernel): 559 call sites, all 65,536 values checked in the ROM, 4,800 frames run. |

## Reproduce

```sh
python3 fit/accuracy.py                              # experiment 1 (needs numpy)
python3 fit/fit.py                                   # S5C6 coefficients -> fit/coeffs.h
python3 fit/fit_quantized.py [--table]               # quantized coefficients
python3 bench/footprint.py --binutils DIR --clang DIR [--elf-dir work/HackerSM64-sincos]   # size
python3 bench/build.py --baserom sm64.us.z64 --clang BIN --binutils BIN [--pad N] [--variants ...] [--cycles] [--hardware]
python3 bench/run.py [--variants ...] [--suffix=-padN | --suffix=-cyc] --out FILE
python3 bench/sample.py --baserom sm64.us.z64 --clang BIN --binutils BIN [--samples 64] [--seed 1]   # experiments 3 and 4
python3 bench/summary.py                             # experiments 2 (cycles), 3 and 4, from bench/results/
python3 bench/readme.py                              # writes the in-game tables of this README
```

- `bench/hsm64-bench.patch` adds the benchmark to HackerSM64.
- `bench/sample.py` builds `asilas`, `abfskl`, `abfsk` and `aone` (separate calls), and the same names with `-sc` (`sincoss()`), for each sample.
- A `--cycles` build adds the timer for experiment 2. These builds are separate, because the code of the timer moves the code after it.
- ares is deterministic: a ROM gives the same counts in each run. Thus, results saved at different times can be combined. Control ROMs built again gave exactly the saved results.

## Credits and license

- Silas Lock designed the fold (refer to [Terms](#terms)) and the baseline kernel.
- License: MIT.
- The repository contains no ROMs.
