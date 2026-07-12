# HANDOFF — Full unlink→relink of patch_mp / patch_zm (TU) as an ISOLATED side project

2026-07-11. Goal: make the update-partition (TU) `patch_mp.ff` / `patch_zm.ff` mapsTable EDIT work
end-to-end so **DLC map rows can be ADDED** (additive, growing the zone), by fully unlinking and
re-linking the zone — WITHOUT modifying the base linker. Feed notable findings back to the MAIN
session so anything useful lands in the PC→Wii U map pipeline.

--------------------------------------------------------------------------------------------------
## 0. ISOLATION RULES (read first)
--------------------------------------------------------------------------------------------------
* **Base linker = READ-ONLY.** Do NOT edit: `wiiu_ref/*`, `native_linker/body_relayout.py`,
  `native_linker/zone_stream.py`, `native_linker/struct_layout.py`, `wiiu_ref/walker.py`,
  `WiiU_FF_Studio/wiiu_ff.py`, and the asset probes (`wiiu_ref/*_probe.py`). Import them read-only,
  exactly as `dlc loading/native/patch_relink.py` already does.
* **All new code lives in the side dir** `dlc loading/native/` (already the home of `patch_relink.py`)
  or a new subdir `dlc loading/native/fullrelink/`. If you need to change base behaviour, SUBCLASS or
  MONKEYPATCH from the side project (see `/tmp/editT.py` in this session for the monkeypatch pattern),
  never edit base files.
* **One deliberate exception, already landed & keep:** the *general walker/delimiter* fixes this
  session (section 3) are correct, verified byte-identical, non-regressive, and directly help the
  pipeline. Treat them as shared infrastructure. If policy requires a pristine base, fork them into
  the side project instead, but do not lose them.

--------------------------------------------------------------------------------------------------
## 1. CURRENT STATE — what works, what doesn't
--------------------------------------------------------------------------------------------------
DEPLOY PIPELINE IS PROVEN. The zone LOADS and LINKS on real hardware (Cemu, update partition).
- Deploy path: `mlc01/usr/title/0005000e/1010cf00/content/english/patch_{mp,zm}.ff` (+ `.stockbak`).
- Sig-bypass RPL patch is active and required (see memory [[wiiu-sig-bypass]]).
- `python` (not python3). Run tools from `native_linker/` (struct_layout reads ../tools/ref_oat/...).

WORKING: a SIZE-PRESERVING mapsTable edit (swap stock rows for DLC rows, NO growth → NO tail shift).
  `dlc loading/native/_swap/upd_patch_mp.ff` boots, maps load, game is stable. See section 5.

BLOCKED: the ADDITIVE edit (grow mapsTable → shift tail → relink). Boots + links ~1341 assets then
  a graceful game `OSFatal` during patch_mp link:
    "Could not load default asset 'void' for asset type 'xmodel'. Tried to load asset 'fx_pistol_shell'."
  Full analysis in section 4. This is the ONE remaining blocker for additive maps.

--------------------------------------------------------------------------------------------------
## 2. THE 4 FORMAT/RELINK FIXES that got the zone to LOAD (all in `patch_relink.py::cmd_edit`)
--------------------------------------------------------------------------------------------------
Each masked the next; the isolation ladder (section 4) cracked them in order. ALL are required.
1. **Header size** — after growth, bump XFileHeader `size@0` AND `blockSize[5]` by +delta
   (stale sizes truncate the decompress → corrupt zone → crash). `c['size']+=delta;
   c['block_sizes'][BLOCK_VIRTUAL]+=delta`.
2. **Fastfile internal NAME seeds the Salsa20 keystream** (`wiiu_ff.HashChain`). Pack with the
   ORIGINAL header name (`patch_mp`), NOT the local filename (`upd_patch_mp`), else the console
   decrypts to garbage. Helper `orig_ff_name()` reads it via `wiiu_ff.parse_header`.
3. **Structural pointer relink = THRESHOLD, not omap.** `ReEmitter.remap_ptr` for known pointer
   fields must do: block-5 alias whose offset >= insertion point → +delta. omap alone MISSES targets
   that aren't registered asset starts (e.g. StringTable cells alias a shared string POOL interior).
   Verbatim assets keep the conservative omap scan (`remap_ptr_omap`). `shift_from = con_body_end-64`.
