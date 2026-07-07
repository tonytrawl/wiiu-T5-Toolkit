#!/usr/bin/env python3
"""
END-TO-END PC .ff -> Wii U .ff + .ipak pipeline (the orchestrator the GUI calls).

Given a PC (Plutonium/T6, v147 LE) fastfile, this runs every stage we have built:

  1. UNLINK   decrypt+decompress the PC .ff -> PC zone (tools/ff_decrypt).
  2. CONVERT  PC zone -> console (BE v148) zone. Uses the native PCConverter for the
              simple/world assets it can source byte-exact, over a console backbone
              (the round-trip ReEmitter). Complex GX2 types (material/techset/xmodel/
              fx) + GfxWorld geometry vd0 fall back to the genuine console body -- so a
              BOOTABLE .ff is produced only when a console reference for that map exists
              (retail maps: auto-found in wiiu_ref/Original FF/<name>.ff, or supplied).
              For a novel/custom map (no console reference) the zone stage is skipped and
              only the .ipak is produced, until complex-type + geometry synthesis lands.
  3. REPACK   console zone -> Wii U v148 .ff (WiiU_FF_Studio/wiiu_ff.pack).
  4. IPAK     scan the PC zone's GfxImages (pc_image_enum) and author the map .ipak from
              the PC image sources (ipak_stream: genuine corpus + PC ipaks -> GX2 tiles).
              This half is general and validated byte-exact vs retail (mp_la: 287/287).

Returns a report dict; writes <out_dir>/<name>_wiiu.ff and <out_dir>/<name>.ipak.
The geometry vd0 uses the current genuine-backbone fix; swap in the real synthesis
(see HANDOFF_geometry_vd0.md) without touching this orchestrator.
"""
import argparse
import os
import struct
import sys
from collections import defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_HERE, os.path.join(_ROOT, 'wiiu_ref'), os.path.join(_ROOT, 'tools'),
           os.path.join(_ROOT, 'WiiU_FF_Studio')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ff_decrypt                       # tools/ff_decrypt.py
import wiiu_ff                          # WiiU_FF_Studio/wiiu_ff.py
import struct_layout
import walker as W
import zone_stream as zs
import body_relayout as BR
import stage1_roundtrip as S1
import pc_to_console as P2C
import pc_zone
import wiiu_zone
import pc_image_enum
import ipak_stream
import dlc_packs

ORIGINAL_FF_DIR = os.path.join(_ROOT, 'wiiu_ref', 'Original FF')
DEFAULT_PC_IPAKS = ipak_stream.DEFAULT_PC_IPAKS
DEFAULT_GENUINE = ipak_stream.DEFAULT_GENUINE_ZONES
MEASURE = {'SkinnedVertsDef'}


# ---------------------------------------------------------------- helpers ---

def _decrypt_any(path):
    """Decrypt a PC or Wii U .ff -> (name, zone_bytes, label)."""
    data = open(path, 'rb').read()
    endian, key, ver, label = ff_decrypt.detect_platform(data)
    hdr, zone, n = ff_decrypt.decrypt_ff(data, key, endian)
    return hdr['name'], zone, label


def _find_console_ref(name, explicit):
    """Locate a genuine console .ff/.zone backbone for this map, if any."""
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    for ext in ('.zone', '.ff'):
        cand = os.path.join(ORIGINAL_FF_DIR, name + ext)
        if os.path.isfile(cand):
            return cand
    return None


def _load_console_zone(ref):
    if ref.lower().endswith('.zone'):
        return open(ref, 'rb').read()
    _n, zone, _l = _decrypt_any(ref)
    return zone


# ----------------------------------------------------- zone conversion -----

