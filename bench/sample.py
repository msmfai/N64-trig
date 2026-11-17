#!/usr/bin/env python3
"""Draw random test conditions, build the ROMs for each one, run them in ares.

  python3 bench/sample.py --baserom sm64.us.z64 --clang BIN --binutils BIN [--samples 64] [--seed 1]

Each sample is one draw z from the distribution below. For each z, the
script builds the 8 comparison builds (Silas and the three S5C6 versions,
each with sincoss() and with separate calls), runs them in ares, and writes
bench/results/samples/sNNN.json: z and the results. All builds of a sample
use the same z, so S5C6 and Silas are compared under the same conditions.

  code shift   TRIG_PAD      0 to 16 KB in 32-byte steps     instruction-cache collisions (16 KB, 32 B lines)
  data shift   TRIG_DPAD     0 to 8 KB in 16-byte steps      data-cache collisions of static data (8 KB, 16 B lines)
  heap shift   TRIG_HEAPPAD  0 to 8 KB in 16-byte steps      data-cache collisions of run-time data
  game seed    TRIG_SEED     0 to 65,113 steps                the random choices of the game objects

Each factor is uniform and independent. Sample i uses its own random
generator (seed, i), so the samples are independent and a run can be
extended or continued: a sample with a results file is skipped.

Each variant reuses one build directory (build-VARIANT-sample), so the disk
holds 8 build trees and the ROMs (8 MB each, work/roms/sNNN/).
"""
import argparse
import json
import random
import shutil
import threading
from pathlib import Path

import build as B
import run as R

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = HERE / 'results' / 'samples'
VARIANTS = ['asilas', 'abfskl', 'abfsk', 'aone', 'asilas-sc', 'abfskl-sc', 'abfsk-sc', 'aone-sc']
RNG_PERIOD = 65114                       # period of SM64's random_u16


def draw(seed, i):
    r = random.Random(f'{seed}-{i}')
    return {'pad': 32 * r.randrange(512), 'dpad': 16 * r.randrange(512),
            'heappad': 16 * r.randrange(512), 'seed': r.randrange(RNG_PERIOD)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    B.add_args(ap)
    ap.add_argument('--samples', type=int, default=64, help='number of samples')
    ap.add_argument('--seed', type=int, default=1, help='seed of the sampler')
    ap.add_argument('--ares', default=R.default_ares())
    ap.add_argument('--run-jobs', type=int, default=4, help='ares processes for each sample')
    ap.add_argument('--parallel', type=int, default=3, help='samples run at the same time')
    args = ap.parse_args()
    sampler_seed = args.seed
    todo = [i for i in range(args.samples) if not (OUT / f's{i:03d}.json').exists()]
    print(f'{args.samples} samples (sampler seed {sampler_seed}), {len(todo)} still to run')
    OUT.mkdir(parents=True, exist_ok=True)
    args.slot = 'sample'
    tree, env = B.setup(args, VARIANTS)
    gate = threading.Semaphore(args.parallel)
    threads = []

    def run(i, z, roms):
        try:
            res = R.run_all(roms, args.ares, args.run_jobs, 1800)
            if all(res.get(v) for v in VARIANTS):
                (OUT / f's{i:03d}.json').write_text(json.dumps({'z': z, 'sampler_seed': sampler_seed,
                                                                 'results': res}, indent=1))
                print(f'sample {i}: done {z}', flush=True)
            else:
                print(f'sample {i}: incomplete, not saved {z}', flush=True)
        finally:
            gate.release()

    for i in todo:
        z = draw(sampler_seed, i)
        args.pad, args.dpad, args.heappad, args.seed = z['pad'], z['dpad'], z['heappad'], z['seed']
        gate.acquire()
        roms = {}
        for v in VARIANTS:
            rom = B.build(tree, v, args, env)
            dest = REPO / 'work' / 'roms' / f's{i:03d}' / f'{v}.z64'
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(rom, dest)
            roms[v] = dest
        t = threading.Thread(target=run, args=(i, z, roms))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()


if __name__ == '__main__':
    main()
