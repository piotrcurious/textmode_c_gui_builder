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
# 1) SERIAL UI ENGINE (The C++ Driver)
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
# 2) DATA MODEL (Serializable)
# ==============================================================================

class Color(Enum):
    WHITE=37; RED=31; GREEN=32; YELLOW=33; BLUE=34; MAGENTA=35; CYAN=36
    
    @classmethod
    def from_str(cls, s):
        try:
            return cls[s.upper()]
        except (KeyError, AttributeError):
            return cls.WHITE

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
        col_str = d.get('color', 'WHITE')
        col = Color.from_str(col_str)
        layer = int(d.get('layer', 0))
        
        if t == "BOX":
            return Box(name=d.get('name','box'), color=col, x=d.get('x',0), y=d.get('y',0), w=d.get('w',0), h=d.get('h',0), layer=layer)
        if t == "TEXT":
            return Text(name=d.get('name','txt'), color=col, x=d.get('x',0), y=d.get('y',0), content=d.get('content',''), layer=layer)
        if t == "LINE":
            return Line(name=d.get('name','line'), color=col, x1=d.get('x1',0), y1=d.get('y1',0), x2=d.get('x2',0), y2=d.get('y2',0), layer=layer)
        if t == "FREEHAND":
            return Freehand(name=d.get('name','fh'), color=col, x=d.get('x',0), y=d.get('y',0), lines=d.get('lines',[]), layer=layer)
        return None

@dataclass
class Box(UIElement):
    x: int=0; y: int=0; w: int=0; h: int=0
    type: str = "BOX"
    def cpp_struct_init(self) -> str:
        return f'{{ {self.x}, {self.y}, {self.w}, {self.h}, UI_Color::{self.color.name} }}'

@dataclass
class Text(UIElement):
    x: int=0; y: int=0; content: str=""
    type: str = "TEXT"
    def cpp_struct_init(self) -> str:
        safe = self.content.replace('"', '\\"').replace('\n', ' ')
        return f'{{ {self.x}, {self.y}, "{safe}", UI_Color::{self.color.name} }}'

@dataclass
class Line(UIElement):
    x1: int=0; y1: int=0; x2: int=0; y2: int=0
    type: str = "LINE"
    def cpp_struct_init(self) -> str:
        return f'{{ {self.x1}, {self.y1}, {self.x2}, {self.y2}, UI_Color::{self.color.name} }}'

@dataclass
class Freehand(UIElement):
    x: int=0; y: int=0; lines: List[str]=field(default_factory=list)
    type: str = "FREEHAND"
    # Freehand is special; the struct points to a global array
    def cpp_struct_init(self) -> str:
        return f'{{ {self.x}, {self.y}, RES_{self.name}_ARR, {len(self.lines)}, UI_Color::{self.color.name} }}'

@dataclass
class Screen:
    name: str
    objects: List[UIElement] = field(default_factory=list)

# ==============================================================================
# 3) GUI & ASSET MANAGER
# ==============================================================================

