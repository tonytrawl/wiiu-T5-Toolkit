# FINDINGS — How Plutonium (BO2/T6) discovers & loads mods, and what ports to Wii U

Research session, 2026-07-10. Read-only investigation of the local Plutonium install at
`C:\Users\Tony - Main Rig\AppData\Local\Plutonium\storage\t6`. No code owed; this is the
findings doc. Scope note: the user's own `mods/mp_peach` and `mods/test` are *self-placed test
mods* — they are the payload, not the mechanism. This doc is about the **engine/client
mechanism** Plutonium uses to surface and mount any mod, and whether that mechanism can be
recreated on the Wii U T6 build.

---

## 0. TL;DR verdict

The Plutonium mod system is **four distinct mechanisms glued together**. Only one of them is
novel PC-client magic; the rest are either stock-T6 behavior or things our Wii U pipeline
*already* reproduces by other means.

| # | Mechanism | What it is | Wii U class |
|---|-----------|-----------|-------------|
| 1 | **Mod discovery** (`Engine.GetModCount`/`GetModInfo`) | Plutonium C++ scan of the `mods/` folder | **(b)** client code → needs a console-side enumerator or RPL patch |
| 2 | **`loadmod` → `fs_game` overlay** | sets the **stock** `fs_game` cvar to `mods/<name>`, restarts, engine adds that folder to the search path | **(a) core is stock** / **(b) the loose-file search path & `loadmod` cmd are client-side on console** |
| 3 | **The Mods menu itself** (`mods.lua`, MainLobby button) | pure **stock LUI** widgets, injected via Plutonium's `raw/` overlay | **(a) LUI is stock** / **(b) the injection path is client** |
| 4 | **Script glue** (`raw/scripts/*.gsc`) | raw GSC compiled at runtime by Plutonium's compiler | **(b/c)** PC-only compiler; console needs baked ScriptParseTree |

**Bottom line:** Plutonium doesn't teach us a *cleaner* load path than our zone-relinking — it
teaches us that **the mod is just a normal map `.ff` loaded by name through `fs_game`**, and
everything else is UI/discovery chrome. Every piece of that chrome has a console analogue we
already own (mapsTable registry, ipak mounting, RPL patches, ScriptParseTree baking). The one
genuinely reusable *idea* is #2: **a mod is a same-named zone loaded on top through a search-path
override** — which is exactly our ipak/loadzone mount model, so it validates our current approach
rather than replacing it.

---

## 1. The loading chain, end to end

Files that make it up (all present locally):

```
raw/ui/t6/mods.lua              ← the Mods menu (LUI) — THE file the user pointed at
raw/ui/t6/mainlobby.lua         ← adds the "MODS" button + open_mods_menu handler
raw/scripts/mp/ranked.gsc       ← example of Plutonium's runtime-GSC surface (replaceFunc)
raw/scripts/zm/ranked.gsc
zone/en_plutonium_mp.ff …       ← Plutonium's own localized-string / ffotd zones
mods/<name>/<mp_name>.ff        ← the actual mod (a map zone), e.g. mp_peach.ff (TAff0100 v147)
players/mods/<name>/…           ← per-mod saved config / classes / stats (client writes here)
```

### 1a. Discovery & mounting
- The **MainLobby** LUI (`raw/ui/t6/mainlobby.lua`) adds a button:
  ```lua
  MainLobbyButtonPane.body.modsButton = ...:addButton(Engine.Localize("MODS"), nil, 12)
  MainLobbyButtonPane.body.modsButton:setActionEventName("open_mods_menu")
  ...
  MainLobbyWidget:registerEventHandler("open_mods_menu", CoD.MainLobby.OpenModsList)
  CoD.MainLobby.OpenModsList = function(w, ci) w:openMenu("Mods", ci.controller, {parent="MainLobby"}) w:close() end
  ```
- The **Mods** menu (`mods.lua`) enumerates mods through **Plutonium-added engine bindings**:
  ```lua
  local modCount = Engine.GetModCount()
  for i = 0, modCount-1 do local modInfo = Engine.GetModInfo(i) ... end
  ```
  `GetModInfo(i)` returns `{ modname, name, author, description, version }`. Source of that
  metadata = the mod folder (a `description.txt`-style manifest; absent in the user's test mods,
  so those show blank author/description). The filter is name-prefix: the menu's no-data text is
  *"Make sure mod is prefixed with `mp_`/`zm_` to be found"* (`modPrefix` line), i.e. discovery
  is **folder-scan + prefix match against the current game mode**.

