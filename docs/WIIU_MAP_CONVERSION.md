# Wii U Custom Map Conversion (Path B) — Status & Plan

> **Current state (2026-07-01).** The FBX→PC→Wii U pipeline below is built and hardware-proven through the
> data/geometry/collision tier. Two blockers named here are now resolved: the **block-policy/TEMP** crash
> (fixed via selective codegen remap + image-pixel strip) and the **MAP_ENTS type** ("cannot find BSP" was
> MAP_ENTS being emitted at the wrong console id — it is **id 47**). The remaining map-boot wall is **GSC**
> (map runs but is unscripted → black screen). Separately, geometry is now decoded (24-byte BE-float
> vertices; console `XSurface`=64B), and a **native unlinker** (`wiiu_ref/`) is the current focus for true
> unlink/relink. Live roadmap: **[NEXT_STEPS.md](NEXT_STEPS.md)**.

Goal: make the **T6 Custom Map Tool** produce a **Wii U-usable map `.ff`** from an FBX.

The tool's `Linker.exe` is a **closed-source PC-only OpenAssetTools fork** (verified: its binary
contains `custom_map` and `map_gfx.fbx`; base OAT has **no** FBX/GfxWorld/clipMap authoring). So we
**keep the closed Linker for FBX→geometry** and **convert its PC output to Wii U** with our extended
OAT + `ff_pack.py`.

```
FBX ──[closed Linker.exe]──► PC map .ff (v147 LE)
   ──[our OAT: load PC, write BE v148]──► raw BE v148 zone   (byte-swap + PC→console enum remap)
   ──[ff_pack.py]──► Wii U .ff (v148, WiiU key, 0x8000 zlib chunks)
```

Invoke:
```bash
# in tools/ref_oat/build/bin/Release_x64
OAT_IGNORE_SIG=1 OAT_REWRITE=1 OAT_WRITE_WIIU=1 ./Unlinker.exe --list mymap.ff   # -> mymap_rewrite.ff (raw BE zone)
python <repo>/tools/ff_pack.py mymap_rewrite.ff mymap                            # -> Wii U .ff (internal name = mymap)
```
To target an existing map slot (so it launches from the menu without a custom `map` command), build
the map in the tool **under that map's name** (e.g. `mp_raid`) so all assets are named
`maps/mp/<name>.*`, then replace the stock `<name>.ff`.

---

## What a custom map `.ff` contains (34 assets / 13 types)

| Type | Count | Conversion tier |
|---|---|---|
| SCRIPTPARSETREE (GSC) | 6 | data*; PC-compiled bytecode (console VM may differ) |
| RAWFILE | 1 | data (trivial) |
| MAP_ENTS | 1 | data |
| FOOTSTEP_TABLE | 6 | data |
| GAMEWORLD_MP | 1 | data |
| COMWORLD | 1 | data |
| CLIPMAP_PVS | 1 | data (collision) |
| IMAGE | 6 | header-only — pixels stream from IPAK (already working) |
| MATERIAL | 6 → 2 unique | data + refs |
| TECHNIQUE_SET | 2 | **GPU** — PC shaders; reference from base game on Wii U |
| XMODEL (skybox) | 1 | **GPU geometry** (Latte re-encode) |
| GFXWORLD | 1 | **GPU geometry** (Latte re-encode) |
| SKINNEDVERTS | 1 | **GPU geometry** |

\* The byte-swap/enum/pointer serialization of all 13 types is validated (see below); the *content*
of the GPU types still needs Latte conversion.

---

## What works (validated this session)

1. **OAT loads the closed tool's PC `.ff` fully** — all 34 assets, 0 errors (only the zeroed RSA
   signature stopped it, handled by `OAT_IGNORE_SIG`).
2. **OAT writes a structurally correct big-endian v148 zone** — header/blocks byte-flipped exactly,
   console-remapped asset enum, strings intact; packs to `TAff0100`/v148; **round-trips
   byte-identical** through decrypt.
3. **The BE serialization is provably correct** — a PC-policy BE zone loads back through OAT with **0
   errors** (all assets, incl. gfxworld/xmodel/clipmap). Byte-swap, enum remap, and pointer encoding
   are all right.

