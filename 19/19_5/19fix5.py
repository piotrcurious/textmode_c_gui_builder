from __future__ import annotations
import curses
import re
import threading
import queue
import json
import tkinter as tk
from tkinter import scrolledtext, ttk, messagebox, simpledialog
from enum import Enum, auto
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict, Any

# ==============================================================================
# SERIAL UI ENGINE HEADER (for code generation)
# ==============================================================================

SERIAL_UI_HEADER = r"""
#ifndef SERIAL_UI_H
#define SERIAL_UI_H
#include <Arduino.h>
#include <avr/pgmspace.h>

// --- TYPES ---
enum class UI_Color { WHITE=37, RED=31, GREEN=32, YELLOW=33, BLUE=34, MAGENTA=35, CYAN=36 };

// POD (Plain Old Data) Structures for Layout Anchors
struct UI_Box { int16_t x, y, w, h; UI_Color color; };
struct UI_Text { int16_t x, y; const char* content; UI_Color color; };
struct UI_Line { int16_t x1, y1, x2, y2; UI_Color color; };
struct UI_Freehand { int16_t x, y; const char* const* lines; uint8_t count; UI_Color color; };

// --- ENGINE ---
class SerialUI {
public:
    void begin(long baud = 115200) {
        Serial.begin(baud);
        while (!Serial) delay(10);
        Serial.print("\x1b[?25l"); // Hide cursor
        clearScreen();
    }
    void clearScreen() { Serial.print("\x1b[2J\x1b[H"); }
    void resetAttr() { Serial.print("\x1b[0m"); }
    
    void setColor(UI_Color color) {
        Serial.print("\x1b[0;"); Serial.print((int)color); Serial.print("m");
    }
    void moveCursor(int x, int y) {
        Serial.print("\x1b["); Serial.print(y + 1); Serial.print(";"); Serial.print(x + 1); Serial.print("H");
    }

    // --- DRAWING METHODS (Accept Structs) ---
    
    void draw(const UI_Text& t) {
        setColor(t.color); moveCursor(t.x, t.y); Serial.print(t.content); resetAttr();
    }

    void draw(const UI_Box& b) {
        setColor(b.color);
        for (int i = 0; i < b.w; i++) {
            moveCursor(b.x + i, b.y); Serial.print("-"); moveCursor(b.x + i, b.y + b.h - 1); Serial.print("-");
        }
        for (int i = 0; i < b.h; i++) {
            moveCursor(b.x, b.y + i); Serial.print("|"); moveCursor(b.x + b.w - 1, b.y + i); Serial.print("|");
        }
        moveCursor(b.x, b.y); Serial.print("+"); moveCursor(b.x + b.w - 1, b.y); Serial.print("+");
        moveCursor(b.x, b.y + b.h - 1); Serial.print("+"); moveCursor(b.x + b.w - 1, b.y + b.h - 1); Serial.print("+");
        resetAttr();
    }

    void draw(const UI_Line& l) {
        setColor(l.color);
        int dx = abs(l.x2 - l.x1), sx = l.x1 < l.x2 ? 1 : -1;
        int dy = -abs(l.y2 - l.y1), sy = l.y1 < l.y2 ? 1 : -1;
        int err = dx + dy, e2;
        int x = l.x1, y = l.y1;
        while (true) {
            moveCursor(x, y); Serial.print("#");
            if (x == l.x2 && y == l.y2) break;
            e2 = 2 * err;
            if (e2 >= dy) { err += dy; x += sx; }
            if (e2 <= dx) { err += dx; y += sy; }
        }
        resetAttr();
    }

    void draw(const UI_Freehand& f) {
        setColor(f.color);
        for(int i=0; i<f.count; i++) {
            moveCursor(f.x, f.y + i);
            const char* strPtr = (const char*)pgm_read_ptr(&(f.lines[i]));
            while(uint8_t c = pgm_read_byte(strPtr++)) { Serial.write(c); }
        }
        resetAttr();
    }
};
#endif
"""

# ==============================================================================
# DATA MODEL (Serializable)
# ==============================================================================

class Color(Enum):
    WHITE = 37; RED = 31; GREEN = 32; YELLOW = 33; BLUE = 34; MAGENTA = 35; CYAN = 36

    @classmethod
    def from_str(cls, s: str):
        try:
            return cls[s.upper()]
        except Exception:
            return cls.WHITE

    @classmethod
    def names(cls):
        return [c.name for c in cls]

