"""
BO2 Fastfile Workbench — GUI frontend for the Black Ops 2 fastfile
conversion toolkit (Xbox 360 / PS3 / PC -> Wii U).

Wraps the command-line tools and our extended OpenAssetTools build:
  - stfs_extract.py   : unpack an Xbox 360 LIVE/STFS DLC container
  - ff_decrypt.py     : decrypt + decompress a Wii U / PC fastfile (zlib)
  - ff_pack.py        : repack a zone into a Wii U v148 fastfile
  - zone_info.py      : inspect a decompressed zone
  - asset_dir.py      : asset-type histogram / diff two zones
  - gsc_extract.py    : extract compiled GSC/CSC scripts
  - (OAT Unlinker)    : decrypt + LZX-decompress an Xbox 360 fastfile;
                        WRITE big-endian v148 (Wii U) zones (OAT_WRITE_WIIU);
                        READ genuine Wii U fastfiles (BE asset parse);
                        signature bypass (OAT_IGNORE_SIG).

Pure standard-library (tkinter) so it runs anywhere Python does, no installs.
"""
import os
import sys
import io
import queue
import threading
import subprocess
import contextlib
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

OAT_DEFAULT = os.path.join(SCRIPT_DIR, "ref_oat", "build", "bin", "Release_x64", "Unlinker.exe")

APP_TITLE = "BO2 Fastfile Workbench"

# ---- palette ---------------------------------------------------------------
BG       = "#eef1f5"   # window background
CARD     = "#ffffff"   # card / panel background
HEADER   = "#1e293b"   # dark header banner
HEADER2  = "#0f172a"   # darker accent
ACCENT   = "#2563eb"   # primary button
ACCENT_H = "#1d4ed8"   # primary button hover
TEXT     = "#1f2937"
SUBTLE   = "#6b7280"
HINT     = "#8a93a2"
BORDER   = "#dfe3e8"

