#!/usr/bin/env python3
"""Coefficient sweep of every kernel form, in float32 bit patterns.

  uv run --with numpy --with scipy python3 fit/sweep.py [--forms S3C2 S5C4 ...] [--out fit/sweep.json]

The search changes the float32 bit patterns of the coefficients and scores the
exact float32 output of the hand-written kernel (the same operations in the
same order). It never rounds an exact fit afterwards.

Forms (x: binary-angle units; the octant fold of kernel/*.s gives |x| <= 0x2000):
  SmCn     S = x(s1 + x²(s3 + ...)), C = 1 + x²(c2 + x²(c4 + ...))    two polynomials
  Cn+sqrt  C as above, S = sqrt(1 - C²)                               one polynomial and a square root
  Sm+sqrt  S as above, C = sqrt(1 - S²)
  Qm       sin = x(q1 + x²(q3 + ...)) on the quadrant fold, |x| <= 0x4000; cos = sin(a + 0x4000)
  Tm       u = x(t1 + x²(t3 + ...)) (u is near tan(x/2)); d = 1/(1 + u²); S = 2u d, C = (1 - u²) d

Families (an 8-bit coefficient has its low 16 bits zero: one lui):
  free        all float32
  top 8-bit   the highest coefficient of each polynomial 8-bit
  quantized   all 8-bit except the first coefficient
  all 8-bit   all 8-bit

Points of each form and family:
  E/U weight w (12 values): minimise max(E, w U), E = max value error, U = max |s² + c² − 1|.
  limits: the gameplay limits of fit/hwsearch.py (direction < 0.5 steps, creep U <= 6.0e-8
          for turns of 0 to 6 degrees, max U <= 2e-5, never above 1); within them, the
          smallest creep, then the smallest E. "meets limits" is false if the search finds
          no point within them.
"""
import argparse
import json
import math
import random
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
F = np.float32
CREEP_CAP, SCREEN_CAP = 6.0e-8, 2e-5
FAMILIES = ['free', 'top 8-bit', 'quantized', 'all 8-bit']
WEIGHTS = [10.0 ** e for e in np.linspace(-1, 4, 12)]

# octant grid (two-polynomial, sqrt and T forms) and quadrant grid (Q forms)
XO = np.arange(0, 8193, dtype=np.float64)
XQ = np.arange(0, 16385, dtype=np.float64)
THO = XO * math.pi / 32768
RSO, RCO = np.sin(THO), np.cos(THO)


def spec(name):
    """'S5C4' -> ('poly', [1,3,5], [2,4]); 'C4+sqrt' -> ('csqrt', [], [2,4]); 'Q7' -> ('quad', [1,3,5,7], [])"""
    if name.endswith('+sqrt'):
        n = int(name[1:-5])
        return ('csqrt', [], list(range(2, n + 1, 2))) if name[0] == 'C' else ('ssqrt', list(range(1, n + 1, 2)), [])
    if name[0] in 'QT':
        return ('quad' if name[0] == 'Q' else 'tan', list(range(1, int(name[1:]) + 1, 2)), [])
    m, n = name[1:].split('C')
    return 'poly', list(range(1, int(m) + 1, 2)), list(range(2, int(n) + 1, 2))


def fixed8(name, family):
    kind, sp, cp = spec(name)
    n = len(sp) + len(cp)
    if family == 'free':
        return []
    if family == 'all 8-bit':
        return list(range(n))
    if family == 'quantized':
        return list(range(1, n))
    tops = []
    if sp:
        tops.append(len(sp) - 1)
    if cp:
        tops.append(n - 1)
    return tops


def f32(bits):
    return np.array(bits, dtype=np.uint32).view(F)


def horner(ks, x2):
    h = ks[-1] * np.ones_like(x2)
    for k in ks[-2::-1]:
        h = h * x2 + k
    return h


def outputs(name, bits):
    """float32 (s, c) on the octant grid (for Q forms: from the quadrant polynomial), as float64."""
    kind, sp, cp = spec(name)
    k = f32(bits)
    ks, kc = k[:len(sp)], k[len(sp):]
    if kind == 'quad':
        x = XQ.astype(F)
        p = horner(ks, x * x) * x                      # sin on 0 .. 90 degrees
        s, c = p[:8193], p[16384:16384 - 8193:-1]       # cos(x) = sin(90 degrees - x)
        return s.astype(np.float64), c.astype(np.float64)
    x = XO.astype(F)
    x2 = x * x
    if kind == 'tan':
        u = horner(ks, x2) * x
        u2 = u * u
        d = F(1) / (F(1) + u2)
        s, c = (u + u) * d, (F(1) - u2) * d
    else:
        s = horner(ks, x2) * x if len(ks) else None
        c = horner(kc, x2) * x2 + F(1) if len(kc) else None
        if kind == 'csqrt':
            s = np.sqrt(np.maximum(F(1) - c * c, F(0)))
        elif kind == 'ssqrt':
            c = np.sqrt(np.maximum(F(1) - s * s, F(0)))
    return s.astype(np.float64), c.astype(np.float64)


