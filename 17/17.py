from __future__ import annotations
import curses
import re
import threading
import queue
import json
import tkinter as tk
from tkinter import scrolledtext, ttk, messagebox
from enum import Enum, auto
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict

# ==============================================================================
# 1) STATIC C++ LIBRARY (Updated for PROGMEM)
# ==============================================================================

SERIAL_UI_HEADER = r"""
#ifndef SERIAL_UI_H
#define SERIAL_UI_H
#include <Arduino.h>
#include <avr/pgmspace.h>

enum class UI_Color { WHITE=37, RED=31, GREEN=32, YELLOW=33, BLUE=34, MAGENTA=35, CYAN=36 };

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

    void drawText(int x, int y, const char* content, UI_Color color) {
        setColor(color); moveCursor(x, y); Serial.print(content); resetAttr();
    }

    void drawBox(int x, int y, int w, int h, UI_Color color) {
        setColor(color);
        for (int i = 0; i < w; i++) {
            moveCursor(x + i, y); Serial.print("-");
            moveCursor(x + i, y + h - 1); Serial.print("-");
        }
        for (int i = 0; i < h; i++) {
            moveCursor(x, y + i); Serial.print("|");
            moveCursor(x + w - 1, y + i); Serial.print("|");
        }
        moveCursor(x, y); Serial.print("+");
        moveCursor(x + w - 1, y); Serial.print("+");
        moveCursor(x, y + h - 1); Serial.print("+");
        moveCursor(x + w - 1, y + h - 1); Serial.print("+");
        resetAttr();
    }

    void drawLine(int x1, int y1, int x2, int y2, UI_Color color) {
        setColor(color);
        int dx = abs(x2 - x1), sx = x1 < x2 ? 1 : -1;
        int dy = -abs(y2 - y1), sy = y1 < y2 ? 1 : -1;
        int err = dx + dy, e2;
        int x = x1, y = y1;
        while (true) {
            moveCursor(x, y); Serial.print("#");
            if (x == x2 && y == y2) break;
            e2 = 2 * err;
            if (e2 >= dy) { err += dy; x += sx; }
            if (e2 <= dx) { err += dx; y += sy; }
        }
        resetAttr();
    }

    // UPDATED: Reads character by character from Flash Memory (PROGMEM)
    // Expects a PROGMEM array of PROGMEM string pointers
    void drawFreehand(int x, int y, const char* const* lines, int count, UI_Color color) {
        setColor(color);
        for(int i=0; i<count; i++) {
            moveCursor(x, y + i);
            // Read the pointer to the line string from flash
            const char* strPtr = (const char*)pgm_read_ptr(&(lines[i]));
            // Read characters from that string until null terminator
            while(uint8_t c = pgm_read_byte(strPtr++)) {
                Serial.write(c);
            }
        }
        resetAttr();
    }
};
#endif
"""

# ==============================================================================
# 2) DATA MODEL
# ==============================================================================

class Color(Enum):
    WHITE = 37; RED = 31; GREEN = 32; YELLOW = 33; BLUE = 34; MAGENTA = 35; CYAN = 36

    @classmethod
    def from_string(cls, name: str) -> Color:
        try: return cls[name.upper()]
        except: return cls.WHITE

@dataclass
class UIElement:
    name: str
    color: Color = Color.WHITE

@dataclass
class Box(UIElement):
    x: int = 0; y: int = 0; w: int = 0; h: int = 0
    def to_cpp(self) -> str:
        return f'    ui.drawBox({self.x}, {self.y}, {self.w}, {self.h}, UI_Color::{self.color.name}); // {self.name}'

@dataclass
class Text(UIElement):
    x: int = 0; y: int = 0; content: str = ""
    def to_cpp(self) -> str:
        clean = self.content.replace('"', '\\"')
        return f'    ui.drawText({self.x}, {self.y}, "{clean}", UI_Color::{self.color.name}); // {self.name}'

@dataclass
class Line(UIElement):
    x1: int = 0; y1: int = 0; x2: int = 0; y2: int = 0
    def to_cpp(self) -> str:
        return f'    ui.drawLine({self.x1}, {self.y1}, {self.x2}, {self.y2}, UI_Color::{self.color.name}); // {self.name}'