### 1b. The `.ff` side — this is the important part
- Selecting a mod → `LoadMod` handler → `Engine.Exec(0, "loadmod " .. modname .. "\n")`.
- `loadmod` sets the **stock `fs_game` cvar** to `mods/<name>` and reloads. Proof from the mod's
  own `games_mp.log`:
  ```
  InitGame: \...\fs_game\mods/test\...\mapname\test\gamename\PT6MP\...
  ```
- With `fs_game = mods/test`, the engine adds that folder to its **file search path**, so when
  the map `test` loads, `mods/test/mp_test.ff` is found and loaded **as the map zone**.
- **Override semantics:** T6 resolves assets by name and the *later*-loaded zone's asset shadows
  the earlier one. `fs_game` sits **higher priority** than the base install, so a mod `.ff`
  can either add new assets or override stock ones by shipping an asset of the same name. This is
  standard idTech/T6 search-path precedence, **not** a Plutonium invention.
- Unload = `loadmod ""` (clears `fs_game`).

### 1c. The Lua side
- `mods.lua` scripts **only against stock T6 LUI surface**: `LUI.UIVerticalList`, `LUI.UIText`,
  `CoD.Menu.New`, `CoD.ButtonList`, `CoD.ListBox`, `LUI.createMenu.*`, `Engine.PlaySound`,
  `Engine.Localize`. All of this exists in retail T6 on console.
- The **only** non-stock calls are `Engine.GetModCount`, `Engine.GetModInfo`, and the `loadmod`
  console command — **Plutonium-added C++ engine bindings**, and `Engine.Exec` of a
  Plutonium-registered command.
- Injection: these `.lua` live under `raw/` and are loaded by Plutonium's client **at runtime**
  (raw-file overlay) on top of the LUI baked into `ui.ff`. That overlay loader is client code.

### 1d. GSC / script loading
- `raw/scripts/mp/ranked.gsc` shows the model: **raw GSC source compiled at load** by
  Plutonium's built-in compiler, using Plutonium extensions like `replaceFunc(GetFunction(...))`
  to hook stock functions. Mods drop `.gsc` under `raw/scripts/` (or their mod folder) and the
  client compiles them. This is **not** ScriptParseTree assets in the `.ff` — it's a PC-only
  runtime compiler.

### 1e. The map/menu (mapsTable) question
- A Plutonium custom **map** becomes playable because the mod ships `mp_<name>.ff` and is
  launched by `mapname <name>` under the mod's `fs_game`. Selectability in the UI is via the
  **Mods list**, not a mapsTable edit — the mod list is the entry point, and once loaded the map
  is started by the private-match/`map` flow. (Contrast with retail console, where a map must be
  a row in `mp/zm mapsTable.csv` and gated by the DLC RPL check — see `wiiu-map-menu-registry`.)

---

## 2. Per-mechanism portability classification

### Mechanism 1 — Mod discovery (`GetModCount`/`GetModInfo`) → class (b)
Plutonium C++ that folder-scans `mods/` and reads a manifest. Does not exist on console.
**Console analogue we already have:** the mapsTable/menu registry approach
(`wiiu-map-menu-registry`) — a custom map row in `mp/zm mapsTable.csv` + our authored menu.
Recreating a *live folder scan* would need an RPL patch adding the two Lua bindings, feasible in
principle (we already do targeted RPL patches — sig-bypass, DLC gate) but higher effort than just
registering a map row. **Recommendation: don't port the scanner; register the map statically.**

### Mechanism 2 — `loadmod` / `fs_game` search-path overlay → class (a) core, (b) delivery
The *concept* — "mount a same-named zone on top of the base and let name-resolution shadow" — is
stock engine and is **exactly what our ipak/loadzone mount trick already does** on Cemu
(`dlc-loadzone-native`, `dlc-ipak-partition`: base+mp+dlcN.ipak fed to prepare; `base_split8`
mount trick). The Wii U build has **no writable loose filesystem** the way PC `fs_game` uses, so
we can't literally point `fs_game` at a folder — but we don't need to; the ipak partition +
loadzone request is the console-native version of the same idea. **This mechanism validates our
current path; nothing new to build.**

