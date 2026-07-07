"""
Wii U FF Editor
===============

A single-window fastfile editor in the spirit of the old "FF Viewer" tools.

  * Open a Wii U `.ff` -- it's decrypted + decompressed in the background.
  * The scripts (GSC/CSC) and rawfiles inside are listed on the left.
  * Pick a text file and edit it on the right in a Notepad-style pane
    (monospace, line numbers, find).
  * Hit Save and the zone is patched and re-packed straight back into the `.ff`.

Edits are applied in place, so a file has to stay within its original byte slot
(the zone is a packed pointer graph -- a different length would shift every
following offset). The byte meter at the bottom shows the budget; shorter text is
padded to fit, over-budget is blocked. Compiled/binary assets (e.g. GSC bytecode)
aren't text-editable -- use Export / Import (same length) for those.
"""
import os
import sys
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)

import wiiu_ff
import ff_assets

APP_TITLE = "Wii U FF Editor"
APP_VERSION = "1.0"

BG     = "#11161f"
PANEL  = "#171e2a"
EDIT   = "#0c1119"
GUTTER = "#0a0e15"
HEAD   = "#0a0e15"
ACCENT = "#18b4a8"
ACCENT2= "#0e8f86"
TEXT   = "#e6edf3"
MUTED  = "#8b97a8"
BORDER = "#27324a"
OK     = "#39c07a"
WARN   = "#e0544f"


def looks_text(buf):
    """Heuristic: is this blob editable as text?"""
    if not buf:
        return True
    sample = buf[:4096]
    printable = sum(1 for c in sample if 0x20 <= c < 0x7f or c in (9, 10, 13))
    return printable / len(sample) >= 0.92