def valid(bits):
    """normal float32 coefficients only: a denormal, an infinity or a NaN operand traps on the VR4300"""
    return all(((b >> 23) & 0xFF) not in (0, 0xFF) for b in bits)


def metrics(name, bits):
    if not valid(bits):
        return {'max error': math.inf, 'max U': math.inf, 'creep U': math.inf, 'direction': math.inf,
                'drift': math.inf, 'above 1': True, 'invalid': True}
    with np.errstate(all='ignore'):
        s, c = outputs(name, bits)
    if not (np.isfinite(s).all() and np.isfinite(c).all()):
        return {'max error': math.inf, 'max U': math.inf, 'creep U': math.inf, 'direction': math.inf,
                'drift': math.inf, 'above 1': True, 'invalid': True}
    u = s * s + c * c - 1
    d = np.abs(np.arctan2(s, c) - THO) * 65536 / (2 * math.pi)
    return {'max error': float(max(np.abs(s - RSO).max(), np.abs(c - RCO).max())),
            'max U': float(np.abs(u).max()), 'creep U': float(np.abs(u[1:1093]).max()),
            'direction': float(d.max()), 'drift': float(u.mean()),
            'above 1': bool((np.abs(s) > 1).any() or (np.abs(c) > 1).any())}


def score_w(m, w):
    if m.get('invalid'):
        return (math.inf, math.inf, math.inf)
    return (10.0 if m['above 1'] else 0.0, max(m['max error'], w * m['max U']), m['max error'])


def score_limits(m):
    if m.get('invalid'):
        return (math.inf, math.inf, math.inf)
    pen = (10 + m['direction'] if m['direction'] >= 0.5 else 0) + (10 if m['above 1'] else 0) + \
          (10 + m['max U'] / SCREEN_CAP if m['max U'] > SCREEN_CAP else 0)
    return (pen, max(m['creep U'], CREEP_CAP) / CREEP_CAP, m['max error'])


def snap(bits, fixed):
    return [((b + 0x8000) & 0xFFFF0000) if i in fixed else b for i, b in enumerate(bits)]


def search(name, start, fixed, score, rng, iters=80):
    cur = snap(start, fixed)
    best_m = metrics(name, cur)
    best = score(best_m)
    steps = [1, 2, 4, 8, 16, 32, 64, 128, 256, 1024, 4096, 16384, 65536]
    n = len(cur)
    for _ in range(iters):
        gain = False
        for i in range(n):
            unit = 0x10000 if i in fixed else 1
            for st in (steps[:5] if i in fixed else steps):
                for sg in (1, -1):
                    cand = list(cur)
                    cand[i] = (cand[i] + sg * st * unit) & 0xFFFFFFFF
                    m = metrics(name, cand)
                    sc = score(m)
                    if sc < best:
                        cur, best, best_m, gain = cand, sc, m, True
        for i in range(n):                     # paired moves: neighbouring coefficients compensate
            for j in range(i + 1, n):
                for _ in range(12):
                    cand = list(cur)
                    for k in (i, j):
                        unit = 0x10000 if k in fixed else 1
                        cand[k] = (cand[k] + rng.choice([-1, 1]) * rng.choice([1, 2, 4, 16, 64, 256]) * unit) \
                            & 0xFFFFFFFF
                    m = metrics(name, cand)
                    sc = score(m)
                    if sc < best:
                        cur, best, best_m, gain = cand, sc, m, True
        if not gain:
            break
    return cur, best, best_m


def to_bits(v):
    return int(np.array([v], dtype=F).view(np.uint32)[0])


