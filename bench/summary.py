#!/usr/bin/env python3
"""The README's speed tables, from the saved results in bench/results/.

  python3 bench/summary.py

Every figure comes from bench/run.py output files (ares v148, HackerSM64
3be00d2f, clang 21). ares is deterministic: a ROM gives the same cycles on
every run, so results saved in different sessions combine (checked: the
cache-line and table builds rerun later matched the saved files exactly).
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RES = HERE / 'results'
CPU_HZ = 93.75e6
LAYOUTS = (0, 1024, 4096)
# label: (table build, call build, sincos build)
KERNELS = [
    ('Silas', 'tasilas', 'asilas', 'asilas-sc'),
    ('S5C6 one cache line', 'tabfskl', 'abfskl', 'abfskl-sc'),
    ('S5C6 pure code', 'tabfsk', 'abfsk', 'abfsk-sc'),
    ('S5C6 one constant', 'taone', 'aone', 'aone-sc'),
]


def load(layout):
    out = {}
    for name in (f'kernels-pad{layout}.json', f'sincos-pad{layout}.json', f'one-pad{layout}.json'):
        p = RES / name
        if p.exists():
            out.update({k: v for k, v in json.loads(p.read_text()).items() if v})
    return out


def per_frame(r):
    d = r['demos']
    f = sum(x['frames'] for x in d)
    return {'us': sum(x['cycles'] - x['preempted'] for x in d) / f / CPU_HZ * 1e6,
            'd': sum(x['d_misses'] for x in d) / f, 'w': sum(x['d_writes'] for x in d) / f,
            'i': sum(x['i_misses'] for x in d) / f}


def same_game(a, b):
    return [(x['hash'], x['frames']) for x in a['demos']] == [(x['hash'], x['frames']) for x in b['demos']]


def row(label, vals, fmt='{:+.0f}'):
    mean = sum(vals) / len(vals)
    return f'| {label} | ' + ' | '.join(fmt.format(v) for v in vals) + f' | **{fmt.format(mean)}** |'


def main():
    data = {L: load(L) for L in LAYOUTS}
    head = '| | layout 0 | layout 1024 | layout 4096 | mean |\n|---|---|---|---|---|'

    print('Table lookups, game-thread µs/frame (the baseline):\n')
    print(head)
    vanilla = json.loads((RES / 'vanilla.json').read_text())
    print(row('vanilla table, unmodified call sites', [per_frame(vanilla[f'vanilla-pad{L}'])['us'] for L in LAYOUTS],
              '{:,.0f}'))
    print(row('vanilla table, sincos call-site build', [per_frame(data[L]['vanilla-sc'])['us'] for L in LAYOUTS],
              '{:,.0f}'))

    print('\nSeparate sins()/coss() calls, µs/frame against the vanilla table:\n')
    print(head)
    for label, t, c, _ in KERNELS:
        print(row(label, [per_frame(data[L][c])['us'] - per_frame(vanilla[f'vanilla-pad{L}'])['us'] for L in LAYOUTS]))

    print('\nSeparate calls against a table refilled with the same values (bit-identical game, checked):\n')
    print(head)
    for label, t, c, _ in KERNELS:
        vals = []
        for L in LAYOUTS:
            assert same_game(data[L][t], data[L][c]), (label, L)
            vals.append(per_frame(data[L][c])['us'] - per_frame(data[L][t])['us'])
        print(row(label, vals))

    print('\nsincoss() at the 13 converted call sites, µs/frame against the vanilla table (same source):\n')
    print(head)
    for label, _, _, sc in KERNELS:
        print(row(label, [per_frame(data[L][sc])['us'] - per_frame(data[L]['vanilla-sc'])['us'] for L in LAYOUTS]))

    print('\nsincoss(): µs/frame saved against Silas:\n')
    print(head)
    for label, _, _, sc in KERNELS[1:]:
        print(row(label, [per_frame(data[L]['asilas-sc'])['us'] - per_frame(data[L][sc])['us'] for L in LAYOUTS]))

    print('\nsincoss(): cache misses per frame against the vanilla table, mean of the 3 layouts '
          '(whole machine; ares charges 40 cycles per data-cache miss or write-back, 48 per instruction-cache miss):\n')
    print('| | data-cache misses | write-backs | instruction-cache misses |\n|---|---|---|---|')
    for label, _, _, sc in KERNELS:
        d = {k: sum(per_frame(data[L][sc])[k] - per_frame(data[L]['vanilla-sc'])[k] for L in LAYOUTS) / 3
             for k in ('d', 'w', 'i')}
        print(f"| {label} | {d['d']:+.0f} | {d['w']:+.0f} | {d['i']:+.0f} |")

    cyc = RES / 'cycles.json'
    if cyc.exists():
        c = json.loads(cyc.read_text())
        print('\nCPU cycles per call, warm cache, interrupts off (ares), loop overhead subtracted. '
              'In order: angles 0, 1, 2, ...; random: a pseudo-random angle each call:\n')
        print('| | sin, in order | sin, random | sin + cos as two calls, random | sincos, random |\n|---|---|---|---|---|')
        for label, v in [('SM64 vanilla table (inline)', 'vanilla-sc')] + [(k[0], k[3]) for k in KERNELS] \
                + [('LUTX16', 'alutx-sc')]:
            x = c.get(v, {}) and c[v].get('cycles')
            if not x:
                continue
            sincos = x['random']['sincos'] if v != 'vanilla-sc' else x['random']['sin_cos_two_calls']
            print(f"| {label} | {x['in_order']['sin']:.1f} | {x['random']['sin']:.1f} | "
                  f"{x['random']['sin_cos_two_calls']:.1f} | {sincos:.1f} |")


if __name__ == '__main__':
    main()
