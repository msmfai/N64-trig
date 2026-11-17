#!/usr/bin/env python3
"""Accuracy of every sine/cosine in the README, over all 65536 binary angles.

  python3 fit/accuracy.py [--markdown]      (needs numpy)

Each method is evaluated in float32, operation by operation as its code does
it (kernel/*.s, bench/trig_kernels.s), so the figures are what the N64
returns. Reference: sin and cos of angle * 2*pi/65536 in float64.

SM64's sine table is float32(sin(i * 2*pi/4096)) for i = 0..5119 with exact
zeros at the half turns (checked entry for entry against the decompilation's
gSineTable); it is regenerated here, not copied. sins(a) reads entry a >> 4,
coss(a) entry (a >> 4) + 1024.
"""
import argparse
import math
import numpy as np

F = np.float32
U = np.arange(65536, dtype=np.int64)
REF_S = np.sin(U * (2 * math.pi / 65536))
REF_C = np.cos(U * (2 * math.pi / 65536))


def f32(bits):
    return np.array([bits], dtype=np.uint32).view(F)[0]


def table():
    i = np.arange(5120)
    t = np.sin(i * (2 * math.pi / 4096))
    t[np.abs(t) < 1e-12] = 0.0
    t = t.astype(F)
    return lambda a: t[(a & 0xFFFF) >> 4], lambda a: t[((a & 0xFFFF) >> 4) + 1024]


def silas():
    """Silas Lock's folded polynomial (bench/trig_impl.c TRIG_FUNC 1, the
    assembly in bench/trig_kernels.s TRIG_FUNC 4 is bit-identical to it)."""
    c1, c2 = F(-0.0000000011485057369884462), F(0.00000000000000000021380733869182293)

    def sin(a):
        a = (a & 0xFFFF).astype(np.int32)
        a = np.where(a >= 0x8000, a - 0x10000, a).astype(np.int32)
        shifter = (a ^ (a << 1)) & 0xC000
        x = (((a + shifter) << 17).astype(np.int32) >> 16).astype(F)
        x2 = x * x
        c = F(1) + x2 * (c1 + c2 * x2)
        s = np.where(shifter & 0x4000, c, np.sqrt(np.maximum(F(1) - c * c, F(0))).astype(F))
        return np.where(a < 0, -s, s).astype(F)
    return sin, lambda a: sin(a + 0x4000)


def s5c6(k):
    """S5C6 as in kernel/*.s: t = a + 0x2000, x = (t & 0x3FFF) - 0x2000;
    S = x(S1 + x2(S3 + S5 x2)), C = 1 + x2(C2 + x2(C4 + C6 x2)); bit 14 of t
    picks C, bit 15 negates."""
    s1, s3, s5, c2, c4, c6 = (f32(b) for b in k)

    def sin(a):
        t = (a & 0xFFFF) + 0x2000
        x = ((t & 0x3FFF) - 0x2000).astype(F)
        x2 = x * x
        s = ((s5 * x2 + s3) * x2 + s1) * x
        c = ((c6 * x2 + c4) * x2 + c2) * x2 + F(1)
        v = np.where(t & 0x4000, c, s)
        return np.where(t & 0x8000, -v, v).astype(F)
    return sin, lambda a: sin(a + 0x4000)


BFSK = (0x38c90dd0, 0xaa24fee4, 0x1a970000, 0xb19de6b5, 0x2280c3c2, 0x925d0000)
ONE = (0x38c90f98, 0xaa250000, 0x1a940000, 0xb19e0000, 0x22860000, 0x932d0000)

METHODS = [
    ('SM64 vanilla table', table()),
    ('Silas', silas()),
    ('S5C6 one cache line / pure code', s5c6(BFSK)),
    ('S5C6 one constant', s5c6(ONE)),
]


def measure(sin, cos):
    s = sin(U).astype(np.float64)
    c = cos(U).astype(np.float64)
    es, ec = np.abs(s - REF_S), np.abs(c - REF_C)
    e = s * s + c * c - 1
    # direction error: the angle the pair (c, s) points at, against the true one,
    # in binary-angle units (1/65536 turn)
    d = (np.arctan2(s, c) - U * (2 * math.pi / 65536) + math.pi) % (2 * math.pi) - math.pi
    d = np.abs(d) * 65536 / (2 * math.pi)
    neg = (-U) & 0xFFFF
    q = np.arange(0x4001)
    sq = sin(q).astype(np.float64)
    return {
        'max error': max(es.max(), ec.max()),
        'mean |error|': (es.mean() + ec.mean()) / 2,
        'RMS error': math.sqrt((np.mean(es ** 2) + np.mean(ec ** 2)) / 2),
        'max |s²+c²−1|': np.abs(e).max(),
        'mean |s²+c²−1|': np.abs(e).mean(),
        'mean s²+c²−1 (drift)': e.mean(),
        'max direction error (1/65536 turn)': d.max(),
        'exact at 0°, 90°, 180°, 270°': all(sin(np.array([0x0000, 0x4000, 0x8000, 0xC000])).astype(np.float64)
                                            == [0, 1, 0, -1])
                                        and all(cos(np.array([0x0000, 0x4000, 0x8000, 0xC000])).astype(np.float64)
                                                == [1, 0, -1, 0]),
        'sin(−a) = −sin(a), cos(−a) = cos(a), exactly': bool(np.all(s[neg] == -s) and np.all(c[neg] == c)),
        'sine never decreases from 0° to 90°': bool(np.all(np.diff(sq) >= 0)),
        'distinct sine values per turn': len(np.unique(s)),
    }


def fmt(v):
    if isinstance(v, (bool, np.bool_)):
        return 'yes' if v else 'no'
    if isinstance(v, (int, np.integer)):
        return f'{v:,}'
    if v == 0:
        return '0'
    if abs(v) >= 0.1:
        return f'{v:.2f}'
    return f'{v:+.1e}' if 'drift' in fmt.key else f'{v:.2e}'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--markdown', action='store_true', help='print a Markdown table')
    args = ap.parse_args()
    res = [(name, measure(*fns)) for name, fns in METHODS]
    keys = list(res[0][1])
    if args.markdown:
        print('| | ' + ' | '.join(n for n, _ in res) + ' |')
        print('|---' * (len(res) + 1) + '|')
        for k in keys:
            fmt.key = k
            label = k.replace('|', '\\|')
            print(f'| {label} | ' + ' | '.join(fmt(r[k]) for _, r in res) + ' |')
    else:
        for name, r in res:
            print(name)
            for k in keys:
                fmt.key = k
                print(f'  {k:46}{fmt(r[k])}')


if __name__ == '__main__':
    main()
