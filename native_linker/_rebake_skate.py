"""Rebake mp_skate with the field-aware SndBank fix + the (still-valid, size-preserving)
measured runtime map, then pack to mp_skate_measured.ff. Mirrors HANDOFF step 3."""
import sys
sys.path.insert(0, '.'); sys.path.insert(0, '../wiiu_ref'); sys.path.insert(0, '../WiiU_FF_Studio')
import loader_sim as LS
import produce_container as PC
from measured_rtmap import MeasuredRuntimeMap
import wiiu_ff

pcp = LS.derive_pc_policy('../mp_skate_pc.zone', verbose=False)
rtm = MeasuredRuntimeMap('_skate_simmap.pkl', '_skate_realmap.pkl')
print('measured rtmap: %d spans, max_rt=%d' % (len(rtm.spans), rtm.max_rt))

zone, info = PC.author_zone('../mp_skate_pc.zone', 'mp_skate',
                            pc_policy=pcp, our_policy=None,
                            override_rtmap=rtm,
                            image_ipak='../skate_artifact/mp_skate.ipak')
open('mp_skate_measured.zone', 'wb').write(zone)
print('wrote mp_skate_measured.zone (%d bytes)' % len(zone))

ff = wiiu_ff.pack(zone, 'mp_skate')
open('mp_skate_measured.ff', 'wb').write(ff)
print('wrote mp_skate_measured.ff (%d bytes)' % len(ff))
