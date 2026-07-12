# HANDOFF — Patch the T6 Wii U RPL to load raw `.lua` from disk

Session date 2026-07-10. Sub-project of the Wii U dynamic mod loader
(see `HANDOFF_wiiu_dynamic_mod_loader.md` + `FINDINGS_plutonium_mod_loading.md`).
**READ `FINDINGS_plutonium_mod_loading.md` FIRST** — the Plutonium mod-loading research
completed; it classifies which mechanisms are stock-T6 (portable) vs PC-only. This RPL patch
is the Wii U-side test of the class-(a) "loose raw file overrides the ff copy by name"
hypothesis — confirm the findings doc agrees that raw-file override is stock engine behavior
before investing in the repack.

## ⚠️ PRE-FLIGHT (main session, 2026-07-10)
- This is an INDEPENDENT test track — it does NOT touch `native_linker/`/`wiiu_ref/` source
  and does NOT gate the mp_skate boot. Safe to run alongside the active assemble session.
- Standing constraint reminder: **stage everything on C:; never write under `E:\`.** The user
  copies the finished patched RPL + `content\ui\t6\*.lua` into the E: install themselves.
- Scope note: an EXTRACTED dump + Cemu means `/vol/content` = the `content\` folder — no image
  edit. This test does NOT need the sig-bypass to be re-solved (it's proven); it needs the hook
  re-resolved on the correct RPL.

## Objective (locked)
Make the game load loose `.lua` files from disk, overriding the copies baked into the fastfiles,
so a Plutonium-style Mods menu (and any modded LUI) can be dropped on disk without rebuilding ffs.
**Decision this session: do it by PATCHING THE RPL directly** (repack a modified RPL), NOT via a
Cemu graphic-pack `patches.txt`. The graphic-pack files were drafted but the user chose the direct
RPL-patch path — treat the Cemu pack as reference only.

## ⚠️ CRITICAL CORRECTION — target RPL identity (VERIFIED by main session 2026-07-10)
All reverse-engineering below was done on `wiiu_ref/t6mp_cafef_rpl.rpl`
(md5 `0a176895f7cb20c0a84ffab5b6ba6d87`, size 9,134,016).
**The ACTUAL game RPL is different — confirmed by direct hash of the E: install:**
- Real target: `E:\Wii U Black ops 2\code\t6mp_cafef_rpl.rpl`
  **md5 `c2f6141eaac7e282b043d37833458ce8`, size 9,124,602** (MP) ✅ hash-verified
- Also present: `E:\Wii U Black ops 2\code\t6_cafef_rpl.rpl` (ZM, size 8,242,568) ✅ verified

Because the two MP RPLs differ (likely different TU/build), **every absolute address, the module
checksum, and the code-cave scan MUST be re-derived from the real `code\` copy before patching.**
The RE *method* and the *structure* (below) carry over; the *numbers* do not. Both RPLs are
symbolized (`.symtab`+`.strtab`), so re-resolving is just re-running the symbol lookup.

## What we know — the load chain (verified on the analyzed copy; re-resolve on real copy)
```
Lua require(name)
  → hksL_loadfile (4-byte stub: b hksL_loadfile_FastFile)
  → hksL_loadfile_FastFile
        → LUI_CoD_GetRawFile(name)         ← THE CHOKEPOINT (every .lua funnels here)
              → DB_FindXAssetHeader(type=0x2A RAWFILE, name)
        → hks Compiler                     ← compiles the returned bytes (SOURCE .lua works!)
