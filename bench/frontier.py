#!/usr/bin/env python3
"""Pareto frontiers of all kernels over seven objectives.

  uv run --with numpy --with matplotlib python3 bench/frontier.py [--readme]

Kernels: the kernels of kernel/ and Silas, and every point of the coefficient
sweep (fit/sweep/) in every hand-written file of kernel/forms/ (one cache line,
pure code), each with two functions and shared (only trig_sincos). A
kernel/forms/ point equal to a kernel of kernel/ in all objectives is one row.

Inputs (all in the repository):
  bench/results/micro/layout1-5.log  the timing ROM output in 5 layouts (bench/micro/build.py --layout)
  bench/results/micro/kernels.json   the timed kernel/forms/ kernels (bench/handforms.py list --select timing)
  bench/results/micro/sizes.json     symbol sizes of the timing ROM
The code of a file depends only on which coefficients are 8-bit. The script
checks that each point has the same lui/ori pattern as its timed point; the
cycles and sizes of the timed point are then those of the point.

Accuracy: a float32 model of each kernel (the operations and their order in
the assembly) gives sin(a) and sin(a + 0x4000) for all 65,536 angles. The
script stops if the CRC-32 of the model output is not the CRC of the timing
ROM: then the model and the kernel are the same, bit for bit.

Objectives (lower is better):
  max error         max |value - exact| of the sine and the cosine
  direction error   max angle error of the (cos, sin) pair, in 1/65536 turn
  creep |U|         max |s² + c² - 1| for turns of 1 to 1092 steps (0 to 6 degrees):
                    a rotation applied once per frame changes the length by this factor
  max |U|           max |s² + c² - 1| over all angles
  sincos cycles     CPU cycles per trig_sincos call (median of 5 layouts, warm cache)
  sin cycles        CPU cycles per trig_sin call (median of 5 layouts, warm cache)
  cold bytes        bytes the two functions and the data move over the RDRAM bus when
                    none of them is cached: 32-byte lines of each function, plus 16 bytes
                    for a data line. A shared kernel counts its one function once.

Rank: non-dominated sorting. Rank 1 is the set of kernels that no other kernel
equals or beats in all seven objectives and beats in one (the Pareto set).
Rank 2 is the Pareto set of the remaining kernels, and so on.

Gameplay limits (fit/hwsearch.py): direction error < 0.5, creep |U| <= 6.0e-8,
max |U| <= 2e-5, |sin| and |cos| never above 1.

Outputs: fit/frontier.json, fit/frontier-parallel.png (parallel coordinates),
fit/frontier-matrix.png (scatterplot matrix of all pairs). With --readme: the
README block between <!-- gen:frontier --> and <!-- /gen:frontier -->.
"""
import argparse
import json
import math
import re
import statistics
import sys
import zlib
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / 'fit'))
import accuracy as ACC          # noqa: E402  (Silas and S5C6 models)

F = np.float32
A = np.arange(65536, dtype=np.int64)
TH = A * (2 * math.pi / 65536)
S5C4_BITS = [0x38c907e2, 0xaa2449da, 0x1a850000, 0xb19ddd5a, 0x227d0000]
CREEP = list(range(1, 1093)) + list(range(65536 - 1092, 65536))
LIMITS = {'direction error': 0.5, 'creep |U|': 6.0e-8, 'max |U|': 2e-5}
OBJ = ['max error', 'direction error', 'creep |U|', 'max |U|', 'sincos cycles', 'sin cycles', 'cold bytes']


def f32(bits):
    return np.array(bits, dtype=np.uint32).view(F)


