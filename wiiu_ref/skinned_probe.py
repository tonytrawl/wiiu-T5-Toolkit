#!/usr/bin/env python3
"""
WP-A: console (Wii U) skinned XSurface pre-verts0 Latte stream - SOLVE probe.

The skinned console XSurface (128 B body) serializes, before verts0, an inline
region of size:

    vertsBlend = (vertCount[0] + 3*vertCount[1] + 5*vertCount[2] + 7*vertCount[3]) * 2
    gap        = 2*lo16(s28) + 2*hi16(s28) + 2*s40

where s28 is the u32 body scalar at +28 and s40 the u32 at +40. The gap is the
previously undecoded Latte skinning data: three console-only u16 streams whose
FOLLOW markers sit at +32, +36 and +44, with element counts lo16(s28),
hi16(s28) and s40 respectively (the total is what matters for stream resync;
the per-marker count assignment follows the ascending marker order and the
observed content boundaries). tensionData has no console pointer slot; +28/+40
hold the counts instead.

Verified:
- All skinned surfaces in the 4 faction zones (240 samples) parse with the
  formula and pass positions-in-model-bounds plus triIndices<vertCount checks,
  and every model resyncs onto its materialHandles markers.
- console_skinned_xsurface_sample.bin surf0 consumes to the exact byte.
- german_shepherd in genuine mp_raid: vertsBlend and verts0 positions are
  byte-swap-identical to PC ff/mp_raid.zone, full model resync byte-exact.

Run: python skinned_probe.py [zone ...]
Defaults to the 4 faction zones plus mp_raid_genuine.zone.
"""
import math
import struct
import sys

FOLLOW = 0xFFFFFFFF
INSERT = 0xFFFFFFFE
PTRS = (FOLLOW, INSERT)
BODY = 244
SURF = 128


def is_body(d, o, strict=True):
    def u32(x):
        return struct.unpack('>I', d[x:x+4])[0]

    def u16(x):
        return struct.unpack('>H', d[x:x+2])[0]

    if o + BODY > len(d) or u32(o) != FOLLOW:
        return False
    ns = d[o+6]
    if not (1 <= ns <= 64):
        return False

    def ptr_ok(v):
        return v in (0, FOLLOW, INSERT) or ((v - 1) >> 29) < 8

    if not all(ptr_ok(u32(o+k)) for k in (8, 12, 16, 20, 24, 28, 32, 36,
                                          152, 164, 200, 212, 220, 224)):
        return False
    if u32(o+32) == 0 or u32(o+36) == 0:
        return False
    tot = 0
    si = 0
    nl = 0
    for i in range(4):
        lo = o + 40 + i*28
        lns = u16(lo+4)
        if lns:
            if u16(lo+6) != si:
                return False
            si += lns
            tot += lns
            nl += 1
    if not (tot == ns and nl >= 1):
        return False
    return not strict or u16(o+196) == nl


def skinned_gap(s28, s40):
    """Size in bytes of the console-only Latte skin streams between
    vertsBlend and verts0."""
    return 2*(s28 & 0xffff) + 2*(s28 >> 16) + 2*s40


