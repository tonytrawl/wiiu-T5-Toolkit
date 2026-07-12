# HANDOFF — console walker gap blocking patch_mp/patch_zm relink (mapsTable extension)

2026-07-10. For the MAIN session (owns `native_linker`/`wiiu_ref`). The patch-zone mapsTable
relink job (add all PC map rows so custom maps are selectable) is **built and ready except for
one shared-walker gap**: the console `body_relayout.ReEmitter` desyncs early on the patch zones
and never reaches the mapsTable as a separable asset. This doc pins the gap precisely so it can
be fixed in the shared walker; the relink machinery downstream is done and waiting.

Files (mine, safe to keep): `dlc loading/native/patch_relink.py` (recon/roundtrip/edit),
`dlc loading/native/FINDINGS_patch_relink.md`. Console + PC copies:
`dlc loading/native/{patch_mp,patch_zm,pc_patch_mp,pc_patch_zm}.ff`.

## The gap (ROOT CAUSE — precise)
Walking genuine console `patch_mp.ff` with `ReEmitter` (Layout console=True), emitting each
body asset in order and tracking the TRUE stream position as `assets_end + len(w.buf)`:

- body#0 PHYSPRESET (PhysPreset) @14973 len=92 → next hdr = valid alias ✅
- **body#1 PHYSCONSTRAINTS (PhysConstraints) @15065 len=2696 → next @17761 = DATA (0x64656661), INVALID ❌**
- bodies #2+ then read from drifted offsets → all garbage; at body#35 a "RawFile" @18887 has
  name*=0x00010000 and len=0x140ffff (~21 MB) → it slurps the entire rest of the zone to EOF,
  swallowing ~1600 assets including the mapsTable (`mp/mapstable.csv` @file 5046670).

PhysConstraints layout (struct_layout): `const char* name; unsigned int count;
PhysConstraint data[16];`. The instance: name*=alias 0xa0003a41, count=0, but the fixed
`data[16]` array elements still carry alias/FOLLOW pointers (e.g. @+28 = FFFFFFFF, @+44 =
alias 0xa0003a49). The emit wrote 2696 B = 8 + 16*168 (struct array only) and did NOT emit the
per-element FOLLOWER strings those pointers reference (or the console PhysConstraint element
size ≠ 168). Either way the body is under-emitted → drift.

## Why the "byte-identical round-trip" LOOKED like it passed (don't be fooled)
`roundtrip_zone` catches the mid-walk exception and does `w.write_bytes(zone[cur:])` — a
verbatim tail copy. Because the drift only SHIFTS follower bytes between adjacent assets (each
missing follower is emitted as the next asset's leading bytes), the concatenated buffer stays
byte-identical to the original even though the per-asset structure is scrambled. So byte-equality
of the whole buffer is NOT a validity signal here. Correct signal: after each asset emit, the
next stream position must be a valid asset header (FOLLOW / alias / null) — body#1 already fails.

## What to fix (shared walker)
Console emit of **PhysConstraints** (fixed-array-of-structs-with-pointers followers), likely in
`body_relayout`/`walker`/`struct_layout`. Verify the console `PhysConstraint` element size and
that FOLLOW/alias pointers inside each of the 16 elements get their inline-name followers
emitted. This type barely appears in map zones (patch zones are physics/menu/table/script-heavy),
so it was never exercised — same class as the menuDef-union fixes done for PC walks.

After PhysConstraints, RE-VALIDATE the next patch-zone types in emit order (they currently read
from drifted offsets so their tiny lengths are meaningless): body#2/#5 techsets (delimiter-bounded,
probably fine), MENULIST, STRINGTABLE, FX, SCRIPTPARSETREE, then the long RawFile run. Use the
"next position is a valid header" check per asset to catch any further gap; the walk must reach
EOF with the final position == len(zone) and every intermediate position a valid header.

## Downstream is READY (no further main-session work needed for the edit itself)
Once ReEmitter walks patch_mp/patch_zm to EOF cleanly, `patch_relink.py` finishes the job:
- mapsTable is a LEAF (verified: 0 aliases point into its block-5 region across the whole zone),
  so substituting a bigger body is safe; `ReEmitter.omap` relinks every downstream back-alias on
  the size delta automatically.
- `EditEmitter` substitutes the mapsTable body for its asset (matches by source offset; needs the
  walk to actually REACH that offset — the only missing piece).
- `emit_stringtable` builds a self-contained console StringTable (all-FOLLOW cells, cellIndex =
  cells sorted by SIGNED djb2ci hash — validated against genuine in session 4).
- `build_console_maprows` merges ALL PC maps (user directive) into console format: PC map-specific
  cols (0,3,4,6,7,8,12,13,14,15) + console constants (1,2,5,9,10,11) copied from a reference
  console map row; updates maxnum_map. Console mp 17x16 (14 maps) → 34 rows (all 31 maps);
  zm 4x19 (Tranzit only) → +DLC zombie rows.

## DoD (unchanged, from the relink handoff)
Both patch zones walk to EOF + true no-edit round-trip (per-asset header validity, not just
buffer byte-equality) + repacked-unmodified boots. patch_mp with all map rows boots, rows visible
in menu, engine requests the expected zone name on select (record it). This also = the console
linker's second end-to-end proof on a non-map zone.
