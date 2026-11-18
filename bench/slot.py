#!/usr/bin/env python3
"""Write a kernel into the fixed slot of a built ROM (TRIG_FUNC 9, bench/trig_slot.s).

  python3 bench/slot.py BASE.z64 BASE.elf KERNEL OUT.z64 --binutils DIR --clang DIR

KERNEL is a published kernel (Silas, S5C6_line, S5C6_code, S5C6_quantized) or
FORMS_FILE:KEY, a form of fit/forms.py or fit/variants.py output (generated
by bench/micro/gen.py).

The kernel is assembled, linked with trig_k at the slot's data address, and
its two functions are copied to their fixed offsets in the slot (a function
only branches inside itself, so it can move; its absolute references are to
trig_k only). The data words go to trig_k. The ROM header checksum (CIC 6102)
is then recalculated. All other bytes of the ROM stay the same.
"""
import argparse
import json
import struct
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
MARKER = b'TRIG-SLOT-MARKER'
SINCOS, SIN, DATA, SIZE = 0x000, 0x180, 0x300, 0x320
HAND = {  # name: (source, preprocessor defines or None, trig_k words)
    'Silas': (REPO / 'bench/trig_kernels.s', ['-DTRIG_FUNC=4', '-DTRIG_SINCOS=1'], []),
    'S5C6_line': (REPO / 'kernel/s5c6.s', None, [0x38c90dd0, 0xaa24fee4, 0xb19de6b5, 0x2280c3c2]),
    'S5C6_code': (REPO / 'kernel/s5c6_code.s', None, []),
    'S5C6_quantized': (REPO / 'kernel/s5c6_quantized.s', None, []),
}


def run(cmd, **kw):
    return subprocess.run([str(c) for c in cmd], check=True, capture_output=True, text=True, **kw).stdout


def n64_crc(rom):
    """The header checksum for CIC 6102 (seed 0xF8CA4DDC) over ROM 0x1000-0x101000."""
    seed = 0xF8CA4DDC
    t1 = t2 = t3 = t4 = t5 = t6 = seed
    words = struct.unpack('>262144I', rom[0x1000:0x101000])
    for d in words:
        if (t6 + d) & 0xFFFFFFFF < t6:
            t4 = (t4 + 1) & 0xFFFFFFFF
        t6 = (t6 + d) & 0xFFFFFFFF
        t3 ^= d
        r = ((d << (d & 0x1F)) | (d >> (32 - (d & 0x1F)))) & 0xFFFFFFFF if d & 0x1F else d
        t5 = (t5 + r) & 0xFFFFFFFF
        t2 = t2 ^ r if t2 > d else t2 ^ (t6 ^ d)
        t1 = (t1 + (t5 ^ d)) & 0xFFFFFFFF
    return (t6 ^ t4 ^ t3) & 0xFFFFFFFF, (t5 ^ t2 ^ t1) & 0xFFFFFFFF


def kernel_source(kernel, work, clang):
    """-> (assembly file, trig_k words)"""
    if kernel in HAND:
        src, defs, words = HAND[kernel]
        if defs is None:
            return src, words
        out = work / 'k.s'
        run([clang, '-E', '-P', '-x', 'assembler-with-cpp'] + defs + ['-o', out, src])
        return out, words
    forms, key = kernel.split(':', 1)
    out = work / 'k.s'
    run(['python3', REPO / 'bench/micro/gen.py', '--forms', REPO / forms, '--only', key, '--prefix', 'trig',
         '--extern-table', '--out', out])
    return out, json.loads(out.with_suffix('.table.json').read_text())


def slot_image(kernel, slot_addr, binutils, clang):
    tool = lambda n: Path(binutils) / f'mips-linux-gnu-{n}'
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        src, words = kernel_source(kernel, work, clang)
        run([tool('as'), '-EB', '-march=vr4300', '-mabi=32', '-mips3', '-G', '0', '-o', work / 'k.o', src])
        run([tool('ld'), '-Ttext=0x80000000', f'--defsym=trig_k=0x{slot_addr + DATA:08x}', '-e', '0',
             '-o', work / 'k.elf', work / 'k.o'])
        syms = {}
        for line in run([tool('nm'), '-S', work / 'k.elf']).splitlines():
            f = line.split()
            if len(f) == 4:
                syms[f[3]] = (int(f[0], 16), int(f[1], 16))
        run([tool('objcopy'), '-O', 'binary', '-j', '.text', work / 'k.elf', work / 'k.bin'])
        text = (work / 'k.bin').read_bytes()
    img = bytearray(SIZE)
    for name, off in (('trig_sincos', SINCOS), ('trig_sin', SIN)):
        addr, size = syms[name]
        if size > 0x180:
            raise SystemExit(f'{kernel}: {name} is {size} bytes, the slot has 0x180')
        img[off:off + size] = text[addr - 0x80000000:addr - 0x80000000 + size]
    for i, w in enumerate(words):
        img[DATA + 4 * i:DATA + 4 * i + 4] = w.to_bytes(4, 'big')
    return bytes(img), {n: syms[n][1] for n in ('trig_sincos', 'trig_sin')}, len(words) * 4


def write(base_rom, base_elf, kernel, out, binutils, clang):
    rom = bytearray(Path(base_rom).read_bytes())
    at = rom.find(MARKER)
    if at < 0 or rom.find(MARKER, at + 1) >= 0:
        raise SystemExit(f'{base_rom}: the slot marker must occur exactly once')
    rom_off = at - DATA
    slot_addr = None
    for line in run([Path(binutils) / 'mips-linux-gnu-nm', base_elf]).splitlines():
        f = line.split()
        if len(f) == 3 and f[2] == 'trig_slot':
            slot_addr = int(f[0], 16)
    img, sizes, data = slot_image(kernel, slot_addr, binutils, clang)
    rom[rom_off:rom_off + SIZE] = img
    if n64_crc(Path(base_rom).read_bytes()) != struct.unpack('>II', bytes(rom[0x10:0x18])):
        raise SystemExit(f'{base_rom}: header checksum is not CIC 6102')
    rom[0x10:0x18] = struct.pack('>II', *n64_crc(rom))
    Path(out).write_bytes(rom)
    return {'code bytes': sizes, 'data bytes': data, 'slot': f'0x{slot_addr:08x}'}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('base_rom')
    ap.add_argument('base_elf')
    ap.add_argument('kernel')
    ap.add_argument('out')
    ap.add_argument('--binutils', required=True)
    ap.add_argument('--clang', required=True, help='bin directory of clang (C preprocessor for Silas)')
    args = ap.parse_args()
    print(write(args.base_rom, args.base_elf, args.kernel, args.out, args.binutils, Path(args.clang) / 'clang'))


if __name__ == '__main__':
    main()
