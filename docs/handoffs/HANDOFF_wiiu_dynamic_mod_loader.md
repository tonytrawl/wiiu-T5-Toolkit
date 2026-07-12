# HANDOFF — Wii U dynamic mod loader (Plutonium-style) for T6

Session start doc. Written 2026-07-10. This is a **new, self-contained sub-project**, separate
from the DLC-map-loading effort. Read `FINDINGS_plutonium_mod_loading.md` first (same folder) —
it is the research this builds on. Read this doc for the goal, architecture, and the exact
milestone order.

---

## The goal (do not let it drift)

Build a **generic, dynamic mod loader** on the Wii U T6 build, functionally equivalent to
Plutonium's PC mod menu:

- Ship **one** menu ff, once. From then on it **scans the SD card**, discovers **whatever**
  `.ff`s the user has dropped there, **auto-builds menu entries**, and **loads a selected mod on
  demand**.
- The engine is **never told in advance** what mods exist. The base game is **never re-modified
  per-mod**. Users add/remove mods just by changing files on the SD.

### Explicit scope decisions (locked by the user — do not reopen)
- **Mod sourcing/format is the USER's responsibility.** The loader does **no** validation, format
  detection, or conversion. If a user drops a wrong-platform / PC-format / corrupt ff and it
  crashes, that is user error and out of scope. Do not build a validation or conversion layer.
- This is **NOT** the DLC/mapsTable static-registration path. A hardcoded catalog defeats the
  entire purpose. The whole value is *dynamic discovery of arbitrary ffs*.
- Target platform for development = **Cemu** first (as with the rest of the project), then real
  hardware. On Cemu the SD is an emulated host folder; on real HW it's `/vol/external01/`.

---

## The one load-bearing fact that shapes everything

**An `.ff` carries assets (data), never engine code.** Therefore the project is fundamentally a
**native-code (RPL patch) project**, not an ff project. Split:

- **Layer A — the ff (small, static, ship once):** the Mods menu LUI + the MainLobby "MODS"
  button + strings. It is *generic* — it only calls `GetModCount` / `GetModInfo` / `loadmod` and
  knows nothing about any specific mod.
- **Layer B — the RPL patch (this IS the product):** the discovery + search-path + mount
  machinery. Same class of work as the already-proven **sig-bypass** (`wiiu-sig-bypass`,
  `wiiu_ref/rpl_sigpatch.py`) and **DLC-gate** (`wiiu_ref/rpl_dlcgate_patch.py`) patches — just
  larger.

---

## Architecture

### Layer A — what to bake into the menu ff
All must be Wii-U-format (v148 BE, WiiU Salsa key) via the existing converter pipeline.

| Asset | Type | Purpose |
|-------|------|---------|
| `ui/t6/mods.lua` (new) | `rawfile` (compiled HKS bytecode) | the Mods menu |
| `ui/t6/mainlobby.lua` (override) | `rawfile` | adds "MODS" button + `open_mods_menu` handler |
| any changed `require`d files | `rawfile` | only if you touch them |
| `"MODS"` + labels | `localizedstring` / stringtable | so `Engine.Localize("MODS")` resolves |

- **Reference source for the menu logic:** the PC Plutonium `.lua` at
  `C:\Users\Tony - Main Rig\AppData\Local\Plutonium\storage\t6\raw\ui\t6\mods.lua` and
  `...\raw\ui\t6\mainlobby.lua`. `mods.lua` uses only stock LUI surface
  (`LUI.UIVerticalList`, `CoD.Menu`, `CoD.ListBox`, `CoD.ButtonList`) plus the three
  Plutonium bindings. MainLobby adds the button at ~line 433/465 and the
  `open_mods_menu`→`OpenModsList` handler at ~line 747/830.
- **Confirmed:** T6 stores LUI as `rawfile` assets keyed by `.lua` path (verified — a stock
  zone contains strings like `mp/T6/Menus/CheckClasses.lua`).
