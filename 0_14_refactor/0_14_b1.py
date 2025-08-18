from future import annotations import curses import re from curses import textpad from enum import Enum, auto from dataclasses import dataclass from pathlib import Path from typing import List, Union

==============================================================================

1. C++ Template

==============================================================================

CPP_TEMPLATE = """ #include <Arduino.h>

// == COLORS == #define FG_BLACK 30 #define FG_RED 31 #define FG_GREEN 32 #define FG_YELLOW 33 #define FG_BLUE 34 #define FG_MAGENTA 35 #define FG_CYAN 36 #define FG_WHITE 37

struct Box { int16_t x, y, w, h; uint8_t color; }; struct Text { int16_t x, y; const char* content; uint8_t color; }; struct Line { int16_t x1, y1, x2, y2; uint8_t color; }; struct Freehand { int16_t x, y; const char** lines; uint8_t line_count; uint8_t color; };

void moveCursor(int16_t x, int16_t y) { Serial.print("\033["); Serial.print(y + 1); Serial.print(";"); Serial.print(x + 1); Serial.print("H"); }

void setColor(uint8_t color) { if (color == 0) { Serial.print("\033[0m"); return; } if (color >= 40) { Serial.print("\033[1;"); Serial.print(color - 10); } else { Serial.print("\033[0;"); Serial.print(color); } Serial.print("m"); }

void clearScreen() { Serial.print("\033[2J\033[H"); }

// [[SCREEN_FUNCTIONS_PLACEHOLDER]]

void setup() { Serial.begin(115200); while (!Serial) { delay(10); } delay(1000); Serial.print("\033[?25l"); // Hide cursor clearScreen(); // [[INITIAL_SCREEN_CALL_PLACEHOLDER]] }

void loop() { delay(100); } """

==============================================================================

2. Drawable Objects (dataclasses)

==============================================================================

class Color(Enum): WHITE = 37 RED = 31 GREEN = 32 YELLOW = 33 BLUE = 34 MAGENTA = 35 CYAN = 36

@dataclass class Box: x: int y: int w: int h: int color: Color

@dataclass class Text: x: int y: int content: str color: Color

@dataclass class Line: x1: int y1: int x2: int y2: int color: Color

@dataclass class Freehand: x: int y: int lines: List[str] color: Color

Drawable = Union[Box, Text, Line, Freehand]

==============================================================================

3. Code Generation Helpers

==============================================================================

def cpp_escape(s: str) -> str: return ( s.replace("\", "\\") .replace(""", "\"") .replace("\n", "\n") .replace("\r", "\r") )

def cpp_declaration(name: str, obj: Drawable) -> str: match obj: case Box(x, y, w, h, color): return f"  Box {name} = {{{x}, {y}, {w}, {h}, {color.value}}};" case Text(x, y, content, color): return f'  Text {name} = {{{x}, {y}, "{cpp_escape(content)}", {color.value}}};' case Line(x1, y1, x2, y2, color): return f"  Line {name} = {{{x1}, {y1}, {x2}, {y2}, {color.value}}};" case Freehand(x, y, lines, color): arr = f"{name}_lines" esc = ", ".join([f'"{cpp_escape(l)}"' for l in lines]) return ( f"  const char* {arr}[] = {{{esc}}};\n" f"  Freehand {name} = {{{x}, {y}, {arr}, {len(lines)}, {color.value}}};" )

def cpp_draw_call(name: str) -> str: return f"  draw({name});"

==============================================================================

4. Designer Class (curses UI)

==============================================================================

class DesignMode(Enum): NAVIGATE = auto() PROMPT = auto()

HELP = { DesignMode.NAVIGATE: "Draw: (b)ox (l)ine (t)ext (f)reehand | (n)ew screen (s)ave", }

class Designer: def init(self, stdscr): self.stdscr = stdscr self.mode = DesignMode.NAVIGATE self.cursor_x, self.cursor_y = 0, 0 self.objects: list[tuple[str, Drawable]] = [] self.status = HELP[self.mode]

def run(self):
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_WHITE, -1)
    curses.init_pair(2, curses.COLOR_RED, -1)
    curses.init_pair(3, curses.COLOR_GREEN, -1)
    curses.init_pair(4, curses.COLOR_YELLOW, -1)
    curses.init_pair(5, curses.COLOR_BLUE, -1)
    curses.init_pair(6, curses.COLOR_MAGENTA, -1)
    curses.init_pair(7, curses.COLOR_CYAN, -1)

    while True:
        self._draw_ui()
        key = self.stdscr.getch()
        if key == ord('q'):
            break
        elif key == ord('s'):
            self._save()

def _draw_ui(self):
    self.stdscr.clear()
    h, w = self.stdscr.getmaxyx()
    pos = f"Pos:({self.cursor_x},{self.cursor_y}) | {self.status}"
    self.stdscr.addstr(h-1, 0, pos.ljust(w-1), curses.A_REVERSE)
    self.stdscr.refresh()

def _save(self):
    code = self._generate_code()
    Path("ui_generated.ino").write_text(code, encoding="utf-8")
    self.status = "✅ Saved to ui_generated.ino"

def _generate_code(self) -> str:
    decls, draws = [], []
    for name, obj in self.objects:
        decls.append(cpp_declaration(name, obj))
        draws.append(cpp_draw_call(name))
    func = "void drawScreen() {\n" + "\n".join(decls+draws) + "\n}" 
    code = CPP_TEMPLATE.replace("// [[SCREEN_FUNCTIONS_PLACEHOLDER]]", func)
    code = code.replace("// [[INITIAL_SCREEN_CALL_PLACEHOLDER]]", "drawScreen();")
    return code

==============================================================================

5. Main

==============================================================================

if name == "main": print("Starting Arduino UI Designer (modernized)...") try: curses.wrapper(lambda stdscr: Designer(stdscr).run()) except Exception as e: print(f"Error: {e}")