def seeds(name):
    """Linear minimax fits (float64, scipy HiGHS) in binary-angle units."""
    from scipy.optimize import linprog
    kind, sp, cp = spec(name)

    def lp(pows, x, target, w=None):
        B = np.stack([x ** e for e in pows], 1)
        w = np.ones(len(x)) if w is None else w
        one = np.ones((len(x), 1))
        A = np.vstack([np.hstack([B * w[:, None], -one]), np.hstack([-B * w[:, None], -one])])
        b = np.concatenate([target * w, -target * w])
        cost = np.zeros(len(pows) + 1)
        cost[-1] = 1
        r = linprog(cost, A_ub=A, b_ub=b, bounds=[(None, None)] * len(pows) + [(0, None)], method='highs')
        return list(r.x[:-1])

    t = np.linspace(0, 1, 801)
    out = []
    for prev in (f'hwsearch-{name}.json', f'variants-{name}.json'):    # earlier searches of the same form
        if (HERE / prev).exists():
            out += [v['coefficients'] for v in json.loads((HERE / prev).read_text()).values()]
    if kind == 'quad':
        x = t * 16384
        sc = [16384.0 ** -e for e in sp]
        ks = lp(sp, t, np.sin(t * math.pi / 2))
        out.append([to_bits(k * s) for k, s in zip(ks, sc)])
        return out
    x = t * 8192
    sco = [8192.0 ** -e for e in sp]
    scc = [8192.0 ** -e for e in cp]
    if kind == 'tan':
        ks = lp(sp, t, np.tan(t * math.pi / 8))
        out.append([to_bits(k * s) for k, s in zip(ks, sco)])
        return out
    ks = lp(sp, t, np.sin(t * math.pi / 4)) if sp else []
    kc = lp(cp, t, np.cos(t * math.pi / 4) - 1) if cp else []
    out.append([to_bits(k * s) for k, s in zip(ks, sco)] + [to_bits(k * s) for k, s in zip(kc, scc)])
    if kind == 'poly' and len(sp) >= 2 and len(cp) >= 2:
        a, b = ks[0] / 8192, ks[1] / 8192 ** 3          # Taylor-consistent cosine: cancels x² and x⁴ of U
        d = -a * a / 2
        e = -(2 * a * b + d * d) / 2
        kc2 = [d, e] + [k * s for k, s in zip(kc[2:], scc[2:])]
        out.append([to_bits(k * s) for k, s in zip(ks, sco)] + [to_bits(v) for v in kc2])
    return out


TG = np.linspace(0, 1, 241)


def scale(name):
    """binary-angle units per unit of t: 8192 (octant) or 16384 (quadrant)"""
    return 16384.0 if spec(name)[0] == 'quad' else 8192.0


def model64(name, p, t):
    """float64 model on t in [0, 1] (t = x / scale): -> (s, c, reference s, reference c)"""
    kind, sp, cp = spec(name)
    ks, kc = p[:len(sp)], p[len(sp):]
    poly = lambda k, pw: sum(a * t ** e for a, e in zip(k, pw))
    if kind == 'quad':
        th = t * math.pi / 2
        s, c = poly(ks, sp), poly(ks, [e for e in sp]) * 0
        c = sum(a * (1 - t) ** e for a, e in zip(ks, sp))      # cos(x) = sin(90 degrees - x)
        return s, c, np.sin(th), np.cos(th)
    th = t * math.pi / 4
    if kind == 'tan':
        u = poly(ks, sp)
        d = 1 / (1 + u * u)
        return 2 * u * d, (1 - u * u) * d, np.sin(th), np.cos(th)
    s = poly(ks, sp) if len(ks) else None
    c = 1 + poly(kc, cp) if len(kc) else None
    if kind == 'csqrt':
        s = np.sqrt(np.maximum(1 - c * c, 1e-30))
    elif kind == 'ssqrt':
        c = np.sqrt(np.maximum(1 - s * s, 1e-30))
    return s, c, np.sin(th), np.cos(th)


def to_t(name, bits):
    kind, sp, cp = spec(name)
    sc = scale(name)
    return [float(v) * sc ** e for v, e in zip(f32(bits), sp + cp)]


def to_xbits(name, p):
    kind, sp, cp = spec(name)
    sc = scale(name)
    return [to_bits(v / sc ** e) for v, e in zip(p, sp + cp)]


def solve64(name, p0, w, fixed_vals):
    """min z: |s - sin|, |c - cos|, w |s² + c² - 1| <= z on TG (SLSQP, float64); fixed_vals: {index: value}"""
    from scipy.optimize import minimize
    free = [i for i in range(len(p0)) if i not in fixed_vals]

    def full(v):
        p = list(p0)
        for i, j in enumerate(free):
            p[j] = v[i]
        for j, val in fixed_vals.items():
            p[j] = val
        return p

    def res(v):
        s, c, rs, rc = model64(name, full(v[:-1]), TG)
        return np.concatenate([s - rs, c - rc, w * (s * s + c * c - 1)])

    if not free:
        return full([])
    v0 = [p0[j] for j in free]
    r0 = np.abs(res(v0 + [0])).max()
    cons = [{'type': 'ineq', 'fun': lambda v: v[-1] - res(v)}, {'type': 'ineq', 'fun': lambda v: v[-1] + res(v)}]
    sc = np.array([max(abs(x), 1e-30) for x in v0] + [max(r0, 1e-30)])
    obj = lambda y: y[-1]
    cons_s = [{'type': c['type'], 'fun': (lambda f: lambda y: f(y * sc) / sc[-1])(c['fun'])} for c in cons]
    r = minimize(obj, np.ones(len(sc)), constraints=cons_s, method='SLSQP', options={'maxiter': 300, 'ftol': 1e-12})
    return full(list(r.x[:-1] * sc[:-1]))