@dataclass
class Freehand(UIElement):
    x: int = 0; y: int = 0; lines: List[str] = None
    
    def to_cpp_definitions(self) -> str:
        """Generates the PROGMEM variable definitions."""
        out = []
        # 1. Define each line as a PROGMEM string variable
        line_vars = []
        for i, line in enumerate(self.lines):
            safe_content = line.replace('"', '\\"').replace('\\', '\\\\')
            var_name = f"{self.name}_L{i}"
            line_vars.append(var_name)
            out.append(f'const char {var_name}[] PROGMEM = "{safe_content}";')
        
        # 2. Define the array of pointers
        pointer_list = ", ".join(line_vars)
        out.append(f'const char* const {self.name}_arr[] PROGMEM = {{ {pointer_list} }};')
        return "\n".join(out)

    def to_cpp_call(self) -> str:
        """Generates the draw call inside the function."""
        return f'    ui.drawFreehand({self.x}, {self.y}, {self.name}_arr, {len(self.lines)}, UI_Color::{self.color.name}); // {self.name}'

# ==============================================================================
# 3) ASSET LIBRARY (JSON)
# ==============================================================================

class AssetLibrary:
    FILE = "library.json"

    @staticmethod
    def load() -> Dict[str, List[str]]:
        if not Path(AssetLibrary.FILE).exists(): return {}
        try:
            return json.loads(Path(AssetLibrary.FILE).read_text(encoding="utf-8"))
        except: return {}

    @staticmethod
    def save(name: str, lines: List[str]):
        data = AssetLibrary.load()
        data[name] = lines
        Path(AssetLibrary.FILE).write_text(json.dumps(data, indent=2), encoding="utf-8")

# ==============================================================================
# 4) GUI MANAGER (Tkinter in Thread)
# ==============================================================================

class GuiManager:
    def __init__(self):
        self.root = None
        self.queue = queue.Queue()
        self.thread = threading.Thread(target=self._run_gui, daemon=True)
        self.thread.start()
        self.ready_event = threading.Event()
        self.help_var = None

    def _run_gui(self):
        self.root = tk.Tk()
        self.root.title("Design Helpers")
        self.root.geometry("350x250+50+50")
        self.root.attributes('-topmost', True)
        
        # Tabs
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True)
        
        # Tab 1: Info
        f_info = tk.Frame(notebook)
        notebook.add(f_info, text="Status")
        self.help_var = tk.StringVar(value="Initializing...")
        tk.Label(f_info, textvariable=self.help_var, wraplength=330, justify="left", padx=10, pady=10).pack()
        tk.Button(f_info, text="Open Asset Manager", command=self._open_asset_manager).pack(pady=10)

        self.ready_event.set()
        self.root.mainloop()

    def update_help(self, text):
        if self.root: self.root.after(0, lambda: self.help_var.set(text))

    def _open_asset_manager(self):
        win = tk.Toplevel(self.root)
        win.title("Asset Library & Freehand")
        win.geometry("500x400")

        # Layout: Left (List), Right (Editor)
        paned = tk.PanedWindow(win, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True)

        left = tk.Frame(paned); paned.add(left, width=150)
        right = tk.Frame(paned); paned.add(right)

        # Left: Asset List
        tk.Label(left, text="Saved Assets").pack()
        lst_assets = tk.Listbox(left)
        lst_assets.pack(fill="both", expand=True)
        
        assets = AssetLibrary.load()
        for k in assets: lst_assets.insert(tk.END, k)

        # Right: Editor
        tk.Label(right, text="Editor (Draw/Paste)").pack()
        txt = scrolledtext.ScrolledText(right, height=10, font=("Courier New", 10))
        txt.pack(fill="both", expand=True)
        
        entry_name = tk.Entry(right)
        entry_name.pack(fill="x", pady=2)
        entry_name.insert(0, "NewAssetName")

        # Logic
        def on_select(evt):
            sel = lst_assets.curselection()
            if not sel: return
            key = lst_assets.get(sel[0])
            content = assets.get(key, [])
            txt.delete("1.0", tk.END)
            txt.insert("1.0", "\n".join(content))
            entry_name.delete(0, tk.END); entry_name.insert(0, key)

        lst_assets.bind("<<ListboxSelect>>", on_select)

        def save_asset():
            name = entry_name.get().strip()
            if not name: return
            raw = txt.get("1.0", tk.END).split("\n")
            # trim
            while raw and not raw[-1].strip(): raw.pop()
            AssetLibrary.save(name, raw)
            # refresh list
            lst_assets.delete(0, tk.END)
            new_assets = AssetLibrary.load()
            for k in new_assets: lst_assets.insert(tk.END, k)
            messagebox.showinfo("Saved", f"Asset '{name}' saved to Library.")

        def send_to_curses():
            raw = txt.get("1.0", tk.END).split("\n")
            while raw and not raw[-1].strip(): raw.pop()
            if raw:
                self.queue.put(("FREEHAND", raw))
                win.destroy()

        btn_frame = tk.Frame(right)
        btn_frame.pack(fill="x", pady=5)
        tk.Button(btn_frame, text="Save to Library", command=save_asset).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Insert into Design", bg="#ddffdd", command=send_to_curses).pack(side="right", padx=5)