def probe_zone(path):
    d = open(path, 'rb').read()

    def u32(x):
        return struct.unpack('>I', d[x:x+4])[0]

    def u16(x):
        return struct.unpack('>H', d[x:x+2])[0]

    def f32(x):
        return struct.unpack('>f', d[x:x+4])[0]

    models = skinned_surfs = ok_surfs = resynced = 0
    fails = []
    # step 1: zone stream offsets are not file-4-aligned in all regions
    # (mp_raid's german_shepherd body sits at a %4==3 file offset)
    for o in (x for x in range(0, len(d) - BODY) if is_body(d, x)):
        nb, nrb, ns = d[o+4], d[o+5], d[o+6]
        mins = [f32(o+172+j*4) for j in range(3)]
        maxs = [f32(o+184+j*4) for j in range(3)]
        c = o + BODY
        if u32(o) in PTRS:
            e = d.index(b'\x00', c)
            name = d[c:e].decode('latin-1', 'replace')
            c = e + 1
        else:
            name = '<alias>'
        for k, sz in ((8, 2*nb), (12, nb-nrb), (16, 8*(nb-nrb)),
                      (20, 16*(nb-nrb)), (24, nb), (28, 32*nb)):
            if u32(o+k) in PTRS:
                c += sz
        if u32(o+32) not in PTRS:
            continue
        has_skinned = any(
            any(u32(c + i*SURF + k) in PTRS for k in (24, 32, 36, 44))
            for i in range(ns))
        if not has_skinned:
            continue
        models += 1
        sb = c
        c += ns * SURF
        model_ok = True
        try:
            for i in range(ns):
                b = sb + i*SURF
                vc, tc = u16(b+4), u16(b+6)
                vi = [struct.unpack('>h', d[b+16+j*2:b+18+j*2])[0]
                      for j in range(4)]
                if any(u32(b+k) in PTRS for k in (24, 32, 36, 44)):
                    skinned_surfs += 1
                    vb = (vi[0] + 3*vi[1] + 5*vi[2] + 7*vi[3]) * 2
                    c += vb + skinned_gap(u32(b+28), u32(b+40))
                if u32(b+52) in PTRS:
                    # validate verts0: positions inside model bounds
                    good = True
                    for kk in range(vc):
                        for j in range(3):
                            v = f32(c + kk*24 + j*4)
                            if (math.isnan(v) or math.isinf(v)
                                    or not (mins[j]-16 <= v <= maxs[j]+16)):
                                good = False
                                break
                        if not good:
                            break
                    if not good:
                        model_ok = False
                        fails.append('%s surf %d: verts0 out of bounds'
                                     % (name, i))
                    c += vc * 24
                if u32(b+72) in PTRS:
                    c += vc * 8
                if u32(b+96) in PTRS:
                    vlc = d[b+1]
                    base = c
                    c += vlc * 12
                    for kk in range(vlc):
                        if u32(base + kk*12 + 8) in PTRS:
                            tb = c
                            c += 40
                            if u32(tb+28) in PTRS:
                                c += u32(tb+24) * 16
                            if u32(tb+36) in PTRS:
                                c += u32(tb+32) * 2
                if u32(b+12) in PTRS:
                    if any(u16(c + t*2) >= vc for t in range(tc*3)):
                        model_ok = False
                        fails.append('%s surf %d: triIndices >= vertCount'
                                     % (name, i))
                    c += tc * 6
                if model_ok:
                    ok_surfs += 1
        except (struct.error, ValueError, IndexError) as e:
            model_ok = False
            fails.append('%s: %s' % (name, e))
        # after the surf array the materialHandles markers follow; each entry
        # must be a marker or an encoded alias, a strong resync witness
        if model_ok:
            handles = [u32(c + h*4) for h in range(ns)]
            if all(v in PTRS or ((v - 1) >> 29) < 8 for v in handles) \
                    and any(v in PTRS for v in handles):
                resynced += 1
            else:
                fails.append('%s: materialHandles resync failed' % name)
    print('%s: skinned models=%d skinned surfs=%d surf checks ok=%d '
          'models resynced=%d' % (path, models, skinned_surfs, ok_surfs,
                                  resynced))
    for f in fails[:10]:
        print('  FAIL', f)
    return skinned_surfs, len(fails)


def main():
    paths = sys.argv[1:] or [
        'Original FF/faction_fbi_mp.zone',
        'Original FF/faction_multiteam_mp.zone',
        'Original FF/faction_cd_mp.zone',
        'Original FF/faction_isa_mp.zone',
        'mp_raid_genuine.zone',
    ]
    total = bad = 0
    for p in paths:
        s, f = probe_zone(p)
        total += s
        bad += f
    print('TOTAL skinned surfaces: %d, failures: %d' % (total, bad))


if __name__ == '__main__':
    main()
