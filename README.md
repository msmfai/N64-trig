**AI use:** I'm a mathematician: I designed the approximation (the polynomial forms, the fit, truncating c and f to 8 bits, the constants in one cache line) and directed the work. Claude (Anthropic's AI) wrote the code, assembly, benchmark and report. No art, models or music.

A folded polynomial joint sine / cosine kernel for the N64 (VR4300), more than 10x more accurate than Silas Lock's.

It uses a polynomial approximation of

    S(x) = x(a + x²(b + cx²))
    C(x) = 1 + x²(d + x²(e + fx²))

instead of Silas's

    C(x) = 1 + x²(a + bx²)
    S(x) = √(1 − C(x)²)

and makes it inexpensive with the use of brackets you can see; by truncating c and f to 8 bit so they fit on one line of assembly; and putting the remaining constants into one cache line.

## Terms used below

- **Angles** are SM64/MM binary angles: 0x10000 is one turn. Only the low 16 bits are used.
- **The fold** (Silas's idea): the angle is reduced to x, its offset from the nearest quarter turn (at most 45°). S(x) or C(x) above, with a sign, gives the sine or cosine of any angle.
- **S5C6** is this kernel: a sine polynomial up to x⁵ and a cosine polynomial up to x⁶.
- **`trig_sin`** returns one value (cosine is `trig_sin(angle + 0x4000)`). **`trig_sincos`** returns the sine and cosine of one angle from one call, which is cheaper than two calls.
- **The vanilla table** is what SM64 ships: `sins()` and `coss()` read a 20 KB table of 4,096 steps per turn.
- **s² + c² − 1** measures whether a sine and cosine fit together. A rotation built from them scales lengths by about half this amount.

## Summary

S5C6 (the cache-line version) against Silas's kernel and SM64's table:

| | SM64 vanilla table | Silas | S5C6 |
|---|---|---|---|
| Max error | 1.4e-3 | 1.9e-4 | **1.45e-5** |
| Max \|s² + c² − 1\| | 7.6e-8 | **7.1e-8** | 1.7e-7 |
| CPU cycles per sine + cosine, warm cache | 51 (random angles) | 93 | **89.5** |
| Game time per frame against the table, SM64 demos | 0 | −9 µs | **−71 µs** |

- S5C6 is 13x more accurate than Silas and 100x more accurate than the table.
- Silas's sine and cosine fit together slightly better (it computes one from the other), but both are within about 1.5 float32 rounding steps.
- In the game, S5C6 saves about 62 µs per frame against Silas. Code placement alone moves results by about ±3%, so read these as means over three layouts (see [In the game](#in-the-game)).
- Measured in the ares emulator. **Not yet tested on a real N64.**

## Three versions

The kernel comes in three versions. They share the fold and the polynomial shapes, and differ in how the six coefficients get into registers.

| | One cache line | Pure code | One constant |
|---|---|---|---|
| Files | [`kernel/sincos.s`](kernel/sincos.s), [`kernel/s5c6.s`](kernel/s5c6.s) | [`kernel/sincos_code.s`](kernel/sincos_code.s), [`kernel/s5c6_code.s`](kernel/s5c6_code.s) | [`kernel/sincos_one.s`](kernel/sincos_one.s), [`kernel/s5c6_one.s`](kernel/s5c6_one.s) |
| c, f and 1.0 | one `lui` each | one `lui` each | one `lui` each |
| a, b, d, e | read from one 16-byte data-cache line | `lui` + `ori` each | a: `lui` + `ori`; b, d, e: one `lui` each |
| Data | 16 B | none | none |
| Instructions executed per sincos | 39–44 | 45–50 | 42–47 |
| Max error | 1.45e-5 | 1.45e-5 (same values, bit for bit) | 2.3e-5 |
| Max \|s² + c² − 1\| | 1.7e-7 | 1.7e-7 | 4.1e-5 |
| µs/frame saved against Silas | 62 | 66 | 73 |

**Why three:**
- **One cache line** runs the fewest instructions, but only while its line is in the data cache. If the game has evicted it, the call waits for RAM.
- **Pure code** can never miss on data, at the cost of 24 more bytes of instruction cache. It is one self-contained file with no `.rodata` to place or align.
- **One constant** is pure code with 3 fewer instructions. With b, d and e cut to 8 bits it needs its own coefficients ([`fit/fit_one.py`](fit/fit_one.py)) and loses the joint fit: its s² + c² − 1 is 240x larger. That only matters where a rotation is applied again and again to its own result. SM64's moving-platform code is one such place, where an object 1,000 units from the centre would creep about half a unit a minute.
- **In ares the three are tied.** The differences are smaller than the layout spread, and ares charges a flat cost per cache miss with no RAM contention, so it cannot say which wins on a console.

## Using it

- **Sine and cosine together:** assemble one of `kernel/sincos*.s` and include [`kernel/sincos.h`](kernel/sincos.h). `sincoss(angle, s, c)` sets both.
- **Sine or cosine alone, and sincos:** assemble one of `kernel/s5c6*.s` and include [`kernel/s5c6.h`](kernel/s5c6.h). It gives SM64-style `sins(a)`, `coss(a)` and `sincoss(a, s, c)`. The cache-line `s5c6.s` also needs [`kernel/s5c6.c`](kernel/s5c6.c), which holds the 16-byte, 16-byte-aligned constant line.
- **Calling convention:** angle in `$a0`. `trig_sin` returns in `$f0`; `trig_sincos` returns sine in `$f0` and cosine in `$f2` (GNU C `_Complex float`), so nothing goes through memory. Leaf functions, no stack, caller-saved registers only: `$t0`–`$t7` and even `$f0`–`$f16`.
- GNU as syntax (o32). No kernel has the multiply pattern of the VR4300 multiply erratum (a multiply right after `mul.s`, or `mul.s` in a branch delay slot).

## Accuracy

Over all 65,536 angles, sine and cosine, evaluated in float32 exactly as each method's code does it, against float64. Reproduce: `python3 fit/accuracy.py`.

| | SM64 vanilla table | Silas | S5C6 (cache line, pure code) | S5C6 one constant |
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

- **The table's error** comes mostly from its 4,096 steps: an angle is rounded down to a multiple of 16.
- **Silas** returns a sine of exactly 0 within 2 steps of 0° and 180°, because 1 − c² rounds to 0 there. That is where its largest error is.
- **s² + c² − 1, for scale:** one float32 rounding step near 1.0 is 1.2e-7. The N64's display-list matrices (16.16 fixed point) round rotation entries to 1.5e-5, which is coarser than every method here except the one-constant version.
- **Drift** is the average of s² + c² − 1. It matters only for a rotation applied again and again to its own result. At 30 frames a second with a different angle each frame, growing 1% takes about 4 days with S5C6 and 38 minutes with the one-constant version. SM64 and MM rebuild their matrices from the angle every frame, so ordinary objects never drift.
- **Direction error** is how far the direction the (cos, sin) pair points is from the true angle.
- **Odd/even exactly:** the one-constant polynomials don't meet exactly at 45°, so sin(−a) and −sin(a) can differ in the last bits near ±45°.

## Cost

Size first, then the time a call takes on its own, then the time it takes inside a game.

### Size

From the assembled kernels (`python3 bench/footprint.py`, which also checks that each `kernel/` file is instruction for instruction the code that was benchmarked). Instructions executed: min / mean / max over all 65,536 angles.

| | function | code bytes | 32-byte I-cache lines | data | instructions executed | mul.s | sqrt.s |
|---|---|---|---|---|---|---|---|
| SM64 vanilla table | `sins()` / `coss()` | inline | | 20 KB; one 16-byte line per lookup | ~4 | 0 | 0 |
| Silas | `trig_sin` | 120 | 4 | none | 25 / 26.5 / 28 | 3–4 | 0–1 |
| | `trig_sincos` | 156 | 5 | none | 35 / 37.0 / 39 | 4 | 1 |
| S5C6 one cache line | `trig_sin` | 168 | 6 | 16 B | 24 / 25.5 / 27 | 4 | 0 |
| | `trig_sincos` | 176 | 6 | 16 B | 39 / 41.5 / 44 | 7 | 0 |
| S5C6 pure code | `trig_sin` | 192 | 6 | none | 26 / 27.5 / 29 | 4 | 0 |
| | `trig_sincos` | 200 | 7 | none | 45 / 47.5 / 50 | 7 | 0 |
| S5C6 one constant | `trig_sin` | 180 | 6 | none | 25 / 26.0 / 27 | 4 | 0 |
| | `trig_sincos` | 188 | 6 | none | 42 / 44.5 / 47 | 7 | 0 |

### Cycles per call

Timed inside the ROM in [ares](https://ares-emu.net) v148: 65,536 calls with interrupts off, after a warm-up pass so the caches are warm, with the loop's own cost subtracted. "In order" means angles 0, 1, 2, …; "random" means a pseudo-random angle for each call. CPU cycles (93.75 MHz).

| | sin, in order | sin, random | sin + cos as two calls, random | sincos, random |
|---|---|---|---|---|
| SM64 vanilla table (inline) | 5.5 | 24.5 | 50.9 | 50.9 (two lookups) |
| Silas | 65.5 | 65.5 | 132.0 | 93.0 |
| S5C6 one cache line | 54.5 | 54.5 | 110.0 | 89.5 |
| S5C6 pure code | 54.5 | 54.5 | 110.0 | 91.5 |
| S5C6 one constant | 53.0 | 53.0 | 107.0 | 88.5 |

- **The table is cheap only while its lines are cached.** In order, neighbouring angles share a cache line. At random angles most lookups miss the 8 KB data cache, and ares charges 40 cycles a miss. The kernels cost the same in any order.
- **One `trig_sincos` saves 18–39 cycles** against two calls.
- **Not in this table:** what a call costs when its own code or its constant line has been evicted. The in-game figures below include that as it actually happens.
- ares charges fixed costs per instruction and has no pipeline model, so treat these as relative.

### In the game

**Method:** SM64's seven attract-mode demos on [HackerSM64](https://github.com/HackerN64/HackerSM64) (commit 3be00d2f, clang 21, `-Os`), in ares v148. That is 4,304 measured frames with about 440 sine and cosine calls per frame. The figure is HackerSM64's own profiler: game-thread CPU microseconds per frame, with audio excluded. The vanilla table takes 12,290 µs per frame.

**Layouts:** where code sits in memory changes which code shares cache lines, and that alone moves every result by about ±3%. Each build was therefore made three times, with 0, 1024 or 4096 bytes of padding before the kernel. The table gives the mean and, in brackets, the lowest and highest of the three. Per-layout figures: `python3 bench/summary.py`.

µs per frame against the vanilla table (negative is faster):

| | sincos at the converted call sites | separate `sins()` / `coss()` calls | saved against Silas, sincos |
|---|---|---|---|
| Silas | −9 (−276 to +461) | +75 (−257 to +400) | |
| S5C6 one cache line | −71 (−322 to +396) | +77 (−325 to +303) | 62 (46 to 75) |
| S5C6 pure code | −75 (−297 to +356) | +92 (−319 to +321) | 66 (21 to 105) |
| S5C6 one constant | −83 (−331 to +374) | +81 (−328 to +310) | 73 (55 to 88) |

- **Sincos** is the main result. [`bench/hsm64-sincos.patch`](bench/hsm64-sincos.patch) converts the 13 functions that make 98% of SM64's sine/cosine pairs to `sincoss()`. **Separate calls** leave the game's call sites unchanged.
- **Why a call can beat a table:** a call executes more instructions than a lookup, but it avoids the table's data-cache misses, and a call site is smaller than an inline lookup, which saves instruction-cache misses. With sincos, per frame against the table: S5C6 makes 150–201 fewer data-cache misses and 484–516 fewer instruction-cache misses; Silas 188 and 358.
- **Same-game control:** every kernel changes the game slightly, so its run is not the table's exact demo. Mario stays within 0.06 units of the vanilla run (checked for the cache-line version). Each kernel was also run against a table refilled at boot with its own values, which plays the identical game (checked every frame). With separate calls the means are Silas +36, cache line −17, pure code −29, one constant −69 µs.

## Checks

| | |
|---|---|
| `trig_sincos` equal to two `trig_sin` calls? | Bit-identical for all 65,536 angles, every kernel, checked inside each ROM. |
| `kernel/` files the same as the benchmarked code? | Yes, instruction for instruction (`bench/footprint.py --elf-dir`). |
| Denormals, NaN, infinity? | None in any intermediate for any angle, all kernels. |
| Negative zero? | sin(0x8000) and cos(0x4000) return −0.0 (table: +0.0). Nothing in SM64 divides by them. |
| Built with IDO? | Cache-line version, in vanilla decomp SM64 (IDO 5.3, GNU as for the kernel): 559 call sites, all 65,536 values checked in the ROM, 4,800 frames run. Not repeated for the other two versions. |
| atan2s(cos, sin) round trip? | Cache-line version: same as the table on its 4,096 angles (max 5); better on all 65,536 (max 5 against 20). |
| Real console? | **Not tested.** Help is appreciated: `bench/build.py --hardware` builds never run the ares-only instructions and show their results on the title screen. |

## Limits

- **ares, not a console.** Its CPU timing is approximate: flat cache-miss costs, no pipeline model, no memory contention with the RCP, and the RDP is not timed.
- **clang, not GCC.** HackerSM64's default compiler is GCC, which was not tested.
- **One game.** The in-game figures come from SM64's demos; another engine calls sine and cosine differently.

## Reproduce

```sh
python3 fit/accuracy.py                              # the accuracy table (numpy)
python3 fit/fit.py                                   # S5C6 coefficients -> fit/coeffs.h
python3 fit/fit_one.py [--table]                     # one-constant coefficients
python3 bench/footprint.py --binutils DIR --clang DIR [--elf-dir work/HackerSM64-sincos]
python3 bench/build.py --baserom sm64.us.z64 --clang BIN --binutils BIN [--pad N] [--variants kernels sincos] [--cycles] [--hardware]
python3 bench/run.py [--variants kernels sincos] [--suffix=-padN | --suffix=-cyc]
python3 bench/summary.py                             # the speed tables, from bench/results/
```

- `bench/hsm64-bench.patch` adds the benchmark to HackerSM64. `--cycles` builds add the cycles-per-call timer; they are separate builds because the timer's code moves the layout.
- ares is deterministic: a ROM gives the same cycles on every run, so results saved at different times combine. Rebuilt control ROMs matched the saved results exactly.

Full report (method, the call-site analysis, LUTX16, glossary): https://msmfai.github.io/N64-trig/

Fold: Silas Lock. MIT. No ROMs included. `fit/accuracy.py` regenerates SM64's table from its formula instead of copying it.
