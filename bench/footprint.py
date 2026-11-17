#!/usr/bin/env python3
"""Static footprint and executed instruction counts of every kernel.

  python3 bench/footprint.py --binutils DIR [--clang DIR] [--elf-dir DIR] [--markdown]

Assembles kernel/*.s (and Silas from bench/trig_kernels.s, TRIG_FUNC 4, which
needs a C preprocessor: --clang DIR or cpp on PATH) with mips-linux-gnu-as,
disassembles them with mips-linux-gnu-objdump, and reports per function:
  bytes and 32-byte instruction-cache lines (the functions are 32-byte aligned),
  data read (bytes, 16-byte data-cache lines), FPU operations, registers written,
  and instructions executed per call: min / mean / max over all 65536 angles,
  found by running the function's integer control flow for every angle.
--elf-dir: also check that each kernel/ function is, instruction for
instruction, the code in the benchmark ROMs (work/HackerSM64-sincos/
build-<variant>-cyc/us_n64/sm64.elf), apart from relocated addresses.
"""
import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
KERNELS = [  # (label, source, cpp defines, functions, data bytes, benchmark variant)
    ('Silas', HERE / 'trig_kernels.s', ['-DTRIG_FUNC=4', '-DTRIG_SINCOS=1'], ('trig_sin', 'trig_sincos'), 0, 'asilas-sc'),
    ('S5C6 one cache line', REPO / 'kernel/s5c6.s', None, ('trig_sin', 'trig_sincos'), 16, 'abfskl-sc'),
    ('S5C6 pure code', REPO / 'kernel/s5c6_code.s', None, ('trig_sin', 'trig_sincos'), 0, 'abfsk-sc'),
    ('S5C6 one constant', REPO / 'kernel/s5c6_one.s', None, ('trig_sin', 'trig_sincos'), 0, 'aone-sc'),
]
FPU = ('mul.s', 'add.s', 'sub.s', 'sqrt.s', 'cvt.s.w', 'neg.s', 'mov.s', 'mtc1', 'lwc1')


