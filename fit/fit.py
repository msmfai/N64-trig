#!/usr/bin/env python3
"""Fit the sine/cosine candidates and write fit/coeffs.h.

  python3 fit/fit.py        (needs numpy)

Every fit pins the mean of s^2+c^2-1 over all 65536 binary angles to zero in
float32 (so rotations neither grow nor shrink vectors on average), then trims one constant by float32 ulps
so the evaluated mean, not the real-number one, is closest to zero. The float32
evaluation here mirrors the C and assembly in bench/ operation by operation.
BFS_* is the S5C6 kernel (called BFSK in bench/); LUTX16_TABLE is LUTX16.
The other families (LUT, rational, CORDIC, power-of-two) were explored and
lost; they are kept because the S5C6 search starts from them.
"""
import math
from pathlib import Path
import numpy as np

F = np.float32
HERE = Path(__file__).resolve().parent
U = np.arange(65536, dtype=np.int64)
RAD = math.pi / 32768


def fold(ang):
    a = np.where(ang >= 0x8000, ang - 0x10000, ang)
    f = (a ^ (a << 1)) & 0xC000
    v = (a + f) & 0x7FFF
    v = np.where(v >= 0x4000, v - 0x8000, v)
    return a, f, v


def finish(a, f, s, c):
    swap = (f & 0x4000) != 0
    sn, cs = np.where(swap, c, s), np.where(swap, s, c)
    return np.where(a < 0, -sn, sn).astype(F), np.where(f & 0x8000, -cs, cs).astype(F)


A, FL, X = fold(U)
AX = np.abs(X)
XF = X.astype(F)


def mean_e(s, c):
    s, c = s.astype(np.float64), c.astype(np.float64)
    return float(np.mean(s * s + c * c - 1))


def trim(make, value, span=200):
    """Nudge one float32 constant by ulps until the float32 mean of e is closest to zero."""
    best = (abs(mean_e(*make(value))), value)
    up = dn = F(value)
    for _ in range(span):
        up, dn = np.nextafter(up, F(np.inf)), np.nextafter(dn, F(-np.inf))
        for v in (up, dn):
            m = abs(mean_e(*make(v)))
            if m < best[0]:
                best = (m, v)
    return F(best[1])


def bits_low16_zero(v):
    return (np.array([v], dtype=F).view(np.uint32)[0] & 0xFFFF) == 0