```
Addresses **on the analyzed copy** (0a1768…) — re-verify names→addrs in the real RPL:
| symbol | analyzed-copy VA | notes |
|---|---|---|
| `LUI_CoD_GetRawFile(const char* name)` | `0x02884ED0` | returns `RawFile*` or NULL |
| `hksL_loadfile_FastFile` | `0x027DC708` | body |
| ↳ `bl LUI_CoD_GetRawFile` **call site** | `0x027DC74C` | **the instruction we repoint** |
| `LUI_CoD_FFReader` (lua_Reader) | `0x02884EA8` | reads `len@+4`, `buffer@+8` |
| `FS_ReadFile(r3=name, r4=&buf)->size` | `0x024DD0C8` | disk read; VirtualAllocs buf; Com_Errors only on empty name |
| `DB_FindXAssetHeader` | `0x0222AAE0` | fallback |

`RawFile` struct (confirmed via the reader): **`{ +0x00 char* name; +0x04 int len; +0x08 char* buffer }`**.

Two facts that make loose SOURCE `.lua` viable:
1. `LUI_CoD_GetRawFile` is a single chokepoint — hook it and all LUI raw loading gains disk support.
2. The HKS **Compiler is linked and invoked** in `hksL_loadfile_FastFile`, so disk *source* `.lua`
   compiles at runtime (not limited to precompiled bytecode).

## The patch design (structure is final; addresses to re-resolve)
Repoint the single `bl` at the GetRawFile call site to a code cave that tries disk first:
```c
RawFile* hook(const char* name){
    void* buf=0; int len=FS_ReadFile(name,&buf);      // /vol/content/<name>
    if(len>0 && buf){ RF.name=name; RF.len=len; RF.buffer=buf; return &RF; }  // disk shadows ff
    return LUI_CoD_GetRawFile(name);                   // untouched fallback
}
```
Validated hook = 37 PPC instrs, **0x88 bytes**, position-independent except the `RawFile` scratch
address (one `lis/ori` pair) and the two absolute call targets (`lis/ori/mtctr/bctrl`). Full
annotated source: `mod_loader_patch/bo2_rawlua_hook.S`. Assemble with keystone
(`Ks(KS_ARCH_PPC, KS_MODE_32|KS_MODE_BIG_ENDIAN)`; installed this session).

Call-site patch: replace `bl LUI_CoD_GetRawFile` at the call site with `bl <cave>`.

## The build path (RPL repack) — what to do next
1. **Re-derive on the real RPL** (`E:\...\code\t6mp_cafef_rpl.rpl`): parse `.symtab`, get the real
   VAs for the 6 symbols above; disassemble to confirm the call-site instruction and the reader
   field offsets still match (they should). Reuse scratch `rpldis2.py` (see below), just point it
   at the real file.
2. **Find space for the cave.** On the analyzed copy `.text` had **no zero-run ≥ 0x40** (no cave).
   Re-scan the real copy. If still none: either (a) repurpose a dead/dev function as the cave, or
   (b) extend `.text` / add a section. `wiiu_ref/rpl_sigpatch.py` already decompresses & recompresses
   `.text` sections (`sh_flags & 0x08000000`, 4-byte uncompressed-size prefix, zlib) — the plumbing
   to rewrite `.text` exists; growing it is the extra work.
3. **Place `RawFile` scratch** (12 bytes) at a fixed writable VA (a reserved `.data`/`.bss` slot),
   set the hook's `lis/ori` to it.
4. **Assemble + splice**: write the cave bytes, write the `bl <cave>` at the call site, recompress
   the section, fix the ELF/RPL section sizes.
5. **Signature**: a repacked RPL fails the signature check → apply the proven sig-bypass
   (`wiiu-sig-bypass`, `wiiu_ref/rpl_sigpatch.py`; also patch the update-partition RPLs so a
   zeroed-sig module loads). This is already CONFIRMED WORKING for repacked RPLs.
6. Drop the patched `t6mp_cafef_rpl.rpl` back into `E:\Wii U Black ops 2\code\` (see E: note) and
   boot.

## Disk / path facts (verified)
- `FS_ReadFile` root = `Sys_DefaultInstallPath` → **`/vol/content`** on console.
- The game at `E:\Wii U Black ops 2\` is an **EXTRACTED dump** (`code/ content/ meta/`), so
  `/vol/content` = the `content\` folder. Loose files can be dropped straight in — no image edit,
  no redirection.
- So a disk `.lua` goes at `E:\Wii U Black ops 2\content\ui\t6\<name>.lua`, and `FS_ReadFile("ui/t6/
  <name>.lua")` finds it. (Confirm the exact name the engine passes by dumping `r3` at the call
  site if the first test misses — could be `ui_mp/` prefixed or case-sensitive.)
- `/vol/external01` (SD) is NOT referenced by the RPL; irrelevant here since we use `/vol/content`
  on an extracted dump. (SD would matter only for real-hardware, not this Cemu/extracted setup.)

## Test content already prepared (in `mod_loader_patch/content_root/ui/t6/`)
- `mainlobby.lua` — PC-Plutonium main lobby (retains Wii U code paths) + a **MODS button**; two
  safety edits so it can't brick the lobby (`pcall(require,"T6.Mods")`, guarded `OpenModsList`).
- `mods.lua` — a **brand-new file that exists ONLY on disk** (never in any ff) → loading it is the
  end-to-end proof of the hook. Hardened: `CoD.BOIIOrange` fallback; `GetModCount/GetModInfo/
  loadmod` all guarded so it opens gracefully even though those bindings don't exist yet (it shows
  "bindings not installed — this menu loaded from disk = the hook works").
Copy these into `E:\Wii U Black ops 2\content\ui\t6\` when testing (see E: note).
Success = MODS button appears in the lobby. Full outcome table in `mod_loader_patch/FIRST_RUN.md`.

## Environment / constraints
- **`E:\` write block:** standing project instruction says never write under `E:\`. Both the game
  (`E:\Wii U Black ops 2`) and Cemu (`E:\Cemu_2.6`) are on E:. Get explicit user go-ahead before
  writing the patched RPL / content files to E:, or stage on C: and have the user copy.
- **Cemu:** `E:\Cemu_2.6` (Cemu 2.6). No `graphicPacks\` folder exists yet. `GAMES\` is empty; the
  game is loaded from `E:\Wii U Black ops 2\` (extracted). ZM disabled via `_dlc_zm_load_disabled`.
- Do **not** edit `native_linker/` or `wiiu_ref/` source if an assemble session is active; new
  scratch goes in a new folder. `rpl_sigpatch.py` is read-only reference for the section codec.
- Keystone (`keystone-engine`) is installed for PPC BE assembly.

## Scratch tooling made this session
- `<scratchpad>/rpldis2.py` — capstone PPC32-BE disassembler for the RPL: parses ELF sections,
  zlib-inflates `sh_flags&0x08000000` sections, builds addr→symbol from `.symtab`/`.strtab`,
  resolves `bl` targets + rodata string refs. Point it at the real RPL. (Prefer copying it into a
  new folder rather than leaving in scratch.)
- `mod_loader_patch/` — `bo2_rawlua_hook.S` (hook source of truth), `patches.txt`/`rules.txt`
  (Cemu-pack reference, deprioritized), `README.md`, `FIRST_RUN.md`, and the `content_root/` test
  LUI.

## Immediate next actions
1. Re-resolve the 6 symbol VAs + confirm call-site/reader on `E:\Wii U Black ops 2\code\t6mp_cafef_rpl.rpl`.
2. Cave scan on that RPL; pick cave + `RawFile` scratch VA.
3. Assemble hook for those VAs; splice + recompress; sig-bypass; write patched RPL (to C: staging,
   then user copies to E: — respecting the E: rule).
4. Drop `content_root/ui/t6/*.lua` into `content\`; boot; MODS button = pass.
5. Repeat for ZM (`t6_cafef_rpl.rpl`) once MP is proven.