def folded(kind, ks, kc):
    """The generated kernels and S5C4 (bench/micro/gen.py, kernel/s5c4_*.s): coefficients
    in binary-angle units (float32 bit patterns), Horner in x², float32 at every step."""
    ks, kc = f32(ks), f32(kc)

    def sin(a):
        t = (a & 0xFFFF) + 0x2000
        xi = (t & 0x3FFF) - 0x2000
        x = xi.astype(F)
        x2 = x * x
        s = c = None
        if len(ks):
            h = ks[-1] * np.ones_like(x)
            for k in ks[-2::-1]:
                h = h * x2 + k
            s = h * x
        if len(kc):
            h = kc[-1] * np.ones_like(x)
            for k in kc[-2::-1]:
                h = h * x2 + k
            c = h * x2 + F(1)
        if kind == 'csqrt':
            s = np.sqrt(F(1) - c * c)
            s = np.where(xi < 0, -s, s)
        elif kind == 'ssqrt':
            c = np.sqrt(F(1) - s * s)
        v = np.where(t & 0x4000, c, s)
        return np.where(t & 0x8000, -v, v).astype(F)
    return sin


def model(form, bits):
    """float32 model of a kernel/forms/ kernel (fit/sweep.py forms) for all angles"""
    import sweep as SW
    kind, sp, cp = SW.spec(form)
    if kind in ('poly', 'csqrt', 'ssqrt'):
        return folded(kind, bits[:len(sp)], bits[len(sp):])
    k = f32(bits)

    def horner(x2):
        h = k[-1] * np.ones_like(x2)
        for c in k[-2::-1]:
            h = h * x2 + c
        return h

    if kind == 'quad':
        def sin(a):
            t = (a & 0xFFFF) + 0x4000
            x = ((t & 0x7FFF) - 0x4000).astype(F)
            v = horner(x * x) * x
            return np.where(t & 0x8000, -v, v).astype(F)
        return sin

    def sin(a):                       # T forms: octant fold, u ~ tan(x/2)
        t = (a & 0xFFFF) + 0x2000
        x = ((t & 0x3FFF) - 0x2000).astype(F)
        u = horner(x * x) * x
        u2 = u * u
        d = F(1) / (F(1) + u2)
        v = np.where(t & 0x4000, (F(1) - u2) * d, (u + u) * d)
        return np.where(t & 0x8000, -v, v).astype(F)
    return sin


def crc(sin):
    s0, c0 = sin(A), sin(A + 0x4000)
    return f'{zlib.crc32(np.stack([s0, c0], 1).astype("<f4").tobytes()) & 0xFFFFFFFF:08x}'


def metrics(sin):
    s0, c0 = sin(A).astype(np.float64), sin(A + 0x4000).astype(np.float64)
    u = s0 * s0 + c0 * c0 - 1
    d = np.abs((np.arctan2(s0, c0) - TH + math.pi) % (2 * math.pi) - math.pi) * 65536 / (2 * math.pi)
    return {'max error': float(max(np.abs(s0 - np.sin(TH)).max(), np.abs(c0 - np.cos(TH)).max())),
            'direction error': float(d.max()), 'creep |U|': float(np.abs(u[CREEP]).max()),
            'max |U|': float(np.abs(u).max()), 'drift': float(u.mean()),
            'never above 1': bool(np.all(np.abs(s0) <= 1) and np.all(np.abs(c0) <= 1))}


HAND_NAME = {'Silas': 'Silas', 'Silas+shared': 'Silas, shared', 'S5C6_line': 'S5C6 one cache line',
             'S5C6_code': 'S5C6 pure code', 'S5C6_quantized': 'S5C6 quantized',
             'S5C4_line': 'S5C4 one cache line', 'S5C4_pure': 'S5C4 pure code', 'S5C4_shared': 'S5C4 shared'}
HAND_FAMILY = {'Silas': 'free', 'Silas+shared': 'free', 'S5C6_line': 'top 8-bit', 'S5C6_code': 'top 8-bit',
               'S5C6_quantized': 'quantized', 'S5C4_line': 'top 8-bit', 'S5C4_pure': 'top 8-bit',
               'S5C4_shared': 'top 8-bit'}


def family(name):
    if name in HAND_FAMILY:
        return HAND_FAMILY[name]
    n = name.replace('_', ' ')
    for f in ('all 8-bit', 'quantized', 'top 8-bit'):
        if f in n:
            return f
    return 'free'


