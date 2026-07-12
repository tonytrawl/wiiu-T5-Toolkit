"""Build mp_raid_authored.ff transplanting a chosen SET of genuine XModel bodies.
  python _build_transplant.py skybox   -> skybox only (alias-clean, safe)
  python _build_transplant.py clean    -> the ~206-prefix cluster (image-only divergence)
  python _build_transplant.py all       -> all 36 under-emitters (may inject bad aliases)
"""
import sys, struct
sys.path.insert(0, '.'); sys.path.insert(0, '../wiiu_ref')
import loader_sim as LS, raid_oracle_control as RC
import xmodel_convert as XC, produce_nobackbone as PN, produce_container as PC

mode = sys.argv[1] if len(sys.argv) > 1 else 'skybox'

em, gsp, CO = LS.simulate(RC.CO_PATH, policy=RC.GEN_POLICY)
gen = [CO[s:e] for (i, nm, root, s, e) in gsp if root == 'XModel' and e > s]

orig = XC.convert_xmodel; calls = []
def cap(pc, off, reloc=XC._default_reloc, memusage=None, marks=None):
    b, n = orig(pc, off, reloc, memusage, marks); calls.append((off, b)); return b, n
XC.convert_xmodel = cap
_, out, _ = PN.assemble_zone('../PC ff/mp_raid.zone', verbose=False,
                             pc_policy=RC.PC_POLICY, our_policy=RC.GEN_POLICY)
outx = [b for (i, nm, root, b, why) in out if root == 'XModel' and b is not None]
final = calls[-len(outx):]

xplant = {}
for (off, b), g in zip(final, gen):
    sf = len(g) - len(b)
    if sf <= 1000:
        continue
    n = min(len(b), len(g)); pref = next((i for i in range(n) if b[i] != g[i]), n)
    is_skybox = (off == 0xf3477)
    clean = pref >= 200            # header+material identical -> alias-light, image-only divergence
    take = (mode == 'all' or (mode == 'clean' and clean) or (mode == 'skybox' and is_skybox))
    if take:
        xplant[off] = g
print('mode=%s  transplanting %d models' % (mode, len(xplant)))

def wrapped(pc, off, reloc=XC._default_reloc, memusage=None, marks=None):
    body, nxt = orig(pc, off, reloc, memusage, marks)
    g = xplant.get(off)
    if g is not None:
        if marks is not None:
            marks.clear()
        return g, nxt
    return body, nxt
XC.convert_xmodel = wrapped
zone, info = PC.raid_dryrun()
import wiiu_ff
# pack
open('mp_raid_authored.zone', 'wb').write(zone)
import subprocess
print('packing...')
