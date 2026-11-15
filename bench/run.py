#!/usr/bin/env python3
"""Run the trig benchmark ROMs in ares and compare table and call builds.

  python3 bench/run.py [--variants kernels] [--ares PATH] [--jobs 4]

Each ROM plays SM64's seven attract-mode demos with no controller. Needs ares
v148 or later (ares-emu.net); each run gets a fresh settings file with Homebrew
Mode on, no video, audio or input, so your own ares settings are not touched.
In Homebrew Mode the ROM uses ares's emux extension: it fast-forwards, prints
a progress line per demo and, when done, all of its results as one line of hex
on ares's terminal, then quits ares. This script reads only that output.

Times are the game's own HackerSM64 profiler figures: microseconds of
game-thread CPU time per frame (PROFILER_TIME_TOTAL, audio preemption already
excluded), measured in emulated time, so a slow or busy host does not change
them. Cache events are ares's own counters for the whole machine.

A pair (table build, call build) computes bit-identical values, so it plays
the same game; a hash of Mario's position over every measured frame checks it.
"""
import argparse
import json
import os
import platform
import selectors
import shutil
import signal
import struct
import subprocess
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
LEVELS = {30: 'bitdw', 24: 'wf', 5: 'ccm', 4: 'bbh', 12: 'jrb', 7: 'hmc', 27: 'pss'}
TB_MAGIC = 0x54524947
TB_DEMOS = 8
HEADER = struct.Struct('>IIIIIiII')
DEMO = struct.Struct('>IIQIIIIQQIIII')
CPU_HZ = 93.75e6
FRAME_US = 1e6 / 30
PAIRS = [('tsilas', 'silas'), ('tbfsk', 'bfsk'), ('tasilas', 'asilas'), ('tabfsk', 'abfsk'),
         ('tabfskl', 'abfskl'), ('talutx', 'alutx')]
GROUPS = {'kernels': ['tasilas', 'asilas', 'tabfsk', 'abfsk', 'tabfskl', 'abfskl', 'talutx', 'alutx'],
          'c': ['tsilas', 'silas', 'tbfsk', 'bfsk']}
SETTINGS = """Video
  Driver: None
Audio
  Driver: None
Input
  Driver: None
  Defocus: Allow
Boot
  Fast: false
  Debugger: false
  AwaitGDBClient: false
General
  Rewind: false
  RunAhead: false
  HomebrewMode: true
  ForceInterpreter: true
  NoFilePrompt: true
DebugServer
  Enabled: false
Nintendo64
  ExpansionPak: true
Paths
  Saves: {saves}/
"""


def default_ares():
    mac = Path('/Applications/ares.app/Contents/MacOS/ares')
    if platform.system() == 'Darwin' and mac.exists():
        return str(mac)
    return shutil.which('ares') or 'ares'


def parse(hexline):
    raw = bytes.fromhex(hexline)
    magic, func, use, counting, done, demo, demos_run, _ = HEADER.unpack_from(raw, 0)
    demos = []
    for i in range(TB_DEMOS):
        (level, frames, cycles, max_cycles, calls, state, _, preempted, audio,
         d_misses, d_writes, i_misses, emux) = DEMO.unpack_from(raw, HEADER.size + i * DEMO.size)
        if frames:
            demos.append({'level': LEVELS.get(level, str(level)), 'frames': frames, 'cycles': cycles,
                          'preempted': preempted, 'audio': audio, 'max_cycles': max_cycles, 'calls': calls,
                          'hash': f'{state:08x}', 'emux': emux, 'd_misses': d_misses,
                          'd_writes': d_writes, 'i_misses': i_misses})
    return {'magic_ok': magic == TB_MAGIC, 'func': func, 'use': use, 'counting': counting, 'done': done,
            'demo': demo, 'demos_run': demos_run, 'demos': demos}


