# N64-trig: sine and cosine kernels for the N64

> [!NOTE]
> - **AI use:** I am a mathematician. I designed the approximation: the polynomial forms, the fit, the 8-bit coefficients, and the constants in one cache line. I directed the work. Claude (the AI from Anthropic) wrote the code, the assembly, the benchmark and the report. The project contains no art, models or music.
> - **Source of the figures:** This documentation is generated from the experiment logs. All figures come from the benchmark results in [`bench/results/`](bench/results/) and from the scripts in [`fit/`](fit/) and [`bench/`](bench/). Refer to [Reproduce](#reproduce).
> - **Style guide:** This documentation uses ASD-STE100 Simplified Technical English.

This repository contains sine and cosine kernels for the N64 CPU (VR4300). It compares them with the kernel from Silas Lock:

- S5C4 and S5C6, in the versions of [Versions](#versions).
- 16 hand-written forms with a coefficient sweep: 3,281 kernels in all ([All forms](#all-forms)).

## Summary

Silas, and the two S5C4 versions with two functions (`trig_sincos` and `trig_sin`):

<!-- gen:summary-table -->
| | Silas | S5C4 pure code | S5C4 one cache line |
|---|---|---|---|
| Max error | 1.92e-04 | 2.89e-05 | 2.89e-05 |
| Max direction error (1/65536 turn) | 2.00 | 0.39 | 0.39 |
| Creep: max \|s²+c²−1\|, turns of 0° to 6° | 3.0e-08 | 6.0e-08 | 6.0e-08 |
| Max \|s²+c²−1\| | 7.1e-08 | 2.0e-05 | 2.0e-05 |
| CPU cycles for one `trig_sincos` call | 89.0 | 74.0 | 72.2 |
| CPU cycles for one `trig_sin` call | 62.2 | 51.0 | 46.1 |
| Code (cache lines) and data | 156 + 120 B (9 lines) | 168 + 124 B (10 lines) | 144 + 128 B (9 lines) + 16 B data |
| CPU time in the game, µs per frame, `sincoss()` | 12,309 ± 49 | 12,283 ± 47 (−27 ± 7) | 12,281 ± 44 (−28 ± 7) |
| Memory traffic in the game, bytes per frame, `sincoss()` | 545,023 ± 1,872 | 545,670 ± 1,701 (+647 ± 831) | 545,406 ± 1,178 (+383 ± 1,093) |
| CPU time in the game, µs per frame, separate calls | 12,538 ± 148 | 12,481 ± 149 (−57 ± 7) | 12,463 ± 148 (−76 ± 10) |
| Memory traffic in the game, bytes per frame, separate calls | 554,276 ± 9,027 | 554,614 ± 9,220 (+338 ± 395) | 554,951 ± 9,075 (+675 ± 525) |
<!-- /gen:summary-table -->

Accuracy: exact values over all 65,536 angles (experiment 1). Cycles: median of 5 layouts of a timing ROM (experiment 2). In-game values: mean ± 95 % confidence interval over 8 samples (experiment 4). In brackets: the paired difference from Silas.

## Criteria

This repository compares sine and cosine kernels by three criteria:

1. **Memory traffic.** The bytes that the CPU moves over the RDRAM bus. The CPU shares this bus with the RCP.
2. **Instructions and CPU cycles.**
3. **Accuracy.** The error of the sine and the cosine, and how well the sine and the cosine agree (s² + c² − 1).

The baseline is the kernel from Silas Lock: a 4th-order cosine polynomial, with the sine from a square root.

| Criterion | Experiment |
|---|---|
| 3. Accuracy | [1. Accuracy](#1-accuracy) |
| 2. Instructions and cycles | [2. Cost for each call](#2-cost-for-each-call), [4. Like-for-like comparison in the game](#4-like-for-like-comparison-in-the-game) |
| 1. Memory traffic | [2. Cost for each call](#2-cost-for-each-call) (bytes when cold), [4. Like-for-like comparison in the game](#4-like-for-like-comparison-in-the-game) |
| All three | [3. Pareto frontiers](#3-pareto-frontiers) |

### Gameplay limits

The S5C4 coefficients come from a search with four limits ([`fit/hwsearch.py`](fit/hwsearch.py)). Each limit is a property of the N64 or of float32:

| Limit | Value | Source of the value |
|---|---|---|
| Direction error | Less than 0.5 × 1/65536 turn | The (cos, sin) pair points to the nearest binary angle. |
| Creep | Max \|s² + c² − 1\| ≤ 6.0e-8 for turns of 0° to 6° (1 to 1,092 binary-angle steps) | The value for correctly rounded float32 sine and cosine. A rotation that is applied to its own result once per frame changes lengths by approximately half of this value per frame. |
| Length | Max \|s² + c² − 1\| ≤ 2e-5 for all angles | The rounding of the 16.16 fixed-point matrices of the RSP. |
| Range | \|sin\| and \|cos\| never above 1 | |

## Terms

| Term | Meaning |
|---|---|
| Angle | An SM64 or MM binary angle. 0x10000 is one turn. The kernels use only the low 16 bits. |
| Fold | The method that changes the angle to x, the offset from the nearest quarter turn. x is 45° or less. A polynomial in x, with a sign, gives the sine or the cosine of all angles. Silas Lock designed this method. |
| S5C4, S5C6 | The kernels of this repository. The sine polynomial goes to x⁵. The cosine polynomial goes to x⁴ (S5C4) or x⁶ (S5C6). |
| Silas | The kernel from Silas Lock: a 4th-order cosine polynomial, and the sine from a square root. |
| `trig_sin` | A kernel function that returns one value. For the cosine, call `trig_sin(angle + 0x4000)`. |
| `trig_sincos` | A kernel function that returns the sine and the cosine of one angle. In C, `sincoss(angle, s, c)` calls it. |
| Shared | A kernel with only `trig_sincos`. A single sine or cosine call runs `trig_sincos` and uses one of the two values. |
| s² + c² − 1 | A measure of how well a sine and a cosine agree. A rotation made from them changes lengths by approximately half of this value. |
| Creep | Max \|s² + c² − 1\| for turns of 0° to 6°. Refer to [Gameplay limits](#gameplay-limits). |
| Cold bytes | The bytes that the functions and the data of a kernel move over the RDRAM bus when none of them is in the cache: the 32-byte instruction-cache lines of each function, and one 16-byte line of data. |
| Memory traffic | The bytes that the CPU moves over the RDRAM bus: instruction-cache fills, data-cache fills and write-backs, and uncached accesses. The emulator counts them on the bus. |
| Sample | One random draw of the test conditions: the positions of code and data in memory, and the random seed of the game. |
| Pareto set | The kernels that no other kernel equals or beats in all objectives and beats in one. |
| ± | The half-width of the 95 % confidence interval of the mean (Student's t). |

## How the kernels work

S5C4 and S5C6 calculate two polynomials of the folded x:

    S5C4:  S(x) = x(a + x²(b + cx²))           C(x) = 1 + x²(d + ex²)
    S5C6:  S(x) = x(a + x²(b + cx²))           C(x) = 1 + x²(d + x²(e + fx²))

Silas calculates one polynomial. It calculates the other value with a square root:

    Silas: C(x) = 1 + x²(a + bx²)              S(x) = √(1 − C(x)²)

Design decisions:

- The nested form (Horner form) needs one multiplication and one addition for each coefficient. There is no square root.
- The highest coefficient of each polynomial has 8 significant bits. One `lui` instruction loads each of them.
- The S5C4 coefficients come from a search of float32 bit patterns under the [gameplay limits](#gameplay-limits) ([`fit/hwsearch.py`](fit/hwsearch.py)). The search scores the float32 output of the kernel, with the operations of the kernel in the same order.

## Versions

The versions of a kernel have the same fold, the same polynomials and the same coefficients, except the quantized version. They load the coefficients in different ways. All versions of one kernel give the same values, bit for bit (except the quantized version).

| Kernel | Version | Files | Constants | Data |
|---|---|---|---|---|
| S5C4 | One cache line | [`kernel/s5c4_line.s`](kernel/s5c4_line.s), [`kernel/s5c4.c`](kernel/s5c4.c) | a, b, d and 1.0: one 16-byte data line. c and e: one `lui` each. | 16 B |
| S5C4 | Pure code | [`kernel/s5c4_code.s`](kernel/s5c4_code.s) | a, b and d: `lui` + `ori`. c, e and 1.0: one `lui` each. | None |
| S5C4 | Shared | [`kernel/s5c4_shared.s`](kernel/s5c4_shared.s), [`kernel/s5c4.c`](kernel/s5c4.c) | As one cache line. Only `trig_sincos`. `trig_sin` is the same address. | 16 B |
| S5C6 | One cache line | [`kernel/s5c6.s`](kernel/s5c6.s), [`kernel/sincos.s`](kernel/sincos.s), [`kernel/s5c6.c`](kernel/s5c6.c) | a, b, d and e: one 16-byte data line. c, f and 1.0: one `lui` each. | 16 B |
| S5C6 | Pure code | [`kernel/s5c6_code.s`](kernel/s5c6_code.s), [`kernel/sincos_code.s`](kernel/sincos_code.s) | a, b, d and e: `lui` + `ori`. c, f and 1.0: one `lui` each. | None |
| S5C6 | Quantized | [`kernel/s5c6_quantized.s`](kernel/s5c6_quantized.s), [`kernel/sincos_quantized.s`](kernel/sincos_quantized.s) | a: `lui` + `ori`. b to f and 1.0: one `lui` each. Its own coefficients ([`fit/fit_quantized.py`](fit/fit_quantized.py)). | None |

- **S5C4 `trig_sin`, pure code:** the sine path and the cosine path load their three constants into the same registers and use one shared tail. The last factor of the cosine is 1.0. Thus the values are bit-identical to the separate polynomials.
- **S5C4 `trig_sin`, one cache line:** a branch-likely instruction (`bnezl`) does the last negation.

## All forms

[`kernel/forms/`](kernel/forms/) contains one hand-written file for each form and load style (one cache line, pure code). Each file has `trig_sincos` and `trig_sin`. The coefficients are assembler symbols (`--defsym S1=0x...`): thus one file serves all coefficient sets of its form. A constant in the code is `lui`, and `ori` only when its low 16 bits are not zero.

| Class | Forms | Values |
|---|---|---|
| S, C polynomials | S3C2, S3C4, S5C4, S5C6, S7C6, S7C8 | S = x(S1 + x²(S3 + …)), C = 1 + x²(C2 + …), on the octant fold |
| C + sqrt | C2+sqrt, C4+sqrt, C6+sqrt | C as above. S = √(1 − C²), with the sign of x. |
| S + sqrt | S3+sqrt, S5+sqrt | S as above. C = √(1 − S²). |
| Q: one polynomial | Q5, Q7 | sin = x(Q1 + x²(Q3 + …)) on the quadrant fold (\|x\| ≤ 90°). cos(a) = sin(a + 0x4000). |
| T: tangent half-angle | T3, T5, T7 | u = x(T1 + x²(T3 + …)), near tan(x/2). d = 1/(1 + u²), S = 2u·d, C = (1 − u²)·d: one division. |

Q9 is not in the set: in binary-angle units, its x⁹ coefficient is less than the smallest normal float32.

### Coefficient sweep

[`fit/sweep.py`](fit/sweep.py) finds the coefficients of each form. It changes the float32 bit patterns and scores the exact float32 output of the hand-written code (the same operations in the same order). For each form and each family of coefficient constraints, it gives these points:

- **12 weights w from 0.1 to 10,000:** minimise max(E, w·U). E is the max value error. U is max \|s² + c² − 1\|. A float64 minimax fit (SLSQP) gives the start point, then a search of the bit patterns.
- **Limits:** within the [gameplay limits](#gameplay-limits), the smallest creep, then the smallest E.

| Family | Constraint |
|---|---|
| free | All coefficients float32. |
| top 8-bit | The highest coefficient of each polynomial has 8 significant bits (one `lui`). |
| quantized | All coefficients 8-bit, except the first. |
| all 8-bit | All coefficients 8-bit. |

The sweep accepts only normal float32 coefficients and finite outputs. A denormal, infinite or NaN operand causes an exception on the VR4300.

Each point of the sweep is a kernel in each of four builds: one cache line or pure code, with two functions or shared (only `trig_sincos`).

<!-- gen:forms -->
| Form | Kernels | In the Pareto set of all kernels | Within the gameplay limits | Max error (min) | Max \|s²+c²−1\| (min) | Creep (min) | `trig_sincos` cycles | `trig_sin` cycles | Cold bytes |
|---|---|---|---|---|---|---|---|---|---|
| C2+sqrt | 156 | 91 | 0 | 4.4e-03 | 7.8e-08 | 3.0e-08 | 72.5–73.7 | 50.5–51.6 | 128–256 |
| C4+sqrt | 208 | 46 | 0 | 1.9e-04 | 6.4e-08 | 3.0e-08 | 82.5–84.5 | 60.5–62.5 | 144–288 |
| C6+sqrt | 208 | 13 | 0 | 1.9e-04 | 6.3e-08 | 3.0e-08 | 92.5–95.5 | 70.5–73.5 | 160–320 |
| Q5 | 208 | 34 | 0 | 9.8e-05 | 8.7e-05 | 8.7e-05 | 81.0–84.0 | 44.5–47.5 | 160–288 |
| Q7 | 208 | 20 | 0 | 7.0e-07 | 3.8e-07 | 3.2e-07 | 99.0–103.0 | 54.5–58.5 | 176–320 |
| S3+sqrt | 208 | 151 | 0 | 1.5e-04 | 8.8e-08 | 8.7e-08 | 78.0–80.0 | 57.2–59.2 | 128–256 |
| S3C2 | 208 | 132 | 0 | 2.6e-03 | 1.8e-05 | 2.8e-06 | 51.0–54.0 | 36.6–40.5 | 128–288 |
| S3C4 | 208 | 131 | 0 | 1.5e-04 | 6.7e-07 | 2.2e-07 | 61.0–65.0 | 41.7–46.6 | 144–320 |
| S5+sqrt | 208 | 100 | 0 | 6.0e-07 | 8.8e-08 | 8.5e-08 | 88.0–91.0 | 67.2–70.2 | 144–288 |
| S5C4 | 205 | 96 | 5 | 1.2e-05 | 2.1e-07 | 6.0e-08 | 71.0–76.0 | 46.1–52.5 | 160–352 |
| S5C6 | 208 | 48 | 16 | 5.9e-07 | 1.2e-07 | 5.9e-08 | 81.0–87.0 | 51.2–58.6 | 176–416 |
| S7C6 | 208 | 72 | 36 | 8.1e-08 | 1.2e-07 | 5.9e-08 | 91.0–98.0 | 56.1–64.5 | 192–400 |
| S7C8 | 208 | 46 | 40 | 5.8e-08 | 1.2e-07 | 6.0e-08 | 101.0–109.0 | 61.2–70.6 | 208–448 |
| T3 | 208 | 0 | 0 | 1.4e-04 | 2.3e-07 | 2.3e-07 | 95.0–97.0 | 85.0–87.0 | 160–304 |
| T5 | 208 | 0 | 0 | 2.3e-06 | 2.3e-07 | 2.2e-07 | 105.0–108.0 | 95.0–98.0 | 160–352 |
| T7 | 208 | 11 | 0 | 1.3e-07 | 2.3e-07 | 2.2e-07 | 115.0–119.0 | 105.0–109.0 | 176–368 |
<!-- /gen:forms -->

![Each form: all points of its parameter sweep](fit/frontier-forms.png)

## Use

### To replace the SM64 functions

1. Assemble one `kernel/s5c4_*.s` or `kernel/s5c6*.s` file.
2. For a version with a data line: also compile [`kernel/s5c4.c`](kernel/s5c4.c) (S5C4) or [`kernel/s5c6.c`](kernel/s5c6.c) (S5C6). This file contains the constant line `trig_k` (16 bytes, 16-byte aligned).
3. Include [`kernel/s5c6.h`](kernel/s5c6.h). It gives `sins(a)`, `coss(a)` and `sincoss(a, s, c)` for all kernels.

### To get the sine and the cosine of one angle

Call `sincoss(angle, s, c)`. It sets `s` to the sine and `c` to the cosine with one `trig_sincos` call.

### Calling convention

| Item | Value |
|---|---|
| Input | The angle in `$a0`. |
| `trig_sin` output | `$f0`. |
| `trig_sincos` output | The sine in `$f0` and the cosine in `$f2` (GNU C `_Complex float`). No value goes through memory. |
| Stack | Not used. All functions are leaf functions. |
| Registers changed | Only caller-saved registers: `$t0`–`$t9`, and the even registers `$f0`–`$f18`. |
| Syntax | GNU as, o32 ABI. |
| VR4300 hazards | No multiplication immediately after `mul.s`. No `mul.s` in a branch delay slot. At least one instruction between `mtc1` or `lwc1` and the first use of its register. [`bench/micro/hazards.py`](bench/micro/hazards.py) checks all kernels. |

## 1. Accuracy

[`bench/frontier.py`](bench/frontier.py) calculates `trig_sin(a)` and `trig_sin(a + 0x4000)` of all 65,536 angles with a float32 model of each kernel. The model does the operations of the assembly in the same order. The reference is float64. The values are exact, because the script calculates all angles. For each kernel, the CRC-32 of the model output is equal to the CRC-32 of the kernel output in the timing ROM (experiment 2).

<!-- gen:accuracy -->
| Kernel | Max error | Max direction error (1/65536 turn) | Creep: max \|s²+c²−1\|, turns of 0° to 6° | Max \|s²+c²−1\| | Mean s²+c²−1 (drift) | \|sin\|, \|cos\| never above 1 | Within the gameplay limits |
|---|---|---|---|---|---|---|---|
| Silas | 1.92e-04 | 2.00 | 3.0e-08 | 7.1e-08 | +2.6e-10 | Yes | No |
| S5C6 one cache line | 1.45e-05 | 0.19 | 6.1e-08 | 1.7e-07 | +1.8e-09 | Yes | No |
| S5C6 pure code | 1.45e-05 | 0.19 | 6.1e-08 | 1.7e-07 | +1.8e-09 | Yes | No |
| S5C6 quantized | 2.28e-05 | 0.23 | 5.7e-06 | 4.1e-05 | +2.9e-07 | Yes | No |
| S5C4 one cache line | 2.89e-05 | 0.39 | 6.0e-08 | 2.0e-05 | -2.3e-06 | Yes | Yes |
| S5C4 pure code | 2.89e-05 | 0.39 | 6.0e-08 | 2.0e-05 | -2.3e-06 | Yes | Yes |
<!-- /gen:accuracy -->

- **Direction error:** The difference between the direction of the (cos, sin) pair and the true angle, in units of 1/65536 turn.
- **Drift:** The mean of s² + c² − 1 over all angles.
- **Silas at 0° and 180°:** Within 2 steps of 0° and 180°, 1 − c² rounds to 0, and the sine of Silas is exactly 0.

## 2. Cost for each call

A timing ROM ([`bench/micro/`](bench/micro/)) runs each kernel in [Ares 64](https://github.com/HailToDodongo/ares-64) (commit b4ead632f), with the CPU interpreter:

- The ROM contains no Nintendo code: it boots with the public-domain IPL3 of libdragon ([`bench/micro/IPL3_LICENSE.md`](bench/micro/IPL3_LICENSE.md)).
- Each function runs on 4,096 pseudo-random angles. A first pass fills the caches. Thus, the caches are warm.
- The cost of an empty function is subtracted. The unit is CPU cycles (93.75 MHz).
- Each kernel runs in 5 layouts of the ROM: 3,232 × N bytes of code (mod 16 KB) and 1,616 × N bytes of data (mod 8 KB) between the timing loop and the kernels (`build.py --layout N`). In one layout, the lines of a kernel can collide with the lines of the timing loop. The value is the median of the 5 layouts. No kernel has a collision in more than one layout ([`bench/results/micro/`](bench/results/micro/)).
- The ROM also checks that `trig_sincos` is equal to two `trig_sin` calls, for all 65,536 angles.

<!-- gen:cost -->
| Kernel | `trig_sincos` bytes | `trig_sin` bytes | Data bytes | Cold bytes | `trig_sincos` cycles | `trig_sin` cycles |
|---|---|---|---|---|---|---|
| Silas | 156 | 120 | None | 288 | 89.0 | 62.2 |
| Silas, shared | 156 | (the `trig_sincos` function) | None | 160 | 89.0 | 90.0 |
| S5C6 one cache line | 176 | 168 | 16 | 400 | 85.7 | 51.6 |
| S5C6 pure code | 200 | 192 | None | 416 | 87.5 | 51.5 |
| S5C6 quantized | 188 | 180 | None | 384 | 84.5 | 50.0 |
| S5C4 one cache line | 144 | 128 | 16 | 304 | 72.2 | 46.1 |
| S5C4 pure code | 168 | 124 | None | 320 | 74.0 | 51.0 |
| S5C4 shared | 144 | (the `trig_sincos` function) | 16 | 176 | 72.2 | 73.2 |
<!-- /gen:cost -->

- **Bytes:** the size of each function. **Cold bytes:** refer to [Terms](#terms).
- **Shared:** a single sine or cosine call runs `trig_sincos`.
- `build.py --hardware` makes a version of the timing ROM for a console. It shows the results on the screen ([`bench/micro/expected-console.png`](bench/micro/expected-console.png)).

## 3. Pareto frontiers

[`bench/frontier.py`](bench/frontier.py) compares all kernels by seven objectives. Lower is better for each objective:

| Objective | Source |
|---|---|
| Max error, max direction error, creep, max \|s² + c² − 1\| | Experiment 1 (the float32 model) |
| `trig_sincos` cycles, `trig_sin` cycles | Experiment 2 (the timing ROM) |
| Cold bytes | The symbol sizes of the timing ROM |

The kernels:

- The kernels of [Versions](#versions), Silas, and Silas shared.
- All points of the [coefficient sweep](#coefficient-sweep) in the files of [`kernel/forms/`](kernel/forms/), in four builds each. A point that is equal to a kernel of `kernel/` in all objectives is one row.

The code of a file depends only on which coefficients are 8-bit. Thus the timing ROM times one point for each file and family (126 kernels, and the same with shared). The script checks that each other point has the same `lui`/`ori` pattern as its timed point.

Method:

- **Rank:** non-dominated sorting on the seven objectives. Rank 1 is the Pareto set. Rank 2 is the Pareto set of the other kernels, and so on.
- **Pareto set within the gameplay limits:** the kernels within the [gameplay limits](#gameplay-limits), ranked on the three costs only.
- **Parallel coordinates** ([`fit/frontier-parallel.png`](fit/frontier-parallel.png)): one line for each kernel, one vertical axis for each objective. The accuracy axes are logarithmic.
- **Scatterplot matrix** ([`fit/frontier-matrix.png`](fit/frontier-matrix.png)): all 21 pairs of objectives, with the Pareto frontier of each pair.
- **Forms** ([`fit/frontier-forms.png`](fit/frontier-forms.png), [All forms](#all-forms)): one panel for each form, with the Pareto set of the form.

![Parallel coordinates of all kernels](fit/frontier-parallel.png)

![Scatterplot matrix of all pairs of objectives](fit/frontier-matrix.png)

<!-- gen:frontier -->
Kernels: 3281. Within the gameplay limits: 100. For each kernel, the CRC of the model output is equal to the CRC of the timing ROM.

**Pareto set within the gameplay limits.** The kernels within the limits that no other kernel within the limits equals or beats in the three costs (sincos cycles, sin cycles, cold bytes) and beats in one (2 kernels):

| Kernel | Form | Coefficients | max error | direction error | creep \|U\| | max \|U\| | sincos cycles | sin cycles | cold bytes | Within the gameplay limits |
|---|---|---|---|---|---|---|---|---|---|---|
| S5C4 one cache line | S, C polynomials | top 8-bit | 2.9e-05 | 0.39 | 6.0e-08 | 2.0e-05 | 72.2 | 46.1 | 304 | Yes |
| S5C4 shared | S, C polynomials | top 8-bit | 2.9e-05 | 0.39 | 6.0e-08 | 2.0e-05 | 72.2 | 73.2 | 176 | Yes |

The Pareto set on all seven objectives has 993 of the 3281 kernels: [`fit/frontier-pareto.md`](fit/frontier-pareto.md). All values: [`fit/frontier.json`](fit/frontier.json).
<!-- /gen:frontier -->

[`fit/pareto.png`](fit/pareto.png) shows the frontier of max error against max \|s² + c² − 1\| for S5C6 coefficient families ([`fit/pareto.py`](fit/pareto.py)).

## 4. Like-for-like comparison in the game

Each match-up compares kernels with the same function structure:

- **Two functions:** `trig_sincos` and `trig_sin`. The reference is Silas.
- **One function:** only `trig_sincos`, also for single calls. The reference is Silas shared.

| Item | Value |
|---|---|
| Game | [HackerSM64](https://github.com/HackerN64/HackerSM64), commit 3be00d2f, clang 21, `-Os` |
| Emulator | Ares 64 (commit b4ead632f), headless, CPU interpreter (it fetches every instruction through the modelled caches), RSP recompiler |
| Input | The seven attract-mode demos of SM64: 4,304 measured frames |
| Builds | **`sincoss()`:** 13 functions get the sine and the cosine of one angle from one `trig_sincos` call ([`bench/hsm64-sincos.patch`](bench/hsm64-sincos.patch)). **Separate calls:** the game calls `sins()` and `coss()`. |
| Kernel slot | The build has a fixed slot for the kernel ([`bench/trig_slot.s`](bench/trig_slot.s)). [`bench/slot.py`](bench/slot.py) writes each kernel into a copy of the ROM. Thus the ROMs of one sample are different only in the slot. |
| Samples | 8. Each sample is one build with a random draw of the code shift, the data shift, the heap shift and the game seed ([`bench/sample.py`](bench/sample.py)). |
| Result | The mean ± 95 % confidence interval. In brackets: the paired difference from the reference in the same sample, with its own interval. |
| Scripts | [`bench/fast.py`](bench/fast.py) (runs), [`bench/fair.py`](bench/fair.py) (tables and plot) |

<!-- gen:fair -->
8 samples.

**Two functions (`trig_sincos` and `trig_sin`).** Reference: Silas.

| Kernel | Code (cache lines) and data | `sincoss()`: CPU time, µs per frame | `sincoss()`: memory traffic, bytes per frame | Separate calls: CPU time, µs per frame | Separate calls: memory traffic, bytes per frame |
|---|---|---|---|---|---|
| Silas | 156 + 120 B (9 lines) | 12,309 ± 49 | 545,023 ± 1,872 | 12,538 ± 148 | 554,276 ± 9,027 |
| S5C4 one cache line | 144 + 128 B (9 lines) + 16 B data | 12,281 ± 44 (−28 ± 7) | 545,406 ± 1,178 (+383 ± 1,093) | 12,463 ± 148 (−76 ± 10) | 554,951 ± 9,075 (+675 ± 525) |
| S5C4 pure code | 168 + 124 B (10 lines) | 12,283 ± 47 (−27 ± 7) | 545,670 ± 1,701 (+647 ± 831) | 12,481 ± 149 (−57 ± 7) | 554,614 ± 9,220 (+338 ± 395) |

**One function (only `trig_sincos`, also for single calls).** Reference: Silas, shared.

| Kernel | Code (cache lines) and data | `sincoss()`: CPU time, µs per frame | `sincoss()`: memory traffic, bytes per frame | Separate calls: CPU time, µs per frame | Separate calls: memory traffic, bytes per frame |
|---|---|---|---|---|---|
| Silas, shared | 156 B (5 lines) | 12,313 ± 49 | 544,633 ± 1,535 | 12,727 ± 148 | 557,196 ± 9,512 |
| S5C4 shared | 144 B (5 lines) + 16 B data | 12,286 ± 43 (−27 ± 8) | 545,411 ± 1,189 (+778 ± 807) | 12,646 ± 149 (−81 ± 8) | 557,409 ± 9,641 (+213 ± 632) |
<!-- /gen:fair -->

![Paired differences in the game](bench/fair.png)

## 5. S5C6 in the game

The S5C6 versions were compared with Silas in an earlier set of runs. Each sample of these runs is a full build of each kernel.

### Method

<!-- gen:method -->
| Item | Value |
|---|---|
| Game | [HackerSM64](https://github.com/HackerN64/HackerSM64), commit 3be00d2f, clang 21, `-Os` |
| Emulator | [Ares 64](https://github.com/HailToDodongo/ares-64) (commit b4ead632f), headless, CPU interpreter: it fetches every instruction through the modelled caches ([`bench/ares64.js`](bench/ares64.js)) |
| Input | The seven attract-mode demos of SM64: 4,304 measured frames, with approximately 456 sine and cosine calls per frame |
| Builds | Two for each kernel. **`sincoss()`:** [`bench/hsm64-sincos.patch`](bench/hsm64-sincos.patch) changes 13 functions to get the sine and the cosine of one angle from one `trig_sincos` call. These 13 functions make 98 % of the sine and cosine pairs. **Separate calls:** the game calls `sins()` and `coss()`, and each is one `trig_sin` call. |
| Test conditions | 64 samples. Each sample is one random draw of the four conditions below ([`bench/sample.py`](bench/sample.py)). All builds of a sample use the same draw. |
| Result | The mean of the 64 samples ± the 95 % confidence interval (Student's t). In brackets: the difference from Silas in the same sample, with its own confidence interval. |

**Test conditions:** The position of code and data in memory decides which of them collide in the caches. These collisions change each result by chance, by up to approximately ±3 %. Each sample draws the positions and the game state at random, from the full period of each cache:

| Condition | Draw | Effect |
|---|---|---|
| Code shift | 0 to 16 KB of padding before the kernel, in 32-byte steps | Instruction-cache collisions (16 KB cache, 32-byte lines) |
| Data shift | 0 to 8 KB of `.bss` padding, in 16-byte steps | Data-cache collisions of the static data (8 KB cache, 16-byte lines) |
| Heap shift | 0 to 8 KB added to the start of the main pool, in 16-byte steps | Data-cache collisions of all data that the game allocates at run time |
| Game seed | 0 to 65,113 steps of the random generator of the game, at boot | The random choices of the objects. The demos give the same input. |

All four conditions are uniform and independent. Each sample has its own random generator, so the samples are independent. New samples are added over time. The tables include all finished samples.
<!-- /gen:method -->

### Memory traffic

Bytes per frame that the CPU moves over the RDRAM bus, counted by the emulator on the bus.

<!-- gen:traffic -->
| | `sincoss()` at the 13 changed call sites | Separate `sins()` and `coss()` calls |
|---|---|---|
| Silas | 543,105 ± 3,035 | 551,562 ± 3,496 |
| S5C6 one cache line | 545,259 ± 3,143 (+2,154 ± 1,390) | 553,459 ± 3,639 (+1,897 ± 1,600) |
| S5C6 pure code | 545,275 ± 3,313 (+2,169 ± 1,690) | 552,762 ± 3,841 (+1,200 ± 1,631) |
| S5C6 quantized | 544,761 ± 3,285 (+1,656 ± 1,396) | 552,666 ± 3,813 (+1,103 ± 1,625) |
<!-- /gen:traffic -->

### CPU time

Game-thread CPU time from the HackerSM64 profiler, in µs per frame. Audio is not included.

<!-- gen:cputime -->
| | `sincoss()` at the 13 changed call sites | Separate `sins()` and `coss()` calls |
|---|---|---|
| Silas | 12,282 ± 55 | 12,536 ± 66 |
| S5C6 one cache line | 12,307 ± 58 (+25 ± 26) | 12,519 ± 68 (−17 ± 31) |
| S5C6 pure code | 12,303 ± 60 (+20 ± 30) | 12,498 ± 71 (−37 ± 30) |
| S5C6 quantized | 12,293 ± 61 (+11 ± 26) | 12,490 ± 71 (−46 ± 30) |
<!-- /gen:cputime -->

## Checks

| Check | Result |
|---|---|
| Is `trig_sincos` equal to two `trig_sin` calls? | Yes, bit for bit, for all 65,536 angles and all kernels. The timing ROM and each game ROM do this check. |
| Is the float32 model equal to the kernel? | Yes. For each timed kernel, the CRC-32 of the model output is equal to the CRC-32 of the timing ROM, in all 5 layouts. A separate ROM checked 306 more points of the sweep (three for each form, family and load style). |
| VR4300 hazards? | None. [`bench/micro/hazards.py`](bench/micro/hazards.py) checks each kernel of the timing ROM. A test file with each hazard gives each finding. |
| Gameplay (S5C6) | With each S5C6 version, Mario stays within 0.06 units of the run with the SM64 table in all demos. |
| Denormals, NaN or infinity? | None in any intermediate value, for all angles and all kernels. |
| Negative zero? | sin(0x8000) and cos(0x4000) return −0.0. No code in SM64 divides by these values. |
| Built with IDO? | S5C6 one-cache-line version only. Built in the vanilla SM64 decompilation (IDO 5.3, GNU as for the kernel): 559 call sites, all 65,536 values checked in the ROM, 4,800 frames run. |

## Console test

[`bench/hardware/`](bench/hardware/) contains a test package for a console: BPS patches for HackerSM64, the exact base ROM to use, and the expected screens. Refer to [`bench/hardware/README.md`](bench/hardware/README.md). The timing ROM of experiment 2 also runs on a console (`bench/micro/build.py --hardware`).

## Reproduce

```sh
uv run --with numpy --with scipy python3 fit/hwsearch.py          # S5C4 coefficients under the gameplay limits
uv run --with numpy --with scipy python3 fit/sweep.py --forms S5C4 --out fit/sweep/S5C4.json   # one form of the sweep
python3 bench/handforms.py list --select timing > bench/results/micro/kernels.json
python3 bench/micro/build.py --clang BIN --binutils BIN --forms bench/micro/no-forms.json --hand-forms bench/results/micro/kernels.json --layout N --out work/micro-LN
ares-test bench/micro/micro.js work/micro-LN/micro.z64 interp     # experiment 2 (N = 1 to 5 -> bench/results/micro/layoutN.log)
uv run --with numpy --with scipy --with matplotlib python3 bench/frontier.py --readme   # experiments 1 and 3
python3 bench/fast.py run --name hand-sincos --kernels Silas S5C4_line S5C4_pure Silas+shared S5C4_shared --clang BIN --binutils BIN --baserom sm64.us.z64 --ares ARES_TEST
python3 bench/fast.py run --name hand-separate --separate --kernels ...    # experiment 4
uv run --with matplotlib python3 bench/fair.py                   # experiment 4 plot
python3 bench/readme.py                                          # the in-game tables of this README
python3 bench/sample.py --baserom sm64.us.z64 --clang BIN --binutils BIN   # experiment 5
```

- `bench/hsm64-bench.patch` adds the benchmark to HackerSM64.
- ares is deterministic: a ROM gives the same counts in each run. Thus, results saved at different times can be combined.
- The docstring of each script gives its options.

## Credits and license

- Silas Lock designed the fold (refer to [Terms](#terms)) and the baseline kernel.
- License: MIT.
- The repository contains no ROMs.
