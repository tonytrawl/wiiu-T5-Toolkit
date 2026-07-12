# STEP 0 — DLC load-infrastructure conversion (menu/mount hardware test)

## RESULT (2026-07-07 hardware test): NEGATIVE — menus do NOT auto-populate
Ran the game with these files in the correct locations. The game **booted fine** (the
null-techset load zones did not crash the frontend), but the **menu did NOT add the DLC maps**.
Conclusion: mounting DLC load infrastructure does NOT surface DLC map entries — **menu
registration is manual/table-driven** (mp/zm `mapsTable.csv`, DLC gate @0x0241CBA0; see memory
`wiiu-map-menu-registry`). A DLC map port therefore needs the registry work: add a mapsTable
row (map-pack index 0 to dodge the DLC gate) + display-name localizedstring + loadscreen, repack
the carrying ff (common_mp / ui_mp), OR patch `Content_PlayerHasDLCForMapPackIndex` @0x0241CBA0
always-true. This cannot be skipped for DLC.

---


Goal: put the converted DLC **loading infrastructure** (NOT the map `.ff`s) on the Wii U and
observe **whether the console auto-adds DLC content to its menus** and whether the
`_load_` KVP `ipak_read` actually mounts a converted pack. This decides whether the
`mapsTable`/DLC-gate registry work (`wiiu-map-menu-registry`) is needed for DLC, or whether
mounting the load infra alone surfaces DLC entries.

## What's here (PC → Wii U v148, all verified `TAff0100` containers)

| load ff (mount KVP)   | authored Wii U ipak            | zone image assets converted |
|-----------------------|--------------------------------|-----------------------------|
| dlc0_load_mp.ff       | — (zone has no image assets*)  | 0 (preorder NT2020 screen lives elsewhere) |
| dlc1_load_mp.ff       | dlc1_load_mp.ipak (1)          | loadscreen_transit_dr_returned_diner |
| dlc2_load_mp.ff       | —                              | 0 (mp loadscreens not enumerated**) |
| dlc3_load_mp.ff       | —                              | 0 ** |
| dlc4_load_mp.ff       | dlc4_load_mp.ipak (1)          | loadscreen_mp_podville |
| dlc1_load_zm.ff       | dlc1_load_zm.ipak (4)          | Die Rise menu + loadscreen |
| dlc2_load_zm.ff       | dlc2_load_zm.ipak (5)          | Mob of the Dead menu + loadscreen |
| dlc3_load_zm.ff       | dlc3_load_zm.ipak (8)          | Buried menu + 3 loadscreens |
| dlc4_load_zm.ff       | dlc4_load_zm.ipak (4)          | Origins menu + loadscreen |
| dlczm0_load_zm.ff     | dlczm0_load_zm.ipak (4)        | Nuketown-Zombies menu + loadscreen (self-contained) |

The **zm load zones are the strongest test cases** — each carries full map-select menu art
(`menu_zm_map_*` large/_blur/_blit) + loadscreens, all with matching streamed part hashes in
the paired ipak. `dlczm0_load_zm` is fully self-contained (art came from its own load ipak).

\* `dlc0_load_mp` has zero GfxImage assets in its zone — the orphan preorder
`loadscreen_mp_nuketown_2020` IWI is irrelevant to Wii U (ships NT2020). Mount KVP only.

\** The mp `_load_` zones' loadscreen images are not caught by `pc_image_enum.scan_pc_images`
(enumerator gap; OAT's asset list shows them but the native scanner misses these particular
bodies). The **KVP mount directive is intact** regardless, so the mount test is unaffected —
only the mp loadscreen art may be blank.

## Known caveats (do not treat as failures — this is a probe)
1. **Null techset.** Every `_load_` zone's `trivial_*` techset has its GX2 shader subtrees
   emitted null (D3D11→GX2 transcode not done here). The loadscreen quad has no shader, so it
   may draw nothing or, if the GPU is asked to draw a null program, hang. The **KVP is asset 0**
   and mounts before any draw, so mount/menu registration should still be observable. If a load
   zone crashes on the draw, that itself is a useful data point (means the frontend draws the
   loadscreen immediately and we need a real substitute techset — the `techset_translate`
   name-grammar can supply one).
2. **KVP mounts `dlcN`/`dlczmN` (the big shared packs), which are NOT shipped here.** That
   mount will find nothing for the streamed map textures — expected. The self-contained load
   ipaks above still resolve the menu/loadscreen art they carry.
3. **Signature.** `wiiu_ff.pack` writes a zeroed signature. Loading requires the sig-bypassed
   update-partition RPL (`wiiu-sig-bypass`, tool `wiiu_ref/rpl_sigpatch.py` / WiiU_FF_Studio →
   Console → RPL Signature Patch). Apply that before booting.

## Deploy + observe (Cemu or console)
1. Sig-patch the update-partition RPLs (if not already).
2. Place these `.ff` + `.ipak` files where the game mounts DLC content (content dir).
3. Boot and record:
   - Does the menu **auto-populate any DLC map / loadscreen entries** from mounting these?
   - Does the `_load_` KVP `ipak_read` **mount** the converted pack (does DLC art appear —
     e.g. the zm map-select thumbnails from the `dlc*_load_zm.ipak`)?
   - Any crash/reject on the converted infrastructure as-is (and at which asset/stage)?
4. Write the observation back to `FINDINGS_dlc_ipak_investigation.md` / memory
   `dlc-ipak-partition`. If menus auto-populate → registry work can be skipped for DLC; if not →
   menu registration is manual (plan the `mapsTable`/DLC-gate path).

## Scope note
The big shared pack ipaks (`dlc0..4.ipak`, `dlczm0..4.ipak`, ~100 MB each) are **out of scope
for this probe** — they hold in-game map textures, not menu/mount infrastructure, and require a
whole-ipak PC→Wii U converter (not yet built). They are irrelevant to the menu/mount question.

Generated by the full image pipeline: OAT `OAT_IMAGE_DUMP`-equivalent native enumeration
(`pc_image_enum`) → `ipak_stream prepare` (GX2-tiled parts + authored ipak) → OAT
`OAT_IMAGE_DIR` + `OAT_WRITE_WIIU` re-embed → `wiiu_ff.pack`.