class Run:
    """One ares process for one ROM, read line by line."""

    def __init__(self, variant, rom, ares, tmp):
        self.variant, self.result, self.buf = variant, None, b''
        work = Path(tmp) / variant
        (work / 'saves').mkdir(parents=True)
        (work / 'settings.bml').write_text(SETTINGS.format(saves=work / 'saves'))
        self.log = (work / 'ares.log').open('wb')
        self.proc = subprocess.Popen([ares, '--settings-file', str(work / 'settings.bml'), '--kiosk', str(rom)],
                                     stdout=subprocess.PIPE, stderr=self.log, start_new_session=True)
        self.start = time.time()

    def feed(self, chunk):
        self.buf += chunk
        while b'\n' in self.buf:
            line, self.buf = self.buf.split(b'\n', 1)
            i = line.find(b'TRIGBENCH ')
            if i < 0:
                continue
            text = line[i + 10:].decode('ascii', 'replace').strip()
            if text.startswith('demo '):
                print(f'{time.time() - self.start:5.0f}s {self.variant}: demo {int(text[5:]) + 1} of 7', flush=True)
            else:
                self.result = parse(text)

    def stop(self):
        if self.proc.poll() is None:
            try:
                self.proc.wait(timeout=15)       # the ROM asked ares to quit
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(self.proc.pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    pass
                self.proc.wait(timeout=15)
        self.log.close()


def run_all(roms, ares, jobs, timeout):
    results = {}
    pending = list(roms.items())
    with tempfile.TemporaryDirectory(prefix='trigbench-') as tmp:
        sel = selectors.DefaultSelector()
        active = {}
        while pending or active:
            while pending and len(active) < jobs:
                v, rom = pending.pop(0)
                r = Run(v, rom, ares, tmp)
                os.set_blocking(r.proc.stdout.fileno(), False)
                sel.register(r.proc.stdout, selectors.EVENT_READ, r)
                active[v] = r
            for key, _ in sel.select(timeout=1.0):
                r = key.data
                chunk = r.proc.stdout.read()     # None: nothing yet; b'': ares has exited
                if chunk:
                    r.feed(chunk)
                if r.result is not None or chunk == b'':
                    sel.unregister(r.proc.stdout)
                    r.stop()
                    results[r.variant] = r.result
                    if r.result is None:
                        print(f'{r.variant}: ares exited without results (see its log in the temp dir)')
                    del active[r.variant]
            for v, r in list(active.items()):
                if time.time() - r.start > timeout:
                    print(f'{v}: no results after {timeout} s, stopping it')
                    sel.unregister(r.proc.stdout)
                    try:
                        os.killpg(r.proc.pid, signal.SIGTERM)
                    except (ProcessLookupError, PermissionError):
                        pass
                    r.stop()
                    results[v] = None
                    del active[v]
    return results


def usec(cycles, frames):
    return cycles / frames / CPU_HZ * 1e6


def total(r):
    d = r['demos']
    return (sum(x['cycles'] - x['preempted'] for x in d), sum(x['frames'] for x in d),
            sum(x['calls'] for x in d), sum(x['audio'] for x in d))


def report(results):
    print('\ngame-thread CPU time per frame (HackerSM64 profiler TOTAL), mean over the measured demo frames')
    print(f"  {'build':11}{'CPU us':>9}{'of 33.3 ms':>12}{'audio us':>10}")
    for v, r in results.items():
        if r is None:
            continue
        cpu, f, calls, audio = total(r)
        extra = f'   {calls / f:.0f} sins+coss calls per frame' if r['counting'] else ''
        print(f'  {v:11}{usec(cpu, f):9.0f}{100 * usec(cpu, f) / FRAME_US:11.1f}%{usec(audio, f):10.0f}{extra}')
    for table, call in PAIRS:
        if not results.get(table) or not results.get(call):
            continue
        a_demos, b_demos = results[table]['demos'], results[call]['demos']
        same = [a['hash'] == b['hash'] and a['frames'] == b['frames'] for a, b in zip(a_demos, b_demos)]
        same = same if len(a_demos) == len(b_demos) else [False]
        print(f"\n{call} (calls) against {table} (table lookups of the same values): "
              + ('identical gameplay in every demo' if all(same) else 'GAMEPLAY DIFFERS: not comparable'))
        print(f"  {'demo':7}{'frames':>7}{'table us':>10}{'calls us':>10}{'difference':>17}{'  same game':>11}")
        for a, b, ok in zip(a_demos, b_demos, same):
            ta = usec(a['cycles'] - a['preempted'], a['frames'])
            tb = usec(b['cycles'] - b['preempted'], b['frames'])
            print(f"  {a['level']:7}{a['frames']:7}{ta:10.0f}{tb:10.0f}{tb - ta:+9.0f} {100 * (tb / ta - 1):+5.2f}%"
                  f"{'yes' if ok else 'NO':>11}")
        (ca, fa, na, _), (cb, fb, _, _) = total(results[table]), total(results[call])
        ta, tb = usec(ca, fa), usec(cb, fb)
        line = f"  {'all':7}{fa:7}{ta:10.0f}{tb:10.0f}{tb - ta:+9.0f} {100 * (tb / ta - 1):+5.2f}%"
        if results[table]['counting'] and na:
            line += f'   {(cb - ca) / na / CPU_HZ * 1e6:+.2f} us per call over {na / fa:.0f} calls per frame'
        print(line)
        cache_report(results[table], results[call])


def cache_report(table, call):
    """Cache events per frame and the miss cost at which the pair would tie.

    ares charges flat costs: 40 cycles per D-cache fill and per write-back, 48
    per I-cache fill. Taking those out of the measured difference leaves what
    the calls cost in instructions; the table's extra misses must cost that
    much for the table to lose. Time compared: game thread plus audio thread,
    since the misses are counted on every thread."""
    if not all(d.get('emux') for r in (table, call) for d in r['demos']):
        print('  (no cache counts: ares did not answer emux; needs Homebrew Mode)')
        return

    def per_frame(r):
        d = r['demos']
        f = sum(x['frames'] for x in d)
        return ({k: sum(x[k] for x in d) / f for k in ('d_misses', 'd_writes', 'i_misses')},
                sum(x['cycles'] - x['preempted'] + x['audio'] for x in d) / f)

    (ma, ta), (mb, tb) = per_frame(table), per_frame(call)
    print(f"  cache events per frame  {'table':>9}{'calls':>9}{'difference':>12}")
    for k, name in (('d_misses', 'D misses'), ('d_writes', 'D writebacks'), ('i_misses', 'I misses')):
        print(f'  {name:22}{ma[k]:9.0f}{mb[k]:9.0f}{mb[k] - ma[k]:+12.0f}')
    miss = 40 * (mb['d_misses'] - ma['d_misses'] + mb['d_writes'] - ma['d_writes']) \
        + 48 * (mb['i_misses'] - ma['i_misses'])
    dt = tb - ta
    work = dt - miss
    print(f'  calls minus table, cycles per frame (game + audio threads): {dt:+.0f} total = '
          f"{miss:+.0f} in cache misses at ares's cost + {work:+.0f} in instructions")
    if miss < 0 < work:
        k = work / -miss
        print(f'  the two tie when a miss costs {k:.2f}x what ares charges: '
              f'{40 * k:.0f} cycles per D-cache line, {48 * k:.0f} per I-cache line')
    elif miss >= 0:
        print('  the calls do not save misses here, so no miss cost makes them win')
    else:
        print('  the calls win at any miss cost')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--variants', nargs='+', default=['kernels'])
    ap.add_argument('--hsm64', type=Path, default=REPO / 'work/HackerSM64', help='HackerSM64 tree (bench/build.py)')
    ap.add_argument('--suffix', default='', help='build directory suffix, e.g. --suffix=-count')
    ap.add_argument('--ares', default=default_ares())
    ap.add_argument('--jobs', type=int, default=4, help='ares processes at once')
    ap.add_argument('--timeout', type=float, default=1800, help='seconds per ROM')
    ap.add_argument('--out', type=Path, default=REPO / 'work/results.json')
    args = ap.parse_args()
    variants = [w for v in args.variants for w in GROUPS.get(v, [v])]
    roms = {v: args.hsm64 / f'build-{v}{args.suffix}' / 'us_n64/sm64.z64' for v in variants}
    missing = [str(p) for p in roms.values() if not p.exists()]
    if missing:
        raise SystemExit('not built: ' + ', '.join(missing))
    results = run_all(roms, args.ares, args.jobs, args.timeout)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=1))
    print(f'results: {args.out}')
    report(results)
    if any(r is None for r in results.values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