4. **XAssetList headerPtr relink.** The asset array `{u32 type, u32 headerPtr}` @ `r.assets_off` is
   copied verbatim in the container header; most headerPtrs are FOLLOW but a few are real block-5
   offsets (aliased/shared headers — mp has 6, 4 past the mapstable). Bump those by +delta after
   building `edited`. (mp relinks 4, zm 0.)

Also required for the walk to reach EOF (general delimiters, section 3).

--------------------------------------------------------------------------------------------------
## 3. GENERAL WALKER/DELIMITER FIXES (landed in base — KEEP; pipeline-relevant)
--------------------------------------------------------------------------------------------------
These made the console ReEmitter walk both TU zones to EOF byte-identical (no-edit round-trip PASS).
They describe genuine Wii U console asset layout → **directly useful to the PC→Wii U pipeline** which
must EMIT these same structures. Report each to the main session.
- `body_relayout._fonticon_end` — FontIcon: 20-B body + name + 24-B entry[] (each: FontIconName
  {string*,hash} + inline Material if handle FOLLOW) + **20-B FontIconAlias** (Wii U, not PC's 8).
- `walker.ASSET_ROOT` += `ATTACHMENT`→WeaponAttachment, `ATTACHMENT_UNIQUE`→WeaponAttachmentUnique.
- `body_relayout._sndbank_end` = `sndbank_probe.parse_sndbank` (generic walker under-read it ~660KB).
- `body_relayout._spt_end` — ScriptParseTree {name*,len,buffer*}=12-B + name + len-byte GSC buffer+1.
- `body_relayout._menulist_end` rewrite — menuCount==0 → 12-B + name; menuCount>0 → scan next
  MenuList(".txt") or StringTable(".csv") header (independent checks; StringTable +8=rows≠FOLLOW).
- `body_relayout._weapon_end` — bounds the single inline-weapDef WeaponVariantDef via its trailing
  WeaponAttachment + rumble RAWFILE cluster (genuine Wii U WeaponDef field layout still unreversed).

--------------------------------------------------------------------------------------------------
## 4. THE BLOCKER — additive shift crashes at `fx_pistol_shell` (deep analysis)
--------------------------------------------------------------------------------------------------
ISOLATION LADDER (each removed one variable; all boot from the UPDATE partition):
  _rt        byte-identical repack, no change              → LOADS  (proves deploy/name/pack OK)
  _sizetest  +delta padding at EOF, NO tail shift          → LOADS  (proves growth OK)
  _citest    same-size mapstable, cellIndex reordered      → LOADS  (proves in-place edits OK)
  _swap      same-size row swap (section 5)                → LOADS  (working deliverable)
  _edit      grow mapstable + shift + relink (all 4 fixes) → CRASH @ fx_pistol_shell
  _edit2     genuine-aliased mapstable format + shift      → CRASH @ (same)  → NOT the format
  _edit3     grow with clones of a WORKING base map        → CRASH  → NOT the new/DLC content
  _editT     threshold relink on VERBATIM assets too       → CRASH EARLIER → blind threshold corrupts
                                                                data (88,509 false-positive words)
CONCLUSION: the **tail SHIFT** is the trigger. Not format, not content, not the 4 fixes.

FACTS about the crash asset (mp):
- `fx_pistol_shell` = xmodel asset #1342 @12,401,764 (261 B), an EMPTY stub (body = `ffffffff`
  then all zeros; no LODs/materials/aliases). Name `,fx_pistol_shell` @12,402,009.
- In `_edit` it is **byte-identical, just shifted** (0 changed bytes) and has NO pointers to relink.
- `_swap` (no shift) loads the SAME empty xmodel fine.
- The failure is the game's own graceful `OSFatal` (asset-resolution logic), NOT a Cemu segfault —
  so there is NO memory-corruption dump; the loader logically failed to resolve a dependency.
- There is NO `void` xmodel in patch_mp — it's a preloaded default (code_post_gfx/common). The
  message = "xmodel fx_pistol_shell failed to load; couldn't substitute the default `void`".

