# Wii U T6 Toolkit — PC → Wii U (Black Ops II) map conversion

A shareable snapshot of the tools for converting **PC (Plutonium/T6) Black Ops II** fastfiles into
**Wii U (v148)** fastfiles + ipaks. Code and documentation only — **no game data is included** (see
"What you supply" below).

> This is a code/docs snapshot for collaborators. It intentionally excludes internal working notes,
> build artifacts, and any copyrighted game content (zones, fastfiles, ipaks, RPLs).

## Layout
```
native_linker/     the from-scratch PC→console converters + zone walker + assembler (Python)
wiiu_ref/          Wii U format probes, GX2 texture tiling, ipak authoring, techset tools (Python)
                   + *_findings.md mechanism notes (how each format works)
tools/
  ff_decrypt.py    decrypt/decompress any T6 fastfile (PC v147 / WiiU v148 / X360 v146)
  salsa20.py       stream cipher used by the fastfile format
  ref_oat/src/     the EXTENDED OpenAssetTools source (our Wii U console read/write additions)
WiiU_FF_Studio/    the desktop GUI (tkinter) for the flat conversions + console tools
docs/              format / reverse-engineering findings (how the conversion works)
```

## Components

### `native_linker/` — the native conversion pipeline
Converts PC zone assets to Wii U console layout, byte-validated against genuine console zones as an
oracle. Key modules:
- `pc_convert_pipeline.py` — end-to-end orchestrator (unlink → convert → repack → author ipak). Also
  what the GUI calls.
- `pc_zone.py` / `zone_stream.py` — PC (LE) zone reader / console (BE) block-stream writer.
- `pc_walk.py` — the asset dispatcher that walks a PC map zone end-to-end (routes each asset type to
  its per-type probe/consumer).
- Per-type converters: `material_convert.py`, `xmodel_convert.py`, `fx_convert.py`,
  `techset_translate.py` (genuine-console substitution), `pc_to_console.py` (simple/world types),
  and the GfxWorld set (`gfxworld_*.py` — body/dynamics/geometry).
- `*_pc.py` — PC-side span/extent parsers used by the walker.
- `validate_*.py` — matched-pair oracle harnesses (convert PC body, diff vs genuine console).

### `wiiu_ref/` — Wii U format primitives
- `gx2_texture.py` — full Latte GX2 tile/detile (2D + cube faces).
- `ipak.py` / `ipak_stream.py` — read/author Wii U ipaks; pull PC image sources by name-hash.
- `pc_image_enum.py` — enumerate a PC zone's GfxImages.
- `gfxworld_probe2.py`, `xmodel_probe.py`, `shader_probe.py`, etc. — both-platform structure probes.
- `rpl_sigpatch.py` — patch a T6 engine RPL to load custom (zeroed-signature) fastfiles.
- `*_findings.md` — the mechanism notes for each area (read these to understand the formats).

### `tools/ref_oat/src/` — extended OpenAssetTools
The upstream OAT unlinker/linker with **added Wii U console read + write paths** (T6). Our additions
of interest: `ZoneWriting/Game/T6/ConsoleWriterT6.{h,cpp}`, `ConsoleSiegeSkinTail.h`,
`ZoneLoading/.../*console*`. Build with the upstream OAT toolchain (premake/VS); the generated
`build/` tree and codegen output are regenerable and were excluded from this snapshot.

### `WiiU_FF_Studio/` — desktop GUI
tkinter front-end (pure stdlib, freezes to a single EXE). Pages: fastfile↔zone, batch convert,
PC-fastfile → Wii U + ipak pipeline, zone inspect/validate/edit, RPL signature patch. See its
`README.md` / `USAGE.md`.

## Requirements
- **Python 3.10+** for the tools (`native_linker`, `wiiu_ref`, `tools`, the GUI). The GUI is
  stdlib-only; some `wiiu_ref` RE helpers use `capstone` (only where noted).
- **A C++ toolchain** (the OAT upstream build setup) if you want to build `ref_oat`.

## What you supply (not in this snapshot)
The tools operate on game data you dump yourself — none is included:
- PC T6 zone/fastfile set (e.g. a Plutonium install) for the source maps + `base`/`mp`/`dlcN` ipaks.
- Genuine Wii U T6 fastfiles for the console oracles / reference (validation + asset reuse).
Point the tools at your own copies. **Do not commit game content into this toolkit.**

