#!/usr/bin/env python3
"""Accuracy against cost for every kernel of the timing ROM: tables and Pareto plots.

  uv run --with numpy --with matplotlib python3 bench/micro/frontier.py [--binutils DIR]

Inputs: fit/forms.json (float32 accuracy of the generated forms),
work/micro/run.log (cycles from bench/micro/micro.js), work/micro/micro.elf
(code sizes). The published kernels take their accuracy from fit/accuracy.py.

Costs:
  sincos cycles, sin cycles   CPU cycles per call, warm cache, random angles (Ares 64, interpreter)
  code bytes                  size of the sincos function
  bytes when cold             32-byte instruction-cache lines of the sincos function, plus its data:
                              what one call moves over the RDRAM bus when nothing of it is cached
A kernel is on the frontier of a pair (accuracy, cost) if no other kernel is
better or equal in both, and better in one.
"""
import argparse
import json
import math
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
HAND_ACC = {   # fit/accuracy.py, all 65536 angles
    'Silas': (1.92e-4, 7.09e-8, 2.00), 'S5C6_line': (1.45e-5, 1.72e-7, 0.19),
    'S5C6_code': (1.45e-5, 1.72e-7, 0.19), 'S5C6_quantized': (2.28e-5, 4.14e-5, 0.23)}
HAND_DATA = {'S5C6_line': 16}


def load(binutils):
    forms = json.loads((REPO / 'fit/forms.json').read_text())
    ids = dict((k, fid) for fid, k in json.loads((REPO / 'work/micro/gen.json').read_text()))
    nm = Path(binutils) / 'mips-linux-gnu-nm' if binutils else 'mips-linux-gnu-nm'
    syms = {}
    for line in subprocess.run([str(nm), '-S', str(REPO / 'work/micro/micro.elf')], capture_output=True,
                               text=True).stdout.splitlines():
        f = line.split()
        if len(f) == 4:
            syms[f[3]] = int(f[1], 16)
    rows = []
    for line in (REPO / 'work/micro/run.log').read_text().splitlines():
        if not line.startswith('MICRO '):
            continue
        _, name, sc, sn, crc, bad = line.split()
        key = name.replace('_', ' ') if name.replace('_', ' ') in forms else name
        if key in forms:
            f = forms[key]
            acc = (f['max error'], f['max |s²+c²−1|'], f['max direction error'])
            sym = f'g_{ids[key]}_sincos'
            data, group = 0, 'generated'
        else:
            acc = HAND_ACC[name]
            sym = f'h_{name}_sincos'
            data, group = HAND_DATA.get(name, 0), 'published'
        size = syms[sym]
        rows.append({'name': key, 'group': group, 'max error': acc[0], 'max |s²+c²−1|': acc[1],
                     'direction error': acc[2], 'sincos cycles': int(sc) / 100, 'sin cycles': int(sn) / 100,
                     'code bytes': size, 'bytes when cold': 32 * math.ceil(size / 32) + data,
                     'bad': int(bad), 'crc': crc})
    return rows


def front(rows, a, c):
    out = set()
    for r in rows:
        if not any((o[a] <= r[a] and o[c] <= r[c]) and (o[a] < r[a] or o[c] < r[c]) for o in rows):
            out.add(r['name'])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--binutils', default=None)
    ap.add_argument('--out', type=Path, default=REPO / 'fit/frontier.png')
    args = ap.parse_args()
    rows = load(args.binutils)
    acc_keys = ['max error', 'max |s²+c²−1|', 'direction error']
    cost_keys = ['sincos cycles', 'sin cycles', 'bytes when cold']
    fronts = {(a, c): front(rows, a, c) for a in acc_keys for c in cost_keys}
    args.out.with_suffix('.json').write_text(json.dumps(
        {'rows': rows, 'frontiers': {f'{a} | {c}': sorted(v) for (a, c), v in fronts.items()}}, indent=1))

    print('| Kernel | sincos cycles | sin cycles | code bytes | bytes when cold | max error | max \\|s²+c²−1\\| '
          '| direction error | on a frontier |')
    print('|---|---|---|---|---|---|---|---|---|')
    for r in sorted(rows, key=lambda r: r['sincos cycles']):
        on = sum(r['name'] in v for v in fronts.values())
        print(f"| {r['name']} | {r['sincos cycles']:.1f} | {r['sin cycles']:.1f} | {r['code bytes']} | "
              f"{r['bytes when cold']} | {r['max error']:.2e} | {r['max |s²+c²−1|']:.2e} | "
              f"{r['direction error']:.2f} | {on} of 9 |")

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(3, 3, figsize=(16, 14), dpi=120)
    fam = lambda n: ('published' if n in HAND_ACC else 'sqrt' if 'sqrt' in n else 'poly')
    col = {'published': '#d62728', 'sqrt': '#2ca02c', 'poly': '#1f77b4'}
    for i, a in enumerate(acc_keys):
        for j, c in enumerate(cost_keys):
            ax = axes[i][j]
            fr = fronts[(a, c)]
            for r in rows:
                on = r['name'] in fr
                ax.scatter(r[c], max(r[a], 1e-3 if a == 'direction error' else 1e-9), s=60 if on else 22,
                           color=col[fam(r['name'])], edgecolor='black' if on else 'none', zorder=3 if on else 2,
                           marker='s' if 'top 8-bit' in r['name'] else 'o')
                if on:
                    ax.annotate(r['name'].replace(' top 8-bit', '·8'), (r[c], max(r[a], 1e-9)), fontsize=7,
                                xytext=(4, 3), textcoords='offset points')
            pts = sorted((r[c], r[a]) for r in rows if r['name'] in fr)
            ax.step([p[0] for p in pts], [max(p[1], 1e-9) for p in pts], where='post', color='#555', lw=1, alpha=.6)
            ax.set_yscale('log')
            ax.set_xlabel(c)
            ax.set_ylabel(a)
            ax.grid(True, which='both', alpha=0.25)
    handles = [plt.Line2D([], [], marker='o', ls='', color=col[k], label=k) for k in col] + \
              [plt.Line2D([], [], marker='s', ls='', color='#777', label='top coefficient(s) 8-bit (·8)'),
               plt.Line2D([], [], marker='o', ls='', color='#fff', markeredgecolor='black', label='on the frontier')]
    fig.legend(handles=handles, loc='upper center', ncol=5, fontsize=10)
    fig.suptitle('Accuracy (float32, all angles) against cost (Ares 64 interpreter): Pareto frontiers', y=0.985)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(args.out)
    print(f'\nplot: {args.out}')


if __name__ == '__main__':
    main()