@dataclass
class UIElement:
    name: str
    color: Color = Color.WHITE
    type: str = "BASE"
    layer: int = 0   # lower numbers drawn first

    def to_dict(self):
        d = asdict(self)
        d['color'] = self.color.name
        return d

    @staticmethod
    def from_dict(d: dict):
        t = d.get('type', 'BASE')
        col = Color.from_str(d.get('color', 'WHITE'))
        layer = int(d.get('layer', 0))
        if t == "BOX":
            return Box(
                name=d.get('name', 'box'),
                color=col,
                x=int(d.get('x', 0)),
                y=int(d.get('y', 0)),
                w=int(d.get('w', 0)),
                h=int(d.get('h', 0)),
                layer=layer
            )
        if t == "TEXT":
            return Text(
                name=d.get('name', 'txt'),
                color=col,
                x=int(d.get('x', 0)),
                y=int(d.get('y', 0)),
                content=str(d.get('content', '')),
                layer=layer
            )
        if t == "LINE":
            return Line(
                name=d.get('name', 'line'),
                color=col,
                x1=int(d.get('x1', 0)),
                y1=int(d.get('y1', 0)),
                x2=int(d.get('x2', 0)),
                y2=int(d.get('y2', 0)),
                layer=layer
            )
        if t == "FREEHAND":
            return Freehand(
                name=d.get('name', 'fh'),
                color=col,
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
        # escape quotes and backslashes, replace real newline with \n sequence
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

# ==============================================================================
# GUI & ASSET MANAGER (Tk thread) - includes blocking editors
# ==============================================================================

class GuiManager:
    def __init__(self):
        self.queue = queue.Queue()   # GUI -> Designer (button events)
        self.root = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.ready = threading.Event()
        self.help_var = None
        self.lst_scr = None
        self.lst_assets = None

    def _run(self):
        self.root = tk.Tk()
        self.root.title("UI Helper")
        self.root.geometry("440x560")
        try:
            self.root.attributes('-topmost', True)
        except Exception:
            pass

        tabs = ttk.Notebook(self.root)
        tabs.pack(fill="both", expand=True)

        # HELP
        f_help = tk.Frame(tabs)
        tabs.add(f_help, text="Help & Status")
        self.help_var = tk.StringVar(value="Initializing...")
        lbl_help = tk.Label(f_help, textvariable=self.help_var, justify="left",
                            font=("Consolas", 10), wraplength=420, bg="#f8f8f8", relief="groove")
        lbl_help.pack(fill="both", expand=True, padx=6, pady=6)

        # SCREENS
        f_scr = tk.Frame(tabs)
        tabs.add(f_scr, text="Screens")
        self.lst_scr = tk.Listbox(f_scr, height=8, exportselection=False)
        self.lst_scr.pack(fill="x", padx=6, pady=6)
        btn_fr = tk.Frame(f_scr)
        btn_fr.pack(fill="x", pady=4)
        tk.Button(btn_fr, text="Switch To", command=lambda: self._emit("SWITCH_SCREEN")).pack(side="left", padx=6)
        tk.Button(btn_fr, text="New Screen", command=lambda: self._emit("ADD_SCREEN")).pack(side="left")
        tk.Button(btn_fr, text="Rename", command=lambda: self._emit("RENAME_SCREEN")).pack(side="left", padx=6)

        # ASSETS
        f_assets = tk.Frame(tabs)
        tabs.add(f_assets, text="Asset Library")
        self.lst_assets = tk.Listbox(f_assets, exportselection=False)
        self.lst_assets.pack(fill="both", expand=True, padx=6, pady=6)
        a_btn_fr = tk.Frame(f_assets)
        a_btn_fr.pack(fill="x", pady=4)
        tk.Button(a_btn_fr, text="Insert Selected", bg="#ddffdd", command=lambda: self._emit("INSERT_ASSET")).pack(side="left", padx=6)
        tk.Button(a_btn_fr, text="Delete Asset", command=self._delete_asset).pack(side="right", padx=6)

        # Save asset from curses
        tk.Button(self.root, text="Save Selected Object to Library", bg="#ffeebb",
                  command=lambda: self._emit("SAVE_ASSET")).pack(fill="x", padx=6, pady=6)

        # Bind focus events to avoid stomping selection during user interaction
        self.lst_scr.bind("<FocusIn>", lambda e: None)
        self.lst_assets.bind("<FocusIn>", lambda e: None)

        self.ready.set()
        self._refresh_assets()
        self.root.mainloop()

    # ---------- listbox helpers ----------
    def _listbox_items(self, lb: tk.Listbox) -> List[str]:
        try:
            return list(lb.get(0, tk.END))
        except Exception:
            return []

    # ---------- GUI -> Designer event emitter ----------
    def _emit(self, cmd):
        data = None
        try:
            if cmd == "SWITCH_SCREEN":
                sel = self.lst_scr.curselection()
                if not sel: return
                data = self.lst_scr.get(sel[0])
            elif cmd == "ADD_SCREEN":
                data = simpledialog.askstring("New Screen", "Name:")
            elif cmd == "RENAME_SCREEN":
                sel = self.lst_scr.curselection()
                if not sel: return
                old = self.lst_scr.get(sel[0])
                new = simpledialog.askstring("Rename", "New Name:")
                data = (old, new) if new else None
            elif cmd == "INSERT_ASSET":
                sel = self.lst_assets.curselection()
                if not sel: return
                data = self.lst_assets.get(sel[0])
            elif cmd == "SAVE_ASSET":
                data = simpledialog.askstring("Save Asset", "Name for this asset:")
        except Exception:
            data = None

        if data is not None or cmd in ["SAVE_ASSET"]:
            self.queue.put((cmd, data))

    # ---------- asset helpers ----------
    def _delete_asset(self):
        sel = self.lst_assets.curselection()
        if not sel: return
        key = self.lst_assets.get(sel[0])
        lib = self._load_lib()
        if key in lib:
            del lib[key]
            Path("library.json").write_text(json.dumps(lib, indent=2), encoding="utf-8")
        self._refresh_assets()

    def _load_lib(self) -> Dict[str, Any]:
        try:
            text = Path("library.json").read_text(encoding="utf-8")
            return json.loads(text) if text else {}
        except Exception:
            return {}

    def _refresh_assets(self):
        try:
            prev_sel = None
            sel = self.lst_assets.curselection()
            if sel:
                try: prev_sel = self.lst_assets.get(sel[0])
                except Exception: prev_sel = None

            lib = self._load_lib()
            keys = sorted(lib.keys())
            cur_items = self._listbox_items(self.lst_assets)
            if cur_items != keys:
                self.lst_assets.delete(0, tk.END)
                for k in keys:
                    self.lst_assets.insert(tk.END, k)
            if prev_sel and prev_sel in keys:
                idx = keys.index(prev_sel)
                try:
                    self.lst_assets.selection_clear(0, tk.END)
                    self.lst_assets.selection_set(idx)
                    self.lst_assets.see(idx)
                except Exception:
                    pass
        except Exception:
            pass

    # ---------- Blocking editors (Designer calls these and waits) ----------
    def edit_text_blocking(self, initial: str = "", title: str = "Edit Text") -> str | None:
        """
        Opens a modal multiline text editor in the GUI thread and waits
        for user to press OK/Cancel. Returns the text (string) or None.
        """
        result: Dict[str, Any] = {"text": None}
        ev = threading.Event()

        def _open():
            dlg = tk.Toplevel(self.root)
            dlg.title(title)
            dlg.geometry("640x480")
            # make modal
            dlg.transient(self.root)
            txt = scrolledtext.ScrolledText(dlg, wrap="none", font=("Courier", 10))
            txt.pack(fill="both", expand=True, padx=6, pady=6)
            txt.insert("1.0", initial)

            btn_fr = tk.Frame(dlg)
            btn_fr.pack(fill="x", padx=6, pady=6)
            def _ok():
                try:
                    result["text"] = txt.get("1.0", "end-1c")
                except Exception:
                    result["text"] = ""
                dlg.grab_release()
                dlg.destroy()
                ev.set()
            def _cancel():
                result["text"] = None
                dlg.grab_release()
                dlg.destroy()
                ev.set()
            tk.Button(btn_fr, text="OK", command=_ok).pack(side="left", padx=6)
            tk.Button(btn_fr, text="Cancel", command=_cancel).pack(side="left", padx=6)
            try:
                dlg.grab_set()
                dlg.focus_force()
            except Exception:
                pass

        # schedule on Tk thread
        self.root.after(0, _open)
        # wait on Designer thread until done
        ev.wait()
        return result["text"]

    def edit_props_blocking(self, obj: UIElement) -> dict | None:
        """
        Opens a modal properties editor for the provided object instance.
        Returns a dict of updated properties or None if cancelled.
        Only edits properties for the current screen's object instance.
        """
        result: Dict[str, Any] = {"props": None}
        ev = threading.Event()

        def _open():
            dlg = tk.Toplevel(self.root)
            dlg.title(f"Edit Properties: {obj.name} ({obj.type})")
            dlg.geometry("420x360")
            dlg.transient(self.root)

            frm = tk.Frame(dlg)
            frm.pack(fill="both", expand=True, padx=6, pady=6)

            entries: Dict[str, tk.Entry] = {}

            row = 0
            def add_label_entry(label_text: str, key: str, value: str):
                nonlocal row
                tk.Label(frm, text=label_text).grid(row=row, column=0, sticky="w")
                ent = tk.Entry(frm)
                ent.grid(row=row, column=1, sticky="ew", padx=4, pady=2)
                ent.insert(0, str(value))
                entries[key] = ent
                row += 1

            # common fields
            add_label_entry("Name", "name", obj.name)
            # color drop-down
            tk.Label(frm, text="Color").grid(row=row, column=0, sticky="w")
            color_var = tk.StringVar(value=obj.color.name if hasattr(obj, "color") else "WHITE")
            color_menu = ttk.Combobox(frm, values=Color.names(), textvariable=color_var, state="readonly")
            color_menu.grid(row=row, column=1, sticky="ew", padx=4, pady=2)
            row += 1

            # per-type fields
            if isinstance(obj, Box):
                add_label_entry("X", "x", obj.x)
                add_label_entry("Y", "y", obj.y)
                add_label_entry("W", "w", obj.w)
                add_label_entry("H", "h", obj.h)

            elif isinstance(obj, Line):
                add_label_entry("X1", "x1", obj.x1)
                add_label_entry("Y1", "y1", obj.y1)
                add_label_entry("X2", "x2", obj.x2)
                add_label_entry("Y2", "y2", obj.y2)

            elif isinstance(obj, Text):
                # For multi-line text, open a separate editor control
                tk.Label(frm, text="Content (multiline)").grid(row=row, column=0, sticky="nw")
                txt = scrolledtext.ScrolledText(frm, height=8, width=40, font=("Courier", 10))
                txt.grid(row=row, column=1, sticky="ew", padx=4, pady=2)
                txt.insert("1.0", obj.content)
                row += 1

            elif isinstance(obj, Freehand):
                tk.Label(frm, text="Lines (multiline)").grid(row=row, column=0, sticky="nw")
                txt = scrolledtext.ScrolledText(frm, height=8, width=40, font=("Courier", 10))
                txt.grid(row=row, column=1, sticky="ew", padx=4, pady=2)
                txt.insert("1.0", "\n".join(obj.lines))
                row += 1

            # make columns expandable
            frm.grid_columnconfigure(1, weight=1)

            btn_fr = tk.Frame(dlg)
            btn_fr.pack(fill="x", padx=6, pady=6)
            def _on_ok():
                props = {}
                # update name
                try:
                    props['name'] = entries.get("name").get().strip() if "name" in entries else obj.name
                except Exception:
                    props['name'] = obj.name
                # color
                try:
                    props['color'] = color_var.get()
                except Exception:
                    props['color'] = obj.color.name
                # per-type values
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
                        props['lines'] = [l.rstrip('\n') for l in raw.splitlines()]
                except Exception:
                    # ignore conversion errors; caller will validate
                    pass

                result['props'] = props
                try:
                    dlg.grab_release()
                except Exception:
                    pass
                dlg.destroy()
                ev.set()

            def _on_cancel():
                result['props'] = None
                try:
                    dlg.grab_release()
                except Exception:
                    pass
                dlg.destroy()
                ev.set()

            tk.Button(btn_fr, text="OK", command=_on_ok).pack(side="left", padx=6)
            tk.Button(btn_fr, text="Cancel", command=_on_cancel).pack(side="left", padx=6)

            try:
                dlg.grab_set()
                dlg.focus_force()
            except Exception:
                pass

        # schedule the dialog in Tk thread and wait
        self.root.after(0, _open)
        ev.wait()
        return result['props']

# ==============================================================================
# PROJECT MANAGER (save/load/generation)
# ==============================================================================

class ProjectManager:
    H_FILE = "ui_layout.h"
    CPP_FILE = "ui_layout.cpp"
    LIB_FILE = "SerialUI.h"

    def ensure_lib(self):
        if not Path(self.LIB_FILE).exists():
            Path(self.LIB_FILE).write_text(SERIAL_UI_HEADER, encoding="utf-8")

    def save_project(self, screens: List[Screen]):
        self.ensure_lib()
        # Header
        h_lines = [
            '#ifndef UI_LAYOUT_H', '#define UI_LAYOUT_H',
            '#include "SerialUI.h"', '',
            '// === LAYOUT ANCHORS ===',
        ]
        for s in screens:
            h_lines.append(f'struct Layout_{s.name} {{')
            for obj in s.objects:
                cpp_type = f"UI_{obj.type.capitalize()}"
                h_lines.append(f'    static const {cpp_type} {obj.name};')
            h_lines.append('};')
            h_lines.append(f'void drawScreen_{s.name}(SerialUI& ui);')
            h_lines.append('')
        h_lines.append('#endif')
        Path(self.H_FILE).write_text("\n".join(h_lines), encoding="utf-8")

        # CPP
        cpp_lines = ['#include "ui_layout.h"', '']
        cpp_lines.append('// === RESOURCES ===')
        processed = set()
        for s in screens:
            for obj in s.objects:
                if isinstance(obj, Freehand) and obj.name not in processed:
                    processed.add(obj.name)
                    for i, l in enumerate(obj.lines):
                        safe = l.replace('\\', '\\\\').replace('"', '\\"')
                        cpp_lines.append(f'const char RES_{obj.name}_L{i}[] PROGMEM = "{safe}";')
                    arr = ", ".join([f"RES_{obj.name}_L{i}" for i in range(len(obj.lines))])
                    cpp_lines.append(f'const char* const RES_{obj.name}_ARR[] PROGMEM = {{ {arr} }};\n')

        cpp_lines.append('// === IMPLEMENTATION ===')
        for s in screens:
            for obj in s.objects:
                cpp_type = f"UI_{obj.type.capitalize()}"
                init_val = obj.cpp_struct_init()
                cpp_lines.append(f'const {cpp_type} Layout_{s.name}::{obj.name} = {init_val};')
            cpp_lines.append(f'\nvoid drawScreen_{s.name}(SerialUI& ui) {{')
            for obj in s.objects:
                cpp_lines.append(f'    ui.draw(Layout_{s.name}::{obj.name});')
            cpp_lines.append('}\n')

        Path(self.CPP_FILE).write_text("\n".join(cpp_lines), encoding="utf-8")

    def load_project(self) -> List[Screen]:
        if Path("project.json").exists():
            try:
                txt = Path("project.json").read_text(encoding="utf-8")
                data = json.loads(txt) if txt else []
                screens: List[Screen] = []
                for s_data in data:
                    s = Screen(s_data.get('name', 'Main'))
                    s.objects = []
                    for o in s_data.get('objects', []):
                        elem = UIElement.from_dict(o)
                        if elem:
                            s.objects.append(elem)
                    screens.append(s)
                if not screens:
                    return [Screen("Main")]
                return screens
            except Exception:
                pass
        return [Screen("Main")]

    def save_json_state(self, screens: List[Screen]):
        data = [{'name': s.name, 'objects': [o.to_dict() for o in s.objects]} for s in screens]
        Path("project.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

# ==============================================================================
# DESIGNER (curses)
# ==============================================================================

class Mode(Enum):
    NAV = auto(); BOX_1 = auto(); BOX_2 = auto(); LINE_1 = auto(); LINE_2 = auto()

class Designer:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.pm = ProjectManager()
        self.screens = self.pm.load_project()
        self.act_idx = 0
        self.mode = Mode.NAV
        self.cx, self.cy = 5, 5
        self.sel_idx = -1
        self.temp: dict = {}
        self.gui = GuiManager()
        # wait for GUI to come up
        self.gui.ready.wait(3)
        self.msg = "Welcome."
        self._update_gui_once()

    @property
    def cur_screen(self) -> Screen:
        if 0 <= self.act_idx < len(self.screens):
            return self.screens[self.act_idx]
        if self.screens:
            self.act_idx = 0
            return self.screens[0]
        self.screens = [Screen("Main")]
        self.act_idx = 0
        return self.screens[0]

    @property
    def cur_objs(self) -> List[UIElement]:
        return self.cur_screen.objects

    def _update_gui_once(self):
        s_names = [s.name for s in self.screens]
        try:
            self.gui.update_state("Ready.", s_names, self.cur_screen.name)
        except Exception:
            pass

    def _valid_sel(self) -> bool:
        return 0 <= self.sel_idx < len(self.cur_objs)

    def _clamp_sel(self):
        if len(self.cur_objs) == 0:
            self.sel_idx = -1
        elif self.sel_idx >= len(self.cur_objs):
            self.sel_idx = len(self.cur_objs) - 1
        elif self.sel_idx < 0:
            self.sel_idx = -1

    def run(self):
        curses.start_color()
        curses.use_default_colors()
        try:
            curses.curs_set(1)
        except Exception:
            pass
        for i, c in enumerate(Color, 1):
            c_val = getattr(curses, f"COLOR_{c.name}", curses.COLOR_WHITE)
            try:
                curses.init_pair(i, c_val, -1)
            except Exception:
                pass

        self.stdscr.nodelay(True)

        while True:
            self._clamp_sel()
            self._draw_interface()
            self._process_gui_queue()

            try: key = self.stdscr.getch()
            except Exception:
                key = -1

            if key == -1:
                curses.napms(30)
                continue

            if not self._handle_key(key):
                break

    def _process_gui_queue(self):
        try:
            while True:
                cmd, data = self.gui.queue.get_nowait()
                if cmd == "SWITCH_SCREEN":
                    for i, s in enumerate(self.screens):
                        if s.name == data:
                            self.act_idx = i
                            self.sel_idx = -1
                elif cmd == "ADD_SCREEN":
                    if data:
                        safe = re.sub(r'[^a-zA-Z0-9_]', '', data)
                        if not safe:
                            safe = "Screen"
                        self.screens.append(Screen(safe))
                        self.act_idx = len(self.screens) - 1
                        self.sel_idx = -1
                elif cmd == "RENAME_SCREEN":
                    if data:
                        old, new = data
                        safe = re.sub(r'[^a-zA-Z0-9_]', '', new)
                        for s in self.screens:
                            if s.name == old:
                                s.name = safe
                elif cmd == "SAVE_ASSET":
                    if self._valid_sel() and data:
                        obj = self.cur_objs[self.sel_idx]
                        lib = self.gui._load_lib()
                        d = obj.to_dict()
                        d['name'] = data
                        lib[data] = d
                        Path("library.json").write_text(json.dumps(lib, indent=2), encoding="utf-8")
                        self.gui.refresh_assets_list()
                        self.msg = f"Saved asset '{data}'"
                elif cmd == "INSERT_ASSET":
                    lib = self.gui._load_lib()
                    if data in lib:
                        new_obj = UIElement.from_dict(lib[data])
                        if new_obj:
                            if hasattr(new_obj, 'x') and hasattr(new_obj, 'y'):
                                new_obj.x = self.cx; new_obj.y = self.cy
                            if isinstance(new_obj, Line):
                                w = new_obj.x2 - new_obj.x1
                                h = new_obj.y2 - new_obj.y1
                                new_obj.x1 = self.cx; new_obj.y1 = self.cy
                                new_obj.x2 = self.cx + w; new_obj.y2 = self.cy + h
                            if isinstance(new_obj, Freehand):
                                new_obj.x = self.cx; new_obj.y = self.cy
                            base = new_obj.name or "obj"
                            cnt = 1
                            names = {o.name for o in self.cur_objs}
                            while new_obj.name in names or not new_obj.name:
                                new_obj.name = f"{base}_{cnt}"
                                cnt += 1
                            self.cur_objs.append(new_obj)
                            self.sel_idx = len(self.cur_objs) - 1
                            self.msg = f"Inserted {new_obj.name}"

                if cmd in ["ADD_SCREEN", "RENAME_SCREEN", "SWITCH_SCREEN"]:
                    try:
                        self.gui.update_state(self.msg, [s.name for s in self.screens], self.cur_screen.name)
                    except Exception:
                        pass

        except queue.Empty:
            pass

    def _handle_key(self, k: int) -> bool:
        # Escape cancels operations / selection
        if k == 27:
            self.mode = Mode.NAV
            self.sel_idx = -1
            self.msg = "Cancelled"
            return True

        # Movement
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

        # Navigation / commands
        if self.mode == Mode.NAV:
            if k == ord('q'): return False
            if k == ord('s'):
                try:
                    self.pm.save_project(self.screens)
                    self.pm.save_json_state(self.screens)
                    self.msg = "Saved ui_layout.cpp & project.json"
                except Exception as e:
                    self.msg = f"Save failed: {e}"
                return True
            if k == 9:  # Tab select next
                if self.cur_objs:
                    if self.sel_idx < 0:
                        self.sel_idx = 0
                    else:
                        self.sel_idx = (self.sel_idx + 1) % len(self.cur_objs)
            if k == ord('b'): self.mode = Mode.BOX_1; self.msg = "Box: Start Point -> Enter"
            if k == ord('l'): self.mode = Mode.LINE_1; self.msg = "Line: Start Point -> Enter"
            if k == ord('t'): self._add_text()
            if k == ord('d') and self._valid_sel():
                try:
                    self.cur_objs.pop(self.sel_idx)
                except Exception:
                    pass
                self.sel_idx = -1
            if k == ord('c') and self._valid_sel():
                o = self.cur_objs[self.sel_idx]
                clist = list(Color)
                try:
                    idx = clist.index(o.color)
                except Exception:
                    idx = 0
                o.color = clist[(idx + 1) % len(clist)]
            if k == ord('n') and self._valid_sel():
                self._rename_obj()

            # layer controls
            if k == ord('[') and self._valid_sel():
                if self.sel_idx > 0:
                    self.cur_objs[self.sel_idx - 1], self.cur_objs[self.sel_idx] = self.cur_objs[self.sel_idx], self.cur_objs[self.sel_idx - 1]
                    self.sel_idx -= 1
                    self.msg = "Moved backward (layer -1)"
            if k == ord(']') and self._valid_sel():
                if self.sel_idx < len(self.cur_objs) - 1:
                    self.cur_objs[self.sel_idx + 1], self.cur_objs[self.sel_idx] = self.cur_objs[self.sel_idx], self.cur_objs[self.sel_idx + 1]
                    self.sel_idx += 1
                    self.msg = "Moved forward (layer +1)"

            # EDIT properties / content (Box/Line/Text/Freehand)
            if k == ord('e') and self._valid_sel():
                target = self.cur_objs[self.sel_idx]
                # open properties editor (blocking)
                try:
                    props = self.gui.edit_props_blocking(target)
                except Exception:
                    props = None
                if props is not None:
                    # apply changes (validate)
                    try:
                        # name (sanitize)
                        new_name = props.get('name', target.name)
                        safe = re.sub(r'[^a-zA-Z0-9_]', '', new_name)
                        if safe:
                            target.name = safe
                        # color
                        cstr = props.get('color', target.color.name)
                        target.color = Color.from_str(cstr)
                        # box
                        if isinstance(target, Box):
                            target.x = int(props.get('x', target.x))
                            target.y = int(props.get('y', target.y))
                            target.w = max(1, int(props.get('w', target.w)))
                            target.h = max(1, int(props.get('h', target.h)))
                        # line
                        if isinstance(target, Line):
                            target.x1 = int(props.get('x1', target.x1))
                            target.y1 = int(props.get('y1', target.y1))
                            target.x2 = int(props.get('x2', target.x2))
                            target.y2 = int(props.get('y2', target.y2))
                        # text
                        if isinstance(target, Text):
                            target.content = str(props.get('content', target.content))
                        # freehand
                        if isinstance(target, Freehand):
                            lines = props.get('lines', target.lines)
                            if isinstance(lines, list):
                                target.lines = lines
                            else:
                                # if string, splitlines
                                target.lines = str(lines).splitlines()
                        self.msg = f"Updated {target.name}"
                    except Exception as e:
                        self.msg = f"Edit failed: {e}"

            # copy properties to other screens? (not implemented)
            return True

        # BOX/LINE creation sequences
        if self.mode == Mode.BOX_1 and k in (10, 13):
            self.temp = {'x': self.cx, 'y': self.cy}
            self.mode = Mode.BOX_2
            self.msg = "Box: End Point -> Enter"
        elif self.mode == Mode.BOX_2 and k in (10, 13):
            x = min(self.temp['x'], self.cx); y = min(self.temp['y'], self.cy)
            w = abs(self.temp['x'] - self.cx) + 1; h = abs(self.temp['y'] - self.cy) + 1
            name = f"box_{len(self.cur_objs)}"
            new_box = Box(name=name, color=Color.WHITE, x=x, y=y, w=w, h=h, layer=len(self.cur_objs))
            self.cur_objs.append(new_box)
            self.mode = Mode.NAV
            self.sel_idx = len(self.cur_objs) - 1
            self.msg = f"Created {name}"
        elif self.mode == Mode.LINE_1 and k in (10, 13):
            self.temp = {'x': self.cx, 'y': self.cy}
            self.mode = Mode.LINE_2
            self.msg = "Line: End Point -> Enter"
        elif self.mode == Mode.LINE_2 and k in (10, 13):
            name = f"line_{len(self.cur_objs)}"
            new_line = Line(name=name, color=Color.WHITE, x1=self.temp['x'], y1=self.temp['y'], x2=self.cx, y2=self.cy, layer=len(self.cur_objs))
            self.cur_objs.append(new_line)
            self.mode = Mode.NAV
            self.sel_idx = len(self.cur_objs) - 1
            self.msg = f"Created {name}"

        return True

    def _add_text(self):
        # Use GUI multiline editor to get content
        try:
            initial = ""
            text = self.gui.edit_text_blocking(initial, title="New Text (multiline)")
        except Exception:
            text = None
        if text is None:
            self.msg = "Text creation canceled"
            return
        name = f"txt_{len(self.cur_objs)}"
        new_txt = Text(name=name, color=Color.WHITE, x=self.cx, y=self.cy, content=str(text), layer=len(self.cur_objs))
        self.cur_objs.append(new_txt)
        self.sel_idx = len(self.cur_objs) - 1
        self.msg = f"Added text {name}"

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

    def _draw_interface(self):
        self.stdscr.clear()
        # Draw objects in list order (0 bottom)
        for i, o in enumerate(self.cur_objs):
            try:
                attr = curses.color_pair(list(Color).index(o.color) + 1)
                if i == self.sel_idx: attr |= (curses.A_BOLD | curses.A_REVERSE)
            except Exception:
                attr = curses.A_NORMAL

            try:
                if isinstance(o, Box):
                    # draw multi-char box; careful with bounds
                    self.stdscr.addch(o.y, o.x, '+', attr)
                    self.stdscr.addch(o.y + o.h - 1, o.x + o.w - 1, '+', attr)
                    for k in range(1, max(1, o.w - 1)):
                        self.stdscr.addch(o.y, o.x + k, '-', attr)
                        self.stdscr.addch(o.y + o.h - 1, o.x + k, '-', attr)
                    for k in range(1, max(1, o.h - 1)):
                        self.stdscr.addch(o.y + k, o.x, '|', attr)
                        self.stdscr.addch(o.y + k, o.x + o.w - 1, '|', attr)
                elif isinstance(o, Text):
                    # support multi-line content
                    lines = o.content.splitlines() or [""]
                    for r, line in enumerate(lines):
                        self.stdscr.addstr(o.y + r, o.x, line, attr)
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
                    for r, l in enumerate(o.lines):
                        self.stdscr.addstr(o.y + r, o.x, l, attr)
            except curses.error:
                # out-of-bounds ignore
                pass

        # status bar
        h, w = self.stdscr.getmaxyx()
        sel_name = ""
        if self._valid_sel():
            try:
                sel_name = f" | Sel: {self.cur_objs[self.sel_idx].name}"
            except Exception:
                sel_name = ""
        stat = f"[{self.cur_screen.name}] {self.msg}{sel_name} | Pos: {self.cx},{self.cy} (e:edit)"
        try:
            self.stdscr.addstr(h - 1, 0, stat[:w - 1], curses.A_REVERSE)
            self.stdscr.move(max(0, min(h - 2, self.cy)), max(0, min(w - 1, self.cx)))
        except Exception:
            pass
        self.stdscr.refresh()

        # update GUI help + lists
        help_txt = (
            f"MODE: {self.mode.name}\n\n"
            "KEYS:\n"
            "Arrows: Move Cursor/Object\n"
            "B: Draw Box\n"
            "T: Draw Text (multiline)\n"
            "L: Draw Line\n"
            "TAB: Select Object\n"
            "E: Edit Selected Properties/Content\n"
            "N: Rename Selected\n"
            "C: Change Color\n"
            "D: Delete Selected\n"
            "S: Save Project\n"
            "[ : Send Selected Backward\n"
            "] : Bring Selected Forward\n\n"
            "ASSETS:\n"
            "Save selected object from curses to library\n"
            "Use the 'Asset Library' tab to insert saved assets."
        )
        try:
            self.gui.update_state(help_txt, [s.name for s in self.screens], self.cur_screen.name)
        except Exception:
            pass

# ==============================================================================
# ENTRYPOINT
# ==============================================================================

if __name__ == "__main__":
    try:
        curses.wrapper(lambda s: Designer(s).run())
    except Exception as e:
        # robust terminal restore
        try:
            curses.nocbreak()
        except Exception:
            pass
        try:
            curses.echo()
        except Exception:
            pass
        try:
            curses.endwin()
        except Exception:
            pass
        print(f"Critical Error: {e}")