def form(name):
    if name.startswith('Silas') or name.startswith('C'):
        return 'C + sqrt'
    if '+sqrt' in name:
        return 'S + sqrt'
    return 'S, C polynomials'


def kernels():
    """-> {timing ROM name: (model, kind of kernel)}"""
    out = {'Silas': (ACC.silas()[0], 'hand'), 'Silas+shared': (ACC.silas()[0], 'hand'),
           'S5C6_line': (ACC.s5c6(ACC.BFSK)[0], 'hand'), 'S5C6_code': (ACC.s5c6(ACC.BFSK)[0], 'hand'),
           'S5C6_quantized': (ACC.s5c6(ACC.ONE)[0], 'hand')}
    for k in ('S5C4_line', 'S5C4_pure', 'S5C4_shared'):
        out[k] = (folded('poly', S5C4_BITS[:3], S5C4_BITS[3:]), 'hand')
    for f in ('fit/forms.json', 'fit/variants-S5C4-builds.json', 'fit/hwsearch-S5C4-builds.json'):
        for key, v in json.loads((REPO / f).read_text()).items():
            ns = len(range(1, v['ns'] + 1, 2)) if v['kind'] != 'csqrt' else 0
            out[key.replace(' ', '_')] = (folded(v['kind'], v['coefficients'][:ns], v['coefficients'][ns:]),
                                          'generated')
    return out


FORM_CLASS = {'poly': 'S, C polynomials', 'csqrt': 'C + sqrt', 'ssqrt': 'S + sqrt', 'quad': 'Q: one polynomial',
              'tan': 'T: tangent half-angle'}
LOAD_NAME = {'line': 'one cache line', 'code': 'pure code'}


def code_ori(k):
    """the coefficients that the code builds with lui + ori (not 8-bit, not in the data line)"""
    import handforms as FO
    _, line = FO.header(REPO / k['src'])
    return tuple(n for n, v in k['defsym'].items() if n not in line and v & 0xFFFF)


