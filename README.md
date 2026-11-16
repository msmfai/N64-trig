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
| Max \|s² + c² − 1\| | 1.7e-7 | |
| Instructions executed per sincos | 39–44 | 35–39 + sqrt |
| µs/frame saved vs Silas in HackerSM64 (ares), 3 code layouts | 46 / 75 / 66, mean 62 | 0 |

- **Kernel:** [`kernel/sincos.s`](kernel/sincos.s) (constants in one 16-byte cache line), or [`kernel/sincos_code.s`](kernel/sincos_code.s) (all constants built in code, no data). C macro: [`kernel/sincos.h`](kernel/sincos.h).
- **Sine or cosine alone:** `kernel/s5c6.s` / `s5c6_code.s` add `trig_sin` (cos is `trig_sin(angle + 0x4000)`) beside `trig_sincos`.
- **Not tested on a real N64.** ares charges flat cache-miss costs. Help with a console run is appreciated: `--hardware` builds never run the ares-only instructions and show results on the title screen.

Full report (accuracy, speed, checks, method, glossary): https://msmfai.github.io/N64-trig/

Reproduce (HackerSM64, clang 21, ares v148; `bench/hsm64-sincos.patch` converts the 13 functions that make 98% of sin/cos pairs to `sincoss()`):

```sh
python3 bench/build.py --baserom sm64.us.z64 [--clang BIN --binutils BIN] [--pad N] [--variants kernels sincos] [--hardware]
python3 bench/run.py [--variants kernels sincos] [--suffix=-padN]
```

`fit/fit.py` regenerates `fit/coeffs.h`. Fold: Silas Lock. Written with AI assistance (Claude). MIT. No ROMs included.