- **Sub-task (real work):** console rawfiles are **precompiled HKS (Havok Script) bytecode**,
  not source. You need an HKS/Lua compiler step in the pipeline to turn the `.lua` source into
  console-loadable bytecode. This does not exist in the pipeline yet.

### Layer B — what the RPL patch must provide (none of this can be an asset)
1. `Engine.GetModCount()` / `Engine.GetModInfo(i)` — new **Lua→engine bindings** registered into
   the LUI VM. `GetModInfo` returns `{ modname, name, author, description, version }` read from
   each mod's manifest (a `description.txt`-style file in the mod folder; absent → blank fields).
2. The `loadmod <name>` **console command** (and `loadmod ""` to unload).
3. **SD-card folder enumeration** — list mod subfolders + read their manifests.
4. **Search-path / mount** — see the recommended primitive below.

### Recommended primitive — replicate `fs_game` search-path shadowing
Plutonium rides the **stock idTech `fs_game`** mechanism, not a bespoke mounter. Do the same:
- `loadmod X` sets the search path to the SD mod folder and triggers the **normal** zone load
  for that name; the mod ff's assets **shadow the base by name**.
- This is less new code than a custom zone-injector **and** it is what makes a mod able to
  *modify* (not just add) content — a same-named asset shadow replaces a weapon tune, menu,
  script, material, etc.
- The stock `fs_game`/search-path code very likely exists in the Wii U RPL but is wired to
  disc/ipak; the patch's job is to (a) add the SD dir to the search path and (b) expose
  `loadmod`. Confirm by RE of the RPL's filesystem/`fs_game` code.

### SD path
- Real HW (Aroma/Tiramisu): `/vol/external01/wiiu/t6/mods/<name>/<name>.ff` (+ optional
  `description.txt`). Cemu: the emulated-SD host folder mapping to the same relative path.
- The RPL enumerator opens that dir via the IOSU/FS layer, lists entries, reads manifests.

---

## THE go/no-go gate (do this first, before any UI work)

**Question:** does a later-loaded/searched ff **override an already-loaded base asset by name**
on console? The entire "add features/content without modifying the base game" premise rests on
this. It is currently an **unverified assumption** (called out as the §4 experiment in the
findings doc).

**Cheap test:** take a stock console zone that already boots on Cemu (e.g. a DLC frontend/
loadzone that renders — see `dlc-loadzone-native`, `batch_loadzones.py`). Author a tiny second
zone loaded *after* it containing **one** asset with the **same name** but altered content — the
safest probe is a **localizedstring** or a **material** already visible on screen (e.g. a menu
title). Mount it via the existing ipak/loadzone path. Observe:
- on-screen value changes → **name-shadow works on console** → the generic-override model is
  valid; proceed.
- no change / earlier load wins → override is **add-only**; the model must change (mods could
  only add assets, not modify existing ones) — escalate this finding before building further.

Reuse `native_linker/batch_loadzones.py` + the ipak mount trick; no new engine RE needed for the
test itself.

---

## Milestones (strict dependency order)

1. **Name-shadow test** (above). Go/no-go for the whole concept. Small.
2. **RPL: mount ONE hardcoded SD ff** via a repointed search path. No menu, no scan — just prove
   the engine will load an arbitrary Wii-U-format ff from `/vol/external01/...` on command.
3. **RPL: the scan + `GetModCount`/`GetModInfo` bindings** — turn the hardcode into a real folder
   enumeration with manifests, exposed to the LUI VM.
4. **Ship the generic menu ff** wired to those bindings (requires the HKS/Lua compile step for
   console LUI in Layer A).

Milestones 1–2 are small and de-risk the entire concept before any UI investment. Do not build
the menu ff until 1 passes and 2 works.

---

## Constraints / guardrails
- **Read-only against the Plutonium install** at
  `C:\Users\Tony - Main Rig\AppData\Local\Plutonium\storage\t6` — it is reference only.
- The user's `mods/mp_peach` and `mods/test` there are **self-placed test payloads**, NOT part
  of the mechanism — ignore them.
