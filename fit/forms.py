#!/usr/bin/env python3
"""Accuracy of smaller and larger polynomial forms, in exact float32.

  uv run --with numpy --with scipy python3 fit/forms.py [--out fit/forms.json]

Each form gives the sine and the cosine of x, the offset from the nearest
quarter turn (0 to 45 degrees, after the fold of kernel/*.s):

  SmCn      S = x(a1 + a3 x² + ...) up to x^m,  C = 1 + c2 x² + ... up to x^n
  Cn+sqrt   C as above, S = sqrt(1 − C²)           (Silas: C4+sqrt)
  Sm+sqrt   S as above, C = sqrt(1 − S²)

The coefficients are fitted in float64 (minimax of max(|S − sin|, |C − cos|)
on the octant), rounded to float32, and then evaluated as a kernel evaluates
them: Horner in x², float32 at every step, sqrt.s correctly rounded. All
metrics are over the 8193 octant steps of the binary angle. The fold maps
every other angle to one of these steps with a sign, so the metrics hold for
all 65,536 angles.

Variants: "free" (all coefficients float32) and "top 8-bit" (the highest
coefficient of each polynomial has 8 significant bits: one lui).
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
TG = np.linspace(0, 1, 513)                      # fit grid, t = x / 45°
Q = math.pi / 4
X = np.arange(0, 8193, dtype=np.float64)         # octant steps, binary-angle units
TH = X * math.pi / 32768
RS, RC = np.sin(TH), np.cos(TH)


def snap8(v):
    b = int(np.array([v], dtype=np.float32).view(np.uint32)[0])
    return float(np.array([(b + 0x8000) & 0xFFFF0000], dtype=np.uint32).view(np.float32)[0])


def spow(m):
    return list(range(1, m + 1, 2))              # 1, 3, 5, ...


def cpow(n):
    return list(range(2, n + 1, 2))              # 2, 4, 6, ...


def eval_t(kind, ns, nc, p, t):
    """float64 model on t in [0, 1]: -> (s, c)"""
    ks, kc = p[:len(spow(ns))], p[len(spow(ns)):]
    s = sum(k * t ** e for k, e in zip(ks, spow(ns))) if ns else None
    c = 1 + sum(k * t ** e for k, e in zip(kc, cpow(nc))) if nc else None
    if kind == 'csqrt':
        s = np.sqrt(np.maximum(1 - c * c, 0))
    elif kind == 'ssqrt':
        c = np.sqrt(np.maximum(1 - s * s, 0))
    return s, c


def lp_minimax(B, f, w=None, fixed=None):
    """Exact weighted linear minimax: min z, |w (B c - f)| <= z (HiGHS). fixed: {column: value}."""
    from scipy.optimize import linprog
    w = np.ones(len(f)) if w is None else w
    fixed = fixed or {}
    free = [j for j in range(B.shape[1]) if j not in fixed]
    r = f - sum((B[:, j] * v for j, v in fixed.items()), np.zeros(len(f)))
    Bf = B[:, free] * w[:, None]
    rw = r * w
    # variables: c_free..., z ; rows: Bf c - z <= rw, -Bf c - z <= -rw
    one = np.ones((len(f), 1))
    A = np.vstack([np.hstack([Bf, -one]), np.hstack([-Bf, -one])])
    b = np.concatenate([rw, -rw])
    cost = np.zeros(len(free) + 1)
    cost[-1] = 1
    res = linprog(cost, A_ub=A, b_ub=b, bounds=[(None, None)] * len(free) + [(0, None)], method='highs')
    c = np.zeros(B.shape[1])
    c[free] = res.x[:-1]
    for j, v in fixed.items():
        c[j] = v
    return c, res.x[-1]


def fit_side(pows, target, w=None, top8=False):
    B = np.stack([TG ** e for e in pows], 1)
    c, z = lp_minimax(B, target, w)
    if not top8:
        return c
    best = None
    t = len(pows) - 1
    base = int(np.array([snap8(c[t])], dtype=np.float32).view(np.uint32)[0])
    for k in range(-12, 13):                 # nearby 8-bit values of the top coefficient
        v = float(np.array([base + k * 0x10000], dtype=np.uint32).view(np.float32)[0])
        cc, zz = lp_minimax(B, target, w, {t: v})
        if best is None or zz < best[0]:
            best = (zz, cc)
    return best[1]


def fit(kind, ns, nc, top8):
    """Minimax coefficients in t units (exact LP), the top coefficient of each polynomial
    optionally 8-bit. Value error separates: S only depends on the sine coefficients."""
    st, ct = np.sin(Q * TG), np.cos(Q * TG)
    ps = fit_side(spow(ns), st, top8=top8) if kind in ('poly', 'ssqrt') else np.array([])
    if kind == 'poly':
        pc = fit_side(cpow(nc), ct - 1, top8=top8)
    elif kind == 'csqrt':
        # sin error = cos/sin * cos error (to first order): weighted minimax, weights from the
        # current fit, a few rounds
        w = np.ones(len(TG))
        for _ in range(4):
            pc = fit_side(cpow(nc), ct - 1, w, top8)
            c = 1 + sum(k * TG ** e for k, e in zip(pc, cpow(nc)))
            s = np.sqrt(np.maximum(1 - c * c, 1e-30))
            w = np.maximum(1, np.minimum(np.abs(c / s), 1e6))
    else:
        pc = np.array([])
    return np.concatenate([ps, pc])


def measure(kind, ns, nc, p):
    """float32 kernel evaluation over the octant: the metrics of the README."""
    f = np.float32
    ks = [f(k / 8192.0 ** e) for k, e in zip(p[:len(spow(ns))], spow(ns))]
    kc = [f(k / 8192.0 ** e) for k, e in zip(p[len(spow(ns)):], cpow(nc))]
    xf = X.astype(f)
    x2 = xf * xf
    s = c = None
    if ks:
        h = ks[-1]
        for k in reversed(ks[:-1]):
            h = h * x2 + k
        s = h * xf
    if kc:
        h = kc[-1]
        for k in reversed(kc[:-1]):
            h = h * x2 + k
        c = h * x2 + f(1)
    if kind == 'csqrt':
        s = np.sqrt(np.maximum(f(1) - c * c, f(0)))
    elif kind == 'ssqrt':
        c = np.sqrt(np.maximum(f(1) - s * s, f(0)))
    s, c = s.astype(np.float64), c.astype(np.float64)
    es, ec = np.abs(s - RS), np.abs(c - RC)
    u = s * s + c * c - 1
    d = np.abs(np.arctan2(s, c) - TH) * 65536 / (2 * math.pi)
    return {'max error': float(max(es.max(), ec.max())),
            'RMS error': float(math.sqrt((np.mean(es ** 2) + np.mean(ec ** 2)) / 2)),
            'max |s²+c²−1|': float(np.abs(u).max()), 'mean |s²+c²−1|': float(np.abs(u).mean()),
            'drift': float(u.mean()), 'max direction error': float(d.max()),
            'never above 1': bool(np.all(np.abs(s) <= 1) and np.all(np.abs(c) <= 1)),
            'coefficients': [int(np.array([v], dtype=np.float32).view(np.uint32)[0]) for v in ks + kc]}


FORMS = [('poly', 3, 2), ('poly', 3, 4), ('poly', 5, 4), ('poly', 5, 6), ('poly', 7, 6), ('poly', 7, 8),
         ('csqrt', 0, 2), ('csqrt', 0, 4), ('csqrt', 0, 6), ('csqrt', 0, 8),
         ('ssqrt', 3, 0), ('ssqrt', 5, 0), ('ssqrt', 7, 0)]


def name(kind, ns, nc):
    return {'poly': f'S{ns}C{nc}', 'csqrt': f'C{nc}+sqrt', 'ssqrt': f'S{ns}+sqrt'}[kind]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', type=Path, default=HERE / 'forms.json')
    args = ap.parse_args()
    out = {}
    for kind, ns, nc in FORMS:
        for top8 in (False, True):
            p = fit(kind, ns, nc, top8)
            m = measure(kind, ns, nc, p)
            key = name(kind, ns, nc) + (' top 8-bit' if top8 else '')
            out[key] = {'kind': kind, 'ns': ns, 'nc': nc, 'top8': top8, **m}
            print(f"{key:22} max err {m['max error']:9.2e}  max|U| {m['max |s²+c²−1|']:9.2e}  "
                  f"dir {m['max direction error']:6.2f}  >1 {'no' if m['never above 1'] else 'YES'}", flush=True)
    args.out.write_text(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