# ==============================================================================
# 5) PROJECT & SMART PARSING
# ==============================================================================

class ProjectManager:
    HEADER_FILE = "ui_layout.h"
    SOURCE_FILE = "ui_layout.cpp"
    LIB_FILE = "SerialUI.h"

    def ensure_lib(self):
        if not Path(self.LIB_FILE).exists():
            Path(self.LIB_FILE).write_text(SERIAL_UI_HEADER, encoding="utf-8")

    def save(self, objects: List[UIElement]):
        self.ensure_lib()
        header = "#ifndef UI_LAYOUT_H\n#define UI_LAYOUT_H\n#include \"SerialUI.h\"\n\nvoid drawScreen_Main(SerialUI& ui);\n#endif\n"
        Path(self.HEADER_FILE).write_text(header)
        
        # Separate definitions (outside function) and calls (inside function)
        definitions = []
        calls = []
        
        for obj in objects:
            if isinstance(obj, Freehand):
                definitions.append(obj.to_cpp_definitions())
                calls.append(obj.to_cpp_call())
            else:
                calls.append(obj.to_cpp()) # Standard objects have no global definitions

        src = ['#include "ui_layout.h"', '', '// --- PROGMEM Definitions ---']
        src.extend(definitions)
        src.append('\n// --- Draw Function ---')
        src.append('void drawScreen_Main(SerialUI& ui) {')
        src.extend(calls)
        src.append('}')
        
        Path(self.SOURCE_FILE).write_text("\n".join(src))

    def load(self) -> List[UIElement]:
        if not Path(self.SOURCE_FILE).exists(): return []
        content = Path(self.SOURCE_FILE).read_text()
        objs = []

        # 1. Parse PROGMEM String definitions: const char name[] PROGMEM = "content";
        # Regex to find: const char (varname)[] PROGMEM = "(content)";
        re_str_def = re.compile(r'const char\s+(\w+)\[\]\s+PROGMEM\s+=\s*"(.*)";')
        string_map = {} # var_name -> content
        for m in re_str_def.finditer(content):
            val = m.group(2).replace('\\"', '"').replace('\\\\', '\\')
            string_map[m.group(1)] = val

        # 2. Parse PROGMEM Arrays: const char* const (arrname)[] PROGMEM = { var1, var2 };
        re_arr_def = re.compile(r'const char\*\s+const\s+(\w+)\[\]\s+PROGMEM\s+=\s*\{(.*?)\};')
        array_map = {} # arr_name -> list[str lines]
        for m in re_arr_def.finditer(content):
            arr_name = m.group(1)
            vars_list = [v.strip() for v in m.group(2).split(',') if v.strip()]
            # Resolve vars to strings
            resolved_lines = [string_map.get(v, "") for v in vars_list]
            array_map[arr_name] = resolved_lines

        # 3. Parse Objects in function calls
        re_box = re.compile(r'ui\.drawBox\(\s*(-?\d+),\s*(-?\d+),\s*(-?\d+),\s*(-?\d+),\s*UI_Color::(\w+)\s*\);\s*//\s*(.*)')
        re_text = re.compile(r'ui\.drawText\(\s*(-?\d+),\s*(-?\d+),\s*"(.*)",\s*UI_Color::(\w+)\s*\);\s*//\s*(.*)')
        re_line = re.compile(r'ui\.drawLine\(\s*(-?\d+),\s*(-?\d+),\s*(-?\d+),\s*(-?\d+),\s*UI_Color::(\w+)\s*\);\s*//\s*(.*)')
        re_fh = re.compile(r'ui\.drawFreehand\(\s*(-?\d+),\s*(-?\d+),\s*(\w+),\s*(\d+),\s*UI_Color::(\w+)\s*\);\s*//\s*(.*)')

        for line in content.splitlines():
            line = line.strip()
            if m := re_box.search(line):
                objs.append(Box(m.group(6), Color.from_string(m.group(5)), *map(int, m.groups()[:4])))
            elif m := re_text.search(line):
                objs.append(Text(m.group(5), Color.from_string(m.group(4)), int(m.group(1)), int(m.group(2)), m.group(3)))
            elif m := re_line.search(line):
                objs.append(Line(m.group(6), Color.from_string(m.group(5)), *map(int, m.groups()[:4])))
            elif m := re_fh.search(line):
                x, y, arr_name, cnt, col, name = m.groups()
                if arr_name in array_map:
                    objs.append(Freehand(name, Color.from_string(col), int(x), int(y), array_map[arr_name]))
        
        return objs