def disasm(objdump, obj):
    """{function: [(word, mnemonic, operands, address)]}"""
    out, cur = {}, None
    text = subprocess.run([objdump, '-d', '--no-show-raw-insn', '-M', 'no-aliases', str(obj)],
                          capture_output=True, text=True, check=True).stdout
    raw = subprocess.run([objdump, '-d', str(obj)], capture_output=True, text=True, check=True).stdout
    words = {}
    for line in raw.splitlines():
        m = re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s', line)
        if m:
            words[int(m.group(1), 16)] = int(m.group(2), 16)
    for line in text.splitlines():
        m = re.match(r'^[0-9a-f]+ <([^>]+)>:', line)
        if m:
            cur = m.group(1)
            out[cur] = []
            continue
        m = re.match(r'^\s*([0-9a-f]+):\s+(\S+)\s*(.*)$', line)
        if m and cur:
            addr = int(m.group(1), 16)
            out[cur].append((words.get(addr), m.group(2), m.group(3), addr))
    # objdump runs a function on to the next symbol, alignment padding included:
    # cut each one at its symbol size (.size)
    sizes = {}
    for line in subprocess.run([objdump, '-t', str(obj)], capture_output=True, text=True, check=True).stdout.splitlines():
        f = line.split()
        if len(f) >= 2 and f[-1] in out:
            try:
                sizes[f[-1]] = int(f[-2], 16)
            except ValueError:
                pass
    return {k: v[:sizes[k] // 4] if sizes.get(k) else v for k, v in out.items()}


def run_paths(insns):
    """Executed instruction counts over all 65536 angles (integer control flow only)."""
    index = {a: i for i, (_, _, _, a) in enumerate(insns)}
    to_index = lambda s: index[int(s.split()[0], 16)]
    counts, fmul, fsqrt = [], [], []
    for angle in range(65536):
        nm = nq = 0
        reg = {'a0': angle, 'zero': 0}
        pc, n, pending = 0, 0, None
        while True:
            _, mn, ops, _ = insns[pc]
            n += 1
            nm += mn == 'mul.s'
            nq += mn == 'sqrt.s'
            args = [a.strip().lstrip('$') for a in ops.split(',')] if ops else []
            nxt = pc + 1
            target = None
            g = lambda r: reg.get(r, 0)
            imm = lambda s: int(s, 0)
            if mn == 'addiu':
                reg[args[0]] = (g(args[1]) + imm(args[2])) & 0xFFFFFFFF
            elif mn == 'addu':
                reg[args[0]] = (g(args[1]) + g(args[2])) & 0xFFFFFFFF
            elif mn == 'subu':
                reg[args[0]] = (g(args[1]) - g(args[2])) & 0xFFFFFFFF
            elif mn == 'andi':
                reg[args[0]] = g(args[1]) & imm(args[2])
            elif mn == 'ori':
                reg[args[0]] = g(args[1]) | imm(args[2])
            elif mn == 'xor':
                reg[args[0]] = g(args[1]) ^ g(args[2])
            elif mn == 'lui':
                reg[args[0]] = (imm(args[1]) << 16) & 0xFFFFFFFF
            elif mn == 'sll':
                reg[args[0]] = (g(args[1]) << imm(args[2])) & 0xFFFFFFFF
            elif mn == 'srl':
                reg[args[0]] = g(args[1]) >> imm(args[2])
            elif mn == 'sra':
                v = g(args[1])
                v = v - (1 << 32) if v & 0x80000000 else v
                reg[args[0]] = (v >> imm(args[2])) & 0xFFFFFFFF
            elif mn in ('beq', 'bne'):
                eq = g(args[0]) == g(args[1])
                if eq == (mn == 'beq'):
                    target = to_index(args[2])
            elif mn in ('beqz', 'bnez', 'blez', 'bgtz', 'bltz', 'bgez'):
                v = g(args[0])
                s = v - (1 << 32) if v & 0x80000000 else v
                take = {'beqz': s == 0, 'bnez': s != 0, 'blez': s <= 0, 'bgtz': s > 0,
                        'bltz': s < 0, 'bgez': s >= 0}[mn]
                if take:
                    target = to_index(args[1])
            elif mn == 'b':
                target = to_index(args[0])
            elif mn == 'jr':
                target = -1
            if pending is not None:          # this was a delay slot
                if pending == -1:
                    break
                pc = pending
                pending = None
                continue
            if target is not None:
                pending = target
            pc = nxt
        counts.append(n)
        fmul.append(nm)
        fsqrt.append(nq)
    return counts, fmul, fsqrt


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--binutils', type=Path, required=True, help='directory with mips-linux-gnu-as/objdump')
    ap.add_argument('--clang', type=Path, help='bin directory of clang, used as the C preprocessor for Silas')
    ap.add_argument('--elf-dir', type=Path, help='HackerSM64-sincos tree with build-<variant>-cyc ROMs')
    ap.add_argument('--markdown', action='store_true')
    args = ap.parse_args()
    as_ = args.binutils / 'mips-linux-gnu-as'
    objdump = str(args.binutils / 'mips-linux-gnu-objdump')
    cpp = [str(args.clang / 'clang'), '-E', '-P', '-x', 'assembler-with-cpp'] if args.clang else ['cpp', '-P']
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for label, src, defines, funcs, data, variant in KERNELS:
            asm = src
            if defines is not None:
                asm = Path(tmp) / (src.stem + '.pp.s')
                text = subprocess.run(cpp + defines + [str(src)], capture_output=True, text=True, check=True).stdout
                asm.write_text(text)
            obj = Path(tmp) / (label.replace(' ', '_') + '.o')
            subprocess.run([str(as_), '-march=vr4300', '-mabi=32', '-o', str(obj), str(asm)], check=True)
            code = disasm(objdump, obj)
            if args.elf_dir:
                elf = args.elf_dir / f'build-{variant}-cyc/us_n64/sm64.elf'
                rom = disasm(objdump, elf)
                for f in funcs:
                    a = [(m, o) for _, m, o, _ in code[f]]
                    b = [(m, o) for _, m, o, _ in rom[f]]
                    norm = lambda l: [(m, re.sub(r'0x[0-9a-f]+(?= <)|[0-9a-f]{8} <[^>]*>|%\w+\([^)]*\)', 'X', o)
                                       if m in ('lui', 'addiu', 'beqz', 'bnez', 'b', 'beq', 'bne') else o)
                                      for m, o in l]
                    same = len(a) == len(b) and all(
                        x == y or (x[0] == y[0] and x[0] in ('lui', 'addiu', 'beqz', 'bnez', 'b', 'beq', 'bne'))
                        for x, y in zip(norm(a), norm(b)))
                    print(f'{label} {f}: {"same as" if same else "DIFFERS FROM"} the benchmarked code ({elf.parent.parent.name})')
            for f in funcs:
                ins = code[f]
                fp = {k: sum(1 for _, m, _, _ in ins if m == k) for k in FPU}
                written = sorted({o.split(',')[0].strip() for _, m, o, _ in ins
                                  if o and m not in ('jr', 'beqz', 'bnez', 'b', 'nop', 'mtc1') and not m.startswith('b')}
                                 | {o.split(',')[1].strip() for _, m, o, _ in ins if m == 'mtc1'})
                ex, fm, fq = run_paths(ins)
                rows.append({
                    'kernel': label, 'function': f, 'instructions': len(ins), 'bytes': 4 * len(ins),
                    'icache_lines': -(-4 * len(ins) // 32),
                    'data_bytes': data if data and f else 0, 'dcache_lines': 1 if data else 0,
                    'executed_min': min(ex), 'executed_mean': sum(ex) / len(ex), 'executed_max': max(ex),
                    'mul.s executed': f'{min(fm)}-{max(fm)}' if min(fm) != max(fm) else str(fm[0]),
                    'sqrt.s executed': f'{min(fq)}-{max(fq)}' if min(fq) != max(fq) else str(fq[0]),
                    'registers': ' '.join(sorted(r for r in written if r != 'zero')),
                })
    keys = ['bytes', 'icache_lines', 'data_bytes', 'dcache_lines', 'executed_min', 'executed_mean',
            'executed_max', 'mul.s executed', 'sqrt.s executed', 'registers']
    if args.markdown:
        print('| kernel | function | ' + ' | '.join(keys) + ' |')
        print('|---' * (len(keys) + 2) + '|')
        for r in rows:
            print(f"| {r['kernel']} | {r['function']} | " + ' | '.join(
                f'{r[k]:.1f}' if isinstance(r[k], float) else str(r[k]) for k in keys) + ' |')
    else:
        for r in rows:
            print(f"{r['kernel']:22}{r['function']:12}" + '  '.join(
                f'{k}={r[k]:.1f}' if isinstance(r[k], float) else f'{k}={r[k]}' for k in keys))


if __name__ == '__main__':
    main()
