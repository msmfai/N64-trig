#!/usr/bin/env python3
"""Check kernel code for VR4300 hazards.

  python3 bench/micro/hazards.py --binutils DIR FILE.o|FILE.elf [...]

Reports, for every function in the files:
  mul-after-mul    a multiplication directly after a multiplication (multiply erratum)
  mul-in-delay     a multiplication in a branch or jump delay slot (multiply erratum)
  load-use         a register used by the instruction directly after the mtc1 or lwc1 that writes it
Exit status 1 if anything is found.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

MUL = re.compile(r'^(mul\.[sd]|mult|multu|dmult|dmultu|mul)$')
BRANCH = re.compile(r'^(b|bal|beq|bne|beqz|bnez|bgez|bgtz|blez|bltz|bc1[tf]|j|jal|jr|jalr)(l)?$')


def check(path, binutils):
    out = subprocess.run([str(Path(binutils) / 'mips-linux-gnu-objdump'), '-d', '-M', 'no-aliases', str(path)],
                         capture_output=True, text=True, check=True).stdout
    found, fn, prev = [], None, None
    for line in out.splitlines():
        m = re.match(r'^[0-9a-f]+ <(.+)>:$', line)
        if m:
            fn, prev = m.group(1), None
            continue
        m = re.match(r'^\s*([0-9a-f]+):\s+[0-9a-f]{8}\s+(\S+)\s*(.*)$', line)
        if not m:
            continue
        addr, op, args = m.group(1), m.group(2), m.group(3).replace(' ', '')
        regs = re.findall(r'\$?(f\d+|[a-z]\d|zero|at|v[01]|ra|sp)', args)
        if prev:
            pop, pargs = prev
            if MUL.match(op) and MUL.match(pop):
                found.append(f'{fn} {addr}: mul-after-mul')
            if MUL.match(op) and BRANCH.match(pop):
                found.append(f'{fn} {addr}: mul-in-delay')
            if pop in ('mtc1', 'lwc1'):
                dst = re.findall(r'f\d+', pargs)
                dst = dst[0] if dst else None
                if dst and dst in regs[1:] + ([regs[0]] if op in ('swc1', 'mfc1') else []):
                    found.append(f'{fn} {addr}: load-use of {dst} after {pop}')
        prev = (op, args)
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--binutils', required=True)
    ap.add_argument('files', nargs='+')
    args = ap.parse_args()
    bad = [f for p in args.files for f in check(p, args.binutils)]
    print('\n'.join(bad) if bad else 'no hazards')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
