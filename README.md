S5C6 sine/cosine for the N64 VR4300, benchmarked in HackerSM64 (clang 21) on ares v148. Not measured on a console. Full report: https://msmfai.github.io/N64-trig/

`kernel/s5c6.s` reads four constants from one 16-byte line; `kernel/s5c6_code.s` builds them in code. Both have `trig_sin` (cos is `trig_sin(angle + 0x4000)`) and `trig_sincos` (sin in $f0, cos in $f2). `fit/fit.py` regenerates `fit/coeffs.h`.

| | S5C6 line | S5C6 code | Silas | LUTX16 | SM64 table |
|---|---|---|---|---|---|
| Max error | 1.45e-5 | 1.45e-5 | 1.9e-4 | 6.4e-7 | 1.4e-3 |
| Data | 16 B | 0 | 0 | 544 B | 20 KB |
| Instructions executed, sin / sincos | 24–27 / 39–44 | 26–29 / 45–50 | 25–28 / 35–39, + sqrt | 34–35 / 48–54 | ~4 / ~8 |
| µs/frame vs table, separate calls | +77 | +92 | +75 | +137 | 0 |
| µs/frame vs table, sincos | −71 | −75 | −9 | −42 | 0 |

Means of 3 code layouts; layout alone moves results ±3%. Seven attract demos, ~440 calls/frame, game thread ~12,300 µs/frame. Every call build plays the same game as its table build. `bench/hsm64-sincos.patch` converts 13 functions (98% of sin/cos pairs) to `sincoss()`.

```sh
python3 bench/build.py --baserom sm64.us.z64 [--clang BIN --binutils BIN] [--pad N] [--variants kernels sincos] [--hardware]
python3 bench/run.py [--variants kernels sincos] [--suffix=-padN]
```

Fold: Silas Lock. Written with AI assistance (Claude). MIT. No ROMs included.
