"""
Wii U Fastfile Studio
=====================

A desktop front-end for working with Black Ops II (T6) Wii U fastfiles.

Two modes:
  * Simple   - the flat format conversions (fastfile <-> zone, list assets).
  * Advanced - the full toolkit (structural validate, in-zone script/rawfile
               editor, and the extended OpenAssetTools console read / v148
               write / decompressed dump paths).

Pure standard library (tkinter) -- no third-party imports -- so it runs
anywhere Python 3 does and freezes cleanly to a single EXE.
"""
import os
import sys
import io
import queue
import threading
import subprocess
import contextlib
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)

import wiiu_ff
import zone_validate
import ff_assets
import batch_convert

APP_TITLE = "Wii U Fastfile Studio"
APP_VERSION = "2.0"

# Default location of the extended OpenAssetTools Unlinker, relative to this app.
OAT_DEFAULT_CANDIDATES = [
    os.path.join(APP_DIR, "oat", "Unlinker.exe"),
    os.path.join(APP_DIR, "Unlinker.exe"),
]

# ---- palette --------------------------------------------------------------
BG       = "#0f1420"   # content background
SIDEBAR  = "#0b0f18"   # nav rail
CARD     = "#1a2233"
HEADER   = "#0b0f18"
ACCENT   = "#18b4a8"
ACCENT2  = "#0e8f86"
TEXT     = "#e6edf3"
MUTED    = "#9aa7b8"
FAINT    = "#5f6c80"
BORDER   = "#26324a"
FIELD    = "#0c1220"
HOVER    = "#141d2c"


def find_oat_default():
    for c in OAT_DEFAULT_CANDIDATES:
        if os.path.isfile(c):
            return c
    return ""


