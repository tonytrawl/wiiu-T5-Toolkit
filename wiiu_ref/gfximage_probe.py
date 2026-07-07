#!/usr/bin/env python3
"""
Task #24: triangulate the console (Wii U GX2) GfxImage layout.

Method: find console Material bodies in a genuine zone by the proven
name-string-at-body-end scan (console Material = 104 bytes, name ptr FOLLOW at
+0, name chars at +104). Follow the material's dynamic stream:
  [body 104][info.name chars][techniqueSet subtree if FOLLOW (skip those)]
  [textureTable: textureCount * MaterialTextureDef(16)] then per-def dynamics:
  def.image FOLLOW -> inline GfxImage body.
GfxImage's ZoneCode reorder loads `name` first, so when the image's name ptr is
FOLLOW its ASCII chars start IMMEDIATELY after the body -> the distance from
body start to name start is the console GfxImage struct size. Triangulate the
modal distance across many materials, then dump aligned bodies to map fields.

RESULT (2026-07-02, verified on mp_raid_genuine + zm_transit_original):
console GfxImage = 328 bytes:
  +0   GX2Texture (156 B inline; u32 words LITTLE-endian inside the BE zone):
       dim,width,height,depth,mipLevels,format,aa,use,imageSize,image,mipSize,
       mipmaps,tileMode,swizzle,alignment,pitch,mipLevelOffset[13],view*/regs=0
  +156 mapType,semantic,category,delayLoadPixels (u8 x4)
  +160 baseSize u32 BE   +164 width,height,depth u16 BE   +170 levelCount,streaming u8
  +172 u32 0             +176 pixels ptr (FOLLOW iff streaming==0; baseSize bytes AFTER name)
  +180 ImageFormat u32 BE
  +184 streamedParts[3] x 44 B {packed level info, ipak hash, u16 w,h, 32 B zero}
  +316 streamedPartCount u8 +pad3   +320 name ptr (FOLLOW->chars right after body)
  +324 hash u32
Stream = 328 + name chars (if FOLLOW) + baseSize pixels (if pixels FOLLOW).
Reference-only images: all-zero body + ",name". Full write-up: WIIU_UNLINK_STATUS.md 0f.
"""
import struct, sys
from collections import Counter

FOLLOW = 0xFFFFFFFF
INSERT = 0xFFFFFFFE
MAT_SIZE = 104           # console Material (solved)
TEXDEF_SIZE = 16         # MaterialTextureDef (no 64-bit/D3D members -> same as PC)
NAME_CHARS = set(b"abcdefghijklmnopqrstuvwxyz0123456789_/~$#&+.-")


def u32(d, o):
    return struct.unpack('>I', d[o:o+4])[0]


def name_run(d, o, minlen=3, maxlen=112):
    """If a NUL-terminated printable name starts at o, return it, else None."""
    e = o
    n = len(d)
    while e < n and d[e] in NAME_CHARS and e - o <= maxlen:
        e += 1
    if e - o < minlen or e >= n or d[e] != 0:
        return None
    return d[o:e].decode('latin-1')


def ptr_marker_ok(v):
    return v in (0, FOLLOW, INSERT) or ((v - 1) >> 29) < 8


def find_materials(d):
    """Yield offsets of console Material bodies (name FOLLOW at +0, name at +104)."""
    out = []
    o = d.find(b'\xff\xff\xff\xff')
    n = len(d)
    while o != -1 and o + MAT_SIZE + 8 < n:
        nm = name_run(d, o + MAT_SIZE, minlen=4)
        if nm:
            tc, cc, sbc = d[o+72], d[o+73], d[o+74]
            # 0xff = "technique has no stateBits entry" — common in genuine data
            sbe_ok = all(b < max(sbc, 1) or b == 0xff for b in d[o+40:o+72])
            ptrs = [u32(d, o+80), u32(d, o+84), u32(d, o+88), u32(d, o+92), u32(d, o+96)]
            if (sbc > 0 and tc <= 24 and cc <= 40 and sbc <= 120 and sbe_ok
                    and all(ptr_marker_ok(p) for p in ptrs)
                    and ptrs[0] != 0                      # techniqueSet never null
                    and (ptrs[1] != 0) == (tc > 0)):      # textureTable iff textureCount
                out.append(o)
        o = d.find(b'\xff\xff\xff\xff', o + 4)
    return out


