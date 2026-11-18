#!/usr/bin/env python3
"""Pareto frontiers of all kernels over seven objectives.

  uv run --with numpy --with matplotlib python3 bench/frontier.py [--readme]

Kernels: the hand-written kernels and the generated kernels of the timing ROM
(bench/micro; fit/forms.json, fit/variants-S5C4-builds.json,
fit/hwsearch-S5C4-builds.json).

Inputs (all in the repository):
  bench/results/micro/run1-5.log   the timing ROM output, 5 runs (MICRO lines)
  bench/results/micro/sizes.json   symbol sizes of the timing ROM
  bench/results/micro/gen.json     the generated kernel names

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
  sincos cycles     CPU cycles per trig_sincos call (median of 5 runs, warm cache)
  sin cycles        CPU cycles per trig_sin call (median of 5 runs, warm cache)
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


def rows():
    runs = []
    for i in range(1, 6):
        runs.append({l.split()[1]: l.split()[2:] for l in (HERE / f'results/micro/run{i}.log').read_text().splitlines()
                     if l.startswith('MICRO ')})
    sizes = json.loads((HERE / 'results/micro/sizes.json').read_text())
    gen = {key.replace(' ', '_'): fid for fid, key in json.loads((HERE / 'results/micro/gen.json').read_text())}
    models = kernels()
    out = []
    for name in runs[0]:
        model, kind = models[name]
        crcs = {r[name][2] for r in runs}
        if crcs != {crc(model)}:
            raise SystemExit(f'{name}: model CRC {crc(model)}, ROM {crcs}')
        shared = name.endswith('+shared') or name == 'S5C4_shared'
        base = name.removesuffix('+shared')
        p = f'h_{base}' if kind == 'hand' else f'g_{gen[name]}'
        sc, sn = sizes[f'{p}_sincos'], sizes[f'{p}_sin']
        data = 16 if (name in ('S5C6_line', 'S5C4_line', 'S5C4_shared') or 'one_cache_line' in name) else 0
        lines = math.ceil(sc / 32) + (0 if shared else math.ceil(sn / 32))
        r = {'name': HAND_NAME[name] if kind == 'hand' else name.replace('_', ' ') + ' (generated)', 'kind': kind,
             'form': form(name), 'family': family(name),
             'sincos cycles': statistics.median(int(r[name][0]) for r in runs) / 100,
             'sin cycles': statistics.median(int(r[name][1]) for r in runs) / 100,
             'sincos bytes': sc, 'sin bytes': 0 if shared else sn, 'data bytes': data,
             'cold bytes': 32 * lines + data, 'crc': crcs.pop(), **metrics(model)}
        r['meets limits'] = bool(r['never above 1'] and all(r[k] <= v if k != 'direction error' else r[k] < v
                                                            for k, v in LIMITS.items()))
        out.append(r)
    return out


def dominates(a, b, keys):
    return all(a[k] <= b[k] for k in keys) and any(a[k] < b[k] for k in keys)


def rank(rs, keys, field='rank'):
    left, r = list(rs), 1
    while left:
        front = [x for x in left if not any(dominates(o, x, keys) for o in left)]
        for x in front:
            x[field] = r
        left = [x for x in left if x not in front]
        r += 1


COL = {'S, C polynomials': '#1f77b4', 'C + sqrt': '#d62728', 'S + sqrt': '#2ca02c'}
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
    for r in sorted(rs, key=lambda r: -r['rank']):
        ys = [norm(r, k) for k in OBJ]
        if r['name'] in ('Silas',):
            ax.plot(xs, ys, color='black', lw=3, zorder=5)
            ax.annotate('Silas', (len(OBJ) - 1, ys[-1]), xytext=(6, 0), textcoords='offset points', fontsize=9,
                        fontweight='bold', va='center')
        elif r['meets limits']:
            ax.plot(xs, ys, color=COL[r['form']], lw=2.2, zorder=4, ls='-' if r['rank'] == 1 else '--')
            ax.annotate(r['name'], (len(OBJ) - 1, ys[-1]), xytext=(6, 0), textcoords='offset points', fontsize=7,
                        va='center', color=COL[r['form']])
        elif r['rank'] == 1:
            ax.plot(xs, ys, color=COL[r['form']], lw=.8, alpha=.35, zorder=3)
        else:
            ax.plot(xs, ys, color='#bbbbbb', lw=.7, alpha=.6, zorder=2)
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
    ax.legend(handles=[Line2D([], [], color='black', lw=3, label='Silas')] +
              [Line2D([], [], color=c, lw=2.2, label=f'within the gameplay limits: {f}') for f, c in COL.items()
               if any(r['meets limits'] and r['form'] == f for r in rs)] +
              [Line2D([], [], color='#555', lw=2.2, ls='--', label='within the limits, rank 2 or higher'),
               Line2D([], [], color='#1f77b4', lw=.8, alpha=.35, label='rank 1, outside the limits'),
               Line2D([], [], color='#bbbbbb', lw=1, label='rank 2 or higher, outside the limits'),
               Line2D([], [], color='#ff7f0e', lw=3, label='gameplay limit')],
              loc='upper center', bbox_to_anchor=(.45, -.07), ncol=4, fontsize=9, frameon=False)
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
            fr = [r for r in rs if not any(dominates(o, r, [kx, ky]) for o in rs)]
            for r in sorted(rs, key=lambda r: r['name'] == 'Silas'):     # Silas last, on top
                on, silas = r in fr, r['name'] == 'Silas'
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
    n1 = sum(r['rank'] == 1 for r in rs)
    nc = sum(r.get('cost rank') == 1 for r in rs)
    block = (f'Kernels: {len(rs)}. Within the gameplay limits: {len(feasible)}. For each kernel, the CRC of the '
             f'model output is equal to the CRC of the timing ROM.\n\n'
             f'**Pareto set within the gameplay limits.** The kernels within the limits that no other kernel within '
             f'the limits equals or beats in the three costs (sincos cycles, sin cycles, cold bytes) and beats in '
             f'one ({nc} kernels):\n\n{table(rs, lambda r: r.get("cost rank") == 1)}\n\n'
             f'<details><summary>Pareto set on all seven objectives ({n1} of {len(rs)} kernels)</summary>\n\n'
             f'{table(rs, lambda r: r["rank"] == 1)}\n\n</details>\n')
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
        for name, body in (('frontier', block), ('accuracy', '\n'.join(acc) + '\n'), ('cost', '\n'.join(cost) + '\n')):
            a, b = f'<!-- gen:{name} -->\n', f'<!-- /gen:{name} -->'
            s = s[:s.index(a) + len(a)] + body + s[s.index(b):]
        p.write_text(s)


if __name__ == '__main__':
    main()