def convert_zone(CO, PC, progress=print):
    """PC zone -> console zone over the genuine console backbone (generalized
    produce_pc_ff). Returns (console_zone_bytes, pc_sourced_names). Every spliced
    body is validated == the genuine console body, so the result is loadable."""
    zc = W.ZoneCode(W.ZC_DIR)
    Lc = struct_layout.Layout(W.HDR, console=True)

    # console backbone via the proven byte-identical round-trip; capture per-asset extents
    rc = wiiu_zone.ZoneReader(CO); rc.read_string_table(); rc.read_asset_list()
    w = zs.ZoneWriter(); w.push_block(zs.BLOCK_VIRTUAL)
    w.block_size[zs.BLOCK_VIRTUAL] = rc.assets_end - BR.B5_BASE
    em = BR.ReEmitter(CO, Lc, zc, w)
    cur = rc.assets_end
    console_bodies = []
    for i, (cid, pc, nm) in enumerate(rc.assets):
        root = W.ASSET_ROOT.get(nm)
        if root is None or root not in Lc.structs:
            console_bodies.append((i, nm, None, cur, cur)); continue
        if pc in BR.DETECTORS and not BR.DETECTORS[pc](CO, cur):
            real = BR.find_next_body(CO, cur, pc)
            if real and real > cur:
                w.write_bytes(CO[cur:real]); cur = real
        start = cur
        try:
            cur = em.emit_asset(root, cur)
        except Exception:
            w.write_bytes(CO[cur:]); cur = len(CO)
            console_bodies.append((i, nm, root, start, cur)); break
        console_bodies.append((i, nm, root, start, cur))
    if cur < len(CO):
        w.write_bytes(CO[cur:])
    cinfo = S1.parse_container(CO)
    backbone = S1.emit_container(cinfo)[:cinfo['container_end']] + bytes(w.buf)
    if backbone != CO:
        raise RuntimeError('console backbone not byte-identical (%d vs %d)'
                           % (len(backbone), len(CO)))

    occ = defaultdict(int); co_regions = {}
    for (i, nm, root, s, e) in console_bodies:
        k = occ[nm]; occ[nm] += 1
        co_regions[(nm, k)] = (s, e)

    # PC source: leading reachable SIMPLE/world assets (until the first complex type)
    rp = pc_zone.PCZoneReader(PC); rp.read_string_table(); rp.read_asset_list()
    Lp = struct_layout.Layout(W.HDR, console=False)
    conv = P2C.PCConverter(PC, Lp, zc); conv.regions = []
    src = rp.assets_end
    pc_converted = {}; pcocc = defaultdict(int)
    for (t, nm, hp) in rp.assets:
        root = W.ASSET_ROOT.get(nm)
        if root not in P2C.SIMPLE and root not in MEASURE:
            break
        k = pcocc[nm]; pcocc[nm] += 1
        cs, ce = co_regions.get((nm, k), (0, 0))
        out, src = conv.convert(root, src, cs, keep_regions=True)
        if root in MEASURE:
            continue
        if bytes(out) == CO[cs:ce]:
            pc_converted[(nm, k)] = bytes(out)

    assembled = bytearray(backbone); occ2 = defaultdict(int); sourced = []
    for (i, nm, root, s, e) in console_bodies:
        k = occ2[nm]; occ2[nm] += 1
        body = pc_converted.get((nm, k))
        if body is not None and len(body) == e - s:
            assembled[s:e] = body; sourced.append(nm)
    return bytes(assembled), sourced


# ----------------------------------------------------------- ipak stage ----

def build_ipak(pc_zone_bytes, name, out_dir, pc_ipaks, genuine_zones, progress=print):
    meta_dir = os.path.join(out_dir, '_meta_' + name)
    body_dir = os.path.join(out_dir, '_bodies_' + name)
    ipak_path = os.path.join(out_dir, name + '.ipak')
    imgs = pc_image_enum.scan_pc_images(pc_zone_bytes)
    pc_image_enum.write_metas(imgs, meta_dir)
    progress('  images: %d GfxImages enumerated from PC zone' % len(imgs))
    ns = argparse.Namespace(dump_dir=meta_dir, out_dir=body_dir, ipak=ipak_path,
                            genuine_zones=genuine_zones, pc_ipaks=pc_ipaks)
    ipak_stream.cmd_prepare(ns)          # authors bodies + the ipak
    return ipak_path if os.path.isfile(ipak_path) else None