ZONE_NAME_HINT = (
    "Leave blank to use the input filename. The internal name is stored in the file AND "
    "seeds the encryption IV, so it must match the name the game loads the zone by "
    "(normally the filename without “.ff”). Only change it if you are deliberately renaming a zone."
)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1000x720")
        self.minsize(860, 600)
        self.configure(bg=BG)
        self.log_queue = queue.Queue()
        self.oat_path = tk.StringVar(value=OAT_DEFAULT if os.path.exists(OAT_DEFAULT) else "")
        self._busy = False
        self.popout = None
        self.popout_text = None

        self._build_style()
        self._build_header()
        self._build_statusbar()
        self.paned = ttk.Panedwindow(self, orient="vertical")
        self.paned.pack(fill="both", expand=True, padx=16, pady=(12, 6))
        self._build_tabs()
        self._build_log()
        self.after(80, self._drain_log)
        self.after(140, self._init_sash)

    def _init_sash(self):
        try:
            h = self.paned.winfo_height()
            if h > 100:
                self.paned.sashpos(0, int(h * 0.66))
        except tk.TclError:
            pass

    # ----------------------------------------------------------------- style
    def _build_style(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure(".", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        st.configure("TFrame", background=BG)
        st.configure("Card.TFrame", background=CARD)
        st.configure("TLabel", background=BG, foreground=TEXT)
        st.configure("Card.TLabel", background=CARD, foreground=TEXT)
        st.configure("CardTitle.TLabel", background=CARD, foreground=TEXT,
                     font=("Segoe UI Semibold", 12))
        st.configure("Sub.TLabel", background=BG, foreground=SUBTLE)
        st.configure("CardSub.TLabel", background=CARD, foreground=SUBTLE)
        st.configure("Hint.TLabel", background=CARD, foreground=HINT, font=("Segoe UI", 8))
        st.configure("Field.TLabel", background=CARD, foreground=TEXT, font=("Segoe UI Semibold", 9))
        st.configure("TEntry", fieldbackground="#ffffff", bordercolor=BORDER)
        st.configure("Card.TCheckbutton", background=CARD, foreground=TEXT, font=("Segoe UI", 9))
        st.map("Card.TCheckbutton", background=[("active", CARD)])

        # notebook
        st.configure("TNotebook", background=BG, borderwidth=0)
        st.configure("TNotebook.Tab", padding=(16, 9), font=("Segoe UI", 10),
                     background="#dde3ea", foreground=SUBTLE, borderwidth=0)
        st.map("TNotebook.Tab",
               background=[("selected", CARD)],
               foreground=[("selected", ACCENT)],
               expand=[("selected", (0, 0, 0, 0))])

        # buttons
        st.configure("TButton", padding=(12, 7), font=("Segoe UI", 10),
                     background="#e2e8f0", foreground=TEXT, borderwidth=0)
        st.map("TButton", background=[("active", "#d4dbe4")])
        st.configure("Accent.TButton", padding=(16, 9), font=("Segoe UI Semibold", 10),
                     background=ACCENT, foreground="#ffffff", borderwidth=0)
        st.map("Accent.TButton",
               background=[("active", ACCENT_H), ("disabled", "#9bb4ec")],
               foreground=[("disabled", "#eef2ff")])

    def _build_header(self):
        bar = tk.Frame(self, bg=HEADER)
        bar.pack(fill="x")
        inner = tk.Frame(bar, bg=HEADER)
        inner.pack(fill="x", padx=20, pady=(14, 12))
        tk.Label(inner, text="BO2 Fastfile Workbench", bg=HEADER, fg="#ffffff",
                 font=("Segoe UI Semibold", 17)).pack(anchor="w")
        tk.Label(inner, text="Convert Black Ops II fastfiles  ·  Xbox 360 / PS3 / PC  →  Wii U",
                 bg=HEADER, fg="#9fb3d1", font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 0))
        tk.Frame(self, bg=ACCENT, height=3).pack(fill="x")

    # ------------------------------------------------------------------ tabs
    def _build_tabs(self):
        nb = ttk.Notebook(self.paned)
        self.paned.add(nb, weight=4)
        self.nb = nb
        self._tab_convert(nb)
        self._tab_stfs(nb)
        self._tab_decrypt(nb)
        self._tab_inspect(nb)
        self._tab_gsc(nb)
        self._tab_repack(nb)
        self._tab_pcmap(nb)
        self._tab_unlink(nb)
        self._tab_settings(nb)

    # ------------------------------------------------------------- log/status
    def _build_log(self):
        wrap = ttk.Frame(self.paned, padding=(0, 6, 0, 0))
        self.paned.add(wrap, weight=1)
        head = ttk.Frame(wrap)
        head.pack(fill="x")
        ttk.Label(head, text="Output log", style="Sub.TLabel",
                  font=("Segoe UI Semibold", 9)).pack(side="left")
        ttk.Label(head, text="(drag the divider above to resize)", style="Sub.TLabel",
                  font=("Segoe UI", 8)).pack(side="left", padx=8)
        ttk.Button(head, text="Clear", command=lambda: self.log_text.delete("1.0", "end")
                   ).pack(side="right")
        ttk.Button(head, text="Pop out ⧉", command=self._popout_log
                   ).pack(side="right", padx=6)
        box = tk.Frame(wrap, bg=BORDER, bd=0)
        box.pack(fill="both", expand=True, pady=(4, 0))
        self.log_text = tk.Text(box, height=11, wrap="word", bg="#0f172a", fg="#cbd5e1",
                                insertbackground="#cbd5e1", relief="flat",
                                font=("Consolas", 9), padx=10, pady=8)
        self.log_text.pack(side="left", fill="both", expand=True, padx=1, pady=1)
        sb = ttk.Scrollbar(box, command=self.log_text.yview)
        sb.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=sb.set)

    def _build_statusbar(self):
        bar = tk.Frame(self, bg="#e2e8f0")
        bar.pack(fill="x", side="bottom")
        self.status_dot = tk.Label(bar, text="●", bg="#e2e8f0", fg="#16a34a",
                                   font=("Segoe UI", 10))
        self.status_dot.pack(side="left", padx=(14, 4), pady=4)
        self.status = tk.Label(bar, text="Ready", bg="#e2e8f0", fg=TEXT, font=("Segoe UI", 9))
        self.status.pack(side="left")
        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=160)
        self.progress.pack(side="right", padx=14, pady=4)

    # ------------------------------------------------------------------- log
    def log(self, msg=""):
        self.log_queue.put(str(msg))

    def _drain_log(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.log_text.insert("end", msg + "\n")
                self.log_text.see("end")
                if self.popout_text is not None:
                    try:
                        self.popout_text.insert("end", msg + "\n")
                        self.popout_text.see("end")
                    except tk.TclError:
                        self.popout_text = None
        except queue.Empty:
            pass
        self.after(80, self._drain_log)

    # --------------------------------------------------------- pop-out log
    def _popout_log(self):
        if self.popout is not None and self.popout.winfo_exists():
            self.popout.deiconify()
            self.popout.lift()
            return
        win = tk.Toplevel(self)
        win.title("Output log — BO2 Fastfile Workbench")
        win.geometry("900x560")
        win.configure(bg=BG)
        self.popout = win

        bar = ttk.Frame(win, padding=(10, 8))
        bar.pack(fill="x")
        ttk.Label(bar, text="Output log", style="Sub.TLabel",
                  font=("Segoe UI Semibold", 10)).pack(side="left")
        self._wrap_on = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Wrap", variable=self._wrap_on,
                        command=self._toggle_wrap).pack(side="right")
        ttk.Button(bar, text="Copy all", command=self._copy_popout).pack(side="right", padx=6)
        ttk.Button(bar, text="Clear", command=lambda: self.popout_text.delete("1.0", "end")
                   ).pack(side="right")

        box = tk.Frame(win, bg=BORDER)
        box.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        txt = tk.Text(box, wrap="word", bg="#0f172a", fg="#cbd5e1",
                      insertbackground="#cbd5e1", relief="flat",
                      font=("Consolas", 11), padx=12, pady=10, undo=False)
        txt.pack(side="left", fill="both", expand=True, padx=1, pady=1)
        sb = ttk.Scrollbar(box, command=txt.yview)
        sb.pack(side="right", fill="y")
        txt.config(yscrollcommand=sb.set)
        txt.insert("end", self.log_text.get("1.0", "end"))
        txt.see("end")
        self.popout_text = txt
        win.protocol("WM_DELETE_WINDOW", self._close_popout)

    def _close_popout(self):
        self.popout_text = None
        if self.popout is not None:
            self.popout.destroy()
            self.popout = None

    def _toggle_wrap(self):
        if self.popout_text is not None:
            self.popout_text.config(wrap="word" if self._wrap_on.get() else "none")

    def _copy_popout(self):
        if self.popout_text is None:
            return
        self.clipboard_clear()
        self.clipboard_append(self.popout_text.get("1.0", "end"))
        self.status.config(text="Log copied to clipboard")

    def set_busy(self, busy, status=None, ok=True):
        self._busy = busy
        if busy:
            self.status_dot.config(fg="#eab308")
            self.progress.start(12)
        else:
            self.status_dot.config(fg="#16a34a" if ok else "#dc2626")
            self.progress.stop()
        if status:
            self.status.config(text=status)
        elif not busy:
            self.status.config(text="Ready")

    def run_async(self, label, fn):
        if self._busy:
            messagebox.showinfo("Busy", "A task is already running. Please wait for it to finish.")
            return

        def worker():
            self.after(0, lambda: self.set_busy(True, f"Running: {label}…"))
            self.log(f"\n===== {label} =====")
            buf = io.StringIO()
            ok = True
            try:
                with contextlib.redirect_stdout(buf):
                    fn()
            except Exception as e:  # noqa: BLE001
                ok = False
                for line in buf.getvalue().splitlines():
                    self.log(line)
                self.log(f"[ERROR] {type(e).__name__}: {e}")
            else:
                for line in buf.getvalue().splitlines():
                    self.log(line)
                self.log(f"[done] {label}")
            self.after(0, lambda: self.set_busy(False, "Done" if ok else "Error", ok))

        threading.Thread(target=worker, daemon=True).start()

    # ======================================================================
    # card helper: titled white panel
    # ======================================================================
    def _card(self, parent, title, subtitle=None):
        outer = ttk.Frame(parent)
        outer.pack(fill="x", pady=(0, 12))
        card = tk.Frame(outer, bg=CARD, highlightbackground=BORDER, highlightthickness=1, bd=0)
        card.pack(fill="x")
        inner = ttk.Frame(card, style="Card.TFrame", padding=16)
        inner.pack(fill="x")
        ttk.Label(inner, text=title, style="CardTitle.TLabel").pack(anchor="w")
        if subtitle:
            ttk.Label(inner, text=subtitle, style="CardSub.TLabel",
                      wraplength=860, justify="left").pack(anchor="w", pady=(2, 8))
        else:
            ttk.Label(inner, text="", style="CardSub.TLabel").pack(anchor="w", pady=(0, 4))
        return inner

    def _scroll_tab(self, nb, text):
        """A tab whose body is a single column of cards."""
        outer = ttk.Frame(nb)
        nb.add(outer, text=text)
        body = ttk.Frame(outer, padding=(4, 10))
        body.pack(fill="both", expand=True)
        return body

    # ======================================================================
    # Tab 1: Convert
    # ======================================================================
    def _tab_convert(self, nb):
        body = self._scroll_tab(nb, "1  Convert 360 → Wii U")
        c = self._card(body, "Convert an Xbox 360 fastfile to Wii U",
                       "Decrypts and decompresses the 360 fastfile, then repacks it as a Wii U v148 "
                       "fastfile in one step.")
        self.cv_in = self._file_row(c, "Xbox 360 fastfile (.ff)", "open",
                                    [("Fastfile", "*.ff"), ("All files", "*.*")])
        self.cv_out = self._file_row(c, "Output Wii U fastfile (.ff)", "save", [("Fastfile", "*.ff")])
        self.cv_name = self._entry_row(c, "Internal zone name", hint=ZONE_NAME_HINT)
        self._actions(c, ("Convert", self._do_convert, True))
        self._note(c, "The repacked file carries a zero RSA signature (we cannot sign). Whether it "
                      "loads depends on your Wii U accepting unsigned / signature-bypassed fastfiles.")

    def _do_convert(self):
        src = self.cv_in.get().strip(); dst = self.cv_out.get().strip()
        name = self.cv_name.get().strip() or os.path.splitext(os.path.basename(src))[0]
        if not (src and dst):
            messagebox.showwarning("Missing", "Pick an input and output file.")
            return
        oat = self.oat_path.get().strip()

        def task():
            import ff_decrypt, ff_pack
            data = open(src, "rb").read()
            endian, key, ver, label = ff_decrypt.detect_platform(data)
            print(f"input platform: {label} (v{ver})")
            if ver == 146:
                if not (oat and os.path.exists(oat)):
                    raise RuntimeError("Xbox 360 input needs the OAT Unlinker.exe — set its path in Settings.")
                zone = decompress_with_oat(src, oat, self.log)
            else:
                _, zone, n = ff_decrypt.decrypt_ff(data, key, endian)
                print(f"decrypted+inflated: {len(zone)} bytes, {n} chunks")
            ff = ff_pack.pack_ff(zone, name)
            open(dst, "wb").write(ff)
            print(f"wrote Wii U v148 fastfile: {dst}  ({len(ff):,} bytes, name={name!r})")
        self.run_async("Convert 360 → Wii U", task)

    # ======================================================================
    # Tab 2: STFS
    # ======================================================================
    def _tab_stfs(self, nb):
        body = self._scroll_tab(nb, "2  Unpack DLC")
        c = self._card(body, "Unpack an Xbox 360 DLC container",
                       "Reads a LIVE / CON / PIRS (STFS) container and extracts the files inside "
                       "(fastfiles, ipak, sound banks).")
        self.stfs_in = self._file_row(c, "STFS container", "open", [("All files", "*.*")])
        self.stfs_out = self._dir_row(c, "Output folder")
        self._actions(c, ("List contents", self._do_stfs_list, False),
                         ("Extract all", self._do_stfs_extract, True))

    def _do_stfs_list(self):
        path = self.stfs_in.get().strip()
        if not path:
            return
        def task():
            import stfs_extract
            s = stfs_extract.STFS(path)
            files = [l for l in s.listings if not l["isdir"]]
            print(f"{len(files)} files:")
            for fl in s.listings:
                print(("  [D] " if fl["isdir"] else "      ") + s.fullpath(fl) +
                      ("" if fl["isdir"] else f"   {fl['size']:,} bytes"))
        self.run_async("STFS list", task)

    def _do_stfs_extract(self):
        path = self.stfs_in.get().strip(); out = self.stfs_out.get().strip()
        if not (path and out):
            messagebox.showwarning("Missing", "Pick a container and output folder.")
            return
        def task():
            import stfs_extract
            os.makedirs(out, exist_ok=True)
            stfs_extract.STFS(path).extract_all(out)
        self.run_async("STFS extract", task)

    # ======================================================================
    # Tab 3: Decrypt
    # ======================================================================
    def _tab_decrypt(self, nb):
        body = self._scroll_tab(nb, "3  Decrypt → Zone")
        c = self._card(body, "Decrypt & decompress a fastfile",
                       "Writes the raw zone. Platform is auto-detected: Wii U / PC use the built-in "
                       "Salsa20 + zlib path; Xbox 360 is routed through OAT (LZX).")
        self.dec_in = self._file_row(c, "Fastfile (.ff)", "open",
                                     [("Fastfile", "*.ff"), ("All files", "*.*")])
        self.dec_out = self._file_row(c, "Output zone (.zone)", "save", [("Zone", "*.zone")])
        self._actions(c, ("Detect platform", self._do_detect, False),
                         ("Decrypt → zone", self._do_decrypt, True))

    def _do_detect(self):
        path = self.dec_in.get().strip()
        if not path:
            return
        def task():
            import ff_decrypt
            data = open(path, "rb").read(16)
            endian, key, ver, label = ff_decrypt.detect_platform(data)
            print(f"magic={data[:8]!r}  platform={label}  version={ver}  "
                  f"endian={'BE' if endian=='>' else 'LE'}")
        self.run_async("Detect platform", task)

    def _do_decrypt(self):
        path = self.dec_in.get().strip(); out = self.dec_out.get().strip()
        if not (path and out):
            messagebox.showwarning("Missing", "Pick an input fastfile and output zone path.")
            return
        oat = self.oat_path.get().strip()
        def task():
            import ff_decrypt
            data = open(path, "rb").read()
            endian, key, ver, label = ff_decrypt.detect_platform(data)
            print(f"platform: {label} (v{ver})")
            if ver == 146:
                if not (oat and os.path.exists(oat)):
                    raise RuntimeError("Xbox 360 input needs OAT Unlinker.exe — set its path in Settings.")
                zone = decompress_with_oat(path, oat, self.log)
            else:
                _, zone, n = ff_decrypt.decrypt_ff(data, key, endian)
                print(f"{n} chunks")
            open(out, "wb").write(zone)
            print(f"wrote zone: {out}  ({len(zone):,} bytes)")
        self.run_async("Decrypt → zone", task)

    # ======================================================================
    # Tab 4: Inspect
    # ======================================================================
    def _tab_inspect(self, nb):
        body = self._scroll_tab(nb, "4  Inspect")
        c = self._card(body, "Inspect a zone (or diff two)",
                       "Show the header, block sizes, asset list and script strings — or diff the "
                       "asset-type histograms of two zones.")
        self.insp_a = self._file_row(c, "Zone A (.zone)", "open", [("Zone", "*.zone"), ("All", "*.*")])
        self.insp_b = self._file_row(c, "Zone B (optional, for diff)", "open",
                                     [("Zone", "*.zone"), ("All", "*.*")])
        self._actions(c, ("Inspect A", self._do_inspect, True),
                         ("Asset histogram / diff", self._do_assetdir, False))

    def _do_inspect(self):
        a = self.insp_a.get().strip()
        if not a:
            return
        def task():
            import zone_info
            zone_info.inspect(a)
        self.run_async("Inspect zone", task)

    def _do_assetdir(self):
        a = self.insp_a.get().strip(); b = self.insp_b.get().strip()
        if not a:
            return
        def task():
            import asset_dir
            paths = [a] + ([b] if b else [])
            results = [(p, *asset_dir.read_dir(p)) for p in paths]
            for p, e, n, types in results:
                print(f"{os.path.basename(p)}: endian={'LE' if e=='<' else 'BE'} assetCount={n}")
            hs = [asset_dir.histo(t) for *_, t in results]
            all_t = sorted({t for *_, types in results for t in set(types)})
            cols = "  ".join(f"{os.path.basename(p)[:16]:>16}" for p, *_ in results)
            print(f"\n{'type':<22} {cols}")
            for t in all_t:
                cells = "  ".join(f"{h.get(t,0):>16}" for h in hs)
                flag = "  <-- differs" if len(hs) == 2 and hs[0].get(t,0) != hs[1].get(t,0) else ""
                print(f"{asset_dir.name(t):<22} {cells}{flag}")
        self.run_async("Asset histogram / diff", task)

    # ======================================================================
    # Tab 5: GSC
    # ======================================================================
    def _tab_gsc(self, nb):
        body = self._scroll_tab(nb, "5  Extract GSC")
        c = self._card(body, "Extract compiled scripts",
                       "Pulls ScriptParseTree (compiled GSC/CSC) assets out of a zone. Feed the output "
                       "to the Cerberus decompiler.")
        self.gsc_in = self._file_row(c, "Zone (.zone)", "open", [("Zone", "*.zone"), ("All", "*.*")])
        self.gsc_out = self._dir_row(c, "Output folder")
        self._actions(c, ("Extract scripts", self._do_gsc, True))

    def _do_gsc(self):
        a = self.gsc_in.get().strip(); out = self.gsc_out.get().strip()
        if not (a and out):
            messagebox.showwarning("Missing", "Pick a zone and output folder.")
            return
        def task():
            import gsc_extract
            os.makedirs(out, exist_ok=True)
            gsc_extract.extract(a, out)
        self.run_async("Extract GSC", task)

    # ======================================================================
    # Tab 6: Repack
    # ======================================================================
    def _tab_repack(self, nb):
        body = self._scroll_tab(nb, "6  Repack → Wii U")
        c = self._card(body, "Repack a zone into a Wii U fastfile",
                       "Packs a raw zone into a Wii U v148 fastfile (zlib + Salsa20 with the Wii U key).")
        self.rp_in = self._file_row(c, "Zone (.zone)", "open", [("Zone", "*.zone"), ("All", "*.*")])
        self.rp_out = self._file_row(c, "Output fastfile (.ff)", "save", [("Fastfile", "*.ff")])
        self.rp_name = self._entry_row(c, "Internal zone name", hint=ZONE_NAME_HINT)
        self._actions(c, ("Repack", self._do_repack, True))

    def _do_repack(self):
        a = self.rp_in.get().strip(); out = self.rp_out.get().strip()
        name = self.rp_name.get().strip() or os.path.splitext(os.path.basename(a))[0]
        if not (a and out):
            messagebox.showwarning("Missing", "Pick a zone and output file.")
            return
        def task():
            import ff_pack
            zone = open(a, "rb").read()
            ff = ff_pack.pack_ff(zone, name)
            open(out, "wb").write(ff)
            print(f"packed {len(zone):,} byte zone -> {len(ff):,} byte ff  (name={name!r})")
        self.run_async("Repack → Wii U", task)

    # ======================================================================
    # Tab 7: PC Map -> Wii U  (OAT big-endian v148 writer)
    # ======================================================================
    def _tab_pcmap(self, nb):
        body = self._scroll_tab(nb, "7  PC Map → Wii U")
        c = self._card(body, "Convert a PC custom-map fastfile to Wii U",
                       "Loads a PC (v147) map .ff built by the T6 Custom Map Tool, re-serializes it as "
                       "a big-endian v148 Wii U zone (byte-swap + PC→console enum remap) using our OAT "
                       "build, then packs it into a Wii U fastfile. Requires the Unlinker.exe (Settings).")
        self.pm_in = self._file_row(c, "PC map fastfile (.ff)", "open",
                                    [("Fastfile", "*.ff"), ("All files", "*.*")])
        self.pm_out = self._file_row(c, "Output Wii U fastfile (.ff)", "save", [("Fastfile", "*.ff")])
        self.pm_name = self._entry_row(c, "Internal zone name", hint=ZONE_NAME_HINT)
        self.pm_remap = tk.BooleanVar(value=False)
        ttk.Checkbutton(c, variable=self.pm_remap, style="Card.TCheckbutton",
                        text="Apply experimental TEMP→VIRTUAL block remap (known-broken — diagnostic only)"
                        ).pack(anchor="w", pady=(8, 0))
        self._actions(c, ("Convert PC → Wii U", self._do_pcmap, True))
        self._note(c, "Serialization is validated (byte-perfect round-trip), but a converted map does "
                      "NOT yet load on Wii U: the zone keeps PC's block policy (megabytes in TEMP) "
                      "which overflows the Wii U's tiny TEMP buffer. See WIIU_MAP_CONVERSION.md. This "
                      "tab is for development/diagnosis until the block-policy relocation lands.")

    def _do_pcmap(self):
        src = self.pm_in.get().strip(); dst = self.pm_out.get().strip()
        name = self.pm_name.get().strip() or os.path.splitext(os.path.basename(src))[0]
        if not (src and dst):
            messagebox.showwarning("Missing", "Pick an input PC .ff and output .ff.")
            return
        oat = self.oat_path.get().strip()
        if not (oat and os.path.exists(oat)):
            messagebox.showwarning("OAT needed", "Set the OAT Unlinker.exe path in Settings.")
            return
        remap = self.pm_remap.get()

        def task():
            convert_pc_to_wiiu(src, oat, dst, name, remap, self.log)
        self.run_async("PC map → Wii U", task)

    # ======================================================================
    # Tab 8: Unlink / List  (OAT — works on PC, 360, AND Wii U fastfiles)
    # ======================================================================
    def _tab_unlink(self, nb):
        body = self._scroll_tab(nb, "8  Unlink / List")
        c = self._card(body, "List or dump assets with OpenAssetTools",
                       "Runs our OAT build on any T6 fastfile — PC, Xbox 360, or Wii U (our build now "
                       "decrypts and parses genuine Wii U fastfiles). 'List' prints the asset directory; "
                       "'Dump' unlinks extractable assets to a folder. Signature check is bypassed.")
        self.ul_in = self._file_row(c, "Fastfile (.ff)", "open",
                                    [("Fastfile", "*.ff"), ("All files", "*.*")])
        self.ul_out = self._dir_row(c, "Dump output folder (for Dump)")
        self._actions(c, ("List assets", self._do_unlink_list, True),
                         ("Dump assets", self._do_unlink_dump, False))
        self._note(c, "Note: GPU assets (techset / gfxworld / xmodel) on console zones may stop the "
                      "parse at a RUNTIME_PHYSICAL back-reference — that is the GPU-format wall, not a "
                      "container error. The data tier (scripts, tables, etc.) lists/dumps fine.")

    def _do_unlink_list(self):
        path = self.ul_in.get().strip()
        if not path:
            return
        oat = self.oat_path.get().strip()
        if not (oat and os.path.exists(oat)):
            messagebox.showwarning("OAT needed", "Set the OAT Unlinker.exe path in Settings.")
            return
        def task():
            oat_unlink(path, oat, True, None, self.log)
        self.run_async("OAT list", task)

    def _do_unlink_dump(self):
        path = self.ul_in.get().strip(); out = self.ul_out.get().strip()
        if not path:
            return
        oat = self.oat_path.get().strip()
        if not (oat and os.path.exists(oat)):
            messagebox.showwarning("OAT needed", "Set the OAT Unlinker.exe path in Settings.")
            return
        if not out:
            messagebox.showwarning("Missing", "Pick a dump output folder.")
            return
        def task():
            os.makedirs(out, exist_ok=True)
            oat_unlink(path, oat, False, out, self.log)
        self.run_async("OAT dump", task)

    # ======================================================================
    # Tab 9: Settings
    # ======================================================================
    def _tab_settings(self, nb):
        body = self._scroll_tab(nb, "Settings")
        c = self._card(body, "OpenAssetTools",
                       "Needed only for Xbox 360 files (LZX decompression). Point this at the "
                       "Unlinker.exe you built from tools/ref_oat.")
        row = ttk.Frame(c, style="Card.TFrame")
        row.pack(fill="x", pady=(2, 2))
        ent = ttk.Entry(row, textvariable=self.oat_path)
        ent.pack(side="left", fill="x", expand=True, ipady=3)
        ttk.Button(row, text="Browse…",
                   command=lambda: self._pick_into(self.oat_path, "open",
                                                   [("Unlinker", "Unlinker.exe"), ("All", "*.*")])
                   ).pack(side="left", padx=(8, 0))
        self.oat_status = ttk.Label(c, style="Hint.TLabel", text="")
        self.oat_status.pack(anchor="w", pady=(6, 0))
        self._refresh_oat_status()
        self.oat_path.trace_add("write", lambda *_: self._refresh_oat_status())

        c2 = self._card(body, "About")
        ttk.Label(c2, style="CardSub.TLabel", wraplength=860, justify="left",
                  text="BO2 Fastfile Workbench converts Black Ops II fastfiles to Wii U. Wii U / PC "
                       "use a pure-Python Salsa20 + zlib pipeline; Xbox 360 uses our OpenAssetTools "
                       "build (with the LZX fix) for XMemCompress. Our OAT build also WRITES "
                       "big-endian v148 (Wii U) zones and READS genuine Wii U fastfiles — see the "
                       "'PC Map → Wii U' and 'Unlink / List' tabs. Repacked files use a zero RSA "
                       "signature (loading depends on a signature-check bypass on the target). "
                       "Note: a converted map's serialization is validated, but it does not yet load "
                       "on Wii U pending the block-policy relocation (see WIIU_MAP_CONVERSION.md)."
                  ).pack(anchor="w")

    def _refresh_oat_status(self):
        if not hasattr(self, "oat_status"):
            return
        ok = os.path.exists(self.oat_path.get().strip())
        self.oat_status.config(text=("✓ Unlinker found" if ok else
                                     "Not set — required for Xbox 360 (.ff v146) files"),
                               foreground=("#16a34a" if ok else "#dc2626"))

    # ----------------------------------------------------------------------
    # reusable widgets
    # ----------------------------------------------------------------------
    def _file_row(self, parent, label, mode, types):
        ttk.Label(parent, text=label, style="Field.TLabel").pack(anchor="w", pady=(8, 2))
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill="x")
        var = tk.StringVar()
        ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True, ipady=3)
        ttk.Button(row, text="Browse…",
                   command=lambda: self._pick_into(var, mode, types)).pack(side="left", padx=(8, 0))
        return var

    def _dir_row(self, parent, label):
        ttk.Label(parent, text=label, style="Field.TLabel").pack(anchor="w", pady=(8, 2))
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill="x")
        var = tk.StringVar()
        ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True, ipady=3)
        ttk.Button(row, text="Browse…",
                   command=lambda: var.set(filedialog.askdirectory() or var.get())
                   ).pack(side="left", padx=(8, 0))
        return var

    def _entry_row(self, parent, label, default="", hint=None):
        ttk.Label(parent, text=label, style="Field.TLabel").pack(anchor="w", pady=(8, 2))
        var = tk.StringVar(value=default)
        ttk.Entry(parent, textvariable=var).pack(fill="x", ipady=3)
        if hint:
            ttk.Label(parent, text=hint, style="Hint.TLabel",
                      wraplength=860, justify="left").pack(anchor="w", pady=(3, 0))
        return var

    def _actions(self, parent, *buttons):
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(anchor="w", pady=(14, 0))
        for i, (text, cmd, primary) in enumerate(buttons):
            ttk.Button(row, text=text, command=cmd,
                       style="Accent.TButton" if primary else "TButton"
                       ).pack(side="left", padx=(0 if i == 0 else 8, 0))

    def _note(self, parent, text):
        ttk.Label(parent, text="ⓘ  " + text, style="Hint.TLabel",
                  wraplength=860, justify="left").pack(anchor="w", pady=(12, 0))

    def _pick_into(self, var, mode, types):
        if mode == "save":
            p = filedialog.asksaveasfilename(
                filetypes=types,
                defaultextension=types[0][1].replace("*", "") if types else "")
        else:
            p = filedialog.askopenfilename(filetypes=types)
        if p:
            var.set(p)