# ---------------------------------------------------------------- 1. LUT + quadratic
def lut_table(n):
    """Node pairs (sin, cos) at i * pi/4 / n, chosen within 2 ulps for the smallest |s^2+c^2-1|."""
    out = []
    for i in range(n + 1):
        th = i * (8192 // n) * RAD
        ts, tc = math.sin(th), math.cos(th)
        best = None
        for ds in range(-2, 3):
            s = F(ts)
            for _ in range(abs(ds)):
                s = np.nextafter(s, F(np.inf) if ds > 0 else F(-np.inf))
            for dc in range(-2, 3):
                c = F(tc)
                for _ in range(abs(dc)):
                    c = np.nextafter(c, F(np.inf) if dc > 0 else F(-np.inf))
                e = abs(float(s) ** 2 + float(c) ** 2 - 1)
                v = max(abs(float(s) - ts), abs(float(c) - tc))
                key = (e if v < 1.2e-7 * 1.0 else 1.0, v)
                if best is None or key < best[0]:
                    best = (key, s, c)
        out.append((best[1], best[2]))
    if n:
        out[0] = (F(0), F(1))
    out[n] = (F(math.sqrt(0.5)), F(math.sqrt(0.5)))
    return out


def lut_eval(n, tab, m, k):
    sh = 13 - int(math.log2(n))
    i = (AX + (1 << (sh - 1))) >> sh
    d = (AX - (i << sh)).astype(F)
    S = np.array([t[0] for t in tab], dtype=F)[i]
    C = np.array([t[1] for t in tab], dtype=F)[i]
    e1 = F(m) * d
    h = F(k) * (e1 * e1)
    a = F(1) - h
    s = S * a + C * e1
    c = C * a - S * e1
    return finish(A, FL, s, c)


def lut_fit(n):
    tab = lut_table(n)
    w = 8192 // n
    d = np.arange(-w // 2, w // 2, dtype=np.float64)
    best = None
    for rel in np.linspace(0.9990, 1.0, 201):
        m = RAD * rel
        p = m * d
        # zero mean of (1 - K p^2)^2 + p^2 - 1 over d: K^2 <p^4> - 2K <p^2> + <p^2> = 0 (smaller root)
        p2, p4 = np.mean(p ** 2), np.mean(p ** 4)
        k = (2 * p2 - math.sqrt(4 * p2 * p2 - 4 * p4 * p2)) / (2 * p4)
        err = np.max(np.abs((1 - k * p ** 2) - np.cos(d * RAD)) + np.abs(p - np.sin(d * RAD)))
        if best is None or err < best[0]:
            best = (err, F(m), F(k))
    _, m, k = best
    k = trim(lambda kv: lut_eval(n, tab, m, kv), k)
    return tab, m, k


def lutx_table(tab, m, k):
    """Per node: S, C*M, S*K*M^2 (sine line) and C, S*M, C*K*M^2 (cosine line), float32."""
    m, k = float(m), float(k)
    return [(F(S), F(float(C) * m), F(float(S) * k * m * m), F(C), F(float(S) * m), F(float(C) * k * m * m))
            for S, C in tab]


def lutx_eval(n, tabx):
    sh = 13 - int(math.log2(n))
    i = (AX + (1 << (sh - 1))) >> sh
    d = (AX - (i << sh)).astype(F)
    T = np.array(tabx, dtype=F)[i]
    d2 = d * d
    s = T[:, 0] + (d * T[:, 1] - d2 * T[:, 2])
    c = T[:, 3] - (d * T[:, 4] + d2 * T[:, 5])
    return finish(A, FL, s, c)


def lutx_fit(n):
    tab, m, k = lut_fit(n)
    best = None
    for j in range(-300, 301):
        kk = float(k) * (1 + j * 2e-7)
        tx = lutx_table(tab, m, kk)
        v = abs(mean_e(*lutx_eval(n, tx)))
        if best is None or v < best[0]:
            best = (v, tx)
    return best[1]


# ---------------------------------------------------------------- 2. rational t = tan(theta/2)
def rat_eval(t1, t3, r0, r1, r2, t5=None, r3=None):
    x2 = XF * XF
    t = XF * (F(t1) + F(t3) * x2) if t5 is None else XF * (F(t1) + x2 * (F(t3) + F(t5) * x2))
    u = t * t
    if r3 is not None:
        r = F(r0) + u * (F(r1) + u * (F(r2) + F(r3) * u))
    elif r2 is not None:
        r = F(r0) + u * (F(r1) + F(r2) * u)
    else:
        r = F(r0) + F(r1) * u
    tr = t * r
    s = np.abs(tr + tr)
    c = r - u * r
    return finish(A, FL, s, c)


def rat_fit(rdeg, tdeg=3):
    # t(x) ~ tan(x * RAD / 2), odd cubic, minimax on |x| <= 8192 (Lawson)
    x = np.arange(0, 8193, dtype=np.float64)
    tgt = np.tan(x * RAD / 2)
    B = np.stack([(x / 8192) ** p for p in range(1, tdeg + 1, 2)], 1)
    w = np.ones(len(x))
    for _ in range(300):
        sw = np.sqrt(w)
        c = np.linalg.lstsq(B * sw[:, None], tgt * sw, rcond=None)[0]
        r = np.abs(B @ c - tgt) + 1e-30
        w = w * r
        w /= w.sum()
    # r(u) ~ 1/(1+u) over the u each angle actually produces, scale error zero-mean, minimax
    tt = B @ c
    u = tt * tt
    wx = np.ones_like(x)
    wx[0] = wx[-1] = 0.5
    # R0 = 1 exactly so cos(0) = 1; R1.. fitted: relative error r(1+u) - 1, minimax, zero mean
    Bu = np.stack([u ** k for k in range(1, rdeg + 1)], 1)
    Arow = Bu * (1 + u)[:, None]
    y0 = -u                                  # (1 + Bu rc)(1+u) - 1 = Arow rc + u
    w = np.ones(len(x))
    for _ in range(300):
        sw = np.sqrt(w)
        Aw = np.vstack([Arow * sw[:, None], 1e6 * (wx @ Arow)[None, :] / wx.sum()])
        y = np.concatenate([y0 * sw, [1e6 * (wx @ y0) / wx.sum()]])
        rc = np.linalg.lstsq(Aw, y, rcond=None)[0]
        res = np.abs(Arow @ rc - y0) + 1e-30
        w = w * res
        w /= w.sum()
    rc = [F(1.0)] + [F(v) for v in rc] + [None] * (3 - rdeg)
    t1, t3 = F(c[0] / 8192), F(c[1] / 8192 ** 3)
    t5 = F(c[2] / 8192 ** 5) if tdeg == 5 else None
    r1 = trim(lambda v: rat_eval(t1, t3, rc[0], v, rc[2], t5, rc[3]), rc[1])
    return t1, t3, rc[0], r1, rc[2], t5, rc[3]


# ---------------------------------------------------------------- 3. power-of-two high coefficients
def poly_eval(sc, cc):
    x2 = XF * XF
    c = F(cc[-1])
    for v in reversed(cc[:-1]):
        c = c * x2 + F(v)
    s = F(sc[-1])
    for v in reversed(sc[:-1]):
        s = s * x2 + F(v)
    s = np.abs(s * XF)
    return finish(A, FL, s, c)


def dc_fit_fixed(ns, nc, lam, fixed_s=None, fixed_c=None, iters=400, seam=False):
    """coherent.py's zero-mean joint fit, with chosen coefficients (t units) held fixed."""
    fixed_s, fixed_c = fixed_s or {}, fixed_c or {}
    x = np.arange(0, 8193, dtype=np.float64)
    wx = np.ones_like(x)
    wx[0] = wx[-1] = 0.5
    t = x / 8192
    th = t * math.pi / 4
    Bs_all = np.stack([t ** (2 * k + 1) for k in range(ns)], 1)
    Bc_all = np.stack([t ** (2 * k) for k in range(1, nc)], 1)
    fs = [k for k in range(ns) if k not in fixed_s]
    fc = [k for k in range(1, nc) if k not in fixed_c]
    off_s = sum(fixed_s[k] * t ** (2 * k + 1) for k in fixed_s) if fixed_s else 0 * t
    off_c = sum(fixed_c[k] * t ** (2 * k) for k in fixed_c) if fixed_c else 0 * t
    Bs = Bs_all[:, fs]
    Bc = Bc_all[:, [k - 1 for k in fc]]
    a = np.linalg.lstsq(Bs, np.sin(th) - off_s, rcond=None)[0]
    b = np.linalg.lstsq(Bc, np.cos(th) - 1 - off_c, rcond=None)[0]
    n = len(t)
    w = np.ones(3 * n)
    for _ in range(iters):
        S, C = Bs @ a + off_s, 1 + Bc @ b + off_c
        e = S * S + C * C - 1
        r = np.concatenate([S - np.sin(th), C - np.cos(th), lam * e])
        J = np.block([[Bs, np.zeros((n, Bc.shape[1]))], [np.zeros((n, Bs.shape[1])), Bc],
                      [lam * 2 * S[:, None] * Bs, lam * 2 * C[:, None] * Bc]])
        jd = np.concatenate([(wx * 2 * S) @ Bs, (wx * 2 * C) @ Bc]) / wx.sum()
        rd = (wx @ e) / wx.sum()
        sw = np.sqrt(w)
        M = np.vstack([J * sw[:, None], 1e6 * jd[None, :]])
        y = np.concatenate([-r * sw, [-1e6 * rd]])
        if seam:
            # hard row: sine and cosine polynomials equal at 45 degrees (t = 1)
            M = np.vstack([M, 1e6 * np.concatenate([Bs[-1], -Bc[-1]])[None, :]])
            y = np.concatenate([y, [-1e6 * (S[-1] - C[-1])]])
        step = np.linalg.lstsq(M, y, rcond=None)[0]
        a, b = a + step[:len(fs)], b + step[len(fs):]
        S, C = Bs @ a + off_s, 1 + Bc @ b + off_c
        rr = np.abs(np.concatenate([S - np.sin(th), C - np.cos(th), lam * (S * S + C * C - 1)]))
        w = w * (rr + 1e-30)
        w /= w.sum()
    full_a = [fixed_s.get(k) for k in range(ns)]
    for j, k in enumerate(fs):
        full_a[k] = a[j]
    full_b = [fixed_c.get(k) for k in range(1, nc)]
    for j, k in enumerate(fc):
        full_b[k - 1] = b[j]
    sc = [F(full_a[k] / 8192.0 ** (2 * k + 1)) for k in range(ns)]
    cc = [F(1.0)] + [F(full_b[k - 1] / 8192.0 ** (2 * k)) for k in range(1, nc)]
    def mk(v):
        c2 = list(cc)
        c2[1] = v
        return poly_eval(sc, c2)
    cc[1] = trim(mk, cc[1])
    return sc, cc


def bf_near(v_t, k_t_scale):
    """8-bit-mantissa (low 16 bits zero: IDO loads it with lui + mtc1) neighbours of a t-unit coefficient."""
    vx = np.array([v_t / k_t_scale], dtype=F).view(np.uint32)[0]
    lo = int(vx) & 0xFFFF0000
    outs = []
    for b in (lo, lo + 0x10000):
        outs.append(float(np.array([b], dtype=np.uint32).view(F)[0]) * k_t_scale)
    return outs


def pow2_near(v_t, k_t_scale):
    """Power-of-two candidates (in x units) around a t-unit coefficient; return t-unit values."""
    vx = v_t / k_t_scale
    e = math.floor(math.log2(abs(vx)))
    return [math.copysign(2.0 ** p, vx) * k_t_scale for p in (e, e + 1)]


def value_err(s, c):
    return max(np.max(np.abs(s - np.sin(U * RAD))), np.max(np.abs(c - np.cos(U * RAD))))


def pow2_search(ns, nc, lam, which, near=None):
    """Hold the highest sine and/or cosine coefficient at a power of two; refit the rest."""
    base_s, base_c = dc_fit_fixed(ns, nc, lam)
    hs, hc = ns - 1, nc - 1
    vs_t = float(base_s[hs]) * 8192.0 ** (2 * hs + 1)
    vc_t = float(base_c[hc]) * 8192.0 ** (2 * hc)
    near = near or pow2_near
    opts_s = near(vs_t, 8192.0 ** (2 * hs + 1)) if 's' in which else [None]
    opts_c = near(vc_t, 8192.0 ** (2 * hc)) if 'c' in which else [None]
    best = None
    for ps in opts_s:
        for pc in opts_c:
            sc, cc = dc_fit_fixed(ns, nc, lam, {hs: ps} if ps else None, {hc: pc} if pc else None)
            s, c = poly_eval(sc, cc)
            err = value_err(s, c)
            emax = float(np.max(np.abs(s.astype(np.float64) ** 2 + c.astype(np.float64) ** 2 - 1)))
            key = err + emax
            if best is None or key < best[0]:
                best = (key, sc, cc, err, emax)
    return best[1], best[2], best[3], best[4]


def seam_values(sc, cc):
    """Float32 sine and cosine polynomials at the 45-degree fold boundary |x| = 8192."""
    x = F(8192)
    x2 = x * x
    c = F(cc[-1])
    for v in reversed(cc[:-1]):
        c = c * x2 + F(v)
    sv = F(sc[-1])
    for v in reversed(sc[:-1]):
        sv = sv * x2 + F(v)
    return F(sv * x), c


def seam_fit(sc, cc, s_span=40, c_span=400):
    """Hold the high (8-bit) coefficients; nudge S1 and C2 by float32 ulps so that the two
    polynomials agree exactly at 45 degrees (sine odd and cosine even, bit for bit),
    then keep the pair whose float32 mean of s^2+c^2-1 is closest to zero."""
    def steps(v, n):
        out, up, dn = [F(v)], F(v), F(v)
        for _ in range(n):
            up, dn = np.nextafter(up, F(np.inf)), np.nextafter(dn, F(-np.inf))
            out += [up, dn]
        return out
    best = None
    for s1 in steps(sc[0], s_span):
        sc2 = [s1] + list(sc[1:])
        for c2 in steps(cc[1], c_span):
            cc2 = [cc[0], c2] + list(cc[2:])
            a, b = seam_values(sc2, cc2)
            if a != b:
                continue
            m = abs(mean_e(*poly_eval(sc2, cc2)))
            if best is None or m < best[0]:
                best = (m, sc2, cc2)
    if best is None:
        raise SystemExit('no seam-exact pair in the search window')
    return best[1], best[2]


# ---------------------------------------------------------------- 5. CORDIC constants
def cordic_consts(n):
    """atan(2^-i) in binary-angle units << 16, and the start value K * 2^30 (zero-mean trimmed later in C)."""
    at = [int(round(math.atan(2.0 ** -i) * 32768 / math.pi * 65536)) for i in range(n)]
    k = 1.0
    for i in range(n):
        k /= math.sqrt(1 + 2.0 ** (-2 * i))
    return at, k


def cordic_eval(n, at, k0, correct):
    z = (AX << 16).astype(np.int64)
    xx = np.full_like(z, k0)
    yy = np.zeros_like(z)
    for i in range(n):
        neg = z < 0
        tx, ty = yy >> i, xx >> i
        xx, yy, z = (np.where(neg, xx + tx, xx - tx), np.where(neg, yy - ty, yy + ty),
                     np.where(neg, z + at[i], z - at[i]))
    Xf, Yf = xx.astype(F), yy.astype(F)
    q = F(2.0 ** -30)
    if correct:
        zs = z.astype(F) * F(RAD / 65536 * 2.0 ** -30)
        s = Yf * q + Xf * zs
        c = Xf * q - Yf * zs
    else:
        s, c = Yf * q, Xf * q
    return finish(A, FL, s, c)


def cordic_fit(n, correct):
    at, k = cordic_consts(n)
    k0 = int(round(k * 2 ** 30))
    best = None
    for dk in range(-80000, 80001, 200) if correct else range(-400, 401, 4):
        m = abs(mean_e(*cordic_eval(n, at, k0 + dk, correct)))
        if best is None or m < best[0]:
            best = (m, k0 + dk)
    base = best[1]
    for dk in range(-200, 201):
        m = abs(mean_e(*cordic_eval(n, at, base + dk, correct)))
        if m < best[0]:
            best = (m, base + dk)
    return at, best[1]


def fl(v):
    return f'{float(v)!r}f'


def main():
    lines = ['/* Generated by fit/fit.py; do not edit. */',
             '#ifndef TRIG_COEFFS_H', '#define TRIG_COEFFS_H', '']
    report = []
    # Reference: an earlier S5C6 zero-mean fit (weight 256), kept for comparison.
    zm_s = [9.586878877598792e-05, -1.4654012866436444e-13, 6.242752378751069e-23]
    zm_c = [1.0, -4.595415159514005e-09, 3.490059465637823e-18, -6.953270582103763e-28]
    for i, v in enumerate(zm_s):
        lines.append(f'#define ZM_S{2 * i + 1} {fl(F(v))}')
    for i, v in enumerate(zm_c[1:]):
        lines.append(f'#define ZM_C{2 * i + 2} {fl(F(v))}')
    lines.append('')
    for n in (8, 16, 32):
        tab, m, k = lut_fit(n)
        s, c = lut_eval(n, tab, m, k)
        report.append(f'LUT{n}: m={m!r} k={k!r} err={value_err(s, c):.2e} mean e={mean_e(s, c):+.1e}')
        lines.append(f'#define LUT{n}_SHIFT {13 - int(math.log2(n))}')
        lines.append(f'#define LUT{n}_M {fl(m)}')
        lines.append(f'#define LUT{n}_K {fl(k)}')
        lines.append(f'#define LUT{n}_TABLE \\')
        lines.append('    ' + ', \\\n    '.join('{ { ' + fl(a) + ', ' + fl(b) + ' } }' for a, b in tab))
        lines.append('')
    for n in (8, 16, 32):
        tx = lutx_fit(n)
        s_, c_ = lutx_eval(n, tx)
        report.append(f'LUTX{n}: err={value_err(s_, c_):.2e} mean e={mean_e(s_, c_):+.1e}')
        lines.append(f'#define LUTX{n}_TABLE \\')
        lines.append('    ' + ', \\\n    '.join('{ { ' + ', '.join(fl(v) for v in r[:3]) + ', 0.0f, '
                                              + ', '.join(fl(v) for v in r[3:]) + ', 0.0f } }' for r in tx))
        lines.append('')
    for tag, rdeg, tdeg in (('RAT32', 2, 3), ('RAT33', 3, 3), ('RAT52', 2, 5), ('RAT53', 3, 5)):
        t1, t3, r0, r1, r2, t5, r3 = rat_fit(rdeg, tdeg)
        s, c = rat_eval(t1, t3, r0, r1, r2, t5, r3)
        e = s.astype(np.float64) ** 2 + c.astype(np.float64) ** 2 - 1
        report.append(f'{tag}: err={value_err(s, c):.2e} max|e|={np.max(np.abs(e)):.1e} mean e={mean_e(s, c):+.1e}')
        for nm, v in (('T1', t1), ('T3', t3), ('T5', t5), ('R0', r0), ('R1', r1), ('R2', r2), ('R3', r3)):
            if v is not None:
                lines.append(f'#define {tag}_{nm} {fl(v)}')
        lines.append('')
    for label, ns, nc, lam, which, near in (('PW56', 3, 4, 256, 'sc', None), ('PW56S', 3, 4, 256, 's', None),
                                            ('PW56C', 3, 4, 256, 'c', None), ('PW54', 3, 3, 16, 'sc', None),
                                            ('BF56', 3, 4, 256, 'sc', bf_near), ('BF54', 3, 3, 16, 'sc', bf_near)):
        sc, cc, err, emax = pow2_search(ns, nc, lam, which, near)
        if label == 'BF56':
            # BFS: BF56's 8-bit top coefficients held, the rest refitted with the 45-degree
            # seam as a hard constraint, then closed bit-exactly in float32 (no runtime cost)
            fs = {2: float(sc[2]) * 8192.0 ** 5}
            fc = {3: float(cc[3]) * 8192.0 ** 6}
            ssc, scc = dc_fit_fixed(3, 4, 256, fs, fc, seam=True)
            ssc, scc = seam_fit(ssc, scc)
            s_, c_ = poly_eval(ssc, scc)
            e_ = s_.astype(np.float64) ** 2 + c_.astype(np.float64) ** 2 - 1
            report.append(f'BFS: err={value_err(s_, c_):.2e} max|e|={np.max(np.abs(e_)):.1e} '
                          f'mean e={mean_e(s_, c_):+.1e} seam {seam_values(ssc, scc)}')
            for i, v in enumerate(ssc):
                lines.append(f'#define BFS_S{2 * i + 1} {fl(v)}')
            for i, v in enumerate(scc[1:]):
                lines.append(f'#define BFS_C{2 * i + 2} {fl(v)}')
            lines.append('')
        s, c = poly_eval(sc, cc)
        flags = [bits_low16_zero(v) for v in sc + cc[1:]]
        report.append(f'{label}: err={err:.2e} max|e|={emax:.1e} mean e={mean_e(s, c):+.1e} lui-only={flags}')
        for i, v in enumerate(sc):
            lines.append(f'#define {label}_S{2 * i + 1} {fl(v)}')
        for i, v in enumerate(cc[1:]):
            lines.append(f'#define {label}_C{2 * i + 2} {fl(v)}')
        lines.append('')
    for n, correct, tag in ((7, True, 'CORDIC7C'), (10, True, 'CORDIC10C'), (14, False, 'CORDIC14')):
        at, k0 = cordic_fit(n, correct)
        s, c = cordic_eval(n, at, k0, correct)
        report.append(f'{tag}: err={value_err(s, c):.2e} mean e={mean_e(s, c):+.1e} k0={k0}')
        lines.append(f'#define {tag}_K0 {k0}')
        for i, v in enumerate(at):
            lines.append(f'#define {tag}_A{i} {v}')
        lines.append('')
    lines.append(f'#define CORDIC_ZSCALE {fl(F(RAD / 65536 * 2.0 ** -30))}')
    lines += ['#endif', '']
    (HERE / 'coeffs.h').write_text('\n'.join(lines))
    print('\n'.join(report))


if __name__ == '__main__':
    main()
