#!/usr/bin/env python3
"""Make and apply BPS patches (the format of Rom Patcher JS and Floating IPS).

  python3 bench/hardware/bps.py create SOURCE TARGET PATCH
  python3 bench/hardware/bps.py apply SOURCE PATCH OUT

create: the patch copies every run of 32 bytes or more that it finds in the
source (SourceRead at the same position, SourceCopy from another position),
and stores only the remaining bytes. apply: checks the CRC-32 of the source,
the result and the patch, as every BPS patcher does.
"""
import sys
import zlib
from pathlib import Path

K = 32                                   # shortest copied run
STEP = 4                                 # source index granularity


def enc_num(n):
    out = bytearray()
    while True:
        x = n & 0x7F
        n >>= 7
        if n == 0:
            out.append(0x80 | x)
            return bytes(out)
        out.append(x)
        n -= 1


def dec_num(b, i):
    n, shift = 0, 1
    while True:
        x = b[i]
        i += 1
        n += (x & 0x7F) * shift
        if x & 0x80:
            return n, i
        shift <<= 7
        n += shift


def create(src, tgt):
    index = {}
    for p in range(0, len(src) - K + 1, STEP):
        index.setdefault(src[p:p + K], p)
    out = bytearray(b'BPS1' + enc_num(len(src)) + enc_num(len(tgt)) + enc_num(0))
    lit = bytearray()
    src_rel = 0                          # SourceCopy offsets are relative to the previous copy's end

    def flush():
        if lit:
            out.extend(enc_num((len(lit) - 1) << 2 | 1))
            out.extend(lit)
            lit.clear()

    t, n = 0, len(tgt)
    while t < n:
        # SourceRead: the same bytes at the same position
        run = 0
        while t + run < n and t + run < len(src) and src[t + run] == tgt[t + run]:
            run += 1
        if run >= K:
            flush()
            out.extend(enc_num((run - 1) << 2 | 0))
            t += run
            continue
        p = index.get(tgt[t:t + K]) if t + K <= n else None
        if p is None:
            lit.append(tgt[t])
            t += 1
            continue
        run = K
        while t + run < n and p + run < len(src) and src[p + run] == tgt[t + run]:
            run += 1
        flush()
        out.extend(enc_num((run - 1) << 2 | 2))
        d = p - src_rel
        out.extend(enc_num((abs(d) << 1) | (d < 0)))
        src_rel = p + run
        t += run
    flush()
    out.extend(zlib.crc32(src).to_bytes(4, 'little'))
    out.extend(zlib.crc32(tgt).to_bytes(4, 'little'))
    out.extend(zlib.crc32(out).to_bytes(4, 'little'))
    return bytes(out)


def apply(src, patch):
    if patch[:4] != b'BPS1':
        raise SystemExit('not a BPS patch')
    if zlib.crc32(patch[:-4]) != int.from_bytes(patch[-4:], 'little'):
        raise SystemExit('patch CRC mismatch')
    if zlib.crc32(src) != int.from_bytes(patch[-12:-8], 'little'):
        raise SystemExit('wrong source ROM (CRC-32 mismatch)')
    i = 4
    ssize, i = dec_num(patch, i)
    tsize, i = dec_num(patch, i)
    msize, i = dec_num(patch, i)
    i += msize
    out = bytearray()
    src_rel = tgt_rel = 0
    end = len(patch) - 12
    while i < end:
        d, i = dec_num(patch, i)
        cmd, length = d & 3, (d >> 2) + 1
        if cmd == 0:
            out.extend(src[len(out):len(out) + length])
        elif cmd == 1:
            out.extend(patch[i:i + length])
            i += length
        else:
            o, i = dec_num(patch, i)
            o = -(o >> 1) if o & 1 else o >> 1
            if cmd == 2:
                src_rel += o
                out.extend(src[src_rel:src_rel + length])
                src_rel += length
            else:
                tgt_rel += o
                for _ in range(length):
                    out.append(out[tgt_rel])
                    tgt_rel += 1
    if len(out) != tsize or zlib.crc32(out) != int.from_bytes(patch[-8:-4], 'little'):
        raise SystemExit('result CRC mismatch')
    return bytes(out)


def main():
    if len(sys.argv) != 5 or sys.argv[1] not in ('create', 'apply'):
        raise SystemExit(__doc__)
    a, b, c = (Path(x) for x in sys.argv[2:])
    if sys.argv[1] == 'create':
        c.write_bytes(create(a.read_bytes(), b.read_bytes()))
    else:
        c.write_bytes(apply(a.read_bytes(), b.read_bytes()))


if __name__ == '__main__':
    main()