WHY IT'S HARD: the crashing asset is intact, pointers relinked, no detectable stream desync, yet it
fails ONLY when shifted. This is a genuine Wii U loader **position-dependency the reference tooling
doesn't capture** — same class as the known menuDef (424≠392) / XAnimParts (104≠92) divergences.
It cannot be isolated from file bytes because the bytes are correct.

LEADING HYPOTHESIS (unconfirmed): a VERBATIM asset (XModel/FX/XAnim/Material/techset/SndBank) has an
internal alias to a shared-data INTERIOR (not an asset start), which the conservative omap relink
misses → stale after +delta → the loader can't resolve a dependency during link. Evidence: the
mapsTable cells themselves alias INTO the `void` XANIMPARTS interior (@9,220,620 = xanim+8326), a
proven interior-target pattern. But blind threshold (which would fix interiors) corrupts data → not
viable; and I could not pin the specific stale pointer because the crashing xmodel has none.

--------------------------------------------------------------------------------------------------
## 5. THE WORKING SWAP (size-preserving; fallback / partial deliverable)
--------------------------------------------------------------------------------------------------
Script pattern in this session: overwrite a stock map's col0 name IN PLACE with a same-length DLC
name, update the cell hash (`djb2ci`), re-sort cellIndex (genuine comparator: signed `hash-hash`
overflow, tie by `a%cols - b%cols`; std::sort in `ObjLoading/StringTable/StringTableLoader.h`), pack
with `orig_ff_name`. Same size → no shift → no relink → LOADS.
- 7 mp maps fit by exact name-length match (concert/magma/vertigo/castaway/paintball/takeoff/studio);
  zm has NO length matches. dig/pod/uplink/bridge/frostbite don't fit.
- LIMITATION found on HW: only col0 (internal name) was swapped → the map LOADS but the menu shows the
  STOCK name (display name is **col03** = `MPUI_*` loc key) and a CHECKERBOARD preview (image is keyed
  off col0 → the DLC map's loadscreen material isn't installed). mapsTable schema (17 cols):
  col00 internal name | col03 display-name loc key | col04 map-select material | col05 map index |
  col06 desc loc key | col07 compass image | col11 DLC pack index | col13/15 faction2 name/image.
- So DISPLAY needs the DLC ASSET PORT regardless of path: the map `.ff`, the loc strings
  (`MPUI_CONCERT`=…; NOT present in `en_patch_loc_mp.ff` — checked), and the loadscreen image material.

--------------------------------------------------------------------------------------------------
## 6. TWO PATHS FOR THE FULL UNLINK→RELINK (pick per effort)
--------------------------------------------------------------------------------------------------
PATH A — delta-patch (current): keep verbatim assets, shift tail +delta, relink pointers.
  Remaining work = **precise verbatim-asset pointer relink**. The probes
  (`xmodel_probe.parse_xmodel`, `fx_probe.parse_fx`, `xanimparts_probe.parse_xanim`,
  `shader_probe.parse_techset`, `destructibledef_probe`, `sndbank_probe.parse_sndbank`,
  `xmodel_probe.consume_material/consume_image`) already WALK the structure and read every pointer
  field. Add (in the SIDE PROJECT, via subclass/wrapper — do not edit base) a mode that yields each
  pointer-field byte offset. Then relink exactly those (threshold +delta), leaving data untouched.
  This is the false-positive-free version of `_editT`. Validate: rebuild `_edit`, re-walk to EOF,
  confirm the crashing xmodel's dependency chain resolves, HW test.
PATH B — full from-scratch re-emit (cleaner, larger): unlink the whole zone into an asset graph and
  RE-EMIT every asset via `zone_stream.ZoneWriter` + `loader_sim` (memory [[trackG-assemble-pointer-model]]
  reproduces genuine alias values), computing ALL pointers by construction. Sidesteps delta-patching
  but STILL needs structural emit (or verbatim+position-tracked relink) for every asset type — same
  core requirement as Path A. This is the same machinery the PC→Wii U pipeline needs → do it here and
  it lands there too.

