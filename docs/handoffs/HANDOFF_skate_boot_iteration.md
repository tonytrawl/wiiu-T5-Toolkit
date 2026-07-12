# HANDOFF — mp_skate Wii U boot: iterate + debug loop

Goal: get the no-backbone-authored `mp_skate` fastfile to boot on Cemu (Wii U T6). It now LOADS,
LINKS, and runs into map-init; it crashes on a garbage pointer-field read. This doc gives a new
session everything to (A) debug crashes properly and (B) build/deploy new iterations.

## Progress ladder (what works, where it crashes)
| stage | status |
|---|---|
| fastfile format / decompress / container accepted | ✅ |
| zone link (every asset body loaded into guest RAM) | ✅ |
| into map-init (first world/entity processing) | ✅ (fixed: runtime-map calibration) |
| past block-5 overflow (late pointers e.g. SOUND banks) | ✅ (fixed: block-5 size) |
| map-init pointer-follow | ❌ CRASH: game reads a garbage word `0x0308001f` as a pointer → null deref |

3 distinct bugs found+fixed this session via the dump-calibration loop, each advanced the boot.

## THE BIG IDEA (why this approach works)
The console GfxWorld/structural RUNTIME allocation model ("gfx_skip") is the project's hardest open
item — NOT count-derivable (proven: LOO-CV ±500K over 9 genuine zones), and it must be EXACT (a
pointer off by 4 B = wrong target = crash). BUT a full-memory crash dump of a boot IS the loader's
ground-truth runtime layout, so we MEASURE it instead of deriving it. The layout does NOT depend on
our (possibly-wrong) alias values — only on FOLLOW pointers + the loader's allocator — so measuring
from a crashed boot and baking pointers to match is correct and self-bootstrapping.

