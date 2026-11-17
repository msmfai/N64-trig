# N64-trig: S5C6 sine and cosine for the N64

> [!NOTE]
> - **AI use:** I am a mathematician. I designed the approximation: the polynomial forms, the fit, the 8-bit coefficients c and f, and the constants in one cache line. I directed the work. Claude (the AI from Anthropic) wrote the code, the assembly, the benchmark and the report. The project contains no art, models or music.
> - **Source of the figures:** This documentation is generated from the experiment logs. All figures come from the benchmark results in [`bench/results/`](bench/results/) and from the scripts in [`fit/`](fit/) and [`bench/`](bench/). Refer to [Reproduce](#reproduce).
> - **Style guide:** This documentation uses ASD-STE100 Simplified Technical English.

S5C6 is a sine and cosine kernel for the N64 CPU (VR4300). This repository compares it with the kernel from Silas Lock.

## Summary

| | Silas | S5C6 (one cache line) |
|---|---|---|
| Max error | 1.92e-4 | **1.45e-5** (13 times smaller) |
| CPU cycles for one sine and one cosine (exact) | 93.0 | **89.5** |
| CPU cycles for one sine (exact) | 65.5 | **54.5** |
| Memory traffic in the game, compared with Silas | | +851 ± 3,289 bytes per frame (Silas: 543,894) |
| CPU time in the game, compared with Silas | | +8 ± 57 µs per frame (Silas: 12,339) |

- S5C6 is 13 times more accurate than Silas.
- For each call, S5C6 uses fewer CPU cycles than Silas.
- In the game, the memory traffic and the CPU time of S5C6 and Silas are the same, within the measurement error.
- Thus, S5C6 gives 13 times the accuracy for the same cost.
- All measurements come from the ares emulator. **The kernels are not tested on a real N64.**

## The question

This repository compares sine and cosine kernels by three criteria:

1. **Memory traffic.** The bytes that move over the RDRAM bus. The CPU shares this bus with the RCP, so less traffic can make the whole frame faster.
2. **Instructions and CPU cycles.**
3. **Accuracy that is sufficient for gameplay.** A character must walk in a straight line. A sine must not go above 1, because animation bones then grow.

The SM64 sine table is not compared here. The baseline is the kernel from Silas Lock: a 4th-order cosine polynomial, with the sine from a square root.

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
| Fold | A method from Silas Lock. The kernel changes the angle to x, the offset from the nearest quarter turn. x is 45° or less. A polynomial in x, with a sign, gives the sine or the cosine of all angles. |
| S5C6 | This kernel. The sine polynomial goes to x⁵. The cosine polynomial goes to x⁶. |
| Silas | The kernel from Silas Lock: a 4th-order cosine polynomial, and the sine from a square root. |
| `trig_sin` | A kernel function that returns one value. For the cosine, call `trig_sin(angle + 0x4000)`. |
| `trig_sincos` | A kernel function that returns the sine and the cosine of one angle. In C, `sincoss(angle, s, c)` calls it. |
| s² + c² − 1 | A measure of how well a sine and a cosine agree. A rotation made from them changes lengths by approximately half of this value. |
| Memory traffic | The bytes that cache misses move over the RDRAM bus. A data-cache miss reads 16 bytes. A write-back writes 16 bytes. An instruction-cache miss reads 32 bytes. |
| Code shift | Padding of 0 to 15 KB before the kernel, in 1 KB steps. Refer to [Method in the game](#method-in-the-game). |
| ± | The 95 % confidence interval. If the interval contains 0, the difference cannot be told apart from chance. |

## How S5C6 works

S5C6 calculates two polynomials:

    S(x) = x(a + x²(b + cx²))
    C(x) = 1 + x²(d + x²(e + fx²))

Silas calculates one polynomial. It calculates the other value with a square root:

    C(x) = 1 + x²(a + bx²)
    S(x) = √(1 − C(x)²)

Three design decisions make S5C6 fast:

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

### How to select a version

- **One cache line** executes the fewest instructions. This is true only while its constant line is in the data cache. If the game removes the line from the cache, the call must wait for RAM.
- **Pure code** cannot have a data-cache miss. It uses 24 more bytes of instruction cache.
- **Quantized** is pure code with 3 fewer instructions. Its coefficients b, d and e are quantized to 8 bits, so this version has its own coefficients ([`fit/fit_quantized.py`](fit/fit_quantized.py)). These coefficients are not fitted jointly, so the maximum of s² + c² − 1 is 240 times larger. This is important only where the code applies a rotation again and again to its own result.
- **In the game, the three versions have the same cost**, within the measurement error.

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

- **Criterion 3:** All kernels are exact at the four quarter turns, and no value goes above 1. Thus, no kernel makes bones grow.
- **Direction error:** The difference between the direction of the (cos, sin) pair and the true angle. For S5C6, it is less than one fifth of an angle step. For Silas, it is 2 angle steps. This error decides if a character walks in the direction that the player holds.
- **Silas error:** Within 2 steps of 0° and 180°, 1 − c² rounds to 0. Thus, the sine of Silas is exactly 0 at these angles. The largest error of Silas is at these angles.
- **s² + c² − 1:** Silas is slightly better, because it calculates one value from the other. Silas and S5C6 are both within approximately 1.5 float32 rounding steps (one step near 1.0 is 1.2e-7). The display-list matrices of the N64 (16.16 fixed point) round rotation values to 1.5e-5. This step is larger than the values of Silas and S5C6.
- **Drift:** Drift is the mean of s² + c² − 1. Drift is important only for a rotation that the code applies again and again to its own result. Example: at 30 frames per second, with a different angle in each frame, a length increases by 1 % in approximately 4 days with S5C6. With the quantized version, this takes approximately 38 minutes. SM64 and MM make their matrices again from the angle in each frame. Thus, usual objects do not drift.
- **Symmetry of the quantized version:** Its two polynomials do not meet exactly at 45°. Thus, near ±45°, the last bits of sin(−a) and −sin(a) can be different.

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

- S5C6 executes more instructions than Silas, but it has no `sqrt.s`. On the VR4300, `sqrt.s` takes much longer than one instruction. Thus, S5C6 uses fewer cycles (refer to the next table).
- S5C6 is larger than Silas. If its code is not in the cache, S5C6 loads 32 to 80 more bytes than Silas.

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

- **One sine:** S5C6 uses 11 to 12.5 fewer cycles than Silas.
- **One sine and one cosine with `trig_sincos`:** S5C6 uses 1.5 to 4.5 fewer cycles than Silas.
- **Not in this table:** the cost of a call when its code or its data is not in the cache. Experiments 3 and 4 include this cost.

## Method in the game

Experiments 3 and 4 use the same runs.

| Item | Value |
|---|---|
| Game | [HackerSM64](https://github.com/HackerN64/HackerSM64), commit 3be00d2f, clang 21, `-Os` |
| Emulator | ares v148 |
| Input | The seven attract-mode demos of SM64: 4,304 measured frames, with approximately 456 sine and cosine calls per frame |
| Builds | Two for each kernel. **`sincoss()`:** [`bench/hsm64-sincos.patch`](bench/hsm64-sincos.patch) changes 13 functions to get the sine and the cosine of one angle from one `trig_sincos` call. These 13 functions make 98 % of the sine and cosine pairs. **Separate calls:** the game calls `sins()` and `coss()`, and each is one `trig_sin` call. |
| Code shifts | Each build is made 16 times, with 0 to 15 KB of padding before the kernel, in 1 KB steps |
| Result | S5C6 minus Silas at the same code shift: the mean of the 16 differences, ± the 95 % confidence interval (Student's t) |

**Why code shifts:** The VR4300 instruction cache is 16 KB. Two functions that are 16 KB apart in memory use the same cache lines and remove each other from the cache. If code moves, different functions collide, and the result changes by chance, by up to approximately ±3 %. The 16 code shifts cover one full period of the cache in equal steps. Thus, the mean includes all positions of the code, and the confidence interval shows the remaining chance.

## 3. Memory traffic in the game

Bytes per frame that cache misses move over the RDRAM bus. ares counts the misses for the whole machine. S5C6 minus Silas:

| | `sincoss()` at the 13 changed call sites | Separate `sins()` and `coss()` calls |
|---|---|---|
| S5C6 one cache line | +851 ± 3,289 | +441 ± 3,324 |
| S5C6 pure code | +778 ± 3,722 | +1,820 ± 3,638 |
| S5C6 quantized | +1,429 ± 3,684 | +1,830 ± 3,642 |
| Silas, total (not a difference) | 543,894 ± 7,050 | 552,340 ± 7,601 |

- **No measurable difference.** All intervals contain 0. Each interval is less than 0.7 % of the total traffic.
- **Why:** Neither kernel reads a table. The only difference is the code size: if its code is not in the cache, S5C6 loads 32 to 80 more bytes than Silas. This is much smaller than the resolution of this measurement.
- **Criterion 1:** Silas and S5C6 have the same memory traffic. Thus, any gain from less memory traffic is the same for both kernels.

## 4. CPU time in the game

Game-thread CPU time from the HackerSM64 profiler, in µs per frame. Audio is not included. S5C6 minus Silas:

| | `sincoss()` at the 13 changed call sites | Separate `sins()` and `coss()` calls |
|---|---|---|
| S5C6 one cache line | +8 ± 57 | −52 ± 80 |
| S5C6 pure code | +13 ± 61 | −25 ± 93 |
| S5C6 quantized | +15 ± 70 | −36 ± 93 |
| Silas, total (not a difference) | 12,339 ± 117 | 12,596 ± 141 |

- **No measurable difference.** All intervals contain 0.
- **Agreement with experiment 2:** With separate calls, there are approximately 456 calls per frame. At 11 cycles less for each call, S5C6 should save approximately 54 µs per frame. The measured value is 52 µs, but the interval (±80 µs) is too wide to confirm it. With `sincoss()`, there are approximately 220 pairs per frame. At 3.5 cycles less for each pair, S5C6 should save approximately 10 µs per frame. This is much smaller than the interval.

## Experiments that were rejected

**Kernel inline at the `sincoss()` call sites** ([`bench/sincos_inline.h`](bench/sincos_inline.h), build variants `abfsk-sci` and `aone-sci`). The inline code removes the call, the return and the saved registers. But each inline copy adds approximately 45 instructions to the hot functions, which causes more instruction-cache misses. Inline build minus call build, 3 code shifts (0, 1 and 4 KB):

| | CPU time, µs per frame | Memory traffic, bytes per frame |
|---|---|---|
| S5C6 pure code | +12 ± 70 | +5,309 ± 5,130 |
| S5C6 quantized | +180 ± 623 | +13,183 ± 31,658 |

The inline kernel was not faster, so the experiment stopped after 3 code shifts.

## What these experiments cannot show

- **The real cost of a cache miss.** ares charges 40 cycles for each data-cache miss or write-back, and 48 cycles for each instruction-cache miss. This agrees approximately with the cost on an idle bus (approximately 41 cycles for a clean line fill). On a console, the CPU shares RDRAM with the RSP, the RDP, audio and cartridge DMA, and a miss can take longer. Silas and S5C6 have the same memory traffic, so this does not change the comparison between them. It changes how much both kernels gain compared with the SM64 table.
- **The RDP.** ares does not time the RDP. Thus, these experiments cannot show if less memory traffic makes the RDP faster.
- **The pipeline.** ares uses fixed costs for each instruction and does not simulate the pipeline. The real cost of `sqrt.s` and of a chain of `mul.s` can be different.
- **A real console.** **Not tested.** A `bench/build.py --hardware` build does not execute the ares-only instructions and shows its results on the title screen. Help is welcome.
- **Other engines.** The in-game results come from the SM64 demos in HackerSM64, built with clang. The default compiler of HackerSM64 is GCC, which was not tested. Other engines and games call sine and cosine in different ways.

## Checks

| Check | Result |
|---|---|
| Is `trig_sincos` equal to two `trig_sin` calls? | Yes, bit for bit, for all 65,536 angles and all kernels. Each ROM does this check. |
| Are the `kernel/` files the same as the benchmarked code? | Yes, instruction for instruction (`bench/footprint.py --elf-dir`). |
| Do Silas and S5C6 play the same game? | Not exactly. Their values are different, so the demos play slightly differently. With each kernel, Mario stays within 0.06 units of the run with the SM64 table. |
| Do the inline builds play the same game as the call builds? | Yes. The position hash of Mario is the same in each frame. |
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
python3 bench/summary.py                             # experiments 2 (cycles), 3 and 4, from bench/results/
```

- `bench/hsm64-bench.patch` adds the benchmark to HackerSM64.
- The builds for experiments 3 and 4 are `asilas`, `abfskl`, `abfsk` and `aone` (separate calls), and the same names with `-sc` (`sincoss()`). Build each one with `--pad 0` to `--pad 15360`, in steps of 1024.
- A `--cycles` build adds the timer for experiment 2. These builds are separate, because the code of the timer moves the code after it.
- ares is deterministic: a ROM gives the same counts in each run. Thus, results saved at different times can be combined. Control ROMs built again gave exactly the saved results.
- The benchmark can also build the SM64 table (`vanilla`, `vanilla-sc`). This documentation does not use these builds.

## Credits and license

- The fold is from Silas Lock.
- License: MIT.
- The repository contains no ROMs.