def rows():
    import handforms as FO
    runs = []
    for i in range(1, 6):
        runs.append({l.split()[1]: l.split()[2:] for l in (HERE / f'results/micro/layout{i}.log').read_text()
                     .splitlines() if l.startswith('MICRO ')})
    sizes = json.loads((HERE / 'results/micro/sizes.json').read_text())
    med = lambda name, i: statistics.median(int(r[name][i]) for r in runs) / 100
    out = []

    def finish(r, sc, sn, data, shared):
        lines = math.ceil(sc / 32) + (0 if shared else math.ceil(sn / 32))
        r.update({'sincos bytes': sc, 'sin bytes': 0 if shared else sn, 'data bytes': data,
                  'cold bytes': 32 * lines + data})
        r['meets limits'] = bool(r['never above 1'] and all(r[k] <= v if k != 'direction error' else r[k] < v
                                                            for k, v in LIMITS.items()))
        out.append(r)

    # the hand-written kernels of kernel/ and Silas
    hand = {'Silas': ACC.silas()[0], 'Silas+shared': ACC.silas()[0], 'S5C6_line': ACC.s5c6(ACC.BFSK)[0],
            'S5C6_code': ACC.s5c6(ACC.BFSK)[0], 'S5C6_quantized': ACC.s5c6(ACC.ONE)[0]}
    for k in ('S5C4_line', 'S5C4_pure', 'S5C4_shared'):
        hand[k] = folded('poly', S5C4_BITS[:3], S5C4_BITS[3:])
    for name, model in hand.items():
        if {r[name][2] for r in runs} != {crc(model)}:
            raise SystemExit(f'{name}: model CRC {crc(model)}, ROM {[r[name][2] for r in runs]}')
        shared = name.endswith('+shared') or name == 'S5C4_shared'
        base = name.removesuffix('+shared')
        data = 16 if name in ('S5C6_line', 'S5C4_line', 'S5C4_shared') else 0
        r = {'name': HAND_NAME[name], 'kind': 'hand', 'group': 'kernel/', 'form': form(name),
             'family': family(name), 'load': 'line' if data else 'code', 'structure': 'shared' if shared else 'two',
             'sincos cycles': med(name, 0), 'sin cycles': med(name, 1), **metrics(model)}
        finish(r, sizes[f'h_{base}_sincos'], sizes[f'h_{base}_sin'], data, shared)

    # kernel/forms/: every point of fit/sweep/, in both load styles, with two functions or shared
    timed = {}
    for k in FO.kernels('timing'):
        timed[(k['src'], k['family'])] = k
    missing = []
    for k in FO.kernels('all'):
        t = timed[(k['src'], k['family'])]
        tname = t['name'] if code_ori(k) == code_ori(t) else k['name']    # same code as the timed point?
        if tname not in runs[0]:
            missing.append(k['name'])
            continue
        if {r[tname][3] for r in runs} != {'0'}:
            raise SystemExit(f'{tname}: sincos is not two sin calls')
        model = globals()['model'](k['form'], k['bits'])
        if tname == k['name'] and {r[tname][2] for r in runs} != {crc(model)}:
            raise SystemExit(f'{tname}: model CRC differs from the ROM')
        m = metrics(model)
        import sweep as SW
        cls = FORM_CLASS[SW.spec(k['form'])[0]]
        for shared in (False, True):
            n = tname + ('+shared' if shared else '')
            r = {'name': f"{k['form']} {LOAD_NAME[k['load']]}{', shared' if shared else ''}, {k['family']}, "
                         f"{k['point']}", 'kind': 'form', 'group': k['form'], 'form': cls, 'family': k['family'],
                 'load': k['load'], 'structure': 'shared' if shared else 'two', 'point': k['point'],
                 'coefficients': k['bits'], 'sincos cycles': med(n, 0), 'sin cycles': med(n, 1), **m}
            finish(r, sizes[f"h_{tname}_sincos"], sizes[f"h_{tname}_sin"], 16 if k['words'] else 0, shared)
    if missing:
        (REPO / 'work/untimed.json').write_text(json.dumps(missing))
        raise SystemExit(f'{len(missing)} points have code different from their timed point: work/untimed.json')
    # a kernel/forms/ point equal to a kernel of kernel/ in all objectives is the same kernel: keep one row
    key = lambda r: tuple(r[k] for k in OBJ) + (r['structure'],)
    hand_keys = {key(r) for r in out if r['kind'] == 'hand'}
    return [r for r in out if r['kind'] == 'hand' or key(r) not in hand_keys]


def dominates(a, b, keys):
    return all(a[k] <= b[k] for k in keys) and any(a[k] < b[k] for k in keys)


def rank(rs, keys, field='rank'):
    """non-dominated sorting (numpy): rank 1 = no other row equals or beats it in all keys and beats it in one"""
    if not rs:
        return
    v = np.array([[r[k] for k in keys] for r in rs], dtype=np.float64)
    left = np.arange(len(rs))
    level = 1
    while len(left):
        x = v[left]
        le = (x[:, None, :] <= x[None, :, :]).all(2)        # le[i, j]: i equals or beats j in all keys
        lt = (x[:, None, :] < x[None, :, :]).any(2)
        dom = (le & lt).any(0)                              # j is dominated by some i
        for i in left[~dom]:
            rs[i][field] = level
        left = left[dom]
        level += 1


COL = {'S, C polynomials': '#1f77b4', 'C + sqrt': '#d62728', 'S + sqrt': '#2ca02c', 'Q: one polynomial': '#9467bd',
       'T: tangent half-angle': '#8c564b'}
MARK = {'free': 'o', 'top 8-bit': 's', 'quantized': 'D', 'all 8-bit': '^'}
LOG = {'max error', 'direction error', 'creep |U|', 'max |U|'}


