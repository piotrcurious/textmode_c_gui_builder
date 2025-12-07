#!/usr/bin/env python3
from __future__ import annotations
import curses
import re
import threading
import queue
import json
import tkinter as tk
from tkinter import scrolledtext, ttk, simpledialog
from enum import Enum, auto
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict, Any, Optional

# ---------------------------
# Minimal Serial UI header for generation
# ---------------------------
SERIAL_UI_HEADER = r"""
#ifndef SERIAL_UI_H
#define SERIAL_UI_H
#include <Arduino.h>
#include <avr/pgmspace.h>
enum class UI_Color { WHITE=37, RED=31, GREEN=32, YELLOW=33, BLUE=34, MAGENTA=35, CYAN=36 };
struct UI_Box { int16_t x, y, w, h; UI_Color color; };
struct UI_Text { int16_t x, y; const char* content; UI_Color color; };
struct UI_Line { int16_t x1, y1, x2, y2; UI_Color color; };
struct UI_Freehand { int16_t x, y; const char* const* lines; uint8_t count; UI_Color color; };
class SerialUI { /* omitted for brevity */ };
#endif
"""

# ---------------------------
# Data model
# ---------------------------
class Color(Enum):
    WHITE = 37; RED = 31; GREEN = 32; YELLOW = 33; BLUE = 34; MAGENTA = 35; CYAN = 36

    @classmethod
    def from_str(cls, s: str) -> "Color":
        try:
            return cls[s.upper()]
        except Exception:
            return cls.WHITE

    @classmethod
    def names(cls) -> List[str]:
        return [c.name for c in cls]

@dataclass
class UIElement:
    name: str
    color: Color = Color.WHITE
    type: str = "BASE"
    layer: int = 0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['color'] = self.color.name
        return d

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> Optional["UIElement"]:
        t = d.get('type', 'BASE')
        color = Color.from_str(d.get('color', 'WHITE'))
        layer = int(d.get('layer', 0))
        if t == "BOX":
            return Box(
                name=str(d.get('name', 'box')),
                color=color,
                x=int(d.get('x', 0)),
                y=int(d.get('y', 0)),
                w=int(d.get('w', 0)),
                h=int(d.get('h', 0)),
                layer=layer
            )
        if t == "TEXT":
            return Text(
                name=str(d.get('name', 'txt')),
                color=color,
                x=int(d.get('x', 0)),
                y=int(d.get('y', 0)),
                content=str(d.get('content', '')),
                layer=layer
            )
        if t == "LINE":
            return Line(
                name=str(d.get('name', 'line')),
                color=color,
                x1=int(d.get('x1', 0)),
                y1=int(d.get('y1', 0)),
                x2=int(d.get('x2', 0)),
                y2=int(d.get('y2', 0)),
                layer=layer
            )
        if t == "FREEHAND":
            return Freehand(
                name=str(d.get('name', 'fh')),
                color=color,
                x=int(d.get('x', 0)),
                y=int(d.get('y', 0)),
                lines=list(d.get('lines', [])),
                layer=layer
            )
        return None

@dataclass
class Box(UIElement):
    x: int = 0; y: int = 0; w: int = 0; h: int = 0
    type: str = "BOX"
    def cpp_struct_init(self) -> str:
        return f'{{ {self.x}, {self.y}, {self.w}, {self.h}, UI_Color::{self.color.name} }}'

@dataclass
class Text(UIElement):
    x: int = 0; y: int = 0; content: str = ""
    type: str = "TEXT"
    def cpp_struct_init(self) -> str:
        safe = self.content.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        return f'{{ {self.x}, {self.y}, "{safe}", UI_Color::{self.color.name} }}'

@dataclass
class Line(UIElement):
    x1: int = 0; y1: int = 0; x2: int = 0; y2: int = 0
    type: str = "LINE"
    def cpp_struct_init(self) -> str:
        return f'{{ {self.x1}, {self.y1}, {self.x2}, {self.y2}, UI_Color::{self.color.name} }}'

@dataclass
class Freehand(UIElement):
    x: int = 0; y: int = 0; lines: List[str] = field(default_factory=list)
    type: str = "FREEHAND"
    def cpp_struct_init(self) -> str:
        return f'{{ {self.x}, {self.y}, RES_{self.name}_ARR, {len(self.lines)}, UI_Color::{self.color.name} }}'

@dataclass
class Screen:
    name: str
    objects: List[UIElement] = field(default_factory=list)