def harvest(d, mats, grab=176):
    """For each material follow the stream to its first inline GfxImage body."""
    samples = []   # dict(mat, matoff, texhash, semantic, body, dist, imgname)
    skipped = Counter()
    for mo in mats:
        tc = d[mo+72]
        tsp, ttp = u32(d, mo+80), u32(d, mo+84)
        cur = mo + MAT_SIZE
        e = d.index(b'\x00', cur)
        matname = d[cur:e].decode('latin-1')
        cur = e + 1
        if tsp == FOLLOW:
            skipped['techniqueSet FOLLOW'] += 1
            continue
        if tc == 0 or ttp != FOLLOW:
            skipped['no inline textureTable'] += 1
            continue
        defs = cur
        cur = defs + tc * TEXDEF_SIZE
        got = False
        for i in range(tc):
            do = defs + i * TEXDEF_SIZE
            img = u32(d, do + 12)
            if img == FOLLOW:
                body = cur
                # ruler: first plausible name string after the body
                dist = None
                imgname = None
                for s in range(body + 4, body + 400):
                    nm = name_run(d, s, minlen=3)
                    if nm and d[s-1] not in NAME_CHARS:
                        dist, imgname = s - body, nm
                        break
                samples.append(dict(mat=matname, matoff=mo, defidx=i,
                                    texhash=u32(d, do), semantic=d[do+7],
                                    body=body, dist=dist, imgname=imgname,
                                    raw=d[body:body+grab]))
                got = True
                break   # cannot advance past an unknown-size image
            elif img == 0:
                continue
            else:
                continue  # alias: no inline data for this def
        if not got:
            skipped['all images aliased'] += 1
    return samples, skipped


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else 'mp_raid_genuine.zone'
    d = open(path, 'rb').read()
    mats = find_materials(d)
    print("zone=%s  material bodies found: %d" % (path, len(mats)))
    samples, skipped = harvest(d, mats)
    print("materials with a first inline GfxImage: %d   skipped: %s" %
          (len(samples), dict(skipped)))
    dists = Counter(s['dist'] for s in samples)
    print("\nbody->name-string distance histogram (candidate struct size):")
    for k, v in sorted(dists.items(), key=lambda x: -x[1]):
        print("  dist=%-6s x%d" % (k, v))
    # aligned dump of the modal-distance samples
    mode = dists.most_common(1)[0][0] if dists else None
    if mode is None:
        return
    show = [s for s in samples if s['dist'] == mode]
    print("\n%d samples at modal dist=%d; first 12 aligned bodies:" % (len(show), mode))
    for s in show[:12]:
        print("\n  mat=%s  sem=%d  img=%s  body=0x%x" %
              (s['mat'], s['semantic'], s['imgname'], s['body']))
        raw = s['raw'][:mode]
        for r in range(0, len(raw), 16):
            chunk = raw[r:r+16]
            print("    +%03d  %s" % (r, ' '.join('%02x' % b for b in chunk)))
    # per-u32-column value diversity at the modal size (field triangulation)
    print("\nper-offset u32 values across %d modal samples:" % len(show))
    for off in range(0, mode, 4):
        vals = Counter(struct.unpack('>I', s['raw'][off:off+4])[0] for s in show)
        top = ', '.join('%08x x%d' % (v, c) for v, c in vals.most_common(4))
        print("  +%03d  distinct=%-4d  %s" % (off, len(vals), top))


if __name__ == '__main__':
    main()