def plots(rs, out_par, out_mat):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    floor = {'creep |U|': 1e-9, 'max |U|': 1e-9}

    def val(r, k):
        v = max(r[k], floor.get(k, 0))
        return math.log10(v) if k in LOG else v

    lo = {k: min(val(r, k) for r in rs) for k in OBJ}
    hi = {k: max(val(r, k) for r in rs) for k in OBJ}
    norm = lambda r, k: (val(r, k) - lo[k]) / ((hi[k] - lo[k]) or 1)

    # parallel coordinates
    fig, ax = plt.subplots(figsize=(15, 8), dpi=120)
    xs = range(len(OBJ))
    layer = lambda r: (3 if r['name'] == 'Silas' else 2 if r.get('cost rank') == 1 else 1 if r['meets limits']
                       else 0)
    for r in sorted(rs, key=lambda r: (layer(r), -r['rank'])):
        ys = [norm(r, k) for k in OBJ]
        if r['name'] == 'Silas':
            ax.plot(xs, ys, color='black', lw=3, zorder=6)
            ax.annotate('Silas', (len(OBJ) - 1, ys[-1]), xytext=(6, 0), textcoords='offset points', fontsize=9,
                        fontweight='bold', va='center')
        elif r.get('cost rank') == 1:
            ax.plot(xs, ys, color=COL[r['form']], lw=3, zorder=5)
            ax.annotate(r['name'], (len(OBJ) - 1, ys[-1]), xytext=(6, 0), textcoords='offset points',
                        fontsize=8, va='center', color=COL[r['form']], fontweight='bold')
        elif r['meets limits']:
            ax.plot(xs, ys, color='#08306b', lw=1.0, alpha=.8, zorder=4)
        elif r['rank'] == 1:
            ax.plot(xs, ys, color=COL[r['form']], lw=.5, alpha=.18, zorder=3)
        else:
            ax.plot(xs, ys, color='#999999', lw=.4, alpha=.08, zorder=2)
    for i, k in enumerate(OBJ):
        ax.axvline(i, color='#444', lw=.8)
        lab = (lambda v: f'{10 ** v:.1e}') if k in LOG else (lambda v: f'{v:.0f}')
        ax.text(i, -0.04, lab(lo[k]), ha='center', va='top', fontsize=8)
        ax.text(i, 1.04, lab(hi[k]), ha='center', va='bottom', fontsize=8)
        if k in LIMITS:
            ax.plot([i - .08, i + .08], [norm({k: LIMITS[k]}, k)] * 2, color='#ff7f0e', lw=3, zorder=6)
    ax.set_xticks(list(xs))
    ax.set_xticklabels([k + (' (log)' if k in LOG else '') for k in OBJ], fontsize=10)
    ax.set_yticks([])
    ax.set_xlim(-.3, len(OBJ) + .9)
    ax.set_ylim(-.1, 1.1)
    for s in ('top', 'right', 'left'):
        ax.spines[s].set_visible(False)
    ax.legend(handles=[Line2D([], [], color='black', lw=3, label='Silas'),
                       Line2D([], [], color='#1f77b4', lw=3, label='Pareto set within the gameplay limits'),
                       Line2D([], [], color='#08306b', lw=1, label='other kernels within the gameplay limits')] +
              [Line2D([], [], color=c, lw=1.5, alpha=.5, label=f'Pareto set (rank 1), outside the limits: {f}')
               for f, c in COL.items()] +
              [Line2D([], [], color='#999999', lw=1, alpha=.4, label='rank 2 or higher, outside the limits'),
               Line2D([], [], color='#ff7f0e', lw=3, label='gameplay limit')],
              loc='upper center', bbox_to_anchor=(.45, -.07), ncol=3, fontsize=9, frameon=False)
    ax.set_title('All kernels on seven objectives (lower is better on each axis; axis ends: min and max)', fontsize=12)
    fig.tight_layout()
    fig.savefig(out_par)
    plt.close(fig)

    # scatterplot matrix: every pair, with the 2-D Pareto frontier of the pair
    n = len(OBJ)
    fig, axes = plt.subplots(n, n, figsize=(22, 22), dpi=100)
    for i, ky in enumerate(OBJ):
        for j, kx in enumerate(OBJ):
            ax = axes[i][j]
            if j >= i:
                ax.axis('off')
                continue
            order = sorted(range(len(rs)), key=lambda q: (rs[q][kx], rs[q][ky]))
            fr, best = [], math.inf
            for q in order:                                  # 2-D Pareto front: running minimum of y
                if rs[q][ky] < best:
                    fr.append(rs[q])
                    best = rs[q][ky]
            fr_ids = {id(r) for r in fr}
            for r in sorted(rs, key=lambda r: r['name'] == 'Silas'):     # Silas last, on top
                on, silas = id(r) in fr_ids, r['name'] == 'Silas'
                ax.scatter(max(r[kx], floor.get(kx, 0)), max(r[ky], floor.get(ky, 0)),
                           s=70 if silas else 40 if on else 14, marker='*' if silas else MARK[r['family']],
                           color='black' if silas else COL[r['form']],
                           edgecolor='black' if on else 'none', alpha=1 if on or silas else .45,
                           zorder=10 if silas else 3 if on else 2)
            pts = sorted((max(r[kx], floor.get(kx, 0)), max(r[ky], floor.get(ky, 0))) for r in fr)
            ax.step([p[0] for p in pts], [p[1] for p in pts], where='post', color='#555', lw=1)
            for k, setter in ((kx, ax.set_xscale), (ky, ax.set_yscale)):
                if k in LOG:
                    setter('log')
            if kx in LIMITS:
                ax.axvline(LIMITS[kx], color='#ff7f0e', lw=1)
            if ky in LIMITS:
                ax.axhline(LIMITS[ky], color='#ff7f0e', lw=1)
            ax.tick_params(labelsize=7)
            ax.grid(True, which='major', alpha=.25)
            if i == n - 1:
                ax.set_xlabel(kx, fontsize=10)
            if j == 0:
                ax.set_ylabel(ky, fontsize=10)
    handles = [Line2D([], [], marker='o', ls='', color=c, label=f) for f, c in COL.items()] + \
              [Line2D([], [], marker=m, ls='', color='#777', label=f'coefficients: {f}') for f, m in MARK.items()] + \
              [Line2D([], [], marker='*', ls='', color='black', markersize=12, label='Silas'),
               Line2D([], [], marker='o', ls='', color='#fff', markeredgecolor='black',
                      label='on the frontier of the pair'),
               Line2D([], [], color='#ff7f0e', label='gameplay limit')]
    fig.legend(handles=handles, loc='upper right', bbox_to_anchor=(.95, .9), fontsize=13, frameon=False)
    fig.suptitle('All pairs of the seven objectives: kernels and the Pareto frontier of each pair', fontsize=16, y=.995)
    fig.tight_layout(rect=(0, 0, 1, .985))
    fig.savefig(out_mat)
    plt.close(fig)