# ---------------------------
# GUI manager (tk thread)
# ---------------------------
class GuiManager:
    def __init__(self):
        self.queue: "queue.Queue[tuple]" = queue.Queue()  # commands -> Designer
        self._root: Optional[tk.Tk] = None
        self._thread = threading.Thread(target=self._run_tk, daemon=True)
        self._thread.start()
        self.ready = threading.Event()
        self._lst_screens: Optional[tk.Listbox] = None
        self._lst_assets: Optional[tk.Listbox] = None
        self.help_var: Optional[tk.StringVar] = None

    def _run_tk(self):
        try:
            root = tk.Tk()
            self._root = root
            root.title("UI Helper")
            root.geometry("420x520")
            try:
                root.attributes('-topmost', True)
            except Exception:
                pass

            nb = ttk.Notebook(root)
            nb.pack(fill="both", expand=True)

            # Help tab
            f_help = tk.Frame(nb)
            nb.add(f_help, text="Help")
            self.help_var = tk.StringVar("Initializing...")
            lbl = tk.Label(f_help, textvariable=self.help_var, justify="left", anchor="nw", font=("Consolas", 10))
            lbl.pack(fill="both", expand=True, padx=6, pady=6)

            # Screens
            f_scr = tk.Frame(nb)
            nb.add(f_scr, text="Screens")
            self._lst_screens = tk.Listbox(f_scr, height=8, exportselection=False)
            self._lst_screens.pack(fill="x", padx=6, pady=6)
            bf = tk.Frame(f_scr); bf.pack(fill="x", pady=4)
            tk.Button(bf, text="Switch To", command=lambda: self._emit_cmd("SWITCH_SCREEN")).pack(side="left", padx=6)
            tk.Button(bf, text="New Screen", command=lambda: self._emit_cmd("ADD_SCREEN")).pack(side="left")
            tk.Button(bf, text="Rename", command=lambda: self._emit_cmd("RENAME_SCREEN")).pack(side="left", padx=6)

            # Assets
            f_assets = tk.Frame(nb)
            nb.add(f_assets, text="Assets")
            self._lst_assets = tk.Listbox(f_assets, exportselection=False)
            self._lst_assets.pack(fill="both", expand=True, padx=6, pady=6)
            af = tk.Frame(f_assets); af.pack(fill="x", pady=4)
            tk.Button(af, text="Insert Selected", command=lambda: self._emit_cmd("INSERT_ASSET")).pack(side="left", padx=6)
            tk.Button(af, text="Delete Asset", command=self._delete_asset).pack(side="right", padx=6)

            tk.Button(root, text="Save Selected Object to Library", bg="#ffeebb", command=lambda: self._emit_cmd("SAVE_ASSET")).pack(fill="x", padx=6, pady=6)

            # small helper: ensure root available to Designer
            self.ready.set()
            # initial populate
            self._refresh_assets()
            root.mainloop()
        except Exception as e:
            # If Tk fails to start, keep ready to avoid blocking designer forever
            self.ready.set()
            print("Tkinter failed to initialize:", e)

    # safe helpers
    def _list_items(self, lb: tk.Listbox) -> List[str]:
        try:
            return list(lb.get(0, tk.END))
        except Exception:
            return []

    def _emit_cmd(self, cmd: str):
        # Called from Tk thread when user clicks a button
        data = None
        try:
            if cmd == "SWITCH_SCREEN":
                sel = self._lst_screens.curselection()
                if not sel: return
                data = self._lst_screens.get(sel[0])
            elif cmd == "ADD_SCREEN":
                data = simpledialog.askstring("New Screen", "Name:", parent=self._root)
            elif cmd == "RENAME_SCREEN":
                sel = self._lst_screens.curselection()
                if not sel: return
                old = self._lst_screens.get(sel[0])
                new = simpledialog.askstring("Rename Screen", "New name:", parent=self._root)
                if new: data = (old, new)
            elif cmd == "INSERT_ASSET":
                sel = self._lst_assets.curselection()
                if not sel: return
                data = self._lst_assets.get(sel[0])
            elif cmd == "SAVE_ASSET":
                data = simpledialog.askstring("Save Asset", "Name for this asset:", parent=self._root)
        except Exception:
            data = None

        if data is not None or cmd == "SAVE_ASSET":
            # push to designer queue
            try:
                self.queue.put((cmd, data))
            except Exception:
                pass

    # assets management
    def _load_lib(self) -> Dict[str, Any]:
        try:
            p = Path("library.json")
            if not p.exists(): return {}
            text = p.read_text(encoding="utf-8")
            return json.loads(text) if text else {}
        except Exception:
            return {}

    def _write_lib(self, lib: Dict[str, Any]):
        try:
            Path("library.json").write_text(json.dumps(lib, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _delete_asset(self):
        try:
            sel = self._lst_assets.curselection()
            if not sel: return
            key = self._lst_assets.get(sel[0])
            lib = self._load_lib()
            if key in lib:
                del lib[key]
                self._write_lib(lib)
            self._refresh_assets()
        except Exception:
            pass

    def _refresh_assets(self):
        # Called on Tk thread
        try:
            lib = self._load_lib()
            keys = sorted(lib.keys())
            if self._lst_assets is None:
                return
            cur = self._list_items(self._lst_assets)
            if cur != keys:
                # preserve selection by name if possible
                prev = None
                sel = self._lst_assets.curselection()
                if sel:
                    try:
                        prev = self._lst_assets.get(sel[0])
                    except Exception:
                        prev = None
                self._lst_assets.delete(0, tk.END)
                for k in keys:
                    self._lst_assets.insert(tk.END, k)
                if prev and prev in keys:
                    idx = keys.index(prev)
                    try:
                        self._lst_assets.selection_clear(0, tk.END)
                        self._lst_assets.selection_set(idx)
                        self._lst_assets.see(idx)
                    except Exception:
                        pass
        except Exception:
            pass

    # blocking editors (Designer calls these; they schedule Tk dialogs and wait)
    def edit_text_blocking(self, initial: str = "", title: str = "Edit Text") -> Optional[str]:
        """
        Open a modal multiline text editor on the Tk thread and wait for user's choice.
        Returns string or None if cancelled.
        """
        # If GUI not available, fall back to simple input (single-line) in designer (rare).
        if not self.ready.is_set() or self._root is None:
            return initial

        result: Dict[str, Optional[str]] = {"value": None}
        done = threading.Event()

        def open_dialog():
            dlg = tk.Toplevel(self._root)
            dlg.title(title)
            dlg.geometry("640x420")
            dlg.transient(self._root)
            txt = scrolledtext.ScrolledText(dlg, wrap="none", font=("Courier", 10))
            txt.pack(fill="both", expand=True, padx=6, pady=6)
            txt.insert("1.0", initial)

            def on_ok():
                try:
                    result["value"] = txt.get("1.0", "end-1c")
                except Exception:
                    result["value"] = ""
                try:
                    dlg.grab_release()
                except Exception:
                    pass
                dlg.destroy()
                done.set()

            def on_cancel():
                result["value"] = None
                try:
                    dlg.grab_release()
                except Exception:
                    pass
                dlg.destroy()
                done.set()

            btnf = tk.Frame(dlg); btnf.pack(fill="x", padx=6, pady=6)
            tk.Button(btnf, text="OK", command=on_ok).pack(side="left", padx=6)
            tk.Button(btnf, text="Cancel", command=on_cancel).pack(side="left", padx=6)

            try:
                dlg.grab_set()
                dlg.focus_force()
            except Exception:
                pass

        # schedule and wait
        self._root.after(0, open_dialog)
        done.wait()
        return result["value"]

    def edit_props_blocking(self, obj: UIElement) -> Optional[Dict[str, Any]]:
        """
        Open a property editor for the provided object on Tk thread.
        Returns props dict or None.
        """
        if not self.ready.is_set() or self._root is None:
            return None

        result: Dict[str, Optional[Dict[str, Any]]] = {"props": None}
        done = threading.Event()

        def open_dialog():
            dlg = tk.Toplevel(self._root)
            dlg.title(f"Edit: {obj.name} ({obj.type})")
            dlg.geometry("420x360")
            dlg.transient(self._root)

            frm = tk.Frame(dlg)
            frm.pack(fill="both", expand=True, padx=6, pady=6)
            entries: Dict[str, tk.Entry] = {}

            row = 0
            def add_pair(label_text: str, key: str, init_val: str):
                nonlocal row
                tk.Label(frm, text=label_text).grid(row=row, column=0, sticky="w")
                ent = tk.Entry(frm)
                ent.grid(row=row, column=1, sticky="ew", padx=4, pady=2)
                ent.insert(0, str(init_val))
                entries[key] = ent
                row += 1

            add_pair("Name", "name", obj.name)
            tk.Label(frm, text="Color").grid(row=row, column=0, sticky="w")
            color_var = tk.StringVar(value=obj.color.name if hasattr(obj, "color") else "WHITE")
            color_combo = ttk.Combobox(frm, values=Color.names(), textvariable=color_var, state="readonly")
            color_combo.grid(row=row, column=1, sticky="ew", padx=4, pady=2)
            row += 1

            if isinstance(obj, Box):
                add_pair("X", "x", obj.x); add_pair("Y", "y", obj.y)
                add_pair("W", "w", obj.w); add_pair("H", "h", obj.h)
            elif isinstance(obj, Line):
                add_pair("X1", "x1", obj.x1); add_pair("Y1", "y1", obj.y1)
                add_pair("X2", "x2", obj.x2); add_pair("Y2", "y2", obj.y2)
            elif isinstance(obj, Text):
                tk.Label(frm, text="Content").grid(row=row, column=0, sticky="nw")
                txt = scrolledtext.ScrolledText(frm, height=10, width=40, font=("Courier", 10))
                txt.grid(row=row, column=1, sticky="ew", padx=4, pady=2)
                txt.insert("1.0", obj.content)
                row += 1
            elif isinstance(obj, Freehand):
                tk.Label(frm, text="Lines").grid(row=row, column=0, sticky="nw")
                txt = scrolledtext.ScrolledText(frm, height=10, width=40, font=("Courier", 10))
                txt.grid(row=row, column=1, sticky="ew", padx=4, pady=2)
                txt.insert("1.0", "\n".join(obj.lines))
                row += 1

            frm.grid_columnconfigure(1, weight=1)

            def on_ok():
                props: Dict[str, Any] = {}
                # name
                try:
                    props['name'] = entries.get("name").get().strip() if "name" in entries else obj.name
                except Exception:
                    props['name'] = obj.name
                # color
                try:
                    props['color'] = color_var.get()
                except Exception:
                    props['color'] = obj.color.name
                # per-type
                try:
                    if isinstance(obj, Box):
                        props['x'] = int(entries['x'].get()); props['y'] = int(entries['y'].get())
                        props['w'] = int(entries['w'].get()); props['h'] = int(entries['h'].get())
                    elif isinstance(obj, Line):
                        props['x1'] = int(entries['x1'].get()); props['y1'] = int(entries['y1'].get())
                        props['x2'] = int(entries['x2'].get()); props['y2'] = int(entries['y2'].get())
                    elif isinstance(obj, Text):
                        props['content'] = txt.get("1.0", "end-1c")
                    elif isinstance(obj, Freehand):
                        raw = txt.get("1.0", "end-1c")
                        props['lines'] = [ln.rstrip("\n") for ln in raw.splitlines()]
                except Exception:
                    # ignore conversion issues; caller will validate
                    pass
                result['props'] = props
                try:
                    dlg.grab_release()
                except Exception:
                    pass
                dlg.destroy()
                done.set()

            def on_cancel():
                result['props'] = None
                try:
                    dlg.grab_release()
                except Exception:
                    pass
                dlg.destroy()
                done.set()

            btnf = tk.Frame(dlg); btnf.pack(fill="x", padx=6, pady=6)
            tk.Button(btnf, text="OK", command=on_ok).pack(side="left", padx=6)
            tk.Button(btnf, text="Cancel", command=on_cancel).pack(side="left", padx=6)

            try:
                dlg.grab_set()
                dlg.focus_force()
            except Exception:
                pass

        self._root.after(0, open_dialog)
        done.wait()
        return result["props"]

# ---------------------------
# Project manager (save/load/generate)
# ---------------------------
class ProjectManager:
    H_FILE = "ui_layout.h"
    CPP_FILE = "ui_layout.cpp"
    LIB_FILE = "SerialUI.h"

    def ensure_lib(self):
        try:
            if not Path(self.LIB_FILE).exists():
                Path(self.LIB_FILE).write_text(SERIAL_UI_HEADER, encoding="utf-8")
        except Exception:
            pass

    def save_project(self, screens: List[Screen]):
        self.ensure_lib()
        try:
            h = ['#ifndef UI_LAYOUT_H', '#define UI_LAYOUT_H', '#include "SerialUI.h"', '']
            for s in screens:
                h.append(f'struct Layout_{s.name} {{')
                for o in s.objects:
                    cpp_type = f"UI_{o.type.capitalize()}"
                    h.append(f'    static const {cpp_type} {o.name};')
                h.append('};')
                h.append(f'void drawScreen_{s.name}(SerialUI& ui);')
                h.append('')
            h.append('#endif')
            Path(self.H_FILE).write_text("\n".join(h), encoding="utf-8")

            cpp = ['#include "ui_layout.h"', '', '// RESOURCES']
            processed = set()
            for s in screens:
                for o in s.objects:
                    if isinstance(o, Freehand) and o.name not in processed:
                        processed.add(o.name)
                        for i, line in enumerate(o.lines):
                            safe = line.replace('\\', '\\\\').replace('"', '\\"')
                            cpp.append(f'const char RES_{o.name}_L{i}[] PROGMEM = "{safe}";')
                        arr = ", ".join([f"RES_{o.name}_L{i}" for i in range(len(o.lines))])
                        cpp.append(f'const char* const RES_{o.name}_ARR[] PROGMEM = {{ {arr} }};\n')

            cpp.append('// IMPLEMENTATION')
            for s in screens:
                for o in s.objects:
                    cpp.append(f'const UI_{o.type.capitalize()} Layout_{s.name}::{o.name} = {o.cpp_struct_init()};')
                cpp.append(f'\nvoid drawScreen_{s.name}(SerialUI& ui) {{')
                for o in s.objects:
                    cpp.append(f'    ui.draw(Layout_{s.name}::{o.name});')
                cpp.append('}\n')
            Path(self.CPP_FILE).write_text("\n".join(cpp), encoding="utf-8")
        except Exception as e:
            raise

    def load_project(self) -> List[Screen]:
        try:
            p = Path("project.json")
            if not p.exists(): return [Screen("Main")]
            txt = p.read_text(encoding="utf-8")
            data = json.loads(txt) if txt else []
            screens: List[Screen] = []
            for s in data:
                name = s.get('name', 'Main')
                scr = Screen(name)
                for o in s.get('objects', []):
                    elem = UIElement.from_dict(o)
                    if elem:
                        scr.objects.append(elem)
                screens.append(scr)
            if not screens:
                return [Screen("Main")]
            return screens
        except Exception:
            return [Screen("Main")]

    def save_json_state(self, screens: List[Screen]):
        try:
            data = [{'name': s.name, 'objects': [o.to_dict() for o in s.objects]} for s in screens]
            Path("project.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

# ---------------------------
# Designer (curses)
# ---------------------------
class Mode(Enum):
    NAV = auto(); BOX_1 = auto(); BOX_2 = auto(); LINE_1 = auto(); LINE_2 = auto()

class Designer:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.pm = ProjectManager()
        self.screens = self.pm.load_project()
        self.act_idx = 0
        self.mode = Mode.NAV
        self.cx = 5; self.cy = 5
        self.sel_idx = -1
        self.temp: Dict[str, int] = {}
        self.gui = GuiManager()
        self.gui.ready.wait(3)
        self.msg = "Welcome."
        # ensure at least one screen
        if not self.screens:
            self.screens = [Screen("Main")]

    @property
    def cur_screen(self) -> Screen:
        if 0 <= self.act_idx < len(self.screens):
            return self.screens[self.act_idx]
        # recover
        self.act_idx = 0
        return self.screens[0]

    @property
    def cur_objs(self) -> List[UIElement]:
        return self.cur_screen.objects

    def _valid_sel(self) -> bool:
        return 0 <= self.sel_idx < len(self.cur_objs)

    def _clamp_sel(self):
        if not self.cur_objs:
            self.sel_idx = -1
        elif self.sel_idx >= len(self.cur_objs):
            self.sel_idx = len(self.cur_objs) - 1
        elif self.sel_idx < 0:
            self.sel_idx = -1

    def run(self):
        curses.start_color()
        curses.use_default_colors()
        try: curses.curs_set(1)
        except Exception: pass
        for i, c in enumerate(Color, 1):
            try:
                curses.init_pair(i, getattr(curses, f"COLOR_{c.name}", curses.COLOR_WHITE), -1)
            except Exception:
                pass
        self.stdscr.nodelay(True)

        while True:
            self._clamp_sel()
            self._draw()
            self._process_gui()
            try:
                key = self.stdscr.getch()
            except Exception:
                key = -1
            if key == -1:
                curses.napms(30)
                continue
            if not self._handle_key(key):
                break

    def _process_gui(self):
        try:
            while True:
                cmd, data = self.gui.queue.get_nowait()
                if cmd == "SWITCH_SCREEN":
                    for i, s in enumerate(self.screens):
                        if s.name == data:
                            self.act_idx = i
                            self.sel_idx = -1
                            self.msg = f"Switched to {s.name}"
                elif cmd == "ADD_SCREEN":
                    if data:
                        safe = re.sub(r'[^a-zA-Z0-9_]', '', data) or "Screen"
                        self.screens.append(Screen(safe))
                        self.act_idx = len(self.screens) - 1
                        self.sel_idx = -1
                        self.msg = f"Added screen {safe}"
                elif cmd == "RENAME_SCREEN":
                    if data:
                        old, new = data
                        safe = re.sub(r'[^a-zA-Z0-9_]', '', new) or old
                        for s in self.screens:
                            if s.name == old:
                                s.name = safe
                                self.msg = f"Renamed {old} -> {safe}"
                elif cmd == "SAVE_ASSET":
                    if self._valid_sel() and data:
                        o = self.cur_objs[self.sel_idx]
                        lib = self.gui._load_lib()
                        d = o.to_dict()
                        d['name'] = data
                        lib[data] = d
                        self.gui._write_lib(lib)
                        # refresh assets on GUI via scheduling
                        if self.gui._root:
                            self.gui._root.after(0, self.gui._refresh_assets)
                        self.msg = f"Saved asset '{data}'"
                elif cmd == "INSERT_ASSET":
                    lib = self.gui._load_lib()
                    if data in lib:
                        new_obj = UIElement.from_dict(lib[data])
                        if new_obj:
                            # place at current cursor/location
                            if hasattr(new_obj, 'x') and hasattr(new_obj, 'y'):
                                new_obj.x = self.cx; new_obj.y = self.cy
                            if isinstance(new_obj, Line):
                                w = new_obj.x2 - new_obj.x1
                                h = new_obj.y2 - new_obj.y1
                                new_obj.x1 = self.cx; new_obj.y1 = self.cy
                                new_obj.x2 = self.cx + w; new_obj.y2 = self.cy + h
                            if isinstance(new_obj, Freehand):
                                new_obj.x = self.cx; new_obj.y = self.cy
                            # unique name
                            base = new_obj.name or "asset"
                            used = {o.name for o in self.cur_objs}
                            cnt = 1
                            while new_obj.name in used or not new_obj.name:
                                new_obj.name = f"{base}_{cnt}"; cnt += 1
                            self.cur_objs.append(new_obj)
                            self.sel_idx = len(self.cur_objs) - 1
                            self.msg = f"Inserted asset {new_obj.name}"
                # after structural changes, update Tk lists
                if self.gui._root:
                    try:
                        names = [s.name for s in self.screens]
                        self.gui._root.after(0, lambda n=names, a=self.cur_screen.name: self.gui._root and self.gui._root and self.gui.update_state(n))  # harmless schedule to keep GUI in sync
                    except Exception:
                        pass
        except queue.Empty:
            pass

    def _handle_key(self, k: int) -> bool:
        # escape cancel
        if k == 27:
            self.mode = Mode.NAV
            self.sel_idx = -1
            self.msg = "Cancelled"
            return True

        dx = dy = 0
        if k == curses.KEY_UP: dy = -1
        elif k == curses.KEY_DOWN: dy = 1
        elif k == curses.KEY_LEFT: dx = -1
        elif k == curses.KEY_RIGHT: dx = 1

        if dx or dy:
            if self.mode == Mode.NAV and self._valid_sel():
                o = self.cur_objs[self.sel_idx]
                if hasattr(o, 'x'):
                    o.x += dx; o.y += dy
                if hasattr(o, 'x1'):
                    o.x1 += dx; o.y1 += dy; o.x2 += dx; o.y2 += dy
            else:
                self.cx += dx; self.cy += dy
                h, w = self.stdscr.getmaxyx()
                self.cx = max(0, min(w - 1, self.cx))
                self.cy = max(0, min(h - 2, self.cy))
            return True

        if self.mode == Mode.NAV:
            if k == ord('q'): return False
            if k == ord('s'):
                try:
                    self.pm.save_project(self.screens)
                    self.pm.save_json_state(self.screens)
                    self.msg = "Saved project & layout"
                except Exception as e:
                    self.msg = f"Save failed: {e}"
                return True
            if k == 9:  # Tab cycles selection
                if self.cur_objs:
                    if self.sel_idx < 0: self.sel_idx = 0
                    else: self.sel_idx = (self.sel_idx + 1) % len(self.cur_objs)
            if k == ord('b'):
                self.mode = Mode.BOX_1; self.msg = "Box: set start -> Enter"
            if k == ord('l'):
                self.mode = Mode.LINE_1; self.msg = "Line: set start -> Enter"
            if k == ord('t'):
                self._create_text()
            if k == ord('d') and self._valid_sel():
                try:
                    self.cur_objs.pop(self.sel_idx)
                except Exception:
                    pass
                self.sel_idx = -1
                self.msg = "Deleted object"
            if k == ord('c') and self._valid_sel():
                o = self.cur_objs[self.sel_idx]
                cl = list(Color)
                try:
                    idx = cl.index(o.color)
                except Exception:
                    idx = 0
                o.color = cl[(idx + 1) % len(cl)]
                self.msg = "Color changed"
            if k == ord('n') and self._valid_sel():
                self._rename_obj()
            if k == ord('e') and self._valid_sel():
                target = self.cur_objs[self.sel_idx]
                # open properties editor (blocking)
                props = None
                try:
                    props = self.gui.edit_props_blocking(target)
                except Exception:
                    props = None
                if props is not None:
                    # apply props safely
                    try:
                        nm = props.get('name', target.name)
                        nm_safe = re.sub(r'[^a-zA-Z0-9_]', '', nm) or target.name
                        target.name = nm_safe
                        target.color = Color.from_str(props.get('color', target.color.name))
                        if isinstance(target, Box):
                            target.x = int(props.get('x', target.x))
                            target.y = int(props.get('y', target.y))
                            target.w = max(1, int(props.get('w', target.w)))
                            target.h = max(1, int(props.get('h', target.h)))
                        if isinstance(target, Line):
                            target.x1 = int(props.get('x1', target.x1)); target.y1 = int(props.get('y1', target.y1))
                            target.x2 = int(props.get('x2', target.x2)); target.y2 = int(props.get('y2', target.y2))
                        if isinstance(target, Text):
                            target.content = str(props.get('content', target.content))
                        if isinstance(target, Freehand):
                            lines = props.get('lines', target.lines)
                            if isinstance(lines, list):
                                target.lines = lines
                            else:
                                target.lines = str(lines).splitlines()
                        self.msg = f"Updated {target.name}"
                    except Exception as e:
                        self.msg = f"Edit failed: {e}"
            # layer controls
            if k == ord('[') and self._valid_sel() and self.sel_idx > 0:
                self.cur_objs[self.sel_idx - 1], self.cur_objs[self.sel_idx] = self.cur_objs[self.sel_idx], self.cur_objs[self.sel_idx - 1]
                self.sel_idx -= 1
                self.msg = "Moved back"
            if k == ord(']') and self._valid_sel() and self.sel_idx < len(self.cur_objs) - 1:
                self.cur_objs[self.sel_idx + 1], self.cur_objs[self.sel_idx] = self.cur_objs[self.sel_idx], self.cur_objs[self.sel_idx + 1]
                self.sel_idx += 1
                self.msg = "Moved forward"
            return True

        # creation flows:
        if self.mode == Mode.BOX_1 and k in (10, 13):
            self.temp = {'x': self.cx, 'y': self.cy}
            self.mode = Mode.BOX_2; self.msg = "Box: set end -> Enter"
        elif self.mode == Mode.BOX_2 and k in (10, 13):
            x = min(self.temp['x'], self.cx); y = min(self.temp['y'], self.cy)
            w = abs(self.temp['x'] - self.cx) + 1; h = abs(self.temp['y'] - self.cy) + 1
            name = f"box_{len(self.cur_objs)}"
            new = Box(name=name, color=Color.WHITE, x=x, y=y, w=w, h=h, layer=len(self.cur_objs))
            self.cur_objs.append(new); self.sel_idx = len(self.cur_objs) - 1; self.mode = Mode.NAV
            self.msg = f"Created {name}"
        elif self.mode == Mode.LINE_1 and k in (10, 13):
            self.temp = {'x': self.cx, 'y': self.cy}
            self.mode = Mode.LINE_2; self.msg = "Line: set end -> Enter"
        elif self.mode == Mode.LINE_2 and k in (10, 13):
            name = f"line_{len(self.cur_objs)}"
            new = Line(name=name, color=Color.WHITE, x1=self.temp['x'], y1=self.temp['y'], x2=self.cx, y2=self.cy, layer=len(self.cur_objs))
            self.cur_objs.append(new); self.sel_idx = len(self.cur_objs) - 1; self.mode = Mode.NAV
            self.msg = f"Created {name}"

        return True

    def _create_text(self):
        try:
            text = self.gui.edit_text_blocking("", title="New multi-line Text")
        except Exception:
            text = None
        if text is None:
            self.msg = "Text creation cancelled"
            return
        name = f"txt_{len(self.cur_objs)}"
        new = Text(name=name, color=Color.WHITE, x=self.cx, y=self.cy, content=str(text), layer=len(self.cur_objs))
        self.cur_objs.append(new); self.sel_idx = len(self.cur_objs) - 1
        self.msg = f"Added {name}"

    def _rename_obj(self):
        curses.echo()
        try:
            self.stdscr.addstr(0, 0, "New Name: ")
            t = self.stdscr.getstr().decode('utf-8')
        except Exception:
            t = ""
        finally:
            curses.noecho()
        if t and self._valid_sel():
            safe = re.sub(r'[^a-zA-Z0-9_]', '', t)
            if safe:
                self.cur_objs[self.sel_idx].name = safe
                self.msg = f"Renamed to {safe}"

    def _draw(self):
        self.stdscr.clear()
        # draw in list order (0 bottom)
        for i, o in enumerate(self.cur_objs):
            try:
                attr = curses.color_pair(list(Color).index(o.color) + 1)
            except Exception:
                attr = curses.A_NORMAL
            if i == self.sel_idx:
                attr |= (curses.A_BOLD | curses.A_REVERSE)
            try:
                if isinstance(o, Box):
                    # draw corners and edges
                    self.stdscr.addch(o.y, o.x, '+', attr)
                    self.stdscr.addch(o.y + o.h - 1, o.x + o.w - 1, '+', attr)
                    for k in range(1, max(1, o.w - 1)):
                        self.stdscr.addch(o.y, o.x + k, '-', attr)
                        self.stdscr.addch(o.y + o.h - 1, o.x + k, '-', attr)
                    for k in range(1, max(1, o.h - 1)):
                        self.stdscr.addch(o.y + k, o.x, '|', attr)
                        self.stdscr.addch(o.y + k, o.x + o.w - 1, '|', attr)
                elif isinstance(o, Text):
                    lines = o.content.splitlines() or [""]
                    for r, ln in enumerate(lines):
                        self.stdscr.addstr(o.y + r, o.x, ln[:max(0, 1000)], attr)
                elif isinstance(o, Line):
                    x1, y1, x2, y2 = o.x1, o.y1, o.x2, o.y2
                    dx = abs(x2 - x1); sx = 1 if x1 < x2 else -1
                    dy = -abs(y2 - y1); sy = 1 if y1 < y2 else -1
                    err = dx + dy
                    cx, cy = x1, y1
                    while True:
                        self.stdscr.addch(cy, cx, '#', attr)
                        if cx == x2 and cy == y2: break
                        e2 = 2 * err
                        if e2 >= dy: err += dy; cx += sx
                        if e2 <= dx: err += dx; cy += sy
                elif isinstance(o, Freehand):
                    for r, ln in enumerate(o.lines):
                        self.stdscr.addstr(o.y + r, o.x, ln, attr)
            except curses.error:
                pass

        # status bar
        h, w = self.stdscr.getmaxyx()
        sel_name = ""
        if self._valid_sel():
            try:
                sel_name = f" | Sel: {self.cur_objs[self.sel_idx].name}"
            except Exception:
                sel_name = ""
        stat = f"[{self.cur_screen.name}] {self.msg}{sel_name} | Pos:{self.cx},{self.cy}  (e:edit t:text b:box l:line )"
        try:
            self.stdscr.addstr(h - 1, 0, stat[:w - 1], curses.A_REVERSE)
            self.stdscr.move(max(0, min(h - 2, self.cy)), max(0, min(w - 1, self.cx)))
        except Exception:
            pass
        self.stdscr.refresh()

        # update Tk help and lists (non-destructive)
        if self.gui._root:
            try:
                # update help text
                help_txt = (
                    f"MODE: {self.mode.name}\n\n"
                    "Arrows: move cursor/object\n"
                    "Tab: next object\n"
                    "b: box, l: line, t: text, e: edit properties\n"
                    "[: layer down, ]: layer up\n"
                    "s: save, d: delete"
                )
                # call a small-safe function on Tk thread to update lists without stomping user selection
                def _sync():
                    try:
                        # help
                        if self.gui.help_var is not None:
                            self.gui.help_var.set(help_txt)
                        # screens: only replace if different and not focused
                        if self.gui._lst_screens:
                            incoming = [s.name for s in self.screens]
                            cur = self.gui._list_items(self.gui._lst_screens)
                            focused = (self.gui._root.focus_get() is self.gui._lst_screens)
                            if cur != incoming and not focused:
                                self.gui._lst_screens.delete(0, tk.END)
                                for n in incoming:
                                    self.gui._lst_screens.insert(tk.END, n)
                                # select active screen if present
                                try:
                                    idx = incoming.index(self.cur_screen.name) if self.cur_screen.name in incoming else 0
                                    self.gui._lst_screens.selection_clear(0, tk.END)
                                    self.gui._lst_screens.selection_set(idx)
                                    self.gui._lst_screens.see(idx)
                                except Exception:
                                    pass
                        # assets refresh (non-destructive)
                        if self.gui._lst_assets:
                            self.gui._refresh_assets()
                    except Exception:
                        pass
                self.gui._root.after(0, _sync)
            except Exception:
                pass

# ---------------------------
# Main
# ---------------------------
def main():
    try:
        curses.wrapper(lambda scr: Designer(scr).run())
    except Exception as e:
        # attempt terminal restore
        try: curses.nocbreak()
        except: pass
        try: curses.echo()
        except: pass
        try: curses.endwin()
        except: pass
        print("Critical Error:", e)

if __name__ == "__main__":
    main()
