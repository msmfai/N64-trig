#!/usr/bin/env python3
"""Generate VR4300 assembly kernels for the polynomial forms of fit/forms.py.

  python3 bench/micro/gen.py [--forms fit/forms.json] [--out DIR]

For each form, two leaf functions (GNU as, o32):
  g_<id>_sincos   angle in $a0 -> sine in $f0, cosine in $f2
  g_<id>_sin      angle in $a0 -> sine in $f0 (the cosine is g_<id>_sin(angle + 0x4000))

The fold is the one of kernel/*.s: t = a + 0x2000, x = (t & 0x3fff) - 0x2000;
bit 14 of t selects the cosine polynomial, bit 15 negates.

The body of each function is a dataflow graph (coefficient loads with lui,
and ori only where the low 16 bits are not zero; Horner steps in x²;
sqrt.s for the sqrt forms), scheduled by a list scheduler with VR4300
latencies. The scheduler:
  - issues the ready instruction with the longest remaining path first;
  - never issues a multiplication directly after a multiplication, and puts
    no multiplication in a branch delay slot (VR4300 multiply erratum);
  - keeps one instruction between mtc1 and the use of its register;
  - allocates registers as it goes (caller-saved only: $t*, $v*, $a1-$a3,
    even $f2-$f18), and holds an instruction back when no register is free.
It writes a nop when nothing is ready.
"""
import argparse
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
LAT = {'luihi': 1, 'lwc1': 2, 'lui': 1, 'ori': 1, 'addiu': 1, 'andi': 1, 'mtc1': 2, 'cvt.s.w': 5, 'mul.s': 5, 'add.s': 3,
       'sub.s': 3, 'sqrt.s': 29, 'mov.s': 1, 'neg.s': 1}
INT_POOL = ['$t4',                       # $t0-$t3 hold t, x and the octant and sign flags
             '$t5', '$t6', '$t7', '$t8', '$t9', '$v0', '$v1', '$a1', '$a2', '$a3']
FP_POOL = [f'$f{n}' for n in range(4, 20, 2)] + ['$f2']


class Graph:
    def __init__(self, load='code', sym=None):
        self.ops = []                    # (opcode, dst, srcs, imm, cls)
        self.n = 0
        self.load, self.sym = load, sym  # 'line': full-precision coefficients from the table at sym
        self.table, self.base = [], None

    def v(self):
        self.n += 1
        return f'v{self.n}'

    def op(self, opc, srcs=(), imm=None, cls='f', dst=True):
        d = self.v() if dst else None
        self.ops.append((opc, d, list(srcs), imm, cls))
        return d

    def const(self, bits):
        if self.load == 'line' and bits & 0xFFFF and (bits in self.table or len(self.table) < 4):
            if bits not in self.table:
                self.table.append(bits)
            if self.base is None:
                self.base = self.op('luihi', imm=self.sym, cls='i')
            return self.op('lwc1', [self.base], imm=f'%lo({self.sym}+{4 * self.table.index(bits)})', cls='f')
        r = self.op('lui', imm=bits >> 16, cls='i')
        if bits & 0xFFFF:
            r = self.op('ori', [r], imm=bits & 0xFFFF, cls='i')
        return self.op('mtc1', [r], cls='f')

    def horner(self, ks, x2):
        """ks: coefficient bit patterns, lowest power first -> value of the inner polynomial in x²."""
        h = self.const(ks[-1])
        for k in reversed(ks[:-1]):
            h = self.op('mul.s', [h, x2])
            h = self.op('add.s', [h, self.const(k)])
        return h


def build(form, which, g, fx, x2):
    """Ops for the sine ('s'), the cosine ('c') or both ('sc') of the folded x. -> {name: value}"""
    kind, ks, kc = form['kind'], form['ks'], form['kc']
    out = {}

    def sine():
        if kind == 'csqrt':
            return root(cosine_poly())
        h = g.horner(ks, x2) if len(ks) > 1 else g.const(ks[0])
        return g.op('mul.s', [h, fx])

    def cosine_poly():
        h = g.horner(kc, x2) if len(kc) > 1 else g.const(kc[0])
        h = g.op('mul.s', [h, x2])
        return g.op('add.s', [h, one()])

    ones = {}

    def one():
        if 'one' not in ones:
            ones['one'] = g.const(0x3F800000)
        return ones['one']

    def root(v):
        sq = g.op('mul.s', [v, v])
        d = g.op('sub.s', [one(), sq])
        return g.op('sqrt.s', [d])

    if which == 'sc':
        if kind == 'poly':
            out['s'], out['c'] = sine(), cosine_poly()
        elif kind == 'csqrt':
            c = cosine_poly()
            out['c'], out['s'] = c, root(c)
        else:
            s = g.horner(ks, x2) if len(ks) > 1 else g.const(ks[0])
            s = g.op('mul.s', [s, fx])
            out['s'], out['c'] = s, root(s)
    elif which == 's':
        out['r'] = sine()
    else:
        if kind == 'ssqrt':
            s = g.horner(ks, x2) if len(ks) > 1 else g.const(ks[0])
            out['r'] = root(g.op('mul.s', [s, fx]))
        else:
            out['r'] = cosine_poly()
    return out