- Do **not** edit `native_linker/` or `wiiu_ref/` code if an assemble session is active in them;
  new scratch scripts go in a new folder. Never write under `E:\`.
- Do **not** re-introduce a format-validation or PC→WiiU auto-conversion layer into the loader —
  explicitly out of scope per the user.

---

---

## RPL RE — the raw-`.lua`-from-disk hook (done 2026-07-10, evidence-backed)

Goal of this track: patch the game RPL so LUI loads loose `.lua` from disk instead of requiring
them baked into an ff. **The exact hook point is now found and the mechanism is proven feasible.**

### RPL facts
- Binary: `wiiu_ref/t6mp_cafef_rpl.rpl` — a **symbolized** Wii U ELF/RPL (`.symtab`+`.strtab`
  present, 174,104 symbols). Sections are zlib-compressed (`sh_flags & 0x08000000`, 4-byte
  uncompressed-size prefix). `.text` @ VA `0x02000000`, size `0xafede0`.
- Reusable disassembler written this session: scratchpad `rpldis2.py` (capstone PPC32 BE, resolves
  `bl` targets + rodata string refs). `rpl_sigpatch.py` already has the section decomp/recomp.

### The load chain (fully traced)
```
Lua require(name)
  → __package_require (0x02839c10)
  → hksL_loadfile (0x027dc8bc)         ← 4-byte STUB: just `b hksL_loadfile_FastFile`
  → hksL_loadfile_FastFile (0x027dc708)
        → LUI_CoD_GetRawFile(name)  (0x02884ed0)   ← THE CHOKEPOINT
              → DB_FindXAssetHeader(type=0x2a RAWFILE, name)  (0x0222aae0)
        → hks Compiler (0x027d8738)   ← compiles the bytes (SOURCE or bytecode both work)
