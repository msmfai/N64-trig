S5C6 sine/cosine for the N64 VR4300, benchmarked in HackerSM64 (clang 21) on ares v148. Not measured on a console. Summary: https://msmfai.github.io/N64-trig/

`kernel/s5c6.s` loads four constants from one 16-byte line; `kernel/s5c6_code.s` builds all constants in code. Identical results. Cosine is `trig_sin(angle + 0x4000)`, exact. `fit/fit.py` regenerates `fit/coeffs.h` (S5C6 = `BFS_*`).

| | S5C6 | Silas | SM64 table |
|---|---|---|---|
| Max error | 1.45e-5 | 1.9e-4 | 1.4e-3 |
| Instructions sin/cos | 24/27 line, 26/29 code | 28/25 + sqrt.s | ~4 inline (index, load) |
| Data | 16 B line, 0 code | 0 | 20 KB |
| Game-thread µs/frame | | | 12,050–12,640 |
| Calls − table, µs/frame (pad 0/1024/4096) | +107/−378/+221 line, +110/−396/+199 code | +61/−186/+234 | 0 (baseline) |
| Cycles per call, misses excluded | ~64 | ~72 | ~4 |

Benchmark: seven attract demos, 4304 frames, ~440 calls/frame. Table build (table refilled from the kernel) vs call build compute identical values; a position hash confirms identical gameplay. Kernel vs table is within code-layout noise; S5C6 is ~10% cheaper than Silas at every layout. ares charges flat miss costs and models no pipeline.

```sh
python3 bench/build.py --baserom sm64.us.z64 [--clang BIN --binutils BIN] [--pad N]
python3 bench/run.py [--suffix=-padN]
```

Fold: Silas Lock. Written with AI assistance (Claude). MIT. No ROMs included.
