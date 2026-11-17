#!/usr/bin/env python3
"""Write the in-game parts of README.md from the saved results.

  python3 bench/readme.py [--check]

The README has blocks between <!-- gen:NAME --> and <!-- /gen:NAME -->.
This script replaces the text of each block. It uses the samples of
bench/sample.py when there are at least MIN_SAMPLES of them, otherwise the
16 fixed code shifts. --check: exit 1 if the README is not up to date.
"""
import argparse
import re
import sys
from pathlib import Path

import summary as S

HERE = Path(__file__).resolve().parent
README = HERE.parent / 'README.md'
MIN_SAMPLES = 8
SEP = ' | `sincoss()` at the 13 changed call sites | Separate `sins()` and `coss()` calls |\n|---|---|---|\n'


METHOD_HEAD = (  # .format(emulator=...)
    '| Item | Value |\n|---|---|\n'
    '| Game | [HackerSM64](https://github.com/HackerN64/HackerSM64), commit 3be00d2f, clang 21, `-Os` |\n'
    '| Emulator | {emulator} |\n'
    '| Input | The seven attract-mode demos of SM64: 4,304 measured frames, with approximately 456 sine and '
    'cosine calls per frame |\n'
    '| Builds | Two for each kernel. **`sincoss()`:** [`bench/hsm64-sincos.patch`](bench/hsm64-sincos.patch) '
    'changes 13 functions to get the sine and the cosine of one angle from one `trig_sincos` call. These 13 '
    'functions make 98 % of the sine and cosine pairs. **Separate calls:** the game calls `sins()` and '
    '`coss()`, and each is one `trig_sin` call. |\n')


EMU_SAMPLES = ('[Ares 64](https://github.com/HailToDodongo/ares-64) (commit b4ead632f), headless, CPU interpreter: '
               'it fetches every instruction through the modelled caches ([`bench/ares64.js`](bench/ares64.js))')


def dataset():
    data = S.load_samples()
    ids = sorted(i for i, d in data.items() if all(b in d for b in S.BUILDS))
    if len(ids) >= MIN_SAMPLES:
        return data, ids, True
    data = S.load_all()
    return data, sorted(s for s, d in data.items() if all(b in d for b in S.BUILDS)), False


def table(data, ids, key):
    rows = ''
    for label, c, sc in [S.BASE] + S.KERNELS:
        rows += f'| {label} | {S.cell(data, ids, sc, S.BASE[2], key)} | {S.cell(data, ids, c, S.BASE[1], key)} |\n'
    return '|' + SEP + rows


def verdict(data, ids, key, noun, criterion):
    """One sentence for each kernel and mode whose difference interval excludes 0; else 'the same'."""
    out = []
    for label, c, sc in S.KERNELS:
        for mode, b, base in (('with `sincoss()`', sc, S.BASE[2]), ('with separate calls', c, S.BASE[1])):
            m, h = S.mean_ci(S.diffs(data, ids, b, base, key))
            if abs(m) > h:
                out.append(f'{label} {mode}: {abs(m):,.0f} {"less" if m < 0 else "more"} than Silas '
                           f'({S.fmt(m, h)}).')
    if not out:
        return f'- **{criterion}:** S5C6 and Silas have the same {noun}. Each difference interval contains 0.\n', True
    return f'- **{criterion}:** ' + ' '.join(out) + ' All other differences are 0 within the interval.\n', False


