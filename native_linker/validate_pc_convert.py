#!/usr/bin/env python3
"""Validate the PC->console converter against the genuine console zone as oracle.

Walk the genuine console zone with the proven ReEmitter to capture each asset's
[start,end) console bytes. Walk the PC zone with PCConverter for the simple types.
Match by asset-name order and assert converted-PC-body == genuine-console-body.
"""
import struct, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'wiiu_ref'))
import struct_layout, walker as W, zone_stream as zs
import body_relayout as BR, pc_to_console as P2C, pc_zone
import wiiu_zone

CO = open(os.path.join('..','wiiu_ref','mp_raid_genuine.zone'),'rb').read()
PC = open(os.path.join('..','PC ff','mp_raid.zone'),'rb').read()

# --- console: capture per-asset regions via ReEmitter (byte-identical round-trip) ---
rc = wiiu_zone.ZoneReader(CO); rc.read_string_table(); rc.read_asset_list()
Lc = struct_layout.Layout(W.HDR, console=True); zc = W.ZoneCode(W.ZC_DIR)
w = zs.ZoneWriter(); w.push_block(zs.BLOCK_VIRTUAL)
w.block_size[zs.BLOCK_VIRTUAL] = rc.assets_end - BR.B5_BASE
em = BR.ReEmitter(CO, Lc, zc, w)
cur = rc.assets_end
console_regions = {}   # name -> list of (start,end)
NMAX = 40
for i,(cid,pc,nm) in enumerate(rc.assets[:NMAX]):
    root = W.ASSET_ROOT.get(nm)
    if root is None or root not in Lc.structs:
        continue
    if pc in BR.DETECTORS and not BR.DETECTORS[pc](CO, cur):
        real = BR.find_next_body(CO, cur, pc)
        if real and real > cur: cur = real
    start = cur
    try:
        cur = em.emit_asset(root, cur)
    except Exception as e:
        print("console walk stopped at %d %s: %s" % (i, nm, e)); break
    console_regions.setdefault(nm, []).append((start, cur))

# --- PC: convert leading simple assets ---
rp = pc_zone.PCZoneReader(PC); rp.read_string_table(); rp.read_asset_list()
Lp = struct_layout.Layout(W.HDR, console=False)
conv = P2C.PCConverter(PC, Lp, zc)
src = rp.assets_end
print("PC bodies start 0x%x, console bodies start 0x%x\n" % (rp.assets_end, rc.assets_end))
# SkinnedVertsDef: converted only to ADVANCE the PC cursor (console layout diverges: +4
# trailing / FOLLOW-name), not validated.
MEASURE = {'SkinnedVertsDef'}
co_idx = {}
passed = fail = 0
for i,(t,nm,hp) in enumerate(rp.assets):
    root = W.ASSET_ROOT.get(nm)
    if root not in P2C.SIMPLE and root not in MEASURE:
        print("[%d] %-16s STOP (first non-simple asset)" % (i, nm)); break
    lst = console_regions.get(nm, [])
    k = co_idx.get(nm, 0); co_idx[nm] = k+1
    cs, ce = lst[k] if k < len(lst) else (0, 0)
    out, nsrc = conv.convert(root, src, cs)
    src = nsrc
    if root in MEASURE:
        print("[%d] %-16s (advance only, console layout diverges)" % (i, nm)); continue
    genuine = CO[cs:ce]
    ok = out == genuine
    print("[%d] %-16s pc->co %d bytes  genuine %d bytes  unresolved=%d  MATCH=%s"
          % (i, nm, len(out), len(genuine), conv.unresolved, ok))
    if ok: passed += 1
    else:
        fail += 1
        for j in range(min(len(out),len(genuine))):
            if out[j]!=genuine[j]:
                print("    first diff @%d: conv=%s gen=%s" %
                      (j, out[j:j+8].hex(), genuine[j:j+8].hex())); break
print("\nsimple-prefix conversion: %d passed, %d failed" % (passed, fail))
