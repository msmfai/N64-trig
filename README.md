**AI use:** I'm a mathematician: I designed the approximation (the polynomial forms, the fit, truncating c and f to 8 bits, the constants in one cache line) and directed the work. Claude (Anthropic's AI) wrote the code, assembly, benchmark and report. No art, models or music.

A folded polynomial joint sine / cosine kernel for the N64 (VR4300), more than 10x more accurate than Silas Lock's.

It uses a polynomial approximation of

    S(x) = x(a + x²(b + cx²))
    C(x) = 1 + x²(d + x²(e + fx²))

instead of Silas's

    C(x) = 1 + x²(a + bx²)
    S(x) = √(1 − C(x)²)

and makes it inexpensive with the use of brackets you can see; by truncating c and f to 8 bit so they fit on one line of assembly; and putting the remaining constants into one cache line.

| | This kernel | Silas |
|---|---|---|
| Max error | 1.45e-5 | 1.9e-4 |
| Max \|s² + c² − 1\| | 1.7e-7 | 7.1e-8 |
| Mean \|s² + c² − 1\| | 8.9e-10 | 1.7e-8 |
| Instructions executed per sincos | 39–44 | 35–39 + sqrt |
| µs/frame saved vs Silas in HackerSM64 (ares), 3 code layouts | 46 / 75 / 66, mean 62 | 0 |

## Two versions: one cache line, or pure code

The kernel comes in two versions. They use the same polynomial and give bit-identical results. The only difference is where four of the six constants come from.

| | [`kernel/sincos.s`](kernel/sincos.s): one cache line | [`kernel/sincos_code.s`](kernel/sincos_code.s): pure code |
|---|---|---|
| c, f and 1.0 | built with one `lui` each | built with one `lui` each |
| a, b, d, e | read from `trig_k`, one 16-byte data-cache line | built with `lui` + `ori` |
| Data | 16 bytes, 16-byte aligned | none |
| Instructions executed per sincos | 39–44 | 45–50 |
| µs/frame saved vs Silas, mean of 3 layouts | 62 | 66 |

**Why there are two:**
- The cache-line version runs 6 fewer instructions, but only if its line is already in the data cache. If the game has evicted the line, the call waits for RAM.
- The pure-code version can never miss on data. It costs 24 more bytes of instruction cache instead.
- On ares the two are tied: the gap is smaller than the ±3% that code layout alone moves results. ares charges a flat cost per cache miss and doesn't model RAM contention, so it can't say which one wins on a console. That is why both are kept until someone measures on hardware.
- The pure-code version is one self-contained file, with no `.rodata` to place or align. Use it if that is easier for your build.

C macro for either: [`kernel/sincos.h`](kernel/sincos.h).

## Details

- **Sine or cosine alone:** `kernel/s5c6.s` (cache line) / `s5c6_code.s` (pure code) add `trig_sin` (cos is `trig_sin(angle + 0x4000)`) beside `trig_sincos`.
- **Not tested on a real N64.** ares charges flat cache-miss costs. Help with a console run is appreciated: `--hardware` builds never run the ares-only instructions and show results on the title screen.

Full report (accuracy, speed, checks, method, glossary): https://msmfai.github.io/N64-trig/

Reproduce (HackerSM64, clang 21, ares v148; `bench/hsm64-sincos.patch` converts the 13 functions that make 98% of sin/cos pairs to `sincoss()`):

```sh
python3 bench/build.py --baserom sm64.us.z64 [--clang BIN --binutils BIN] [--pad N] [--variants kernels sincos] [--hardware]
python3 bench/run.py [--variants kernels sincos] [--suffix=-padN]
```

`fit/fit.py` regenerates `fit/coeffs.h`. Fold: Silas Lock. MIT. No ROMs included.
