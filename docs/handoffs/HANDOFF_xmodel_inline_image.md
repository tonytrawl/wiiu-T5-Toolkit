# HANDOFF — fix XModel inline-material image emit (dropped skybox texture)

Date: 2026-07-11. Work order to complete the XModel inline-material image conversion. Read
`HANDOFF_raid_control_status.md` first for the full context and the proven build/deploy/test
harness. This is the actionable fix.

## The bug in one line
Our XModel converter emits inline-material images as **streamed/stubbed** (pixels dropped)
where genuine ships them **inline** (pixels in the zone). Worst case: `skybox_mp_raid`
emits 15,380 B vs genuine 1,588,228 B — the whole ~1.5 MB skybox texture is gone. 36/440
raid XModels under-emit 3.68 MB total this way. The skybox draws every frame during the load
screen → dangling texture → GPU wild-pointer crash (raid dump 25192; likely skate too).

## Where the drop happens (code path, verified this session)
- `native_linker/xmodel_pc.py::parse_xmodel_pc` line ~132-139: for each FOLLOW
  `materialHandle`, it calls `MC.convert_material(d, c[0])` → the inline material is converted
  in place. This is the entry to the inline-material (and thus inline-image) conversion.
- `native_linker/material_convert.py` — the material/image emit. Key machinery:
  - `pc_image_span(d, off)` — reads ONE inline PC GfxImage. Note (verbatim from source):
    "texture.loadDef = a GfxImageLoadDef 12-B header (levelCount/flags/format/resourceSize) +
    resourceSize pixel bytes (**streamed images have resourceSize=0 → bare 12-B tail;
    inline-pixel images carry real pixels**)."
  - Streamed-body style: "MAP images use (1,1) [streaming]; frontend/menu images use (0,2)
    [inline]" (delayLoadPixels, streaming flags). Hooks: `IMAGE_STREAM_RESOLVER`,
    `IMAGE_STREAM_STYLE`, `IMAGE_STREAM_MANIFEST`.
- **Hypothesis to confirm first:** the converter applies the "map image ⇒ streamed
  (resourceSize=0)" rule uniformly, so it drops the pixels for images that genuine actually
  ships INLINE (skybox + ~35 others). Genuine keeps skybox pixels inline; ours streams it.

## STEP 0 — confirm the hypothesis (ghost-guard before coding)
On `skybox_mp_raid` specifically, compare our emitted inline image vs genuine:
1. Get the paired bodies (use the harness pattern — assemble `out_assets` for ours, genuine
   via `LS.simulate(RC.CO_PATH, RC.GEN_POLICY)`; pair by name; DO NOT use two mismatched
   walks — see the ghost-trap note in the status handoff).
2. In the genuine `skybox_mp_raid` body: walk to the materialHandle → inline Material →
   inline GfxImage; read its `GfxImageLoadDef.resourceSize` and confirm it's ~1.5 MB
   (inline pixels present). Console GfxImage layout: `wiiu_ref/gfximage_probe.py` docstring
   (streaming flag @+170, `pixels` ptr @+176 FOLLOW iff streaming==0, baseSize @+160).
3. In OUR body at the same material: confirm `resourceSize==0` / streaming flag set / pixels
   absent. If so, hypothesis confirmed: we stream what should be inline.
4. Also check: does the PC zone (`PC ff/mp_raid.zone`) actually CARRY the skybox pixels
   inline? (`pc_image_span` / `wiiu_ref/pc_image_enum.py`). If PC has them, we can emit them;
   if PC also streams them, the pixels must come from the ipak (`ipak_stream` /
   `IMAGE_STREAM_RESOLVER`) — different fix.

## STEP 0 RESULT (2026-07-11, CONFIRMED — ghost-free vs genuine)
Walked `skybox_mp_raid`'s XModel → inline material → inline GfxImage in both zones:

| field | genuine | ours |
|---|---|---|
| size | 512×512 | 1×1 |
| baseSize | 1,572,864 (1.5 MB) | 0 |
| streaming | 0 (inline) | 1 (streamed) |
| pixels | FOLLOW (present) | null (00000000) |

