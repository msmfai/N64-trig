#!/usr/bin/env python3
"""Pareto frontiers of value error against unit-scale error, for families of coefficient constraints.

  uv run --with numpy --with scipy --with matplotlib python3 fit/pareto.py [--out fit/pareto.png]

Form S5C6, with t = x / 45 degrees (t is 0 to 1):
  S = t(a + b t² + c t⁴),   C = 1 + d t² + e t⁴ + f t⁶

Families of constraints on the coefficients:
  free          a to f are real numbers
  c, f 8-bit    c and f have 8 significant bits (one lui each); a, b, d, e are float32
                (the published S5C6: one cache line, pure code)
  quantized     b, c, d, e, f have 8 significant bits; a is float32 (the published quantized version)
  all 8-bit     a to f have 8 significant bits (one lui each)
An 8-bit coefficient is a float32 with the low 16 bits zero. Scaling by a power
of two (the change to binary-angle units, 8192 = 2^13) keeps this property.

For each weight λ (1e-3 to 1e4), the script minimises max(E, λU) on the
folded range, where E = max(|S − sin|, |C − cos|) and U = max |S² + C² − 1|
(minimax, SLSQP, float64). Each λ gives one point; the points that no other
point beats in both E and U form the frontier. For a constrained family the
script runs a local search from three seeds (the free optimum, the published
kernel of the family, and the family's point at the previous weight): it
snaps the constrained coefficients to 8 bits, then moves one at a time to the
best of its 13 nearest 8-bit values, with the free coefficients solved again
each time, until a pass gives no gain. The curve is the best point found, an
upper bound of the true frontier of the family.

Each point is then measured on all 8193 octant steps (binary-angle units), in
exact arithmetic (solid lines) and as the kernel evaluates it in float32
(dashed lines: coefficients rounded to float32, Horner in x², float32 at each
step). Reference markers: the published kernels and Silas.
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
Q = math.pi / 4
T = np.linspace(0, 1, 513)                      # solver grid
SIN, COS = np.sin(Q * T), np.cos(Q * T)
BS = np.stack([T, T ** 3, T ** 5], 1)
BC = np.stack([T ** 2, T ** 4, T ** 6], 1)
POWER = [1, 3, 5, 2, 4, 6]
ORDER = [2, 5, 1, 4, 0, 3]                       # highest power first: c, f, b, e, a, d
FAMILIES = {
    'free': [],
    'c, f 8-bit (published S5C6)': [2, 5],
    'quantized: b, c, d, e, f 8-bit': [1, 2, 3, 4, 5],
    'all 8-bit (one lui each)': [0, 1, 2, 3, 4, 5],
}
X = np.arange(0, 8193, dtype=np.float64)        # the octant in binary-angle steps
TH = X * math.pi / 32768


def model(p):
    return BS @ p[:3], 1 + BC @ p[3:]


def errs(p):
    s, c = model(p)
    return s - SIN, c - COS, s * s + c * c - 1


def to_bits(v):
    return int(np.array([v], dtype=np.float32).view(np.uint32)[0])


def from_bits(b):
    return float(np.array([b & 0xFFFFFFFF], dtype=np.uint32).view(np.float32)[0])


def grid8(v, n=8):
    """8-significant-bit floats near v."""
    b = to_bits(v) & 0xFFFF0000
    return [from_bits(b + k * 0x10000) for k in range(-n, n + 1)]


def solve(p0, fixed, lam):
    """Minimise max(value error, lam * max|S²+C²−1|) over the free coefficients (solver grid).
    -> (coefficients, value error, unit-scale error, objective)"""
    free = [i for i in range(6) if i not in fixed]
    if not free:
        es, ec, eu = errs(p0)
        e, u = max(np.abs(es).max(), np.abs(ec).max()), np.abs(eu).max()
        return p0, e, u, max(e, lam * u)
    nf, zs = len(free), 1e-6

    def full(v):
        p = p0.copy()
        p[free] = v[:nf]
        return p

    def cons(v):
        es, ec, eu = errs(full(v))
        z = v[nf] * zs
        return np.concatenate([z - es, z + es, z - ec, z + ec, z - lam * eu, z + lam * eu]) / zs

    def jac(v):
        s, c = model(full(v))
        ds = np.hstack([BS, np.zeros_like(BC)])[:, free]
        dc = np.hstack([np.zeros_like(BS), BC])[:, free]
        du = 2 * s[:, None] * ds + 2 * c[:, None] * dc
        one, zero = np.ones((len(T), 1)) * zs, np.zeros((len(T), 1))
        return np.vstack([np.hstack([-ds, one]), np.hstack([ds, one]), np.hstack([-dc, one]),
                          np.hstack([dc, one]), np.hstack([-lam * du, one]), np.hstack([lam * du, one])]) / zs

    es, ec, eu = errs(p0)
    v0 = np.concatenate([p0[free], [max(np.abs(es).max(), np.abs(ec).max(), lam * np.abs(eu).max()) / zs * 1.01]])
    r = minimize(lambda v: v[nf], v0, jac=lambda v: np.eye(nf + 1)[nf], method='SLSQP',
                 constraints=[{'type': 'ineq', 'fun': cons, 'jac': jac}],
                 options={'maxiter': 300, 'ftol': 1e-14})
    p = full(r.x)
    es, ec, eu = errs(p)
    e, u = max(np.abs(es).max(), np.abs(ec).max()), np.abs(eu).max()
    return p, e, u, max(e, lam * u)


def minimax_free():
    """Separate minimax fits (Lawson IRLS): the free optimum without a unit-scale limit."""
    out = []
    for b, target in ((BS, SIN), (BC, COS - 1)):
        w = np.ones(len(T))
        for _ in range(300):
            sw = np.sqrt(w)
            coef = np.linalg.lstsq(b * sw[:, None], target * sw, rcond=None)[0]
            r = np.abs(b @ coef - target)
            w = w * (r + 1e-300)
            w /= w.sum()
        out.append(coef)
    return np.concatenate(out)


def measure(p):
    """(exact (U, E), float32 (U, E)) on all 8193 octant steps, binary-angle units."""
    kx = [p[i] / 8192.0 ** POWER[i] for i in range(6)]
    s = X * (kx[0] + X * X * (kx[1] + kx[2] * X * X))
    c = 1 + X * X * (kx[3] + X * X * (kx[4] + kx[5] * X * X))
    f = np.float32
    k32 = [f(v) for v in kx]
    xf = X.astype(f)
    x2 = xf * xf
    s32 = (((k32[2] * x2 + k32[1]) * x2 + k32[0]) * xf).astype(np.float64)
    c32 = (((k32[5] * x2 + k32[4]) * x2 + k32[3]) * x2 + f(1)).astype(np.float64)
    rs, rc = np.sin(TH), np.cos(TH)
    return tuple((float(np.abs(a * a + b * b - 1).max()), float(max(np.abs(a - rs).max(), np.abs(b - rc).max())))
                 for a, b in ((s, c), (s32, c32)))


def snap8(v):
    """The nearest 8-significant-bit float."""
    return from_bits((to_bits(v) + 0x8000) & 0xFFFF0000)


def family_search(seeds, fixed_set, lam, n=6, passes=3):
    """Local search over the 8-bit coefficients: from each seed, snap the constrained coefficients to
    8 bits, solve the free ones, then move one constrained coefficient at a time to the best of its
    2n+1 nearest 8-bit values (the free ones solved again each time), until a pass gives no gain.
    -> the best coefficients found"""
    fixed = [i for i in ORDER if i in fixed_set]
    best = None
    for seed in seeds:
        p = seed.copy()
        for i in fixed:
            p[i] = snap8(p[i])
        p, _, _, obj = solve(p, fixed, lam)
        for _ in range(passes):
            gain = False
            for i in fixed:
                for v in grid8(p[i], n):
                    if v == p[i]:
                        continue
                    q = p.copy()
                    q[i] = v
                    q, _, _, o = solve(q, fixed, lam)
                    if o < obj * (1 - 1e-9):
                        p, obj, gain = q, o, True
            if not gain:
                break
        if best is None or obj < best[1]:
            best = (p, obj)
    return best[0]


def pareto(pts):
    keep, best = [], math.inf
    for u, e in sorted(pts):
        if e < best:
            keep.append((u, e))
            best = e
    return keep


PUBLISHED = {'S5C6': (0x38c90dd0, 0xaa24fee4, 0x1a970000, 0xb19de6b5, 0x2280c3c2, 0x925d0000),
             'S5C6 quantized': (0x38c90f98, 0xaa250000, 0x1a940000, 0xb19e0000, 0x22860000, 0x932d0000)}


def published_t(name):
    """A published kernel's coefficients in t units (a to f)."""
    kx = [from_bits(b) for b in PUBLISHED[name]]          # S1 S3 S5 C2 C4 C6 in binary-angle units
    return np.array([kx[i] * 8192.0 ** POWER[i] for i in range(6)])


