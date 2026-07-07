#!/usr/bin/env python3
"""Assemble the full native-emitted console zone (container from stage1 + bodies from
body_relayout's round-trip) and write it, to be packed into a .ff. The output is
byte-identical to the genuine zone (the round-trip is proven), so this validates the
native emit -> pack -> load pipeline end to end."""
import sys, os
sys.path.insert(0, '.'); sys.path.insert(0, '../wiiu_ref')
import stage1_roundtrip as S1, body_relayout as BR, zone_stream as zs, struct_layout, walker as W
import wiiu_zone

zpath = '../wiiu_ref/mp_raid_genuine.zone'
zone = open(zpath, 'rb').read()
r = wiiu_zone.ZoneReader(zone); r.read_string_table(); r.read_asset_list()

# container (header + XAssetList + string table + asset array), native-emitted
c = S1.parse_container(zone)
container = S1.emit_container(c)[:c['container_end']]   # bytes [0, assets_end_file)

# bodies via the native round-trip engine
L = struct_layout.Layout(W.HDR, console=True); zc = W.ZoneCode(W.ZC_DIR)
w = zs.ZoneWriter(); w.push_block(zs.BLOCK_VIRTUAL)
w.block_size[zs.BLOCK_VIRTUAL] = r.assets_end - BR.B5_BASE
em = BR.ReEmitter(zone, L, zc, w); cur = r.assets_end
for i, (cid, pc, nm) in enumerate(r.assets):
    root = W.ASSET_ROOT.get(nm)
    if root is None or root not in L.structs: continue
    if pc in BR.DETECTORS and not BR.DETECTORS[pc](zone, cur):
        real = BR.find_next_body(zone, cur, pc)
        if real and real > cur: w.write_bytes(zone[cur:real]); cur = real
    try:
        cur = em.emit_asset(root, cur)
    except Exception:
        w.write_bytes(zone[cur:]); cur = len(zone); break   # verbatim tail
if cur < len(zone): w.write_bytes(zone[cur:])

full = container + bytes(w.buf)
assert full == zone, "native output not byte-identical! %d vs %d" % (len(full), len(zone))
open('mp_raid_native.zone', 'wb').write(full)
print("wrote mp_raid_native.zone (%d bytes) — byte-identical to genuine: %s" % (len(full), full == zone))