# --------------------------------------------------------------- driver ----

def convert_pc_ff(pc_ff_path, out_dir, pc_ipaks=None, console_ref=None,
                  genuine_zones=None, progress=print):
    os.makedirs(out_dir, exist_ok=True)
    pc_ipaks = [p for p in (pc_ipaks or DEFAULT_PC_IPAKS) if os.path.exists(p)]
    genuine_zones = genuine_zones or DEFAULT_GENUINE
    report = {'ff': None, 'ipak': None, 'name': None, 'pc_sourced': 0,
              'bootable': False, 'notes': []}

    progress('[1/4] unlink: decrypting PC fastfile...')
    name, pc_zone_bytes, label = _decrypt_any(pc_ff_path)
    report['name'] = name
    if label != 'PC':
        report['notes'].append('input is %s, not PC -- expected a PC v147 fastfile' % label)
    progress("       name='%s'  platform=%s  zone=%d bytes" % (name, label, len(pc_zone_bytes)))

    # auto-select the map's DLC source ipak(s) (dlcN/dlczmN + per-map). Stock
    # maps resolve to nothing extra and keep the base/mp-only path.
    pc_ipaks = dlc_packs.resolve_pc_ipaks(name, pc_ipaks, pc_zone_bytes,
                                          progress=progress)

    progress('[2/4] convert: PC zone -> console zone...')
    ref = _find_console_ref(name, console_ref)
    if ref:
        CO = _load_console_zone(ref)
        console_zone, sourced = convert_zone(CO, pc_zone_bytes, progress)
        report['pc_sourced'] = len(sourced)
        report['bootable'] = True
        progress('       backbone=%s  PC-sourced assets=%d  (rest: genuine fallback)'
                 % (os.path.basename(ref), len(sourced)))
        progress('[3/4] repack: console zone -> Wii U fastfile...')
        ff = wiiu_ff.pack(console_zone, name)
        ff_path = os.path.join(out_dir, name + '_wiiu.ff')
        open(ff_path, 'wb').write(ff)
        report['ff'] = ff_path
        progress('       wrote %s (%d bytes)' % (os.path.basename(ff_path), len(ff)))
    else:
        report['notes'].append(
            'no console reference for "%s" -- a bootable .ff needs complex-type + '
            'geometry synthesis (unbuilt); producing .ipak only.' % name)
        progress('       [skip] no console backbone found; see notes. (.ipak still built)')
        progress('[3/4] repack: skipped (no console zone)')

    progress('[4/4] ipak: authoring map image pak from PC sources...')
    report['ipak'] = build_ipak(pc_zone_bytes, name, out_dir, pc_ipaks,
                                genuine_zones, progress)
    if report['ipak']:
        progress('       wrote %s' % os.path.basename(report['ipak']))
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('pc_ff')
    ap.add_argument('out_dir')
    ap.add_argument('--console-ref', default=None,
                    help='genuine console .ff/.zone backbone (auto-found for retail maps)')
    ap.add_argument('--pc-ipaks', nargs='*', default=None)
    ap.add_argument('--genuine-zones', nargs='*', default=None)
    a = ap.parse_args()
    rep = convert_pc_ff(a.pc_ff, a.out_dir, a.pc_ipaks, a.console_ref,
                        a.genuine_zones)
    print('\n=== RESULT ===')
    print(' name      :', rep['name'])
    print(' wii u ff  :', rep['ff'] or '(not produced -- see notes)')
    print(' ipak      :', rep['ipak'] or '(none)')
    print(' bootable  :', rep['bootable'], '(%d PC-sourced assets)' % rep['pc_sourced'])
    for n in rep['notes']:
        print(' note      :', n)


if __name__ == '__main__':
    main()
