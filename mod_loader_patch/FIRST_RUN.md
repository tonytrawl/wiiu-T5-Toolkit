# First run — get the MODS button on screen

This is the end-to-end test of the raw-`.lua`-from-disk hook. If the MODS button appears in the
main lobby, a `.lua` that exists **only on disk** (never in any fastfile) was loaded by the engine
— which proves the whole loose-file mechanism.

## Pieces
1. **The RPL hook** — `patches.txt` + `rules.txt` (see `README.md`). This is what makes the engine
   look on disk. **Without it, nothing below happens.**
2. **The loose LUI** — `content_root/ui/t6/mainlobby.lua` and `content_root/ui/t6/mods.lua`.
   - `mainlobby.lua`: PC-Plutonium's main lobby (keeps its Wii U code paths) + a MODS button.
     Two safety edits: `require("T6.Mods")` is wrapped in `pcall`, and opening the Mods menu is
     guarded — so a missing/broken mods.lua can **not** brick the lobby.
   - `mods.lua`: brand-new file (exists ONLY on disk) — hardened so it opens with or without the
     `Engine.GetModCount`/`loadmod` bindings. It is the true proof: the stock ff has no such file.

## Install
1. Apply the hook pack (`README.md`): `rules.txt` + `patches.txt` → `<Cemu>/graphicPacks/BO2_RawLuaLoader/`, enable it.
2. Copy the contents of `content_root/` into the title's `/vol/content` root in Cemu, preserving
   layout, so you end up with:
   ```
   <content>/ui/t6/mainlobby.lua
   <content>/ui/t6/mods.lua
   ```
   (`<content>` = the game content dir Cemu serves as `/vol/content`. If unsure of the exact host
   path, confirm it against Cemu's file-access log while the title boots — see "Finding the name"
   below.)
3. Boot to the Multiplayer/Zombies main lobby.

## Reading the result (diagnostic table)
| What you see | Meaning | Next |
|---|---|---|
| Lobby loads, **MODS button present** | **FULL PASS** — hook works, loose files load, name-shadow works, brand-new `mods.lua` loaded | Proceed to build the real loader (RPL bindings). Clicking MODS opens the menu; it will say "bindings not installed" until those are written — that's expected. |
| Lobby loads, looks normal, **no MODS button** | Our `mainlobby.lua` was **not** loaded — hook not active | Fix `moduleMatches` / cave syntax in `patches.txt` (README §"two things to verify"). Content is fine. |
| Lobby errors / different / partial | Hook **works** (it loaded our file) but there's a LUI **API mismatch** between this Wii U build and the PC-Plutonium source | Progress! The hook is proven. Iterate on `mainlobby.lua` against this build's API. |
| Black screen / hard crash entering lobby | Our `mainlobby.lua` errored hard (hook still likely working) | Remove `mainlobby.lua`, keep only `mods.lua`, and instead prove the hook with a trivial file first (below). |

**Key point:** every outcome except "no MODS button" means the hook is loading disk files. Only the
"no MODS button / identical lobby" case points at the patch (`moduleMatches`) rather than content.

## De-risk option: trivial hook proof first
If you'd rather validate the hook in isolation before the full lobby:
1. Do NOT copy `mainlobby.lua`. Copy only `mods.lua`.
2. Temporarily edit any small already-working menu's on-disk copy with a one-line visible change,
   OR just watch Cemu's log: with the hook active, note whether the engine's file-open calls hit
   `/vol/content/ui/t6/...` paths for `.lua` names. Seeing those reads = the hook is firing.

## Finding the on-disk name (if MODS button never shows despite a correct patch)
The name the engine passes to the loader must match the on-disk path. To confirm the exact string:
temporarily add a logging stub, or dump `r3` at the call site `0x027DC74C` (that register holds the
`const char*` name). If it is e.g. `ui/t6/mainlobby.lua` you are correct; if it differs (case,
`ui_mp/` prefix, no extension) mirror that on disk.

## Scope reminder
- MP RPL only. ZM = same hook re-resolved in `t6_cafef_rpl.rpl`.
- Clicking MODS + actually loading a mod needs the `Engine.GetModCount/GetModInfo/loadmod` bindings
  (the next RPL patch). This first run only proves loose `.lua` loading + the menu wiring.
