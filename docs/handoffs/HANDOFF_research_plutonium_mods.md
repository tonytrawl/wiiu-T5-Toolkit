# HANDOFF — RESEARCH session: how Plutonium (BO2/T6) loads mods → what ports to Wii U

Standalone investigation doc, 2026-07-10. Pure research, no deliverable code required — the
output is a findings doc. Context: the main project converts PC T6 fastfiles to bootable
Wii U ones (see `PROJECT_STATE.md`); this side project asks whether Plutonium's MOD-loading
mechanism teaches us a cleaner path for getting custom content (maps/mods/menus) onto the
Wii U build than raw zone relinking.

## Starting point (from the user)
A `mod.lua` exists that loads the mod's menu item. Start there: locate it, read it, and map
the full chain it participates in.

## Questions to answer (the findings doc's skeleton)
1. **Discovery & mounting:** how does Plutonium find a mod? (mods folder layout, manifest
   files, `mod.ff`/`mod.lua` naming conventions, search-path injection.) What does the engine
   see — an extra fastfile in the zone search path, a filesystem overlay, or both?
2. **The .ff side:** does a mod ship its own fastfile? If so: which zone name does it load
   under, WHEN in the load sequence (before/after common/patch/map), and what asset types are
   allowed to override already-loaded assets vs only add new ones. Asset override semantics
   are the key question — T6 normally resolves by name; does a later zone's asset shadow an
   earlier one's?
3. **The Lua side:** what engine surface does `mod.lua` script against? (Plutonium's LUI/Lua
   hooks vs stock T6 LUI.) Is the menu item added by Lua at runtime, or does Lua just
   register something a stock menu consumes? Distinguish Plutonium-added engine surface
   (won't exist on Wii U) from stock-T6 surface (exists on console).
4. **GSC/script loading:** how do mod scripts get in — ScriptParseTree assets in the mod ff,
   raw GSC compiled at load (Plutonium has a compiler), or override of stock script names?
5. **The mapsTable/menu question:** how does a Plutonium custom MAP become selectable —
   is it a mapsTable-equivalent edit, an override zone, or a Lua-registered entry? Compare
   directly with our Wii U findings (`wiiu-map-menu-registry` memory: menus list maps from
   mp/zm mapsTable.csv; DLC gate RPL patch).
6. **Portability verdict per mechanism:** for each mechanism found, classify:
   (a) stock-T6 behavior Plutonium merely uses → likely works on Wii U as-is (test idea),
   (b) Plutonium client-side code → needs an RPL patch equivalent (feasible? we already do
   targeted RPL patches: sig-bypass, DLC gate), (c) PC-only (Lua VM surface etc.) → dead end.

## Method
- Plutonium is a closed client but its game interface is observable: the local install's
  files (mods folder, .lua, any shipped .ff), its documentation/forums, and the open-source
  ecosystem around it (GSC compilers, dumped LUI scripts) are all fair sources.
- The PC unlink pipeline (`native_linker`, `pc_walk`) can open any mod .ff found — enumerate
  its asset list and compare against a stock zone to see what a mod zone actually contains.
- Stock T6 zone-loading order and asset-override behavior can be cross-checked against OAT's
  loader source (`tools/ref_oat`) — that part is engine-generic, not Plutonium-specific.
- Wii U side facts to compare against are already established: zone load requests, mapsTable
  registry, RPL patching capability, DLC mount rules (`dlc-ipak-partition` memory).

## Constraints
Read-only investigation. Do NOT edit any `native_linker`/`wiiu_ref` code (an assemble session
is running in those files); new scratch scripts go in a new folder. Never write under `E:\`.
The deliverable bar is honesty about classification (a)/(b)/(c) — do not oversell a PC-only
mechanism as portable.

## Deliverable
`FINDINGS_plutonium_mod_loading.md`: the loading chain end-to-end (discovery → mount → ff →
Lua/menu → GSC), each mechanism classified for Wii U portability with evidence, and — if any
class-(a) mechanism looks testable — a concrete cheap experiment proposal for the Wii U build
(e.g. "does a later-loaded zone override an asset by name on console?"). No code owed.