class Studio(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE} {APP_VERSION}")
        self.geometry("1060x760")
        self.minsize(880, 620)
        self.configure(bg=BG)
        try:
            self.iconbitmap(os.path.join(getattr(sys, "_MEIPASS", APP_DIR), "studio.ico"))
        except Exception:
            pass

        self._busy = False
        self._logq = queue.Queue()
        self.mode = "simple"           # "simple" | "advanced"
        self.pages = {}                # key -> built page frame (cache)
        self.nav_items = {}            # key -> (row, bar, label) for active styling
        self.active_key = None

        self._style()
        self._banner()
        self._main()
        self._log_pane()
        self._statusbar()

        self._build_nav()
        self._show_page(self._first_key())
        self.after(60, self._drain_log)

    # -- page catalog -------------------------------------------------------
    def _catalog(self):
        # (key, group, label, title, subtitle, simple?, builder)
        return [
            ("batch",    "Convert", "Batch Convert → Wii U",
             "Batch Convert  ·  PC → Wii U",
             "Drop in fastfiles, sound banks and image paks together — each is converted to its "
             "Wii U version and written to your output folder under its original name.",
             True, self._page_batch),
            ("decrypt",  "Convert", "Fastfile → Zone",
             "Fastfile → Zone", "Decrypt and decompress a Wii U .ff into its raw zone.",
             True, self._page_decrypt),
            ("repack",   "Convert", "Zone → Fastfile",
             "Zone → Fastfile", "Pack a decompressed zone back into a Wii U v148 fastfile.",
             True, self._page_repack),
            ("pipeline", "Convert", "PC Fastfile → Wii U + IPAK",
             "PC Fastfile  →  Wii U Fastfile + IPAK",
             "Feed a PC (Plutonium/T6) map fastfile and run the whole pipeline end to end: "
             "unlink → PC-to-console zone conversion → repack as a Wii U .ff, plus author the "
             "map's image .ipak from the PC sources.",
             True, self._page_pipeline),
            ("read",     "Inspect", "Read Assets",
             "Read a Wii U fastfile's assets",
             "List the assets in a genuine big-endian Wii U (v148) fastfile through OpenAssetTools.",
             True, self._page_read),
            ("dump",     "Inspect", "Dump Zone",
             "Dump the decompressed zone",
             "Decompress a fastfile and write its raw decompressed content to a file.",
             False, self._page_dump),
            ("validate", "Inspect", "Validate Zone",
             "Structural zone validator",
             "Check a decompressed zone against genuine Wii U loader conventions.",
             False, self._page_validate),
            ("editor",   "Edit", "Zone Editor",
             "Browse & edit zone contents",
             "List, export and in-place replace the scripts and rawfiles inside a zone.",
             False, self._page_editor),
            ("write",    "Build", "Write Wii U Zone",
             "Write a big-endian v148 Wii U zone",
             "Re-emit a fastfile as a big-endian Wii U (v148) zone with the write-path transforms.",
             False, self._page_write),
            ("sigpatch", "Console", "RPL Signature Patch",
             "Patch a T6 engine RPL to bypass the fastfile signature check",
             "Neutralize __DBX_AuthLoad_ValidateSignature_Try in a Black Ops II engine RPL so the game "
             "loads zeroed-signature (custom / repacked) fastfiles.",
             True, self._page_sigpatch),
            ("about",    "Help", "About",
             f"{APP_TITLE}  {APP_VERSION}", "Tools for Black Ops II (T6) Wii U fastfiles.",
             True, self._page_about),
        ]

    def _visible_catalog(self):
        return [c for c in self._catalog() if self.mode == "advanced" or c[5]]

    def _first_key(self):
        return self._visible_catalog()[0][0]

    def _meta(self, key):
        for c in self._catalog():
            if c[0] == key:
                return c
        return None

    # -- theming ------------------------------------------------------------
    def _style(self):
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
        st.configure("H.TLabel", background=CARD, foreground=TEXT, font=("Segoe UI Semibold", 15))
        st.configure("Sub.TLabel", background=CARD, foreground=MUTED, font=("Segoe UI", 9))
        st.configure("TCheckbutton", background=CARD, foreground=TEXT)
        st.map("TCheckbutton", background=[("active", CARD)])
        st.configure("TEntry", fieldbackground=FIELD, foreground=TEXT, bordercolor=BORDER,
                     insertcolor=TEXT)
        st.configure("Accent.TButton", background=ACCENT, foreground="#03110f",
                     font=("Segoe UI Semibold", 10), borderwidth=0, padding=(16, 9))
        st.map("Accent.TButton", background=[("active", ACCENT2), ("disabled", BORDER)],
               foreground=[("disabled", MUTED)])
        st.configure("Ghost.TButton", background=CARD, foreground=TEXT,
                     borderwidth=1, padding=(10, 6))
        st.map("Ghost.TButton", background=[("active", BORDER)])
        st.configure("TProgressbar", background=ACCENT, troughcolor=HEADER, borderwidth=0)
        st.configure("FE.Treeview", background=FIELD, fieldbackground=FIELD, foreground=TEXT,
                     rowheight=22, borderwidth=0)
        st.configure("FE.Treeview.Heading", background=HEADER, foreground=MUTED, font=("Segoe UI", 9))
        st.map("FE.Treeview", background=[("selected", ACCENT2)], foreground=[("selected", "#03110f")])

    # -- banner (title + mode toggle) --------------------------------------
    def _banner(self):
        bar = tk.Frame(self, bg=HEADER, height=60)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(bar, text="   Wii U Fastfile Studio", bg=HEADER, fg=TEXT,
                 font=("Segoe UI Semibold", 16)).pack(side="left", pady=12)
        tk.Label(bar, text="T6  ·  v148  ·  big-endian    ", bg=HEADER, fg=FAINT,
                 font=("Segoe UI", 10)).pack(side="right", pady=20)

        # segmented Simple / Advanced control
        seg = tk.Frame(bar, bg=BORDER)
        seg.pack(side="right", pady=14, padx=6)
        self._seg = {}
        for m, lbl in (("simple", "Simple"), ("advanced", "Advanced")):
            b = tk.Label(seg, text=lbl, bg=SIDEBAR, fg=MUTED, padx=16, pady=6,
                         font=("Segoe UI Semibold", 9), cursor="hand2")
            b.pack(side="left", padx=1, pady=1)
            b.bind("<Button-1>", lambda _e, mm=m: self._set_mode(mm))
            self._seg[m] = b
        self._paint_seg()
        tk.Frame(self, bg=ACCENT, height=2).pack(fill="x")

    def _paint_seg(self):
        for m, b in self._seg.items():
            if m == self.mode:
                b.configure(bg=ACCENT, fg="#03110f")
            else:
                b.configure(bg=SIDEBAR, fg=MUTED)

    def _set_mode(self, m):
        if m == self.mode:
            return
        self.mode = m
        self._paint_seg()
        self._build_nav()
        # keep the current page if still visible, else jump to the first one
        keys = [c[0] for c in self._visible_catalog()]
        self._show_page(self.active_key if self.active_key in keys else self._first_key())

    # -- main split: sidebar + content -------------------------------------
    def _main(self):
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)
        self.side = tk.Frame(body, bg=SIDEBAR, width=210)
        self.side.pack(side="left", fill="y")
        self.side.pack_propagate(False)
        self.content = tk.Frame(body, bg=BG)
        self.content.pack(side="left", fill="both", expand=True)

    def _build_nav(self):
        for w in self.side.winfo_children():
            w.destroy()
        self.nav_items = {}
        tk.Frame(self.side, bg=SIDEBAR, height=8).pack(fill="x")
        last_group = None
        for key, group, label, *_ in self._visible_catalog():
            if group != last_group:
                tk.Label(self.side, text=group.upper(), bg=SIDEBAR, fg=FAINT,
                         font=("Segoe UI Semibold", 8), anchor="w").pack(
                    fill="x", padx=16, pady=(14, 4))
                last_group = group
            self._nav_item(key, label)

    def _nav_item(self, key, label):
        row = tk.Frame(self.side, bg=SIDEBAR, cursor="hand2")
        row.pack(fill="x")
        bar = tk.Frame(row, bg=SIDEBAR, width=3)
        bar.pack(side="left", fill="y")
        lbl = tk.Label(row, text=label, bg=SIDEBAR, fg=MUTED, anchor="w",
                       font=("Segoe UI", 10), padx=13, pady=9)
        lbl.pack(side="left", fill="x", expand=True)
        self.nav_items[key] = (row, bar, lbl)

        def enter(_e):
            if self.active_key != key:
                row.configure(bg=HOVER); lbl.configure(bg=HOVER)

        def leave(_e):
            if self.active_key != key:
                row.configure(bg=SIDEBAR); lbl.configure(bg=SIDEBAR)
        for w in (row, lbl):
            w.bind("<Enter>", enter)
            w.bind("<Leave>", leave)
            w.bind("<Button-1>", lambda _e, k=key: self._show_page(k))

    def _paint_nav(self):
        for key, (row, bar, lbl) in self.nav_items.items():
            active = key == self.active_key
            row.configure(bg=BG if active else SIDEBAR)
            lbl.configure(bg=BG if active else SIDEBAR, fg=TEXT if active else MUTED,
                          font=("Segoe UI Semibold", 10) if active else ("Segoe UI", 10))
            bar.configure(bg=ACCENT if active else SIDEBAR)

    def _show_page(self, key):
        if key not in self.pages:
            meta = self._meta(key)
            page = tk.Frame(self.content, bg=BG)
            self.pages[key] = page
            meta[6](page)                # call the builder
        for k, pg in self.pages.items():
            pg.pack_forget()
        self.pages[key].pack(fill="both", expand=True)
        self.active_key = key
        self._paint_nav()

    # -- log pane + status --------------------------------------------------
    def _log_pane(self):
        wrap = tk.Frame(self, bg=BG)
        wrap.pack(fill="both", expand=False, padx=12, pady=(0, 6))
        head = tk.Frame(wrap, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="Output log", bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")
        ttk.Button(head, text="Clear", style="Ghost.TButton",
                   command=lambda: self.log.delete("1.0", "end")).pack(side="right")
        box = tk.Frame(wrap, bg=BORDER)
        box.pack(fill="both", expand=True, pady=(4, 0))
        self.log = tk.Text(box, height=9, bg=FIELD, fg="#cfe9e5", insertbackground=TEXT,
                           relief="flat", wrap="word", font=("Consolas", 9), bd=0)
        sb = ttk.Scrollbar(box, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True, padx=1, pady=1)

    def _statusbar(self):
        bar = tk.Frame(self, bg=HEADER, height=26)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        self.status = tk.Label(bar, text="Ready", bg=HEADER, fg=MUTED, font=("Segoe UI", 9))
        self.status.pack(side="left", padx=10)
        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=150)
        self.progress.pack(side="right", padx=10, pady=4)

    # -- shared UI helpers --------------------------------------------------
    def _card(self, parent, title, subtitle):
        outer = ttk.Frame(parent, padding=16)
        outer.pack(fill="both", expand=True)
        card = tk.Frame(outer, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="both", expand=True)
        pad = ttk.Frame(card, style="Card.TFrame", padding=20)
        pad.pack(fill="both", expand=True)
        ttk.Label(pad, text=title, style="H.TLabel").pack(anchor="w")
        ttk.Label(pad, text=subtitle, style="Sub.TLabel").pack(anchor="w", pady=(3, 16))
        return pad

    def _file_row(self, parent, label, var, save=False, types=None, dirpick=False):
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, style="Card.TLabel", width=16).pack(side="left")
        ent = ttk.Entry(row, textvariable=var)
        ent.pack(side="left", fill="x", expand=True, padx=(0, 8))

        def browse():
            if dirpick:
                p = filedialog.askdirectory()
            elif save:
                p = filedialog.asksaveasfilename(filetypes=types or [])
            else:
                p = filedialog.askopenfilename(filetypes=types or [])
            if p:
                var.set(p)
        ttk.Button(row, text="Browse", style="Ghost.TButton", command=browse).pack(side="left")
        return ent

    def _note(self, parent, text):
        ttk.Label(parent, text=text, style="Sub.TLabel", wraplength=860,
                  justify="left").pack(anchor="w", pady=(10, 0))

    def _run_btn(self, parent, text, fn):
        b = ttk.Button(parent, text=text, style="Accent.TButton", command=fn)
        b.pack(anchor="w", pady=(18, 0))
        return b

    def _oat_row(self, parent, var):
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="Unlinker.exe", style="Card.TLabel", width=16).pack(side="left")
        ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True, padx=(0, 8))

        def browse():
            p = filedialog.askopenfilename(filetypes=[("Unlinker", "Unlinker.exe"), ("All", "*.*")])
            if p:
                var.set(p)
        ttk.Button(row, text="Browse", style="Ghost.TButton", command=browse).pack(side="left")

    # -- log / task plumbing ------------------------------------------------
    def log_line(self, s):
        self._logq.put(s)

    def _drain_log(self):
        try:
            while True:
                s = self._logq.get_nowait()
                self.log.insert("end", s + "\n")
                self.log.see("end")
        except queue.Empty:
            pass
        self.after(60, self._drain_log)

    def _set_busy(self, on, msg="Ready"):
        self._busy = on
        self.status.config(text=msg)
        if on:
            self.progress.start(12)
        else:
            self.progress.stop()

    def _task(self, name, fn):
        if self._busy:
            messagebox.showinfo(APP_TITLE, "A task is already running.")
            return
        self._set_busy(True, name + "...")
        self.log_line(f"\n=== {name} ===")

        def worker():
            try:
                fn()
                self.log_line(f"[done] {name}")
                self.after(0, lambda: self._set_busy(False, "Done"))
            except Exception as e:
                self.log_line(f"[error] {e}")
                self.after(0, lambda: self._set_busy(False, "Error"))
        threading.Thread(target=worker, daemon=True).start()

    def _run_oat(self, exe, ff_path, env_extra, cwd_out):
        if not os.path.isfile(exe):
            raise FileNotFoundError("Point 'Unlinker.exe' at the extended OpenAssetTools build")
        if not os.path.isfile(ff_path):
            raise FileNotFoundError("Select a valid fastfile")
        work = os.path.dirname(os.path.abspath(cwd_out)) or "."
        # Unlinker name-verifies the file against its internal name; stage a copy named to match.
        try:
            data = open(ff_path, "rb").read()
            internal = data[24:56].split(b"\x00")[0].decode("latin1") or os.path.splitext(os.path.basename(ff_path))[0]
        except Exception:
            internal = os.path.splitext(os.path.basename(ff_path))[0]
        staged = os.path.join(work, internal + ".ff")
        if os.path.abspath(staged) != os.path.abspath(ff_path):
            open(staged, "wb").write(open(ff_path, "rb").read())
        env = dict(os.environ)
        env.update(env_extra)
        self.log_line(f"$ Unlinker --list {internal}.ff   ({' '.join(k+'='+v for k, v in env_extra.items())})")
        proc = subprocess.Popen([exe, "--list", staged], cwd=work,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                env=env, text=True, bufsize=1)
        for line in proc.stdout:
            self.log_line(line.rstrip())
        proc.wait()
        return proc.returncode, work, internal

    # ======================================================================
    #  Pages
    # ======================================================================
    # -- batch convert page -------------------------------------------------
    _KIND_LABEL = {"fastfile": "fastfile (.ff)", "soundbank": "sound bank",
                   "ipak": "image pak (.ipak)"}

    def _page_batch(self, page):
        p = self._card(page, "Batch Convert  ·  PC → Wii U",
                       "Add fastfiles (.ff), sound banks (.sabs/.sabl) and image paks (.ipak) — mixed "
                       "types are fine. Each is converted to its Wii U version and written to the output "
                       "folder under its original name.")
        self.b_files = []
        self.b_out = tk.StringVar()
        self.b_oat = tk.StringVar(value=find_oat_default())

        # queue list
        tw = tk.Frame(p, bg=BORDER)
        tw.pack(fill="both", expand=True, pady=(0, 6))
        cols = ("file", "type", "status")
        self.b_tree = ttk.Treeview(tw, columns=cols, show="headings", style="FE.Treeview", height=8)
        self.b_tree.heading("file", text="File")
        self.b_tree.heading("type", text="Type")
        self.b_tree.heading("status", text="Status")
        self.b_tree.column("file", width=470, anchor="w")
        self.b_tree.column("type", width=130, anchor="w", stretch=False)
        self.b_tree.column("status", width=150, anchor="w", stretch=False)
        sb = ttk.Scrollbar(tw, command=self.b_tree.yview)
        self.b_tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.b_tree.pack(side="left", fill="both", expand=True, padx=1, pady=1)

        # optional real drag-and-drop (Windows) if the `windnd` helper is present
        self.b_dnd = False
        try:
            import windnd
            windnd.hook_dropfiles(self.b_tree, func=lambda files: self._batch_add(
                [f.decode("mbcs", "replace") if isinstance(f, bytes) else f for f in files]))
            self.b_dnd = True
        except Exception:
            pass

        qb = ttk.Frame(p, style="Card.TFrame")
        qb.pack(fill="x", pady=(0, 6))
        ttk.Button(qb, text="Add files…", style="Ghost.TButton", command=self._batch_pick).pack(side="left")
        ttk.Button(qb, text="Remove", style="Ghost.TButton", command=self._batch_remove).pack(side="left", padx=6)
        ttk.Button(qb, text="Clear", style="Ghost.TButton", command=self._batch_clear).pack(side="left")
        hint = ("drag files onto the list, or " if self.b_dnd else "") + "use Add files… (multi-select supported)"
        ttk.Label(qb, text=hint, style="Sub.TLabel").pack(side="right")

        self._file_row(p, "Output folder", self.b_out, dirpick=True)
        self._oat_row(p, self.b_oat)
        self._note(p, "Output keeps each file's original name; only the folder changes — so originals are "
                      "never touched. Unlinker.exe is only needed for .ff fastfiles. Sound banks convert "
                      "with the built-in encoder. Image-pak (.ipak) PC→Wii U conversion is still in "
                      "development; those entries report their status and are skipped.")
        self._run_btn(p, "Convert All → Wii U", lambda: self._task("Batch convert", self._batch_run))

    def _batch_add(self, paths):
        added = 0
        for pth in paths:
            pth = pth.strip('"')
            if not os.path.isfile(pth):
                continue
            if any(os.path.abspath(pth) == os.path.abspath(x) for x in self.b_files):
                continue
            kind = batch_convert.detect_kind(pth)
            if kind is None:
                self.log_line(f"[skip] unsupported type: {os.path.basename(pth)}")
                continue
            self.b_files.append(pth)
            self.b_tree.insert("", "end", iid=str(len(self.b_files) - 1),
                               values=(os.path.basename(pth), self._KIND_LABEL.get(kind, kind), "queued"))
            added += 1
        if added:
            self.log_line(f"added {added} file(s) to the batch  (total {len(self.b_files)})")

    def _batch_pick(self):
        types = [("All supported", "*.ff *.sabs *.sabl *.ipak"),
                 ("Fastfiles", "*.ff"), ("Sound banks", "*.sabs *.sabl"),
                 ("Image paks", "*.ipak"), ("All files", "*.*")]
        paths = filedialog.askopenfilenames(title="Add files to convert", filetypes=types)
        if paths:
            self._batch_add(list(paths))

    def _batch_remove(self):
        sel = self.b_tree.selection()
        if not sel:
            return
        drop = {int(i) for i in sel}
        self.b_files = [f for i, f in enumerate(self.b_files) if i not in drop]
        self._batch_refresh()

    def _batch_clear(self):
        self.b_files = []
        self._batch_refresh()

    def _batch_refresh(self):
        for r in self.b_tree.get_children():
            self.b_tree.delete(r)
        for i, pth in enumerate(self.b_files):
            kind = batch_convert.detect_kind(pth)
            self.b_tree.insert("", "end", iid=str(i),
                               values=(os.path.basename(pth), self._KIND_LABEL.get(kind, kind), "queued"))

    def _batch_status(self, idx, text):
        self.after(0, lambda: self.b_tree.set(str(idx), "status", text) if self.b_tree.exists(str(idx)) else None)

    def _batch_run(self):
        if not self.b_files:
            raise ValueError("Add some files first.")
        out_dir = self.b_out.get().strip()
        if not out_dir:
            raise ValueError("Choose an output folder.")
        os.makedirs(out_dir, exist_ok=True)
        oat = self.b_oat.get().strip()
        ok = fail = 0
        for i, pth in enumerate(list(self.b_files)):
            name = os.path.basename(pth)
            self._batch_status(i, "converting…")
            self.log_line(f"\n--- {name} ---")
            try:
                out = batch_convert.convert_file(pth, out_dir, oat_exe=oat, log=self.log_line)
                self._batch_status(i, "done ✓")
                self.log_line(f"  -> {out}")
                ok += 1
            except Exception as e:
                self._batch_status(i, "failed ✗")
                self.log_line(f"  [failed] {e}")
                fail += 1
        self.log_line(f"\nBatch finished: {ok} converted, {fail} failed  ->  {out_dir}")

    def _page_decrypt(self, page):
        p = self._card(page, "Fastfile → Zone",
                       "Decrypt and decompress a Wii U .ff into its raw decompressed zone.")
        self.d_in = tk.StringVar()
        self.d_out = tk.StringVar()
        self._file_row(p, "Wii U fastfile", self.d_in, types=[("Fastfile", "*.ff"), ("All files", "*.*")])
        self._file_row(p, "Output zone", self.d_out, save=True, types=[("Zone", "*.zone")])

        def go():
            src = self.d_in.get().strip()
            if not os.path.isfile(src):
                raise FileNotFoundError("Select a valid .ff file")
            data = open(src, "rb").read()
            if not wiiu_ff.is_wiiu_fastfile(data):
                raise ValueError("Not a Wii U (v148) fastfile")
            hdr, zone, n = wiiu_ff.decrypt(data)
            out = self.d_out.get().strip() or os.path.splitext(src)[0] + ".zone"
            open(out, "wb").write(zone)
            self.log_line(f"name='{hdr['name']}'  chunks={n}")
            self.log_line(f"decompressed zone = {len(zone):,} bytes")
            self.log_line(f"wrote {out}")
        self._run_btn(p, "Decrypt + Decompress", lambda: self._task("Decrypt", go))

    def _page_repack(self, page):
        p = self._card(page, "Zone → Fastfile",
                       "Pack a decompressed zone back into a Wii U v148 fastfile.")
        self.r_in = tk.StringVar()
        self.r_name = tk.StringVar()
        self.r_out = tk.StringVar()
        self._file_row(p, "Zone", self.r_in, types=[("Zone", "*.zone"), ("All files", "*.*")])

        def autoname(*_):
            base = os.path.splitext(os.path.basename(self.r_in.get()))[0]
            if base and not self.r_name.get():
                self.r_name.set(base)
        self.r_in.trace_add("write", autoname)
        nr = ttk.Frame(p, style="Card.TFrame")
        nr.pack(fill="x", pady=4)
        ttk.Label(nr, text="Internal name", style="Card.TLabel", width=16).pack(side="left")
        ttk.Entry(nr, textvariable=self.r_name).pack(side="left", fill="x", expand=True)
        self._file_row(p, "Output fastfile", self.r_out, save=True, types=[("Fastfile", "*.ff")])
        self._note(p, "The internal name must match the slot the game loads it as.")

        def go():
            src = self.r_in.get().strip()
            if not os.path.isfile(src):
                raise FileNotFoundError("Select a valid .zone file")
            name = self.r_name.get().strip() or os.path.splitext(os.path.basename(src))[0]
            zone = open(src, "rb").read()
            ff = wiiu_ff.pack(zone, name)
            out = self.r_out.get().strip() or os.path.splitext(src)[0] + "_repacked.ff"
            open(out, "wb").write(ff)
            self.log_line(f"packed {len(zone):,} byte zone -> {len(ff):,} byte ff")
            self.log_line(f"name='{name}'  wrote {out}")
        self._run_btn(p, "Pack Fastfile", lambda: self._task("Repack", go))

    def _page_pipeline(self, page):
        p = self._card(page, "PC Fastfile → Wii U Fastfile + IPAK",
                       "Unlink a PC map fastfile, convert its zone to console, repack as a "
                       "Wii U .ff, and author the map .ipak — in one pass.")
        self.pl_in = tk.StringVar()
        self.pl_out = tk.StringVar()
        self.pl_ref = tk.StringVar()
        self._file_row(p, "PC fastfile", self.pl_in,
                       types=[("Fastfile", "*.ff"), ("All files", "*.*")])
        self._file_row(p, "Output folder", self.pl_out, dirpick=True)
        self._file_row(p, "Console ref", self.pl_ref,
                       types=[("Console ff/zone", "*.ff *.zone"), ("All files", "*.*")])
        self._note(p,
                   "Console ref is optional — for a retail map it is found automatically. It is "
                   "the genuine Wii U .ff/.zone used as the conversion backbone: complex GX2 "
                   "assets (materials, techsets, models, FX) and the world geometry fall back to "
                   "it until native synthesis is complete, so a bootable .ff needs it. Without a "
                   "reference (a novel/custom map) only the .ipak is produced. The .ipak image "
                   "conversion is general and validated byte-exact against retail.")

        def go():
            src = self.pl_in.get().strip()
            if not os.path.isfile(src):
                raise FileNotFoundError("Select a valid PC .ff file")
            out_dir = self.pl_out.get().strip() or os.path.join(
                os.path.dirname(src), "pipeline_out")
            ref = self.pl_ref.get().strip() or None
            nl = os.path.join(os.path.dirname(APP_DIR), "native_linker")
            if nl not in sys.path:
                sys.path.insert(0, nl)
            try:
                import pc_convert_pipeline as PL
            except Exception as e:
                raise RuntimeError(
                    "pipeline modules not found next to the app (native_linker/): %s" % e)
            rep = PL.convert_pc_ff(src, out_dir, console_ref=ref,
                                   progress=self.log_line)
            self.log_line("")
            self.log_line("name     : %s" % rep["name"])
            self.log_line("wii u ff : %s" % (rep["ff"] or "(not produced — see notes)"))
            self.log_line("ipak     : %s" % (rep["ipak"] or "(none)"))
            self.log_line("bootable : %s (%d PC-sourced assets)"
                          % (rep["bootable"], rep["pc_sourced"]))
            for n in rep["notes"]:
                self.log_line("note     : %s" % n)
        self._run_btn(p, "Convert PC → Wii U + IPAK",
                      lambda: self._task("PC → Wii U pipeline", go))

    def _page_read(self, page):
        p = self._card(page, "Read a Wii U fastfile's assets",
                       "List the assets in a genuine big-endian Wii U (v148) fastfile through the extended "
                       "OpenAssetTools. The console read path parses the Wii U struct layouts (materials, "
                       "GX2 images, technique/shader sets, geometry and the GfxWorld) that differ from PC.")
        self.rd_oat = tk.StringVar(value=find_oat_default())
        self.rd_in = tk.StringVar()
        self._oat_row(p, self.rd_oat)
        self._file_row(p, "Source fastfile", self.rd_in, types=[("Fastfile", "*.ff"), ("All files", "*.*")])
        opts = ttk.Frame(p, style="Card.TFrame")
        opts.pack(fill="x", pady=(10, 0))
        self.rd_blockremap = tk.BooleanVar(value=True)
        self.rd_aliasnull = tk.BooleanVar(value=True)
        self.rd_sig = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="Wii U console read path (block remap + console struct layouts)",
                        variable=self.rd_blockremap).pack(anchor="w")
        ttk.Checkbutton(opts, text="Resolve reused-memory / cross-zone references (read further)",
                        variable=self.rd_aliasnull).pack(anchor="w")
        ttk.Checkbutton(opts, text="Ignore signature check (read unsigned)",
                        variable=self.rd_sig).pack(anchor="w")
        self._note(p, "The asset trace streams to the log below. Reference resolution is lossy (it drops "
                      "reused-memory references), so it is a read/enumeration aid, not a faithful relink.")

        def go():
            env = {}
            if self.rd_blockremap.get():
                env["OAT_WIIU_BLOCKREMAP"] = "1"
            if self.rd_aliasnull.get():
                env["OAT_ALIAS_NULL"] = "1"
            if self.rd_sig.get():
                env["OAT_IGNORE_SIG"] = "1"
            rc, _w, _i = self._run_oat(self.rd_oat.get().strip(), self.rd_in.get().strip(),
                                       env, self.rd_in.get().strip())
            self.log_line(f"(exit {rc}) asset read finished - see the trace above")
        self._run_btn(p, "Read Assets", lambda: self._task("OAT read assets", go))

    def _page_dump(self, page):
        p = self._card(page, "Dump the decompressed zone content",
                       "Decompress a fastfile through OpenAssetTools and write its raw decompressed content "
                       "to a file (works even when the asset graph can't be fully parsed).")
        self.u_oat = tk.StringVar(value=find_oat_default())
        self.u_in = tk.StringVar()
        self.u_out = tk.StringVar()
        self._oat_row(p, self.u_oat)
        self._file_row(p, "Source fastfile", self.u_in, types=[("Fastfile", "*.ff"), ("All files", "*.*")])
        self._file_row(p, "Output .bin", self.u_out, save=True, types=[("Binary", "*.bin")])
        self.u_sig = tk.BooleanVar(value=True)
        ttk.Checkbutton(p, text="Ignore signature check", variable=self.u_sig).pack(anchor="w", pady=(8, 0))

        def go():
            outp = self.u_out.get().strip() or os.path.splitext(self.u_in.get().strip())[0] + "_content.bin"
            env = {"OAT_DUMP_ZONE": os.path.abspath(outp)}
            if self.u_sig.get():
                env["OAT_IGNORE_SIG"] = "1"
            rc, work, internal = self._run_oat(self.u_oat.get().strip(), self.u_in.get().strip(), env, outp)
            if os.path.isfile(outp):
                self.log_line(f"wrote decompressed content -> {outp} ({os.path.getsize(outp):,} bytes)")
            else:
                self.log_line(f"(exit {rc}) no output produced - see log above")
        self._run_btn(p, "Dump Decompressed Zone", lambda: self._task("OAT dump zone", go))

    def _page_validate(self, page):
        p = self._card(page, "Structural Zone Validator",
                       "Check a decompressed zone against genuine Wii U structural conventions.")
        self.v_in = tk.StringVar()
        self.v_ref = tk.StringVar()
        self._file_row(p, "Zone", self.v_in, types=[("Zone", "*.zone"), ("All files", "*.*")])
        self._file_row(p, "Reference (opt)", self.v_ref, types=[("Zone", "*.zone"), ("All files", "*.*")])
        self._note(p,
                   "Checks the structure of a SINGLE zone against Wii U loader conventions - block policy "
                   "(TEMP stays small / data in VIRTUAL), the XAssetList follow-pointers, the script-string "
                   "table and the asset directory. It is a load-time sanity gate, NOT a content comparison; "
                   "the optional reference is only printed alongside for eyeballing, never diffed.")

        def go():
            src = self.v_in.get().strip()
            if not os.path.isfile(src):
                raise FileNotFoundError("Select a valid .zone file")
            buf = io.StringIO()
            argv = [src]
            ref = self.v_ref.get().strip()
            if ref:
                argv += ["--ref", ref]
            old = sys.argv
            sys.argv = ["zone_validate"] + argv
            try:
                with contextlib.redirect_stdout(buf):
                    rc = zone_validate.main()
            finally:
                sys.argv = old
            for ln in buf.getvalue().splitlines():
                self.log_line(ln)
            self.log_line("VALIDATION PASSED" if rc == 0 else "VALIDATION FOUND DIVERGENCES")
        self._run_btn(p, "Validate Zone", lambda: self._task("Validate", go))

    def _page_write(self, page):
        p = self._card(page, "Write a big-endian v148 Wii U zone",
                       "Load a fastfile through the extended OpenAssetTools and re-emit it as a big-endian "
                       "Wii U (v148) zone with the Wii U write-path transforms applied.")
        self.c_oat = tk.StringVar(value=find_oat_default())
        self.c_in = tk.StringVar()
        self._oat_row(p, self.c_oat)
        self._file_row(p, "Source fastfile", self.c_in, types=[("Fastfile", "*.ff"), ("All files", "*.*")])
        opts = ttk.Frame(p, style="Card.TFrame")
        opts.pack(fill="x", pady=(10, 0))
        self.c_sig = tk.BooleanVar(value=True)
        self.c_rtphys = tk.BooleanVar(value=True)
        self.c_dropgsc = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="Ignore signature check (read unsigned)", variable=self.c_sig).pack(anchor="w")
        ttk.Checkbutton(opts, text="Reserve RUNTIME_PHYSICAL block (0xc60000)", variable=self.c_rtphys).pack(anchor="w")
        ttk.Checkbutton(opts, text="Drop script (scriptparsetree) assets", variable=self.c_dropgsc).pack(anchor="w")
        self._note(p, "Output is written next to the source as <name>_rewrite.ff (a raw v148 zone). "
                      "Block-policy remap, inline-image stripping and the Wii U asset-type remap are applied "
                      "automatically. Pack it with 'Zone → Fastfile' to produce a loadable .ff.")

        def go():
            env = {"OAT_REWRITE": "1", "OAT_WRITE_WIIU": "1"}
            if self.c_sig.get():
                env["OAT_IGNORE_SIG"] = "1"
            if self.c_rtphys.get():
                env["OAT_RT_PHYS"] = "c60000"
            if self.c_dropgsc.get():
                env["OAT_DROP_GSC"] = "1"
            rc, work, internal = self._run_oat(self.c_oat.get().strip(), self.c_in.get().strip(),
                                               env, self.c_in.get().strip())
            out = os.path.join(work, internal + "_rewrite.ff")
            if os.path.isfile(out):
                self.log_line(f"wrote raw Wii U zone -> {out} ({os.path.getsize(out):,} bytes)")
                self.log_line("Pack it with 'Zone → Fastfile' to produce a loadable .ff.")
            else:
                self.log_line(f"(exit {rc}) no _rewrite.ff produced - see log above")
        self._run_btn(p, "Write Wii U Zone", lambda: self._task("OAT write Wii U zone", go))

    # -- zone editor page ---------------------------------------------------
    def _page_editor(self, page):
        p = self._card(page, "Browse & Edit Zone Contents",
                       "List the scripts (GSC/CSC) and rawfiles inside a zone, export them, and replace "
                       "them in place before repacking.")
        self.fe_zone = None
        self.fe_path = ""
        self.fe_entries = []
        self.fe_in = tk.StringVar()

        row = ttk.Frame(p, style="Card.TFrame")
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="Zone", style="Card.TLabel", width=14).pack(side="left")
        ttk.Entry(row, textvariable=self.fe_in).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(row, text="Browse", style="Ghost.TButton",
                   command=lambda: self.fe_in.set(filedialog.askopenfilename(
                       filetypes=[("Zone", "*.zone"), ("All files", "*.*")]) or self.fe_in.get())).pack(side="left")
        ttk.Button(row, text="Open", style="Accent.TButton", command=self._fe_open).pack(side="left", padx=(8, 0))

        tw = tk.Frame(p, bg=BORDER)
        tw.pack(fill="both", expand=True, pady=(10, 6))
        cols = ("kind", "size", "name")
        self.fe_tree = ttk.Treeview(tw, columns=cols, show="headings", style="FE.Treeview", height=10)
        self.fe_tree.heading("kind", text="Kind")
        self.fe_tree.heading("size", text="Size")
        self.fe_tree.heading("name", text="Name")
        self.fe_tree.column("kind", width=80, anchor="w", stretch=False)
        self.fe_tree.column("size", width=90, anchor="e", stretch=False)
        self.fe_tree.column("name", width=560, anchor="w")
        sb = ttk.Scrollbar(tw, command=self.fe_tree.yview)
        self.fe_tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.fe_tree.pack(side="left", fill="both", expand=True, padx=1, pady=1)

        btns = ttk.Frame(p, style="Card.TFrame")
        btns.pack(fill="x")
        ttk.Button(btns, text="Export selected", style="Ghost.TButton", command=self._fe_export).pack(side="left")
        ttk.Button(btns, text="Replace selected (in-place)", style="Ghost.TButton",
                   command=self._fe_replace).pack(side="left", padx=8)
        ttk.Button(btns, text="Save zone", style="Accent.TButton", command=self._fe_save).pack(side="right")
        self._note(p, "Replacement must be the exact same byte length (in-place edit). To resize a script, "
                      "recompile to the same length or rebuild via the OAT GSC-inject path.")

    def _fe_open(self):
        src = self.fe_in.get().strip()
        if not os.path.isfile(src):
            messagebox.showerror(APP_TITLE, "Select a valid .zone file")
            return
        try:
            self.fe_zone = open(src, "rb").read()
            self.fe_path = src
            self.fe_entries = ff_assets.scan_buffers(self.fe_zone)
        except Exception as e:
            messagebox.showerror(APP_TITLE, str(e))
            return
        for r in self.fe_tree.get_children():
            self.fe_tree.delete(r)
        for i, e in enumerate(self.fe_entries):
            self.fe_tree.insert("", "end", iid=str(i), values=(e["kind"], f"{e['len']:,}", e["name"]))
        ns = sum(1 for e in self.fe_entries if e["kind"] == "script")
        nr = sum(1 for e in self.fe_entries if e["kind"] == "rawfile")
        self.log_line(f"\n=== Zone editor: opened {os.path.basename(src)} ===")
        self.log_line(f"found {len(self.fe_entries)} editable assets  (scripts={ns} rawfiles={nr})")

    def _fe_selected(self):
        sel = self.fe_tree.selection()
        if not sel or self.fe_zone is None:
            messagebox.showinfo(APP_TITLE, "Open a zone and select an entry first.")
            return None
        return self.fe_entries[int(sel[0])]

    def _fe_export(self):
        e = self._fe_selected()
        if not e:
            return
        base = os.path.basename(e["name"]) or "asset.bin"
        out = filedialog.asksaveasfilename(initialfile=base)
        if not out:
            return
        open(out, "wb").write(ff_assets.extract_buffer(self.fe_zone, e))
        self.log_line(f"exported '{e['name']}' ({e['len']:,} bytes) -> {out}")

    def _fe_replace(self):
        e = self._fe_selected()
        if not e:
            return
        src = filedialog.askopenfilename(title=f"Replacement for {e['name']} (must be {e['len']:,} bytes)")
        if not src:
            return
        data = open(src, "rb").read()
        try:
            self.fe_zone = ff_assets.replace_buffer(self.fe_zone, e, data)
        except ValueError as ex:
            messagebox.showerror(APP_TITLE, str(ex))
            self.log_line(f"[replace rejected] {ex}")
            return
        self.log_line(f"replaced '{e['name']}' in place ({e['len']:,} bytes). Save the zone to keep it.")

    def _fe_save(self):
        if self.fe_zone is None:
            messagebox.showinfo(APP_TITLE, "Nothing to save.")
            return
        out = filedialog.asksaveasfilename(initialfile=os.path.basename(self.fe_path) or "edited.zone",
                                           filetypes=[("Zone", "*.zone")])
        if not out:
            return
        open(out, "wb").write(self.fe_zone)
        self.log_line(f"saved edited zone -> {out}  (now repack it with 'Zone → Fastfile')")

    # -- about page ---------------------------------------------------------
    def _page_sigpatch(self, page):
        p = self._card(page, "RPL Signature Patch",
                       "Bypass the Black Ops II fastfile signature check so custom / repacked "
                       "(zeroed-signature) fastfiles load on a Wii U.")
        self.sp_in = tk.StringVar()
        self.sp_out = tk.StringVar()
        self._file_row(p, "Engine RPL", self.sp_in,
                       types=[("Wii U RPL", "*.rpl"), ("All files", "*.*")])
        self._file_row(p, "Output RPL", self.sp_out, save=True,
                       types=[("Wii U RPL", "*.rpl")])

        def autoname(*_):
            src = self.sp_in.get().strip()
            if src and not self.sp_out.get():
                self.sp_out.set(src + ".patched")
        self.sp_in.trace_add("write", autoname)

        self._note(
            p,
            "Patches __DBX_AuthLoad_ValidateSignature_Try to always report a valid signature "
            "(the one bl to DB_SetPublicKey becomes a branch to the function's own success block).\n\n"
            "IMPORTANT:\n"
            "  - Patch BOTH t6_cafef_rpl.rpl and t6mp_cafef_rpl.rpl from the UPDATE title build.\n"
            "  - Keep a .orig backup of each original RPL (this tool never overwrites the input).\n"
            "  - Install the patched RPLs into the title's UPDATE code partition, then load your "
            "zeroed-signature fastfile. Requires CFW (Aroma / Tiramisu) on real hardware; works as-is "
            "in Cemu.\n"
            "  - The tool auto-locates the function by symbol, so it works across base / MP / update "
            "builds (different VAs).")

        def go():
            src = self.sp_in.get().strip()
            if not os.path.isfile(src):
                raise FileNotFoundError("Select a valid engine .rpl file")
            try:
                import rpl_sigpatch
            except SystemExit:
                raise RuntimeError("capstone is required: pip install capstone")
            except ImportError:
                raise RuntimeError("rpl_sigpatch.py not found next to the app")
            out = self.sp_out.get().strip() or (src + ".patched")
            if os.path.abspath(out) == os.path.abspath(src):
                raise ValueError("Output must differ from the input (keep the original as backup)")
            va = rpl_sigpatch.find_validate_va(bytearray(open(src, "rb").read()))
            if va is None:
                raise RuntimeError("No ValidateSignature_Try symbol — is this a T6 engine RPL?")
            self.log_line(f"found __DBX_AuthLoad_ValidateSignature_Try @ VA {va:#010x}")
            rpl_sigpatch.patch_rpl(src, out)
            self.log_line(f"patched RPL written: {out}")
            self.log_line("signature check neutralized (verified). Remember to patch BOTH t6/t6mp RPLs.")
        self._run_btn(p, "Patch RPL", lambda: self._task("Sig patch", go))

    def _page_about(self, page):
        p = self._card(page, f"{APP_TITLE}  {APP_VERSION}", "Tools for Black Ops II (T6) Wii U fastfiles.")
        txt = (
            "Simple mode - flat conversions:\n"
            "   · Fastfile → Zone     decrypt + decompress a Wii U .ff (Salsa20 + deflate, v148)\n"
            "   · Zone → Fastfile     repack a zone into a v148 fastfile (chunk framing + alignment)\n"
            "   · Read Assets         list a genuine Wii U fastfile's assets via OpenAssetTools\n\n"
            "Advanced mode - full toolkit:\n"
            "   · Dump Zone           write a fastfile's raw decompressed content to a file\n"
            "   · Validate Zone       structural load-time sanity gate (block policy, directory, strings)\n"
            "   · Zone Editor         browse / export / in-place replace scripts and rawfiles\n"
            "   · Write Wii U Zone    re-emit a fastfile as a big-endian v148 zone (write-path transforms)\n\n"
            "The console read path parses the Wii U struct layouts that differ from PC: Material (104 B),\n"
            "GX2 GfxImage (328 B), the technique / GX2 vertex+pixel-shader chain, XModel/XSurface geometry\n"
            "and the GfxWorld. See README.md and USAGE.md for the full list of Wii U fixes."
        )
        ttk.Label(p, text=txt, style="Card.TLabel", justify="left", font=("Consolas", 9)).pack(anchor="w")
        url = "https://github.com/tonytrawl/Wiiu_ff_studio"
        lr = ttk.Frame(p, style="Card.TFrame")
        lr.pack(anchor="w", pady=(16, 0))
        ttk.Label(lr, text="Project & source:  ", style="Card.TLabel").pack(side="left")
        link = tk.Label(lr, text="github.com/tonytrawl/Wiiu_ff_studio", bg=CARD, fg=ACCENT,
                        cursor="hand2", font=("Segoe UI", 10, "underline"))
        link.pack(side="left")
        link.bind("<Button-1>", lambda _e: webbrowser.open(url))


if __name__ == "__main__":
    Studio().mainloop()
