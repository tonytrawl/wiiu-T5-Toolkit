# FINDINGS — PC DLC fastfile + ipak structure (Wii U conversion)

Investigation of how PC BO2 DLC content partitions between `.ff` (zone) and `.ipak` (streamed
pixels), and what it means for converting a DLC map to Wii U. **Bottom line: H1 confirmed.**
DLC uses the exact same offload model as stock PC — the `.ff` holds zone + streamed GfxImage
stubs (no inline pixels); pixels live in ipaks. The *only* difference is DLC pixels come from
`dlcN.ipak` instead of `base.ipak`/`mp.ipak`. **DLC conversion is a source-ipak wiring change to
the existing pipeline, not new `.ff`→ipak repacking.**

Sources used:
- DLC zone dir: `E:\Call of Duty Black Ops II\pluto_t6_dlcs\zone\all` (read-only)
- Stock ipaks: `E:\pluto_t6_full_game\zone\all\{base,mp}.ipak`
- Tools: `tools/ff_decrypt.py`, `wiiu_ref/pc_image_enum.py`, `wiiu_ref/ipak.py`

---

## Q1 — Does a DLC `.ff` carry inline pixels, or is it fully offloaded like Wii U? → FULLY OFFLOADED
Cross-referencing every hash-valid GfxImage in a DLC map against the ipaks resolves essentially
all of them from ipaks — nothing is inline in the `.ff`:

| map        | GfxImages | resolved from ipaks | unresolved |
|------------|-----------|---------------------|------------|
| mp_bridge  | 776       | 767                 | 9          |
| mp_skate   | 1029      | 1022                | 7          |

The unresolved handful are **engine runtime/default images, not streamed pixels** — identical to
what stock maps leave unresolved:
- `$identitynormalmap`, `$outdoor` — `$`-prefixed engine built-ins (never in any ipak, any platform)
- a few composited decal/`~~-g...` parts (`decal_carrier_2048_n`, `concrete_exposed_n`, …)

So a DLC `.ff` = zone + metadata + streamed GfxImage stubs, conceptually the same as Wii U. No
pixel data needs to be extracted from the `.ff` and repacked.

## Q2 — Which ipak(s) source a DLC map's images? → base + mp + exactly one dlcN
Per-map breakdown (unique-new = images first supplied by that pack, in scan order):

**mp_skate** (1029): base 600, mp 32, **dlc1 +378**, (dlc0/2/3/4 add only shared/dup parts).
→ mp_skate's DLC textures live in **dlc1.ipak**. This is exactly the earlier "392 skips":
they were the dlc1 textures, skipped because only base/mp were fed as sources.

**mp_bridge** (776): base 423, mp 20, **dlc3 +242**, dlc2 +42, dlc1 +38 (+ small shared).
→ mp_bridge's DLC textures live primarily in **dlc3.ipak**.

Pattern: a map's shared/common textures come from stock `base.ipak` (+ a little `mp.ipak`), and
its DLC-unique textures come from **one** `dlcN.ipak` (the pack that map shipped in). Some cross-
pack sharing exists but is subsumed by feeding base + mp + that map's dlcN.

To identify the dlcN for any other DLC map, run the cross-ref script (below) and pick the pack
with the largest `uniqueNew`.

## Q3 — What are the `_load_` ff/ipak pairs? → stream-source registration zones (thin)
`dlc0_load_mp.ff` decrypts to a 7865-byte zone. Its strings are literally the **ipak stream keys**
the engine should mount: `base`, `lowmip`, `dlc0`, plus one shared shader
(`pimp_shader_vertcolorsimple`) and `PerSceneConsts` techset constants. The matching
`dlc0_load_mp.ipak` holds a single entry.

Role: a preload/registration zone that tells the engine which stream paks exist for that DLC pack
(stream-key registration), not a content zone. On Wii U the analog is however the console mounts
its per-map ipak; these thin PC `_load_` zones are **not** map content and don't need per-asset
conversion — at most they inform which ipak name to register.

## Q4 — Per-map ipaks (mp_frostbite, mp_nuketown_2020, zm_nuked) vs shared dlcN
Only a few maps carry their own per-map ipak (`mp_frostbite.ipak` 86MB, `mp_nuketown_2020.ipak`
158MB, `zm_nuked.ipak` 136MB) — the bonus/standalone maps. These are the DLC analog of a Wii U
per-map ipak: map-unique streamed parts kept out of the shared `dlcN.ipak`. For converting those,
feed **both** the per-map ipak **and** base/mp (and likely the associated dlcN) as sources.

---

## Conversion recipe (per DLC map)
Feed the existing `ipak_stream.py prepare` pipeline these `--pc-ipaks` sources:

1. **Ordinary DLC map** (bridge, castaway, concert, dig, downhill, hydro, magma, mirage,
   paintball, pod, skate, studio, takeoff, uplink, vertigo):
   `base.ipak` + `mp.ipak` + the map's `dlcN.ipak` (skate→dlc1, bridge→dlc3; identify others via
   the script below). Expect skip count → ~0 (only `$`-builtins remain, as on stock).
2. **Bonus maps with a per-map ipak** (frostbite, nuketown_2020, zm_nuked):
   `base.ipak` + `mp.ipak` + `<map>.ipak` (per-map) + the relevant `dlcN.ipak`.
3. **`_load_` zones:** treat as stream-key registration, not content. No per-asset conversion;
   only relevant to know which ipak name the console should mount.