## KEY FILES
- `native_linker/produce_container.py` — author the console zone (container + bodies). `author_zone(
  pc_path, map_name, our_policy=None, override_rtmap=<MeasuredRuntimeMap>)`. Sizes block-5 from
  `override_rtmap.max_rt` when calibrated (else the sim's block_size[5]).
- `native_linker/produce_nobackbone.py` — `assemble_zone(...)`, pass-3 runtime pointer bake. Has
  `override_rtmap` param: after building the sim rtmap it swaps in the measured one.
- `native_linker/measured_rtmap.py` — `MeasuredRuntimeMap(simmap_pkl, realmap_pkl)`: `.rt(dom)`
  returns the measured runtime block-5 offset (carry-forward from nearest measured anchor);
  `.max_rt` = max measured runtime END (for block-5 sizing).
- `native_linker/_measure_real.py` — sequential local-window alignment (fast, ~370 assets).
- `native_linker/_measure_fallback.py` — full-buffer unique-needle fallback for misses (→698/837).
- `native_linker/_skate_simmap.pkl` — {assets_end, spans:[(idx,name,root,disk_start,disk_end)],
  rt_keys/rt_vals (sim RuntimeMap)}. Rebuilt by re-authoring (see below).
- `native_linker/_skate_realmap.pkl` — {base, ae, real:{asset_stream_b5_start -> real_rt_b5_start}}.
- `native_linker/mp_skate_calibrated.zone` / `.ff` — the current build.
- `FINDINGS_skate_boot_dump_calibration.md` — the measurement method write-up.
- Source PC zone: `mp_skate_pc.zone` (repo root). GfxWorld emit input: `skate_gfxworld_trackF.bin`.

## GOTCHAS (bit us repeatedly)
- **Use `python` NOT `python3`** for anything touching the GfxWorld emit — `numpy` (in
  `gfxworld_gx2.conv_lightmaps`) is ONLY in `python` here. `python3` silently DROPS GfxWorld (zone
  comes out 77 MB not 99.5 MB). Dump-parsing scripts (no numpy) can use `python3`.
- **Cemu `log.txt` is overwritten every launch** (`AppData/Roaming/Cemu/log.txt`). Read it BEFORE
  relaunching. The persistent record is the crash DUMP.
- **GDB stub** (Cemu Debug menu) = port **1337**, single-connection-per-launch, minimal protocol
  (`?`→`T05…`, no qSupported/vCont); DO NOT disconnect mid-session (it won't re-accept). It froze
  more than it helped — prefer the full dump.
- **Deploy path** the game actually loads: `AppData/Roaming/Cemu/mlc01/usr/title/0005000c/1010cf00/
  content/0010/english/mp_skate.ff` (the aoc/DLC path). The `/e/Wii U Black ops 2/...` copy is NOT
  the active one. NEVER write under `E:\`.
- Re-authoring is NON-deterministic in POINTER VALUES but the LAYOUT (offsets/sizes) is stable, so
  the sim map + measured map stay valid across rebuilds.

## (A) DEBUG A CRASH — full memory dump + analysis
1. **Enable full dumps** (admin cmd, once): `reg add "HKLM\SOFTWARE\Microsoft\Windows\Windows Error
   Reporting\LocalDumps\Cemu.exe" /v DumpType /t REG_DWORD /d 2 /f` and `/v DumpFolder /t
   REG_EXPAND_SZ /d "C:\CemuFullDumps" /f`. Repro → ~3.3 GB `C:\CemuFullDumps\Cemu.exe.<pid>.dmp`.
   (Cemu's own "Crash dump: Full" setting does NOT produce a full-memory dump.)
2. **Parse minidump** (python3 fine): header `MDMP`@0, `(nStreams,dirRVA)`@8, dir = n×(type,size,rva).
   - Exception stream **type 6**: @loc: ThreadId(4),align(4),Code(4),Flags(4),Record(8),
     **ExceptionAddress/IP**(8),NumParams(4),align(4),Info[15]×8. Info[0]=0/1/8=R/W/X, Info[1]=faulting
     addr. `accessed=0x0` (host null) = Cemu's ConvertOffsetToPointer returned null (out-of-block/bad
     alias) and JIT code deref'd it. `accessed=guest_base+0` = a genuine guest-null deref.
   - Memory64List **type 9**: (count(8),baseRVA(8)), then count×(startVA(8),size(8)); i-th range bytes
     at baseRVA+Σ prior sizes. Guest RAM = ranges with base≤VA<base+4 GB. Guest base = log line
     "Init Wii U memory space (base: 0x…)".
   - Crash-thread registers: ThreadList **type 3** = count(4), then MINIDUMP_THREAD(48 B):
     ThreadId(4),Suspend(4),PriorityClass(4),Priority(4),Teb(8),Stack(MEM_DESC 16),ThreadContext(
     LocDesc: size(4),rva(4) @offset 40). x64 CONTEXT: GP regs @CONTEXT+0x78 in order Rax,Rcx,Rdx,Rbx,
     Rsp,Rbp,Rsi,Rdi,R8..R15; RIP @0xF8. (R13 typically = guest_base.) A register holding a small
     (<4 GB) value that decodes as a T6 zone ptr `(v-1)>>29`=block, `&0x1FFFFFFF`=offset is the
     failing alias; if offset ≥ that block's header size → out-of-block → the null.
3. **Measure the real runtime layout** (this is the calibration oracle):
   - Anchor: a unique 40 B needle from the zone's script-string table (block-5 offset ≈ 3108, ~0
     shift). `block5_base = guest(anchor) - anchor_stream_b5`. Restrict search to the zone window
     [block5_base, +~110 MB] inside the (1.3 GB) guest range — searching the whole range is too slow.
   - `runtime_shift(asset) = (guest(needle) - block5_base) - asset_stream_b5`. Measured skate total ≈
     +1.08 MB (distributed, grows through the zone; the sim predicts ~−145 K ⇒ was off ~1.2 MB).
   - Loader REWRITES pointer fields, so needles must come from DATA regions (strings/floats/verts);
     sequential local-window alignment + full-buffer fallback for misses.

## (B) BUILD A NEW ITERATION
```
cd native_linker
# 1. (re)build the sim map (needed if the zone layout changed). python (numpy!). ~3-5 min:
python - <<'PY'
import sys; sys.path.insert(0,'.'); sys.path.insert(0,'../wiiu_ref')
import loader_sim as LS, produce_container as PC, pickle
pcp=LS.derive_pc_policy('../mp_skate_pc.zone',verbose=False)
zone,info=PC.author_zone('../mp_skate_pc.zone','mp_skate',verbose=False,pc_policy=pcp,our_policy=None)
ae=info['assets_end']; out=info['out_assets']; cur=ae; spans=[]
for (i,nm,root,body,why) in out:
    if body is None: continue
    spans.append((i,nm,root,cur,cur+len(body))); cur+=len(body)
om=info['omap']
pickle.dump(dict(assets_end=ae,spans=spans,rt_keys=list(om.rtmap.keys),rt_vals=list(om.rtmap.vals)),
            open('_skate_simmap.pkl','wb'))
open('mp_skate_authored.zone','wb').write(zone)   # the CANONICAL layout the dump must match
PY
# 2. measure real layout from the newest dump (edit the .dmp path in the scripts; python3 ok):
python3 _measure_real.py && python3 _measure_fallback.py     # -> _skate_realmap.pkl (698/837)
# 3. author calibrated zone (python/numpy):
python - <<'PY'
import sys; sys.path.insert(0,'.'); sys.path.insert(0,'../wiiu_ref')
import loader_sim as LS, produce_container as PC, measured_rtmap as MR
ov=MR.MeasuredRuntimeMap('_skate_simmap.pkl','_skate_realmap.pkl')
pcp=LS.derive_pc_policy('../mp_skate_pc.zone',verbose=False)
z,info=PC.author_zone('../mp_skate_pc.zone','mp_skate',verbose=False,pc_policy=pcp,our_policy=None,override_rtmap=ov)
print('stats',ov.stats,'block5',__import__('struct').unpack_from('>8I',z,8)[5],'max_rt',ov.max_rt)
open('mp_skate_calibrated.zone','wb').write(z)
PY
# 4. pack + deploy:
python ../WiiU_FF_Studio/wiiu_ff.py pack mp_skate_calibrated.zone mp_skate mp_skate_calibrated.ff
cp mp_skate_calibrated.ff "C:/Users/Tony - Main Rig/AppData/Roaming/Cemu/mlc01/usr/title/0005000c/1010cf00/content/0010/english/mp_skate.ff"
```
Verify each build: `author_zone` prints `unresolved: 0`; roundtrip (`wiiu_ff.decrypt(ff)==zone`);
block5 ≥ max_rt. Deploy the .ff to the DLC path above (back up the prior one). Also ship the ipak
(`skate_artifact/mp_skate.ipak`) + `Converted_Sound_Banks/skate/*.sabl/.sabs` (content/sound[/loaded]).

## CURRENT CRASH — next debug steps (dump `C:\CemuFullDumps\Cemu.exe.2896.dmp`)
- Signature: `0xC0000005` READ `accessed=0x0`; crash-thread `Rax=0` deref'd, `Rbx=R8=0x0308001f`,
  R9=0x800, R11=0x1000, R13=guest_base, RIP in JIT. IDENTICAL across boot #3 (20596) and #4 (2896)
  ⇒ deterministic, NOT interpolation-related.
- `0x0308001f` decodes block-0 (TEMP) offset 0x0308001e=50.6 MB, block-0 size=4780 ⇒ out-of-block →
  null. The value is NOT in our zone (0 hits) ⇒ the game READ it as a pointer FROM some asset's field
  that holds a garbage/unrelocated word.
- Hypothesis: a MEASURED asset has a MISALIGNED field (wrong console struct size/layout) or an
  UNRELOCATED pointer, so the game reads a data word where it expects a pointer. This is a
  converter/layout bug, independent of the runtime map.
- To localize: (1) walk the crash thread's stack (Rsp=0x1d6046bbf30 region in the dump's memory) for
  a guest pointer into the zone buffer = the asset being processed; (2) or find in the LOADED guest
  buffer where the bytes `03 08 00 1f` sit (the source field) and map that guest offset back to an
  asset+field via the measured layout; (3) suspect the map-init consumers first: clipMap_t,
  GameWorldMp, MapEnts, ComWorld (all measured, all processed early in map-init).

## GUARD DISCIPLINE (don't regress the map-zone converters)
Any change to shared walker/converter/struct files must keep the map-zone guards green:
`cd native_linker && python raid_oracle_control.py anchors` (ANCHOR SUITE PASS) and
`python raid_oracle_control.py` (GATE PASS, unresolved 0). The container/measured-rtmap files are
skate-only and don't touch those. Never write under `E:\`.
