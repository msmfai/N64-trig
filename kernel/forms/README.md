# Hand-written kernels of all forms

One file for each form and load style. Each file has `trig_sincos` and `trig_sin`
(the calling convention of the main README).

- `*_line.s`: the constants named in the `# LINE:` header are one 16-byte data line,
  `trig_k`, in that order (`ONE` is 1.0). The other constants are in the code.
- `*_code.s`: all constants are in the code. No data.

The coefficients are assembler symbols: assemble with `--defsym S1=0x...` (float32
bit patterns, binary-angle units; names in the `# COEFFICIENTS:` header). A constant
in the code is `lui`, plus `ori` only when its low 16 bits are not zero (`.if`).
Thus one file serves every coefficient set of its form (fit/sweep.py).

The fold is the one of kernel/s5c4_line.s, except the Q forms (quadrant fold).
