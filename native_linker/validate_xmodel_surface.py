#!/usr/bin/env python3
"""Validate the XModel *surface* PC->console converter (HANDOFF Track C tail).

Matched-pair oracle, joined by model name + surface index:
  * MP models -> genuine console `mp_raid_genuine.zone` vs `PC ff/mp_raid.zone`
    (or common_mp; any shared MP zone works).
  * ZM models -> the ZM map zone itself (zm maps are self-contained).

Three checks per surface / model:
  1. HEADER  (80->128 B) byte-exact vs genuine console, with the 4 relocatable
     pointer words (triIndices@12, verts0@52, verts1@72, vertList@96) masked —
     those are omap-resolved at integration, same convention as the body test.
  2. DYNAMIC span byte-exact vs genuine, EXCEPT two inherently-non-reproducible
     regions (documented, not bugs):
       - verts0 normal(snorm16 @+12..17) + tangent(snorm8 @+20..22): PC's 10-bit
         packed frame already lost precision (see latte_vertex).
       - collision-tree node counts: the console linker REBUILDS the surface BVH
         (observed nc 18 vs PC 20, same leaves) so per-tree node bytes can differ.
  3. SELF-CONSISTENCY: the converted [headers][dynamic] block re-parses through
     the genuine console walker (xmodel_probe.parse_surface_dyn) and consumes
     exactly its own length -> the output is internally valid / loadable even for
     the surfaces whose collision BVH is not byte-reproducible.
"""
import struct, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'wiiu_ref'))
import xmodel_probe as XP
import xmodel_convert as XC

MASK = (12, 52, 72, 96)   # header pointer words (omap-relocated)


def collect_console(path):
    """Genuine console: name -> [ (hdr_off, vertCount, triCount, verts0_abs, dyn_end), ... ]."""
    d = open(path, 'rb').read()
    n = len(d)
    out = {}
    cur = []

    def hook(dd, b, c):
        vc, tc = XP.u16(dd, b + 4), XP.u16(dd, b + 6)
        if any(XP.u32(dd, b + k) in XP.PTRS for k in (24, 32, 36, 44)):
            raise XP.Fail('skinned')
        v0 = c.o if XP.u32(dd, b + 52) in XP.PTRS else None
        if v0 is not None:
            c.skip(vc * 24)
        if XP.u32(dd, b + 72) in XP.PTRS:
            c.skip(vc * 8)
        if XP.u32(dd, b + 96) in XP.PTRS:
            vlc = dd[b + 1]
            base = c.o
            c.skip(vlc * 12)
            for k in range(vlc):
                if XP.u32(dd, base + k * 12 + 8) in XP.PTRS:
                    tb = c.o
                    c.skip(40)
                    nc_, lc_ = XP.u32(dd, tb + 24), XP.u32(dd, tb + 32)
                    if XP.u32(dd, tb + 28) in XP.PTRS:
                        c.skip(nc_ * 16)
                    if XP.u32(dd, tb + 36) in XP.PTRS:
                        c.skip(lc_ * 2)
        if XP.u32(dd, b + 12) in XP.PTRS:
            c.skip(tc * 6)
        cur.append((b, vc, tc, v0, c.o))

    orig = XP.parse_surface_dyn
    XP.parse_surface_dyn = hook
    try:
        cands = [o for o in range(0, n - XP.BODY + 1, 4) if XP.is_body(d, o)]
        seen = set()
        q = list(cands)
        qi = 0
        while qi < len(q):
            o = q[qi]
            qi += 1
            if o in seen:
                continue
            seen.add(o)
            before = len(cur)
            try:
                end, name = XP.parse_xmodel(d, o)
            except Exception:
                del cur[before:]
                continue
            if name and not name.startswith('<'):
                out.setdefault(name, list(cur[before:]))
            if XP.is_body(d, end, strict=False) and end not in seen:
                q.append(end)
    finally:
        XP.parse_surface_dyn = orig
    return d, out