## Quick start
```bash
# decrypt a PC fastfile to its raw zone
python tools/ff_decrypt.py <map.ff> <out.zone>

# end-to-end: PC fastfile -> Wii U fastfile + ipak  (see the module header for options)
python native_linker/pc_convert_pipeline.py <pc_map.ff> <out_dir> [--console-ref <wiiu .ff/.zone>]

# author a Wii U ipak from a PC map's images
python wiiu_ref/pc_image_enum.py <pc_map.zone> <meta_dir>
python wiiu_ref/ipak_stream.py prepare <meta_dir> <out_dir> --ipak <map>.ipak --pc-ipaks <base.ipak> <mp.ipak> <dlcN.ipak>

# or launch the GUI
python WiiU_FF_Studio/wiiu_ff_studio.py
```

## How it works (docs)
Start with `docs/WIIU_MAP_CONVERSION.md`, then the format findings in `docs/` and the `*_findings.md`
notes under `wiiu_ref/`. Each converter's module header documents its layout map and validation.

## Current state — honest, per component
Status legend: ✅ built & validated · 🟡 partial / WIP · ⬜ not built. "Byte-exact" = output matches a
genuine console asset byte-for-byte (matched-pair oracle). "HW-confirmed" = loaded/rendered correctly
on Cemu.

### Fastfile I/O & console tooling
| Tool | State | Truth |
|---|---|---|
| `tools/ff_decrypt.py` | ✅ | Decrypts PC v147 / WiiU v148 / X360 v146. Solid. |
| `WiiU_FF_Studio` pack/decrypt | ✅ | WiiU v148 pack is **boot-confirmed**; flat conversions (ff↔zone, batch) work. |
| `wiiu_ref/rpl_sigpatch.py` | ✅ | Reproduces the installed working RPLs byte-exact; custom (zeroed-sig) ffs load. |
| `WiiU_FF_Studio` pipeline page | 🟡 | Wraps `native_linker` pipeline — inherits its state below (bootable only with a console backbone). |

### Geometry & GfxWorld
| Tool | State | Truth |
|---|---|---|
| GfxWorld geometry (`gfxworld_dynamics/assemble`) | ✅ HW-confirmed | vd0 (group-aware 36B), vd1 (swap2), indices, surfaces + material-ptr relocation render correct on Cemu. Offset = stored `vertexDataOffset0` (no console reorder). |
| GfxWorld body/dynamics | ✅ HW-confirmed | Body + all dynamic regions convert; validated vs oracle. |
| Lighting exactness | 🟡 | Tangent + vd1 second-UV are console-repacked → map renders slightly darker (cosmetic; geometry unaffected). |
| No-backbone region generators (`gfxworld` novel synthesis) | 🟡 WIP | The console-only regions for a map with no console counterpart. Breakdown: ~7.2 MB GX2 textures (existing image pipeline, cubemaps verified 6/6), ~4.2 MB PC-sourced bounded conversions, **~90 KB genuinely-new synthesis** (streamInfo / sortedSurfIndex / smodelCastsShadow). In progress. |

