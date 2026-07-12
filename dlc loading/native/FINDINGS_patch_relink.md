> **CURRENT STATUS (2026-07-10, latest — read this first; supersedes the two sections below).**
> The whole document below is superseded by `../../FINDINGS_menu_console_layout.md`. Reconciliation
> of the two conflicting sections in THIS file:
> - The top "Stage 1 + Stage 2 BOTH PASS / NO shared-walker gap; NO routing needed" section is
>   **WRONG** (stale). Verified: `patch_relink recon patch_mp.ff` gives `STAGE 2 GATE FAIL … first
>   diff @38690`. There IS a shared-walker gap and routing WAS needed.
> - The "CORRECTION" section below is **directionally right** (byte-identical pass was an artifact
>   of the verbatim-tail copy; the walk desyncs; route to main session) but its named suspects are
>   **also stale**: PhysConstraints (body#1) and RawFile #35 were since fixed; the real first
>   blocker was **MENULIST (idx6)**, now SOLVED via a `_menulist_end` delimiter.
> - Current frontier: the walk now reaches **idx1477** (mapsTable region fully walks). idx1477-1486
>   are **DDL assets mislabeled XGLOBALS** by `console_to_pc` (cid46→pc44); DDLDef isn't in
>   T6_Assets.h. Then the weapon family. See FINDINGS_menu_console_layout.md Part 2.

# FINDINGS — patch_mp/patch_zm mapsTable relink (console→console)

2026-07-10. Job: extend genuine Wii U patch_mp/patch_zm mapsTable with all PC map rows.
Files (this dir): patch_mp.ff, patch_zm.ff = genuine CONSOLE (from Wii U content). 
pc_patch_mp.ff, pc_patch_zm.ff = PC (all DLC maps present). Tool: patch_relink.py.

## Stage 1 (walk) + Stage 2 (byte-exact round-trip): BOTH PASS on both zones
The earlier "patch_zm walk desync at asset 99" was a FALSE ALARM: the per-asset RETURN
cursor from ReEmitter.emit_asset is unreliable for some console asset types
(StringTable/techset), but the ReEmitter's internal block-5 accounting is correct and
the emitted buffer is byte-identical. NO shared-walker gap; NO routing needed.
Gate detail: slice the container at r.assets_end (NOT parse_container's container_end,
which rounds up — patch_mp assets_end=14973 vs container_end=14976; slicing at
container_end double-counts 3 pad bytes). patch_zm assets_end==container_end (no pad).
Both repack (0x7FC0) and re-decrypt to the identical zone. Controls in _rt/.

## mapsTable facts
- console mp/mapstable.csv @5046670 = 17 rows x 16 cols (R02-R15 = 14 stock maps only).
- console zm/mapstable.csv @4145344 = 4 rows x 19 cols (transit only).
- PC pc_patch_mp mapstable @7180288 = 34 rows x 17 cols: ALL 31 maps (stock R02-R15 +
  DLC R16-R32: nuketown_2020/downhill/mirage/hydro/skate/concert/magma/vertigo/studio/
  uplink/bridge/castaway/paintball/dig/frostbite/pod/takeoff). R33 = default 'B'.
- **console schema != PC schema** (not just -1 col). Per-map transferable cols (same):
  c00 name, c03 MPUI_<key>, c04 menu img, c06 MPUI_DESC, c07 compass, c08 size,
  c12-15 faction short/id. DIFFER: console c01/c02 = player-group symbol (TEAM_FOUR/19/14)
  + 'sa'/'bi'/'e' vs PC numbers (220/68); console c05/c11 = \x1e, c09/c10 =
  ICOPTER_COMLINK/_DESTROYED_HELICOPTER_COMLINK constants vs PC NO/YES/empty. PC has extra
  c16 (dropped by console). => build console DLC rows = PC map-specific cols + console
  constants (copy c01,c02,c05,c09,c10,c11 from a reference console row).

## Edit feasibility (Stage 3)
ZERO aliases point INTO the console mapstable region (leaf asset) — verified by hooking
ReEmitter.remap_ptr over the whole zone. So replacing it with a bigger self-contained
(all-FOLLOW) table is safe; ReEmitter.omap recomputes every downstream back-alias on the
size shift automatically. Approach: subclass ReEmitter (MY file), substitute the mapstable
body for that asset, advance source cursor past the original body; re-walk edited zone for
self-consistency; pack + sig-patch; Cemu.

---

# CORRECTION + ROUTING (2026-07-10, later) — Stage 2 gate does NOT truly pass; walk desyncs

**The earlier "Stage 2 byte-identical PASS" was an ARTIFACT, not a real walk.** roundtrip_zone
catches the ReEmitter's mid-walk exception and does `w.write_bytes(zone[cur:])` (verbatim
tail copy). The ReEmitter actually emits only ~36 bodies then throws; the verbatim tail makes
the buffer coincidentally byte-identical. So the no-edit gate is meaningless as written and the
mapstable (body ~600, file ~5.05MB) is NEVER reached as a separable asset -> Stage 3 edit is
BLOCKED. (My EditEmitter substitution silently no-op'd: emit never reached the mapstable's
src_file; edited zone came out +0 bytes, 14 maps.)

## Precise desync characterization (for ROUTING to the main session)
- Body-asset order (patch_mp): #0 PhysPreset, #1 PhysConstraints, #2 techset, #3 Material,
  #4 GfxImage, #5 techset, #6 MenuList, #7 StringTable, #8 Fx, #9 ScriptParseTree,
  #10..#34 RawFile (x25), then it breaks at #35/#36 RawFile.
- ReEmitter emits 36 bodies; body#35 RawFile returns cur=21055955 (> zone len 7053673): it
  read len≈0x140ffff (~21MB) and would slurp the rest. body#36 then reads OOB -> exception.
- Two drift signals: (a) valid-next-header check flags body#1 PhysConstraints @15065->cur=17761
  (next u32=0x64656661 mid-string); (b) the RawFile at the break has start bytes
  `00 01 00 00 01 40 ff ff ff ff` — the real FOLLOW-name is +6, i.e. the PRIOR RawFile
  under-emitted 6 bytes. So the first mis-size is at/near body#1 (PhysConstraints) OR a RawFile
  trailing-pad the console emit drops.
- Walker coverage: DELIMITERS = techset/Fx/XModel/Destructible/GfxLightDef/Material/GfxImage/
  GfxWorld/GameWorldMp (map-zone types). NO delimiter/detector for PhysConstraints, PhysPreset,
  RawFile trailing-pad, MenuList, Weapon/Attachment/Tracer/WeaponCamo — the patch-zone-specific
  types. These barely appear in map zones, so their console emit was never exercised.

## ROUTE TO MAIN SESSION (owns native_linker/body_relayout — read-only here)
Fix the console emit for the patch-zone asset types so the ReEmitter walks patch_mp/patch_zm
to EOF byte-exact (same treatment map-zone types got). Prime suspects in emit order:
PhysConstraints (body#1) body sizing, and RawFile trailing alignment (the +6). Once the walk
reaches the mapstable as a separable asset, the Stage 3 machinery here is ready: leaf mapstable
(0 incoming aliases, verified), EditEmitter substitution + all-FOLLOW emit + omap relink, and
build_console_maprows (PC map-specific cols + console constants) already produce the 34-row
table. Deliverables built + tested up to this wall: patch_relink.py (recon/roundtrip/edit),
emit_stringtable, build_console_maprows.
