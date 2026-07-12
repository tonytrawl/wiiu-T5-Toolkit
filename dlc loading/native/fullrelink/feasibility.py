#!/usr/bin/env python3
"""
FEASIBILITY PASS (isolated side project; base linker READ-ONLY).

Assess a full PC->Wii U conversion of patch_mp. Because we HAVE the genuine console
patch_mp as a backbone (same zone minus the extra DLC map rows), the real conversion
surface is only what DIFFERS. This pass:
  1. walks the PC patch_mp zone (type histogram, mapstable rows).
  2. walks the console patch_mp backbone (type histogram, mapstable rows).
  3. diffs type distributions and the mapstable (how many extra maps PC carries).
  4. classifies every PC asset type: have-converter / carry-verbatim-from-console / blocked.

Run from native_linker/:
  python "../dlc loading/native/fullrelink/feasibility.py" \
      --pc  "../dlc loading/native/pc_patch_mp.ff" \
      --con "../dlc loading/native/upd_patch_mp.ff" --tag mp
"""
import sys, os, argparse
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
for _p in (os.path.join(_ROOT, 'native_linker'), os.path.join(_ROOT, 'wiiu_ref'),
           os.path.join(_ROOT, 'WiiU_FF_Studio'), os.path.join(_ROOT, 'tools'),
           os.path.join(_ROOT, 'dlc loading', 'native')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
_ORIG_CWD = os.getcwd()
os.chdir(os.path.join(_ROOT, 'native_linker'))

import ff_decrypt, wiiu_ff, wiiu_zone, pc_zone
import walker as W
import body_relayout as BR
import patch_relink as PR

# converter status per PC/console asset-type name. Derived from pc_convert_pipeline's
# strategy (simple/world = native PCConverter byte-exact; complex GX2 = carry the
# genuine console body) and body_relayout.DELIMITERS (types with a solved console
# delimiter we can copy verbatim + relink).
VERBATIM = set(BR.DELIMITERS.keys())      # solved console delimiter -> carry-verbatim OK
# types the native converter sources directly (world/simple) -- from pipeline docs
NATIVE_OK = {'StringTable', 'RawFile', 'ScriptParseTree', 'LeaderboardDef', 'DDLFile',
             'KeyValuePairs', 'PhysPreset', 'PhysConstraints', 'TracerDef',
             'FootstepTableDef', 'GfxImage', 'Material', 'MaterialTechniqueSet',
             'XModel', 'FxEffectDef', 'DestructibleDef', 'XAnimParts', 'GfxLightDef',
             'FontIcon', 'SndBank', 'GameWorldMp', 'GfxWorld', 'MenuList'}
# console layouts still unreversed (pipeline/handoff): a from-scratch emit is blocked,
# but a single instance can be carried verbatim from the console backbone.
BLOCKED_STRUCT = {'WeaponVariantDef', 'WeaponFullDef', 'weapon', 'MenuList'}


def decrypt_any(path):
    if not os.path.isabs(path):
        path = os.path.join(_ORIG_CWD, path)
    data = open(path, 'rb').read()
    endian, key, ver, label = ff_decrypt.detect_platform(data)
    hdr, zone, n = ff_decrypt.decrypt_ff(data, key, endian)
    return hdr['name'], zone, label


def con_maps(zone, tag):
    h = PR._st_header(zone, ('%s/mapstable.csv' % tag).encode(), le=False)
    if not h:
        return None
    cc, rr, tbl = PR.read_table(zone, h[0], le=False)
    return [row[0] for row in tbl if row and row[0].startswith(tag + '_')]


def pc_maps(zone, tag):
    h = PR._st_header(zone, ('%s/mapstable.csv' % tag).encode(), le=True)
    if not h:
        return None
    cc, rr, tbl = PR.read_table(zone, h[0], le=True)
    return [row[0] for row in tbl if row and row[0].startswith(tag + '_')]


def classify(t):
    root = W.ASSET_ROOT.get(t, t)
    if t in ('weapon', 'WeaponVariantDef') or root in ('WeaponVariantDef',):
        return 'CARRY-VERBATIM (console WeaponDef unreversed; from backbone)'
    if t == 'MenuList' or root == 'MenuList':
        return 'CARRY-VERBATIM (console menuDef unreversed; from backbone)'
    if root in VERBATIM:
        return 'carry-verbatim (solved delimiter)'
    if t in NATIVE_OK or root in NATIVE_OK:
        return 'native-convert'
    return 'UNKNOWN -> investigate'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pc', required=True)
    ap.add_argument('--con', required=True)
    ap.add_argument('--tag', default='mp')
    a = ap.parse_args()

    # ---- console backbone ----
    _h, cz, _n = wiiu_ff.decrypt(open(
        a.con if os.path.isabs(a.con) else os.path.join(_ORIG_CWD, a.con), 'rb').read())
    cr = wiiu_zone.ZoneReader(cz); cr.read_string_table(); cr.read_asset_list()
    con_hist = Counter(nm for _, _, nm in cr.assets)
    cmaps = con_maps(cz, a.tag)

    # ---- PC zone ----
    name, pz, label = decrypt_any(a.pc)
    pr = pc_zone.PCZoneReader(pz); pr.read_string_table(); pr.read_asset_list()
    pc_hist = Counter(nm for _, nm, _ in pr.assets)
    pmaps = pc_maps(pz, a.tag)

    print('== PC %s (%s): %d assets, %d B' % (name, label, pr.asset_count, len(pz)))
    print('== console backbone: %d assets, %d B' % (cr.asset_count, len(cz)))
    print()
    print('== mapstable rows ==')
    print('   console maps (%d): %s' % (len(cmaps or []), cmaps))
    print('   PC maps      (%d): %s' % (len(pmaps or []), pmaps))
    if cmaps is not None and pmaps is not None:
        extra = [m for m in pmaps if m not in set(cmaps)]
        print('   PC-only maps (%d): %s' % (len(extra), extra))
    print()

    print('== PC asset-type histogram + conversion classification ==')
    allt = sorted(set(pc_hist) | set(con_hist), key=lambda t: -pc_hist.get(t, 0))
    bucket = Counter()
    for t in allt:
        pcn = pc_hist.get(t, 0); con = con_hist.get(t or '', 0)
        cls = classify(t) if t else 'UNKNOWN(type id)'
        bucket[cls.split(' ')[0]] += pcn
        flag = '' if pcn == con else '   <-- DELTA %+d' % (pcn - con)
        print('   %-22s PC=%-5d con=%-5d  %s%s' % (t, pcn, con, cls, flag))
    print()
    print('== conversion-surface summary (by PC asset count) ==')
    for k, v in bucket.most_common():
        print('   %-18s %d' % (k, v))


if __name__ == '__main__':
    main()
