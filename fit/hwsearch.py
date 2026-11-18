#!/usr/bin/env python3
"""Search S5C4 coefficients directly in float32, under the gameplay precision caps.

  uv run --with numpy --with scipy python3 fit/hwsearch.py [--out fit/hwsearch-S5C4.json]

Kernel: S = x(a + x²(b + c x²)), C = 1 + x²(d + e x²), x in binary-angle steps
(the fold of kernel/*.s), evaluated in float32 as the kernel does (Horner in
x², float32 at every step). The search changes the float32 bit patterns of
a to e directly and scores the exact kernel output; it never rounds an exact
fit afterwards.

Caps (accuracy beyond them changes nothing that a game computes):
  direction   the (cos, sin) pair points to the nearest binary angle: error under 0.5 steps
  creep       a rotation applied to its own result, one per frame, turning 0 to 6 degrees per frame
              (1 to 1092 steps): |s²+c²−1| no larger than for correctly rounded float32 sin and
              cos (6.0e-8, 0.054 units per minute at 1000 units, 30 frames per second)
  screen      max |s²+c²−1| at most 2e-5 (the rounding of the 16.16 matrices of the RSP)
  values      |sin|, |cos| never above 1 (exact at the quarter turns by construction)

Families (cheapest code last): free (a to e float32), top 8-bit (c and e with
one lui each), quantized (b, c, d, e 8-bit). For each, the search minimises
the creep; once the creep is at the cap, it minimises the max value error.
"""
import argparse
import json
import math
import random
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
F = np.float32
X = np.arange(0, 8193, dtype=np.float64)
TH = X * math.pi / 32768
RS, RC = np.sin(TH), np.cos(TH)
XF = X.astype(F)
X2 = XF * XF
SMALL = slice(1, 1093)                      # turns of 1 to 1092 steps: 0 to 6 degrees
CREEP_CAP = 6.0e-8
SCREEN_CAP = 2e-5
FAMILIES = {'free': [], 'top 8-bit': [2, 4], 'quantized': [1, 2, 3, 4]}


def f32(bits):
    return np.array(bits, dtype=np.uint32).view(F)


def kernel(bits):
    a, b, c, d, e = f32(bits)
    s = ((c * X2 + b) * X2 + a) * XF
    co = (e * X2 + d) * X2 + F(1)
    return s.astype(np.float64), co.astype(np.float64)


def metrics(bits):
    s, c = kernel(bits)
    u = s * s + c * c - 1
    d = np.abs(np.arctan2(s, c) - TH) * 65536 / (2 * math.pi)
    return {'creep U': float(np.abs(u[SMALL]).max()), 'max U': float(np.abs(u).max()),
            'mean U 0-6': float(np.abs(u[SMALL]).mean()), 'drift': float(u.mean()),
            'direction': float(d.max()), 'max error': float(max(np.abs(s - RS).max(), np.abs(c - RC).max())),
            'above 1': bool((np.abs(s) > 1).any() or (np.abs(c) > 1).any())}


def score(bits):
    m = metrics(bits)
    pen = 0.0
    if m['direction'] >= 0.5:
        pen += 10 + m['direction']
    if m['above 1']:
        pen += 10
    if m['max U'] > SCREEN_CAP:
        pen += 10 + m['max U'] / SCREEN_CAP
    creep = max(m['creep U'], CREEP_CAP) / CREEP_CAP     # 1 once at the cap
    # lexicographic: penalties, then creep (to the cap), then value error
    return (pen, creep, m['max error']), m


def snap8(bits):
    return (bits + 0x8000) & 0xFFFF0000


def seeds():
    """Taylor-consistent seeds: minimax sine, then d and e that cancel the x² and x⁴ terms of
    s² + c² − 1; plus the frontier points of fit/variants.py."""
    out = []
    import forms as FM
    for top8 in (False, True):
        p = FM.fit('poly', 5, 4, top8)                       # t units: a1 a3 a5 c2 c4
        a, b, c = p[0] / 8192, p[1] / 8192 ** 3, p[2] / 8192 ** 5
        d = -a * a / 2
        e = -(2 * a * b + d * d) / 2
        out.append([int(np.array([v], dtype=F).view(np.uint32)[0]) for v in (a, b, c, d, e)])
    v = json.loads((HERE / 'variants-S5C4.json').read_text())
    out += [r['coefficients'] for r in v.values()]
    return out


def search(start, fixed8, rng, iters=60):
    cur = list(start)
    for i in fixed8:
        cur[i] = snap8(cur[i])
    best, m = score(cur)
    steps = [1, 2, 4, 8, 16, 32, 64, 128, 256, 1024, 4096, 16384]
    for _ in range(iters):
        gain = False
        for i in range(5):
            unit = 0x10000 if i in fixed8 else 1
            for st in (steps[:4] if i in fixed8 else steps):
                for sgn in (1, -1):
                    cand = list(cur)
                    cand[i] = (cand[i] + sgn * st * unit) & 0xFFFFFFFF
                    sc, mm = score(cand)
                    if sc < best:
                        cur, best, m, gain = cand, sc, mm, True
        # paired moves of the coefficients that cancel each other in s² + c² − 1
        for (i, j) in ((0, 3), (1, 4), (0, 4)):
            for _ in range(40):
                cand = list(cur)
                for k in (i, j):
                    unit = 0x10000 if k in fixed8 else 1
                    cand[k] = (cand[k] + rng.choice([-1, 1]) * rng.choice([1, 2, 4, 16, 64]) * unit) & 0xFFFFFFFF
                sc, mm = score(cand)
                if sc < best:
                    cur, best, m, gain = cand, sc, mm, True
        if not gain:
            break
    return cur, best, m


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', type=Path, default=HERE / 'hwsearch-S5C4.json')
    ap.add_argument('--restarts', type=int, default=12)
    args = ap.parse_args()
    rng = random.Random(1)
    out = {}
    for fam, fixed8 in FAMILIES.items():
        best = None
        starts = seeds()
        for r in range(args.restarts):
            s0 = starts[r % len(starts)] if r < len(starts) else \
                [(b + rng.randint(-64, 64)) & 0xFFFFFFFF for b in best[0]]
            res = search(s0, fixed8, rng)
            if best is None or res[1] < best[1]:
                best = res
        bits, sc, m = best
        ok = sc[0] == 0 and m['creep U'] <= CREEP_CAP
        key = f'S5C4 {fam}, hardware caps'
        out[key] = {'kind': 'poly', 'ns': 5, 'nc': 4, 'family': fam, 'coefficients': bits, 'meets caps': ok,
                    **{k: v for k, v in m.items()}}
        print(f"{key:30} caps {'met' if ok else 'NOT met'}  creep U {m['creep U']:.2e} "
              f"(creep {m['creep U'] / 2 * 1000 * 1800:.3f} u/min)  max U {m['max U']:.2e}  "
              f"dir {m['direction']:.3f}  max error {m['max error']:.2e}  drift {m['drift']:+.1e}", flush=True)
    args.out.write_text(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
