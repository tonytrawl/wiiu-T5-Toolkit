# FINDINGS — patch_mp/patch_zm walk past MENULIST → the tail (console layout), 2026-07-10

Goal (HANDOFF_patch_walk_console_layout.md): console ReEmitter walks patch_mp/patch_zm to EOF so
the mapsTable substitution (patch_relink cmd_edit) can land.

## ✅ DONE: patch_mp AND patch_zm walk to EOF, byte-identical no-edit round-trip PASS
`patch_relink.py recon` STAGE 2 GATE = **byte-identical** for BOTH: patch_mp (7,053,673 B, 1656
assets) and patch_zm (6,163,064 B, 1600 assets). The handoff's goal is met — Stage 3 (the mapsTable
edit) is unblocked. Raid round-trip stays **BYTE-IDENTICAL** (86,174,226 B) after every change below.

The full chain of fixes (all in wiiu_ref/wiiu_zone.py, wiiu_ref/struct_layout.py,
native_linker/body_relayout.py): MENULIST delimiter; console 64-bit-scalar align; ReEmitter
alias/ptr2/inline-asset + ptr2-before-string; the console→PC asset-id remap rewrite
(LEADERBOARD/XGLOBALS/DDL); DDL walk; and the **XAnimParts delimiter** — the last piece.

---
## Part 1 — MENULIST (SOLVED)

