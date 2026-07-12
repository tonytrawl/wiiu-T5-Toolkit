# FINDINGS — zm additive mapstable boot test (2026-07-12)

Boot-tested the additive zm mapstable edit on real Cemu (update-partition deploy), with the
AUTHENTIC PC patch_zm as the row source. Isolated the failure with a controlled A/B ladder.

## Results ladder (all deployed to .../english/patch_zm.ff; stockbak = genuine 4-map)
| variant | zm maps | boot result |
|---|---|---|
| stock (genuine) | 4 | LOADS to zombie menu |
| additive +3 (prison/buried/tomb), PC packs 4/5/6, real display | 7 | crash during zombie-frontend init |
| +3, display borrowed from zm_transit | 7 | crash (same spot) |
| +3, DLC pack forced to 0 (in-range, un-gated) | 7 | crash (same spot) |
| **re-emit UNCHANGED (emit_stringtable, 4 maps)** | 4 | **LOADS** |
| **additive +1 (zm_prison only, pack 0)** | 5 | **crash (same spot)** |

## What this proves
1. **The zm zone LINKS cleanly — no position-dependency crash.** Zero "Could not load default
   asset" in the log; boot progresses far past patch_mp's `fx_pistol_shell` point, through GX2 init
   and zombie sound-bank loads. So zm does NOT have patch_mp's loader position-dependency, and the
   patch_relink additive machinery produces a loadable zone.
2. **`emit_stringtable` is faithful** — re-emitting the same 4-map table (all-FOLLOW cells + cellIndex
   resort) LOADS. So the rebuild path (cells/cellIndex) is correct. (0 cell mismatches offline too.)
3. **Not display assets, not pack index, not mappack_count**: borrowing display cols, forcing pack 0,
   all still crash; `mappack_count` is absent from the WiiU table entirely (lookup→0, loop skipped).
4. **Hard limit = 4 zombie maps.** Adding even ONE map (5 total) crashes at the identical point
   (right after loading `zmb_code_post_gfx` sound, during zombie UI init). Stock 4 loads.

## Mechanism (static RE of t6_cafef_rpl.rpl)
`UI_LoadMaps__Fv` @0x02482960 reads `zm/mapstable.csv`: looks up `maxnum_map` (per-map loop bound)
and `mappack_count` (absent→0). Per-map struct array @base+0x47c0, stride 0x58, memset 0xb00 ⇒ holds
**32 maps** — so UI_LoadMaps itself does NOT overflow at 5-7. The crash is therefore a DOWNSTREAM
consumer of the built map array with a fixed assumption of the shipped count (native size-4 array
and/or the LUI zombie globe `GetStartLocsZombie` hardcoded start-loc list — see
[[wiiu-map-menu-registry]] which found zombie map registration is heavily hardcoded). The crash is a
silent hang/soft-fault: no OSFatal, no CrashReport3, log just ends — WER sometimes catches a full
dump, sometimes not.

## Consequence for adding zombie maps
ADDITIVE (grow the zombie map count) is blocked by a UI-side count limit, NOT by the fastfile.
Two ways forward:
- **SWAP (count-preserving) — proven-safe path.** Replace a stock zm map's identity with a DLC map
  (keep 4 rows, indices 0-3). This is the zm analogue of the working mp swap; avoids the UI limit
  entirely. Ceiling: 4 zombie maps at a time, display degraded until DLC art is ported.
- **Patch the UI limit — the "unlimited" path.** Find the size-4 consumer (native array bound in the
  zombie frontend, and/or the LUI/Lua globe start-locs) and enlarge it. We have RPL-patch tooling
  (rpl_*_patch.py) and located UI_LoadMaps; the consumer array needs identifying (dump-fault RIP or
  further disasm). LUI/Lua involvement would make it harder than the existing native gate patches.

