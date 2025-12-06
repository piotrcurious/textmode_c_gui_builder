from __future__ import annotations
import curses
import re
import threading
import queue
import tkinter as tk
from tkinter import scrolledtext, font
from enum import Enum, auto
from dataclasses import dataclass
from pathlib import Path
from typing import List

# ==============================================================================
# 1) STATIC C++ LIBRARY CONTENT (Updated with Freehand support)
# ==============================================================================

SERIAL_UI_HEADER = r"""
#ifndef SERIAL_UI_H
#define SERIAL_UI_H
#include <Arduino.h>

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

    // New: Freehand drawing support
    void drawFreehand(int x, int y, const char* lines[], int count, UI_Color color) {
        setColor(color);
        for(int i=0; i<count; i++) {
            moveCursor(x, y + i);
            Serial.print(lines[i]);
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
    WHITE = 37
    RED = 31
    GREEN = 32
    YELLOW = 33
    BLUE = 34
    MAGENTA = 35
    CYAN = 36

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
    
    def to_cpp(self) -> str:
        # We generate a local array for the lines to keep it self-contained
        array_name = f"res_{self.name}"
        lines_cpp = ", ".join([f'"{l.replace("\"", "\\\"")}"' for l in self.lines])
        return (f'    const char* {array_name}[] = {{ {lines_cpp} }};\n'
                f'    ui.drawFreehand({self.x}, {self.y}, {array_name}, {len(self.lines)}, UI_Color::{self.color.name}); // {self.name}')

# ==============================================================================
# 3) GUI MANAGER (Tkinter in a Thread)
# ==============================================================================

class GuiManager:
    def __init__(self):
        self.root = None
        self.help_label = None
        self.queue = queue.Queue() # For sending data back to Curses
        self.thread = threading.Thread(target=self._run_gui, daemon=True)
        self.thread.start()
        self.ready_event = threading.Event()

    def _run_gui(self):
        self.root = tk.Tk()
        self.root.title("Designer Helpers")
        self.root.geometry("300x150+50+50")
        self.root.attributes('-topmost', True) # Keep on top of terminal
        
        # Help Window Section
        lbl_frame = tk.LabelFrame(self.root, text="Current Context", padx=5, pady=5)
        lbl_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.help_var = tk.StringVar(value="Initializing...")
        self.help_label = tk.Label(lbl_frame, textvariable=self.help_var, wraplength=280, justify="left")
        self.help_label.pack(fill="both")

        # Buttons
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(fill="x", padx=5, pady=5)
        tk.Button(btn_frame, text="Freehand Editor", command=self._open_freehand_window).pack(fill="x")

        self.ready_event.set()
        self.root.mainloop()

    def update_help(self, text):
        if self.root:
            self.root.after(0, lambda: self.help_var.set(text))

    def _open_freehand_window(self):
        # Create a new Toplevel window for ASCII editing
        win = tk.Toplevel(self.root)
        win.title("Freehand / ASCII Editor")
        win.geometry("400x300")
        
        lbl = tk.Label(win, text="Draw or Paste ASCII Art below:")
        lbl.pack(pady=2)
        
        # Monospace text area
        txt = scrolledtext.ScrolledText(win, width=40, height=10, font=("Courier New", 10))
        txt.pack(fill="both", expand=True, padx=5)
        
        def on_send():
            raw = txt.get("1.0", tk.END)
            # Split into lines, remove trailing empty lines
            lines = raw.split("\n")
            while lines and not lines[-1].strip(): lines.pop()
            if lines:
                self.queue.put(("FREEHAND", lines))
                win.destroy()
        
        tk.Button(win, text="Insert into Design", bg="#ddffdd", command=on_send).pack(pady=5, fill="x")

# ==============================================================================
# 4) PROJECT & PARSING LOGIC
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
        
        src = ['#include "ui_layout.h"', '', 'void drawScreen_Main(SerialUI& ui) {']
        for obj in objects:
            src.append(obj.to_cpp())
        src.append('}')
        Path(self.SOURCE_FILE).write_text("\n".join(src))

    def load(self) -> List[UIElement]:
        if not Path(self.SOURCE_FILE).exists(): return []
        content = Path(self.SOURCE_FILE).read_text()
        objs = []
        
        # Regex Parsers
        re_box = re.compile(r'ui\.drawBox\(\s*(-?\d+),\s*(-?\d+),\s*(-?\d+),\s*(-?\d+),\s*UI_Color::(\w+)\s*\);\s*//\s*(.*)')
        re_text = re.compile(r'ui\.drawText\(\s*(-?\d+),\s*(-?\d+),\s*"(.*)",\s*UI_Color::(\w+)\s*\);\s*//\s*(.*)')
        re_line = re.compile(r'ui\.drawLine\(\s*(-?\d+),\s*(-?\d+),\s*(-?\d+),\s*(-?\d+),\s*UI_Color::(\w+)\s*\);\s*//\s*(.*)')
        # Freehand is complex, simplified regex for standard generated format
        re_fh_arr = re.compile(r'const char\*\s+(\w+)\[\]\s*=\s*\{(.*?)\};', re.DOTALL)
        re_fh_call = re.compile(r'ui\.drawFreehand\(\s*(-?\d+),\s*(-?\d+),\s*(\w+),\s*(\d+),\s*UI_Color::(\w+)\s*\);\s*//\s*(.*)')

        # Extract arrays first
        arrays = {}
        for m in re_fh_arr.finditer(content):
            name, raw_content = m.groups()
            # Crude split by quote to get content
            lines = [s for s in raw_content.split('"') if s.strip() and s.strip() != ',']
            arrays[name] = lines

        for line in content.splitlines():
            line = line.strip()
            if m := re_box.search(line):
                objs.append(Box(m.group(6), Color.from_string(m.group(5)), *map(int, m.groups()[:4])))
            elif m := re_text.search(line):
                objs.append(Text(m.group(5), Color.from_string(m.group(4)), int(m.group(1)), int(m.group(2)), m.group(3)))
            elif m := re_line.search(line):
                objs.append(Line(m.group(6), Color.from_string(m.group(5)), *map(int, m.groups()[:4])))
            elif m := re_fh_call.search(line):
                x, y, arr_name, cnt, col, name = m.groups()
                if arr_name in arrays:
                    objs.append(Freehand(name, Color.from_string(col), int(x), int(y), arrays[arr_name]))
        return objs

# ==============================================================================
# 5) CURSES DESIGNER
# ==============================================================================

class DesignMode(Enum):
    NAVIGATE = auto()
    DRAW_BOX_START = auto()
    DRAW_BOX_END = auto()
    DRAW_LINE_START = auto()
    DRAW_LINE_END = auto()
    WAIT_GUI = auto() # Waiting for Freehand

HELP_TEXT = {
    DesignMode.NAVIGATE: "Move: ARROWS | Box: b | Line: l | Text: t | Freehand: f (Popup) | Save: s | Del: d | Tab: Select",
    DesignMode.DRAW_BOX_START: "BOX: Move to Top-Left -> ENTER",
    DesignMode.DRAW_BOX_END: "BOX: Move to Bottom-Right -> ENTER",
    DesignMode.DRAW_LINE_START: "LINE: Start Point -> ENTER",
    DesignMode.DRAW_LINE_END: "LINE: End Point -> ENTER",
    DesignMode.WAIT_GUI: "Check the Popup Window to insert content...",
}

class Designer:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.mode = DesignMode.NAVIGATE
        self.cursor_x, self.cursor_y = 5, 5
        self.pm = ProjectManager()
        self.objects = self.pm.load()
        self.selected_idx = -1
        self.temp = {}
        self.colors = list(Color)
        
        # Start GUI
        self.gui = GuiManager()
        self.gui.ready_event.wait(timeout=2)
        self._update_status()

    def _update_status(self):
        msg = HELP_TEXT.get(self.mode, "")
        self.gui.update_help(msg) # Send to Tkinter
        
    def run(self):
        curses.start_color()
        curses.use_default_colors()
        curses.curs_set(1)
        for i, c in enumerate(self.colors, 1):
            curses.init_pair(i, getattr(curses, f"COLOR_{c.name}"), -1)

        self.stdscr.nodelay(True) # Non-blocking input to check GUI queue

        while True:
            self._draw()
            self._check_gui_queue()
            
            try:
                key = self.stdscr.getch()
            except: key = -1

            if key == -1: 
                curses.napms(50)
                continue
                
            if not self._handle_key(key):
                break

    def _check_gui_queue(self):
        try:
            while True:
                action, data = self.gui.queue.get_nowait()
                if action == "FREEHAND":
                    # Data is list of strings
                    name = f"art_{len(self.objects)}"
                    obj = Freehand(name, Color.WHITE, self.cursor_x, self.cursor_y, data)
                    self.objects.append(obj)
                    self.mode = DesignMode.NAVIGATE
                    self._update_status()
        except queue.Empty:
            pass

    def _handle_key(self, key):
        if key == 27: # ESC
            self.mode = DesignMode.NAVIGATE
            self.selected_idx = -1
            self._update_status()
            return True

        # Common movement
        if key in (curses.KEY_UP, curses.KEY_DOWN, curses.KEY_LEFT, curses.KEY_RIGHT):
            self._move(key)
            return True

        if self.mode == DesignMode.NAVIGATE:
            if key == ord('q'): return False
            if key == ord('s'): self.pm.save(self.objects); self.gui.update_help("Saved to C++!"); return True
            if key == ord('b'): self.mode = DesignMode.DRAW_BOX_START
            if key == ord('l'): self.mode = DesignMode.DRAW_LINE_START
            if key == ord('t'): self._add_text_prompt()
            if key == ord('f'): 
                self.mode = DesignMode.WAIT_GUI
                self.gui._open_freehand_window() # Force open
            
            if key == 9: # Tab
                if self.objects: self.selected_idx = (self.selected_idx + 1) % len(self.objects)
            if key == ord('d') and self.selected_idx >= 0:
                self.objects.pop(self.selected_idx)
                self.selected_idx = -1
            if key == ord('c') and self.selected_idx >= 0:
                o = self.objects[self.selected_idx]
                o.color = self.colors[(self.colors.index(o.color)+1)%len(self.colors)]
            
            self._update_status()

        elif self.mode == DesignMode.DRAW_BOX_START:
            if key in (10, 13):
                self.temp = {'x': self.cursor_x, 'y': self.cursor_y}
                self.mode = DesignMode.DRAW_BOX_END
                self._update_status()

        elif self.mode == DesignMode.DRAW_BOX_END:
            if key in (10, 13):
                x, y = min(self.temp['x'], self.cursor_x), min(self.temp['y'], self.cursor_y)
                w, h = abs(self.temp['x']-self.cursor_x)+1, abs(self.temp['y']-self.cursor_y)+1
                self.objects.append(Box(f"box_{len(self.objects)}", Color.WHITE, x, y, w, h))
                self.mode = DesignMode.NAVIGATE
                self._update_status()

        elif self.mode == DesignMode.DRAW_LINE_START:
            if key in (10, 13):
                self.temp = {'x': self.cursor_x, 'y': self.cursor_y}
                self.mode = DesignMode.DRAW_LINE_END
                self._update_status()

        elif self.mode == DesignMode.DRAW_LINE_END:
            if key in (10, 13):
                self.objects.append(Line(f"line_{len(self.objects)}", Color.WHITE, self.temp['x'], self.temp['y'], self.cursor_x, self.cursor_y))
                self.mode = DesignMode.NAVIGATE
                self._update_status()

        return True

    def _add_text_prompt(self):
        curses.echo()
        self.stdscr.addstr(0, 0, "TEXT: ")
        t = self.stdscr.getstr().decode('utf-8')
        curses.noecho()
        if t: self.objects.append(Text(f"txt_{len(self.objects)}", Color.WHITE, self.cursor_x, self.cursor_y, t))

    def _move(self, key):
        dx, dy = 0, 0
        if key == curses.KEY_UP: dy = -1
        if key == curses.KEY_DOWN: dy = 1
        if key == curses.KEY_LEFT: dx = -1
        if key == curses.KEY_RIGHT: dx = 1
        
        if self.mode == DesignMode.NAVIGATE and self.selected_idx >= 0:
            o = self.objects[self.selected_idx]
            if hasattr(o, 'x'): o.x += dx; o.y += dy
            if hasattr(o, 'x1'): o.x1 += dx; o.y1 += dy; o.x2 += dx; o.y2 += dy
        else:
            self.cursor_x += dx
            self.cursor_y += dy
        
        # Clamp
        h, w = self.stdscr.getmaxyx()
        self.cursor_x = max(0, min(w-1, self.cursor_x))
        self.cursor_y = max(0, min(h-1, self.cursor_y))

    def _draw(self):
        self.stdscr.clear()
        
        for i, obj in enumerate(self.objects):
            attr = curses.color_pair(self.colors.index(obj.color)+1)
            if i == self.selected_idx: attr |= (curses.A_BOLD | curses.A_REVERSE)
            
            try:
                if isinstance(obj, Box):
                    # Simple box visualization
                    self.stdscr.addch(obj.y, obj.x, '+', attr)
                    self.stdscr.addch(obj.y+obj.h-1, obj.x+obj.w-1, '+', attr)
                    for k in range(1, obj.w-1): 
                        self.stdscr.addch(obj.y, obj.x+k, '-', attr)
                        self.stdscr.addch(obj.y+obj.h-1, obj.x+k, '-', attr)
                    for k in range(1, obj.h-1): 
                        self.stdscr.addch(obj.y+k, obj.x, '|', attr)
                        self.stdscr.addch(obj.y+k, obj.x+obj.w-1, '|', attr)
                elif isinstance(obj, Text):
                    self.stdscr.addstr(obj.y, obj.x, obj.content, attr)
                elif isinstance(obj, Line):
                    self.stdscr.addline(obj.y1, obj.x1, obj.y2, obj.x2, attr) # Curses helper if avail, else manual
                elif isinstance(obj, Freehand):
                    for r, line in enumerate(obj.lines):
                        self.stdscr.addstr(obj.y + r, obj.x, line, attr)
            except: pass

        # Draw Cursor
        try: self.stdscr.addch(self.cursor_y, self.cursor_x, 'X', curses.A_REVERSE)
        except: pass
        self.stdscr.refresh()

if __name__ == "__main__":
    try:
        curses.wrapper(lambda s: Designer(s).run())
    except Exception as e:
        print(e)