No change to the image-source *assumptions* in `HANDOFF_native_converters.md` is needed — PC DLC
is the same offload model already validated on mp_la (287/287). The only wiring change is pointing
`--pc-ipaks` at the correct `dlcN.ipak` for the map instead of just base/mp.

## Deep-dive: `dlc1_load_mp.ff` (representative `_load_mp` zone)
Full OAT asset list:
```
keyvaluepairs, dlc1_load_mp          <- the payload: ipak mount directives
techniqueset,  trivial_9z33feqw      <- 2D unlit textured-quad + its VS/PS
image+material, loadscreen_mp_downhill
image+material, loadscreen_mp_hydro
image+material, loadscreen_mp_mirage
image+material, loadscreen_mp_skate
image+material, loadscreen_transit_dr_returned_diner   (zm variant)
rawfile, dlc1_load_mp                 <- empty (0 bytes)
```
The KeyValuePairs asset reconstructs (via OAT) as:
```
>level.ipak_read, dlc1_load_mp
>level.ipak_read, base
>level.ipak_read, lowmip
>level.ipak_read, dlc1
```
→ loading this zone MOUNTS `base`/`lowmip`/`dlc1` ipaks. **This is the mechanism that wires
the DLC1 maps' streamed textures to `dlc1.ipak`.** The image+material pairs are per-map
loadscreen previews (trivial fullscreen quad, one `colorMap`); the images are streamed stubs
(pixels in `dlc1.ipak`, all 4 confirmed by hash).

- It is **NOT** a menu-registration zone (no `mapsTable`/menu asset; that lives elsewhere).
- It is **NOT** a `common_mp`-style content zone (zero gameplay assets).
- It IS a per-pack frontend preload: ipak-mount manifest + loadscreen art.

Pack→map falls out of the loadscreen list: **dlc1 = downhill, hydro, mirage, skate** (+ zm
transit variant), independently confirming mp_skate→dlc1.

Why dlc1 has no `_load_` ipak but dlc0 does: dlc1's loadscreens stream from the mounted
`dlc1.ipak`; dlc0 carries a 688 KB self-contained load ipak holding only
`loadscreen_mp_nuketown_2020` so the preorder-bonus screen shows before the 102 MB `dlc0.ipak`
mounts. Irrelevant to Wii U (ships Nuketown 2020).

**Convert a loadscreen zone:** rewrite the KVP mounted-pak name to the Wii U pak + push the
loadscreen images through the existing `ipak_stream` pipeline. No gameplay content to port.

## zm `_load_zm` zones — richer than mp
Same skeleton (keyvaluepairs mount + trivial techset + streamed image/material pairs + rawfile)
but they carry TWO extra things mp load zones don't:
1. **Zombies map-select menu art** — `menu_zm_map_<X>` image/material sets: a large thumbnail,
   a `_blur` version, and `_blit_<region>` sub-region images for the ZM map-selection UI.
2. **A load soundbank** — `soundbank, zmb_<X>_load.all` (menu/load stinger).
Plus the usual per-map `loadscreen_*` images. All images are streamed stubs.

KVP mount naming quirk: the ff is `dlcN_load_zm` but it mounts **`dlczmN`** (e.g.
`dlc3_load_zm` → `>level.ipak_read dlczm3`). The bonus `dlczm0_load_zm` mounts `dlczm0` and,
like dlc0 (mp), carries its OWN self-contained load ipak (`dlczm0_load_zm.ipak`, 4 entries =
its 1 loadscreen + 3 menu images) so Nuketown-Zombies frontend art shows before the big
`dlczm0.ipak` mounts. dlc1-4_load_zm have no load ipak (art streams from the mounted dlczmN).

**zm pack → map (from the loadscreen/menu names + mounts):**
| load ff          | mounts   | map        | (DLC)            |
|------------------|----------|------------|------------------|
| dlczm0_load_zm   | dlczm0   | zm_nuked   | Nuketown Zombies |
| dlc1_load_zm     | dlczm1   | zm_highrise| Die Rise         |
| dlc2_load_zm     | dlczm2   | zm_prison  | Mob of the Dead  |
| dlc3_load_zm     | dlczm3   | zm_buried  | Buried           |
| dlc4_load_zm     | dlczm4   | zm_tomb    | Origins          |

Note: still no `mapsTable`/menu-registry asset here (that's separate) — but unlike the mp load
zones, the zm load zone DOES supply the map-select menu imagery + a load soundbank, so a zm DLC
port needs those converted too (menu images + soundbank via existing SAB path), not just a
loadscreen.

## Reproduce / find a map's dlcN pack
```python
import wiiu_ref.ipak as ip, wiiu_ref.pc_image_enum as pe
paks={n:set(e.name_hash for e in ip.IPak.read(p).entries) for n,p in [
  ("base","…/base.ipak"),("mp","…/mp.ipak"),
  *[(f"dlc{i}",f"…/dlc{i}.ipak") for i in range(5)]]}
hs=set(pe.scan_pc_images(open("<map>.zone","rb").read()))
rem=set(hs)
for n,nh in paks.items():
    new=len(rem&nh); print(n,"covers",len(hs&nh),"new",new); rem-=nh
print("missing",len(rem))  # dominant dlcN = largest 'new'
```
(zm maps: use `dlczm0..4.ipak` in place of `dlc0..4`.)