## Contrast with patch_mp
- patch_mp additive: crashes DURING LINK (fx_pistol_shell position-dependency) — never reaches UI.
- patch_zm additive: LINKS fine, crashes IN THE UI at >4 maps.
Different blockers per zone; the from-PC full-assemble idea addresses mp's link crash but would still
hit zm's UI count limit.

## UPDATE — both gates are LUI, not native (2026-07-12)
Compared WiiU vs PC `patch_ui_zm.ff` and disassembled the native map consumers:
- **Gate 2 (display list) is LUI in patch_ui_zm.ff.** The zombie map table is compiled LUI
  constants, format `0x04 <len> <string+null>` with len BE on WiiU / LE on PC. WiiU table =
  6 maps (…TRANSIT_TM, PRISON) + categories to DLC2Maps; PC = 8 maps (+MAP_ZM_BURIED, MAP_ZM_TOMB)
  + DLC3Maps/DLC4Maps/SideQuestMaps/CharacterNameDisplayMaps. WiiU is a truncated build of the same
  table. Editing = LUI bytecode work (insert constants + extend the table-construction ops); PC
  rawfile can't be dropped in (BE/LE + layout differ).
- **Gate 1 (the crash) is ALSO LUI, not native.** Native map fns (UI_LoadMaps per-map array holds
  32; UI_GetMapNameForCurrentIndex/UI_GetMapLoadNameForCurrentIndex iterate maxnum_map correctly up
  to 32) do NOT cap at 4. So the >4 crash at zombie init is the globe LUI (GameGlobeZombie/
  GetStartLocsZombie), not the RPL. ⇒ the additive unlock is fundamentally a LUI/Lua editing effort
  (or guest-debug to pin the Lua limit), not an RPL patch.
- **Consequence:** SWAP (count 4, reuse a stock slot already in the LUI table) sidesteps BOTH LUI
  gates and is the clean path. First swap tried: zm_transit_dr -> zm_prison (prison is in the WiiU
  LUI table), pack 0, map index kept at slot 3. Deployed for boot test.

## UPDATE 2 — swap reaches the globe; convert-PC-LUI blocked by custom format (2026-07-12)
- **Name-only swap WORKS to the globe.** zm_transit_dr row with col0=zm_prison but ALL of
  transit_dr's existing display columns -> boots, globe renders, scrolling works. So: the internal
  name change is safe; the earlier full-prison-swap crash was its MISSING DISPLAY ASSETS
  (menu_zm_map_signpost_prison / faction_guards / faction_inmates absent from the WiiU zone).
- **New wall: selecting a map SOFT-HANGS** (game keeps rendering GX2 frames; not a crash). This is
  the LUI start-path / content gate. DLC ownership IS already patched in the deployed t6 rpl
  (Content_PlayerHasDLCForMapPackIndex = li r3,1; Content_AnyNewMapPacks = li r3,0), so it's the
  map launch/content path or a separate LUI content check — and playing a DLC map ultimately needs
  its map CONTENT (zm_prison.ff+ipak) ported regardless. Baseline unknown: whether STOCK lets you
  select+start transit in this setup (all prior validated boots were MP).
- **Convert PC patch_ui_zm -> WiiU is BLOCKED by custom LUI format.** patch_ui_zm = 86 assets (46
  RAWFILE/39 MATERIAL/1 TECHSET), no weapons/xmodels -> simple asset surface, BUT the 46 rawfiles are
  T6 LUI bytecode format 0x0d: `\x1bLua` v5.1 header (endian flag byte[6]=00 WiiU/01 PC is the ONLY
  header diff) followed by a NON-standard body (custom prepended type-enum/string section; not
  Lua 5.1 luac layout). A standard endian-swap transcoder hangs (misparses counts). WiiU LUI = 6-map
  table (to DLC2); PC = 8-map (+buried/tomb, DLC3/4). Tool `fullrelink/lua_endian.py` written but the
  standard-format parser does NOT fit 0x0d -> needs the custom T6 LUI format reversed first.
  => Both zombie-UI paths (edit WiiU LUI in place, OR convert PC LUI) require reversing the custom
  LUI 0x0d bytecode. Substantial RE (may be documented in T6 LUI modding communities).

