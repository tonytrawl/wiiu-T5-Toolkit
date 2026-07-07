"""
batch_convert.py -- one-call PC -> Wii U conversion dispatch for the Studio's
Batch Convert tab (and CLI). Detects the file type by extension and routes it
to the right converter, always writing the output under its ORIGINAL name into
a chosen directory.

Supported inputs:
  * .ff              PC Black Ops II fastfile  -> Wii U big-endian v148 fastfile
                     (OAT big-endian writer -> wiiu_ff.pack). Needs Unlinker.exe.
  * .sabs / .sabl    PC sound bank            -> Wii U sound bank (sab_convert).
  * .ipak            PC image pak             -> Wii U image pak  (in development).

Every converter keeps the input's basename; only the directory changes.
"""
import os
import sys
import io
import contextlib
import subprocess

APP_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(APP_DIR)
for _p in (APP_DIR, os.path.join(REPO, "wiiu_ref")):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

import wiiu_ff

FF_EXT = {".ff"}
SAB_EXT = {".sabs", ".sabl"}
IPAK_EXT = {".ipak"}
SUPPORTED_EXT = FF_EXT | SAB_EXT | IPAK_EXT


def detect_kind(path):
    """-> 'fastfile' | 'soundbank' | 'ipak' | None (unsupported)."""
    ext = os.path.splitext(path)[1].lower()
    if ext in FF_EXT:
        return "fastfile"
    if ext in SAB_EXT:
        return "soundbank"
    if ext in IPAK_EXT:
        return "ipak"
    return None


def is_supported(path):
    return detect_kind(path) is not None


def _fastfile_internal_name(path):
    try:
        data = open(path, "rb").read(56)
        nm = data[24:56].split(b"\x00")[0].decode("latin1")
        if nm:
            return nm
    except Exception:
        pass
    return os.path.splitext(os.path.basename(path))[0]


def convert_fastfile(path, out_path, oat_exe, log=print):
    """PC .ff -> Wii U .ff. Runs the OAT big-endian v148 writer to produce a raw
    Wii U zone, then containers it with wiiu_ff.pack under the fastfile's own
    internal name (so it loads in the same slot). Output keeps the source name."""
    if not oat_exe or not os.path.isfile(oat_exe):
        raise FileNotFoundError("A valid Unlinker.exe is required to convert .ff files "
                                "(set it in the Batch Convert tab).")
    data = open(path, "rb").read(12)
    if wiiu_ff.is_wiiu_fastfile(data):
        raise ValueError("This .ff is already a Wii U (v148) fastfile - nothing to convert.")
    internal = _fastfile_internal_name(path)
    workdir = os.path.dirname(os.path.abspath(oat_exe)) or "."
    # OAT name-verifies the file against its internal name: stage a copy named to match.
    staged = os.path.join(workdir, internal + ".ff")
    if os.path.abspath(staged) != os.path.abspath(path):
        open(staged, "wb").write(open(path, "rb").read())
    rewrite = os.path.join(workdir, internal + "_rewrite.ff")
    if os.path.exists(rewrite):
        os.remove(rewrite)
    env = dict(os.environ)
    env.update({"OAT_IGNORE_SIG": "1", "OAT_REWRITE": "1", "OAT_WRITE_WIIU": "1"})
    log(f"  OAT big-endian v148 writer on {internal}.ff ...")
    proc = subprocess.Popen([oat_exe, "--list", staged], cwd=workdir, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in proc.stdout:
        line = line.rstrip()
        if line:
            log("  oat: " + line)
    proc.wait()
    if not os.path.isfile(rewrite):
        raise RuntimeError("OAT did not produce <name>_rewrite.ff - input must be a T6 fastfile. See log.")
    zone = open(rewrite, "rb").read()
    ff = wiiu_ff.pack(zone, internal)
    open(out_path, "wb").write(ff)
    log(f"  packed Wii U fastfile {len(ff):,} B (internal name '{internal}')")
    return out_path


def convert_soundbank(path, out_path, log=print):
    """PC .sabs/.sabl -> Wii U sound bank via sab_convert.convert_bank."""
    import sab_convert
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        sab_convert.convert_bank(path, out_path, verbose=True)
    for ln in buf.getvalue().splitlines():
        if ln.strip():
            log("  " + ln.strip())
    return out_path


def convert_ipak(path, out_path, log=print):
    """PC .ipak -> Wii U .ipak. The image payloads must be GX2-tiled per part
    (wiiu_ref/ipak.py + gx2_texture.py). A validated one-call converter is being
    finished under the pipeline's inline-texture/ipak work; if it is present we
    use it, otherwise this reports 'in development' rather than emit an unverified
    pak."""
    try:
        import ipak  # from wiiu_ref
    except Exception as e:
        raise RuntimeError(f"ipak module not importable: {e}")
    for fn in ("convert_pc_to_wiiu", "convert_pc_ipak_to_wiiu", "pc_to_wiiu"):
        conv = getattr(ipak, fn, None)
        if callable(conv):
            log(f"  ipak: using ipak.{fn}()")
            conv(path, out_path)
            return out_path
    raise RuntimeError("PC->Wii U .ipak conversion (GX2 texture tiling) is still in "
                       "development and not yet wired. This file was skipped; .ff and "
                       "sound banks convert normally.")


def convert_file(path, out_dir, oat_exe=None, log=print):
    """Dispatch one file. Output keeps the source basename, placed in out_dir.
    Returns the output path. Raises on failure (caller reports per-file)."""
    kind = detect_kind(path)
    if kind is None:
        raise ValueError(f"unsupported file type: {os.path.basename(path)}")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, os.path.basename(path))
    if os.path.abspath(out_path) == os.path.abspath(path):
        raise ValueError("output directory is the same as the source - choose a different folder "
                         "so originals are never overwritten.")
    if kind == "fastfile":
        return convert_fastfile(path, out_path, oat_exe, log)
    if kind == "soundbank":
        return convert_soundbank(path, out_path, log)
    if kind == "ipak":
        return convert_ipak(path, out_path, log)
    raise ValueError(kind)


# ---- CLI ------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Batch PC->Wii U convert (.ff/.sabs/.sabl/.ipak)")
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("-o", "--out-dir", required=True)
    ap.add_argument("--oat", help="path to Unlinker.exe (needed for .ff)")
    args = ap.parse_args()
    ok = 0
    for p in args.inputs:
        try:
            print(f"[{detect_kind(p) or '?'}] {os.path.basename(p)}")
            convert_file(p, args.out_dir, oat_exe=args.oat)
            ok += 1
            print("  -> done")
        except Exception as e:
            print(f"  -> FAILED: {e}")
    print(f"{ok}/{len(args.inputs)} converted -> {args.out_dir}")