def plot_forms(rs, path):
    """one panel per form: all points of its parameter sweep (coefficient trade-off, coefficient family,
    load style, function structure); the form's own Pareto set on the seven objectives outlined"""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    groups = [g for g in dict.fromkeys(r['group'] for r in rs if r['kind'] == 'form')]
    n = len(groups)
    cols = 4
    fig, axes = plt.subplots(math.ceil(n / cols), cols, figsize=(20, 4.6 * math.ceil(n / cols)), dpi=100)
    fcol = {'free': '#1f77b4', 'top 8-bit': '#2ca02c', 'quantized': '#ff7f0e', 'all 8-bit': '#d62728'}
    silas = next(r for r in rs if r['name'] == 'Silas')
    for ax, g in zip(axes.flat, groups):
        sub = [r for r in rs if r['group'] == g]
        rank(sub, OBJ, 'form rank')
        for r in sub:
            on = r['form rank'] == 1
            ax.scatter(r['max error'], max(r['max |U|'], 1e-9), s=34 if on else 12,
                       marker='s' if r['load'] == 'line' else 'o', facecolor=fcol[r['family']] if on else 'none',
                       edgecolor=fcol[r['family']], alpha=1 if on else .5, lw=.8)
        ax.scatter(silas['max error'], silas['max |U|'], marker='*', s=120, color='black', zorder=5)
        ax.axhline(LIMITS['max |U|'], color='#888', lw=.8, ls='--')
        ax.set_xscale('log')
        ax.set_yscale('log')
        best = min(sub, key=lambda r: r['sincos cycles'])
        cyc = sorted({r['sincos cycles'] for r in sub if r['structure'] == 'two'})
        cold = sorted({r['cold bytes'] for r in sub})
        nlim = sum(r['meets limits'] for r in sub)
        ax.set_title(f"{g}: sincos {cyc[0]:.1f}–{cyc[-1]:.1f} cycles, cold {cold[0]}–{cold[-1]} B\n"
                     f"{len(sub)} kernels, {sum(r['form rank'] == 1 for r in sub)} in its Pareto set, "
                     f"{nlim} within the gameplay limits", fontsize=9)
        ax.tick_params(labelsize=7)
        ax.grid(True, which='major', alpha=.25)
        ax.set_xlabel('max error', fontsize=8)
        ax.set_ylabel('max |s²+c²−1|', fontsize=8)
    for ax in list(axes.flat)[n:]:
        ax.axis('off')
    handles = [Line2D([], [], marker='o', ls='', color=c, label=f'coefficients: {f}') for f, c in fcol.items()] + \
              [Line2D([], [], marker='s', ls='', color='#777', label='one cache line'),
               Line2D([], [], marker='o', ls='', color='#777', label='pure code'),
               Line2D([], [], marker='o', ls='', markerfacecolor='none', markeredgecolor='#777',
                      label='outside the Pareto set of the form'),
               Line2D([], [], marker='*', ls='', color='black', markersize=12, label='Silas'),
               Line2D([], [], color='#888', ls='--', label='gameplay limit of max |s²+c²−1|')]
    fig.legend(handles=handles, loc='lower center', ncol=5, fontsize=11, frameon=False)
    fig.suptitle('Each form: all points of its parameter sweep. Filled: the Pareto set of the form on the seven '
                 'objectives.', fontsize=14)
    fig.tight_layout(rect=(0, .04, 1, .97))
    fig.savefig(path)
    plt.close(fig)


