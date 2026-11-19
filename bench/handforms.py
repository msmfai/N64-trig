#!/usr/bin/env python3
"""The hand-written kernels of kernel/forms/ with the coefficient sets of fit/sweep/.

  python3 bench/handforms.py list [--select timing|all]      # print the kernel list (JSON) for bench/micro/build.py

A kernel is one file (form and load style) with one coefficient set (form,
family and point of fit/sweep.py). The file names its coefficients in its
"# COEFFICIENTS:" header and its data line in its "# LINE:" header.

--select timing: one kernel for each file and family (the "limits" point):
the code of a file depends only on which coefficients are 8-bit, so this
set gives the size and the cycles of every point.
"""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / 'fit'))
import sweep as SW              # noqa: E402

KDIR = REPO / 'kernel' / 'forms'
SDIR = REPO / 'fit' / 'sweep'
ONE = 0x3F800000
FAM = {'free': 'free', 'top 8-bit': 't8', 'quantized': 'q', 'all 8-bit': 'a8'}


def file_id(form):
    return form.lower().replace('+', '')          # 'C4+sqrt' -> 'c4sqrt'


def names(form):
    kind, sp, cp = SW.spec(form)
    if kind == 'quad':
        return [f'Q{e}' for e in sp]
    if kind == 'tan':
        return [f'T{e}' for e in sp]
    return [f'S{e}' for e in sp] + [f'C{e}' for e in cp]


def header(path):
    text = path.read_text()
    co = re.search(r'^# COEFFICIENTS:(.*)$', text, re.M).group(1).split()
    line = re.search(r'^# LINE:(.*)$', text, re.M).group(1).split()
    return co, line


def entry(form, load, family, label, bits):
    src = KDIR / f'{file_id(form)}_{load}.s'
    co, line = header(src)
    vals = dict(zip(names(form), bits))
    if sorted(co) != sorted(vals):
        raise SystemExit(f'{src}: coefficients {co}, form {form} has {list(vals)}')
    words = [ONE if n == 'ONE' else vals[n] for n in line]
    lab = re.sub(r'[^A-Za-z0-9]+', '', label.replace('.', 'p'))
    return {'name': f'{file_id(form)}_{load}_{FAM[family]}_{lab}', 'form': form, 'load': load, 'family': family,
            'point': label, 'src': str(src.relative_to(REPO)), 'defsym': {n: vals[n] for n in co}, 'words': words,
            'bits': bits}


def kernels(select='all'):
    out = []
    for f in sorted(SDIR.glob('*.json')):
        for form, fams in json.loads(f.read_text()).items():
            for load in ('line', 'code'):
                if not (KDIR / f'{file_id(form)}_{load}.s').exists():
                    continue
                for family, pts in fams.items():
                    for p in pts:
                        if select == 'timing' and p['label'] != 'limits':
                            continue
                        e = entry(form, load, family, p['label'], p['coefficients'])
                        e['shared'] = select == 'timing'          # also time trig_sincos for single calls
                        out.append(e)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=['list', 'check'])
    ap.add_argument('--list', type=Path, help='check: the kernel list given to bench/micro/build.py')
    ap.add_argument('--log', type=Path, nargs='+', help='check: timing ROM output(s)')
    ap.add_argument('--select', choices=['timing', 'all'], default='timing')
    args = ap.parse_args()
    if args.cmd == 'list':
        print(json.dumps(kernels(args.select), indent=1))
        return
    import frontier as FR
    ks = json.loads(args.list.read_text())
    rom = {}
    for log in args.log:
        for l in log.read_text().splitlines():
            if l.startswith('MICRO '):
                f = l.split()
                rom.setdefault(f[1], set()).add((f[4], f[5]))
    bad = 0
    for k in ks:
        model = FR.crc(FR.model(k['form'], k['bits']))
        got = rom.get(k['name'])
        ok = got == {(model, '0')}
        bad += not ok
        if not ok:
            print(f"{k['name']}: model {model}, ROM {got}")
    print(f'{len(ks) - bad} of {len(ks)} kernels: ROM CRC = model CRC, sincos = two sin calls')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
