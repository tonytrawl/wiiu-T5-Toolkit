# BO2 (T6) Wii U — raw-`.lua`-from-disk loader patch

Makes the game load loose `.lua` files from disk, overriding the copies baked into the
fastfiles — the first concrete step toward a Plutonium-style mod loader on Wii U. No `.ff`
rebuild required to iterate on menus/scripts.

See `HANDOFF_wiiu_dynamic_mod_loader.md` (repo root) for the full reverse-engineering trail.

## How it works (one-paragraph)
Every LUI `.lua` load funnels through `LUI_CoD_GetRawFile(name)` (`0x02884ED0`), reached from
`hksL_loadfile_FastFile` via the `bl` at **`0x027DC74C`**. We repoint that one `bl` to a code
cave that calls `FS_ReadFile(name,&buf)` (`0x024DD0C8`) **first**; on a hit it synthesizes a
`RawFile { name; len; buffer }` and returns it (disk shadows the ff); on a miss it tail-calls the
untouched `LUI_CoD_GetRawFile` (original behavior). The bytes then go through the HKS Compiler, so
loose **source** `.lua` works, not just bytecode.

## Files
- `bo2_rawlua_hook.S` — authoritative, commented hook source (source of truth).
- `patches.txt` — Cemu graphic-pack patch (call-site redirect + cave).
- `rules.txt` — Cemu pack definition.

## Install (Cemu)
1. Copy `rules.txt` + `patches.txt` into `<Cemu>/graphicPacks/BO2_RawLuaLoader/`.
2. Cemu → Options → Graphic Packs → enable **BO2 Raw Lua Loader**. Restart the title.
3. If the pack does not take effect, it is almost always `moduleMatches` — see below.

## The two things to verify (honest gaps)
1. **`moduleMatches`** in `patches.txt` must equal Cemu's checksum of `t6mp_cafef_rpl.rpl`'s
   `.text`. Two candidates are pre-filled (`0x41AAD672` first, then `0x47BE531D`). If neither
   activates, load the title, open Cemu's `log.txt`, find the line where the RPL/module loads, and
   use the checksum printed there. (Different region dumps / TU versions → different checksum.)
2. **Cave syntax.** `patches.txt` uses Cemu 2.x native labels + `@h/@l` + auto code cave. If your
   Cemu build rejects it, use the absolute-address fallback in the next section.

### If the cave syntax is rejected (absolute-address fallback)
Pick a free VA for the cave (e.g. `0x02B00000`, just past `.text` which ends at `0x02AFEDE0`) and
write each instruction at an explicit address, and put `rawfile_scratch` at cave+0x88. The
hook body is validated (37 instrs, 0x88 bytes); regenerate exact bytes for your chosen
cave/scratch VA with keystone:
`Ks(KS_ARCH_PPC, KS_MODE_32|KS_MODE_BIG_ENDIAN)`. The only address that changes with placement is
the `rawfile_scratch` immediate (the `lis 5 / ori 5` pair); everything else is position-independent.
Call-site line stays: `0x027DC74C = bl 0x02B00000`.

## Test procedure (go/no-go for the whole loose-file path)
1. With the patch active, find the on-disk path that maps to `/vol/content` for your title in
   Cemu (the game's content dir).
2. Drop a loose file at `<content>/ui/t6/mainlobby.lua` containing a **visibly modified** copy of
   the stock main-lobby menu (e.g. change a button label, or add a `MODS` button — reference:
   `...\Plutonium\storage\t6\raw\ui\t6\mainlobby.lua`). Start with a trivial edit first.
3. Boot to the main menu.
   - Change appears  → **PASS**: loose-file loading + name-shadow both work. This unblocks the
     whole loader (ship the generic Mods menu as a loose `.lua`, no ff repack).
   - No change      → patch not applied (recheck `moduleMatches`) OR the name reaching
     `LUI_CoD_GetRawFile` differs from the on-disk path (add logging / dump `r3` at `0x027DC74C`).
   - Crash on load  → the on-disk `.lua` is malformed for the HKS compiler (user-side content
     error — expected and out of scope per project directive), or the `RawFile` field offsets
     need rechecking against `LUI_CoD_FFReader` (`0x02884EA8`).

## Notes / scope
- MP only (`t6mp_cafef_rpl.rpl`). For ZM apply the identical logic to `t6_cafef_rpl.rpl` after
  re-resolving the three addresses there (they will differ).
- Real-hardware use needs the SD (`/vol/external01`) redirect (currently reads `/vol/content`) and
  porting the cave into a repacked, signature-bypassed RPL — not covered here.
- GSC (`.gsc`) is a **separate** chain (`Scr_LoadScript` / ScriptParseTree, no confirmed runtime
  GSC compiler) — this patch does NOT enable loose `.gsc`.
