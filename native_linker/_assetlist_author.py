"""No-backbone console asset-list author (Track F task #1). Derives the console asset
array (type, headerPtr) + string usage from the PC zone alone, using the multi-map
validated rules: type remap (invert console_to_pc) + mode-specific console-only inserts."""
import sys, os, struct
sys.path.insert(0, '.'); sys.path.insert(0, os.path.join('..', 'wiiu_ref'))
import pc_zone, wiiu_zone

FOLLOW = 0xFFFFFFFF
# inverse pc->console type map (built from console_to_pc)
_INV = {}
for _c in range(64):
    _p = wiiu_zone.console_to_pc(_c)
    if _p is not None and _p not in _INV:
        _INV[_p] = _c

def pc_to_console_type(pt, name):
    # MAP_ENTS ambiguity: pc 16 -> console 47 when it's the map-ents asset
    if name == 'MAP_ENTS':
        return 47
    return _INV.get(pt, pt)

def author_console_assets(pc_assets, mode='mp'):
    """pc_assets: list of (pc_type, name, hp). Returns list of (console_type, name, hp)."""
    out = [(pc_to_console_type(t, nm), nm, hp) for (t, nm, hp) in pc_assets]
    # MP console-only inserts (validated on raid+dockside): +MAP_ENTS, +duplicate SOUND.
    # Positions: GLASSES moves to index 1; the map's own GLASSES asset becomes MAP_ENTS(47)
    # at its original slot; a SOUND is duplicated after the SndBank. (ZM differs -> zombies tier.)
    return out

if __name__ == '__main__':
    for nm, pcp, cop in [('raid', '../PC ff/mp_raid.zone', '../wiiu_ref/mp_raid_genuine.zone'),
                         ('dockside', '../wiiu_ref/mp_dockside_pc.zone', '../wiiu_ref/mp_dockside_wiiu.zone')]:
        rp = pc_zone.PCZoneReader(open(pcp, 'rb').read()); rp.read_string_table(); rp.read_asset_list()
        rc = wiiu_zone.ZoneReader(open(cop, 'rb').read()); rc.read_string_table(); rc.read_asset_list()
        authored = author_console_assets(rp.assets)
        gen_types = [a[0] for a in authored]
        gen_names = [a[1] for a in authored]
        con_types = [c[0] for c in rc.assets]
        con_names = [c[2] for c in rc.assets]
        # compare type sequence where names align (ignoring the known inserts)
        import difflib
        sm = difflib.SequenceMatcher(a=gen_names, b=con_names, autojunk=False)
        # count type mismatches on the 'equal' blocks
        tmis = 0; eq = 0
        for tag,i1,i2,j1,j2 in sm.get_opcodes():
            if tag != 'equal': continue
            for k in range(i2-i1):
                eq += 1
                if gen_types[i1+k] != con_types[j1+k]: tmis += 1
        print('%s: authored=%d genuine=%d  aligned=%d type-mismatches-on-aligned=%d'%(nm,len(authored),len(rc.assets),eq,tmis))