# ----------------------------------------------------------------------------
def _run_oat(args, workdir, env_extra, log, prefix="oat"):
    """Run an OAT command, streaming non-debug output to the log. Returns the CompletedProcess."""
    env = dict(os.environ)
    env.update(env_extra or {})
    proc = subprocess.run(args, cwd=workdir, capture_output=True, text=True, env=env)
    for line in (proc.stdout + proc.stderr).splitlines():
        s = line.strip()
        if s and not s.startswith("[DBG]"):
            log(f"  {prefix}: " + s)
    return proc


def convert_pc_to_wiiu(ff_path, oat_exe, out_ff, name, remap, log):
    """PC map .ff -> Wii U .ff via OAT's big-endian v148 writer, then ff_pack.

    Runs the Unlinker with OAT_WRITE_WIIU (and OAT_REWRITE / OAT_IGNORE_SIG) which emits a raw
    decompressed big-endian v148 zone next to the exe as <internalName>_rewrite.ff; that zone is
    then containerized into a Wii U fastfile with ff_pack.
    """
    import ff_pack
    workdir = os.path.dirname(oat_exe)
    base = os.path.splitext(os.path.basename(ff_path))[0]
    rewrite = os.path.join(workdir, base + "_rewrite.ff")
    if os.path.exists(rewrite):
        os.remove(rewrite)
    env = {"OAT_IGNORE_SIG": "1", "OAT_REWRITE": "1", "OAT_WRITE_WIIU": "1"}
    if remap:
        env["OAT_WIIU_BLOCKREMAP"] = "1"
        log("  [warn] TEMP→VIRTUAL block remap enabled (diagnostic; known to break alias pointers)")
    log(f"  running OAT BE v148 writer on {os.path.basename(ff_path)} …")
    _run_oat([oat_exe, "--list", ff_path], workdir, env, log)
    if not os.path.exists(rewrite):
        raise RuntimeError("OAT did not produce the raw BE zone (<name>_rewrite.ff). See log — the "
                           "input must be a T6 fastfile and its filename must match its internal name.")
    zone = open(rewrite, "rb").read()
    log(f"  raw big-endian v148 zone: {len(zone):,} bytes")
    ff = ff_pack.pack_ff(zone, name)
    open(out_ff, "wb").write(ff)
    log(f"  wrote Wii U fastfile: {out_ff}  ({len(ff):,} bytes, name={name!r})")