# ==============================================================================
# 6) CURSES DESIGNER (Added Layering)
# ==============================================================================

class DesignMode(Enum):
    NAVIGATE = auto(); DRAW_BOX_START = auto(); DRAW_BOX_END = auto()
    DRAW_LINE_START = auto(); DRAW_LINE_END = auto(); WAIT_GUI = auto()

HELP_TEXT = {
    DesignMode.NAVIGATE: "Move: ARROWS | Layers: +/- | Box: b | Line: l | Text: t | Freehand: f | Save: s | Del: d | Tab: Select",
    DesignMode.DRAW_BOX_START: "BOX: Top-Left -> ENTER", DesignMode.DRAW_BOX_END: "BOX: Bottom-Right -> ENTER",
    DesignMode.DRAW_LINE_START: "LINE: Start -> ENTER", DesignMode.DRAW_LINE_END: "LINE: End -> ENTER",
    DesignMode.WAIT_GUI: "Using External Window...",
}

class Designer:
    def __init__(self, stdscr):
        self.stdscr = stdscr; self.mode = DesignMode.NAVIGATE
        self.cursor_x, self.cursor_y = 5, 5
        self.pm = ProjectManager(); self.objects = self.pm.load()
        self.selected_idx = -1; self.temp = {}; self.colors = list(Color)
        self.gui = GuiManager(); self.gui.ready_event.wait(2); self._update_status()

    def _update_status(self): self.gui.update_help(HELP_TEXT.get(self.mode, ""))

    def run(self):
        curses.start_color(); curses.use_default_colors(); curses.curs_set(1)
        for i, c in enumerate(self.colors, 1): curses.init_pair(i, getattr(curses, f"COLOR_{c.name}"), -1)
        self.stdscr.nodelay(True)
        while True:
            self._draw(); self._check_gui()
            try: key = self.stdscr.getch()
            except: key = -1
            if key == -1: curses.napms(30); continue
            if not self._handle_key(key): break

    def _check_gui(self):
        try:
            while True:
                act, data = self.gui.queue.get_nowait()
                if act == "FREEHAND":
                    self.objects.append(Freehand(f"art_{len(self.objects)}", Color.WHITE, self.cursor_x, self.cursor_y, data))
                    self.mode = DesignMode.NAVIGATE; self._update_status()
        except queue.Empty: pass

    def _handle_key(self, key):
        if key == 27: 
            self.mode = DesignMode.NAVIGATE; self.selected_idx = -1; self._update_status(); return True
        
        # Navigation
        if key in (curses.KEY_UP, curses.KEY_DOWN, curses.KEY_LEFT, curses.KEY_RIGHT):
            self._move(key); return True

        if self.mode == DesignMode.NAVIGATE:
            if key == ord('q'): return False
            if key == ord('s'): self.pm.save(self.objects); self.gui.update_help("Saved ui_layout.cpp!"); return True
            if key == ord('b'): self.mode = DesignMode.DRAW_BOX_START
            if key == ord('l'): self.mode = DesignMode.DRAW_LINE_START
            if key == ord('t'): self._text_prompt()
            if key == ord('f'): self.mode = DesignMode.WAIT_GUI; self.gui._open_asset_manager()
            if key == 9: self.selected_idx = (self.selected_idx + 1) % len(self.objects) if self.objects else -1
            if key == ord('d') and self.selected_idx >= 0: self.objects.pop(self.selected_idx); self.selected_idx = -1
            if key == ord('c') and self.selected_idx >= 0:
                o = self.objects[self.selected_idx]
                o.color = self.colors[(self.colors.index(o.color)+1)%len(self.colors)]
            
            # Layering (+/-)
            if key == ord('+') and self.selected_idx >= 0 and self.selected_idx < len(self.objects) - 1:
                # Move UP (draw later)
                i = self.selected_idx
                self.objects[i], self.objects[i+1] = self.objects[i+1], self.objects[i]
                self.selected_idx += 1
            if key == ord('-') and self.selected_idx > 0:
                # Move DOWN (draw earlier)
                i = self.selected_idx
                self.objects[i], self.objects[i-1] = self.objects[i-1], self.objects[i]
                self.selected_idx -= 1
            
            self._update_status()
            
        elif self.mode == DesignMode.DRAW_BOX_START and key in (10,13):
            self.temp = {'x':self.cursor_x, 'y':self.cursor_y}; self.mode = DesignMode.DRAW_BOX_END; self._update_status()
        elif self.mode == DesignMode.DRAW_BOX_END and key in (10,13):
            x,y=min(self.temp['x'],self.cursor_x),min(self.temp['y'],self.cursor_y)
            w,h=abs(self.temp['x']-self.cursor_x)+1,abs(self.temp['y']-self.cursor_y)+1
            self.objects.append(Box(f"box_{len(self.objects)}", Color.WHITE, x,y,w,h))
            self.mode = DesignMode.NAVIGATE; self._update_status()
        elif self.mode == DesignMode.DRAW_LINE_START and key in (10,13):
            self.temp = {'x':self.cursor_x, 'y':self.cursor_y}; self.mode = DesignMode.DRAW_LINE_END; self._update_status()
        elif self.mode == DesignMode.DRAW_LINE_END and key in (10,13):
            self.objects.append(Line(f"line_{len(self.objects)}", Color.WHITE, self.temp['x'], self.temp['y'], self.cursor_x, self.cursor_y))
            self.mode = DesignMode.NAVIGATE; self._update_status()
        return True

    def _text_prompt(self):
        curses.echo(); self.stdscr.addstr(0,0,"TEXT: "); t=self.stdscr.getstr().decode('utf-8'); curses.noecho()
        if t: self.objects.append(Text(f"txt_{len(self.objects)}", Color.WHITE, self.cursor_x, self.cursor_y, t))

    def _move(self, key):
        dx,dy = {curses.KEY_UP:(0,-1), curses.KEY_DOWN:(0,1), curses.KEY_LEFT:(-1,0), curses.KEY_RIGHT:(1,0)}[key]
        if self.mode==DesignMode.NAVIGATE and self.selected_idx >= 0:
            o = self.objects[self.selected_idx]
            if hasattr(o,'x'): o.x+=dx; o.y+=dy
            if hasattr(o,'x1'): o.x1+=dx; o.y1+=dy; o.x2+=dx; o.y2+=dy
        else: self.cursor_x+=dx; self.cursor_y+=dy
        h,w = self.stdscr.getmaxyx(); self.cursor_x=max(0,min(w-1,self.cursor_x)); self.cursor_y=max(0,min(h-1,self.cursor_y))

    def _draw(self):
        self.stdscr.clear()
        for i, obj in enumerate(self.objects):
            attr = curses.color_pair(self.colors.index(obj.color)+1)
            if i == self.selected_idx: attr |= (curses.A_BOLD | curses.A_REVERSE)
            try:
                if isinstance(obj, Box):
                    self.stdscr.addch(obj.y, obj.x, '+', attr); self.stdscr.addch(obj.y+obj.h-1, obj.x+obj.w-1, '+', attr)
                    for k in range(1, obj.w-1): self.stdscr.addch(obj.y, obj.x+k, '-', attr); self.stdscr.addch(obj.y+obj.h-1, obj.x+k, '-', attr)
                    for k in range(1, obj.h-1): self.stdscr.addch(obj.y+k, obj.x, '|', attr); self.stdscr.addch(obj.y+k, obj.x+obj.w-1, '|', attr)
                elif isinstance(obj, Text): self.stdscr.addstr(obj.y, obj.x, obj.content, attr)
                elif isinstance(obj, Line): 
                     # Simple Bresenham approximation for visual preview
                    x1, y1, x2, y2 = obj.x1, obj.y1, obj.x2, obj.y2
                    dx, sx = abs(x2 - x1), 1 if x1 < x2 else -1
                    dy, sy = -abs(y2 - y1), 1 if y1 < y2 else -1
                    err = dx + dy
                    cx, cy = x1, y1
                    while True:
                        self.stdscr.addch(cy, cx, '#', attr)
                        if cx == x2 and cy == y2: break
                        e2 = 2 * err
                        if e2 >= dy: err += dy; cx += sx
                        if e2 <= dx: err += dx; cy += sy
                elif isinstance(obj, Freehand):
                    for r, l in enumerate(obj.lines): self.stdscr.addstr(obj.y+r, obj.x, l, attr)
            except: pass
        try: self.stdscr.addch(self.cursor_y, self.cursor_x, 'X', curses.A_REVERSE)
        except: pass
        self.stdscr.refresh()

if __name__ == "__main__":
    try: curses.wrapper(lambda s: Designer(s).run())
    except Exception as e: print(e)
