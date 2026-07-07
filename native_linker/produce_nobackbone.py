#!/usr/bin/env python3
"""
No-backbone console-zone ASSEMBLE loop (Track G). Authors a console zone from a PC map
alone. Two modes:

  raid-control : run on raid (has a genuine console oracle). Emit each body from PC via
                 the real converters (+ stubs where mp_skate would stub), diff vs the
                 genuine console body. A KNOWN-EXCEPTION ALLOWLIST masks the converters
                 that are intentionally not byte-identical (material sort-hash, substituted
                 techsets, skinned). Any diff OUTSIDE the allowlist = an assemble-machinery
                 bug (ordering / body dispatch / size). This validates the MACHINERY, not
                 converter byte-perfection.
  build        : run blind on mp_skate -> emit loadable bodies -> (container + pack).

This file: the emit dispatch + per-asset oracle diff (raid) + per-asset log. The container
emission / omap finalize / pack are layered on once the body loop is proven on raid.
"""
import sys, os, struct
sys.path.insert(0, '.'); sys.path.insert(0, os.path.join('..', 'wiiu_ref'))
import struct_layout, walker as W
import pc_zone, wiiu_zone
import material_convert as MC
import fx_pc, xmodel_pc, techset_pc, gfxworld_pc, clipmap_pc, sndbank_pc, lightdef_pc, glasses_pc
import destructibledef_probe as _DP
import gameworldmp_probe as _GW
import xanimparts_probe as _XA

FOLLOW = 0xFFFFFFFF

# ---- PC per-asset body-span walk (Track E dispatch, yields spans) ----
def walk_pc_bodies(PC):
    r = pc_zone.PCZoneReader(PC); r.read_string_table(); r.read_asset_list()
    L = struct_layout.Layout(W.HDR, console=False)
    wk = W.Walker(PC, L, W.ZoneCode(W.ZC_DIR), r.block_sizes)
    wk.u16 = lambda o: struct.unpack_from('<H', PC, o)[0]
    wk.u32 = lambda o: struct.unpack_from('<I', PC, o)[0]
    wk._scalar = lambda base, o: (lambda s: PC[o] if s == 1 else
                                  struct.unpack_from('<H' if s == 2 else '<I', PC, o)[0])(L._resolve(base)[0])
    cur = r.assets_end
    out = []
    for i, (t, nm, hp) in enumerate(r.assets):
        root = W.ASSET_ROOT.get(nm)
        if root is None or root not in L.structs or hp != FOLLOW:
            out.append((i, nm, root, None, None, hp)); continue
        start = cur
        try:
            if root == 'FxEffectDef':          cur = fx_pc.parse_fx_pc(PC, start)[0]
            elif root == 'XModel':             cur = xmodel_pc.parse_xmodel_pc(PC, start)
            elif root == 'MaterialTechniqueSet': cur = techset_pc.parse_techset_pc(PC, start)
            elif root == 'Material':           _, cur = MC.convert_material(PC, start)
            elif root == 'DestructibleDef':    cur = _DP.parse_destructible(PC, start, '<')[0]
            elif root == 'GfxLightDef':        cur = lightdef_pc.parse_lightdef_pc(PC, start)
            elif root == 'Glasses':            cur = glasses_pc.parse_glasses_pc(PC, start)
            elif root == 'clipMap_t':          cur = clipmap_pc.parse_clipmap_pc(PC, start)
            elif root == 'SndBank':            cur = sndbank_pc.parse_sndbank_pc(PC, start)
            elif root == 'GfxWorld':           cur = gfxworld_pc.parse_gfxworld_pc(PC, start)
            elif root == 'GameWorldMp':        cur = _GW.Walker(PC, '<', 144).walk(start)[0]
            elif root == 'XAnimParts':         cur = _XA.parse_xanim(PC, start, '<')[0]
            elif root == 'GfxImage':           cur = MC.pc_image_span(PC, start)
            else:                              cur = wk.walk(root, cur)
        except Exception as e:
            out.append((i, nm, root, start, None, hp))
            return out, ('walk-break', i, nm, start, str(e))
        out.append((i, nm, root, start, cur, hp))
    return out, None


def main():
    PC = open('../PC ff/mp_raid.zone', 'rb').read()
    bodies, brk = walk_pc_bodies(PC)
    done = [b for b in bodies if b[3] is not None and b[4] is not None]
    from collections import Counter
    c = Counter(b[2] for b in done)
    print("PC raid: walked %d/%d inline bodies" % (len(done), len(bodies)))
    print("  by type:", dict(c.most_common(14)))
    if brk:
        print("  walk break:", brk)
    # size sanity: emit order == asset order, spans contiguous & monotonic
    prev = None; gaps = 0
    for (i, nm, root, s, e, hp) in done:
        if prev is not None and s != prev:
            gaps += 1
        prev = e
    print("  span monotonic/contiguous: gaps=%d (0 = clean)" % gaps)


if __name__ == '__main__':
    main()