```
Two important consequences:
1. **`LUI_CoD_GetRawFile` @ `0x02884ed0` is a single chokepoint** — *every* `.lua` load funnels
   through it. Hook this one function and all LUI raw-file loading gains disk support.
   - Signature: `RawFile* LUI_CoD_GetRawFile(const char* name)`. It lowercases `name` into a
     stack buffer, calls `DB_FindXAssetHeader(0x2a, name, ...)`, returns the header (or NULL).
     T6 `RawFile` struct = `{ const char* name; int len; const char* buffer; ... }`.
2. **The HKS Compiler is linked and called in this path**, so loose **source** `.lua` compiles at
   runtime — the console is NOT limited to precompiled bytecode for LUI. (Earlier hedge retracted:
   this is confirmed by the `Compiler__3hks...` call inside `hksL_loadfile_FastFile`.)

### The FS primitives (already present, already used for saves)
- `FS_ReadFile` @ `0x024dd0c8` — `int FS_ReadFile(const char* name, void** buf)`: builds an OS path
  via `Sys_DefaultInstallPath` + `FS_BuildOSPathForThread`, opens `FS_FileOpenReadBinary`, gets
  size, `Z_VirtualAllocInternal`s a buffer, `FS_FileRead`s, closes, returns size. **This is a
  ready-made "read a whole file from disk into a buffer" call** the hook can just invoke.
- Root path = `Sys_DefaultInstallPath` → on console = **`/vol/content`** (the disc). SD
  (`/vol/external01`) is NOT referenced anywhere in the RPL.
  - **Cemu dev shortcut:** `/vol/content` maps to the game's content folder, which is writable on
    the host — so on Cemu you can drop loose `.lua` there and `FS_ReadFile` reads them with **no
    path redirect at all**. Real hardware needs an SD redirect (build path to `/vol/external01/…`
    via `FS_FileOpenReadBinary` directly, bypassing `Sys_DefaultInstallPath`).

### The patch (concrete design)
Hook `LUI_CoD_GetRawFile` so it tries disk first, falls back to the DB:
```c
RawFile* LUI_CoD_GetRawFile_hook(const char* name) {
    void* buf = 0;
    int len = FS_ReadFile(name, &buf);          // 0x024dd0c8 ; /vol/content/<name> (Cemu: works as-is)
    if (len > 0 && buf) {
        RawFile* rf = alloc();                   // static/scratch RawFile
        rf->name = name; rf->len = len; rf->buffer = buf;
        return rf;                               // shadow: disk wins
    }
    return DB_FindXAssetHeader(0x2a, name, ...); // 0x0222aae0 ; original behavior
}
```
~30–40 PPC instructions. Then repoint the entry (or the call site at `0x027dc74c` inside
`hksL_loadfile_FastFile`) to the hook.

### The one blocker for building it: no code cave
`.text` has **no zero-run ≥ 0x40** — it is fully packed, so there's nowhere to drop new code
in-place. Options, easiest first:
1. **Cemu code patch (recommended for dev):** target Cemu with a runtime `patches.txt`
   (Cemuhook/Cemu graphic-pack patch) — inject the hook as a runtime code patch; **no RPL repack
   needed** to prototype. Fastest iteration loop and matches the project's Cemu-first target.
2. **Repurpose a dead function** as a cave (a dev-only/never-called routine) and redirect to it.
3. **Extend `.text`** via the RPL toolchain (relocation-heavy; `rpl_sigpatch.py` already
   decompresses/recompresses `.text`, so the plumbing exists, but adding executable space is more
   work than 1–2).

### Revised milestone 2 (supersedes the generic one above for the LUI track)
1. **Cemu, no patch:** confirm whether dropping a loose file under `/vol/content` and forcing a DB
   miss does anything (it won't load yet — GetRawFile doesn't fall through — but confirms the
   content-dir mapping and that FS reads there).
2. **Cemu code patch:** implement `LUI_CoD_GetRawFile_hook` as a Cemuhook `patches.txt` code patch
   calling `FS_ReadFile` → build RawFile → else `DB_FindXAssetHeader`. Drop a modified
   `ui/t6/mainlobby.lua` (or a tiny test `.lua`) on disk and confirm it loads over the baked one.
   **This is the real go/no-go for the loose-raw path** and needs no ff work or name-shadow zone.
3. Only then port the patch into a repacked RPL (cave/extend) for real-hardware use, and add the
   SD (`/vol/external01`) redirect.

### Honesty / open items
- The `RawFile` struct layout (`{name,len,buffer}`) is the known T6 shape but should be confirmed
  against how `hksL_loadfile_FastFile` reads the returned header (fields at which offsets) before
  trusting the hook's writes. Disassembly of `hksL_loadfile_FastFile` body around `0x027dc74c`+
  will show the exact field offsets it dereferences.
- GSC (not LUI) has a *separate* chain (`Scr_LoadScript`/`GScr_LoadGameTypeScript`, ScriptParseTree
  DB) and **no confirmed runtime GSC compiler** — the LUI result here does NOT automatically extend
  to loose `.gsc`. Treat GSC as a separate investigation.
- `FS_ReadFile`'s arg contract (`(name, void** buf)` returning size) is inferred from its
  disassembly (calls FileOpen→GetSize→VirtualAlloc→FileRead→Close); confirm register usage before
  wiring.

## Key references
- `FINDINGS_plutonium_mod_loading.md` — the full mechanism research + classification (a)/(b)/(c).
- Plutonium `raw/ui/t6/mods.lua`, `raw/ui/t6/mainlobby.lua`, `raw/scripts/mp/ranked.gsc` — the
  PC-side source to port/imitate.
- `tools/ff_decrypt.py` — decrypts PC (v147) and Wii U (v148) ffs to `.zone` (used read-only here).
- Memories: `wiiu-sig-bypass`, `wiiu-map-menu-registry`, `dlc-loadzone-native`,
  `dlc-ipak-partition` (RPL-patch + mount infrastructure precedents).
- `PROJECT_STATE.md` — master project index (the *other*, separate effort).
