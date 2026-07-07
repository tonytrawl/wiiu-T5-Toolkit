#!/usr/bin/env python3
"""
DLC source-ipak resolver for the PC -> Wii U conversion pipeline.

A DLC map's streamed textures do NOT live in base/mp.ipak; they live in a shared
`dlcN.ipak` (zm: `dlczmN.ipak`), plus a per-map `<map>.ipak` for the three bonus
maps (mp_frostbite, mp_nuketown_2020, zm_nuked).  See
FINDINGS_dlc_ipak_investigation.md / memory dlc-ipak-partition.

Given a map name (+ its PC zone bytes) this returns the extra ipak(s) to append
to the base --pc-ipaks list so `ipak_stream.prepare` resolves the DLC pixels.

Two ways to know a map's pack, both implemented:
  1. cached table  wiiu_ref/dlc_map_pack.json  (map -> {pack, has_per_map_ipak})
  2. cross-ref fallback: scan the map's GfxImage nameHashes against every
     candidate dlc pack and pick the one contributing the most *new* hashes
     (the same dominant-uniqueNew rule the findings doc uses).  The result is
     cached back into the table.

Stock (non-DLC) maps resolve entirely from base/mp -> no dlc pack dominates ->
returns [] and the pipeline keeps its existing base/mp-only behaviour.
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_WIIUREF = os.path.join(_ROOT, 'wiiu_ref')
if _WIIUREF not in sys.path:
    sys.path.insert(0, _WIIUREF)

import ipak as IP                        # wiiu_ref/ipak.py
import pc_image_enum                     # wiiu_ref/pc_image_enum.py

# READ-ONLY DLC source dir (never write under E:)
DLC_DIR = r'E:\Call of Duty Black Ops II\pluto_t6_dlcs\zone\all'
TABLE_PATH = os.path.join(_WIIUREF, 'dlc_map_pack.json')

# maps that ship their own per-map ipak (bonus/standalone)
PER_MAP_IPAKS = ('mp_frostbite', 'mp_nuketown_2020', 'zm_nuked')

# a dlc pack must supply at least this many *new* image hashes to count as the
# map's source pack; below this a map is treated as stock (base/mp only).
MIN_UNIQUE_NEW = 16

# seed facts (proven in FINDINGS_dlc_ipak_investigation.md); the live cross-ref
# fills in / corrects the rest and caches back to TABLE_PATH.
_SEED_TABLE = {
    # mp
    'mp_skate':    {'pack': 'dlc1', 'has_per_map_ipak': False},
    'mp_downhill': {'pack': 'dlc1', 'has_per_map_ipak': False},
    'mp_hydro':    {'pack': 'dlc1', 'has_per_map_ipak': False},
    'mp_mirage':   {'pack': 'dlc1', 'has_per_map_ipak': False},
    'mp_bridge':   {'pack': 'dlc3', 'has_per_map_ipak': False},
    'mp_nuketown_2020': {'pack': 'dlc0', 'has_per_map_ipak': True},
    # zm (mount name is dlczmN; loadscreen-derived pack->map)
    'zm_nuked':    {'pack': 'dlczm0', 'has_per_map_ipak': True},
    'zm_highrise': {'pack': 'dlczm1', 'has_per_map_ipak': False},
    'zm_prison':   {'pack': 'dlczm2', 'has_per_map_ipak': False},
    'zm_buried':   {'pack': 'dlczm3', 'has_per_map_ipak': False},
    'zm_tomb':     {'pack': 'dlczm4', 'has_per_map_ipak': False},
}


def _is_zm(map_name):
    return map_name.startswith('zm_')


def _candidate_packs(map_name, dlc_dir):
    """[(pack_name, path), ...] for the 5 shared packs of this map's flavour."""
    prefix = 'dlczm' if _is_zm(map_name) else 'dlc'
    out = []
    for i in range(5):
        pn = '%s%d' % (prefix, i)
        p = os.path.join(dlc_dir, pn + '.ipak')
        if os.path.isfile(p):
            out.append((pn, p))
    return out


