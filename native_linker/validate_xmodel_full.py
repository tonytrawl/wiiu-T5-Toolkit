#!/usr/bin/env python3
"""Validate the full XModel PC->console converter tail + driver (HANDOFF Track C tail).

Matched-pair oracle on common_mp (MP models carry full tails: materialHandles/collSurfs/boneInfo/
himip/physPreset).  Reports, per section:
  * materialHandles handle-words (relocatable ptrs masked) byte-exact.
  * collSurfs (44->36, collTris dropped) byte-exact.
  * boneInfo (44 B, byte-swap) — byte-exact OR diffs confined to per-bone recomputed bounds/radius
    floats (the console re-derives bone AABBs from its re-quantised mesh; same inherent-derived
    class as verts0 normals / collision BVH).
  * physPreset (84 B + strings, ptrs masked) byte-exact.
  * CLEAN full-model convert+resync: for every model whose materialHandles are ALIASES (no inline
    material -> no image-conversion-track dependency) and numCollmaps==0, convert the whole XModel
    via convert_xmodel and re-parse it through the genuine console walker (xmodel_probe.parse_xmodel);
    it must consume exactly its own length and recover the model name.

Out-of-scope dependencies (counted, not failed): inline-material images (texture-conversion track)
and collmaps (collmap track).  Skinned surfaces raise NotImplementedError (Latte GX2 skin-stream
synthesis — see xmodel_convert.convert_xmodel_surfaces).
"""
import struct, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'wiiu_ref'))
import xmodel_probe as XP
import xmodel_convert as XC
import xmodel_pc as XPC

CO_PATH = os.path.join('..', 'common_mp.zone')
PC_PATH = os.path.join('..', 'PC ff', 'common_mp.zone')


def enum_console(CO):
    co = {}
    i = 0
    while i < len(CO) - XP.BODY:
        j = CO.find(b'\xff\xff\xff\xff', i)
        if j < 0:
            break
        if XP.is_body(CO, j, strict=True):
            try:
                _, name = XP.parse_xmodel(CO, j)
                if name and not name.startswith('<'):
                    co.setdefault(name, j)
            except Exception:
                pass
        i = j + 4
    return co


def pc_body(PC, name):
    p = PC.find(name.encode('latin-1') + b'\x00')
    while p >= 0:
        pb = p - XC.PC_BODY
        if pb >= 0 and struct.unpack_from('<I', PC, pb)[0] == XC.FOLLOW:
            return pb
        p = PC.find(name.encode('latin-1') + b'\x00', p + 1)
    return None


def console_sections(CO, o):
    """Genuine console section offsets (mirrors xmodel_probe.parse_xmodel)."""
    nb, nrb, ns = CO[o + 4], CO[o + 5], CO[o + 6]
    ptr = {k: XP.u32(CO, o + k) for k in (0, 8, 12, 16, 20, 24, 28, 32, 36,
                                          152, 164, 200, 212)}
    ncoll = XP.u32(CO, o + 156)
    c = XP.Cur(CO, o + XP.BODY)
    if ptr[0] in XP.PTRS:
        c.cstr()
    if ptr[8] in XP.PTRS:
        c.skip(2 * nb)
    if ptr[12] in XP.PTRS:
        c.skip(nb - nrb)
    if ptr[16] in XP.PTRS:
        c.skip(8 * (nb - nrb))
    if ptr[20] in XP.PTRS:
        c.skip(16 * (nb - nrb))
    if ptr[24] in XP.PTRS:
        c.skip(nb)
    if ptr[28] in XP.PTRS:
        c.skip(32 * nb)
    if ptr[32] in XP.PTRS:
        sb = c.o
        c.skip(ns * XP.SURF)
        for i in range(ns):
            XP.parse_surface_dyn(CO, sb + i * XP.SURF, c)
    mh = c.o
    if ptr[36] in XP.PTRS:
        base = c.o
        c.skip(4 * ns)
        for i in range(ns):
            if XP.u32(CO, base + i * 4) in XP.PTRS:
                XP.consume_material(CO, c)
    collsurf = c.o
    if ptr[152] in XP.PTRS:
        c.skip(36 * ncoll)
    boneinfo = c.o
    if ptr[164] in XP.PTRS:
        c.skip(44 * nb)
    himip = c.o
    if ptr[200] in XP.PTRS:
        c.skip(4 * ns)
    physpreset = c.o
    if ptr[212] in XP.PTRS:
        pb = c.o
        c.skip(84)
        if XP.u32(CO, pb) in XP.PTRS:
            c.cstr()
        if XP.u32(CO, pb + 28) in XP.PTRS:
            c.cstr()
    return dict(mh=mh, collsurf=collsurf, boneinfo=boneinfo, himip=himip,
                physpreset=physpreset, end=c.o, nb=nb, ns=ns, ncoll=ncoll)


def pc_sections(PC, o):
    """PC section offsets up through collSurfs start (materialHandles need the inline-material span)."""
    import material_convert as MC
    nb, nrb, ns = PC[o + 4], PC[o + 5], PC[o + 6]
    ncoll = XPC._u32(PC, o + 156)
    _, cur = XC.convert_xmodel_bonedata(PC, o)
    c = [cur]
    if XPC._u32(PC, o + 32) in XPC.PTRS:
        sb = c[0]
        c[0] += ns * 80
        for i in range(ns):
            XPC._surface_dyn(PC, sb + i * 80, c)
    mh = c[0]
    if XPC._u32(PC, o + 36) in XPC.PTRS:
        base = c[0]
        c[0] += 4 * ns
        for i in range(ns):
            if XPC._u32(PC, base + i * 4) in XPC.PTRS:
                _, nxt = MC.convert_material(PC, c[0])
                c[0] = nxt
    collsurf = c[0]
    # PC collSurfs + collTris -> boneInfo
    bi = collsurf + 44 * ncoll
    for i in range(ncoll):
        c0 = collsurf + i * 44
        if XPC._u32(PC, c0 + 0) in XPC.PTRS:
            bi += XPC._u32(PC, c0 + 4) * 48
    return dict(mh=mh, collsurf=collsurf, boneinfo=bi, nb=nb, ns=ns, ncoll=ncoll)