def schedule(g, pre, live_out):
    """List-schedule g.ops. pre: {virtual: physical} already assigned (inputs).
    live_out: virtuals that must stay live (their registers are not reused). -> (lines, regmap)"""
    ops = g.ops
    users = {}
    for i, (_, d, srcs, _, _) in enumerate(ops):
        for s in srcs:
            users.setdefault(s, []).append(i)
    # priority: longest latency path from the op to the end
    prio = [0] * len(ops)
    defs = {d: i for i, (_, d, _, _, _) in enumerate(ops) if d}
    for i in reversed(range(len(ops))):
        opc, d = ops[i][0], ops[i][1]
        prio[i] = LAT[opc] + max([prio[u] for u in users.get(d, [])], default=0)
    reg = dict(pre)
    ready_at = {v: 0 for v in pre}
    free = {'i': [r for r in INT_POOL if r not in pre.values()], 'f': [r for r in FP_POOL if r not in pre.values()]}
    remaining_uses = {v: len(users.get(v, [])) for v in list(defs) + list(pre)}
    done, lines, cycle, last_mul = set(), [], 0, False
    while len(done) < len(ops):
        cand = []
        for i, (opc, d, srcs, imm, cls) in enumerate(ops):
            if i in done or any(s not in reg or ready_at[s] > cycle for s in srcs):
                continue
            if opc == 'mul.s' and last_mul:
                continue
            # a register: reuse a source that dies here, else a free one
            dying = [s for s in srcs if remaining_uses[s] == 1 and s not in live_out and s not in pre
                     and (reg[s].startswith('$f')) == (cls == 'f')]
            if not dying and not free[cls]:
                continue
            cand.append((prio[i], -i, i, dying))
        if not cand:
            lines.append('nop')
            last_mul = False
            cycle += 1
            continue
        _, _, i, dying = max(cand)
        opc, d, srcs, imm, cls = ops[i]
        rs = [reg[s] for s in srcs]
        for s in srcs:
            remaining_uses[s] -= 1
            if remaining_uses[s] == 0 and s not in live_out and s not in pre and s not in dying[:1]:
                free['f' if reg[s].startswith('$f') else 'i'].append(reg[s])
        rd = reg[dying[0]] if dying else free[cls].pop(0)
        reg[d] = rd
        ready_at[d] = cycle + LAT[opc]
        if opc == 'luihi':
            lines.append(f'lui     {rd}, %hi({imm})')
        elif opc == 'lwc1':
            lines.append(f'lwc1    {rd}, {imm}({rs[0]})')
        elif opc == 'lui':
            lines.append(f'lui     {rd}, 0x{imm:04x}')
        elif opc == 'ori':
            lines.append(f'ori     {rd}, {rs[0]}, 0x{imm:04x}')
        elif opc == 'mtc1':
            lines.append(f'mtc1    {rs[0]}, {rd}')
        else:
            lines.append(f'{opc:7} {rd}, ' + ', '.join(rs))
        last_mul = opc == 'mul.s'
        done.add(i)
        cycle += 1
    return lines, reg


def fold_prologue():
    return ['addiu   $t0, $a0, 0x2000', 'andi    $t1, $t0, 0x3fff', 'addiu   $t1, $t1, -0x2000',
            'mtc1    $t1, $f20', 'andi    $t2, $t0, 0x4000         # set: odd octant',
            'andi    $t3, $t0, 0x8000         # set: negate']


def gen_sincos(fid, form):
    g = Graph(form.get('load', 'code'), f'g_{fid}_k')
    pre = {'fx': '$f0'}
    x2 = g.op('mul.s', ['fx', 'fx'])
    out = build(form, 'sc', g, 'fx', x2)
    body, reg = schedule(g, pre, set(out.values()))
    rs, rc = reg[out['s']], reg[out['c']]
    tmp = next(r for r in FP_POOL if r not in (rs, rc))
    pro = [l.replace('$f20', '$f0') for l in fold_prologue()] + ['cvt.s.w $f0, $f0']
    epi = ['beqz    $t2, 1f', 'nop', f'mov.s   {tmp}, {rs}', f'mov.s   {rs}, {rc}', f'neg.s   {rc}, {tmp}',
           '1: beqz  $t3, 2f', f'mov.s   $f0, {rs}', f'neg.s   $f0, {rs}', f'neg.s   {rc}, {rc}',
           '2: jr    $ra', f'mov.s   $f2, {rc}']
    if rc == '$f0':
        raise SystemExit(f'{fid}: cosine in $f0')
    if form['kind'] == 'csqrt':          # sqrt(1 - C^2) is not negative: the sine takes the sign of x ($t1)
        body += ['bltzl   $t1, 9f', f'neg.s   {rs}, {rs}', '9:']
    return func(f'g_{fid}_sincos', pro + body + epi), g.table