def form_table(rs):
    out = ['| Form | Kernels | In the Pareto set of all kernels | Within the gameplay limits | Max error (min) | '
           'Max \\|s²+c²−1\\| (min) | Creep (min) | `trig_sincos` cycles | `trig_sin` cycles | Cold bytes |',
           '|---|---|---|---|---|---|---|---|---|---|']
    for g in dict.fromkeys(r['group'] for r in rs if r['kind'] == 'form'):
        sub = [r for r in rs if r['group'] == g]
        two = [r for r in sub if r['structure'] == 'two']
        rng = lambda k, f, rows=sub: f'{f.format(min(r[k] for r in rows))}–{f.format(max(r[k] for r in rows))}'
        out.append(f"| {g} | {len(sub)} | {sum(r['rank'] == 1 for r in sub)} | {sum(r['meets limits'] for r in sub)} | "
                   f"{min(r['max error'] for r in sub):.1e} | {min(r['max |U|'] for r in sub):.1e} | "
                   f"{min(r['creep |U|'] for r in sub):.1e} | {rng('sincos cycles', '{:.1f}', two)} | "
                   f"{rng('sin cycles', '{:.1f}', two)} | {rng('cold bytes', '{}')} |")
    return '\n'.join(out)


def fmt(v, k):
    if k in ('sincos cycles', 'sin cycles'):
        return f'{v:.1f}'
    if k == 'direction error':
        return f'{v:.2f}'
    if k == 'cold bytes':
        return f'{v}'
    return f'{v:.1e}'


COST = ['sincos cycles', 'sin cycles', 'cold bytes']


