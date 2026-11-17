# N64-trig: S5C6 sine and cosine for the N64

**AI use:** I am a mathematician. I designed the approximation: the polynomial forms, the fit, the 8-bit coefficients c and f, and the constants in one cache line. I directed the work. Claude (the AI from Anthropic) wrote the code, the assembly, the benchmark and the report. The project contains no art, models or music.

S5C6 is a sine and cosine kernel for the N64 CPU (VR4300). It uses a folded polynomial. Its maximum error is 13 times smaller than the maximum error of the kernel from Silas Lock.

S5C6 calculates two polynomials:

    S(x) = x(a + x²(b + cx²))
    C(x) = 1 + x²(d + x²(e + fx²))

The kernel from Silas calculates one polynomial. It calculates the other value with a square root:

    C(x) = 1 + x²(a + bx²)
    S(x) = √(1 − C(x)²)

Three design decisions make S5C6 fast:

- The nested form above (Horner form) needs only one multiplication and one addition for each coefficient.
- The coefficients c and f have only 8 significant bits. One `lui` instruction loads each of them.
- The four other coefficients are in one 16-byte data-cache line.

## Terms

| Term | Meaning |
|---|---|
| Angle | An SM64 or MM binary angle. 0x10000 is one turn. The kernels use only the low 16 bits. |
| Fold | A method from Silas Lock. The kernel changes the angle to x, the offset from the nearest quarter turn. x is 45° or less. S(x) or C(x), with a sign, gives the sine or the cosine of all angles. |
| S5C6 | This kernel. The sine polynomial goes to x⁵. The cosine polynomial goes to x⁶. |
| Method | One of the three procedures that this document compares: the SM64 vanilla table, Silas, and S5C6. |
| Vanilla table | The method that SM64 uses. `sins()` and `coss()` read a 20 KB table with 4,096 steps for each turn. |
| `trig_sin` | A kernel function that returns one value. For the cosine, call `trig_sin(angle + 0x4000)`. |
| `trig_sincos` | A kernel function that returns the sine and the cosine of one angle. One call costs less than two `trig_sin` calls. |
| s² + c² − 1 | A measure of how well a sine and a cosine agree. A rotation made from them changes lengths by approximately half of this value. |

## Summary

This table compares S5C6 (the one-cache-line version) with Silas and with the SM64 vanilla table.

| | SM64 vanilla table | Silas | S5C6 |
|---|---|---|---|
| Max error | 1.4e-3 | 1.9e-4 | **1.45e-5** |
| Max \|s² + c² − 1\| | 7.6e-8 | **7.1e-8** | 1.7e-7 |
| CPU cycles for one sine and one cosine, warm cache, random angles | 51 | 93 | **89.5** |
| Game time per frame, compared with the table, SM64 demos | 0 | −9 µs | **−71 µs** |

