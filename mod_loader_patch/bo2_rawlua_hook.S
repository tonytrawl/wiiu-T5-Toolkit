/* =====================================================================
 * BO2 (T6) Wii U — raw-.lua-from-disk hook  (LUI loose-file loader)
 * Target module: t6mp_cafef_rpl.rpl   (MP RPL; do the same in t6_cafef_rpl.rpl for ZM)
 * Author aid: FINDINGS_plutonium_mod_loading.md / HANDOFF_wiiu_dynamic_mod_loader.md
 *
 * WHAT IT DOES
 *   Every LUI .lua load funnels through LUI_CoD_GetRawFile(name) @ 0x02884ED0,
 *   which returns a RawFile* from the fastfile DB (or NULL). We intercept the
 *   CALL SITE inside hksL_loadfile_FastFile @ 0x027DC74C so the engine tries
 *   the loose file on disk FIRST, and only falls back to the untouched
 *   LUI_CoD_GetRawFile when the file is not present on disk.
 *
 *   Because hksL_loadfile_FastFile then runs the bytes through the HKS Compiler,
 *   loose *source* .lua works (not only precompiled bytecode).
 *
 * STRUCTS / ABI (verified by disassembly)
 *   RawFile { +0x00 const char* name; +0x04 int len; +0x08 const char* buffer; }
 *     -> the reader LUI_CoD_FFReader @0x02884EA8 reads len@+4 and buffer@+8.
 *   int FS_ReadFile(r3=const char* qpath, r4=void** buffer)  @0x024DD0C8
 *     -> returns size (<=0 if missing); VirtualAllocs *buffer (persistent).
 *        Com_Errors ONLY on empty/NULL name (our name is always non-empty).
 *   RawFile* LUI_CoD_GetRawFile(r3=const char* name)         @0x02884ED0
 *
 * PATH NOTE
 *   FS_ReadFile builds  Sys_DefaultInstallPath + name.  On Cemu that root is
 *   /vol/content (the game content dir), which is writable on the host — so a
 *   loose file dropped at  <content>/<name>  (e.g. ui/t6/mainlobby.lua) is read
 *   with NO redirect. Real hardware (/vol/content = read-only disc) needs an SD
 *   redirect: build "/vol/external01/..." and call FS_FileOpenReadBinary
 *   directly instead of FS_ReadFile (future step).
 * ===================================================================== */

/* --- call-site patch @ 0x027DC74C ---------------------------------------
 *   original : bl LUI_CoD_GetRawFile     (bytes 49 8C C0 39)
 *   patched  : bl hook                    (bl to the code cave below)
 * ---------------------------------------------------------------------- */

hook:
    mflr   r0
    stwu   r1, -0x20(r1)
    stw    r0, 0x24(r1)
    stw    r31, 0x1c(r1)
    mr     r31, r3            /* save name (arg0) */
    li     r0, 0
    stw    r0, 8(r1)          /* buf = NULL */
    addi   r4, r1, 8          /* r4 = &buf */
    /* r3 still = name */
    lis    r12, 0x024D        /* FS_ReadFile = 0x024DD0C8 */
    ori    r12, r12, 0xD0C8
    mtctr  r12
    bctrl                     /* r3 = FS_ReadFile(name, &buf) */
    cmpwi  r3, 0
    ble    miss
    lwz    r4, 8(r1)          /* buf */
    cmpwi  r4, 0
    beq    miss
    /* found on disk -> synthesize RawFile at 'rawfile_scratch' */
    lis    r5, rawfile_scratch@h    /* Cemu: resolves the cave label */
    ori    r5, r5, rawfile_scratch@l
    stw    r31, 0(r5)         /* name   */
    stw    r3, 4(r5)          /* len    */
    stw    r4, 8(r5)          /* buffer */
    mr     r3, r5             /* return RawFile* (disk shadows the ff) */
    b      out
miss:
    mr     r3, r31            /* restore name */
    lis    r12, 0x0288        /* LUI_CoD_GetRawFile = 0x02884ED0 (untouched) */
    ori    r12, r12, 0x4ED0
    mtctr  r12
    bctrl                     /* r3 = original DB lookup */
out:
    lwz    r31, 0x1c(r1)
    lwz    r0, 0x24(r1)
    addi   r1, r1, 0x20
    mtlr   r0
    blr

rawfile_scratch:
    .int 0        /* name   */
    .int 0        /* len    */
    .int 0        /* buffer */
