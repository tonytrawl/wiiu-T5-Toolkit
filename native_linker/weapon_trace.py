#!/usr/bin/env python3
"""Trace the generic walker's traversal of an asset body in a PC zone (default WeaponVariantDef).

Uses the walker's built-in trace hook (wk.trace), so it always reflects the real walk logic.
Diff the output against the OAT weaponvariantdef_t6_load_db.cpp order.
"""
import struct, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'wiiu_ref'))
import struct_layout, walker as W


def make_walker(PC):
    L = struct_layout.Layout(W.HDR, console=False)
    zc = W.ZoneCode(W.ZC_DIR)
    wk = W.Walker(PC, L, zc, None)
    wk.u16 = lambda o: struct.unpack_from('<H', PC, o)[0]
    wk.u32 = lambda o: struct.unpack_from('<I', PC, o)[0]
    wk._scalar = lambda base, o: (lambda s: PC[o] if s == 1 else
                                  struct.unpack_from('<H' if s == 2 else '<I', PC, o)[0])(L._resolve(base)[0])
    return wk, L


def trace(PC, start, root='WeaponVariantDef', out=sys.stdout, limit=6000):
    wk, L = make_walker(PC)
    wk.trace = []
    try:
        end = wk.walk(root, start)
    except Exception as e:
        end = None
        print('EXC: %r' % e, file=out)
    for depth, sn, nm, b4, after in wk.trace[:limit]:
        preview = PC[b4:min(b4+20, after)].hex()
        print('%s%s.%s +0x%x (0x%x->0x%x) %s' % ('  '*depth, sn, nm, after-b4, b4, after, preview), file=out)
    if len(wk.trace) > limit:
        print('... (%d more)' % (len(wk.trace)-limit), file=out)
    if wk.errors:
        print('ERRORS: %s' % wk.errors[:10], file=out)
    print('END = %s' % (hex(end) if end is not None else 'EXC'), file=out)
    return end


if __name__ == '__main__':
    path = sys.argv[1]
    start = int(sys.argv[2], 16)
    root = sys.argv[3] if len(sys.argv) > 3 else 'WeaponVariantDef'
    PC = open(path, 'rb').read()
    trace(PC, start, root)
