# HANDOFF — two console-walker gaps blocking the TU patch_mp/patch_zm mapsTable relink

2026-07-11. For the MAIN session (owns `native_linker`/`wiiu_ref`). The mapsTable edit machinery
(`dlc loading/native/patch_relink.py`) is COMPLETE and PROVEN — it produces correct extended
tables and relinks via `ReEmitter.omap`. But deploying requires the walk to reach **EOF** so the
whole tail is relinked; on the **update-partition (TU)** patch zones the ReEmitter stops early,
leaving a verbatim (un-relinked) tail whose pointers are stale after the +delta shift → the zone
**does not load** (hardware-confirmed: broke zombies; reverted).

IMPORTANT: the zones that actually load are the **update partition** ones, NOT base:
`C:\Users\...\Cemu\mlc01\usr\title\0005000e\1010cf00\content\english\patch_{mp,zm}.ff`
Copies to work from (this session): `dlc loading/native/upd_patch_mp.ff` (zone 14,713,280 B,
763-ish… actually 1656 assets) and `upd_patch_zm.ff` (zone 10,316,826 B, 763 assets). The 7 MB
BASE patch zones walk fine and edit fine — but they're not what the engine loads.

## GAP 1 — ZM: `_menulist_end` can't bound a MenuList not followed by a StringTable
`upd_patch_zm`: walk stops at asset **724 (MENULIST) @8008612** (AFTER the mapstable @5979206, so
the mapstable relink is correct — only the ~2.3 MB tail is verbatim). Assets 724–730 are **7
consecutive MENULISTs**, then SOUND(731), then RAWFILE×11 / TECHNIQUE_SET×7 / MATERIAL×6 /
XANIMPARTS×3 / FX×3 to EOF. **There is NO StringTable after asset 724.** `_menulist_end`
(`body_relayout.py`) bounds a MenuList by byte-scanning for the next `{FOLLOW,cols,rows,FOLLOW,
FOLLOW}+".csv"` StringTable header — which does not exist here → RuntimeError, walk aborts.
FIX NEEDED: bound a MenuList that is followed by another MenuList / SOUND / RAWFILE (not a
StringTable). Either a real console MenuList structural walker, or a MenuList→next-asset anchor
that works for MenuList-terminated runs (the menuDef/itemDef graph is the same one the comment at
`_menulist_end` describes as 424-B menuDef, not load_db's 392).

## GAP 2 — MP: ~~a MATERIAL mis-sized~~ **SOLVED — it was FONTICON, not a material** (2026-07-11)
CORRECTION to the original diagnosis below: material #142 is **fine**. The "invalid next header"
that flagged it (@273855 u32=0x01000000) was a FALSE POSITIVE — a genuine console GfxImage body
begins `01000000 <w> <h> 01000000` (not a pointer word), so 273855 IS the real image start and the
walk continues correctly through it.

The real MP drift was **body #458 = FONTICON @724649**. The generic walker has no structural model
for FontIcon's per-entry inline sub-tree and slurped ~875 KB → the first *provably* bad asset
downstream was RAWFILE #461. FIX LANDED in `native_linker/body_relayout.py`: new `_fonticon_end`
delimiter registered in `DELIMITERS['FontIcon']`. Console FontIcon layout (from
`fonticon_t6_load_db.cpp`): 20-B body {name*, numEntries, numAliasEntries, entry*, alias*} → name
XString → the 24-B FontIconEntry array (numEntries) → per-entry sub-data in order: FontIconName.string
(inline cstr if FOLLOW) + a full inline console Material (if fontIconMaterialHandle is FOLLOW) →
fontIconAlias array. **Wii U FontIconAlias = 20 B** (measured byte-exact: 1960 B / 98 aliases), NOT
the PC 8-B {aliasHash,buttonHash}. VERIFIED: re-emitted stream byte-identical to source for all
10,537,200 B up to the weapon, and the walk now passes the mp mapstable @8550268 cleanly.

MP EDIT NOW COMPLETE (2026-07-11): the walk reaches EOF and the tail is correctly relinked.
`dlc loading/native/_edit/upd_patch_mp.ff` = 31-map mp mapstable (recon byte-identical, edit
re-walks clean to EOF, 31 maps re-read). What it took, beyond FONTICON:
  * ASSET_ROOT was missing `ATTACHMENT`/`ATTACHMENT_UNIQUE` (walker.py) → asset 1269 WeaponAttachment
    was skipped, desyncing the walk. WeaponAttachment itself is trivial (284-B body + 2 XStrings).
  * `_sndbank_end` delimiter (sndbank_probe.parse_sndbank) — the generic walker under-read the
    ~660KB SndBank (asset 1301) by ~660KB.
  * `_weapon_end` delimiter — the genuine WiiU WeaponDef field layout diverges from the OAT header
    (unreversed) so neither the generic walker nor a load_db interpreter reproduces its extent; the
    single inline-weapDef WeaponVariantDef is BOUNDED instead, by anchoring on its trailing
    WeaponAttachment + rumble RAWFILE cluster. Bounding is enough because of the relink model below.
  * RELINK MODEL: genuine console cross-asset aliases only ever target asset STARTS (registered in
    the omap) or use FOLLOWING (inline). Interior-pointing alias-VALUED words are all DATA
    false-positives (verified 8808/8809). So a 2-PASS omap relink (pass 1 builds the complete
    src->writer map, pass 2 rewrites only registered-target words by +delta) is correct AND
    false-positive-free — no heuristic threshold bump needed. `cmd_edit` is now 2-pass;
    `emit_verbatim` relinks delimiter-asset bodies via omap when delta!=0 (byte-identical at delta=0).

STILL OPEN: ZM (GAP 1) — the 7 MenuLists still block the zm walk to EOF; once a MenuList walker
lands, the SAME 2-pass relink makes the zm edit correct too.

--- ORIGINAL (incorrect) GAP 2 diagnosis, kept for the record: ---
`upd_patch_mp`: walk drifts by 8 bytes at body #142 = MATERIAL @273349 ... [disproven above]

## How to reproduce / verify (drop-in, read-only)
```
cd native_linker
python - <<'PY'   # walk to EOF, report first drift + culprit
# (see this session's probes: valid-next-header check finds body#142 MATERIAL for mp,
#  and the MenuList RuntimeError for zm at asset 724)
PY
```
Success signal after the fix: `ReEmitter` emits every body with `assets_end+len(w.buf)`
monotonically == the per-asset return cursor, final position == len(zone), and every intermediate
next-position is a valid header (FOLLOW/alias/null). Then:
```
cd "dlc loading/native"
python patch_relink.py edit upd_patch_mp.ff --pc pc_patch_mp.ff --tag mp -o _edit
python patch_relink.py edit upd_patch_zm.ff --pc pc_patch_zm.ff --tag zm -o _edit
```
must print NO "walk stopped ... tail copied verbatim" and re-read all maps OK. Deploy the packed
`_edit/*.ff` to the UPDATE partition (`.stockbak` backups already there); boot Cemu.

## What's DONE and correct (downstream, no further work)
`patch_relink.py`: `read_table` (resolves alias cells via djb2 hash map — MT.dump_stringtable only
did inline), `build_console_maprows` (copies ALL PC cols incl. c05 map-index and c11 DLC-pack-index;
overrides only schema-divergent cols — mp c01/c02/c09/c10, zm none), `emit_stringtable`
(all-FOLLOW, signed-hash cellIndex), `EditEmitter` (leaf-substitution + `register()`/omap relink;
FIXED: was calling nonexistent `_reg`). Verified on the BASE zones: mp 14→31 maps, zm 1→7 maps,
+delta zone, mapstable re-reads OK. Column semantics (hw-relevant for the SEPARATE DLC-entitlement
gate): col5=map index, col11=DLC pack index (0 base,1 nuketown2020,3 Revolution,4 Uprising,
5 Vengeance,6 Apocalypse). Everything reverted to stock; zombies + MP load normally now.
