"""Decisive raid confirmation for the field-aware convert_sndbank:
build GENUINE bodies for every root EXCEPT SndBank, AND hold the english INSERT
genuine (author_english_bank is independently broken for raid) — so the ONLY
our-authored SndBank component is the MAIN bank via convert_sndbank. If this boots
past +0x3817ce, the field-aware main-bank conversion is proven correct on hardware."""
import sys, struct
sys.path.insert(0, '.'); sys.path.insert(0, '../wiiu_ref'); sys.path.insert(0, '../WiiU_FF_Studio')
from collections import defaultdict, OrderedDict
import loader_sim as LS, raid_oracle_control as RC
import produce_nobackbone as PN, produce_container as PC
import smalls_convert as SC
import wiiu_ff

# genuine bodies per root (for the transplant of everything-but-SndBank)
em, gsp, CO = LS.simulate(RC.CO_PATH, policy=RC.GEN_POLICY)
gen_by_root = defaultdict(list)
for (i, nm, root, s, e) in gsp:
    if e > s:
        gen_by_root[root].append(CO[s:e])
targets = set(gen_by_root) - {'SndBank'}

# hold the english insert GENUINE (extract mpl_raid.english body from CO)
GEN_ENGLISH = CO[0x45bea9e:0x45c04a5]           # 6663 B, validated above
_orig_eng = SC.author_english_bank
SC.author_english_bank = lambda map_name, *a, **k: GEN_ENGLISH

# phase 1: capture emit order
PN.BISECT_LOG = OrderedDict()
PC.author_zone('../PC ff/mp_raid.zone', 'mp_raid',
               pc_policy=RC.PC_POLICY, our_policy=RC.GEN_POLICY, verbose=False)
log = PN.BISECT_LOG; PN.BISECT_LOG = None
by_root = defaultdict(list)
for s, (root, blen) in log.items():
    by_root[root].append((s, blen))

BMAP = {}
for root in sorted(targets):
    ours = by_root.get(root, []); gen = gen_by_root.get(root, [])
    if len(ours) == len(gen):
        for (s, _), g in zip(ours, gen):
            BMAP[s] = g
print('transplanting %d roots (all but SndBank), %d bodies; english insert=GENUINE; '
      'main SndBank=OUR field-aware convert_sndbank' % (len(targets), len(BMAP)))

# phase 2: build
PN.BISECT_MAP = BMAP
zone, info = PC.author_zone('../PC ff/mp_raid.zone', 'mp_raid',
                            pc_policy=RC.PC_POLICY, our_policy=RC.GEN_POLICY, verbose=False)
PN.BISECT_MAP = None
SC.author_english_bank = _orig_eng
PC.rewalk_zone(zone, 'bisect[sndmain]')
open('mp_raid_bisect_sndmain.zone', 'wb').write(zone)
open('mp_raid_bisect_sndmain.ff', 'wb').write(wiiu_ff.pack(zone, 'mp_raid'))
print('zone %.2f MB  genuine %.2f MB  -> mp_raid_bisect_sndmain.ff'
      % (len(zone) / 1e6, len(CO) / 1e6))