def table(rs, cond):
    head = ['Kernel', 'Form', 'Coefficients', *OBJ, 'Within the gameplay limits']
    out = ['| ' + ' | '.join(h.replace('|', '\\|') for h in head) + ' |', '|' + '---|' * len(head)]
    for r in sorted((r for r in rs if cond(r)), key=lambda r: (r['sincos cycles'], r['name'])):
        out.append(f"| {r['name']} | {r['form']} | {r['family']} | " + ' | '.join(fmt(r[k], k) for k in OBJ) +
                   f" | {'Yes' if r['meets limits'] else 'No'} |")
    return '\n'.join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--readme', action='store_true', help='write the table into README.md')
    args = ap.parse_args()
    rs = rows()
    rank(rs, OBJ)
    feasible = [r for r in rs if r['meets limits']]
    rank(feasible, COST, 'cost rank')
    (REPO / 'fit/frontier.json').write_text(json.dumps(rs, indent=1))
    plots(rs, REPO / 'fit/frontier-parallel.png', REPO / 'fit/frontier-matrix.png')
    plot_forms(rs, REPO / 'fit/frontier-forms.png')
    (REPO / 'fit/frontier-pareto.md').write_text(
        '# Pareto set on all seven objectives\n\nGenerated by bench/frontier.py from bench/results/micro/ and '
        f'fit/sweep/. {sum(r["rank"] == 1 for r in rs)} of {len(rs)} kernels.\n\n' + table(rs, lambda r: r['rank'] == 1) + '\n')
    n1 = sum(r['rank'] == 1 for r in rs)
    nc = sum(r.get('cost rank') == 1 for r in rs)
    block = (f'Kernels: {len(rs)}. Within the gameplay limits: {len(feasible)}. For each kernel, the CRC of the '
             f'model output is equal to the CRC of the timing ROM.\n\n'
             f'**Pareto set within the gameplay limits.** The kernels within the limits that no other kernel within '
             f'the limits equals or beats in the three costs (sincos cycles, sin cycles, cold bytes) and beats in '
             f'one ({nc} kernels):\n\n{table(rs, lambda r: r.get("cost rank") == 1)}\n\n'
             f'The Pareto set on all seven objectives has {n1} of the {len(rs)} kernels: '
             f'[`fit/frontier-pareto.md`](fit/frontier-pareto.md). All values: [`fit/frontier.json`](fit/frontier.json).\n')
    print(block)
    hand = [r for r in rs if r['kind'] == 'hand']
    acc = ['| Kernel | Max error | Max direction error (1/65536 turn) | Creep: max \\|s²+c²−1\\|, turns of 0° to 6° '
           '| Max \\|s²+c²−1\\| | Mean s²+c²−1 (drift) | \\|sin\\|, \\|cos\\| never above 1 | Within the gameplay limits |',
           '|---|---|---|---|---|---|---|---|']
    cost = ['| Kernel | `trig_sincos` bytes | `trig_sin` bytes | Data bytes | Cold bytes | '
            '`trig_sincos` cycles | `trig_sin` cycles |', '|---|---|---|---|---|---|---|']
    for r in hand:
        if r['name'] != 'Silas, shared' and not r['name'].startswith('S5C4 shared'):
            acc.append(f"| {r['name']} | {r['max error']:.2e} | {r['direction error']:.2f} | {r['creep |U|']:.1e} | "
                       f"{r['max |U|']:.1e} | {r['drift']:+.1e} | {'Yes' if r['never above 1'] else 'No'} | "
                       f"{'Yes' if r['meets limits'] else 'No'} |")
        cost.append(f"| {r['name']} | {r['sincos bytes']} | {r['sin bytes'] or '(the `trig_sincos` function)'} | "
                    f"{r['data bytes'] or 'None'} | {r['cold bytes']} | {r['sincos cycles']:.1f} | "
                    f"{r['sin cycles']:.1f} |")
    if args.readme:
        p = REPO / 'README.md'
        s = p.read_text()
        for name, body in (('frontier', block), ('accuracy', '\n'.join(acc) + '\n'), ('cost', '\n'.join(cost) + '\n'),
                           ('forms', form_table(rs) + '\n')):
            a, b = f'<!-- gen:{name} -->\n', f'<!-- /gen:{name} -->'
            s = s[:s.index(a) + len(a)] + body + s[s.index(b):]
        p.write_text(s)


if __name__ == '__main__':
    main()