**Exact code + mechanism** (`material_convert.py::convert_image`, ~line 142):
- Path 1 (`if pixels:`, line 177) → `IS.build_inline_body(meta, pixels)` — inline, streaming=0. CORRECT.
- Path 2 (streamed + `IMAGE_SOURCE` resolves, line 183-195) → `build_streamed_body` — streaming=1, pixels via ipak.
- Path 3 (streamed + `IMAGE_SOURCE` None/miss, lines 197-206) → **the 1×1 stub** (`pack_into('>HHH',body,164,1,1,1)`, `body[171]=1`). **This is what the skybox hits.**

**Root of the starvation:** `produce_container.author_zone` deliberately leaves
`material_convert.IMAGE_SOURCE` **unset** — comment (line ~118): "NOT material_convert.IMAGE_SOURCE,
whose raw blobs would corrupt the materialMemory inline-image path (latent _console_material_pieces
overrun)." So EVERY streamed inline-material image in an XModel falls to path 3 (1×1 stub) → crash.

**Pixels ARE available:** `wiiu_ref/ipak_stream.DEFAULT_PC_IPAKS` =
`E:\pluto_t6_full_game\zone\all\base.ipak` + `mp.ipak` (both exist; read-only, never write E:).
So a properly-scoped `IMAGE_SOURCE` over these can resolve the skybox pixels.

**Design tension the fix MUST resolve (the crux):**
1. `IMAGE_SOURCE` is needed for XModel-inline-material streamed images (skybox) but is unsafe when
   applied to the GfxWorld materialMemory path (`_console_material_pieces` overrun). → Either SCOPE
   `IMAGE_SOURCE` per call-site (XModel-inline yes, GfxWorld-materialMemory keeps its dedicated hook),
   OR fix the `_console_material_pieces` overrun so `IMAGE_SOURCE` is universally safe.
2. Genuine ships the skybox **INLINE** (streaming=0), but path 2 builds a **STREAMED** body. To match
   genuine, the fix likely needs a new branch: streamed-PC-image whose console form is inline →
   resolve PC pixels via IMAGE_SOURCE, then `build_inline_body(meta, resolved_pixels)` (NOT
   build_streamed_body). Which images are inline-on-console is oracle-knowable on raid (the 36
   droppers); skate has no oracle, so validate the class on raid first.

## STEP 1 — IMPLEMENTED (A1), but needs a SCOPE discriminator (2026-07-11/12)
A1 landed and the mechanism WORKS + is safe:
- New scoped resolver `material_convert.XMODEL_IMAGE_SOURCE` + flag `XMODEL_INLINE_ACTIVE`,
  set ONLY around the inline-material convert in `xmodel_convert.convert_xmodel_materialhandles`
  (NOT the walker `xmodel_pc.parse_xmodel_pc` — that was my first wrong spot; reverted).
- `convert_image` gains an `elif XMODEL_INLINE_ACTIVE and XMODEL_IMAGE_SOURCE resolves (mips+gx2_format)`
  branch → `build_inline_body` (inline, streaming=0) instead of the 1x1 stub.
- Wired in `produce_container.author_zone`: `XMODEL_IMAGE_SOURCE = _make_pc_image_source(DEFAULT_PC_IPAKS[+image_ipak])`.
- RESULT: skybox_mp_raid 15380 → 277524 (real inline pixels, no more 1x1 null stub).
- GUARDS GREEN: `raid_oracle_control.py` GATE PASS, **unresolved-omap 0** (A1 scoping held —
  GfxWorld materialMemory untouched, none of the 16,734 unres a global source causes).

**PROBLEM — over-inline:** the zone ballooned to 209 MB (was 95, genuine 86). The branch
inlines EVERY XModel-inline streamed image that resolves, but genuine inlines only a small
RESIDENT subset (~3.68 MB, the 36 droppers) and STREAMS the rest. Need a stream-vs-inline
DISCRIMINATOR so only the genuinely-resident class inlines. A 209 MB zone likely exceeds the
console block-5 allocation → may fail to load; must fix scope before trusting a boot.

**DISCRIMINATOR FOUND (2026-07-12): it is IPAK MEMBERSHIP, not mapType/semantic.** Tested on
genuine raid — the same (mapType,semantic) combos appear in BOTH inline and streamed sets
((3,2): 17 inline vs 251 stream; (3,5): 5 vs 195; (3,8): 2 vs 96), so type is NOT a clean
signal. Genuine INLINES an image (resident) when it is NOT in the streaming ipak, and STREAMS
it when it is. So the correct fix: in the XModel-inline branch, emit inline ONLY when the
image's name_hash is absent from the map's streaming ipak; otherwise emit a proper STREAMED
body (build_streamed_body), NOT the 1x1 stub and NOT inline.

