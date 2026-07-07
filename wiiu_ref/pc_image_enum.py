#!/usr/bin/env python3
"""
PC .ff GfxImage enumerator -> .meta dump dir for ipak_stream.py prepare.

This is the LE / PC-zone analog of ipak_stream.scan_genuine_bodies. It lets the
ipak creation pipeline be driven end-to-end from a PC .ff (+ that game's PC
ipaks) instead of requiring an OAT_IMAGE_DUMP of a console zone.

A PC (Plutonium/T6) GfxImage body is 64 bytes, LE. The interior field offsets do
NOT match struct_layout's GfxImage (that layout is for a different variant); the
ones below were derived empirically by cross-matching hashes against the genuine
console zone (non-square images pin width/height/depth uniquely):
   +0  u32 texture ptr
   +4  u16 width   +6 u16 height   +8 u16 depth   (REAL dims -- the console
        streamed body only carries the 1x1 stub, so the PC .ff is the richer source)
   +56 u32 name ptr          (FOLLOW=0xFFFFFFFF -> name string inlined after body)
   +60 u32 hash              (== R_HashString(name))

Scan technique (self-validating, no walker): find name-ptr FOLLOW at +56, take
the hash at +60, read the inlined name at body+64, and KEEP only bodies where
R_HashString(name) == hash. This bypasses zone walking entirely, exactly like the
console-side scanner. It catches images whose name is inline-adjacent (streamed
images + zero-inline images -- i.e. everything the PC-ipak pixel path can source).
Genuinely-inline-pixel custom images (name sits after the pixel blob) are the
.pcpix inline path's job, not this one.

Emitted per image: <safe name>.meta with the keys ipak_stream.read_meta reads
(name, hash, width, height, depth, mapType, semantic, category). width/height are
authoritative here; mapType/semantic/category are defaulted (minor metadata, and
prepare's genuine-corpus source overrides them when the image exists on console).
`format` is omitted: the PC-ipak pixel path derives the real GX2 format from the
IWI. PC .ff images have no inline pixels, so no .pcpix is produced -- prepare's
genuine / PC-ipak sources supply the pixels.

Usage:
  python pc_image_enum.py <pc zone> <out dump dir>
  python pc_image_enum.py --selfcheck <pc zone>     # report hit count, no write
Then:
  python ipak_stream.py prepare <out dump dir> <out bodies> --ipak map.ipak \
        --pc-ipaks <that game's base/mp/... .ipak>
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipak as IP

FOLLOW = 0xFFFFFFFF
BODY = 64
NAME_CHARS = set(b"abcdefghijklmnopqrstuvwxyz0123456789_/~$#&+.-")


def scan_pc_images(zone_bytes):
    """-> {nameHash: dict(name,hash,width,height,depth,mapType,semantic,
    category)} for every hash-valid PC GfxImage body in an LE zone."""
    d = zone_bytes
    out = {}
    o = d.find(b'\xff\xff\xff\xff')
    while o != -1:
        B = o - 56                       # name ptr FOLLOW sits at body+56
        nxt = d.find(b'\xff\xff\xff\xff', o + 4)
        if B < 0 or B + BODY > len(d):
            o = nxt
            continue
        # name string is inlined right after the 64-byte body
        e = d.find(b'\x00', B + BODY, B + BODY + 128)
        if e <= B + BODY:
            o = nxt
            continue
        nm = d[B + BODY:e]
        if len(nm) < 3 or not all(c in NAME_CHARS for c in nm):
            o = nxt
            continue
        name = nm.decode('latin-1')
        h = struct.unpack_from('<I', d, B + 60)[0]
        if IP.r_hash_string(name) != h:
            o = nxt
            continue
        width, height, depth = struct.unpack_from('<HHH', d, B + 4)
        out[h] = dict(name=name, hash=h, width=width, height=height,
                      depth=max(1, depth), mapType=3, semantic=0, category=0)
        o = nxt
    return out


def safe_name(name):
    return name.replace('/', '__')


def write_metas(images, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    keys = ('name', 'hash', 'width', 'height', 'depth',
            'mapType', 'semantic', 'category')
    for img in images.values():
        path = os.path.join(out_dir, safe_name(img['name']) + '.meta')
        with open(path, 'w') as f:
            for k in keys:
                f.write('%s %s\n' % (k, img[k]))
    return len(images)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('zone')
    ap.add_argument('out_dir', nargs='?')
    ap.add_argument('--selfcheck', action='store_true')
    a = ap.parse_args()
    imgs = scan_pc_images(open(a.zone, 'rb').read())
    print('%s: %d GfxImages (hash-validated)'
          % (os.path.basename(a.zone), len(imgs)))
    if a.selfcheck or not a.out_dir:
        for v in sorted(imgs.values(), key=lambda x: x['name'])[:8]:
            print('   %-40s %5dx%-5d d%d' %
                  (v['name'], v['width'], v['height'], v['depth']))
        return
    n = write_metas(imgs, a.out_dir)
    print('wrote %d .meta files to %s' % (n, a.out_dir))


if __name__ == '__main__':
    main()
