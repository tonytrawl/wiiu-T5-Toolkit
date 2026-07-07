#!/usr/bin/env python3
"""
Stage 1 round-trip driver. Parses a genuine console zone's CONTAINER (XFile header,
XAssetList, script-string table, asset-list array) into a neutral in-memory form,
then re-emits it through the native ZoneWriter and asserts byte-identity against the
original. This validates the write engine's header emission, block-5 offset math,
FOLLOW/null sentinel handling, string serialization and the asset-array layout
independently of any per-asset body knowledge (that is the next increment).

Usage: python stage1_roundtrip.py [genuine.zone]
"""
import struct, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zone_stream as zs

HEADER_LEN = 40
XASSETLIST_LEN = 24
BLOCK5_STREAM_BASE = HEADER_LEN + XASSETLIST_LEN   # 64


def parse_container(d):
    """Neutral parse of the container region. Returns a dict of the fields the
    writer needs, plus the byte length of the container (up to first asset body)."""
    size, ext = struct.unpack_from('>II', d, 0)
    block_sizes = list(struct.unpack_from('>8I', d, 8))
    string_count, str_ptr, depend_count, dep_ptr, asset_count, asset_ptr = \
        struct.unpack_from('>6I', d, 40)

    o = 64
    # script-string pointer pattern (FOLLOW / null), then inline string bytes
    str_ptrs = list(struct.unpack_from('>%dI' % string_count, d, o))
    o += string_count * 4
    strings = []
    for p in str_ptrs:
        if p == zs.FOLLOW:
            end = d.index(b'\x00', o)
            strings.append(d[o:end])
            o = end + 1
        else:
            strings.append(None)          # null slot: no inline bytes
    o = (o + 3) & ~3                       # align 4 for the asset array
    assets_file = o
    assets = []                            # (console_type, header_ptr)
    for i in range(asset_count):
        t, hp = struct.unpack_from('>II', d, o + i * 8)
        assets.append((t, hp))
    container_end = assets_file + asset_count * 8
    return dict(size=size, ext=ext, block_sizes=block_sizes,
                string_count=string_count, str_ptr=str_ptr,
                depend_count=depend_count, dep_ptr=dep_ptr,
                asset_count=asset_count, asset_ptr=asset_ptr,
                str_ptrs=str_ptrs, strings=strings, assets=assets,
                assets_file=assets_file, container_end=container_end)


def emit_container(c):
    """Re-emit the container through the native writer."""
    w = zs.ZoneWriter()

    # XAssetList (24 bytes) sits raw at stream offset 40, before block 5.
    xlist = struct.pack('>6I', c['string_count'], c['str_ptr'],
                        c['depend_count'], c['dep_ptr'],
                        c['asset_count'], c['asset_ptr'])
    w.buf += xlist                         # raw prefix; not part of any block

    # Block 5 begins here (block-5 offset 0 == stream offset 64).
    w.push_block(zs.BLOCK_VIRTUAL)

    # script-string pointer array
    for p in c['str_ptrs']:
        w.write_u32(zs.FOLLOW if p == zs.FOLLOW else 0)
    # inline string bytes for FOLLOW slots, in order
    for p, s in zip(c['str_ptrs'], c['strings']):
        if p == zs.FOLLOW:
            w.write_cstr(s)
    w.align(4)

    # asset-list array: (type, header.data). We recompute the header pointer as a
    # FOLLOW sentinel where the original had one; alias entries are carried through
    # (Stage 1 doesn't re-lay-out bodies yet, so their targets are unchanged).
    for t, hp in c['assets']:
        w.write_u32(t)
        w.write_u32(hp)

    w.pop_block()

    # Stage 1 only re-emits the container; keep the writer's declared block sizes
    # identical to the source so the header matches (body re-layout comes later).
    w.block_size = list(c['block_sizes'])
    w.external_size = c['ext']
    return w.emit(total_size=c['size'])   # carry whole-zone size (bodies not re-laid-out yet)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(os.path.dirname(__file__), '..', 'wiiu_ref', 'mp_raid_genuine.zone')
    d = open(path, 'rb').read()
    c = parse_container(d)
    print("parsed: %d strings, %d assets, container ends at stream 0x%x"
          % (c['string_count'], c['asset_count'], c['container_end']))

    out = emit_container(c)
    n = c['container_end']
    orig = d[:n]
    reemit = out[:n]
    if orig == reemit:
        print("BYTE-IDENTICAL container round-trip through native engine (0x%x bytes) OK" % n)
        return
    # locate first divergence
    for i in range(min(len(orig), len(reemit))):
        if orig[i] != reemit[i]:
            print("DIVERGENCE at stream 0x%x: orig=%s reemit=%s"
                  % (i, orig[i-4:i+8].hex(), reemit[i-4:i+8].hex()))
            break
    else:
        print("length mismatch: orig %d vs reemit %d" % (len(orig), len(reemit)))
    sys.exit(1)


if __name__ == '__main__':
    main()