def continuous(name, w, fixed, start_bits):
    """float64 fit for weight w; the fixed (8-bit) coefficients snapped one at a time, the others re-fitted"""
    p = solve64(name, to_t(name, start_bits), w, {})
    vals = {}
    for i in sorted(fixed, key=lambda i: -i):                  # highest powers first
        b = (to_xbits(name, p)[i] + 0x8000) & 0xFFFF0000
        best = None
        for k in (-2, -1, 0, 1, 2):
            v = to_t(name, [0] * i + [(b + k * 0x10000) & 0xFFFFFFFF] + [0] * (len(p) - i - 1))[i]
            q = solve64(name, p, w, {**vals, i: v})
            s, c, rs, rc = model64(name, q, TG)
            z = max(np.abs(s - rs).max(), np.abs(c - rc).max(), w * np.abs(s * s + c * c - 1).max())
            if best is None or z < best[0]:
                best = (z, v, q)
        vals[best[1:2] and i] = best[1]
        p = best[2]
    return to_xbits(name, p)


def sweep(name, restarts, rng):
    res = {}
    for fam in FAMILIES:
        fixed = fixed8(name, fam)
        if fam == 'top 8-bit' and len(fixed) == len(spec(name)[1]) + len(spec(name)[2]):
            continue                            # equal to all 8-bit
        pts = []
        start = seeds(name)
        prev = None
        for w in WEIGHTS:
            score = lambda m, w=w: score_w(m, w)
            best = None
            cont = []
            for s0 in start + ([prev] if prev else []):
                try:
                    cont.append(continuous(name, w, fixed, s0))
                except Exception:                              # a failed SLSQP run: the bit search alone
                    pass
            for s0 in start + cont + ([prev] if prev else []):
                r = search(name, s0, fixed, score, rng)
                if best is None or r[1] < best[1]:
                    best = r
            prev = best[0]
            if best[2].get('invalid'):
                continue                       # no valid point for this weight
            pts.append({'label': f'w={w:.3g}', 'coefficients': best[0], **best[2]})
        best = None
        cands = start + [p['coefficients'] for p in pts]
        for r in range(restarts):
            s0 = cands[r % len(cands)] if r < len(cands) else \
                [(b + rng.randint(-64, 64) * (0x10000 if i in fixed else 1)) & 0xFFFFFFFF
                 for i, b in enumerate(best[0])]
            rr = search(name, s0, fixed, score_limits, rng)
            if best is None or rr[1] < best[1]:
                best = rr
        m = best[2]
        ok = best[1][0] == 0 and m['creep U'] <= CREEP_CAP
        pts.append({'label': 'limits', 'coefficients': best[0], 'meets limits': ok, **m})
        res[fam] = pts
        lim = pts[-1]
        print(f"{name:8} {fam:10} limits {'met' if ok else 'not met':7} E {lim['max error']:.2e} "
              f"U {lim['max U']:.2e} creep {lim['creep U']:.2e} dir {lim['direction']:.2f} | "
              f"E range {min(p['max error'] for p in pts):.1e}..{max(p['max error'] for p in pts):.1e}", flush=True)
    return res


# Q9 is not in the list: in binary-angle units its x^9 coefficient is below the smallest normal float32.
ALL = ['S3C2', 'S3C4', 'S5C4', 'S5C6', 'S7C6', 'S7C8', 'C2+sqrt', 'C4+sqrt', 'C6+sqrt', 'S3+sqrt', 'S5+sqrt',
       'Q5', 'Q7', 'T3', 'T5', 'T7']


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--forms', nargs='+', default=ALL)
    ap.add_argument('--restarts', type=int, default=24)
    ap.add_argument('--out', type=Path, default=HERE / 'sweep.json')
    args = ap.parse_args()
    out = json.loads(args.out.read_text()) if args.out.exists() else {}
    for name in args.forms:
        out[name] = sweep(name, args.restarts, random.Random(1))
        args.out.write_text(json.dumps(out, indent=1))          # saved after each form


if __name__ == '__main__':
    main()