def collect_pc(path):
    """PC: name -> (body_off, surfs_off, numsurfs)."""
    d = open(path, 'rb').read()
    out = {}
    i = 0
    while True:
        j = d.find(b'\xff\xff\xff\xff', i)
        if j < 0:
            break
        i = j + 4
        pb = j
        try:
            ns = d[pb + 6]
            if not (1 <= ns <= 64):
                continue
            if struct.unpack_from('<I', d, pb + 32)[0] != XC.FOLLOW:
                continue
            _, sb = XC.convert_xmodel_bonedata(d, pb)
            if struct.unpack_from('<H', d, sb + 4)[0] == 0:
                continue
            ne = d.index(0, pb + XC.PC_BODY)
            name = d[pb + XC.PC_BODY:ne].decode('latin-1', 'replace')
            if not name or name.startswith('<'):
                continue
            out.setdefault(name, (pb, sb, ns))
        except Exception:
            continue
    return d, out


def maskhdr(h):
    h = bytearray(h)
    for o in MASK:
        h[o:o + 4] = b'\x00\x00\x00\x00'
    return bytes(h)


def validate(console_zone, pc_zone, label):
    cd, cons = collect_console(console_zone)
    pd, pc = collect_pc(pc_zone)
    common = [k for k in cons if k in pc]
    hok = hbad = 0
    dyn_exact = dyn_lossy = dyn_bad = 0
    rt_ok = rt_bad = 0
    skinned = 0
    badnames = []
    for name in common:
        crecs = cons[name]
        pb, sb, ns = pc[name]
        if len(crecs) != ns:
            continue
        try:
            conv, _ = XC.convert_xmodel_surfaces(pd, sb, ns)
        except NotImplementedError:
            skinned += 1
            continue
        except Exception as e:
            dyn_bad += 1
            badnames.append((name, 'conv:' + str(e)[:30]))
            continue
        # header
        for i, (b, vc, tc, v0, ce) in enumerate(crecs):
            if maskhdr(cd[b:b + 128]) == maskhdr(conv[i * 128:(i + 1) * 128]):
                hok += 1
            else:
                hbad += 1
        # dynamic
        dyn_start = crecs[0][0] + ns * 128
        dyn_end = crecs[-1][4]
        gd = cd[dyn_start:dyn_end]
        cvd = conv[ns * 128:]
        allowed = set()
        for (b, vc, tc, v0, ce) in crecs:
            if v0 is None:
                continue
            for vi in range(vc):
                base = (v0 - dyn_start) + vi * 24
                for k in list(range(12, 18)) + list(range(20, 23)):
                    allowed.add(base + k)
        if len(gd) == len(cvd):
            diffs = [i for i in range(len(gd)) if gd[i] != cvd[i]]
            if not diffs:
                dyn_exact += 1
            elif all(i in allowed for i in diffs):
                dyn_lossy += 1
            else:
                # only the collision-BVH-rebuild category is tolerated beyond lossy verts
                dyn_bad += 1
                if len(badnames) < 8:
                    badnames.append((name, 'ndiff', len(diffs), diffs[:4]))
        else:
            # length differs only when the console rebuilt a collision BVH; still must self-resync
            dyn_bad += 1
        # self-consistency
        c = XP.Cur(conv, ns * 128)
        try:
            for i in range(ns):
                XP.parse_surface_dyn(conv, i * 128, c)
            if c.o == len(conv):
                rt_ok += 1
            else:
                rt_bad += 1
        except Exception:
            rt_bad += 1
    print('== %s ==  models=%d  skinned_skipped=%d' % (label, len(common), skinned))
    print('  HEADER (masked ptrs):   %d exact, %d differ' % (hok, hbad))
    print('  DYNAMIC vs genuine:     %d byte-exact, %d lossy-only (normals/BVH), %d structural-bad'
          % (dyn_exact, dyn_lossy, dyn_bad))
    print('  SELF-CONSISTENCY:       %d resync-exact, %d bad' % (rt_ok, rt_bad))
    for f in badnames[:8]:
        print('     ', f)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.join(here, '..')
    validate(os.path.join(root, 'wiiu_ref', 'mp_raid_genuine.zone'),
             os.path.join(root, 'PC ff', 'mp_raid.zone'), 'MP mp_raid')
    zm_con = os.path.join(root, 'wiiu_ref', 'zm_transit_original.zone')
    zm_pc = os.path.join(root, 'PC ff', 'zm_nuked.zone')
    if os.path.exists(zm_con) and os.path.exists(zm_pc):
        validate(zm_con, zm_pc, 'ZM zm_transit')


if __name__ == '__main__':
    main()
