# HANDOFF — DLC ipak auto-select wiring (small integration)

Standalone doc. Goal: make the conversion pipeline **auto-detect a DLC map's source ipak(s)** so DLC
maps convert without the user hand-passing `--pc-ipaks`. Small, well-scoped; closes the loop on the
already-resolved DLC investigation. Fully independent of the walk/geometry work.

## Background (already proven — don't re-investigate)
The DLC image-offload question is resolved (`FINDINGS_dlc_ipak_investigation.md`, memory
`dlc-ipak-partition.md`). Confirmed:
- DLC maps use the **identical offload model to stock** — `.ff` holds zone + streamed GfxImage stubs
  (no inline pixels); the pixels live in ipaks. The ONLY difference: a DLC map's textures are in a
  shared **`dlcN.ipak`** (zm: `dlczmN.ipak`), not `base`/`mp.ipak`.
- Source per map = `base.ipak` + `mp.ipak` + **exactly one `dlcN.ipak`** (+ a per-map ipak for the 3
  special maps below). Proven: mp_skate → **dlc1**, mp_bridge → **dlc3**.
- Practical demo (already run): mp_skate `prepare` with `base mp dlc1` dropped skips **397 → 7** (the 7
  are engine builtins — `$identitynormalmap`, `$outdoor` — same residue as stock, not gaps).
- **Per-map ipaks** exist only for `mp_frostbite`, `mp_nuketown_2020`, `zm_nuked` — those need their
  `<map>.ipak` added too.

## STEP 0 — PRELIMINARY (do FIRST, before any wiring): batch-convert the DLC *infrastructure* as-is and hardware-test menu behavior
Before building any DLC *map*, convert only the DLC **infrastructure** files (NOT the map `.ff`s) to
Wii U format exactly as they stand, put them on the console, and observe **whether the Wii U
auto-adds DLC content to its menus** (i.e. does the pack-mount + loadscreen/menu-art machinery cause
the game to surface DLC entries on its own, or is menu registration entirely manual?). This decides
whether we need the `mapsTable`/DLC-gate registry work at all for DLC, and de-risks the whole
approach cheaply.

**Convert these (infrastructure only):**
- Shared pack ipaks: `dlc0.ipak … dlc4.ipak`, `dlczm0.ipak … dlczm4.ipak` — PC→Wii U ipak
  (iterate every entry, GX2-tile via `ipak.py`/`gx2_texture.py`, re-author as a BE Wii U ipak).
  (These are large; a whole-ipak "convert as-is" pass, not the per-image `prepare` path.)
- Load fastfiles: `dlcN_load_mp.ff`, `dlcN_load_zm.ff` — PC v147 → Wii U v148 via the zone converters
  (they're thin: KVP + a 2D techset + loadscreen image/material pairs + rawfile; zm load zones also
  carry `menu_zm_map_*` art + a `zmb_*_load.all` soundbank). The KVP does `>level.ipak_read
  base/lowmip/dlcN` — that's the **pack-mount mechanism**; keep/rewrite the mounted-pak name to the
  Wii U pak naming.
- Load ipaks: `dlc0_load_mp.ipak`, `dlczm0_load_zm.ipak` (the only two that exist).

**Deploy + observe (Cemu):** place the converted DLC ipaks + load ffs where the game mounts them
(content dir), sig-patch as needed, boot, and record:
- Does the menu **auto-populate any DLC map/loadscreen entries**?
- Does the `_load_` KVP `ipak_read` actually **mount** the converted pack (does DLC art appear)?
- Any crash/reject on the converted infrastructure as-is?

**Why it matters / cross-reference:** the menu-registry finding (`wiiu-map-menu-registry.md` — menus
list maps from `mapsTable.csv`, DLC gate @0x0241CBA0) suggests menu listing is table-driven, so DLC
maps may NOT auto-add from infrastructure alone. This experiment confirms which: if the Wii U
auto-adds, we skip a chunk of registry work; if not, we know menu registration is manual and can plan
for it. Either outcome is a decision we want **before** committing to per-map DLC conversion.