GUEST-DEBUG (to crack the position-dependency before big work): the crash is a graceful `OSFatal`, so
set a Cemu debugger breakpoint / add logging at the asset-resolution site, or bisect: build edits that
shift by increasing deltas and find the threshold where it breaks; or shift only PART of the tail
(grow a benign already-relinkable asset, NOT a parsed config — `_rawgrow` was invalid because it
padded `_gametypes.txt` with nulls and corrupted a parsed file). Compare the guest asset-registry /
default-asset table between `_swap` (works) and `_edit` (fails) at the OSFatal point.

--------------------------------------------------------------------------------------------------
## 7. REPORT-BACK TO MAIN SESSION (PC→Wii U map pipeline)
--------------------------------------------------------------------------------------------------
Notable findings from this side project that the pipeline MUST also get right when authoring console
zones from scratch — surface each as a memory entry / note to main:
- Pointer model is FILE-OFFSET based: `value = (block<<29)|(fileoff-64) + 1`. Any content move needs
  every real block-5 pointer relinked; FOLLOW/INSERT are position-independent.
- The XAssetList holds real block-5 headerPtrs for aliased/shared-header assets (not all FOLLOW).
- Console aliases can target asset INTERIORS (StringTable cells → shared pool inside an XAnim blob),
  not just asset starts — the pipeline's pointer emit must handle interior targets.
- The genuine Wii U StringTable cellIndex sort (signed `hash-hash` overflow, tie by column, std::sort).
- The fastfile name seeds the Salsa20 keystream (wiiu_ff.HashChain) — packing name must match the
  target on-disk name.
- The section-3 delimiters (FontIcon 20-B alias, SndBank, SPT, MenuList, weapon-cluster bounding) are
  genuine console layouts the pipeline can reuse.
- OPEN: a Wii U loader POSITION-DEPENDENCY (section 4) that breaks a shifted-but-intact xmodel's
  dependency resolution. If the pipeline ever sees "could not load default asset" it is the same
  class — the guest-debug findings here should feed the pipeline's asset-placement model.

MECHANISM: write findings to `FINDINGS_patch_fullrelink.md` (create) and add one-line pointers in the
memory index `MEMORY.md`; the main session reads MEMORY.md each session. Tag pipeline-relevant items
"PIPELINE:" so they're easy to lift.

--------------------------------------------------------------------------------------------------
## 8. QUICK REFERENCE (paths / commands / artifacts)
--------------------------------------------------------------------------------------------------
- Zones (this session, decrypt copies): `dlc loading/native/upd_patch_{mp,zm}.ff` (TU, what loads),
  `pc_patch_{mp,zm}.ff` (PC source of DLC map rows). Base 7 MB `patch_{mp,zm}.ff` are NOT what the
  engine loads.
- Edit machinery (side project, extend here): `dlc loading/native/patch_relink.py`
  (`cmd_recon`/`cmd_roundtrip`/`cmd_edit`, `emit_stringtable`, `build_console_maprows`, `read_table`,
  `EditEmitter`, `orig_ff_name`). Run from `native_linker/`:
    python "../dlc loading/native/patch_relink.py" recon     "../dlc loading/native/upd_patch_mp.ff"
    python "../dlc loading/native/patch_relink.py" edit       "../dlc loading/native/upd_patch_mp.ff" --pc "../dlc loading/native/pc_patch_mp.ff" --tag mp -o "../dlc loading/native/_edit"
- Validate an edit: decrypt → ReEmitter walk to EOF (must reach `len(zone)`); recon must stay
  byte-identical (delta=0 ⇒ threshold identity); check header size/blockSize5; check XAssetList ptrs.
- Cemu log: `AppData/Roaming/Cemu/log.txt` (volatile — read before relaunch). Game crash report:
  `mlc01/usr/save/00050000/1010cf00/user/common/CrashReport3.txt`. Full dumps: `C:\CemuFullDumps`.
- Prior memory: [[patch-tu-fonticon-walker]] (this whole effort, all 4 fixes + swap + blocker),
  [[patch-mapstable-relink]], [[trackG-assemble-pointer-model]], [[native-console-linker]].
