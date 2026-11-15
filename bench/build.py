#!/usr/bin/env python3
"""Build the trig benchmark ROMs on HackerSM64.

  python3 bench/build.py --baserom PATH [--variants kernels] [--clang BIN_DIR]

First run: clones HackerSM64 at the pinned commit into work/HackerSM64 (or
--hsm64), copies your US base ROM in, applies hsm64-bench.patch and copies the
benchmark sources to src/game. Later runs reuse the tree; nothing is deleted.
Each variant is built into work/HackerSM64/build-<variant>/us_n64/sm64.z64.
The "-sc" variants (group sincos) need the call sites converted to sincoss()
(hsm64-sincos.patch), so they get their own tree, work/HackerSM64-sincos,
with both patches; vanilla-sc is the table baseline from that same source.

Toolchain: by default HackerSM64's own (a MIPS gcc on PATH, see its README).
--clang BIN_DIR builds with COMPILER=clang instead; the published results were
built that way (clang 21). HackerSM64 still runs its hand-written assembly
through a MIPS gcc, so this script then puts mips-gcc-shim on PATH as
mips-linux-gnu-gcc; GNU binutils (mips-linux-gnu-as, -ld, -objcopy) must be on
PATH, or give their directory with --binutils.

Variants, as (TRIG_FUNC, TRIG_USE): a "t" prefix is the table build of the
same values (sins/coss stay table lookups, the table is refilled at boot from
the kernel), the other is the call build. Compare only the two of a pair.
A "-sc" variant is the call build with sin and cos of one angle from one
trig_sincos call; compare it with vanilla-sc.
Your base ROM and the built ROMs are Nintendo's; do not distribute them.
"""
import argparse
import os
import platform
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
UPSTREAM = 'https://github.com/HackerN64/HackerSM64.git'
PINNED = '3be00d2f3cf4d1c73e21bf14ae02bbb5e89fcb94'  # 2026-11-11, the results' tree
# variant: (TRIG_FUNC, TRIG_USE); "-sc" variants also TRIG_SINCOS=1 (sincos tree)
VARIANTS = {
    'vanilla': (0, 0),
    # C versions (trig_impl.c)
    'tsilas': (1, 0), 'silas': (1, 1), 'tbfsk': (2, 0), 'bfsk': (2, 1),
    # hand-written kernels (trig_kernels.s)
    'tasilas': (4, 0), 'asilas': (4, 1),     # Silas
    'tabfsk': (5, 0), 'abfsk': (5, 1),       # S5C6, every constant built in code
    'tabfskl': (6, 0), 'abfskl': (6, 1),     # S5C6, four constants loaded from one line
    'talutx': (7, 0), 'alutx': (7, 1),       # LUTX16
    # combined sin+cos at the converted call sites (hsm64-sincos.patch)
    'vanilla-sc': (0, 0), 'asilas-sc': (4, 1), 'abfsk-sc': (5, 1), 'abfskl-sc': (6, 1), 'alutx-sc': (7, 1),
}
GROUPS = {'kernels': ['tasilas', 'asilas', 'tabfsk', 'abfsk', 'tabfskl', 'abfskl', 'talutx', 'alutx'],
          'c': ['tsilas', 'silas', 'tbfsk', 'bfsk'],
          'sincos': ['vanilla-sc', 'asilas-sc', 'abfsk-sc', 'abfskl-sc', 'alutx-sc']}
SOURCES = ('trig_impl.c', 'trig_bench.c', 'trig_bench.h', 'trig_kernels.s')


def run(cmd, **kw):
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def sincos_tree(tree):
    return tree.with_name(tree.name + '-sincos')


def prepare(tree, baserom, patches=('hsm64-bench.patch',)):
    if not tree.exists():
        tree.parent.mkdir(parents=True, exist_ok=True)
        run(['git', 'clone', '-q', UPSTREAM, tree])
        run(['git', '-C', tree, 'checkout', '-q', PINNED])
    if not (tree / 'baserom.us.z64').exists():
        if baserom is None:
            raise SystemExit('first build: give --baserom (a US Super Mario 64 ROM, .z64)')
        shutil.copy2(baserom, tree / 'baserom.us.z64')
    for name in patches:
        patch = HERE / name
        applied = subprocess.run(['git', '-C', str(tree), 'apply', '--reverse', '--check', str(patch)],
                                 capture_output=True).returncode == 0
        if not applied:
            run(['git', '-C', tree, 'apply', patch])
    for name in SOURCES:
        shutil.copy2(HERE / name, tree / 'src/game' / name)
    shutil.copy2(REPO / 'fit/coeffs.h', tree / 'src/game/trig_coeffs.h')


