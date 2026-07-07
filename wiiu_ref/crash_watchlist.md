# Guest crash-address watch-list (BO2 t6mp RPL symbols)

Symbolicate any crashlog with `python wiiu_ref/rpl_symbolize.py --threads`
(reads the last crashlog in the Cemu log). Or name specific addresses:
`python wiiu_ref/rpl_symbolize.py 0x022239c4 ...`. 41,560 STT_FUNC symbols
loaded from the RPL `.symtab`.

If a crashing thread's IP/LR falls in one of these ranges, it names the asset
whose console-write layout our writer got wrong (the current bisection target):

## World render cluster (current suspects)
| range | function | asset |
|---|---|---|
| 0x022239c4–0x02224ae0 | `Load_GfxWorld__Fb` | GfxWorld (root) |
| 0x02222fb8–0x022237cc | `Load_GfxWorldDraw__Fb` | **GfxWorldDraw — the deferred +48-word console struct** |
| 0x02221920–0x02221bb0 | `Load_GfxWorldDpvsDynamic__Fb` | GfxWorld dpvs |
| 0x0221d624–…            | `Load_GfxLightGridEntry` | GfxWorld lightGrid ("FAT unsolved") |
| 0x021d3814–0x021d45d4 | `Load_clipMap_t__Fb` | clipMap |
| 0x02405830–0x02405ccc | `CM_LoadMap__FPCcPi` | clipMap/collision |
| 0x021d243c–0x021d24e8 | `Load_MapEnts__Fb` | MapEnts |
| 0x021c6548–0x021c65bc | `Load_GameWorldMp__Fb` | GameWorldMp |

## DB / link path (generic — need caller/LR for the asset)
| range | function |
|---|---|
| 0x0219727c–0x021979d8 | `DB_LoadXFile__FPCc…` (the DB-load driver) |
| 0x02230ecc–0x022314b4 | `__DB_LinkXAssetEntry` (per-asset linker) |
| 0x02957de0–0x02958080 | `R_LoadWorld` (renderer world init) |

## Known red herrings
| addr | function | note |
|---|---|---|
| 0x02240280–0x0224?? | `DDL_LUI_ArrayToString(lua_State*)` | menu/loading-screen Lua thread, NOT the linker |

Note: Cemu crashlog GPR dump (RAX/RBX/…) are **host x86** registers, not
guest. Guest state = the per-thread `IP`/`LR` in the thread table. The crashing
thread is the one whose IP is in a load/link function above (not WAITING in an
OS primitive).
