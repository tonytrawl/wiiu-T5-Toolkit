# FINDINGS — PC patch_mp → Wii U full-conversion feasibility

2026-07-12. Side project (isolated). Tooling: `dlc loading/native/fullrelink/feasibility.py`
(re-runnable on any authentic PC patch_mp). Motivation: the additive-shift edit crashes on a
genuine loader POSITION-dependency ([[pathA-interior-ptr-disproven]]). Converting the whole PC
patch_mp fresh (in PC asset order = the genuine linker's order) would place every asset where the
loader expects — sidestepping the shift entirely — and yields ALL maps at once.

## The map delta
- Console patch_mp mapstable = **19 maps**. PC patch_mp = **31 maps**.
- **12 PC-only maps**: mp_concert, mp_magma, mp_vertigo, mp_studio, mp_uplink, mp_bridge,
  mp_castaway, mp_paintball, mp_dig, mp_frostbite, mp_pod, mp_takeoff.
- One conversion delivers all 12 → serves the "all DLC maps at once" goal directly.

## Conversion surface (PC 1764 assets vs console 1533; delta ~248, PC-order)
Because we HAVE the genuine console patch_mp as a backbone, only the DELTA must be converted from
PC; the shared ~1500 assets carry verbatim from the backbone.
- **MATERIAL +217** (PC 664 / con 447) — CONFIRMED the DLC-map DISPLAY layer: per map,
  `compass_map_mp_<map>`, `compass_overlay_map_<map>`, `menu_mp_<map>_map_select_final`. This is
  exactly the name+preview the size-preserving swap was missing. PC→console Material converter
  exists (byte-exact 437/446, [[trackA-material-converter]]).
- **TECHNIQUE_SET +7**, **XMODEL +5**, **FX +4**, **LEADERBOARD +14**, **DDL +1** — new DLC assets;
  converters/translate exist ([[trackB-techset-translate]], [[trackC-xmodel-converter]], Track D FX).
- **RAWFILE −16, SCRIPTPARSETREE −1** — console has MORE (console-specific); carry from backbone.
- The bigger **mapstable** (StringTable) is emitted natively (already done for the swap/edit).

## The unreversed types are NOT blockers here
- **WEAPON = 1**, **MENULIST = 1** — equal count PC vs console → carry the console body verbatim
  from the backbone (console WeaponDef/menuDef layouts remain unreversed, but a byte-identical
  single instance needs no re-emit).
- WEAPON_CAMO/ATTACHMENT/SOUND_PATCH/DDL: equal counts → also carry-verbatim ("UNKNOWN" in the
  classifier only because it lacked entries; not real unknowns).

## Why this can succeed where the additive shift failed
The additive edit kept the console 19-map ORDER and grew the table in place, shifting the tail to
positions the 19-map layout's loader didn't expect → OSFatal at fx_pistol_shell. A full assemble in
**PC's 31-map asset order** (= the order a genuine console 31-map linker would use; console order is
derivable from PC, multi-map validated [[trackF-nobackbone-assemble]]) places every asset at a
freshly-computed correct position with pointers computed by construction (Track G loader_sim,
[[trackG-assemble-pointer-model]]). That is structurally what the loader wants.

## Main residual risk
The +217 materials carry inline techsets + inline GX2 images. Material/techset conversion is solved;
the GX2 IMAGE pixel path (tiling / inline-material image emit) is the known-incomplete area
([[trackC-xmodel-converter]] image track; [[pipeline-fails-raid-control]]). Compass/map-select
images are 2D UI textures (simpler than 3D map textures), so lower risk — but this is the piece to
validate first.

## Recommended next step
Build the assemble on the existing `pc_convert_pipeline.py` (which already does "native-convert
simple/world + carry genuine console body for complex GX2 over a console backbone"), driving it with
the console patch_mp as backbone and PC order. First milestone: convert the DELTA (map rows + the
12 maps' display materials/images) and round-trip-validate before a full HW boot.

## Artifacts
- `dlc loading/native/fullrelink/feasibility.py` — the diff+classify pass.
  Run from native_linker/: `python "../dlc loading/native/fullrelink/feasibility.py"
  --pc "../dlc loading/native/pc_patch_mp.ff" --con "../dlc loading/native/upd_patch_mp.ff" --tag mp`