**Tools:** `tools/ff_decrypt.py` (copy `.ff` out of `E:\` first), `WiiU_FF_Studio/wiiu_ff.py` (pack),
`wiiu_ref/ipak.py` + `gx2_texture.py` (ipak convert), `WiiU_FF_Studio/batch_convert.py` (batch driver),
`wiiu_ref/rpl_sigpatch.py` (sig bypass). Source: `E:\Call of Duty Black Ops II\pluto_t6_dlcs\zone\all`.
Deliverable: a short note on the observed menu/mount behavior → feeds whether registry work is needed.

## The rule to implement
Given a map name, build the `--pc-ipaks` source list automatically:
```
base.ipak + mp.ipak (mp)  OR  base.ipak + mp.ipak + dlczm-common (zm)
  + the map's dlcN.ipak (mp) / dlczmN.ipak (zm)
  + <map>.ipak  IF a per-map ipak exists (frostbite / nuketown_2020 / zm_nuked)
```
DLC source dir: `E:\Call of Duty Black Ops II\pluto_t6_dlcs\zone\all` (READ-ONLY; the pipeline reads
ipak indices in place — never write under E:).

## Two ways to know a map's pack (implement both: table + fallback)
1. **Cached map→pack table (fast path).** Build it once for all 15 mp + 5 zm DLC maps via the
   cross-ref script in `FINDINGS_dlc_ipak_investigation.md` (enumerate a map's GfxImage nameHashes,
   count matches per candidate pack, pick the **dominant `uniqueNew`** pack). Cache to a small json
   (e.g. `wiiu_ref/dlc_map_pack.json`: map → {pack, has_per_map_ipak}). Ship it.
2. **Cross-ref fallback (unknown maps / custom).** If a map isn't in the table, run the same
   cross-ref live against the candidate packs and pick the dominant one. Keeps it working for maps
   not pre-tabulated.

## Where to wire it
- `native_linker/pc_convert_pipeline.py` — `convert_pc_ff` / `build_ipak`: before calling
  `ipak_stream` prepare, resolve the map's pack and extend the `pc_ipaks` list with the dlcN/dlczmN
  (+ per-map) ipak. Detect mp-vs-zm from the map name prefix (`mp_` / `zm_`).
- `wiiu_ref/ipak_stream.py` — `DEFAULT_PC_IPAKS` currently hardcodes stock base/mp; leave those as the
  base and append the resolved DLC pack. `PcImageSource` already takes an arbitrary path list, so no
  change to the reader.
- Add the map→pack resolver as a small helper (e.g. `native_linker/dlc_packs.py`) reused by both.

## Validation
- **mp_skate**: pipeline auto-selects `dlc1` → prepare skips drop to ~7 (matches the manual demo).
- **mp_bridge**: auto-selects `dlc3`.
- **a zm map** (e.g. zm_buried): auto-selects the right `dlczmN`.
- A **per-map-ipak map** (nuketown_2020): auto-adds `mp_nuketown_2020.ipak` on top of its dlcN.
- **A stock (non-DLC) map** (mp_raid): resolver returns no DLC pack, pipeline falls back to base/mp
  only — must not break the existing path.

## Out of scope
- The `_load_` frontend zones (loadscreen/menu art, zm soundbank) — separate frontend-polish track,
  not needed for a map to boot. See the DLC findings doc.
- Building the full per-map-ipak split logic — just add `<map>.ipak` when present; the existing
  prepare handles the parts.

## Files
`native_linker/pc_convert_pipeline.py`, `wiiu_ref/ipak_stream.py`, new `native_linker/dlc_packs.py`
(+ cached `dlc_map_pack.json`); `FINDINGS_dlc_ipak_investigation.md` (the cross-ref script + the
map→pack evidence). Read-only DLC dir under `E:\`.