def references():
    out = {}
    for name, bits in (('S5C6', (0x38c90dd0, 0xaa24fee4, 0x1a970000, 0xb19de6b5, 0x2280c3c2, 0x925d0000)),
                       ('S5C6 quantized', (0x38c90f98, 0xaa250000, 0x1a940000, 0xb19e0000, 0x22860000, 0x932d0000))):
        kx = [from_bits(b) for b in bits]               # S1 S3 S5 C2 C4 C6 in binary-angle units
        p = np.array([kx[i] * 8192.0 ** POWER[i] for i in range(6)])
        ex, f32 = measure(p)
        out[f'{name}, exact'], out[f'{name}, float32'] = ex, f32
    c1, c2 = -0.0000000011485057369884462, 0.00000000000000000021380733869182293
    xs = 2 * X
    c = 1 + xs * xs * (c1 + c2 * xs * xs)
    s = np.sqrt(np.maximum(1 - c * c, 0))
    out['Silas, exact'] = (float(np.abs(s * s + c * c - 1).max()),
                           float(max(np.abs(s - np.sin(TH)).max(), np.abs(c - np.cos(TH)).max())))
    out['Silas, float32'] = (7.09e-08, 1.92e-04)        # fit/accuracy.py, all 65536 angles
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', type=Path, default=HERE / 'pareto.png')
    args = ap.parse_args()
    lams = [10 ** (k / 2) for k in range(-6, 9)]        # weight of the unit-scale error: 1e-3 to 1e4
    res = {f: {'exact': [], 'float32': [], 'coefficients': []} for f in FAMILIES}
    seed_pub = {'c, f 8-bit (published S5C6)': published_t('S5C6'),
                'quantized: b, c, d, e, f 8-bit': published_t('S5C6 quantized'),
                'all 8-bit (one lui each)': published_t('S5C6 quantized')}
    prev = {}
    p_free = minimax_free()
    for lam in lams:
        p_free = solve(p_free, [], lam)[0]
        for fam, fixed_set in FAMILIES.items():
            if not fixed_set:
                p = p_free
            else:
                seeds = [p_free, seed_pub[fam]] + ([prev[fam]] if fam in prev else [])
                p = prev[fam] = family_search(seeds, fixed_set, lam)
            ex, f32 = measure(p)
            res[fam]['exact'].append(ex)
            res[fam]['float32'].append(f32)
            res[fam]['coefficients'].append([to_bits(p[i] / 8192.0 ** POWER[i]) for i in range(6)])
        print(f'weight {lam:.2e} done', flush=True)
    refs = references()
    out = {f: {'exact': pareto(r['exact']), 'float32': pareto(r['float32']), 'all': r} for f, r in res.items()}
    args.out.with_suffix('.json').write_text(json.dumps({'families': out, 'references': refs}, indent=1))
    for f, r in out.items():
        for kind in ('exact', 'float32'):
            print(f'{f}, {kind}: ' + ', '.join(f'({u:.2e}, {e:.2e})' for u, e in r[kind]))
    for k, (u, e) in refs.items():
        print(f'{k:24} max|s²+c²−1| {u:9.2e}   max error {e:9.2e}')
    plot(out, refs, args.out)