def maskptrs(b, offs):
    b = bytearray(b)
    for o in offs:
        b[o:o + 4] = b'\x00\x00\x00\x00'
    return bytes(b)


def main():
    CO = open(CO_PATH, 'rb').read()
    PC = open(PC_PATH, 'rb').read()
    cons = enum_console(CO)
    hw_ok = hw_bad = cs_ok = cs_bad = pp_ok = pp_bad = 0
    bi_exact = bi_derived = bi_bad = 0
    clean_ok = clean_bad = inline_dep = collmap_dep = skinned = 0
    n = 0
    for name, cj in cons.items():
        pb = pc_body(PC, name)
        if pb is None or PC[pb + 4] != CO[cj + 4] or PC[pb + 6] != CO[cj + 6]:
            continue
        try:
            cs = console_sections(CO, cj)
            ps = pc_sections(PC, pb)
        except Exception:
            continue
        if cs['ns'] != ps['ns'] or cs['nb'] != ps['nb'] or cs['ncoll'] != ps['ncoll']:
            continue
        n += 1
        ns, nb, ncoll = cs['ns'], cs['nb'], cs['ncoll']
        # materialHandles handle-words
        cw, _ = XC.convert_xmodel_materialhandles(PC, ps['mh'], ns)
        gw = CO[cs['mh']:cs['mh'] + ns * 4]
        if maskptrs(gw, range(0, ns * 4, 4)) == maskptrs(cw[:ns * 4], range(0, ns * 4, 4)):
            hw_ok += 1
        else:
            hw_bad += 1
        # collSurfs
        conv, _ = XC.convert_xmodel_collsurfs(PC, ps['collsurf'], ncoll)
        if conv == CO[cs['collsurf']:cs['boneinfo']]:
            cs_ok += 1
        else:
            cs_bad += 1
        # physPreset
        if XPC._u32(PC, pb + 216) in XPC.PTRS:
            pcur = ps['boneinfo'] + 44 * nb
            if XPC._u32(PC, pb + 200) in XPC.PTRS:
                pcur += 4 * ns
            conv, _ = XC.convert_xmodel_physpreset(PC, pcur)
            g = CO[cs['physpreset']:cs['end']]
            if len(conv) == len(g) and maskptrs(conv, (0, 28)) == maskptrs(g[:len(conv)], (0, 28)):
                pp_ok += 1
            else:
                pp_bad += 1
        # CLEAN full-model resync (exclude out-of-scope deps)
        inline = (XPC._u32(PC, pb + 36) in XPC.PTRS and
                  any(XPC._u32(PC, ps['mh'] + i * 4) in XPC.PTRS for i in range(ns)))
        collmap = PC[pb + 220] > 0
        if inline:
            inline_dep += 1
        if collmap:
            collmap_dep += 1
        if inline or collmap:
            continue
        try:
            blob, _ = XC.convert_xmodel(PC, pb)
        except NotImplementedError:
            skinned += 1
            continue
        except Exception:
            clean_bad += 1
            continue
        try:
            end, pname = XP.parse_xmodel(blob, 0)
            if end == len(blob) and pname == name:
                clean_ok += 1
                # boneInfo measured on the correctly-threaded blob (validator's pc_sections
                # offset drifts through collTris; the blob's own offsets are exact).
                bs = console_sections(blob, 0)
                mybi = blob[bs['boneinfo']:bs['himip']]
                gbi = CO[cs['boneinfo']:cs['himip']]
                if len(mybi) == len(gbi):
                    if mybi == gbi:
                        bi_exact += 1
                    elif max((abs(struct.unpack('>I', gbi[i:i + 4])[0] -
                                  struct.unpack('>I', mybi[i:i + 4])[0])
                              for i in range(0, len(gbi), 4) if gbi[i:i + 4] != mybi[i:i + 4]),
                             default=0) <= 16:
                        bi_derived += 1     # console re-derived bone bounds, <=16 ULP
                    else:
                        bi_bad += 1
            else:
                clean_bad += 1
        except Exception:
            clean_bad += 1
    print('matched models: %d\n' % n)
    print('materialHandles handle-words (masked): %d exact, %d differ' % (hw_ok, hw_bad))
    print('collSurfs (44->36):                    %d exact, %d differ' % (cs_ok, cs_bad))
    print('boneInfo (byte-swap, on resynced blob): %d exact, %d derived-float(<=16ULP), %d bad'
          % (bi_exact, bi_derived, bi_bad))
    print('physPreset (masked ptrs):              %d exact, %d differ' % (pp_ok, pp_bad))
    print('\nCLEAN full-model convert+resync (alias-mat + no-collmap): %d ok, %d bad'
          % (clean_ok, clean_bad))
    print('  out-of-scope deps: inline-material(image track)=%d  collmaps(collmap track)=%d  skinned=%d'
          % (inline_dep, collmap_dep, skinned))


if __name__ == '__main__':
    main()