def gen_sin(fid, form, table):
    blocks = {}
    for which in ('c', 's'):
        g = Graph(form.get('load', 'code'), f'g_{fid}_k')
        g.table = table                  # one table for both blocks and for sincos
        x2 = g.op('mul.s', ['fx', 'fx'])
        out = build(form, which, g, 'fx', x2)
        body, reg = schedule(g, {'fx': '$f0'}, {out['r']})
        blocks[which] = body + [f'mov.s   $f0, {reg[out["r"]]}']
        if which == 's' and form['kind'] == 'csqrt':   # the sine takes the sign of x ($t1)
            blocks[which] += ['bltzl   $t1, 9f', 'neg.s   $f0, $f0', '9:']
    pro = [l.replace('$f20', '$f0') for l in fold_prologue()] + ['beqz    $t2, 1f', 'cvt.s.w $f0, $f0']
    lines = pro + blocks['c'] + ['b       2f', 'nop', '1:'] + blocks['s'] + \
        ['2: beqz  $t3, 3f', 'nop', 'neg.s   $f0, $f0', '3: jr    $ra', 'nop']
    return func(f'g_{fid}_sin', lines), table


def func(name, lines):
    out = ['    .global ' + name, '    .type   ' + name + ', @function', '    .balign 32', name + ':']
    for l in lines:
        out.append(l if l.endswith(':') else ('    ' + l if not l[0].isdigit() else l))
    out.append(f'    .size   {name}, . - {name}')
    return '\n'.join(out) + '\n'


def form_id(key):
    return re.sub(r'[^A-Za-z0-9]+', '_', key.replace('+', 'p').replace(' top 8-bit', '_t8')).strip('_')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--forms', type=Path, nargs='+', default=[REPO / 'fit/forms.json'])
    ap.add_argument('--out', type=Path, default=REPO / 'work/micro/gen.s')
    ap.add_argument('--only', help='generate this one form only')
    ap.add_argument('--prefix', help='with --only: name the functions PREFIX_sin, PREFIX_sincos (table PREFIX_k)')
    ap.add_argument('--extern-table', action='store_true',
                    help='with --only: do not emit the table; write its words to OUT.table.json (bench/slot.py)')
    args = ap.parse_args()
    forms = {}
    for p in args.forms:
        forms.update(json.loads(p.read_text()))
    if args.only:
        forms = {args.only: forms[args.only]}
    text = ['# Generated by bench/micro/gen.py. Do not edit.', '    .set noreorder', '    .set noat', '    .text']
    data = ['    .section .rodata']
    ids = []
    for key, f in forms.items():
        n_s = len(range(1, f['ns'] + 1, 2)) if f['ns'] else 0
        form = {'kind': f['kind'], 'ks': f['coefficients'][:n_s], 'kc': f['coefficients'][n_s:],
                'load': f.get('load', 'code')}
        fid = form_id(key)
        sc, t1 = gen_sincos(fid, form)
        sn, t2 = gen_sin(fid, form, list(t1))
        if args.prefix:
            sc, sn = (x.replace(f'g_{fid}_k', f'{args.prefix}_k').replace(f'g_{fid}_sincos', f'{args.prefix}_sincos')
                      .replace(f'g_{fid}_sin', f'{args.prefix}_sin') for x in (sc, sn))
            fid_k = f'{args.prefix}_k'
        else:
            fid_k = f'g_{fid}_k'
        text += [sc, sn]
        table = t2                       # starts with the sincos table; sin may add entries
        if len(table) > 4:
            raise SystemExit(f'{fid}: more than one 16-byte line')
        if args.extern_table:
            args.out.with_suffix('.table.json').write_text(json.dumps(table))
        elif table:
            data += ['    .balign 16', f'{fid_k}:'] + [f'    .word   0x{b:08x}' for b in table]
        ids.append((fid, key))
    text += data
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text('\n'.join(text))
    (args.out.with_suffix('.json')).write_text(json.dumps(ids))
    print(f'{len(ids)} forms -> {args.out}')


if __name__ == '__main__':
    main()