def plot(out, refs, path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    xmin = 1e-9
    fig, ax = plt.subplots(figsize=(11, 6.5), dpi=150)
    colors = dict(zip(FAMILIES, ['#1f6fd1', '#2a9d4b', '#d17a1f', '#9b3fb5']))
    for f, r in out.items():
        for kind, ls, mk in (('exact', '-', '.'), ('float32', '--', 'x')):
            if not r[kind]:
                continue
            u, e = zip(*r[kind])
            ax.plot(u, e, ls, marker=mk, color=colors[f], lw=2 if kind == 'exact' else 1.3, ms=5,
                    label=f'{f}: {"exact arithmetic" if kind == "exact" else "float32 kernel"}')
    marks = {'S5C6': ('o', '#2a9d4b'), 'S5C6 quantized': ('s', '#d17a1f'), 'Silas': ('^', '#555555')}
    for k, (u, e) in refs.items():
        name, kind = k.rsplit(', ', 1)
        m, col = marks[name]
        if u == 0:
            ax.annotate('Silas, exact: max|s²+c²−1| = 0', xy=(xmin, e), xytext=(xmin * 1.6, e * 2.2),
                        color=col, fontsize=8, arrowprops={'arrowstyle': '->', 'color': col})
            ax.plot(xmin, e, '<', color=col, ms=9, mfc='none', label='Silas, exact (at 0, drawn at the edge)')
            continue
        ax.plot(u, e, m, color=col, ms=10, mfc=col if kind == 'float32' else 'none', mew=1.6,
                label=f'{name} (published), {kind}')
    for x, col, txt in ((7.09e-8, '#555555', 'Silas, float32'), (1.2e-7, '#999999', 'one float32 step near 1.0')):
        ax.axvline(x, color=col, ls=':', lw=1)
        ax.text(x, 1.3e-3, txt, color=col, fontsize=8, rotation=90, va='top', ha='right')
    ax.set_xscale('log')
    ax.set_yscale('log')
    ax.set_xlim(xmin * 0.7, 2e-4)
    ax.set_ylim(1e-7, 1.5e-3)
    ax.set_xlabel('max |s² + c² − 1|  (unit-scale error), over the octant')
    ax.set_ylabel('max |error| of sine and cosine, over the octant')
    ax.set_title('S5C6: value error against unit-scale error, by constraint on the coefficients')
    ax.grid(True, which='both', alpha=0.25)
    ax.legend(fontsize=8, loc='upper left', bbox_to_anchor=(1.01, 1.0), borderaxespad=0)
    fig.tight_layout()
    fig.savefig(path)
    print(f'plot: {path}')


if __name__ == '__main__':
    main()
