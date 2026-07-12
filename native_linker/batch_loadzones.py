#!/usr/bin/env python3
"""Batch-build ALL DLC load fastfiles + the consolidated menu-image ipak.

For every PC DLC load zone: find its streamed sound bank (zm only), convert the
bank (sab_convert), assemble the console zone (assemble_loadzone), and collect
every streamed-image ipak entry the materials embed. Then author ONE merged
big-endian ipak from the collected entries, deployed as base_split8.ipak --
the engine auto-mounts base_split<N> at boot (hw-confirmed 2026-07-09; the
lazy AOC-ipak mount never fires under Cemu's stubbed nn_aoc, so menu images
must live in a boot-mounted pak).

Outputs to <out>/: <zone>.ff, sound/<bank>.all.sabs, base_split8.ipak.
"""
import os, re, sys, subprocess
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
os.chdir(_HERE)
for p in (_HERE, os.path.join(_ROOT, 'wiiu_ref'), os.path.join(_ROOT, 'tools'),
          os.path.join(_ROOT, 'WiiU_FF_Studio')):
    sys.path.insert(0, p)
import ff_decrypt, ipak as IP
import assemble_loadzone as AL
import material_convert as MC
import wiiu_ff

PC_ZONES = AL.PC_DLC_ZONE_DIR
PC_SOUND = os.path.join(os.path.dirname(os.path.dirname(PC_ZONES)), 'sound')
ZONES = [('dlc0_load_mp', None), ('dlc1_load_mp', None), ('dlc2_load_mp', None),
         ('dlc3_load_mp', None), ('dlc4_load_mp', None),
         ('dlczm0_load_zm', ('dlczm0_load_zm', 'dlc0_load_zm')),
         ('dlc1_load_zm', None), ('dlc2_load_zm', None), ('dlc3_load_zm', None),
         ('dlc4_load_zm', None)]


def streamed_bank(pc_zone):
    """The streamed sound bank name referenced by a zm load zone ('X' of
    X.all.sabs), from the '<name>\\0all\\0' tail after the bank path."""
    m = re.search(rb'\x00\xff\xff([\w]{4,40})\x00all\x00', pc_zone)
    return m.group(1).decode() if m else None


def main(out_dir):
    os.makedirs(os.path.join(out_dir, 'sound'), exist_ok=True)
    collected = []
    MC.COLLECT_ENTRIES = collected
    built = []
    for name, rename in ZONES:
        src = os.path.join(PC_ZONES, name + '.ff')
        if not os.path.exists(src):
            print('SKIP (no PC source):', name); continue
        PC = AL.load_pc_zone(src)
        sab_out = None
        if name.endswith('_zm'):
            bank = streamed_bank(PC)
            if bank is None:
                print('SKIP (no streamed bank found):', name); continue
            pc_sab = os.path.join(PC_SOUND, bank + '.all.sabs')
            sab_out = os.path.join(out_dir, 'sound', bank + '.all.sabs')
            if not os.path.exists(pc_sab):
                print('SKIP (missing PC sab %s):' % pc_sab, name); continue
            if not os.path.exists(sab_out):
                subprocess.check_call([sys.executable,
                                       os.path.join(_ROOT, 'WiiU_FF_Studio', 'sab_convert.py'),
                                       pc_sab, '-o', os.path.join(out_dir, 'sound')])
        out_name = rename[1] if rename else name
        zone, bodies, report = AL.assemble(PC, out_name, sab=sab_out,
                                           rename=rename, keep_ipak_kvp=True,
                                           log=lambda *a: None)
        ff = wiiu_ff.pack(zone, out_name)
        ffp = os.path.join(out_dir, out_name + '.ff')
        open(ffp, 'wb').write(ff)
        built.append(out_name)
        print('built %-16s zone %6d B  ff %5d B  (bank: %s)'
              % (out_name, len(zone), len(ff),
                 os.path.basename(sab_out) if sab_out else '-'))

    # merged menu-image ipak (dedupe on (name_hash, data_hash))
    seen = {}
    for nh, dh, payload in collected:
        seen[(nh, dh)] = payload
    entries = [(nh, dh, pl) for (nh, dh), pl in sorted(seen.items())]
    blob = IP.write_ipak(entries, endian='>')
    mp = os.path.join(out_dir, 'base_split8.ipak')
    open(mp, 'wb').write(blob)
    print('merged ipak: %d unique entries -> %s (%d B)' % (len(entries), mp, len(blob)))

    # verify: every embedded hash resolves in the merged pak
    pak = IP.IPak.read(mp)
    have = {(e.name_hash, e.data_hash) for e in pak.entries}
    missing = [k for k in seen if k not in have]
    print('readback verify:', 'OK all %d entries' % len(have) if not missing
          else 'MISSING %d!' % len(missing))
    return built


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(_ROOT, 'dlc loading', 'native'))
