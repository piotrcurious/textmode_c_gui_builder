from __future__ import annotations
import curses
import re
import os
from curses import textpad
from enum import Enum, auto
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Union, Tuple, Optional

# ==============================================================================
# 1) STATIC C++ LIBRARY CONTENT (The "Engine")
# ==============================================================================

# This file (SerialUI.h) allows the generated code to be clean and minimal.
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
        // Top & Bottom
        for (int i = 0; i < w; i++) {
            moveCursor(x + i, y); Serial.print("-");
            moveCursor(x + i, y + h - 1); Serial.print("-");
        }
        // Left & Right
        for (int i = 0; i < h; i++) {
            moveCursor(x, y + i); Serial.print("|");
            moveCursor(x + w - 1, y + i); Serial.print("|");
        }
        // Corners
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
};
#endif
"""

# ==============================================================================
# 2) DATA MODEL & SERIALIZATION
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
        try:
            return cls[name.upper()]
        except KeyError:
            return cls.WHITE

@dataclass
class UIElement:
    name: str
    color: Color = Color.WHITE

    def to_cpp(self) -> str:
        raise NotImplementedError

@dataclass
class Box(UIElement):
    x: int = 0; y: int = 0; w: int = 0; h: int = 0
    
    def to_cpp(self) -> str:
        return f'    ui.drawBox({self.x}, {self.y}, {self.w}, {self.h}, UI_Color::{self.color.name}); // {self.name}'

@dataclass
class Text(UIElement):
    x: int = 0; y: int = 0
    content: str = ""
    
    def to_cpp(self) -> str:
        clean_content = self.content.replace('"', '\\"')
        return f'    ui.drawText({self.x}, {self.y}, "{clean_content}", UI_Color::{self.color.name}); // {self.name}'

@dataclass
class Line(UIElement):
    x1: int = 0; y1: int = 0; x2: int = 0; y2: int = 0
    
    def to_cpp(self) -> str:
        return f'    ui.drawLine({self.x1}, {self.y1}, {self.x2}, {self.y2}, UI_Color::{self.color.name}); // {self.name}'

# ==============================================================================
# 3) ROUND-TRIP PARSER
# ==============================================================================

class ProjectManager:
    """Handles reading/writing the generated C++ files."""
    
    HEADER_FILE = "ui_layout.h"
    SOURCE_FILE = "ui_layout.cpp"
    LIB_FILE = "SerialUI.h"

    def __init__(self):
        self.objects: List[UIElement] = []

    def ensure_lib_exists(self):
        if not Path(self.LIB_FILE).exists():
            Path(self.LIB_FILE).write_text(SERIAL_UI_HEADER, encoding="utf-8")

    def save_project(self, objects: List[UIElement]):
        self.ensure_lib_exists()
        self.objects = objects
        
        # 1. Generate Header
        header_content = (
            "#ifndef UI_LAYOUT_H\n#define UI_LAYOUT_H\n"
            "#include \"SerialUI.h\"\n\n"
            "void drawScreen_Main(SerialUI& ui);\n\n"
            "#endif\n"
        )
        Path(self.HEADER_FILE).write_text(header_content, encoding="utf-8")

        # 2. Generate Source
        cpp_lines = [
            '#include "ui_layout.h"',
            '',
            'void drawScreen_Main(SerialUI& ui) {',
        ]
        for obj in self.objects:
            cpp_lines.append(obj.to_cpp())
        cpp_lines.append('}')
        
        Path(self.SOURCE_FILE).write_text("\n".join(cpp_lines), encoding="utf-8")

    def load_project(self) -> List[UIElement]:
        """Parses the C++ source file to reconstruct the UI objects."""
        if not Path(self.SOURCE_FILE).exists():
            return []

        content = Path(self.SOURCE_FILE).read_text(encoding="utf-8")
        loaded_objects = []

        # Regex patterns to parse specific C++ function calls
        # Looks for: ui.drawBox(1, 2, 3, 4, UI_Color::RED); // name
        
        re_box = re.compile(r'ui\.drawBox\(\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*UI_Color::(\w+)\s*\);\s*//\s*(.*)')
        re_text = re.compile(r'ui\.drawText\(\s*(\d+),\s*(\d+),\s*"(.*)",\s*UI_Color::(\w+)\s*\);\s*//\s*(.*)')
        re_line = re.compile(r'ui\.drawLine\(\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*UI_Color::(\w+)\s*\);\s*//\s*(.*)')

        for line in content.splitlines():
            line = line.strip()
            
            # Box
            m = re_box.search(line)
            if m:
                x, y, w, h, col_str, name = m.groups()
                loaded_objects.append(Box(name.strip(), Color.from_string(col_str), int(x), int(y), int(w), int(h)))
                continue

            # Text
            m = re_text.search(line)
            if m:
                x, y, txt, col_str, name = m.groups()
                # Unescape quotes
                txt = txt.replace('\\"', '"')
                loaded_objects.append(Text(name.strip(), Color.from_string(col_str), int(x), int(y), content=txt))
                continue

            # Line
            m = re_line.search(line)
            if m:
                x1, y1, x2, y2, col_str, name = m.groups()
                loaded_objects.append(Line(name.strip(), Color.from_string(col_str), int(x1), int(y1), int(x2), int(y2)))
                continue

        return loaded_objects

# ==============================================================================
# 4) CURSES DESIGNER UI (Enhanced)
# ==============================================================================

class DesignMode(Enum):
    NAVIGATE = auto()
    PROMPT = auto()
    DRAW_BOX_START = auto()
    DRAW_BOX_END = auto()
    DRAW_LINE_START = auto()
    DRAW_LINE_END = auto()
    GET_TEXT = auto()

HELP_TEXT = {
    DesignMode.NAVIGATE: "ARROWS:Move | b:Box l:Line t:Text | TAB:Select c:Color d:Delete | s:Save q:Quit",
    DesignMode.DRAW_BOX_START: "BOX: Move to start corner -> ENTER",
    DesignMode.DRAW_BOX_END: "BOX: Move to opposite corner -> ENTER",
    DesignMode.GET_TEXT: "Type text -> ENTER to finish",
}

class Designer:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.mode = DesignMode.NAVIGATE
        self.cursor_x, self.cursor_y = 0, 0
        self.project_mgr = ProjectManager()
        
        # Load existing project if available
        self.objects: List[UIElement] = self.project_mgr.load_project()
        
        self.selected_idx: int = -1
        self.temp_coords: dict = {}
        self.msg = "Loaded." if self.objects else "New Project."
        self.colors = [c for c in Color]

    def run(self):
        curses.start_color()
        curses.use_default_colors()
        curses.curs_set(1)
        # Init color pairs based on Enum values mapping to curses indices
        for i, c in enumerate(self.colors, start=1):
            # Map VT100 colors roughly to curses constants
            c_const = getattr(curses, f"COLOR_{c.name}", curses.COLOR_WHITE)
            curses.init_pair(i, c_const, -1)

        while True:
            self._draw_screen()
            key = self.stdscr.getch()
            if not self._handle_input(key):
                break

    def _handle_input(self, key) -> bool:
        if key == 27: # ESC
            self.mode = DesignMode.NAVIGATE
            self.selected_idx = -1
            self.msg = "Cancelled."
            return True

        if self.mode == DesignMode.NAVIGATE:
            if key == ord('q'): return False
            if key == ord('s'): 
                self.project_mgr.save_project(self.objects)
                self.msg = f"Saved to {self.project_mgr.SOURCE_FILE}"
            
            # Tools
            elif key == ord('b'): self.mode = DesignMode.DRAW_BOX_START; self.msg = HELP_TEXT[self.mode]
            elif key == ord('l'): self.mode = DesignMode.DRAW_LINE_START; self.msg = "LINE: Start point -> ENTER"
            elif key == ord('t'): self._add_text()
            
            # Edit
            elif key == 9: # TAB
                if self.objects: self.selected_idx = (self.selected_idx + 1) % len(self.objects)
            elif key == ord('d') and self.selected_idx != -1:
                self.objects.pop(self.selected_idx)
                self.selected_idx = -1
            elif key == ord('c') and self.selected_idx != -1:
                self._cycle_color()
            
            # Move Cursor or Object
            elif key in (curses.KEY_UP, curses.KEY_DOWN, curses.KEY_LEFT, curses.KEY_RIGHT):
                self._move(key)
        
        elif self.mode == DesignMode.DRAW_BOX_START:
            if key in (10, 13):
                self.temp_coords = {'x': self.cursor_x, 'y': self.cursor_y}
                self.mode = DesignMode.DRAW_BOX_END
                self.msg = HELP_TEXT[self.mode]
            else:
                self._move_cursor(key)

        elif self.mode == DesignMode.DRAW_BOX_END:
            if key in (10, 13):
                x1, y1 = self.temp_coords['x'], self.temp_coords['y']
                x, y = min(x1, self.cursor_x), min(y1, self.cursor_y)
                w, h = abs(self.cursor_x - x1) + 1, abs(self.cursor_y - y1) + 1
                name = f"box_{len(self.objects)}"
                self.objects.append(Box(name, Color.WHITE, x, y, w, h))
                self.mode = DesignMode.NAVIGATE
            else:
                self._move_cursor(key)

        elif self.mode == DesignMode.DRAW_LINE_START:
            if key in (10, 13):
                self.temp_coords = {'x': self.cursor_x, 'y': self.cursor_y}
                self.mode = DesignMode.DRAW_LINE_END
                self.msg = "LINE: End point -> ENTER"
            else:
                self._move_cursor(key)

        elif self.mode == DesignMode.DRAW_LINE_END:
            if key in (10, 13):
                name = f"line_{len(self.objects)}"
                self.objects.append(Line(name, Color.WHITE, self.temp_coords['x'], self.temp_coords['y'], self.cursor_x, self.cursor_y))
                self.mode = DesignMode.NAVIGATE
            else:
                self._move_cursor(key)

        return True

    def _add_text(self):
        self.mode = DesignMode.PROMPT
        curses.echo()
        self.stdscr.addstr(self.stdscr.getmaxyx()[0]-1, 0, "Text: ")
        txt = self.stdscr.getstr().decode('utf-8')
        curses.noecho()
        if txt:
            name = f"txt_{len(self.objects)}"
            self.objects.append(Text(name, Color.WHITE, self.cursor_x, self.cursor_y, txt))
        self.mode = DesignMode.NAVIGATE

    def _move(self, key):
        dx, dy = 0, 0
        if key == curses.KEY_UP: dy = -1
        elif key == curses.KEY_DOWN: dy = 1
        elif key == curses.KEY_LEFT: dx = -1
        elif key == curses.KEY_RIGHT: dx = 1

        if self.selected_idx != -1:
            obj = self.objects[self.selected_idx]
            if isinstance(obj, (Box, Text)):
                obj.x += dx; obj.y += dy
            elif isinstance(obj, Line):
                obj.x1 += dx; obj.y1 += dy; obj.x2 += dx; obj.y2 += dy
        else:
            self.cursor_x += dx
            self.cursor_y += dy
        
        # Clamp cursor
        h, w = self.stdscr.getmaxyx()
        self.cursor_x = max(0, min(w-1, self.cursor_x))
        self.cursor_y = max(0, min(h-2, self.cursor_y))

    def _move_cursor(self, key):
        # Helper for drawing modes where we only move cursor, not objects
        dx, dy = 0, 0
        if key == curses.KEY_UP: dy = -1
        elif key == curses.KEY_DOWN: dy = 1
        elif key == curses.KEY_LEFT: dx = -1
        elif key == curses.KEY_RIGHT: dx = 1
        self.cursor_x += dx
        self.cursor_y += dy

    def _cycle_color(self):
        obj = self.objects[self.selected_idx]
        idx = self.colors.index(obj.color)
        obj.color = self.colors[(idx + 1) % len(self.colors)]

    def _get_color_attr(self, color_enum):
        idx = self.colors.index(color_enum) + 1
        return curses.color_pair(idx)

    def _draw_screen(self):
        self.stdscr.clear()
        
        # Draw Objects
        for i, obj in enumerate(self.objects):
            attr = self._get_color_attr(obj.color)
            if i == self.selected_idx: attr |= curses.A_BOLD | curses.A_REVERSE

            try:
                if isinstance(obj, Text):
                    self.stdscr.addstr(obj.y, obj.x, obj.content, attr)
                elif isinstance(obj, Box):
                    # Basic box drawing
                    self.stdscr.addch(obj.y, obj.x, '+', attr)
                    self.stdscr.addch(obj.y + obj.h - 1, obj.x + obj.w - 1, '+', attr)
                    for x in range(1, obj.w - 1):
                        self.stdscr.addch(obj.y, obj.x + x, '-', attr)
                        self.stdscr.addch(obj.y + obj.h - 1, obj.x + x, '-', attr)
                    for y in range(1, obj.h - 1):
                        self.stdscr.addch(obj.y + y, obj.x, '|', attr)
                        self.stdscr.addch(obj.y + y, obj.x + obj.w - 1, '|', attr)
                elif isinstance(obj, Line):
                    # Bresenham preview
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
            except curses.error:
                pass # Clipping

        # Draw Temp Drawing Preview
        if self.mode == DesignMode.DRAW_BOX_END:
            try:
                y1, x1 = self.temp_coords['y'], self.temp_coords['x']
                y2, x2 = self.cursor_y, self.cursor_x
                textpad.rectangle(self.stdscr, min(y1,y2), min(x1,x2), max(y1,y2), max(x1,x2))
            except: pass

        # Status Bar
        h, w = self.stdscr.getmaxyx()
        status = f" {self.msg} | Pos: {self.cursor_x},{self.cursor_y} "
        try:
            self.stdscr.addstr(h-1, 0, status.ljust(w-1), curses.A_REVERSE)
            self.stdscr.move(self.cursor_y, self.cursor_x)
        except: pass
        self.stdscr.refresh()

if __name__ == "__main__":
    try:
        curses.wrapper(lambda stdscr: Designer(stdscr).run())
        print(f"Done. Files generated: {ProjectManager.SOURCE_FILE}, {ProjectManager.HEADER_FILE}, {ProjectManager.LIB_FILE}")
    except Exception as e:
        print(f"Error: {e}")
