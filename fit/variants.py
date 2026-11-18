#!/usr/bin/env python3
"""Coefficient variants of one polynomial form, on the float32 frontier of value and unit-scale error.

  uv run --with numpy --with scipy python3 fit/variants.py --form S5C4 [--out fit/variants-S5C4.json]

Form SmCn: S = x(a1 + a3 x² + ...), C = 1 + c2 x² + ... (fit/forms.py).

Families of constraints (8-bit: 8 significant bits, one lui):
  free        all coefficients float32
  top 8-bit   the highest coefficient of each polynomial 8-bit
  quantized   all coefficients 8-bit except the x coefficient of the sine
  all 8-bit   all coefficients 8-bit

For each weight λ, the script minimises max(E, λU) with E = max(|S − sin|,
|C − cos|) and U = max |S² + C² − 1| (SLSQP, float64; for a constrained
family a local search over the nearby 8-bit values, as fit/pareto.py). It
then measures every result as the float32 kernel computes it (fit/forms.py
measure) and keeps the float32 frontier: no other result of the family is
better in both float32 E and float32 U.

Selected variants (written to the output for bench/micro/gen.py), for each
family: the smallest E, the smallest U, and the balance point (smallest
log E + log U).
"""
import argparse
import itertools
import json
import math
import re
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

import forms as F

HERE = Path(__file__).resolve().parent
T = F.TG
Q = F.Q
SIN, COS = np.sin(Q * T), np.cos(Q * T)


def basis(ns, nc):
    return np.stack([T ** e for e in F.spow(ns)], 1), np.stack([T ** e for e in F.cpow(nc)], 1)


def errs(p, BS, BC):
    s, c = BS @ p[:BS.shape[1]], 1 + BC @ p[BS.shape[1]:]
    return s - SIN, c - COS, s * s + c * c - 1


def solve(p0, fixed, lam, BS, BC):
    n = BS.shape[1] + BC.shape[1]
    free = [i for i in range(n) if i not in fixed]
    if not free:
        return p0
    zs = 1e-6
    D = np.hstack([BS, np.zeros_like(BC)]), np.hstack([np.zeros_like(BS), BC])

    def full(v):
        p = p0.copy()
        p[free] = v[:-1]
        return p

    def cons(v):
        es, ec, eu = errs(full(v), BS, BC)
        z = v[-1] * zs
        return np.concatenate([z - es, z + es, z - ec, z + ec, z - lam * eu, z + lam * eu]) / zs

    def jac(v):
        p = full(v)
        s, c = BS @ p[:BS.shape[1]], 1 + BC @ p[BS.shape[1]:]
        ds, dc = D[0][:, free], D[1][:, free]
        du = 2 * s[:, None] * ds + 2 * c[:, None] * dc
        one = np.ones((len(T), 1)) * zs
        return np.vstack([np.hstack([-ds, one]), np.hstack([ds, one]), np.hstack([-dc, one]),
                          np.hstack([dc, one]), np.hstack([-lam * du, one]), np.hstack([lam * du, one])]) / zs

    es, ec, eu = errs(p0, BS, BC)
    z0 = max(np.abs(es).max(), np.abs(ec).max(), lam * np.abs(eu).max()) / zs * 1.01
    r = minimize(lambda v: v[-1], np.concatenate([p0[free], [z0]]), jac=lambda v: np.eye(len(free) + 1)[-1],
                 method='SLSQP', constraints=[{'type': 'ineq', 'fun': cons, 'jac': jac}],
                 options={'maxiter': 400, 'ftol': 1e-15})
    return full(r.x)


def obj(p, lam, BS, BC):
    es, ec, eu = errs(p, BS, BC)
    return max(np.abs(es).max(), np.abs(ec).max(), lam * np.abs(eu).max())


def grid8(v, k):
    b = int(np.array([F.snap8(v)], dtype=np.float32).view(np.uint32)[0])
    return float(np.array([b + k * 0x10000], dtype=np.uint32).view(np.float32)[0])


def local8(seed, fixed, lam, BS, BC, n=6, passes=3):
    p = seed.copy()
    for i in fixed:
        p[i] = F.snap8(p[i])
    p = solve(p, fixed, lam, BS, BC)
    best = obj(p, lam, BS, BC)
    for _ in range(passes):
        gain = False
        for i in fixed:
            for k in range(-n, n + 1):
                if k == 0:
                    continue
                q = p.copy()
                q[i] = grid8(p[i], k)
                q = solve(q, fixed, lam, BS, BC)
                o = obj(q, lam, BS, BC)
                if o < best * (1 - 1e-9):
                    p, best, gain = q, o, True
        if not gain:
            break
    return p, best


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--form', default='S5C4')
    ap.add_argument('--out', type=Path)
    args = ap.parse_args()
    m = re.fullmatch(r'S(\d)C(\d)', args.form)
    ns, nc = int(m.group(1)), int(m.group(2))
    BS, BC = basis(ns, nc)
    nsc, ncc = BS.shape[1], BC.shape[1]
    n = nsc + ncc
    tops = [nsc - 1, n - 1]
    fams = {'free': [], 'top 8-bit': tops, 'quantized': list(range(1, n)), 'all 8-bit': list(range(n))}
    lams = [10 ** (k / 3) for k in range(-9, 13)]           # 1e-3 to 1e4
    start = np.concatenate([F.fit('poly', ns, nc, False)])
    results = {f: [] for f in fams}
    prev = {}
    for lam in lams:
        pf = solve(prev.get('free', start), [], lam, BS, BC)
        prev['free'] = pf
        for fam, fixed in fams.items():
            if not fixed:
                p = pf
            else:
                seeds = [pf] + ([prev[fam]] if fam in prev else [])
                p = min((local8(s, fixed, lam, BS, BC) for s in seeds), key=lambda r: r[1])[0]
                prev[fam] = p
            meas = F.measure('poly', ns, nc, p)
            results[fam].append({'lambda': lam, **meas})
        print(f'λ {lam:.2e} done', flush=True)
    out = {}
    for fam, rs in results.items():
        front = []
        for r in rs:
            if not any(o['max error'] <= r['max error'] and o['max |s²+c²−1|'] <= r['max |s²+c²−1|'] and
                       (o['max error'] < r['max error'] or o['max |s²+c²−1|'] < r['max |s²+c²−1|']) for o in rs):
                if not any(r['coefficients'] == f['coefficients'] for f in front):
                    front.append(r)
        front.sort(key=lambda r: r['max |s²+c²−1|'])
        picks = {'min E': min(front, key=lambda r: r['max error']),
                 'min U': min(front, key=lambda r: r['max |s²+c²−1|']),
                 'balance': min(front, key=lambda r: math.log(r['max error']) + math.log(r['max |s²+c²−1|']))}
        print(f'\n{fam}: float32 frontier')
        for r in front:
            print(f"  E {r['max error']:.2e}  U {r['max |s²+c²−1|']:.2e}  drift {r['drift']:+.1e}  "
                  f"dir {r['max direction error']:.3f}")
        for what, r in picks.items():
            key = f'{args.form} {fam}, {what}'
            if any(v['coefficients'] == r['coefficients'] for v in out.values()):
                continue
            out[key] = {'kind': 'poly', 'ns': ns, 'nc': nc, 'top8': fam != 'free', 'family': fam, **r}
    path = args.out or HERE / f'variants-{args.form}.json'
    path.write_text(json.dumps(out, indent=1))
    print(f'\n{len(out)} variants -> {path}')


if __name__ == '__main__':
    main()