def clang_shims(clang, shims):
    """A PATH directory: clang/clang++ from BIN_DIR, the host C compiler as
    gcc/g++ (for HackerSM64's host tools), mips-gcc-shim as mips-linux-gnu-gcc."""
    shims.mkdir(parents=True, exist_ok=True)
    if platform.system() == 'Darwin':     # Apple's: other compilers on PATH may not link there
        host_cc, host_cxx = '/usr/bin/cc', '/usr/bin/c++'
    else:
        host_cc, host_cxx = shutil.which('gcc') or shutil.which('cc'), shutil.which('g++') or shutil.which('c++')
    for name, target in (('clang', clang / 'clang'), ('clang++', clang / 'clang++'),
                         ('gcc', host_cc), ('g++', host_cxx)):
        link = shims / name
        if link.is_symlink() and os.readlink(link) != str(target):
            link.unlink()                    # a link this script made earlier, now re-pointed
        if not link.is_symlink() and target:
            link.symlink_to(target)
    shutil.copy2(HERE / 'mips-gcc-shim', shims / 'mips-linux-gnu-gcc')
    (shims / 'mips-linux-gnu-gcc').chmod(0o755)


def build(tree, variant, args, env):
    func, use = VARIANTS[variant]
    sincos = variant.endswith('-sc')
    if sincos:
        tree = sincos_tree(tree)
    out = f'build-{variant}' + ('-count' if args.count else '') + (f'-pad{args.pad}' if args.pad else '')
    cmd = [args.make, '-C', tree, 'VERSION=us', f'BUILD_DIR_BASE={out}', 'TRIG_BENCH=1',
           f'TRIG_FUNC={func}', f'TRIG_USE={use}', 'TRIG_QUANT=1', f'TRIG_COUNT={int(args.count)}',
           f'TRIG_PAD={args.pad}', f'TRIG_SINCOS={int(sincos)}', f'-j{args.jobs}']
    if args.clang:
        cmd.insert(3, 'COMPILER=clang')
    log = tree / f'{out}.log'
    with log.open('w') as f:
        result = subprocess.run([str(c) for c in cmd], env=env, stdout=f, stderr=subprocess.STDOUT)
    if result.returncode:
        raise SystemExit(f'{variant}: build failed, see {log}')
    print(tree / out / 'us_n64/sm64.z64')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--variants', nargs='+', default=['kernels'], choices=list(VARIANTS) + list(GROUPS))
    ap.add_argument('--baserom', type=Path, help='US Super Mario 64 ROM (.z64), needed for the first build')
    ap.add_argument('--hsm64', type=Path, default=REPO / 'work/HackerSM64', help='HackerSM64 tree')
    ap.add_argument('--clang', type=Path, help='bin directory of a clang with MIPS targets: build with clang')
    ap.add_argument('--binutils', type=Path, help='directory with mips-linux-gnu-as/ld/objcopy, put on PATH')
    ap.add_argument('--count', action='store_true', help='count sins/coss calls (timings are then not clean)')
    ap.add_argument('--pad', type=int, default=0, help='layout control: bytes of padding before trig_sin')
    ap.add_argument('--make', default='gmake' if platform.system() == 'Darwin' else 'make')
    ap.add_argument('--jobs', type=int, default=max(1, (os.cpu_count() or 4) - 2))
    args = ap.parse_args()
    tree = args.hsm64.resolve()
    variants = [w for v in args.variants for w in GROUPS.get(v, [v])]
    prepare(tree, args.baserom)
    if any(v.endswith('-sc') for v in variants):
        prepare(sincos_tree(tree), args.baserom or tree / 'baserom.us.z64',
                ('hsm64-bench.patch', 'hsm64-sincos.patch'))
    path = os.environ['PATH']
    if args.binutils:
        path = f'{args.binutils}:{path}'
    if args.clang:
        shims = tree.parent / 'clang-shims'
        clang_shims(args.clang.resolve(), shims)
        path = f'{shims}:{path}'
    env = dict(os.environ, PATH=path)
    for v in variants:
        build(tree, v, args, env)


if __name__ == '__main__':
    main()