def _load_table():
    table = dict(_SEED_TABLE)
    if os.path.isfile(TABLE_PATH):
        try:
            with open(TABLE_PATH) as f:
                table.update(json.load(f))
        except (ValueError, OSError):
            pass
    return table


def _save_table(table):
    try:
        with open(TABLE_PATH, 'w') as f:
            json.dump(table, f, indent=2, sort_keys=True)
    except OSError:
        pass


def _crossref_pack(pc_zone_bytes, candidates):
    """Dominant-uniqueNew rule: scan the map's image hashes against the packs in
    order and pick the pack that first supplies the most previously-unseen ones.
    -> (pack_name or None, unique_new_count)."""
    hashes = set(pc_image_enum.scan_pc_images(pc_zone_bytes).keys())
    if not hashes:
        return None, 0
    best, best_new = None, 0
    for pn, path in candidates:
        try:
            pak_hashes = set(e.name_hash for e in IP.IPak.read(path).entries)
        except (OSError, ValueError):
            continue
        new = len(hashes & pak_hashes)
        if new > best_new:
            best, best_new = pn, new
    return best, best_new


def resolve_dlc_ipaks(map_name, pc_zone_bytes=None, dlc_dir=DLC_DIR,
                      progress=None):
    """Return the extra ipak paths (dlcN + optional per-map) to append to the
    base --pc-ipaks list for this map.  [] for a stock/non-DLC map.

    Uses the cached table first; falls back to a live cross-ref (needs
    pc_zone_bytes) for maps not yet tabulated, caching the result back.
    """
    def log(msg):
        if progress:
            progress(msg)

    if not os.path.isdir(dlc_dir):
        return []

    table = _load_table()
    entry = table.get(map_name)

    if entry is None and pc_zone_bytes is not None:
        candidates = _candidate_packs(map_name, dlc_dir)
        pack, new = _crossref_pack(pc_zone_bytes, candidates)
        if pack is not None and new >= MIN_UNIQUE_NEW:
            entry = {'pack': pack,
                     'has_per_map_ipak': map_name in PER_MAP_IPAKS}
            table[map_name] = entry
            _save_table(table)
            log('  dlc: cross-ref resolved %s -> %s (+%d unique images)'
                % (map_name, pack, new))
        else:
            log('  dlc: %s resolves from base/mp (no DLC pack; +%d best)'
                % (map_name, new))
            return []

    if entry is None:
        # not in table and no zone to cross-ref: assume stock.
        return []

    extras = []
    pack_path = os.path.join(dlc_dir, entry['pack'] + '.ipak')
    if os.path.isfile(pack_path):
        extras.append(pack_path)
        log('  dlc: %s -> %s.ipak' % (map_name, entry['pack']))
    else:
        log('  dlc: WARNING %s pack %s.ipak not found in %s'
            % (map_name, entry['pack'], dlc_dir))

    if entry.get('has_per_map_ipak') or map_name in PER_MAP_IPAKS:
        per = os.path.join(dlc_dir, map_name + '.ipak')
        if os.path.isfile(per):
            extras.append(per)
            log('  dlc: + per-map %s.ipak' % map_name)

    return extras


def resolve_pc_ipaks(map_name, base_pc_ipaks, pc_zone_bytes=None,
                     dlc_dir=DLC_DIR, progress=None):
    """base list + resolved DLC pack(s), de-duplicated, order preserved."""
    extras = resolve_dlc_ipaks(map_name, pc_zone_bytes, dlc_dir, progress)
    out = list(base_pc_ipaks)
    for p in extras:
        if p not in out:
            out.append(p)
    return out


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='resolve a DLC map -> source ipaks')
    ap.add_argument('map_name')
    ap.add_argument('--zone', help='PC .zone for the map (enables cross-ref)')
    ap.add_argument('--dlc-dir', default=DLC_DIR)
    a = ap.parse_args()
    zb = open(a.zone, 'rb').read() if a.zone else None
    extras = resolve_dlc_ipaks(a.map_name, zb, a.dlc_dir, progress=print)
    print('DLC ipaks for %s:' % a.map_name)
    for p in extras:
        print('  ', p)
    if not extras:
        print('   (none -- stock/base+mp only)')