class GuiManager:
    def __init__(self):
        self.queue = queue.Queue()
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
        self.root.geometry("400x500")
        self.root.attributes('-topmost', True)
        
        tabs = ttk.Notebook(self.root)
        tabs.pack(fill="both", expand=True)

        # -- TAB 1: HELP --
        f_help = tk.Frame(tabs)
        tabs.add(f_help, text="Help & Status")
        self.help_var = tk.StringVar(value="Initializing...")
        
        lbl_help = tk.Label(f_help, textvariable=self.help_var, justify="left", 
                            font=("Consolas", 10), wraplength=380, bg="#f0f0f0", relief="groove")
        lbl_help.pack(fill="both", expand=True, padx=5, pady=5)

        # -- TAB 2: SCREENS --
        f_scr = tk.Frame(tabs)
        tabs.add(f_scr, text="Screens")
        self.lst_scr = tk.Listbox(f_scr, height=6)
        self.lst_scr.pack(fill="x", padx=5, pady=5)
        
        tk.Button(f_scr, text="Switch To", command=lambda: self._emit("SWITCH_SCREEN")).pack(side="left", padx=5)
        tk.Button(f_scr, text="New Screen", command=lambda: self._emit("ADD_SCREEN")).pack(side="left")
        tk.Button(f_scr, text="Rename", command=lambda: self._emit("RENAME_SCREEN")).pack(side="left", padx=5)

        # -- TAB 3: ASSETS --
        f_assets = tk.Frame(tabs)
        tabs.add(f_assets, text="Asset Library")
        
        self.lst_assets = tk.Listbox(f_assets)
        self.lst_assets.pack(fill="both", expand=True, padx=5, pady=5)
        self._refresh_assets()

        btn_fr = tk.Frame(f_assets)
        btn_fr.pack(fill="x", pady=5)
        tk.Button(btn_fr, text="Insert Selected", bg="#ddffdd", command=lambda: self._emit("INSERT_ASSET")).pack(side="left", padx=5)
        tk.Button(btn_fr, text="Delete Asset", command=self._delete_asset).pack(side="right", padx=5)
        
        # Global Save Asset Button
        tk.Button(self.root, text="Save Selected Object to Library", bg="#ffeebb", 
                  command=lambda: self._emit("SAVE_ASSET")).pack(fill="x", padx=5, pady=5)

        self.ready.set()
        self.root.mainloop()

    def _emit(self, cmd):
        data = None
        if cmd == "SWITCH_SCREEN":
            if not self.lst_scr.curselection(): return
            data = self.lst_scr.get(self.lst_scr.curselection()[0])
        elif cmd == "ADD_SCREEN":
            data = simpledialog.askstring("New Screen", "Name:")
        elif cmd == "RENAME_SCREEN":
            if not self.lst_scr.curselection(): return
            old = self.lst_scr.get(self.lst_scr.curselection()[0])
            new = simpledialog.askstring("Rename", "New Name:")
            data = (old, new) if new else None
        elif cmd == "INSERT_ASSET":
            if not self.lst_assets.curselection(): return
            data = self.lst_assets.get(self.lst_assets.curselection()[0])
        elif cmd == "SAVE_ASSET":
            data = simpledialog.askstring("Save Asset", "Name for this asset:")
            
        if data or cmd in ["SAVE_ASSET"]:
             self.queue.put((cmd, data))

    def _delete_asset(self):
        sel = self.lst_assets.curselection()
        if not sel: return
        key = self.lst_assets.get(sel[0])
        lib = self._load_lib()
        if key in lib: del lib[key]
        Path("library.json").write_text(json.dumps(lib), encoding="utf-8")
        self._refresh_assets()

    def _load_lib(self):
        try: return json.loads(Path("library.json").read_text(encoding="utf-8"))
        except: return {}

    def _refresh_assets(self):
        self.lst_assets.delete(0, tk.END)
        for k in self._load_lib().keys(): self.lst_assets.insert(tk.END, k)

    def update_state(self, help_text, screens, active_scr):
        if not self.ready.is_set(): return
        # Using self.root.after is thread-safe for Tkinter
        try:
            self.root.after(0, lambda: self.help_var.set(help_text))
            def _u():
                self.lst_scr.delete(0, tk.END)
                idx = 0
                for i, s in enumerate(screens): 
                    self.lst_scr.insert(tk.END, s)
                    if s == active_scr: idx = i
                if screens:
                    self.lst_scr.selection_set(idx)
            self.root.after(0, _u)
        except: pass
    
    def refresh_assets_list(self):
        if self.root:
            self.root.after(0, self._refresh_assets)

# ==============================================================================
# 4) PROJECT MANAGER (Generator & Parser)
# ==============================================================================