### Per-asset converters (`native_linker`)
| Tool | State | Truth |
|---|---|---|
| `material_convert.py` | ✅ | 437/446 byte-exact (the 9 differ by 2 bytes in a sort hash — low-impact, loadable). Console Material = 104 B. |
| `xmodel_convert.py` (rigid) | ✅ | body+bones+surfaces(128B)+materialHandles+collSurfs+boneInfo+physPreset; full driver 186/0 clean resync. |
| `xmodel_convert.py` inline-material **image** emission | 🟡 REQUIRED, WIP | Emits material handles but **not the inline GfxImage pixels** → bodies are truncated → **not yet loadable** for maps with inline models (mp_skate has 466 inline XModels). Wiring the existing GX2 image path into the inline-material branch; not new RE. |
| `xmodel_convert.py` skinned surfaces | ⬜ | `vertsBlend` swaps cleanly, but the 3 Latte skin-streams are **not derivable from PC data** (confirmed independently by OAT). Plan: emit rigid (stream-valid, bind-pose) + loader-tolerance test; real synthesis is a later item. Blocks zombies characters/weapons. |
| `xmodel_convert.py` collmaps chain | ⬜ | 109/465 models; collision, deferrable past a first render. |
| `fx_convert.py` | 🟡 | FxEffectDef header 388/388 byte-exact; the FxElemDef body/curve tail is not yet wired. |
| `techset_translate.py` | ✅ (substitution) | Substitutes a genuine console techset per PC techset via **name grammar**; mp_skate = 0 unresolved (202 exact + 34 struct + 5 prefix). Not byte-identical (it's a valid *substitute* console shader, not a transcode). D3D→GX2 shader recompilation is intentionally NOT done. |
| `pc_to_console.py` (simple/world) | ✅ | StringTable/KVP/RawFile/… + ComWorld/MapEnts/GameWorldMp/clipMap byte-exact. |
| `sndbank_pc.py` | ✅ (span) | PC SndBank is byte-identical to WiiU → byte-copy; walker sizes it correctly. |
| `validate_*.py` | ✅ | Matched-pair oracle harnesses; the discipline behind every "byte-exact" claim above. |

### Walk / images / assemble
| Tool | State | Truth |
|---|---|---|
| `pc_walk.py` (zone traversal) | ✅ / ⬜ | Reaches **end-of-zone on mp_skate (840) + raid**. **WEAPON consumer not built** → blocks any map with inline weapons (nuketown MP + all ZM maps, ~100/zm map). |
| `pc_image_enum.py` + `ipak_stream.py` + `gx2_texture.py` | ✅ | Author a WiiU ipak from PC images; **byte-exact vs retail** (mp_la 287/287). GX2 tiling covers 2D + cube faces. |
| `dlc_packs.py` (DLC source auto-select) | ✅ | DLC maps stream from `dlcN`/`dlczmN.ipak`; auto-selects the right pack (mp_skate skips 397→7). |
| Asset-list authoring (`_assetlist_author.py`) | ✅ (foundation) | Console order + type remap byte-exact on 2 MP maps; string table reused verbatim; MP console-only inserts characterized. |
| `pc_convert_pipeline.py` (with console backbone) | ✅ | For a map that **exists on Wii U**, produces a bootable ff (backbone splice) + ipak. |
| No-backbone whole-zone assembler (`produce_nobackbone.py`) | 🟡 WIP | The path that authors a complete console zone from PC alone (the goal). Raid-oracle control runs; **not yet producing a bootable no-backbone ff** — gated on the XModel inline-image emission + region generators + assemble wiring above. |

### `tools/ref_oat/src` — extended OpenAssetTools
| | State | Truth |
|---|---|---|
| Console read/write (per-struct) | ✅ (byte oracle) | Emits/reads individual console asset structs — useful as a **byte reference** for validating the native converters. |
| Bootable output | ⚠️ **never** | OAT has **never produced a bootable Wii U ff** — it leaves dangling cross-asset world pointers on load (this is *why* the native `native_linker` pipeline exists). Do not treat OAT output as a working target; use it as a per-struct oracle only. |
| Techset write | ⬜ | Emits **null shader subtrees** (no D3D→GX2 transcode) — real shaders come from genuine-blob substitution. |
| "Siege-skin" work | ✅ (transplant) | `ConsoleSiegeSkinTail.h` is the GfxWorld GPU-skinning *shaders* transplanted verbatim — NOT the XModel skinned skin-streams (those remain unsolved, see above). |

### Bottom line
The scary reverse-engineering is done (geometry is HW-confirmed; every converter has an oracle). The
**one thing that makes a from-scratch, no-backbone map actually boot is not finished**: the whole-zone
no-backbone assembler, plus its two current prerequisites — **XModel inline-material image emission**
and the **GfxWorld region generators**. A map that already exists on Wii U can be converted bootably
today (backbone path); a brand-new map cannot yet. Skinned models and the WEAPON consumer are the
outstanding gates for the zombies tier.

## License / attribution
`tools/ref_oat` derives from OpenAssetTools (see its upstream license). The Wii U additions and the
`native_linker`/`wiiu_ref` tooling are this project's work. Game assets are the property of their
respective owners and are not included or redistributed here.
