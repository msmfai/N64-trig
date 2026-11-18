#!/usr/bin/env python3
"""Like-for-like comparisons in the game, from the runs of bench/fast.py.

  uv run --with matplotlib python3 bench/fair.py      # prints the tables, writes bench/fair.png

Runs: bench/results/fast/hand-sincos (build aslot-sc: sincoss() at the 13
changed call sites) and bench/results/fast/hand-separate (build aslot:
separate sins() and coss() calls). Both runs use the same 8 samples, and all
kernels of a sample run in copies of one base ROM.

Two match-ups, each with the same function structure on both sides:
  two functions   trig_sincos and trig_sin: Silas against S5C4 one cache line and S5C4 pure code
  one function    only trig_sincos, also for single calls: Silas shared against S5C4 shared
A difference is paired: kernel minus reference in the same sample, then the
mean and its 95 % interval (Student's t) over the samples.
"""
import json
import math
from pathlib import Path

import summary as S

HERE = Path(__file__).resolve().parent
RES = HERE / 'results' / 'fast'
RUNS = [('hand-sincos', '`sincoss()`'), ('hand-separate', 'Separate calls')]
MATCHUPS = [('Two functions (`trig_sincos` and `trig_sin`)', 'Silas', ['S5C4_line', 'S5C4_pure']),
            ('One function (only `trig_sincos`, also for single calls)', 'Silas+shared', ['S5C4_shared'])]
NAMES = {'Silas': 'Silas', 'S5C4_line': 'S5C4 one cache line', 'S5C4_pure': 'S5C4 pure code',
         'Silas+shared': 'Silas, shared', 'S5C4_shared': 'S5C4 shared'}


def kid(k):
    return k.replace('+', '_')


def load(run):
    out = RES / run
    sizes = json.loads((out / 'kernels.json').read_text())
    data = {}
    for d in sorted(out.glob('s[0-9]*')):
        r = {}
        for k in NAMES:
            f = d / f'{kid(k)}.json'
            if f.exists():
                r[k] = S.per_frame(json.loads(f.read_text()))
        if len(r) == len(NAMES):
            data[int(d.name[1:])] = r
    return data, sizes


def stats(data, k, ref, key):
    ids = sorted(data)
    m = S.mean_ci([data[i][k][key] for i in ids])
    d = S.mean_ci([data[i][k][key] - data[i][ref][key] for i in ids]) if k != ref else None
    return m, d


def size_cell(sizes, k):
    z = sizes[k]
    sc, sn, data = z['code bytes']['trig_sincos'], z['code bytes']['trig_sin'], z['data bytes']
    lines = math.ceil(sc / 32) + math.ceil(sn / 32)
    code = f'{sc} + {sn} B' if sn else f'{sc} B'
    return f'{code} ({lines} lines)' + (f' + {data} B data' if data else '')


def tables():
    loaded = {run: load(run) for run, _ in RUNS}
    n = min(len(d) for d, _ in loaded.values())
    blocks = []
    for title, ref, ks in MATCHUPS:
        head = '| Kernel | Code (cache lines) and data | ' + ' | '.join(
            f'{lab}: CPU time, µs per frame | {lab}: memory traffic, bytes per frame'
            for _, lab in RUNS) + ' |'
        rows = [head, '|' + '---|' * (2 + 2 * len(RUNS))]
        for k in [ref] + ks:
            cells = [NAMES[k], size_cell(loaded[RUNS[0][0]][1], k)]
            for run, _ in RUNS:
                data = loaded[run][0]
                for key in ('us', 'bytes'):
                    m, d = stats(data, k, ref, key)
                    c = f'{m[0]:,.0f} ± {m[1]:,.0f}'
                    if d:
                        c += f' ({S.fmt(*d)})'
                    cells.append(c)
            rows.append('| ' + ' | '.join(cells) + ' |')
        blocks.append(f'**{title}.** Reference: {NAMES[ref]}.\n\n' + '\n'.join(rows) + '\n')
    return n, blocks


def plot(path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    loaded = {run: load(run) for run, _ in RUNS}
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), dpi=120)
    style = {'S5C4_line': ('#1f77b4', 's'), 'S5C4_pure': ('#2ca02c', 'o'), 'S5C4_shared': ('#9467bd', 'D')}
    for ax, (run, lab) in zip(axes, RUNS):
        data = loaded[run][0]
        for title, ref, ks in MATCHUPS:
            for k in ks:
                _, du = stats(data, k, ref, 'us')
                _, db = stats(data, k, ref, 'bytes')
                col, mk = style[k]
                ax.errorbar(du[0], db[0], xerr=du[1], yerr=db[1], fmt=mk, color=col, ms=8, capsize=4,
                            label=f'{NAMES[k]} − {NAMES[ref]}')
        ax.axhline(0, color='black', lw=.8)
        ax.axvline(0, color='black', lw=.8)
        ax.set_title(lab.replace('`', ''), fontsize=11)
        ax.set_xlabel('CPU time difference, µs per frame')
        ax.set_ylabel('memory traffic difference, bytes per frame')
        ax.grid(True, alpha=.3)
        ax.legend(fontsize=9)
    fig.suptitle(f'Paired differences in the game ({len(data)} samples, 95 % intervals). '
                 'Origin: the reference of each match-up.', fontsize=11)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


if __name__ == '__main__':
    n, bs = tables()
    print(n, 'samples\n')
    print('\n'.join(bs))
    plot(HERE / 'fair.png')
