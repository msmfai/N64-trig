#!/usr/bin/env python3
"""Build the timing ROM: every form of fit/forms.json plus the published kernels.

  python3 bench/micro/build.py --clang BIN_DIR --binutils BIN_DIR [--out work/micro]

The ROM contains no Nintendo code or data: libdragon's public-domain IPL3
(ipl3_compat.z64, IPL3_LICENSE.md), our startup code (crt0.s), the harness
(main.c) and the kernels. Run it with bench/micro/run.py.
"""
import argparse
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CFLAGS = ['-target', 'mips', '-mips2', '-mfpxx', '-mabi=32', '-G', '0', '-mhard-float', '-fno-PIC', '-mno-abicalls',
          '-ffreestanding', '-fno-builtin', '-O2', '-fno-common', '-fwrapv']
# hand-written kernels: (name, source, preprocessor defines, trig_k data words)
SHARED = ['Silas']          # also timed as one function: its trig_sincos for single calls
S5C4_K = [0x38c907e2, 0xaa2449da, 0xb19ddd5a, 0x3f800000]
HAND = [('Silas', REPO / 'bench/trig_kernels.s', ['-DTRIG_FUNC=4', '-DTRIG_SINCOS=1'], None),
        ('S5C6_line', REPO / 'kernel/s5c6.s', None, [0x38c90dd0, 0xaa24fee4, 0xb19de6b5, 0x2280c3c2]),
        ('S5C6_code', REPO / 'kernel/s5c6_code.s', None, None),
        ('S5C6_quantized', REPO / 'kernel/s5c6_quantized.s', None, None),
        ('S5C4_line', REPO / 'kernel/s5c4_line.s', None, S5C4_K),
        ('S5C4_pure', REPO / 'kernel/s5c4_code.s', None, None),
        ('S5C4_shared', REPO / 'kernel/s5c4_shared.s', None, S5C4_K)]


def run(cmd, **kw):
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--clang', type=Path, required=True)
    ap.add_argument('--binutils', type=Path, required=True)
    ap.add_argument('--out', type=Path, default=REPO / 'work/micro')
    ap.add_argument('--hardware', action='store_true',
                    help='results on the screen; no ares-only instructions are executed (for a console)')
    ap.add_argument('--forms', type=Path, nargs='+', default=[REPO / 'fit/forms.json'],
                    help='forms to generate (fit/forms.py, fit/variants.py output)')
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    clang = args.clang / 'clang'
    tool = lambda n: args.binutils / f'mips-linux-gnu-{n}'
    asm = [tool('as'), '-EB', '-march=vr4300', '-mabi=32', '-mips3', '-G', '0']

    run(['python3', HERE / 'gen.py', '--out', out / 'gen.s', '--forms'] + args.forms)
    ids = json.loads((out / 'gen.json').read_text())
    objs = []
    run(asm + ['-o', out / 'gen.o', out / 'gen.s'])
    objs.append(out / 'gen.o')
    for name, src, defs, words in HAND:
        s = src
        if defs is not None:                 # Silas lives in trig_kernels.s behind TRIG_FUNC
            s = out / f'{name}.s'
            run([clang, '-E', '-P', '-x', 'assembler-with-cpp'] + defs + ['-o', s, src])
        o = out / f'{name}.o'
        run(asm + ['-o', o, s])
        run([tool('objcopy'), '--redefine-sym', f'trig_sin=h_{name}_sin',
             '--redefine-sym', f'trig_sincos=h_{name}_sincos', '--redefine-sym', f'trig_k=h_{name}_k', o])
        objs.append(o)
        if words:                            # the kernel's 16-byte data line, under its own name
            ds = out / f'{name}_data.s'
            ds.write_text('    .section .rodata\n    .balign 16\n    .global h_' + name + '_k\nh_' + name + '_k:\n' +
                          ''.join(f'    .word   0x{w:08x}\n' for w in words))
            run(asm + ['-o', out / f'{name}_data.o', ds])
            objs.append(out / f'{name}_data.o')
    # (sin symbol, sincos symbol, name); NAME+shared: the kernel's trig_sincos also serves single calls
    entries = [(f'h_{n}_sin', f'h_{n}_sincos', n) for n, *_ in HAND] + \
              [(f'h_{n}_sincos', f'h_{n}_sincos', f'{n}+shared') for n in SHARED] + \
              [(f'g_{fid}_sin', f'g_{fid}_sincos', key) for fid, key in ids]
    run(['python3', HERE / 'hazards.py', '--binutils', args.binutils] + objs)   # refuse a kernel with a hazard
    (out / 'table.h').write_text(
        ''.join(f'extern float {sn}(int);\n' for sn, sc, _ in entries if sn != sc) +
        ''.join(f'extern _Complex float {sc}(int);\n' for _, sc, _ in entries if not _.endswith('+shared')) +
        'static const struct { const char *name; SinFn sin; ScFn sincos; } KERNELS[] = {\n' +
        ''.join(f'    {{ "{key.replace(" ", "_")}", ' + (f'(SinFn) {sn}' if sn == sc else sn) + f', {sc} }},\n'
                for sn, sc, key in entries) + '};\n')
    run([clang] + CFLAGS + (['-DMICRO_HW'] if args.hardware else []) +
        ['-I', out, '-I', HERE, '-c', '-o', out / 'main.o', HERE / 'main.c'])
    run(asm + ['-o', out / 'crt0.o', HERE / 'crt0.s'])
    run([tool('ld'), '-T', HERE / 'link.ld', '-Map', out / 'micro.map', '-o', out / 'micro.elf',
         out / 'crt0.o', out / 'main.o'] + objs)
    run([tool('objcopy'), '-O', 'binary', out / 'micro.elf', out / 'micro.bin'])
    body = (out / 'micro.bin').read_bytes()
    assert len(body) <= 0x100000, 'IPL3 compat loads 1 MiB'
    head = bytearray((HERE / 'ipl3_compat.z64').read_bytes()[:0x1000])
    head[0x20:0x34] = b'N64-TRIG MICRO'.ljust(20)
    rom = bytes(head) + body
    rom += bytes(max(0, 0x101000 - len(rom)))        # IPL3 reads a full MiB after the header
    (out / 'micro.z64').write_bytes(rom)
    print(out / 'micro.z64', len(entries), 'kernels')


if __name__ == '__main__':
    main()