## UPDATE 3 — T6 LUI format reversal (partial; 2026-07-12)
Goal: transcode PC LUI -> WiiU (endian) to port PC's fuller zombie globe (8 maps) into patch_ui_zm.
- **CONFIRMED pure endian-swap.** All 45 patch_ui_zm scripts are matched WiiU(BE)/PC(LE) pairs, mostly
  identical byte-length; W/P diff = strings identical, numeric 4-byte fields byte-reversed. Extraction
  via `lua_endian._rawfiles` (find \x1bLua, name back-scan, len = u32 @rawfile_hdr+4). 45/45 clean.
- **SOLVED header + custom prefix:** [0:12] Lua5.1 hdr (magic, ver 0x51, fmt 0x0d, endian@[6]=00 BE/
  01 LE, int/sizet/instr/number all 4) -> [12:14] 2 opaque bytes (=0x0000) -> u32 typeCount(=13) ->
  13x {u32 id, u32 len, byte[len]} type-enum table (TNIL,TBOOLEAN,TLIGHTUSERDATA,TNUMBER,TSTRING,
  TTABLE,TFUNCTION,TUSERDATA,TTHREAD,TIFUNCTION,TCFUNCTION,TUI64,TSTRUCT). Function proto starts @238
  for privateonlinegamelobby.lua (876B, smallest). Type table round-trips.
- **BLOCKER: the function-proto/instruction section is a CUSTOM T6 layout**, NOT standard Lua 5.1
  luac. Parsing proto as standard (source String, linedefined/lastlinedefined int, 4 count-bytes,
  code, constants, protos, debug) yields absurd values (e.g. lastlinedefined=0x02000000 BE). Byte-
  staring insufficient; needs the T6 luac proto field spec (exists in PC T6 LUI modding tools:
  compile/decompile). Tool `lua_endian.py` = framework + BE->LE->BE validator, ready to slot the
  proto layout in. NEXT: obtain T6 luac proto spec, complete `function()`, validate 45/45 round-trip,
  then transcode PC's zombie globe LUI -> BE and splice into patch_ui_zm (backbone) for the full map
  table + globe. (Playing DLC zm maps still needs map CONTENT ported separately.)

## UPDATE 4 — T6 LUI transcoder SOLVED (2026-07-12)
T6 LUI = **HavokScript** (not standard Lua 5.1). Format from Deewarz/CoDHVKDecompiler
`LuaFileTypes/LuaFileT6.cs`: header (magic,ver,compiler,endian@6,4 sizes,integral,gameByte,
+1 skip, i32 constantTypeCount, table of {i32 id,i32 len,bytes}) then Function (hdr: i32 upval,
i32 params, u8 vararg, i32 regs, i32 instrCount, PAD to 4; instrCount x 4B; i32 constCount x
{u8 type: 0nil/1bool u8/3number f32/4string i32len+bytes/13hash u64}; footer i32+f32+i32
subCount; subCount x Function). PURE endian swap of all multibyte fields.
`fullrelink/lua_endian.py` transcode()+validate: **round-trip BE->LE->BE 45/45 OK**; GOLD PC->BE ==
genuine WiiU **17/17** on identical scripts (the other 28 differ in LENGTH = WiiU shipped TRUNCATED
builds -> exactly the content to port). Zombie map/globe scripts (PC bigger, transcode clean):
selectmapzombie.lua PC44133/WiiU38255, basezombie 10743/8145, gameglobezombie, selectstartloczombie
41209/38905, gamemapzombie. **TRANSCODER IS THE UNBLOCK.** NEXT: transcode PC zombie scripts->BE +
splice into patch_ui_zm (rawfile-body substitution -> zone grows -> reuse mapstable relink machinery;
patch_ui_zm = UI-only 46 RAWFILE/39 MAT/1 TS) + convert PC DLC display materials (signpost/faction)
via material_convert; rebuild+boot. (Playing DLC zm maps still needs map CONTENT ported.)