REMAINING WORK to finish A1 correctly:
1. Thread the streaming-ipak name_hash SET into convert_image (e.g. module global
   `MC.RESIDENT_IMAGE_TEST = callable(hash)->bool`; produce_container builds it from the map's
   streaming ipak(s): raid=retail base/dlc (console ipaks, name_hash is platform-independent),
   skate=mp_skate.ipak+dlc1). Inline iff the test says resident.
2. For streamed XModel-inline images that currently stub: route to build_streamed_body (+
   COLLECT_ENTRIES so pixels land in the output ipak) instead of the 1x1 stub. That fixes the
   null WITHOUT ballooning the zone.
3. Cubemap: skybox is 6-face (mapType 5); build_inline_body is 2D. Add cubemap tiling for the
   inline path (or confirm 2D-single-face still clears the crash on the raid boot test).
Verify: after gating, zone should return to ~86-90 MB (near genuine), unresolved 0, GATE PASS,
skybox_mp_raid still ~1.5 MB inline. Then boot-test raid.

CURRENT DEPLOYED (as of this session): the OVER-INLINED 209 MB raid build is in the update
partition — likely too big to load; treat any boot of it as only a crude "did the null clear"
signal, not the real form. Re-deploy genuine or the gated build before a clean test.

## STEP 1 — COMPLETE (2026-07-12, discriminator landed + measured)
The A1 discriminator is implemented and the balloon is fixed. **raid zone 215 MB → 95.3 MB**
(genuine 86 MB), GATE PASS, ANCHOR SUITE PASS, unresolved-omap 0, asset array 0 diffs,
REWALK EOF-EXACT.

**What was wrong with the first cut:** I defaulted the streaming-ipak test to
`wiiu_ref/mp_raid_english.ipak` — that is the localized English audio/menu pak (only 76 image
hashes), NOT the texture streaming pak. So nearly everything tested "resident" and it still
over-inlined (215 MB).

**Measured the real signal (instrumented `convert_image` over a full raid assemble):**
- 2670 XModel-inline images processed; **2643 resolve from base+mp.ipak = 360 MB if all
  inlined**. Genuine STREAMS exactly those. Only 27 are NOT in base/mp (~0 B).
- So the streaming-ipak set = the map's **PC source ipaks (base+mp[+image_ipak])**, and
  name_hash is platform-independent (verified: 76 console↔PC hash intersection).
- skybox_mp_raid never reaches this branch — it goes through branch 1 (`if pixels:`, PC-inline
  pixels), so it inlines correctly regardless of the discriminator.
- Genuine's 3.93 MB of inline images are small shared **default/system** textures
  (`$identitynormalmap`, `global_white_16x16`, `com_black2` …). Their harvested `texhash`
  repeats (deduped shared defaults, not per-image name_hashes) and they are emitted by the
  **unchanged** top-level / GfxWorld-materialMemory paths — OUTSIDE the `XMODEL_INLINE_ACTIVE`
  scope — so the discriminator does not touch them.

**The fix (landed):**
- `material_convert.RESIDENT_IMAGE_TEST = callable(name_hash)->bool` (True == resident ==
  inline). In the `XMODEL_INLINE_ACTIVE` branch: inline iff resident; else emit a real
  `build_streamed_body` (+ `COLLECT_ENTRIES`), NOT the 1×1 stub and NOT inline.
- `produce_container.author_zone(..., stream_ipak=None)`: builds `RESIDENT_IMAGE_TEST` from
  `_make_resident_test(_pc_src)` where `_pc_src = base+mp[+image_ipak]` — resident iff the
  hash is ABSENT from that set. (`stream_ipak` param overrides per call site if needed.)
- Anything the A1 branch catches resolved FROM base/mp → in the streaming ipak → streams.

**Residual (separate, pre-existing — NOT the balloon, NOT introduced here):** 95.3 vs genuine
86 MB (~9 MB) is non-image converter overhead. The dropper classifier (`assemble_zone`
directly) still shows the old 15380 skybox number because it BYPASSES the produce_container
wiring (never sets XMODEL_IMAGE_SOURCE/RESIDENT_IMAGE_TEST) — it is not a valid check of the
wired path; measure the authored zone instead. **NEXT = boot-test the 95.3 MB
mp_raid_authored.zone** (was previously blocked on the oversized 209 MB build).