class Editor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1080x740")
        self.minsize(900, 600)
        self.configure(bg=BG)
        try:
            self.iconbitmap(os.path.join(getattr(sys, "_MEIPASS", APP_DIR), "editor.ico"))
        except Exception:
            pass

        self.ff_path = ""
        self.zone = None
        self.name = ""
        self.entries = []           # ff_assets entries (scripts + rawfiles)
        self.edits = {}             # index -> current text (only for text files)
        self.cur = None             # current entry index
        self.dirty = False
        self._q = queue.Queue()
        self._busy = False

        self._style()
        self._menu()
        self._toolbar()
        self._body()
        self._statusbar()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(60, self._drain)
        self.bind_all("<Control-s>", lambda e: self._save())
        self.bind_all("<Control-o>", lambda e: self._open())
        self.bind_all("<Control-f>", lambda e: self._find())

    # -- chrome -------------------------------------------------------------
    def _style(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure(".", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        st.configure("TFrame", background=BG)
        st.configure("Panel.TFrame", background=PANEL)
        st.configure("TLabel", background=BG, foreground=TEXT)
        st.configure("Accent.TButton", background=ACCENT, foreground="#03110f",
                     font=("Segoe UI Semibold", 10), borderwidth=0, padding=(13, 6))
        st.map("Accent.TButton", background=[("active", ACCENT2), ("disabled", BORDER)])
        st.configure("Ghost.TButton", background=PANEL, foreground=TEXT, borderwidth=1, padding=(10, 5))
        st.map("Ghost.TButton", background=[("active", BORDER)])

    def _menu(self):
        m = tk.Menu(self)
        fm = tk.Menu(m, tearoff=0)
        fm.add_command(label="Open FF...\tCtrl+O", command=self._open)
        fm.add_command(label="Save\tCtrl+S", command=self._save)
        fm.add_command(label="Save FF As...", command=lambda: self._save(save_as=True))
        fm.add_separator()
        fm.add_command(label="Exit", command=self._on_close)
        m.add_cascade(label="File", menu=fm)
        self.config(menu=m)

    def _toolbar(self):
        bar = tk.Frame(self, bg=HEAD, height=46)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        ttk.Button(bar, text="Open FF", style="Ghost.TButton", command=self._open).pack(side="left", padx=(10, 4), pady=7)
        ttk.Button(bar, text="Save", style="Accent.TButton", command=self._save).pack(side="left", padx=4, pady=7)
        ttk.Button(bar, text="Export", style="Ghost.TButton", command=self._export).pack(side="left", padx=4, pady=7)
        ttk.Button(bar, text="Import", style="Ghost.TButton", command=self._import).pack(side="left", padx=4, pady=7)
        self.title_lbl = tk.Label(bar, text="no fastfile open", bg=HEAD, fg=MUTED, font=("Segoe UI", 10))
        self.title_lbl.pack(side="left", padx=14)
        tk.Frame(self, bg=ACCENT, height=2).pack(fill="x")

    def _body(self):
        pan = tk.PanedWindow(self, orient="horizontal", bg=BORDER, sashwidth=4, bd=0)
        pan.pack(fill="both", expand=True)

        # left: file list
        left = tk.Frame(pan, bg=PANEL, width=300)
        tk.Label(left, text="  Files in fastfile", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9), anchor="w").pack(fill="x", pady=(8, 4))
        lw = tk.Frame(left, bg=BORDER)
        lw.pack(fill="both", expand=True, padx=6, pady=(0, 8))
        self.lst = tk.Listbox(lw, bg=EDIT, fg=TEXT, selectbackground=ACCENT2,
                              selectforeground="#03110f", relief="flat", bd=0,
                              activestyle="none", font=("Consolas", 9), highlightthickness=0)
        sb = ttk.Scrollbar(lw, command=self.lst.yview)
        self.lst.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.lst.pack(side="left", fill="both", expand=True, padx=1, pady=1)
        self.lst.bind("<<ListboxSelect>>", self._on_pick)
        pan.add(left, minsize=210)

        # right: editor with line gutter
        right = tk.Frame(pan, bg=EDIT)
        self.path_lbl = tk.Label(right, text="select a file", bg=EDIT, fg=MUTED,
                                 anchor="w", font=("Consolas", 9))
        self.path_lbl.pack(fill="x", padx=8, pady=(6, 2))
        ew = tk.Frame(right, bg=EDIT)
        ew.pack(fill="both", expand=True)
        self.gutter = tk.Text(ew, width=6, bg=GUTTER, fg=MUTED, relief="flat", bd=0,
                              font=("Consolas", 11), padx=6, takefocus=0, state="disabled",
                              highlightthickness=0)
        self.gutter.pack(side="left", fill="y")
        self.txt = tk.Text(ew, bg=EDIT, fg=TEXT, insertbackground=ACCENT, relief="flat", bd=0,
                           wrap="none", undo=True, font=("Consolas", 11), padx=8,
                           highlightthickness=0)
        vsb = ttk.Scrollbar(ew, command=self._yview)
        hsb = ttk.Scrollbar(right, orient="horizontal", command=self.txt.xview)
        self.txt.configure(yscrollcommand=self._on_yscroll, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        self.txt.pack(side="left", fill="both", expand=True)
        hsb.pack(fill="x")
        self.txt.bind("<KeyRelease>", self._on_key)
        self.txt.bind("<<Modified>>", self._on_modified)
        self._set_editable(False)
        pan.add(right)

    def _statusbar(self):
        bar = tk.Frame(self, bg=HEAD, height=26)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        self.status = tk.Label(bar, text="Open a .ff to begin", bg=HEAD, fg=MUTED, font=("Segoe UI", 9))
        self.status.pack(side="left", padx=10)
        self.budget = tk.Label(bar, text="", bg=HEAD, fg=MUTED, font=("Consolas", 9))
        self.budget.pack(side="right", padx=10)
        st = ttk.Style(self)
        st.configure("FF.Horizontal.TProgressbar", background=ACCENT, troughcolor=HEAD, borderwidth=0)
        self.pbar = ttk.Progressbar(bar, style="FF.Horizontal.TProgressbar", length=170,
                                    mode="determinate", maximum=1000)
        self.pbar.pack(side="right", padx=10, pady=4)

    # -- editor plumbing ----------------------------------------------------
    def _yview(self, *a):
        self.txt.yview(*a)
        self.gutter.yview(*a)

    def _on_yscroll(self, lo, hi):
        self.gutter.yview_moveto(lo)
        return lo, hi

    def _set_editable(self, on):
        self.txt.config(state="normal" if on else "disabled")

    def _refresh_gutter(self):
        n = int(self.txt.index("end-1c").split(".")[0])
        self.gutter.config(state="normal")
        self.gutter.delete("1.0", "end")
        self.gutter.insert("1.0", "\n".join(str(i) for i in range(1, n + 1)))
        self.gutter.config(state="disabled")
        self.gutter.yview_moveto(self.txt.yview()[0])

    def _on_modified(self, _e=None):
        if self.txt.edit_modified():
            self.txt.edit_modified(False)
            self._refresh_gutter()

    def _on_key(self, _e=None):
        if self.cur is None:
            return
        e = self.entries[self.cur]
        if not e.get("_text"):
            return
        text = self.txt.get("1.0", "end-1c")
        self.edits[self.cur] = text
        used = len(text.encode("latin1", "replace"))
        cap = e["len"]
        self._mark_dirty(True)
        over = used > cap
        self.budget.config(text=f"{used:,} / {cap:,} bytes" + ("  OVER BUDGET" if over else ""),
                           fg=WARN if over else MUTED)

    def _mark_dirty(self, on):
        self.dirty = on
        if self.ff_path:
            base = os.path.basename(self.ff_path)
            self.title_lbl.config(text=("● " if on else "") + base)

    # -- file ops -----------------------------------------------------------
    def _open(self, *_):
        if self._busy:
            return
        if self.dirty and not messagebox.askyesno(APP_TITLE, "Discard unsaved edits?"):
            return
        p = filedialog.askopenfilename(filetypes=[("Wii U fastfile", "*.ff"), ("All files", "*.*")])
        if not p:
            return
        self._busy = True
        self.pbar["value"] = 0
        self.status.config(text="Decrypting " + os.path.basename(p) + "  (a full map can take ~30s)...")
        threading.Thread(target=self._worker_open, args=(p,), daemon=True).start()

    def _worker_open(self, p):
        # runs off the main thread; communicates only via self._q
        try:
            data = open(p, "rb").read()
            if not wiiu_ff.is_wiiu_fastfile(data):
                raise ValueError("Not a Wii U fastfile (TAff0100 / version 148 expected).")
            hdr, zone, n = wiiu_ff.decrypt(data, progress=lambda d, t: self._q.put(("progress", d / t if t else 0)))
            keep = []
            for e in ff_assets.scan_buffers(zone):
                if e["kind"] in ("script", "rawfile"):
                    e["_text"] = looks_text(ff_assets.extract_buffer(zone, e))
                    keep.append(e)
            keep.sort(key=lambda e: (e["kind"] != "rawfile", e["name"]))
            self._q.put(("opened", (p, zone, hdr["name"], keep, n)))
        except Exception as ex:
            self._q.put(("err", str(ex)))

    def _apply_open(self, p, zone, name, keep, n):
        self.ff_path, self.zone, self.name, self.entries = p, zone, name, keep
        self.edits.clear()
        self.cur = None
        self.lst.delete(0, "end")
        for e in keep:
            tag = "  " if e["_text"] else " *"
            self.lst.insert("end", f"{tag}{e['name']}")
        self._set_editable(False)
        self.txt.config(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.config(state="disabled")
        self.path_lbl.config(text=f"{name}  -  {len(keep)} files  ( * = binary, export/import only )")
        self._mark_dirty(False)
        self.budget.config(text="")
        if not keep:
            self.status.config(text=f"Opened {os.path.basename(p)} - no editable scripts/rawfiles found")
        else:
            self.status.config(text=f"Opened {os.path.basename(p)}  ({n} chunks, zone {len(zone):,} bytes)")

    def _on_pick(self, _e=None):
        sel = self.lst.curselection()
        if not sel:
            return
        idx = sel[0]
        self.cur = idx
        e = self.entries[idx]
        self.path_lbl.config(text=f"{e['name']}   ({e['kind']}, {e['len']:,} bytes)")
        if e["_text"]:
            text = self.edits.get(idx)
            if text is None:
                text = ff_assets.extract_buffer(self.zone, e).decode("latin1")
            self._set_editable(True)
            self.txt.config(state="normal")
            self.txt.delete("1.0", "end")
            self.txt.insert("1.0", text)
            self.txt.edit_modified(False)
            self._refresh_gutter()
            used = len(text.encode("latin1", "replace"))
            self.budget.config(text=f"{used:,} / {e['len']:,} bytes", fg=MUTED)
        else:
            self.txt.config(state="normal")
            self.txt.delete("1.0", "end")
            self.txt.insert("1.0",
                            f"[ {e['name']} ]\n\nCompiled / binary asset ({e['len']:,} bytes) - not text-editable.\n"
                            f"Use Export to pull it out, edit with your own tooling, then Import a same-length file.")
            self.txt.config(state="disabled")
            self.budget.config(text=f"{e['len']:,} bytes (binary)", fg=MUTED)

    def _export(self):
        if self.cur is None:
            return
        e = self.entries[self.cur]
        out = filedialog.asksaveasfilename(initialfile=os.path.basename(e["name"]))
        if not out:
            return
        data = self.edits[self.cur].encode("latin1", "replace") if (e["_text"] and self.cur in self.edits) \
            else ff_assets.extract_buffer(self.zone, e)
        open(out, "wb").write(data)
        self.status.config(text=f"Exported {e['name']} -> {out}")

    def _import(self):
        if self.cur is None or self.zone is None:
            return
        e = self.entries[self.cur]
        src = filedialog.askopenfilename(title=f"Import (must be {e['len']:,} bytes)")
        if not src:
            return
        data = open(src, "rb").read()
        try:
            self.zone = ff_assets.replace_buffer(self.zone, e, data)
        except ValueError as ex:
            messagebox.showerror(APP_TITLE, str(ex))
            return
        self.edits.pop(self.cur, None)
        self._mark_dirty(True)
        self._on_pick()
        self.status.config(text=f"Imported {e['name']} (in place)")

    def _save(self, *_, save_as=False):
        if self.zone is None:
            return
        # fold any pending text edit
        if self.cur is not None and self.entries[self.cur].get("_text"):
            self.edits[self.cur] = self.txt.get("1.0", "end-1c")
        # check budgets first
        over = []
        for idx, text in self.edits.items():
            e = self.entries[idx]
            if len(text.encode("latin1", "replace")) > e["len"]:
                over.append(e["name"])
        if over:
            messagebox.showerror(APP_TITLE,
                                 "These files exceed their byte budget - trim them to fit:\n\n  "
                                 + "\n  ".join(over))
            return
        out = self.ff_path
        if save_as or not out:
            out = filedialog.asksaveasfilename(defaultextension=".ff",
                                               initialfile=os.path.basename(self.ff_path) or (self.name + ".ff"),
                                               filetypes=[("Wii U fastfile", "*.ff")])
            if not out:
                return
        self._busy = True
        self.pbar["value"] = 0
        self.status.config(text="Repacking " + os.path.basename(out) + "...")
        edits = dict(self.edits)
        threading.Thread(target=self._worker_save, args=(out, edits), daemon=True).start()

    def _worker_save(self, out, edits):
        try:
            zone = bytearray(self.zone)
            for idx, text in edits.items():
                e = self.entries[idx]
                blob = text.encode("latin1", "replace")
                blob = blob + b" " * (e["len"] - len(blob))   # pad shorter text to the slot
                zone[e["buf_off"]:e["buf_off"] + e["len"]] = blob
            zone = bytes(zone)
            ff = wiiu_ff.pack(zone, self.name)
            open(out, "wb").write(ff)
            self._q.put(("saved", (out, zone, len(ff))))
        except Exception as ex:
            self._q.put(("err", str(ex)))

    def _apply_save(self, out, zone, fflen):
        self.zone = zone
        self.ff_path = out
        self.edits.clear()
        # re-scan so offsets/entries stay valid for further edits
        self.entries = [e for e in ff_assets.scan_buffers(zone) if e["kind"] in ("script", "rawfile")]
        for e in self.entries:
            e["_text"] = looks_text(ff_assets.extract_buffer(zone, e))
        self.entries.sort(key=lambda e: (e["kind"] != "rawfile", e["name"]))
        self._mark_dirty(False)
        self.status.config(text=f"Saved {os.path.basename(out)}  ({fflen:,} bytes)")

    # -- find ---------------------------------------------------------------
    def _find(self, *_):
        if self.cur is None:
            return
        win = tk.Toplevel(self)
        win.title("Find")
        win.configure(bg=PANEL)
        win.transient(self)
        tk.Label(win, text="Find:", bg=PANEL, fg=TEXT).pack(side="left", padx=8, pady=8)
        var = tk.StringVar()
        ent = ttk.Entry(win, textvariable=var, width=30)
        ent.pack(side="left", padx=4)
        ent.focus_set()

        def go(*_a):
            self.txt.tag_remove("hit", "1.0", "end")
            q = var.get()
            if not q:
                return
            start = self.txt.index("insert")
            pos = self.txt.search(q, start + "+1c", stopindex="end", nocase=1)
            if not pos:
                pos = self.txt.search(q, "1.0", stopindex="end", nocase=1)
            if pos:
                end = f"{pos}+{len(q)}c"
                self.txt.tag_add("hit", pos, end)
                self.txt.tag_config("hit", background=ACCENT2, foreground="#03110f")
                self.txt.mark_set("insert", end)
                self.txt.see(pos)
        ttk.Button(win, text="Next", style="Accent.TButton", command=go).pack(side="left", padx=6)
        ent.bind("<Return>", go)

    # -- queue pump (all GUI updates happen here, on the main thread) -------
    def _drain(self):
        try:
            while True:
                item = self._q.get_nowait()
                kind = item[0]
                if kind == "progress":
                    self.pbar["value"] = int(item[1] * 1000)
                    continue
                # terminal events
                self._busy = False
                self.pbar["value"] = 0
                if kind == "err":
                    self.status.config(text="Error: " + item[1])
                    messagebox.showerror(APP_TITLE, item[1])
                elif kind == "opened":
                    self._apply_open(*item[1])
                elif kind == "saved":
                    self._apply_save(*item[1])
        except queue.Empty:
            pass
        self.after(60, self._drain)

    def _on_close(self):
        if self.dirty and not messagebox.askyesno(APP_TITLE, "Discard unsaved edits and quit?"):
            return
        self.destroy()


if __name__ == "__main__":
    Editor().mainloop()