class ProjectManager:
    H_FILE = "ui_layout.h"
    CPP_FILE = "ui_layout.cpp"
    LIB_FILE = "SerialUI.h"

    def ensure_lib(self):
        if not Path(self.LIB_FILE).exists(): Path(self.LIB_FILE).write_text(SERIAL_UI_HEADER, encoding="utf-8")

    def save_project(self, screens: List[Screen]):
        self.ensure_lib()
        
        # --- 1. HEADER GENERATION ---
        h_lines = [
            '#ifndef UI_LAYOUT_H', '#define UI_LAYOUT_H', 
            '#include "SerialUI.h"', '', 
            '// === LAYOUT ANCHORS ===',
            '// Access these in your code: Layout_Main::myBox.x',
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

        # --- 2. SOURCE GENERATION ---
        cpp_lines = ['#include "ui_layout.h"', '']
        
        # Global Resources (Freehand) - Deduplicated by Object Name
        processed_res = set()
        cpp_lines.append('// === RESOURCES ===')
        for s in screens:
            for obj in s.objects:
                if isinstance(obj, Freehand) and obj.name not in processed_res:
                    processed_res.add(obj.name)
                    # Definitions
                    for i, l in enumerate(obj.lines):
                        safe = l.replace('"', '\\"').replace('\\', '\\\\')
                        cpp_lines.append(f'const char RES_{obj.name}_L{i}[] PROGMEM = "{safe}";')
                    arr = ", ".join([f"RES_{obj.name}_L{i}" for i in range(len(obj.lines))])
                    cpp_lines.append(f'const char* const RES_{obj.name}_ARR[] PROGMEM = {{ {arr} }};\n')

        # Struct Initializations & Draw Functions
        cpp_lines.append('// === IMPLEMENTATION ===')
        for s in screens:
            # Init Static Members
            for obj in s.objects:
                cpp_type = f"UI_{obj.type.capitalize()}"
                init_val = obj.cpp_struct_init()
                cpp_lines.append(f'const {cpp_type} Layout_{s.name}::{obj.name} = {init_val};')
            
            # Draw Function
            cpp_lines.append(f'\nvoid drawScreen_{s.name}(SerialUI& ui) {{')
            for obj in s.objects:
                cpp_lines.append(f'    ui.draw(Layout_{s.name}::{obj.name});')
            cpp_lines.append('}\n')

        Path(self.CPP_FILE).write_text("\n".join(cpp_lines), encoding="utf-8")

    def load_project(self) -> List[Screen]:
        # Uses JSON as source of truth for Project State
        if Path("project.json").exists():
            try:
                data = json.loads(Path("project.json").read_text(encoding="utf-8"))
                screens = []
                for s_data in data:
                    s = Screen(s_data['name'])
                    s.objects = []
                    for o in s_data['objects']:
                        elem = UIElement.from_dict(o)
                        if elem: s.objects.append(elem)
                    screens.append(s)
                # Ensure at least one screen
                if not screens:
                    return [Screen("Main")]
                return screens
            except Exception:
                pass
        return [Screen("Main")]

    def save_json_state(self, screens):
        data = [{'name': s.name, 'objects': [o.to_dict() for o in s.objects]} for s in screens]
        Path("project.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

# ==============================================================================
# 5) DESIGNER LOGIC
# ==============================================================================

class Mode(Enum):
    NAV=auto(); BOX_1=auto(); BOX_2=auto(); LINE_1=auto(); LINE_2=auto()

class Designer:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.pm = ProjectManager()
        self.screens = self.pm.load_project()
        self.act_idx = 0
        self.mode = Mode.NAV
        self.cx, self.cy = 5, 5
        self.sel_idx = -1
        self.temp = {}
        self.gui = GuiManager()
        # wait a bit for GUI to be ready, but don't hang forever
        self.gui.ready.wait(2)
        self.msg = "Welcome."
        self._update_gui_once()
        
    @property
    def cur_screen(self): 
        if 0 <= self.act_idx < len(self.screens):
            return self.screens[self.act_idx]
        # fallback
        if self.screens:
            self.act_idx = 0
            return self.screens[0]
        # ensure at least one
        self.screens = [Screen("Main")]
        self.act_idx = 0
        return self.screens[0]

    @property
    def cur_objs(self): return self.cur_screen.objects

    def _update_gui_once(self):
        # Initial gui update
        s_names = [s.name for s in self.screens]
        self.gui.update_state("Ready.", s_names, self.cur_screen.name)

    def _valid_sel(self) -> bool:
        return 0 <= self.sel_idx < len(self.cur_objs)

    def _clamp_sel(self):
        if self.sel_idx >= len(self.cur_objs):
            self.sel_idx = len(self.cur_objs) - 1
        if self.sel_idx < 0:
            self.sel_idx = -1

    def run(self):
        curses.start_color()
        curses.use_default_colors()
        try:
            curses.curs_set(1)
        except:
            pass
        for i, c in enumerate(Color, 1): 
            # Safe access to curses colors
            c_val = getattr(curses, f"COLOR_{c.name}", curses.COLOR_WHITE)
            try:
                curses.init_pair(i, c_val, -1)
            except:
                # Some terminals might not support many color pairs
                pass
            
        self.stdscr.nodelay(True)
        
        while True:
            self._clamp_sel()
            self._draw_interface()
            self._process_gui_queue()
            
            try: key = self.stdscr.getch()
            except: key = -1
            
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
                            self.act_idx = i; self.sel_idx = -1
                            
                elif cmd == "ADD_SCREEN":
                    if data: 
                        # sanitize
                        safe = re.sub(r'[^a-zA-Z0-9_]', '', data)
                        self.screens.append(Screen(safe))
                        self.act_idx = len(self.screens)-1
                        self.sel_idx = -1
                        
                elif cmd == "RENAME_SCREEN":
                    if data:
                        old, new = data
                        safe = re.sub(r'[^a-zA-Z0-9_]', '', new)
                        for s in self.screens: 
                            if s.name == old: s.name = safe
                            
                elif cmd == "SAVE_ASSET":
                    if self._valid_sel() and data:
                        obj = self.cur_objs[self.sel_idx]
                        lib = self.gui._load_lib()
                        d = obj.to_dict()
                        # Override name with user provided name for the Library entry
                        d['name'] = data 
                        lib[data] = d
                        Path("library.json").write_text(json.dumps(lib), encoding="utf-8")
                        self.gui.refresh_assets_list()
                        self.msg = f"Saved asset '{data}'"
                        
                elif cmd == "INSERT_ASSET":
                    lib = self.gui._load_lib()
                    if data in lib:
                        new_obj = UIElement.from_dict(lib[data])
                        if new_obj:
                            # Reposition at cursor sensibly depending on type
                            # For Box/Text/Freehand: set x,y
                            if hasattr(new_obj, 'x') and hasattr(new_obj, 'y'):
                                new_obj.x = self.cx; new_obj.y = self.cy
                            # For Line: maintain width/height and move start to cursor
                            if isinstance(new_obj, Line):
                                w = new_obj.x2 - new_obj.x1
                                h = new_obj.y2 - new_obj.y1
                                new_obj.x1 = self.cx; new_obj.y1 = self.cy
                                new_obj.x2 = self.cx + w; new_obj.y2 = self.cy + h
                            # For Freehand: place top-left at cursor
                            if isinstance(new_obj, Freehand):
                                new_obj.x = self.cx; new_obj.y = self.cy
                            
                            # Unique Name Generation
                            base = new_obj.name
                            cnt = 1
                            names = {o.name for o in self.cur_objs}
                            while new_obj.name in names:
                                new_obj.name = f"{base}_{cnt}"
                                cnt += 1
                                
                            self.cur_objs.append(new_obj)
                            self.sel_idx = len(self.cur_objs)-1
                            self.msg = f"Inserted {new_obj.name}"
                
                # Update GUI list if needed
                if cmd in ["ADD_SCREEN", "RENAME_SCREEN", "SWITCH_SCREEN"]:
                    self.gui.update_state(self.msg, [s.name for s in self.screens], self.cur_screen.name)
                    
        except queue.Empty: pass

    def _handle_key(self, k):
        if k == 27: 
            self.mode = Mode.NAV; self.sel_idx = -1; 
            self.msg = "Cancelled"; return True
        
        # Movement
        dx, dy = 0, 0
        if k == curses.KEY_UP: dy = -1
        elif k == curses.KEY_DOWN: dy = 1
        elif k == curses.KEY_LEFT: dx = -1
        elif k == curses.KEY_RIGHT: dx = 1
        
        if (dx or dy):
            if self.mode == Mode.NAV and self._valid_sel():
                o = self.cur_objs[self.sel_idx]
                # Boundary checks omitted for brevity, but could be added
                if hasattr(o,'x'): 
                    o.x += dx; o.y += dy
                if hasattr(o,'x1'): 
                    o.x1 += dx; o.y1 += dy; o.x2 += dx; o.y2 += dy
            else:
                self.cx += dx; self.cy += dy
                # Clamp cursor
                h, w = self.stdscr.getmaxyx()
                self.cx = max(0, min(w-1, self.cx))
                self.cy = max(0, min(h-2, self.cy))  # leave room for status bar
            return True

        if self.mode == Mode.NAV:
            if k == ord('q'): return False
            if k == ord('s'): 
                self.pm.save_project(self.screens)
                self.pm.save_json_state(self.screens)
                self.msg = "Saved ui_layout.cpp & project.json"
                return True
            if k == 9: # Tab
                if self.cur_objs:
                    if self.sel_idx < 0:
                        self.sel_idx = 0
                    else:
                        self.sel_idx = (self.sel_idx + 1) % len(self.cur_objs)
            if k == ord('b'): self.mode = Mode.BOX_1; self.msg = "Box: Start Point -> Enter"
            if k == ord('l'): self.mode = Mode.LINE_1; self.msg = "Line: Start Point -> Enter"
            if k == ord('t'): self._add_text()
            if k == ord('d') and self._valid_sel(): 
                self.cur_objs.pop(self.sel_idx); self.sel_idx = -1
            if k == ord('c') and self._valid_sel(): 
                o = self.cur_objs[self.sel_idx]
                clist = list(Color)
                try:
                    idx = clist.index(o.color)
                except ValueError:
                    idx = 0
                o.color = clist[(idx+1)%len(clist)]
            if k == ord('n') and self._valid_sel():
                self._rename_obj()

            # Layer controls: '[' send backward, ']' bring forward
            if k == ord('[') and self._valid_sel():
                if self.sel_idx > 0:
                    # swap with previous item (send backward)
                    self.cur_objs[self.sel_idx-1], self.cur_objs[self.sel_idx] = self.cur_objs[self.sel_idx], self.cur_objs[self.sel_idx-1]
                    self.sel_idx -= 1
                    self.msg = "Moved backward (layer -1)"
            if k == ord(']') and self._valid_sel():
                if self.sel_idx < len(self.cur_objs)-1:
                    # swap with next item (bring forward)
                    self.cur_objs[self.sel_idx+1], self.cur_objs[self.sel_idx] = self.cur_objs[self.sel_idx], self.cur_objs[self.sel_idx+1]
                    self.sel_idx += 1
                    self.msg = "Moved forward (layer +1)"

        elif self.mode == Mode.BOX_1 and k in (10,13):
            self.temp = {'x': self.cx, 'y': self.cy}; self.mode = Mode.BOX_2; self.msg = "Box: End Point -> Enter"
        elif self.mode == Mode.BOX_2 and k in (10,13):
            x, y = min(self.temp['x'], self.cx), min(self.temp['y'], self.cy)
            w, h = abs(self.temp['x']-self.cx)+1, abs(self.temp['y']-self.cy)+1
            name = f"box_{len(self.cur_objs)}"
            self.cur_objs.append(Box(name, Color.WHITE, x, y, w, h, layer=len(self.cur_objs)))
            self.mode = Mode.NAV; self.msg = f"Created {name}"
            self.sel_idx = len(self.cur_objs)-1

        elif self.mode == Mode.LINE_1 and k in (10,13):
            self.temp = {'x': self.cx, 'y': self.cy}; self.mode = Mode.LINE_2; self.msg = "Line: End Point -> Enter"
        elif self.mode == Mode.LINE_2 and k in (10,13):
            name = f"line_{len(self.cur_objs)}"
            self.cur_objs.append(Line(name, Color.WHITE, self.temp['x'], self.temp['y'], self.cx, self.cy, layer=len(self.cur_objs)))
            self.mode = Mode.NAV; self.msg = f"Created {name}"
            self.sel_idx = len(self.cur_objs)-1

        return True

    def _add_text(self):
        curses.echo()
        try:
            self.stdscr.addstr(0,0,"Text: ")
            # getstr returns bytes
            t = self.stdscr.getstr().decode('utf-8')
        except Exception:
            t = ""
        finally:
            curses.noecho()
        if t:
            name = f"txt_{len(self.cur_objs)}"
            self.cur_objs.append(Text(name, Color.WHITE, self.cx, self.cy, t, layer=len(self.cur_objs)))
            self.sel_idx = len(self.cur_objs)-1

    def _rename_obj(self):
        curses.echo()
        try:
            self.stdscr.addstr(0,0,"New Name: ")
            t = self.stdscr.getstr().decode('utf-8')
        except Exception:
            t = ""
        finally:
            curses.noecho()
        if t and self._valid_sel():
            # Enforce C++ Identifier rules
            safe = re.sub(r'[^a-zA-Z0-9_]', '', t)
            if safe:
                self.cur_objs[self.sel_idx].name = safe
                self.msg = f"Renamed to {safe}"

    def _draw_interface(self):
        self.stdscr.clear()
        
        # Sort objects by their physical stacking order (list order is draw order).
        # We will draw in list order, which we've defined as bottom->top
        # (index 0 is bottom). No need to change objects; we respect their order in self.cur_objs.

        # Draw Objects
        for i, o in enumerate(self.cur_objs):
            # Safe color pair lookup
            try:
                attr = curses.color_pair(list(Color).index(o.color)+1)
                if i == self.sel_idx: attr |= (curses.A_BOLD | curses.A_REVERSE)
            except: attr = curses.A_NORMAL

            try:
                if isinstance(o, Box):
                    # Corners
                    self.stdscr.addch(o.y, o.x, '+', attr)
                    self.stdscr.addch(o.y+o.h-1, o.x+o.w-1, '+', attr)
                    # Horiz
                    for k in range(1, max(1, o.w-1)): 
                        self.stdscr.addch(o.y, o.x+k, '-', attr)
                        self.stdscr.addch(o.y+o.h-1, o.x+k, '-', attr)
                    # Vert
                    for k in range(1, max(1, o.h-1)): 
                        self.stdscr.addch(o.y+k, o.x, '|', attr)
                        self.stdscr.addch(o.y+k, o.x+o.w-1, '|', attr)
                        
                elif isinstance(o, Text): 
                    self.stdscr.addstr(o.y, o.x, o.content, attr)
                    
                elif isinstance(o, Line): 
                    # Naive Line Draw for Preview
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
                        self.stdscr.addstr(o.y+r, o.x, l, attr)
            except curses.error: 
                pass # Clipping

        # Draw Status Bar & Cursor
        h, w = self.stdscr.getmaxyx()
        # ensure sel_name is safe even if sel_idx out-of-range
        sel_name = ""
        if self._valid_sel():
            try:
                sel_name = f" | Sel: {self.cur_objs[self.sel_idx].name}"
            except Exception:
                sel_name = ""
        stat = f"[{self.cur_screen.name}] {self.msg}{sel_name} | Pos: {self.cx},{self.cy}"
        
        try:
            self.stdscr.addstr(h-1, 0, stat[:w-1], curses.A_REVERSE)
            # Move physical cursor (keep inside screen bounds)
            self.stdscr.move(max(0, min(h-2, self.cy)), max(0, min(w-1, self.cx)))
        except: pass
        
        self.stdscr.refresh()

        # Update Tkinter Text
        help_txt = (
            f"MODE: {self.mode.name}\n\n"
            "KEYS:\n"
            "Arrows: Move Cursor/Object\n"
            "B: Draw Box\n"
            "T: Draw Text\n"
            "L: Draw Line\n"
            "TAB: Select Object\n"
            "N: Rename Selected\n"
            "C: Change Color\n"
            "D: Delete Selected\n"
            "S: Save Project\n"
            "[ : Send Selected Backward\n"
            "] : Bring Selected Forward\n\n"
            "ASSETS:\n"
            "Select an object and click\n"
            "'Save Selected Object to Library'\n"
            "in the window to reuse it."
        )
        self.gui.update_state(help_txt, [s.name for s in self.screens], self.cur_screen.name)

if __name__ == "__main__":
    try:
        curses.wrapper(lambda s: Designer(s).run())
    except Exception as e:
        # Try to cleanly restore terminal. Some curses functions may raise if already broken.
        try:
            curses.nocbreak()
        except:
            pass
        try:
            curses.echo()
        except:
            pass
        try:
            curses.endwin()
        except:
            pass
        print(f"Critical Error: {e}")
