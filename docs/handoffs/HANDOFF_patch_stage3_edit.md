# HANDOFF — patch_mp/patch_zm Stage 3: mapsTable edit + DLC-entitlement gate

Goal: make mp_skate (and every other PC map) SELECTABLE **and PLAYABLE** on Wii U by extending the
genuine console patch_mp/patch_zm mapsTable with the PC map rows, re-emitting a byte-correct console
zone, packing, sig-patching, and booting on Cemu.

## ⛳ CURRENT BLOCKER (2026-07-11) — DLC-entitlement / content gate, likely fixable via the mapsTable
With the RPL patch, **mp_skate now appears in the menu and DLC1 content is unlocked** — the mapsTable
+ menu-registry work is DONE (Stage 3 mapstable row is live). Selecting mp_skate now throws the
engine's per-map DLC gate:
> "You do not have this map or the content is damaged. You can get this map by downloading map packs
> from the Nintendo eShop." (Cemu, BO2 US v128)

This is a DIFFERENT, later gate than "map not in menu": the map row is accepted, but the engine's
per-map DLC/entitlement + content-location check rejects it. Working hypothesis (STRONG — the map
being visible proves the row is parsed): **one of the mapsTable columns tags each map with a DLC pack
the engine validates**, and mp_skate's generated row carries a DLC-pack/ownership value the engine
treats as un-owned or wrong-partition. Resolution path (do these in order):

1. **mapsTable column diff (primary).** Dump the EDITED console mp/mapstable.csv and compare the
   mp_skate row column-by-column against (a) a STOCK base map that plays fine (e.g. an always-owned
   launch map) and (b) the PC pc_patch_mp row for mp_skate. Find the column(s) that encode DLC-pack
   index / isDlc / content-partition. `build_console_maprows` currently copies PC map-specific cols +
   console constants for the fixed cols — the DLC discriminator is likely one it should be forcing to
   the "owned/base" (or the unlocked-dlc1) value rather than copying from PC. Candidates to inspect
   closely: the faction/id cols (c12-15) and any col not in the known-semantics list below. Set
   mp_skate's DLC column to match a playable map (or to dlc1, since dlc1 is the unlocked pack), re-run
   the edit, re-verify, re-boot.
2. **Content location.** "…or the content is damaged" can also mean the map's ipak/zone content
   isn't mounted where the engine looks for that DLC pack. Confirm mp_skate's zone + `mp_skate.ipak`
   (boot artifact skate_artifact/, memory [[container-author]]) are deployed to the partition the row
   points at, per the DLC offload model ([[dlc-ipak-partition]]: base+mp+dlcN.ipak). The mapsTable
   DLC column and the ipak partition must AGREE.
3. **DLC gate patch (fallback/complement).** If the mapsTable column alone doesn't clear it, the
   executable DLC gate at **0x0241CBA0** ([[wiiu-map-menu-registry]]) is the hard entitlement check;
   patching it is the belt-and-suspenders route. Prefer the mapsTable fix first (data, not code).

Known console mapstable column semantics (16 cols) for the diff: c00 name, c01/c02 player-group
symbol (TEAM_FOUR/…), c03 MPUI_<key>, c04 menu image, c05 = \x1e, c06 MPUI_DESC, c07 compass, c08
size, c09/c10 = ICOPTER_COMLINK/_DESTROYED_HELICOPTER_COMLINK, c11 = \x1e, c12-15 faction short/id.
The DLC/ownership discriminator is NOT obviously in this list → the diff in step 1 is how to find it
(it may be one of c12-15 repurposed, or a value inside c01/c02).

---

## (original Stage 3 mechanics — the edit itself, still the machinery)

## STATE: the wall is GONE — Stage 1/2 complete for BOTH zones (2026-07-11)
`patch_relink.py recon` STAGE 2 GATE = byte-identical no-edit round-trip **PASS** for both:
- patch_mp.ff : 7,053,673 B, 1656 assets, assets_end=14973, mp/mapstable.csv @5,046,670 (16 cols x 17 rows)
- patch_zm.ff : 6,163,064 B, 1600 assets, assets_end=12868, zm/mapstable.csv @4,145,344 (19 cols x 4 rows)

The whole console asset graph now walks to EOF and re-emits byte-exact, so the ReEmitter's `omap`
will relink every downstream back-alias across the mapsTable size delta. Stage 3 is unblocked.
(Files live in `dlc loading/native/`: patch_mp.ff, patch_zm.ff = genuine CONSOLE; pc_patch_mp.ff,
pc_patch_zm.ff = PC, all DLC maps present.)

## What landed this session to get here (all shared machinery — keep the raid gate green)
- `wiiu_ref/wiiu_zone.py::console_to_pc` REWRITTEN — WiiU v148 enum: one console-only type at id 7,
  MAP_ENTS at id 47, so ids 8..46 shift -1 and ids >=48 shift -2. The old Xbox360 rule mislabeled
  LEADERBOARD(cid44)->None [59 bodies SKIPPED], XGLOBALS(cid45), DDL(cid46). raid/skate/dock have no
  cid 44/45/46 so map-zone gates are unaffected.
