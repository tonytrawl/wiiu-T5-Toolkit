# HANDOFF — patch_mp/patch_zm walk to EOF (console struct-layout RE)

Goal: make the console `ReEmitter` (native_linker/body_relayout.py) walk patch_mp.ff and
patch_zm.ff to EOF, every intermediate stream position a valid header. That unblocks the
DLC session's mapsTable substitution (patch_relink.py EditEmitter + build_console_maprows,
already DONE) → mp_skate (and all PC maps) become menu-selectable.

## Why this is needed (the bypass was ruled out — do not retry it)
The mapsTable (`mp/mapstable.csv` StringTable @file 5,046,670, 16×17) is MID-zone, in a run
of ~20 StringTables (4.91–5.53 MB), with a HARD asset cluster AFTER it (5.5–7 MB, asset idx
1477–1615: XGLOBALS/XANIM/XMODEL/WEAPON_CAMO/TRACER/WEAPON/ATTACHMENT). Editing the mapsTable
grows it and shifts the whole tail; the tail's real block-5 aliases need +delta, but 95% of
tail words in the block-5 numeric range are FLOAT/vertex DATA (resolve to 130–460 MB offsets
in a 7 MB zone) — real pointers are indistinguishable from geometry WITHOUT a structural walk.
So verbatim-copy-and-patch corrupts geometry; there is no clean bypass. (OAT Unlinker also
SEGFAULTs mid-load on this Wii U zone — not a usable oracle; its offsets drift vs genuine.)

## Progress already landed (verified, map-zone guards green: anchors PASS, raid gate PASS/0)
Walk advanced from body #1 to body #6 via two fixes (both in the guard path, no regression):
1. `body_relayout.ReEmitter.follow`: fixed-size embedded struct arrays (arr>1) were DROPPED —
   only arr==1 recursed. Now recurses per element. Fixes PhysConstraints.data[16] (each
   element's target_bone1@+20/target_bone2@+36 XString + material@+140 emit in order).
2. `shader_probe.parse_techset`: read the inline name cstring unconditionally; now guarded on
   `name@o+0 == FOLLOW`. Menu/loadscreen techsets have ALIAS names (no inline string).
Also built the correct validity gate: per-asset, emitted bytes must equal source[start:cur]
AND cur must land on each true next-body start (NOT whole-buffer equality — the verbatim tail
masks drift). Use this as the round-trip gate permanently. (Confirmed NOT bugs: GfxImage
`consume_image` matches `LoadConsoleImage` exactly.)

## Where it breaks now: asset #6 MENULIST (console menu layout diverges)
`menuDef_t` console = 392 B, PC = 400 B (`menudef_t_t6_load_db.cpp`:
`LoadWithFill(SwapEndianness ? 392 : 400)`). Divergent field offsets (console vs PC):
`rectXExp` 356/360, `rectYExp` 372/376, `items` 388/392. Up to `visibleExp`@276 they match.
`ExpressionStatement` is 16 B both (filename@0,line@4,numRpn@8,rpn@12). `windowDef_t` 164 B both.
The `numRpn = 0xFFFFFFFF` crash means struct_layout (PC header, 400 B) mis-sizes menuDef_t and/or
the `menus` field is `menuDef_t**` (double pointer) not handled — re-derive the console menu
sub-graph from the *_load_db FillStruct offsets (menuDef_t/itemDef_s/itemDefData_t union/
windowDef_t/rectDef_s), honoring every `SwapEndianness ? console : pc` offset.

## The RE work (bounded but real — the two hard families)
1. **Menu family** (asset #6, pre-mapsTable): menuDef_t 392, itemDef_s + itemDefData_t UNION
   (walker.walk already handles the union via the `alias` path — port that into ReEmitter.follow,
   which currently calls followers() without the union alias), the double-pointer `menus`/`items`
   arrays, GenericEventHandler/GenericEventScript/ScriptCondition/ItemKeyHandler followers.
   Source of truth: `.../XAssets/menudef_t/menudef_t_t6_load_db.cpp` FillStruct_* offsets.
2. **Weapon family** (asset idx 1592–1615, post-mapsTable): WeaponVariantDef/WeaponDef/
   WeaponAttachment(Unique)/WeaponCamo*/TracerDef — large console-divergent structs. Same method:
   read each `*_t6_load_db.cpp`, honor console offsets. Also XGLOBALS(1477-86), XANIM, XMODEL in
   that tail (XModel/XAnim converters exist in native_linker — reuse their console layouts).

## Method (proven this session)
Per asset in emit order: emit, then assert the NEXT stream position is a valid header for the
next asset's known type. When a struct mis-sizes, diff struct_layout's computed size against the
`*_t6_load_db.cpp` `LoadWithFill(SwapEndianness ? C : PC)` value; add the console offsets. Test
harness: the per-asset validity walk in this session (source-is-oracle for the no-edit round-trip).

## Done when
Both patch_mp and patch_zm walk to EOF, final cur == len(zone), every intermediate a valid
header. Then patch_relink.py cmd_edit runs (downstream is complete); it records which zone name
the engine requests for the mp_skate row (the boot artifact wants that). Keep the full guard
suite green (anchors, both gates, ST, self-checks) — PhysConstraints/menus/weapons are rare in
map zones but confirm no map-zone regression after each struct change. Never write under `E:\`.
