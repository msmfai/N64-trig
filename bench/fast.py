#!/usr/bin/env python3
"""Compare kernels in the game, fast: one build per sample, the kernels written into a fixed slot.

  python3 bench/fast.py run --name NAME --kernels K1 K2 ... [--samples 8] [--emulators 8] \\
      --clang BIN --binutils BIN --baserom sm64.us.z64 --ares ARES_TEST
  python3 bench/fast.py report --name NAME

A kernel is a published kernel (Silas, S5C6_line, S5C6_code, S5C6_quantized)
or FORMS_FILE:KEY (bench/slot.py). The first kernel is the reference.

For each sample (bench/sample.py draw: code, data and heap shift, game seed),
the script builds one HackerSM64 ROM with the fixed kernel slot (build
aslot-sc: sincoss() at the 13 changed call sites; or aslot with --separate),
writes each kernel into a copy of it (bench/slot.py) and runs the copies in
Ares 64: CPU interpreter (exact cache fetches), RSP recompiler. The ROMs of a
sample differ only in the slot, so the difference between two kernels in one
sample contains no change of code position.

Files (all kept; a stopped run continues):
  work/fast/base/BUILD/sNNN.z64, .elf        the base ROM of each sample (shared by all runs)
  work/fast/NAME/sNNN/KERNEL.z64              the ROM with the kernel
  bench/results/fast/NAME/sNNN/KERNEL.json    the result, written when the run ends
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import build as B
import run as R
import sample as SA
import slot
import summary as S

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
RES = HERE / 'results' / 'fast'


def kid(kernel):
    return re.sub(r'[^A-Za-z0-9]+', '_', kernel.split(':', 1)[-1]).strip('_')


def cmd_run(args):
    variant = 'aslot' if args.separate else 'aslot-sc'
    args.slot = 'fast'
    SA.BUILD = SA.build_id()
    tree, env = B.setup(args, [variant])
    base_dir = REPO / 'work/fast/base' / f'{SA.BUILD}-{variant}'
    out = RES / args.name
    out.mkdir(parents=True, exist_ok=True)
    (out / 'run.json').write_text(json.dumps({'kernels': args.kernels, 'variant': variant, 'build': SA.BUILD,
                                              'emulator': SA.emulator(args.ares) + ', RSP recompiler',
                                              'sampler seed': args.sampler_seed}, indent=1))
    gate = threading.Semaphore(args.emulators)
    threads, lock = [], threading.Lock()
    info = json.loads((out / 'kernels.json').read_text()) if (out / 'kernels.json').exists() else {}

    def run_one(i, k, rom):
        try:
            res = R.run_all({k: rom}, args.ares, 1, 3600)
            if res.get(k):
                d = out / f's{i:03d}'
                SA.write_atomic(d / f'{kid(k)}.json', json.dumps(res[k]))
                with lock:
                    print(f'sample {i} {k}: done', flush=True)
        finally:
            gate.release()

    for i in range(args.samples):
        z = SA.draw(args.sampler_seed, i)
        todo = [k for k in args.kernels if not (out / f's{i:03d}' / f'{kid(k)}.json').exists()]
        if not todo:
            continue
        base = base_dir / f's{i:03d}.z64'
        if not base.exists():
            args.pad, args.dpad, args.heappad, args.seed = z['pad'], z['dpad'], z['heappad'], z['seed']
            SA.build_checked(tree, variant, args, env, z, base)
            elf = (B.sincos_tree(tree) if variant.endswith('-sc') else tree) / f'build-{variant}-fast/us_n64/sm64.elf'
            shutil.copy2(elf, base.with_suffix('.elf'))
        for k in todo:
            rom = REPO / 'work/fast' / args.name / f's{i:03d}' / f'{kid(k)}.z64'
            rom.parent.mkdir(parents=True, exist_ok=True)
            info[k] = slot.write(base, base.with_suffix('.elf'), k, rom, args.binutils,
                                 Path(args.clang) / 'clang')
            gate.acquire()
            t = threading.Thread(target=run_one, args=(i, k, rom))
            t.start()
            threads.append(t)
    (out / 'kernels.json').write_text(json.dumps(info, indent=1))
    for t in threads:
        t.join()
    cmd_report(args)


def cmd_report(args):
    out = RES / args.name
    meta = json.loads((out / 'run.json').read_text())
    kernels = meta['kernels']
    sizes = json.loads((out / 'kernels.json').read_text()) if (out / 'kernels.json').exists() else {}
    data = {}
    for d in sorted(out.glob('s[0-9]*')):
        r = {k: json.loads((d / f'{kid(k)}.json').read_text()) for k in kernels if (d / f'{kid(k)}.json').exists()}
        if len(r) == len(kernels):
            data[int(d.name[1:])] = r
    ids = sorted(data)
    if len(ids) < 2:
        print(f'{len(ids)} complete samples: not enough for an interval')
        return
    ref = kernels[0]
    print(f"{len(ids)} samples, {meta['variant']}, {meta['emulator']}. Value: mean ± 95 % confidence interval; "
          f"in brackets: difference from {ref} in the same sample.\n")
    print('RAM pressure: code bytes and 32-byte instruction-cache lines of each function, data bytes, and '
          '"cold": the bytes both functions and the data move over the RDRAM bus when none of them is cached. '
          'A sin of 0 bytes is one function for both (the slot adds an 8-byte branch to it).\n')
    print('| Kernel | sincos bytes (lines) | sin bytes (lines) | data | cold | CPU time, µs per frame | '
          'Memory traffic, bytes per frame |')
    print('|---|---|---|---|---|---|---|')
    for k in kernels:
        cells = []
        for key in ('us', 'bytes'):
            v = S.mean_ci([S.per_frame(data[i][k])[key] for i in ids])
            c = f'{v[0]:,.0f} ± {v[1]:,.0f}'
            if k != ref:
                c += ' (' + S.fmt(*S.mean_ci([S.per_frame(data[i][k])[key] - S.per_frame(data[i][ref])[key]
                                              for i in ids])) + ')'
            cells.append(c)
        sz = sizes.get(k, {})
        code = sz.get('code bytes', {})
        sc, sn, dbytes = code.get('trig_sincos'), code.get('trig_sin'), sz.get('data bytes')
        if sc is None:
            ram = '| ? | ? | ? | ?'
        else:
            lines = lambda n: -(-n // 32)
            cold = 32 * (lines(sc) + lines(sn)) + (16 if dbytes else 0)
            ram = f'| {sc} ({lines(sc)}) | {sn} ({lines(sn)}) | {dbytes} | {cold}'
        print(f"| {k.split(':', 1)[-1]} {ram} | {cells[0]} | {cells[1]} |")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run')
    B.add_args(r)
    r.add_argument('--name', required=True)
    r.add_argument('--kernels', nargs='+', required=True)
    r.add_argument('--samples', type=int, default=8)
    r.add_argument('--sampler-seed', type=int, default=1, help='seed of the draws (as bench/sample.py --seed)')
    r.add_argument('--emulators', type=int, default=8)
    r.add_argument('--separate', action='store_true', help='separate sins()/coss() calls (build aslot)')
    r.add_argument('--ares', default=R.default_ares())
    p = sub.add_parser('report')
    p.add_argument('--name', required=True)
    args = ap.parse_args()
    (cmd_run if args.cmd == 'run' else cmd_report)(args)


if __name__ == '__main__':
    main()
