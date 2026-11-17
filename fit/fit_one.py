#!/usr/bin/env python3
"""Fit the "one constant" S5C6 coefficients (kernel/s5c6_one.s, sincos_one.s).

  python3 fit/fit_one.py [--table]      (needs numpy; about a minute)

The constraint: every coefficient except S1 has 8 significant bits (low 16
bits of the float zero), so it is built with one lui and no data is read.
S1 keeps full precision (lui + ori). The fit minimises the maximum value
error, sine and cosine separately (each polynomial only sees its own
coefficients): a Remez-style minimax fit of all coefficients, then each one in
turn is rounded to its allowed grid (nearby grid points searched exhaustively)
and the remaining ones refitted. Errors are then checked in float32 with the
kernel's own operation order over all 8193 angles of the octant.

Unlike fit.py's S5C6 it is not fitted jointly, so s^2 + c^2 - 1 is not pinned
to zero on average and the two polynomials do not meet exactly at 45 degrees.

--table: the same search for every choice of full-precision coefficients
(0 to 6 of them), best per count: what each extra lui + ori buys.
"""
import argparse
import itertools
import math
import numpy as np

F = np.float32
X = np.arange(0, 8193, dtype=np.float64)       # |x| in binary-angle units, 0 to 45 degrees
T = X / 8192
TH = X * math.pi / 32768
NAMES = ['S1', 'S3', 'S5', 'C2', 'C4', 'C6']


def bits(v):
    return int(np.array([v], dtype=F).view(np.uint32)[0])


def from_bits(b):
    return float(np.array([b & 0xFFFFFFFF], dtype=np.uint32).view(F)[0])


def grid(v, n):
    """8-significant-bit floats around v, n steps either side."""
    b = bits(v) & 0xFFFF0000
    return [from_bits(b + k * 0x10000) for k in range(-n, n + 1)]


def minimax(powers, target):
    """Lawson's iteratively reweighted least squares: near-minimax coefficients (x units)."""
    B = np.stack([T ** p for p in powers], 1)
    w = np.ones(len(T))
    for _ in range(150):
        sw = np.sqrt(w)
        c = np.linalg.lstsq(B * sw[:, None], target * sw, rcond=None)[0]
        r = np.abs(B @ c - target)
        w = w * (r + 1e-30)
        w /= w.sum()
    return [ci / 8192.0 ** p for ci, p in zip(c, powers)]


def fit_side(powers, target, full):
    """Coefficients for one polynomial; full[i]: coefficient i keeps 24 bits."""
    span = [8, 12, 30]
    best = [None]

    def rec(i, resid, chosen):
        c0 = minimax(powers[i:], resid)[0]
        cands = [from_bits(bits(c0) + k) for k in (-1, 0, 1)] if full[i] else grid(c0, span[i])
        xp = X ** powers[i]
        for c in cands:
            r = resid - c * xp
            if i == len(powers) - 1:
                e = np.max(np.abs(r))
                if best[0] is None or e < best[0][0]:
                    best[0] = (e, chosen + [c])
            else:
                rec(i + 1, r, chosen + [c])
    rec(0, target, [])
    return best[0][1]


def check(k):
    """Float32, the kernel's operation order, over the octant."""
    s1, s3, s5, c2, c4, c6 = (F(v) for v in k)
    xf = X.astype(F)
    x2 = xf * xf
    s = (((s5 * x2 + s3) * x2 + s1) * xf).astype(np.float64)
    c = (((c6 * x2 + c4) * x2 + c2) * x2 + F(1)).astype(np.float64)
    return (np.max(np.abs(s - np.sin(TH))), np.max(np.abs(c - np.cos(TH))),
            np.max(np.abs(s * s + c * c - 1)))


def fit(full_mask):
    s = fit_side([1, 3, 5], np.sin(TH), full_mask[:3])
    c = fit_side([2, 4, 6], np.cos(TH) - 1, full_mask[3:])
    return s + c


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--table', action='store_true', help='best fit for every count of full-precision coefficients')
    args = ap.parse_args()
    if args.table:
        sides = {}
        for m in itertools.product([0, 1], repeat=3):
            sides['s', m] = fit_side([1, 3, 5], np.sin(TH), m)
            sides['c', m] = fit_side([2, 4, 6], np.cos(TH) - 1, m)
        rows = []
        for ms in itertools.product([0, 1], repeat=3):
            for mc in itertools.product([0, 1], repeat=3):
                k = sides['s', ms] + sides['c', mc]
                es, ec, el = check(k)
                rows.append((sum(ms + mc), max(es, ec), el, [n for n, b in zip(NAMES, ms + mc) if b], k))
        print('full  max error  max|s2+c2-1|  full-precision coefficients')
        for n in range(7):
            r = min((r for r in rows if r[0] == n), key=lambda r: r[1])
            print(f'{n:4}  {r[1]:9.2e}  {r[2]:12.2e}  {",".join(r[3]) or "none"}   '
                  + ' '.join(f'{bits(v):08x}' for v in r[4]))
        return
    k = fit((1, 0, 0, 0, 0, 0))
    es, ec, el = check(k)
    for n, v in zip(NAMES, k):
        print(f'{n} = 0x{bits(v):08x}  {float(F(v))!r}')
    print(f'max error: sine {es:.2e}, cosine {ec:.2e}; max |s^2+c^2-1| {el:.2e}')


if __name__ == '__main__':
    main()