## STEP 1 (original plan) — the fix
Make the inline-material image emit **preserve inline pixels when genuine does**:
- Decide inline-vs-streamed per image the way genuine does, not by a blanket map-image rule.
  The genuine oracle tells you which images are inline (resourceSize>0). For an XModel
  inline-material image that genuine ships inline, emit the real pixels (from the PC inline
  image via `pc_image_span`, or from the ipak via the stream resolver if PC streams them).
- Keep the console GfxImage body layout correct (gfximage_probe: 328-B body; streaming=0 →
  `pixels` FOLLOW with baseSize bytes after the name; format/dims/mipLevelOffset fields).
- Watch the pointer bake: the emitted pixel blob adds bytes → block-5 size and all downstream
  runtime addresses must stay correct (the assemble pass-3 handles this if the body is emitted
  through the normal path, but verify — this is the +9 MB layout that must reconcile).

## STEP 2 — verify against ground truth (cheap, decisive loop)
1. Rebuild: `cd native_linker && python produce_container.py` (raid_dryrun; GATE PASS,
   unresolved 0). Confirm `skybox_mp_raid` emitted size ≈ genuine 1,588,228 B.
2. Re-run the dropper classifier (below) — the 36 droppers / −3.68 MB should collapse toward 0
   (skinned ×3 stay; that's a separate known-incomplete converter, out of scope here).
3. Pack + deploy to the update partition (see status handoff) and **boot raid**.
   - Loads/renders the skybox → fix confirmed on ground truth.
   - Still crashes → get the new dump; compare fault vs 25192; iterate.
4. Then rebuild + deploy **skate** and re-test (skate deploy path =
   `mlc01/.../0005000c/1010cf00/content/0010/english/mp_skate.ff`; USE `python` not `python3`
   for skate — numpy/GfxWorld emit).

## The dropper classifier (paste-run; ghost-free, pairs emitted vs genuine by name)
```
cd native_linker && python3 - <<'PY'
import sys,struct; sys.path.insert(0,'.'); sys.path.insert(0,'../wiiu_ref')
import loader_sim as LS, raid_oracle_control as RC, produce_nobackbone as PN
from collections import defaultdict
em,gsp,CO=LS.simulate(RC.CO_PATH,policy=RC.GEN_POLICY)
gen=defaultdict(list)
for (i,nm,root,s,e) in gsp:
    if e>s: gen[nm].append(CO[s:e])
stat,out,omap=PN.assemble_zone('../PC ff/mp_raid.zone',verbose=False,pc_policy=RC.PC_POLICY,our_policy=RC.GEN_POLICY)
occ=defaultdict(int); rows=[]
for (i,nm,root,body,why) in out:
    if root!='XModel' or body is None: continue
    k=occ[nm]; occ[nm]+=1; gl=gen.get(nm)
    if not gl or k>=len(gl): continue
    rows.append((len(body)-len(gl[k]),nm,len(body),len(gl[k])))
big=[r for r in rows if abs(r[0])>1000]
print('divergent >1KB: %d/%d, under-emit total %d B'%(len(big),len(rows),sum(r[0] for r in rows if r[0]<0)))
for d,nm,lo,lg in sorted(rows)[:15]: print('  %+9d %-22s ours=%d gen=%d'%(d,nm[:22],lo,lg))
PY
```
Baseline today: 36 divergent, −3,681,674 B, top dropper `skybox_mp_raid` (15,380 vs 1,588,228).
The name field reads generic "XMODEL" in some walks — the real model name comes from the body
name string (the classifier used to id skybox parses it from the body).

## Scope / non-goals
- **In scope:** XModel inline-material INLINE-pixel images (skybox + the ~33 non-skinned
  droppers).
- **Out of scope here:** the 3 skinned models (−10K..−76K) — separate `xmodel_convert` skinned
  GX2 skin-stream converter, a known-incomplete item ([[trackC-xmodel-converter]]).
- Do not touch shared walker/converter files without keeping the raid guards green:
  `python raid_oracle_control.py` (GATE PASS, unresolved 0) and `... anchors`. Never write E:\.