- The maximum error of S5C6 is 13 times smaller than the maximum error of Silas. It is 100 times smaller than the maximum error of the table.
- The sine and the cosine of Silas agree slightly better, because Silas calculates one value from the other. Both methods are within approximately 1.5 float32 rounding steps.
- In the game, S5C6 saves approximately 62 µs per frame, compared with Silas.
- The position of the code in memory changes all in-game results by approximately ±3 %. Thus, the in-game results are the mean of three layouts. Refer to [In the game](#in-the-game).
- All measurements come from the ares emulator. **The kernels are not tested on a real N64.**

## Versions

There are three versions of S5C6. All versions use the same fold and the same polynomial forms. They load the six coefficients into registers in different ways.

| | One cache line | Pure code | One constant |
|---|---|---|---|
| Files | [`kernel/sincos.s`](kernel/sincos.s), [`kernel/s5c6.s`](kernel/s5c6.s) | [`kernel/sincos_code.s`](kernel/sincos_code.s), [`kernel/s5c6_code.s`](kernel/s5c6_code.s) | [`kernel/sincos_one.s`](kernel/sincos_one.s), [`kernel/s5c6_one.s`](kernel/s5c6_one.s) |
| Load of c, f and 1.0 | One `lui` each | One `lui` each | One `lui` each |
| Load of a, b, d and e | Read from one 16-byte data-cache line | `lui` + `ori` each | a: `lui` + `ori`. b, d and e: one `lui` each. |
| Data | 16 B | None | None |
| Instructions executed for each sincos | 39–44 | 45–50 | 42–47 |
| Max error | 1.45e-5 | 1.45e-5 (the same values, bit for bit) | 2.3e-5 |
| Max \|s² + c² − 1\| | 1.7e-7 | 1.7e-7 | 4.1e-5 |
| µs per frame saved, compared with Silas | 62 | 66 | 73 |

### How to select a version

- **One cache line** executes the fewest instructions. This is true only while its constant line is in the data cache. If the game removes the line from the cache, the call must wait for RAM.
- **Pure code** cannot have a data-cache miss. It uses 24 more bytes of instruction cache. It is one file, with no `.rodata` to place or align.
- **One constant** is pure code with 3 fewer instructions. The coefficients b, d and e have only 8 bits, so this version has its own coefficients ([`fit/fit_one.py`](fit/fit_one.py)). These coefficients are not fitted jointly, so the maximum of s² + c² − 1 is 240 times larger. This is important only where the code applies a rotation again and again to its own result. One example is the moving-platform code of SM64. On a platform, an object 1,000 units from the centre moves approximately 0.5 units per minute.
- **In ares, the three versions have the same speed.** The differences are smaller than the differences between layouts. ares uses a fixed cost for each cache miss and does not simulate RAM contention. Thus, ares cannot show which version is the fastest on a console.

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

## Accuracy

`fit/accuracy.py` calculates the sine and the cosine of all 65,536 angles with each method. It uses float32 and the same operation order as the code of the method. The reference is float64.

| | SM64 vanilla table | Silas | S5C6 (one cache line, pure code) | S5C6 one constant |
|---|---|---|---|---|
| Max error | 1.44e-03 | 1.92e-04 | 1.45e-05 | 2.28e-05 |
| Mean \|error\| | 4.58e-04 | 1.41e-05 | 4.97e-06 | 9.48e-06 |
| RMS error | 5.97e-04 | 1.73e-05 | 6.63e-06 | 1.18e-05 |
| Max \|s²+c²−1\| | 7.55e-08 | 7.09e-08 | 1.72e-07 | 4.14e-05 |
| Mean \|s²+c²−1\| | 2.96e-08 | 1.73e-08 | 3.66e-08 | 1.80e-05 |
| Mean s²+c²−1 (drift) | −4.5e-09 | +2.6e-10 | +1.8e-09 | +2.9e-07 |
| Max direction error (1/65536 turn) | 15.00 | 2.00 | 0.19 | 0.23 |
| Exact at 0°, 90°, 180° and 270° | Yes | Yes | Yes | Yes |
| sin(−a) = −sin(a) and cos(−a) = cos(a), exactly | No | Yes | Yes | No |
| Sine does not decrease from 0° to 90° | Yes | Yes | Yes | Yes |
| Different sine values in one turn | 2,049 | 32,757 | 32,763 | 32,765 |

- **Table error:** Most of the error of the table comes from its 4,096 steps. The table rounds each angle down to a multiple of 16.
- **Silas error:** Within 2 steps of 0° and 180°, 1 − c² rounds to 0. Thus the sine of Silas is exactly 0 at these angles. The largest error of Silas is at these angles.
- **Scale of s² + c² − 1:** One float32 rounding step near 1.0 is 1.2e-7. The display-list matrices of the N64 (16.16 fixed point) round rotation values to 1.5e-5. This step is larger than the values of all methods, except the one-constant version.
- **Drift:** Drift is the mean of s² + c² − 1. Drift is important only for a rotation that the code applies again and again to its own result. Example: at 30 frames per second, with a different angle in each frame, a length increases by 1 % in approximately 4 days with S5C6. With the one-constant version, this takes approximately 38 minutes. SM64 and MM make their matrices again from the angle in each frame. Thus, usual objects do not drift.
- **Direction error:** The difference between the direction of the (cos, sin) pair and the true angle.
- **Symmetry of the one-constant version:** Its two polynomials do not meet exactly at 45°. Thus, near ±45°, the last bits of sin(−a) and −sin(a) can be different.

## Cost

This section gives three measurements. They go from the smallest scope to the largest:

1. The size of the code.
2. The time for one call.
3. The time in a game.

### Size

`bench/footprint.py` measures the assembled kernels. It also checks that each `kernel/` file is the same as the benchmarked code, instruction for instruction. The column "Instructions executed" gives the minimum, the mean and the maximum for all 65,536 angles.

| | Function | Code bytes | 32-byte I-cache lines | Data | Instructions executed (min / mean / max) | `mul.s` | `sqrt.s` |
|---|---|---|---|---|---|---|---|
| SM64 vanilla table | `sins()` / `coss()` | Inline | | 20 KB; one 16-byte line for each lookup | Approximately 4 | 0 | 0 |
| Silas | `trig_sin` | 120 | 4 | None | 25 / 26.5 / 28 | 3–4 | 0–1 |
| | `trig_sincos` | 156 | 5 | None | 35 / 37.0 / 39 | 4 | 1 |
| S5C6 one cache line | `trig_sin` | 168 | 6 | 16 B | 24 / 25.5 / 27 | 4 | 0 |
| | `trig_sincos` | 176 | 6 | 16 B | 39 / 41.5 / 44 | 7 | 0 |
| S5C6 pure code | `trig_sin` | 192 | 6 | None | 26 / 27.5 / 29 | 4 | 0 |
| | `trig_sincos` | 200 | 7 | None | 45 / 47.5 / 50 | 7 | 0 |
| S5C6 one constant | `trig_sin` | 180 | 6 | None | 25 / 26.0 / 27 | 4 | 0 |
| | `trig_sincos` | 188 | 6 | None | 42 / 44.5 / 47 | 7 | 0 |

### Cycles for each call

A timer in the ROM measures 65,536 calls in [ares](https://ares-emu.net) v148:

- Interrupts are off.
- A first pass fills the caches. Thus, the caches are warm.
- The cost of the timing loop is subtracted.
- "In order" means the angles 0, 1, 2, …. "Random" means a pseudo-random angle for each call.
- The unit is CPU cycles (93.75 MHz).

| | sin, in order | sin, random | sin + cos as two calls, random | sincos, random |
|---|---|---|---|---|
| SM64 vanilla table (inline) | 5.5 | 24.5 | 50.9 | 50.9 (two lookups) |
| Silas | 65.5 | 65.5 | 132.0 | 93.0 |
| S5C6 one cache line | 54.5 | 54.5 | 110.0 | 89.5 |
| S5C6 pure code | 54.5 | 54.5 | 110.0 | 91.5 |
| S5C6 one constant | 53.0 | 53.0 | 107.0 | 88.5 |

- **The table is fast only while its lines are in the cache.** With angles in order, adjacent angles use the same cache line. With random angles, most lookups miss the 8 KB data cache. ares charges 40 cycles for each miss. The kernels have the same cost with angles in order and with random angles.
- **One `trig_sincos` call saves 18–39 cycles**, compared with two calls.
- **Not in this table:** the cost of a call when its code or its constant line is not in the cache. The in-game results include this cost.
- **Use these values only to compare methods.** ares uses fixed costs for each instruction and does not simulate the pipeline.

### In the game

| Item | Value |
|---|---|
| Game | [HackerSM64](https://github.com/HackerN64/HackerSM64), commit 3be00d2f, clang 21, `-Os` |
| Emulator | ares v148 |
| Input | The seven attract-mode demos of SM64: 4,304 measured frames, with approximately 440 sine and cosine calls per frame |
| Measurement | The HackerSM64 profiler: CPU time of the game thread, in µs per frame. Audio is not included. |
| Baseline | The vanilla table: 12,290 µs per frame |

**Layouts:** The position of code in memory changes which code shares cache lines. This alone changes each result by approximately ±3 %. Thus, each build was made three times, with 0, 1024 or 4096 bytes of padding before the kernel. The table below gives the mean of the three layouts. The brackets give the lowest and the highest value. To get the values for each layout, run `python3 bench/summary.py`.

Time in µs per frame, compared with the vanilla table. A negative value is faster than the table.

| | sincos at the changed call sites | Separate `sins()` and `coss()` calls | Saved compared with Silas, sincos |
|---|---|---|---|
| Silas | −9 (−276 to +461) | +75 (−257 to +400) | |
| S5C6 one cache line | −71 (−322 to +396) | +77 (−325 to +303) | 62 (46 to 75) |
| S5C6 pure code | −75 (−297 to +356) | +92 (−319 to +321) | 66 (21 to 105) |
| S5C6 one constant | −83 (−331 to +374) | +81 (−328 to +310) | 73 (55 to 88) |

- **Sincos** is the main result. [`bench/hsm64-sincos.patch`](bench/hsm64-sincos.patch) changes 13 functions to use `sincoss()`. These 13 functions make 98 % of the sine and cosine pairs in SM64.
- **Separate calls:** the call sites of the game do not change.
- **A call can be faster than a table lookup.** A call executes more instructions than a lookup. But a call does not cause the data-cache misses of the table. Also, a call site is smaller than an inline lookup, so there are fewer instruction-cache misses. With sincos, compared with the table, S5C6 has 150–201 fewer data-cache misses and 484–516 fewer instruction-cache misses per frame. Silas has 188 and 358 fewer.
- **Same-game control:** Each kernel changes the game slightly. Thus, the run with a kernel is not exactly the same as the run with the table. In the run with the one-cache-line version, Mario stays within 0.06 units of the vanilla run. As a second control, each kernel was compared with a table that the ROM fills at boot with the values of that kernel. These two runs play the same game (checked in each frame). With separate calls, the means of this control are: Silas +36, one cache line −17, pure code −29, one constant −69 µs.

## Checks

| Check | Result |
|---|---|
| Is `trig_sincos` equal to two `trig_sin` calls? | Yes, bit for bit, for all 65,536 angles and all kernels. Each ROM does this check. |
| Are the `kernel/` files the same as the benchmarked code? | Yes, instruction for instruction (`bench/footprint.py --elf-dir`). |
| Denormals, NaN or infinity? | None in any intermediate value, for all angles and all kernels. |
| Negative zero? | sin(0x8000) and cos(0x4000) return −0.0. The table returns +0.0. No code in SM64 divides by these values. |
| Built with IDO? | One-cache-line version only. Built in the vanilla SM64 decompilation (IDO 5.3, GNU as for the kernel): 559 call sites, all 65,536 values checked in the ROM, 4,800 frames run. |
| atan2s(cos, sin) round trip? | One-cache-line version only. On the 4,096 angles of the table: the same as the table (max 5). On all 65,536 angles: better than the table (max 5, table max 20). |
| Real console? | **Not tested.** Help is welcome: a `bench/build.py --hardware` build does not execute the ares-only instructions and shows its results on the title screen. |

## Limits

- **ares, not a console.** The CPU timing of ares is approximate. Cache-miss costs are fixed. There is no pipeline model and no memory contention with the RCP. The RDP is not timed.
- **clang, not GCC.** The default compiler of HackerSM64 is GCC. GCC was not tested.
- **One game.** The in-game results come from the SM64 demos. Other engines call sine and cosine in different ways.

## Reproduce

```sh
python3 fit/accuracy.py                              # the accuracy table (needs numpy)
python3 fit/fit.py                                   # S5C6 coefficients -> fit/coeffs.h
python3 fit/fit_one.py [--table]                     # one-constant coefficients
python3 bench/footprint.py --binutils DIR --clang DIR [--elf-dir work/HackerSM64-sincos]
python3 bench/build.py --baserom sm64.us.z64 --clang BIN --binutils BIN [--pad N] [--variants kernels sincos] [--cycles] [--hardware]
python3 bench/run.py [--variants kernels sincos] [--suffix=-padN | --suffix=-cyc]
python3 bench/summary.py                             # the speed tables, from bench/results/
```

- `bench/hsm64-bench.patch` adds the benchmark to HackerSM64.
- A `--cycles` build adds the timer for the cycles for each call. These builds are separate, because the code of the timer changes the layout.
- ares is deterministic: a ROM gives the same cycles in each run. Thus, results saved at different times can be combined. Control ROMs built again gave exactly the saved results.

The full report (method, call-site analysis, LUTX16 and glossary) is at https://msmfai.github.io/N64-trig/.

## Credits and license

- The fold is from Silas Lock.
- License: MIT.
- The repository contains no ROMs. `fit/accuracy.py` calculates the SM64 table from its formula. It does not copy the table.
