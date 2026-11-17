#!/usr/bin/env python3
"""The README's in-game and per-call tables, from the saved results in bench/results/.

  python3 bench/summary.py

The baseline is Silas Lock's kernel. Every in-game figure is S5C6 minus
Silas, built from the same source at the same code shift: each value is
given with its difference from Silas in brackets.

Every figure comes from bench/run.py output files (ares v148, HackerSM64
3be00d2f, clang 21). ares is deterministic: a ROM gives the same counts on
every run, so results saved in different sessions combine (checked: rebuilt
ROMs matched the saved files exactly).

Code shifts: each build is made with 0 to 15 KB of padding before the kernel
(bench/build.py --pad), in 1 KB steps: one full period of the 16 KB
instruction cache. Moving code changes which functions collide in the cache,
which changes a result by chance. For each code shift, the script takes the
difference between S5C6 and Silas at that shift. A figure is the mean of
these differences with its 95 % confidence interval (Student's t). If the
interval contains 0, the difference cannot be told apart from code-position
chance.

Memory traffic: the bytes that the CPU moves over the RDRAM bus. With Ares 64
the emulator counts them on the bus, by device (instruction cache, data cache,
uncached). With ares v148 they come from the cache-miss counts: a data-cache
miss reads one 16-byte line, a write-back writes one 16-byte line, an
instruction-cache miss reads one 32-byte line (VR4300); the two agree exactly.
"""
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
RES = HERE / 'results'
CPU_HZ = 93.75e6
OLD_SHIFTS = (0, 1024, 4096)                   # results/{kernels,sincos,one}-padN.json
BASE = ('Silas', 'asilas', 'asilas-sc')
# label: (separate-calls build, sincos build)
KERNELS = [
    ('S5C6 one cache line', 'abfskl', 'abfskl-sc'),
    ('S5C6 pure code', 'abfsk', 'abfsk-sc'),
    ('S5C6 quantized', 'aone', 'aone-sc'),
]
BUILDS = [b for k in [BASE] + KERNELS for b in k[1:]]
LINE = {'d': 16, 'w': 16, 'i': 32}             # bytes per data miss, write-back, instruction miss

# Student t, 0.975 quantile, by degrees of freedom
T975 = {1: 12.71, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
        11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 18: 2.101, 20: 2.086, 25: 2.060,
        30: 2.042, 40: 2.021, 50: 2.009, 60: 2.000, 80: 1.990, 100: 1.984, 120: 1.980}


def load_all():
    """{shift: {build: result}}"""
    out = {}
    for s in OLD_SHIFTS:
        d = {}
        for name in (f'kernels-pad{s}.json', f'sincos-pad{s}.json', f'one-pad{s}.json'):
            p = RES / name
            if p.exists():
                d.update({k: v for k, v in json.loads(p.read_text()).items() if v})
        out[s] = d
    for p in sorted((RES / 'shifts').glob('pad*.json')):
        s = int(p.stem[3:])
        out.setdefault(s, {}).update({k: v for k, v in json.loads(p.read_text()).items() if v})
    return out


def per_frame(r):
    d = r['demos']
    f = sum(x['frames'] for x in d)
    m = {'us': sum(x['cycles'] - x['preempted'] for x in d) / f / CPU_HZ * 1e6,
         'd': sum(x['d_misses'] for x in d) / f, 'w': sum(x['d_writes'] for x in d) / f,
         'i': sum(x['i_misses'] for x in d) / f}
    if d and d[0].get('bus_icache'):          # Ares 64: bytes counted on the RDRAM bus, by device
        bus = {k: sum(x[k] for x in d) / f for k in ('bus_icache', 'bus_dcache', 'bus_uncached', 'bus_sp_dma')}
        m['ibytes'], m['dbytes'] = bus['bus_icache'], bus['bus_dcache'] + bus['bus_uncached']
        m['rsp'] = bus['bus_sp_dma']
    else:                                      # ares v148: bytes from the cache-miss counts
        m['dbytes'] = LINE['d'] * m['d'] + LINE['w'] * m['w']
        m['ibytes'] = LINE['i'] * m['i']
    m['bytes'] = m['dbytes'] + m['ibytes']
    return m


def mean_ci(v):
    """Mean and the half-width of its 95 % t interval."""
    n = len(v)
    m = sum(v) / n
    if n < 2:
        return m, float('nan')
    sd = math.sqrt(sum((x - m) ** 2 for x in v) / (n - 1))
    df = n - 1
    t = T975.get(df) or T975[max(k for k in T975 if k <= df)]
    return m, t * sd / math.sqrt(n)


def sign(x):
    return f'{x:+,.0f}'.replace('-', '−')


def fmt(m, h):
    return f'{sign(m)} ± {h:,.0f}'


def diffs(data, shifts, build, base, key):
    return [per_frame(data[s][build])[key] - per_frame(data[s][base])[key] for s in shifts]


def cell(data, shifts, build, base, key):
    """Value ± CI; for a kernel other than the baseline, (difference from Silas ± CI) after it."""
    v = mean_ci([per_frame(data[s][build])[key] for s in shifts])
    out = f'{v[0]:,.0f} ± {v[1]:,.0f}'
    if build != base:
        out += f' ({fmt(*mean_ci(diffs(data, shifts, build, base, key)))})'
    return out


def table(data, shifts, key, title):
    print(title + '\n')
    print('| | `sincoss()` at the 13 changed call sites | Separate `sins()` and `coss()` calls |\n|---|---|---|')
    for label, c, sc in [BASE] + KERNELS:
        print(f'| {label} | {cell(data, shifts, sc, BASE[2], key)} | {cell(data, shifts, c, BASE[1], key)} |')


def load_samples():
    """{sample index: {build: result}} from bench/sample.py."""
    out = {}
    for p in sorted((RES / 'samples').glob('s*.json')):
        out[int(p.stem[1:])] = {k: v for k, v in json.loads(p.read_text())['results'].items() if v}
    return out


def main():
    data = load_samples()
    what = 'samples (bench/sample.py)'
    if not data:
        data, what = load_all(), 'code shifts'
    shifts = sorted(s for s, d in data.items() if all(b in d for b in BUILDS))
    print(f'{len(shifts)} {what}. Every value: mean over the samples ± 95 % confidence interval. '
          'In brackets: difference from Silas in the same sample.\n')
    table(data, shifts, 'bytes', 'Memory traffic, bytes per frame moved over the RDRAM bus by cache misses:')
    print()
    table(data, shifts, 'us', 'Game-thread CPU time, µs per frame:')

    cyc = RES / 'cycles.json'
    if cyc.exists():
        c = json.loads(cyc.read_text())
        print('\nCPU cycles per call, warm cache, interrupts off (ares), loop overhead subtracted. '
              'In order: angles 0, 1, 2, ...; random: a pseudo-random angle each call. Exact: ares is '
              'deterministic and each loop covers all 65,536 calls, so these have no sampling error:\n')
        print('| | sin, in order | sin, random | sin + cos as two calls, random | sincos, random |\n|---|---|---|---|---|')
        for label, v in [(BASE[0], BASE[2])] + [(k[0], k[2]) for k in KERNELS]:
            x = c.get(v, {}) and c[v].get('cycles')
            if x:
                print(f"| {label} | {x['in_order']['sin']:.1f} | {x['random']['sin']:.1f} | "
                      f"{x['random']['sin_cos_two_calls']:.1f} | {x['random']['sincos']:.1f} |")


if __name__ == '__main__':
    main()