def oat_unlink(ff_path, oat_exe, list_only, out_dir, log):
    """Run OAT Unlinker on any T6 fastfile (PC / 360 / Wii U). Signature check bypassed."""
    workdir = os.path.dirname(oat_exe)
    args = [oat_exe, "--list"] if list_only else [oat_exe, "-o", out_dir]
    args.append(ff_path)
    log(f"  running OAT on {os.path.basename(ff_path)} …")
    _run_oat(args, workdir, {"OAT_IGNORE_SIG": "1"}, log)
    if not list_only:
        log(f"  dump complete → {out_dir}")


def decompress_with_oat(ff_path, oat_exe, log):
    """Run OAT Unlinker to decrypt + LZX-decompress a 360 fastfile, return raw zone bytes."""
    workdir = os.path.dirname(oat_exe)
    base = os.path.splitext(os.path.basename(ff_path))[0]
    dat = os.path.join(workdir, base + ".dat")
    if os.path.exists(dat):
        os.remove(dat)
    log(f"  running OAT Unlinker on {os.path.basename(ff_path)} …")
    proc = subprocess.run([oat_exe, ff_path], cwd=workdir, capture_output=True, text=True)
    for line in (proc.stdout + proc.stderr).splitlines():
        if line.strip():
            log("  oat: " + line.strip())
    if not os.path.exists(dat):
        raise RuntimeError("OAT did not produce a .dat dump (see log).")
    data = open(dat, "rb").read()
    log(f"  decompressed zone: {len(data):,} bytes")
    return data


if __name__ == "__main__":
    App().mainloop()
