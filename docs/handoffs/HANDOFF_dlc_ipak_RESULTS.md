# HANDOFF → main session — PC DLC ipak/ff structure (RESOLVED)

Answers the exploratory task in `HANDOFF_dlc_ipak_investigation.md`. **All questions answered;
H1 confirmed.** Full detail in `FINDINGS_dlc_ipak_investigation.md`; memory:
`dlc-ipak-partition.md`.

## TL;DR
PC DLC uses the **identical texture-offload model to stock PC**. A DLC map `.ff` holds zone +
streamed GfxImage stubs — **no inline pixels**. The only difference vs stock: a map's DLC-unique
textures live in a shared **`dlcN.ipak`** (zm: `dlczmN.ipak`) instead of `base`/`mp.ipak`.
→ **DLC conversion = a source-ipak wiring change to the existing `ipak_stream` pipeline, NOT new
`.ff`→ipak repacking.** Nothing new to build for images.

## Q&A
- **Q1 — DLC `.ff` inline pixels?** No. Fully offloaded like Wii U. Cross-ref resolves ~all
  GfxImages from ipaks (mp_bridge 767/776, mp_skate 1022/1029); the handful unresolved are engine
  builtins (`$identitynormalmap`, `$outdoor`) + a few composited decals — same residue as stock.
- **Q2 — which ipak sources a map?** `base.ipak` + `mp.ipak` + exactly one `dlcN.ipak`.
  Proven: **mp_skate → dlc1** (the old "392 skips" = dlc1 textures), **mp_bridge → dlc3**.
- **Q3 — `_load_` ff/ipak pairs?** Frontend loadscreen + ipak-mount manifest zones (see below).
  Not menu registration, not `common_mp`.
- **Q4 — per-map ipaks (frostbite / nuketown_2020 / zm_nuked)?** Bonus/standalone maps whose
  map-unique streamed parts live in a per-map ipak; convert with base+mp+`<map>.ipak`(+dlcN).

## Conversion recipe (per DLC map)
Feed `ipak_stream.py prepare <meta> <out> --pc-ipaks ...`:
- ordinary DLC map: `base.ipak mp.ipak <map's dlcN.ipak>` → skips drop to ~0.
- bonus map w/ per-map ipak: also add `<map>.ipak`.
- zm map: use `dlczmN.ipak` in place of `dlcN.ipak`.
Find a map's pack: run the cross-ref script in FINDINGS (dominant `uniqueNew`).
No change to image-source assumptions in `HANDOFF_native_converters.md` (same model as the
mp_la 287/287 validation).

## The `_load_` zones (deep-dived)
Thin per-pack frontend zones. Asset list = **keyvaluepairs** (payload) + trivial 2D techset +
per-map `loadscreen_*` image/material pairs + empty rawfile. The KVP reconstructs as
`>level.ipak_read base/lowmip/dlcN` — **this is the mechanism that mounts the pack's ipak.**
Loadscreen images are streamed stubs.

- **mp** (`dlcN_load_mp`, mounts `dlcN`): loadscreens only. dlc1 = downhill/hydro/mirage/skate.
- **zm** (`dlcN_load_zm`, mounts **`dlczmN`** — naming quirk): richer — ALSO carries zombies
  map-select menu art (`menu_zm_map_<X>` large/_blur/_blit region sets) **and** a load soundbank
  (`zmb_<X>_load.all`). zm map→pack: dlczm0=zm_nuked, dlczm1=zm_highrise, dlczm2=zm_prison,
  dlczm3=zm_buried, dlczm4=zm_tomb.
- **Bonus load ipaks:** only `dlc0_load_mp.ipak` (688KB, 1 entry = loadscreen_mp_nuketown_2020)
  and `dlczm0_load_zm.ipak` (4 entries = zm_nuked frontend art) exist — self-contained so the
  preorder-bonus frontend shows before the big pack ipak mounts. **Irrelevant to Wii U** (ships
  Nuketown / NT-Zombies). dlc1-4 load zones have no load ipak (art streams from mounted dlcN).

Still **no** `mapsTable`/menu-registry asset in any load zone — menu registration stays separate
(see `wiiu-map-menu-registry.md`, mapsTable.csv + DLC gate).

## To port a DLC map's frontend
Convert the thin `_load_` zone: rewrite the KVP mounted-pak name → Wii U pak, run loadscreen
images through `ipak_stream`. For **zm** additionally convert the menu images (ipak_stream) + the
load soundbank (existing SAB path, `wiiu-sab-converter.md`). No gameplay content in these zones.

## Suggested next steps (not done here)
1. End-to-end proof: run `ipak_stream.py prepare` on mp_skate with `--pc-ipaks base mp dlc1` and
   confirm skip count → ~0 (cross-ref already proves it; this is the practical demo).
2. Build the full map→pack table for all 15 mp + 5 zm DLC maps via the FINDINGS script.
3. Decide whether Wii U needs a converted `_load_` analog at all, or if the menu-registry path
   already handles loadscreen/menu art for custom maps.

## Artifacts / tooling used
- `tools/ff_decrypt.py` (PC v147), `wiiu_ref/pc_image_enum.py`, `wiiu_ref/ipak.py`,
  `tools/ref_oat/build/bin/Release_x64/Unlinker.exe` (`--list`, `-o <dir>`).
- Sources: DLC `E:\Call of Duty Black Ops II\pluto_t6_dlcs\zone\all`; stock ipaks
  `E:\pluto_t6_full_game\zone\all\{base,mp}.ipak`. Read-only — copy `.ff` to scratchpad before
  decrypt (ff_decrypt writes next to input).