### The load_db is NOT authoritative for the Wii U menu layout
`menudef_t_t6_load_db.cpp` "console" offsets give menuDef_t=392, but the genuine Wii U menuDef_t
body is **424 bytes**: window.name (FOLLOW@0) points to the first dynamic, and the real string
"default_menu" begins at 0x98ce → 424 (not 392, not PC's 400). The dynamics hold an inline
material (3f800000/3f666666) + an item "@MENU_MENU_COULDNT_BE_FOUND", so item/expression fields
sit at offsets the load_db doesn't describe. Re-deriving the whole sub-graph from one mostly-empty
stub is unreliable, and menus are copied unchanged for the mapsTable relink.

### Fix (landed)
`native_linker/body_relayout.py` `_menulist_end` DELIMITER: bounds MenuList like GfxWorld/techset/
XModel and copies it verbatim. Scans forward **byte-by-byte** (console StringTable bodies are NOT
4-aligned — mp/defaultstringtable.csv's header lands at 0x9b07 ≡ 3 mod 4; a 4-byte stride skipped
it and swallowed ~4.4 MB) for the next `{name FOLLOW, cols<64, rows<4096, values FOLLOW, cellIndex
FOLLOW}` header with an inline `<path>.csv` name. Also landed: console 64-bit-scalar alignment in
`struct_layout.py` (`_SCALAR64`, a valid WiiU ABI fact), and `ReEmitter.follow` alias/emit_ptr2/
emit_inline_asset port.

---
## Part 2 — the tail: DDL + LeaderboardDef SOLVED (frontier now = XAnim/Weapon family)

### SOLVED: console→PC asset-id remap was wrong for WiiU (LEADERBOARD/XGLOBALS/DDL)
`wiiu_ref/wiiu_zone.py::console_to_pc` was Xbox360-v146-derived: it treated console id 44 as
console-only and used -2 past id 44, which mislabeled **LEADERBOARD (cid44) → None** (skipped!),
**XGLOBALS (cid45) → 43**, **DDL (cid46) → 44 (XGLOBALS)**. The correct WiiU v148 rule: ONE
console-only type at id 7, MAP_ENTS relocated to id 47, so ids 8..46 shift -1 and ids >=48 shift -2.
Rewritten accordingly. Verified on genuine patch_mp: cid44 = 59 LeaderboardDef bodies (~86 KB that
were being skipped), cid46 = 10 ddlRoot_t "*.ddl". **raid/skate/dock have NO cid 44/45/46 asset**
(only 43/47/48/50 in this range) → map-zone gates unaffected (raid stays BYTE-IDENTICAL).

### SOLVED: DDLs walk (ddlRoot_t → ddlDef_t → structs/enums)
All DDL structs are in T6_Assets.h (lowercase: ddlDef_t/ddlStructDef_t/ddlEnumDef_t/
ddlMemberDef_t/ddlHash_t), plain 32-bit (console layout == PC), no SwapEndianness. The generic
walker handles them once labeled DDL — EXCEPT a ReEmitter bug the walker didn't have:
**`ddlEnumDef_t.members` is `const char** members` = ptr2 AND string.** `ReEmitter.follow` checked
the plain-`string` case BEFORE `ptr2`, emitting ONE cstring instead of the N-slot array of string
pointers → ~889-byte under-read per multi-enum DDL (stats.ddl). Fix: check `ptr2` before `string`
in `follow()` (emit_ptr2 already handles the string element). Now all 10 DDLs walk byte-exact.

### ✅ SOLVED: XAnim/XModel/Weapon family (idx1583-1615) via the XAnimParts delimiter
The whole family cleared once XAnimParts was bounded. `struct_layout` used the PC 92-B XAnimParts,
but the console body is 104 B (boneCount[10]@24, counts@40/44, ptrs@64-100). The existing
`wiiu_ref/xanimparts_probe.py::parse_xanim(z, o, '>')` parses it CORRECTLY (the earlier "3rd anim =
all-0xFF" was a red herring — parse_xanim ended 'void_loop' exactly at the next asset, a 25-technique
MaterialTechniqueSet; my chain-test just mis-parsed that techset as an anim). Fix = register
`_xanim_end` (= parse_xanim) in `body_relayout.DELIMITERS`. XModel/WEAPON_CAMO/TRACER/WEAPON/
ATTACHMENT then all walk via their existing struct layouts / delimiters. Both zones reach EOF.

### (historical) diagnosis of the XAnimParts blocker
idx1583 XANIMPARTS @0x546afd. Diagnosis complete:
- The PLAIN WALKER also overflows here (not a ReEmitter bug): struct_layout uses the PC 92-B
  XAnimParts, but the **console body is 104 B** (documented in `wiiu_ref/xanimparts_probe.py` and
  `native_linker/smalls_convert.py:167`): boneCount[10]@24, notifyCount@34, randomDataShortCount@40
  (u32), indexCount@44, ptrs@64-100. raid does NOT structurally walk XAnimParts (0 in its output),
  so it was never exercised by the ReEmitter gate.
- `xanimparts_probe.py::parse_xanim(z, o, '>') -> (end, name)` is the right delimiter and walks the
  first two patch_mp anims cleanly ('void' 16449 B, 'void_loop' 16482 B, each -> next=FOLLOW), but
  MIS-SIZES the run: the "3rd" position 0x54eba0 is all-0xFF (every count/ptr = 0xFFFF/0xFFFFFFFF),
  i.e. parse_xanim over/under-read one of the first two and landed in a 0xFF region. This is the
  SAME unsolved delta/streamed-data sizing gap recorded in `CAVEATS_nobackbone_boot.md` ("dockside
  oracle: one XAnimParts 16,047 vs 16,053 genuine, +6 bytes then hard-diff from offset 3,412 — a
  convert_xanim walk/size gap"). So the XAnimParts delimiter is one bug-fix away: fix parse_xanim's
  delta record / streamed-data size math (the +6 gap), then register `_xanim_end` in
  body_relayout.DELIMITERS and the walk continues into XMODEL/WEAPON_CAMO/TRACER/WEAPON/ATTACHMENT.
- Next after xanim: XMODEL (reuse native_linker convert_xmodel console layout), then the weapon
  structs (WEAPON_CAMO/TRACER/WEAPON/ATTACHMENT) idx~1592-1615.

### (historical, now resolved) idx1477-1486 are DDL assets MISLABELED as XGLOBALS
- r.assets[1477..1486] = (cid=46, pc=44, 'XGLOBALS'). But the body @0x526376 is `{FOLLOW, FOLLOW}`
  (8 bytes) followed by the inline name "ddl_mp/gametype_settings.ddl". **`ddlRoot_t` = exactly 8
  bytes `{const char* name; DDLDef* ddlDef;}`** — a perfect match. Ten assets each named after a
  `.ddl` file are DDLs; ten "XGlobals" would be nonsensical (a zone has ~1 xglobals).
- Root cause: `wiiu_ref/wiiu_zone.py::console_to_pc` maps cid46→pc44 (XGLOBALS) and makes pc45
  (DDL) UNREACHABLE (cid47 is special-cased to MAP_ENTS/16). The remap was derived for Xbox360
  v146 ("console-only types inserted at ids 7 and 44"); the Wii U v148 enum around 44-47 differs,
  so DDLs land on the XGlobals id. The walker then uses XGlobals (564 B) for an 8-B ddlRoot body
  → reads garbage counts (gumpsCount) → runs off the end.
- **Safe to fix: raid (and other walked map zones) have ZERO DDL and ZERO XGLOBALS assets**, so a
  remap correction / DDL handling cannot regress the raid gate.

### Blocker within the DDL: DDLDef is not in T6_Assets.h
`struct_layout.get('DDLDef')` → KeyError (also DDLStruct/DDLMember absent). So even with the label
fixed, the `ddlRoot_t.ddlDef` inline sub-tree (the actual DDL: structs/members/enums/hashtables)
cannot be walked structurally from the header. Two paths:
  1. Derive the WiiU DDLDef console layout from genuine bytes (like the other console structs), OR
  2. A `_ddlroot_end` verbatim delimiter bounding each ddlRoot by the next asset — BUT verbatim
     does NOT relink internal block-5 aliases, so it is only valid for the NO-EDIT round-trip, not
     for the mapsTable EDIT (the DDLs are after the mapstable and their internal aliases need +delta).

### After the DDLs: the weapon family (handoff "family #2")
idx1487+ returns to RAWFILE, then later XANIM/XMODEL/WEAPON_CAMO/TRACER/WEAPON/ATTACHMENT
(idx~1592-1615). Same method: derive console layouts from genuine bytes. XModel/XAnim converters
already exist in native_linker — reuse their console layouts.

### Why the tail must WALK (not verbatim) for the EDIT
The mapstable edit grows the table and shifts every later body by +delta. Tail-internal block-5
aliases (pointing after the edit) need +delta; the ReEmitter's omap does this ONLY for structurally
-emitted assets. Verbatim-delimited tail assets keep stale aliases → broken edit. (Menus are before
the mapstable, so verbatim is fine there.)

---
## Next steps (task #3)
1. Confirm/derive the WiiU console enum around ids 44-47 (DDL vs XGLOBALS) — patch_zm gives a second
   sample; fix `console_to_pc` (or add a targeted cid46→DDL) so ddlRoot_t is used. Raid unaffected.
2. Derive the WiiU DDLDef console layout (ddlRoot → DDLDef → DDLStruct/DDLMember/DDLHash) from
   genuine bytes so the 10 DDLs walk + relink; or bound-and-verbatim for the no-edit gate only.
3. Weapon family console layouts for idx~1592-1615.

## Repro / gates
- patch_mp walk probe: `<scratch>/probe_walk.py <patch_mp.ff>` (per-asset; .csv anchor; overflow +
  header guards). Tail boundary probe: `<scratch>/tail_probe.py`.
- raid gate (must stay green): `python native_linker/body_relayout.py wiiu_ref/mp_raid_genuine.zone
  2000` → "*** FULL ZONE ROUND-TRIP BYTE-IDENTICAL ***".
Never write under E:.