- `wiiu_ref/struct_layout.py` — `_SCALAR64`: console aligns 64-bit scalars to 4 (menuDef showBits).
- `native_linker/body_relayout.py` — ReEmitter `follow(alias)`/`emit_ptr2`/`emit_inline_asset`;
  **ptr2 checked BEFORE string** (ddlEnumDef.members = `const char**`); DELIMITERS gained
  `MenuList` (`_menulist_end`, verbatim, byte-step .csv scan) and `XAnimParts` (`_xanim_end` =
  `xanimparts_probe.parse_xanim`, console 104-B body).
- Reconciled the self-contradictory `dlc loading/native/FINDINGS_patch_relink.md` (top "no gap"
  section was stale/wrong).
Full detail: `FINDINGS_menu_console_layout.md`.

## RUN THE EDIT (Stage 3)
Work from `dlc loading/native/`. The `edit` subcommand does: dump the console mapstable, dump the PC
mapstable, merge (console meta rows + console-format rows for every PC map not already present, via
`build_console_maprows`: PC map-specific cols + console constants for the fixed cols), emit a new
self-contained all-FOLLOW StringTable (`emit_stringtable`), substitute it for the asset via
`EditEmitter`, re-emit the whole zone (omap relinks the tail), re-walk for self-consistency, then
**pack**. Command:

```
cd "dlc loading/native"
python patch_relink.py edit patch_mp.ff --pc pc_patch_mp.ff --tag mp -o _edit
python patch_relink.py edit patch_zm.ff --pc pc_patch_zm.ff --tag zm -o _edit
```

Expected prints: "console had N maps, adding K PC maps -> M rows total", the new map names
(mp_skate should be in the mp list), the mapstable size delta, "re-read edited mapstable: M maps
present (OK)", and "packed <n> B ff -> _edit/patch_mp.ff". A "(WALK MISMATCH - inspect)" suffix or
"MISMATCH" means the self-consistency re-walk failed — do NOT ship it; debug before packing.

## VERIFY before shipping (do all three)
1. **Self-consistency (built into cmd_edit):** the re-read must report OK and M == expected map count.
2. **Re-walk the EDITED zone to EOF byte-clean:** decrypt `_edit/patch_mp.ff`, run the ReEmitter to
   EOF and confirm no desync/overflow (reuse `<scratch>/probe_walk.py` pattern, or add a recon-style
   gate on the edited zone). The edit grows the mapstable and shifts the tail; this proves the omap
   relink is correct end-to-end, not just around the mapstable.
3. **Regression gate MUST stay green** after any code change:
   `python native_linker/body_relayout.py wiiu_ref/mp_raid_genuine.zone 2000`
   -> "*** FULL ZONE ROUND-TRIP BYTE-IDENTICAL ***".

## DEPLOY (after verify passes)
- The packed `_edit/patch_*.ff` are zeroed-signature repacks (0x7FC0 codec). They load ONLY on a
  console/emulator with the update-partition RPL signature check patched:
  `wiiu_ref/rpl_sigpatch.py` (also in WiiU_FF_Studio GUI: Console -> RPL Signature Patch). See memory
  [[wiiu-sig-bypass]] (CONFIRMED WORKING).
- Boot on Cemu; open the map-select menu; confirm mp_skate (and the other added maps) appear and the
  engine requests the expected zone name for the mp_skate row. Note which zone name it requests — the
  boot artifact ([[container-author]] skate_artifact/) must match it.

## KNOWN RISKS / WATCH-FORS
- **Console mapstable schema != PC schema** (not just a dropped column). Per-map transferable cols:
  c00 name, c03 MPUI_<key>, c04 menu img, c06 MPUI_DESC, c07 compass, c08 size, c12-15 faction.
  DIFFER (copy console constants from a reference console map row): c01/c02 player-group symbol, c05/
  c11 = \x1e, c09/c10 = ICOPTER_COMLINK/_DESTROYED_HELICOPTER_COMLINK. PC has an extra c16 (dropped).
  `build_console_maprows` already encodes this; sanity-check a couple of the generated mp_skate cols
  against a genuine console row before shipping.
- The mapstable is a leaf (0 incoming aliases — verified by hooking remap_ptr over the whole zone),
  so growing it is safe; the risk is entirely in the downstream +delta relink, which Verify step 2
  covers.
- `cmd_edit`'s emit loop still wraps `emit_asset` in `try/except: pass`. With the walk now clean this
  should never fire, but if a future zone/asset regresses it would silently corrupt — consider making
  it raise during Stage 3 bring-up so problems surface loudly.
- Also add the mp_skate (and all PC map) ROWS to the map/menu registry if not already done — see
  memory [[wiiu-map-menu-registry]] / [[patch-mapstable-relink]] (USER wants ALL PC map rows).

## DONE WHEN
Zone/edit plumbing (ACHIEVED): both `_edit/patch_*.ff` pack from an edited zone that re-walks to EOF
byte-clean, mapstable re-reads with all maps, raid gate byte-identical, and mp_skate is SELECTABLE in
the Cemu menu with the RPL patch.
Final bar (CURRENT): selecting mp_skate LOADS INTO THE MAP instead of the DLC-entitlement/"content is
damaged" error — via the mapsTable DLC-column fix (+ matching ipak/zone deployment; DLC gate
@0x0241CBA0 as fallback). Never write under `E:\`.
