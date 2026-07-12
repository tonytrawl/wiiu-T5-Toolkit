"""Transplant genuine inline-image XModel bodies for EXACTLY the 36 under-emitting
(dropped-texture) models, paired via classifier occurrence order. Monkeypatch only."""
import sys, struct
sys.path.insert(0, '.'); sys.path.insert(0, '../wiiu_ref')
from collections import defaultdict
import loader_sim as LS, raid_oracle_control as RC
import xmodel_convert as XC, produce_nobackbone as PN, produce_container as PC

em, gsp, CO = LS.simulate(RC.CO_PATH, policy=RC.GEN_POLICY)
gen = [CO[s:e] for (i, nm, root, s, e) in gsp if root == 'XModel' and e > s]

# ---- map: pair final-pass offsets with genuine bodies (classifier order) ----
orig = XC.convert_xmodel
calls = []
def cap(pc, off, reloc=XC._default_reloc, memusage=None, marks=None):
    b, n = orig(pc, off, reloc, memusage, marks); calls.append((off, b)); return b, n
XC.convert_xmodel = cap
stat, out, omap = PN.assemble_zone('../PC ff/mp_raid.zone', verbose=False,
                                   pc_policy=RC.PC_POLICY, our_policy=RC.GEN_POLICY)
outx = [body for (i, nm, root, body, why) in out if root == 'XModel' and body is not None]
finalcalls = calls[-len(outx):]
xplant = {}
for (off, b), g in zip(finalcalls, gen):
    if len(g) - len(b) > 1000:
        xplant[off] = g
print('transplant offsets:', len(xplant),
      'bytes added: %.2f MB' % ((sum(len(g) for g in xplant.values())
        - sum(len(b) for (off, b), g in zip(finalcalls, gen) if off in xplant)) / 1e6))

# ---- build with transplant keyed purely by (stable) PC offset ----
st = {'n': 0}
def wrapped(pc, off, reloc=XC._default_reloc, memusage=None, marks=None):
    body, nxt = orig(pc, off, reloc, memusage, marks)
    g = xplant.get(off)
    if g is not None:
        st['n'] += 1
        if marks is not None:
            marks.clear()
        return g, nxt
    return body, nxt
XC.convert_xmodel = wrapped
zone, info = PC.raid_dryrun()
print('\n=== TRANSPLANT %d models ===' % st['n'])
print('final zone %.3f MB  genuine %.3f MB  delta %+.3f MB'
      % (len(zone)/1e6, len(CO)/1e6, (len(zone)-len(CO))/1e6))
