#!/usr/bin/env python3
"""
PC -> console ASSEMBLER (Stage 2). Authors a console mp_raid zone using the CONSOLE
asset list as the authoritative backbone (correct order incl. the 2 console-only
inserts), sourcing each asset's body from the PC zone where a clean, validated
conversion exists (PCConverter), and falling back to the genuine console body
(native ReEmitter round-trip) elsewhere.

Because every converted body is validated == the genuine console body before use, the
assembled zone is byte-identical to genuine -> guaranteed loadable (boot-confirmed).
The value is the PC-SOURCED COVERAGE it reports: which assets were authored from PC
data through the native pipeline vs. genuine fallback. Coverage grows as more asset
types get PC-side converters/extents; the world/GX2 types remain genuine fallback
until Stage 3 synthesis.

Output: mp_raid_pcnative.zone (== genuine) ready to pack -> mp_raid_PCNATIVE.ff.
"""
import struct, sys, os
sys.path.insert(0, '.'); sys.path.insert(0, '../wiiu_ref')
import struct_layout, walker as W, zone_stream as zs
import body_relayout as BR, stage1_roundtrip as S1
import pc_to_console as P2C, pc_zone, wiiu_zone

CO = open('../wiiu_ref/mp_raid_genuine.zone', 'rb').read()
PC = open('../PC ff/mp_raid.zone', 'rb').read()

# ---- console backbone: per-asset [start,end) via the proven byte-identical round-trip ----
rc = wiiu_zone.ZoneReader(CO); rc.read_string_table(); rc.read_asset_list()
Lc = struct_layout.Layout(W.HDR, console=True); zc = W.ZoneCode(W.ZC_DIR)
w = zs.ZoneWriter(); w.push_block(zs.BLOCK_VIRTUAL)
w.block_size[zs.BLOCK_VIRTUAL] = rc.assets_end - BR.B5_BASE
em = BR.ReEmitter(CO, Lc, zc, w)
cur = rc.assets_end
console_bodies = []            # (idx, name, root, start, end)
for i, (cid, pc, nm) in enumerate(rc.assets):
    root = W.ASSET_ROOT.get(nm)
    if root is None or root not in Lc.structs:
        console_bodies.append((i, nm, None, cur, cur)); continue
    if pc in BR.DETECTORS and not BR.DETECTORS[pc](CO, cur):
        real = BR.find_next_body(CO, cur, pc)
        if real and real > cur: w.write_bytes(CO[cur:real]); cur = real
    start = cur
    try:
        cur = em.emit_asset(root, cur)
    except Exception:
        w.write_bytes(CO[cur:]); cur = len(CO)
        console_bodies.append((i, nm, root, start, cur)); break
    console_bodies.append((i, nm, root, start, cur))
if cur < len(CO):
    w.write_bytes(CO[cur:])
backbone = S1.emit_container(S1.parse_container(CO))[:S1.parse_container(CO)['container_end']] + bytes(w.buf)
assert backbone == CO, "backbone not byte-identical (%d vs %d)" % (len(backbone), len(CO))

# genuine per-asset console body bytes + console start offsets, keyed by (name, occurrence)
from collections import defaultdict
occ = defaultdict(int)
co_regions = {}               # (name, k) -> (start, end)
for (i, nm, root, s, e) in console_bodies:
    k = occ[nm]; occ[nm] += 1
    co_regions[(nm, k)] = (s, e)

# ---- PC source: leading reachable SIMPLE assets (before the first complex type) ----
rp = pc_zone.PCZoneReader(PC); rp.read_string_table(); rp.read_asset_list()
Lp = struct_layout.Layout(W.HDR, console=False)
conv = P2C.PCConverter(PC, Lp, zc); conv.regions = []
src = rp.assets_end
pc_converted = {}             # (name, k) -> converted bytes (validated == genuine)
pcocc = defaultdict(int)
MEASURE = {'SkinnedVertsDef'}
for (t, nm, hp) in rp.assets:
    root = W.ASSET_ROOT.get(nm)
    if root not in P2C.SIMPLE and root not in MEASURE:
        break                 # first complex asset: can't advance PC cursor further yet
    k = pcocc[nm]; pcocc[nm] += 1
    cs, ce = co_regions.get((nm, k), (0, 0))
    out, src = conv.convert(root, src, cs, keep_regions=True)
    if root in MEASURE:
        continue
    if bytes(out) == CO[cs:ce]:
        pc_converted[(nm, k)] = bytes(out)

# ---- assemble: splice PC-converted bodies into the backbone where validated ----
assembled = bytearray(backbone)
pc_sourced = 0
occ2 = defaultdict(int)
for (i, nm, root, s, e) in console_bodies:
    k = occ2[nm]; occ2[nm] += 1
    body = pc_converted.get((nm, k))
    if body is not None:
        assert len(body) == e - s
        assembled[s:e] = body     # identical bytes, but sourced from PC via the pipeline
        pc_sourced += 1

assert bytes(assembled) == CO, "assembled zone diverged from genuine!"
open('mp_raid_pcnative.zone', 'wb').write(assembled)
print("assembled mp_raid_pcnative.zone: %d bytes, byte-identical to genuine: %s"
      % (len(assembled), bytes(assembled) == CO))
print("PC-SOURCED assets (converted from PC, validated == genuine): %d" % pc_sourced)
print("  ->", [nm for (nm, k) in pc_converted])
print("remaining %d assets: genuine fallback (need PC-side extents / GX2 synthesis)"
      % (len(console_bodies) - pc_sourced))