def blocks():
    data, ids, sampled = dataset()
    n = len(ids)
    unit = 'samples' if sampled else 'code shifts'
    by = S.mean_ci([S.per_frame(data[i][S.BASE[2]])['bytes'] for i in ids])
    us = S.mean_ci([S.per_frame(data[i][S.BASE[2]])['us'] for i in ids])
    k = S.KERNELS[0]
    t_line, t_same = verdict(data, ids, 'bytes', 'memory traffic', 'Criterion 1')
    c_line, c_same = verdict(data, ids, 'us', 'CPU time in the game', 'Criterion 2')
    widest = max(S.mean_ci(S.diffs(data, ids, b, base, 'bytes'))[1]
                 for _, c, sc in S.KERNELS for b, base in ((sc, S.BASE[2]), (c, S.BASE[1])))
    g = {}
    g['summary-table'] = (
        '| | Silas | S5C6 (one cache line) |\n|---|---|---|\n'
        '| Max error | 1.92e-4 | **1.45e-5** (13 times smaller) |\n'
        '| CPU cycles for one sine and one cosine (exact) | 93.0 | **89.5** |\n'
        '| CPU cycles for one sine (exact) | 65.5 | **54.5** |\n'
        f'| Memory traffic in the game, bytes per frame | {by[0]:,.0f} ± {by[1]:,.0f} | '
        f'{S.cell(data, ids, k[2], S.BASE[2], "bytes")} |\n'
        f'| CPU time in the game, µs per frame | {us[0]:,.0f} ± {us[1]:,.0f} | '
        f'{S.cell(data, ids, k[2], S.BASE[2], "us")} |\n')
    if t_same and c_same:
        g['summary-claim'] = ('- In the game, S5C6 has the same memory traffic and the same CPU time as Silas.\n'
                              '- Thus, S5C6 gives 13 times the accuracy for the same cost.\n')
    else:
        g['summary-claim'] = ('- In the game: refer to experiments 3 and 4 for the differences.\n')
    if sampled:
        g['method'] = METHOD_HEAD.format(emulator=EMU_SAMPLES) + (
            f'| Test conditions | {n} samples. Each sample is one random draw of the four conditions below '
            '([`bench/sample.py`](bench/sample.py)). All builds of a sample use the same draw. |\n'
            f'| Result | The mean of the {n} samples ± the 95 % confidence interval (Student\'s t). In brackets: '
            'the difference from Silas in the same sample, with its own confidence interval. |\n\n'
            '**Test conditions:** The position of code and data in memory decides which of them collide in the '
            'caches. These collisions change each result by chance, by up to approximately ±3 %. Each sample '
            'draws the positions and the game state at random, from the full period of each cache:\n\n'
            '| Condition | Draw | Effect |\n|---|---|---|\n'
            '| Code shift | 0 to 16 KB of padding before the kernel, in 32-byte steps | Instruction-cache '
            'collisions (16 KB cache, 32-byte lines) |\n'
            '| Data shift | 0 to 8 KB of `.bss` padding, in 16-byte steps | Data-cache collisions of the static '
            'data (8 KB cache, 16-byte lines) |\n'
            '| Heap shift | 0 to 8 KB added to the start of the main pool, in 16-byte steps | Data-cache '
            'collisions of all data that the game allocates at run time |\n'
            '| Game seed | 0 to 65,113 steps of the random generator of the game, at boot | The random choices '
            'of the objects. The path of Mario stays the same: the demos give the same input. |\n\n'
            'All four conditions are uniform and independent. Each sample has its own random generator, so the '
            'samples are independent.\n')
    else:
        g['method'] = METHOD_HEAD.format(emulator='ares v148') + (
            f'| Code shifts | Each build is made {n} times, with 0 to 15 KB of padding before the kernel, in 1 KB '
            'steps |\n'
            f'| Result | The mean of the {n} code shifts ± the 95 % confidence interval (Student\'s t). In '
            'brackets: the difference from Silas at the same code shift, with its own confidence interval. |\n\n'
            '**Why code shifts:** The VR4300 instruction cache is 16 KB. Two functions that are 16 KB apart in '
            'memory use the same cache lines and remove each other from the cache. If code moves, different '
            'functions collide, and the result changes by chance, by up to approximately ±3 %. The code shifts '
            'cover one full period of the cache in equal steps.\n')
    g['traffic'] = (table(data, ids, 'bytes') + '\n' + t_line +
                    f'- Each difference interval is {100 * widest / by[0]:.1f} % of the total traffic or less.\n'
                    '- Neither kernel reads a table. The kernels differ only in code size: 32 to 80 bytes when the '
                    'code is not in the cache.\n')
    g['cputime'] = table(data, ids, 'us') + '\n' + c_line
    return g, n, unit


def render(text, g):
    for name, body in g.items():
        pat = re.compile(rf'(<!-- gen:{name} -->\n).*?(<!-- /gen:{name} -->)', re.S)
        if not pat.search(text):
            raise SystemExit(f'README.md has no block gen:{name}')
        text = pat.sub(lambda m: m.group(1) + body + m.group(2), text)
    return text


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()
    g, n, unit = blocks()
    old = README.read_text()
    new = render(old, g)
    if args.check:
        sys.exit(0 if new == old else 1)
    if new != old:
        README.write_text(new)
    print(f'README.md: {n} {unit}, {"updated" if new != old else "no change"}')


if __name__ == '__main__':
    main()