So the converter's *core* is done and correct.

---

## The wall: block policy (this is what crashes on hardware)

Comparing the **same map (`mp_dockside`) across PC, Xbox 360, and Wii U**, and TEMP across 8 genuine
Wii U zones:

| Block | PC | Xbox 360 | Wii U |
|---|---|---|---|
| **TEMP** | **0xc00478 (12.6 MB)** | **0x12ac** | **0x12ac** (constant across all maps) |
| RUNTIME_PHYS | 0 | 0x900000 | 0xc60000 (constant; GPU scratch) |
| VIRTUAL | 129 MB | 55 MB | 82 MB |

**PC dumps persistent asset data into the file-backed TEMP block; both consoles keep TEMP tiny and
place it in VIRTUAL.** Our converter inherits PC policy → ~6 MB in TEMP → overflows the Wii U
loader's fixed ~4.7 KB TEMP buffer → **crash on the first `0x80000` super-block.** Confirmed on
hardware: the engine opens `mp_raid.ff`, reads exactly one super-block, then dies — every time,
independent of other variables.

### Why the obvious fix doesn't work
A blanket "redirect TEMP allocations to VIRTUAL" remap (env `OAT_WIIU_BLOCKREMAP`) produces the right
*block shape* but **corrupts back-reference/alias pointers**. OAT loads 32-bit console zones into a
64-bit host by relocating pointer arrays **out-of-block** (tracked via an alias table) and keeps that
region *separate* from the main block data. Merging TEMP into VIRTUAL collapses that separation, so
in-block (writer) offsets and out-of-block (64-bit loader) offsets drift apart (~0x5000), and aliased
pointers resolve to the wrong place. Traced precisely via `OAT_DBG_ALIAS`: a pointer references
VIRTUAL `0x70f0` but its target array was placed at `0x76xxx`. **The remap is a dead end.**

---

## The fix (two viable approaches)

**Option 1 — native console block assignment (codegen).** Add conditional-`set block` support to
OAT's ZoneCodeGenerator so every T6 asset's default block can be `VIRTUAL` for console targets where
it is `TEMP` for PC, then regenerate. All offsets are then computed on one consistent basis — no
remap, no alias drift. Correct and general; real work inside ZoneCodeGenerator.

**Option 2 — metadata-only relocation (recommended next).** Keep OAT's correct PC-policy output
untouched; in a post-pass rewrite **only**: (a) the header block sizes (TEMP→`0x12ac`-ish, VIRTUAL
absorbs it, set the fixed `RT_PHYSICAL` reservation), and (b) the explicit **back-reference block
tags** (block 0 → block 5). "Follows-inline" pointers need no change — the Wii U loader's own
PushBlock sequence assigns them to VIRTUAL. The hard part is computing relocated back-ref *offsets*,
which means partially simulating the console loader's block accumulation. Lighter than Option 1 and
reuses the validated serializer.

Either way, after the block wall comes the **GPU asset wall**.

---

## The GPU wall (behind the block wall)

Empirically (PC vs 360 vs Wii U), console vertex buffers are **32 bytes/vertex like PC** but **not
the same byte layout** — position floats exist but packed differently (Latte attribute order). So
`GfxWorld` / `XModel` / `SkinnedVerts` vertices need **per-vertex re-encoding**, and the 2 generic
`TechniqueSet`s (PC D3D shaders) should be **referenced from the Wii U base game** rather than
shipped. Textures are already solved (IPAK). The exact Wii U vertex layout still needs to be decoded
from a genuine Wii U `GfxWorld` (now possible — OAT reads Wii U zones).

---

## Open items
- [ ] Block-policy relocation (Option 2 recommended) — unblocks loading.
- [ ] Decode exact Wii U `GfxPackedVertex`/`XSurface` byte layout from a genuine zone.
- [ ] Geometry re-encoder PC→Latte; reference base-game techsets/materials.
- [ ] Confirm GSC bytecode compatibility (PC VM vs console VM).
