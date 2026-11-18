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
generator (seed, i), so the samples are independent and the run can be
extended with more samples.

Each variant reuses one build directory (build-VARIANT-sample). make does
not see a change of the sample switches, so the script touches the files
that use them before each build, and then reads gTrigConfig from the ELF
to check that the build has the switches of the sample.

Stop and continue at any time. Nothing that has finished is lost:
  work/roms/sNNN/VARIANT.z64     a checked ROM is kept and not built again
  work/partial/BUILD/EMULATOR/sNNN/VARIANT.json  the result of each ROM, written when it finishes
  bench/results/samples/sNNN.json written when all 8 results of the sample exist
All files are written to a temporary name and then renamed.
"""
import argparse
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import threading
from pathlib import Path

import build as B
import run as R

HERE = Path(__file__).resolve().parent
BUILD = None
REPO = HERE.parent
OUT = HERE / 'results' / 'samples'
ROMS = REPO / 'work' / 'roms'
PARTIAL = REPO / 'work' / 'partial'
VARIANTS = ['asilas', 'abfskl', 'abfsk', 'aone', 'asilas-sc', 'abfskl-sc', 'abfsk-sc', 'aone-sc']
RNG_PERIOD = 65114                       # period of SM64's random_u16
SAMPLE_FILES = ('src/game/trig_impl.c', 'src/game/trig_bench.c', 'src/boot/main.c')


def build_id():
    """Fingerprint of everything a benchmark ROM is built from in this repository."""
    h = hashlib.sha256()
    for f in sorted(list(HERE.glob('trig_*')) + list(HERE.glob('*.patch')) + [HERE / 'sincos_inline.h',
                                                                         REPO / 'fit' / 'coeffs.h']):
        h.update(f.name.encode() + f.read_bytes())
    return h.hexdigest()[:12]


def emulator(ares):
    """Name of the emulator: Ares 64 (ares-test) with its git commit, or the ares app."""
    p = Path(ares).resolve()
    if p.name == 'ares-test':
        for d in p.parents:
            if (d / '.git').exists():
                rev = subprocess.run(['git', '-C', str(d), 'rev-parse', '--short', 'HEAD'],
                                     capture_output=True, text=True).stdout.strip()
                return f'ares-64 {rev} interpreter'
        return 'ares-64 interpreter'
    return str(p)


def draw(seed, i):
    r = random.Random(f'{seed}-{i}')
    return {'pad': 32 * r.randrange(512), 'dpad': 16 * r.randrange(512),
            'heappad': 16 * r.randrange(512), 'seed': r.randrange(RNG_PERIOD)}


def write_atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(text)
    os.replace(tmp, path)


def tool(binutils, name):
    return str(Path(binutils) / f'mips-linux-gnu-{name}') if binutils else f'mips-linux-gnu-{name}'


def config_in_elf(elf, binutils):
    """The 4 words of gTrigConfig in the ELF: pad, dpad, heappad, seed."""
    syms = subprocess.run([tool(binutils, 'objdump'), '-t', str(elf)], capture_output=True, text=True).stdout
    m = re.search(r'^([0-9a-f]+)\s.*\s(\S+)\s+[0-9a-f]+\s+gTrigConfig$', syms, re.M)
    if not m:
        raise SystemExit(f'{elf}: no gTrigConfig')
    addr, sec = int(m.group(1), 16), m.group(2)
    dump = subprocess.run([tool(binutils, 'objdump'), '-s', '-j', sec, f'--start-address={addr}',
                           f'--stop-address={addr + 16}', str(elf)], capture_output=True, text=True).stdout
    words = []
    for line in dump.splitlines():
        f = line.split()
        if f and re.fullmatch(r'[0-9a-f]{8}', f[0]) and int(f[0], 16) >= addr - 15:
            words += [int(w, 16) for w in f[1:5] if re.fullmatch(r'[0-9a-f]{8}', w)]
    return words[:4]


def build_checked(tree, v, args, env, z, dest):
    t = B.sincos_tree(tree) if B.is_sincos(v) else tree
    for f in SAMPLE_FILES:
        (t / f).touch()
    rom = B.build(tree, v, args, env)
    got = config_in_elf(rom.with_name('sm64.elf'), args.binutils)
    want = [z['pad'], z['dpad'], z['heappad'], z['seed']]
    if got != want:
        raise SystemExit(f'{v}: the build has switches {got}, the sample wants {want}')
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + '.tmp')
    shutil.copy2(rom, tmp)
    os.replace(tmp, dest)
    write_atomic(dest.with_suffix('.ok'), json.dumps({'z': z, 'build': BUILD}))


def main():
    global OUT, VARIANTS
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    B.add_args(ap)
    ap.add_argument('--samples', type=int, default=64, help='number of samples')
    ap.add_argument('--seed', type=int, default=1, help='seed of the sampler')
    ap.add_argument('--ares', default=R.default_ares())
    ap.add_argument('--run-jobs', type=int, default=4, help='ares processes for each sample')
    ap.add_argument('--parallel', type=int, default=3, help='samples run at the same time')
    ap.add_argument('--builds', nargs='+', default=VARIANTS, help='the builds of each sample')
    ap.add_argument('--tag', help='write to bench/results/samples-TAG/ (another set of builds)')
    args = ap.parse_args()
    VARIANTS = args.builds
    if args.tag:
        OUT = HERE / 'results' / f'samples-{args.tag}'
    global BUILD
    BUILD = build_id()
    emu = emulator(args.ares)
    part_root = PARTIAL / BUILD / emu.replace(' ', '_')
    print(f'build {BUILD}, emulator {emu}', flush=True)
    sampler_seed = args.seed
    todo = [i for i in range(args.samples) if not (OUT / f's{i:03d}.json').exists()]
    print(f'{args.samples} samples (sampler seed {sampler_seed}), {len(todo)} still to run', flush=True)
    args.slot = 'sample'
    tree, env = B.setup(args, VARIANTS)
    gate = threading.Semaphore(args.parallel)
    threads = []

    def finish(i, z):
        part = part_root / f's{i:03d}'
        res = {v: json.loads((part / f'{v}.json').read_text()) for v in VARIANTS
               if (part / f'{v}.json').exists()}
        if len(res) == len(VARIANTS):
            write_atomic(OUT / f's{i:03d}.json', json.dumps({'z': z, 'sampler_seed': sampler_seed, 'build': BUILD,
                                                              'emulator': emu, 'results': res}, indent=1))
            print(f'sample {i}: done {z}', flush=True)
        else:
            print(f'sample {i}: {len(res)} of {len(VARIANTS)} results, continues on the next start', flush=True)

    def run(i, z, roms):
        try:
            def save(v, result):
                if result:
                    write_atomic(part_root / f's{i:03d}' / f'{v}.json', json.dumps(result))
            if roms:
                R.run_all(roms, args.ares, args.run_jobs, 1800, on_result=save)
            finish(i, z)
        finally:
            gate.release()

    for i in todo:
        z = draw(sampler_seed, i)
        args.pad, args.dpad, args.heappad, args.seed = z['pad'], z['dpad'], z['heappad'], z['seed']
        gate.acquire()
        roms = {}
        for v in VARIANTS:
            if (part_root / f's{i:03d}' / f'{v}.json').exists():
                continue
            dest = ROMS / f's{i:03d}' / f'{v}.z64'
            ok = dest.with_suffix('.ok')
            if not (dest.exists() and ok.exists() and json.loads(ok.read_text()) == {'z': z, 'build': BUILD}):
                build_checked(tree, v, args, env, z, dest)
            roms[v] = dest
        t = threading.Thread(target=run, args=(i, z, roms))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()


if __name__ == '__main__':
    main()