### Mechanism 3 — The Mods menu (LUI) → class (a) content, (b) injection
The menu is **stock LUI** and would run on console if the compiled `.lua`/menu were present in a
zone. We **already author console zones** and bake menu art (`dlc-loadzone-native` renders a
DLC zm frontend with zone+menu on Cemu). So a "Mods"-style menu is buildable as an authored
menu asset. What does **not** port is Plutonium's `raw/` runtime overlay loader (client C++) —
on console the menu must be **baked into a zone**, not dropped as a loose `.lua`. **Testable
console analogue exists.**

### Mechanism 4 — Runtime GSC compile (`raw/scripts/*.gsc`, `replaceFunc`) → class (b/c)
Plutonium's runtime GSC compiler and `replaceFunc`/`GetFunction` detour API are **PC-only client
code** — dead end to port as-is (c). But the *effect* (custom script logic in a map) is
achievable on console the retail way: **ScriptParseTree assets baked into the map zone** by our
linker. So: the *compiler* is a dead end, the *outcome* is reachable through our existing
zone-authoring. (We already handle GSC swaps — `gsc_swap.py`, `chaos-dogs-pluto-port`.)

---

## 3. What this actually teaches the Wii U effort

1. **No shortcut.** Plutonium does *not* have a magic loose-file mod path that would let us skip
   zone relinking on Wii U. Under the hood a Plutonium mod is a **normal T6 map `.ff`** loaded by
   name; the "mod system" is discovery UI + a search-path override. Our zone-conversion pipeline
   is already producing the equivalent artifact (a bootable console map zone).

2. **The mount model is the same shape as ours.** `fs_game` = "later same-named zone shadows the
   base by name-resolution." Our ipak partition + loadzone mount is the console realization of the
   identical precedence rule. This is a **confidence result**, not a new task: it says our DLC/ipak
   mount approach is the *correct* console equivalent of how PC mods load.

3. **Asset-override-by-name is real and exploitable on console** — worth a cheap experiment
   (below), because if a later-loaded zone shadows an earlier asset by name on Wii U the same way
   it does on PC, that's a lighter path to *patching* individual assets (a menu string, a material,
   a script) than rebuilding a whole map zone.

4. **The UI/discovery layer is optional chrome.** For a first custom map on Wii U we don't need a
   live mod scanner or a Mods menu — we register the map in `mapsTable.csv` and reach it through
   the stock map-select flow (already our plan). A Plutonium-style Mods menu is a *later polish*
   item that is buildable (stock LUI, baked into a zone) but not on the critical path.

---

## 4. Proposed cheap experiment (class-(a) mechanism, console-testable)

**Question:** does a later-loaded zone override an already-loaded asset **by name** on the Wii U
build, the way `fs_game` precedence does on PC?

**Cheap test:** take a stock console zone that we already boot on Cemu (e.g. a DLC loadzone /
frontend that renders — `dlc-loadzone-native`). Author a tiny second zone loaded *after* it that
contains **one** asset with the **same name** but altered content — the safest probe is a
**localized string** or a **material** already visible on screen (e.g. a menu title string).
Mount it via the ipak/loadzone path we already use. Observe:
- string changes on screen → **name-shadowing works on console**; opens a lightweight
  asset-patch path (ship a small override zone instead of rebuilding the map).
- no change / load order wins the other way → override is add-only; we must patch in-place in the
  base zone.

Cost: one small authored zone + one Cemu boot, reusing the existing `batch_loadzones.py`/ipak
mount infrastructure. No new engine RE. This is the single most useful follow-up because it tells
us whether we can distribute Wii U content as **thin override zones** (Plutonium-mod-like) rather
than full map rebuilds.

---

## 5. Honesty on classification

- I did **not** decompile the Plutonium client, so the exact C++ of `GetModCount`/`GetModInfo`/
  `loadmod` is inferred from their Lua call sites + the `games_mp.log` `fs_game` evidence, not
  read from a binary. The classification of those three as client-added (b) is well-supported
  (they are absent from stock T6 LUI and set the stock `fs_game` cvar) but is inference.
- `fs_game` being a **stock** cvar and search-path precedence being **stock** engine behavior is
  solid (it's idTech heritage and matches the log). The claim that this maps onto our ipak mount
  is an *analogy of behavior*, verified only to the extent our ipak mount already boots on Cemu —
  the name-shadow equivalence is exactly what §4 proposes to actually test.
- The GSC runtime compiler as PC-only (c) is confident: it's a documented Plutonium feature and
  the `raw/scripts` + `replaceFunc` surface confirms it.

No mechanism here is oversold as "drop-in portable." The genuinely reusable output is the
**mental model** (mod = same-named zone via search-path shadow) and the **one testable
experiment** in §4.