## UPDATE 5 — LUI splice pipeline WORKS; count crash is NATIVE not LUI (2026-07-12)
Built `fullrelink/ui_splice.py`: transcode PC LUI rawfiles->BE (lua_endian) + multi-rawfile-buffer
substitution into patch_ui_zm with cumulative-delta relink (generalized EditEmitter). GOTCHA: console
RawFile asset = {name*,len,buffer*}(12) + name\0 + buffer(len) + **1 trailing \0** (sub_end=boff+len+1).
Offline: 6/6 spliced scripts round-trip==PC, zone re-walks 86 assets, ff repacks. BOOT-TESTED:
- Converted patch_ui_zm (6 zombie scripts) BOOTS to zombie menu (pipeline structurally sound on HW!)
  but "Local" wouldn't load the lobby (regression -> a replaced script breaks lobby entry; lobbypanes
  shared w/ MP the prime suspect).
- basezombie-ONLY conversion: Local loads fine (safe). 5 zombie scripts (no lobbypanes): also crashes.
- **KEY: with ANY UI conversion (stock / basezombie / 5-script), a >4-row mapstable crashes at the
  IDENTICAL early point (zombie init, loading zmb_code_post_gfx, before the menu).** So the count crash
  is triggered purely by mapstable rows>4 during zombie INIT and is NOT in the LUI scripts I can
  transcode -> it's a NATIVE/core-init limit (or an init Lua script not yet found), earlier than the
  globe. Native UI_LoadMaps handles 32, so it's a DIFFERENT consumer. Fresh dump Cemu.exe.14704.dmp
  (02:46) would pin the fault (guest-PC extract; heavy). LUI transcoder+splicer are proven, reusable.
  VIABLE zombie deliverable w/o cracking the native limit: SWAP (stay at 4 maps) + basezombie-converted
  UI (DLC map in LUI table) + ported display materials. >4 maps needs the native count limit found.

## UPDATE 6 — ⭐ ff-baked Lua SOURCE compiles+runs on WiiU (mod loading unlocked) 2026-07-12
Inserted the mod_loader_patch modded `ui/t6/mainlobby.lua` (PC-Plutonium SOURCE, 42KB, has MODS
button + pcall(require,"T6.Mods")) as a rawfile-buffer substitution into patch_ui_mp (fullrelink/
mod_insert.py, source buffer = no transcode, +trailing \0). BOOT-TESTED: Cemu LOG shows
`unable to load module "t6.mainlobby"` with a real LUI stack traceback + `4067036743:26: LUI Error:
Tried to add nonexistent menu main`. => **the WiiU engine's hksL_loadfile COMPILED our raw source at
load and EXECUTED it** (runtime LUI error proves it ran). Failure = PC-vs-WiiU LUI API mismatch
(content), NOT the mechanism. **CAPABILITY UNLOCKED: bake new/modified Lua SOURCE into the ff -> engine
compiles+runs it. No offline HKS compiler, no disk-hook, no RPL patch needed for source.** (Transcoder
still needed for cross-platform BYTECODE.) PATH to working mod: decompile WiiU stock mainlobby
(CoDLUIDecompiler) -> API-correct source base -> add require+MODS button -> insert + mods.lua as new
source asset. Tools: fullrelink/mod_insert.py, ui_splice.py. Deploy reverted stock.

## Artifacts (dlc loading/native/fullrelink/)
diag_interior_ptrs.py, feasibility.py, zm_edit_safedisplay.py, zm_edit_pack0.py,
zm_reemit_nogrow.py, zm_edit_addN.py (ADD_N ceiling probe). Deploy dir stockbak restored.
