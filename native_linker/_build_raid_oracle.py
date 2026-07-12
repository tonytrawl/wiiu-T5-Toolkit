"""Build raid with our field-aware bank BUT genuine name/assetId/aliasIndex (oracle),
so our bank matches the genuine .sab's console hashes -> fixes the gameplay wild-read.
Verifies positional alias pairing (our PC-walk order == genuine order) by assetFileName."""
import sys, struct
sys.path.insert(0, '.'); sys.path.insert(0, '../wiiu_ref'); sys.path.insert(0, '../WiiU_FF_Studio')
from collections import defaultdict, OrderedDict
import sndbank_probe as S
import loader_sim as LS, raid_oracle_control as RC
import produce_nobackbone as PN, produce_container as PC
import smalls_convert as SC
import wiiu_ff

GEN = open('../wiiu_ref/mp_raid_genuine.zone', 'rb').read()
PCZ = open('../PC ff/mp_raid.zone', 'rb').read()
GB1 = S.parse_sndbank(GEN, 0x45bea9e, '>')[0]

def walk(d, b, e):
    """EXACT mirror of sndbank_probe.parse_sndbank string consumption, capturing per-alias
    (name_word, assetId_word) in order + aliasIndex bytes. Self-verified: returned end must
    equal parse_sndbank's end."""
    u32 = lambda o: struct.unpack_from(e + 'I', d, o)[0]
    name_p, ac, alias_p, ai_p, rc, rp, dc, dp = struct.unpack_from(e + '8I', d, b)
    o = b + S.BODY; aliases = []; listids = []
    if name_p in S.PTRS: o = d.index(b'\x00', o) + 1
    idx = None
    if alias_p in S.PTRS:
        base = o; o += ac * S.ALIASLIST
        for i in range(ac):
            lb = base + i * S.ALIASLIST
            ln, lid, hp, cnt, sq = struct.unpack_from(e + '5I', d, lb)
            listids.append(lid)
            if ln in S.PTRS: o = d.index(b'\x00', o) + 1
            if hp in S.PTRS:
                ab = o; o += cnt * S.ALIAS
                for k in range(cnt):
                    a = ab + k * S.ALIAS
                    aliases.append((u32(a + 0), u32(a + 16)))
                    for po in (a + 0, a + 8, a + 12, a + 20):
                        if u32(po) in S.PTRS:
                            o = d.index(b'\x00', o) + 1
    if ai_p in S.PTRS:
        idx = d[o:o + ac * 4]; o += ac * 4
    return aliases, idx, o, listids

gen_al, gen_idx, gen_end, gen_lids = walk(GEN, GB1, '>')
pc_al, _, _, pc_lids = walk(PCZ, 0x5bcc5a6, '<')
print('genuine aliases=%d  pc aliases=%d' % (len(gen_al), len(pc_al)))
assert len(gen_al) == len(pc_al) == 12467, 'alias count mismatch'
# ORDER PROOF: SndAliasList.id is platform-consistent -> matching id sequence proves same order
lid_mism = sum(1 for g, p in zip(gen_lids, pc_lids) if g != p)
print('list-id order check: %d/%d lists mismatched' % (lid_mism, len(gen_lids)))
assert lid_mism == 0, 'list order differs -> positional pairing invalid'
print('ORDER VERIFIED: PC emit order == genuine order (list ids match positionally)')

# MODE bisect: which change flips crash <-> "build problem"?
#   neither  = assetId oracle only (the 2414-frame wild-ptr CRASH build)
#   loaded   = + genuine loadedAssets entryCount/dataSize only
#   checksum = + genuine .sab checksum overlay only
#   both     = both (the "build problem" build)
mode = sys.argv[1] if len(sys.argv) > 1 else 'both'
SC.SNDBANK_ALIAS_ORACLE = list(gen_al)          # assetId/name/aliasIndex always on (the base fix)
SC.SNDBANK_ALIASINDEX_ORACLE = gen_idx
g_ec = struct.unpack_from('>I', GEN, GB1 + 0x1270)[0]
g_ds = struct.unpack_from('>I', GEN, GB1 + 0x1278)[0]
if mode in ('loaded', 'both'):
    SC.SNDBANK_LOADEDASSETS_ORACLE = (g_ec, g_ds)
if mode in ('checksum', 'both'):
    SC.SNDBANK_HEAD_OVERLAY = GEN[GB1:GB1 + S.BODY]
print('MODE=%s | alias oracle on | loadedAssets=%s | checksum=%s'
      % (mode, SC.SNDBANK_LOADEDASSETS_ORACLE is not None, SC.SNDBANK_HEAD_OVERLAY is not None))

# build: genuine everything else + genuine english + our bank(with oracle)
em, gsp, CO = LS.simulate(RC.CO_PATH, policy=RC.GEN_POLICY)
gen_by_root = defaultdict(list)
for (i, nm, root, s, e) in gsp:
    if e > s: gen_by_root[root].append(CO[s:e])
targets = set(gen_by_root) - {'SndBank'}
GEN_ENGLISH = CO[0x45bea9e:0x45c04a5]
_oe = SC.author_english_bank
SC.author_english_bank = lambda m, *a, **k: GEN_ENGLISH

PN.BISECT_LOG = OrderedDict()
PC.author_zone('../PC ff/mp_raid.zone', 'mp_raid', pc_policy=RC.PC_POLICY,
               our_policy=RC.GEN_POLICY, verbose=False)
log = PN.BISECT_LOG; PN.BISECT_LOG = None
by_root = defaultdict(list)
for s, (root, blen) in log.items(): by_root[root].append((s, blen))
BMAP = {}
for root in sorted(targets):
    ours = by_root.get(root, []); gen = gen_by_root.get(root, [])
    if len(ours) == len(gen):
        for (s, _), gg in zip(ours, gen): BMAP[s] = gg
PN.BISECT_MAP = BMAP
zone, info = PC.author_zone('../PC ff/mp_raid.zone', 'mp_raid', pc_policy=RC.PC_POLICY,
                            our_policy=RC.GEN_POLICY, verbose=False)
PN.BISECT_MAP = None; SC.author_english_bank = _oe
SC.SNDBANK_ALIAS_ORACLE = None; SC.SNDBANK_ALIASINDEX_ORACLE = None
SC.SNDBANK_LOADEDASSETS_ORACLE = None; SC.SNDBANK_HEAD_OVERLAY = None
PC.rewalk_zone(zone, 'raid_oracle[%s]' % mode)
open('mp_raid_oracle.zone', 'wb').write(zone)
ffn = 'mp_raid_oracle_%s.ff' % mode
open(ffn, 'wb').write(wiiu_ff.pack(zone, 'mp_raid'))
print('wrote %s (%d bytes)' % (ffn, len(open(ffn, 'rb').read())))
