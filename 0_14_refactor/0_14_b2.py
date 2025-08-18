from future import annotations import curses import re from curses import textpad from enum import Enum, auto from dataclasses import dataclass, replace from pathlib import Path from typing import List, Union

==============================================================================

1) C++ TEMPLATE (unchanged in behavior)

==============================================================================

CPP_TEMPLATE = """ #include <Arduino.h>

// == COLORS == // Add 10 to make it bold in terminal emulators (e.g. FG_RED + 10) #define FG_BLACK 30 #define FG_RED 31 #define FG_GREEN 32 #define FG_YELLOW 33 #define FG_BLUE 34 #define FG_MAGENTA 35 #define FG_CYAN 36 #define FG_WHITE 37

struct Box { int16_t x, y, w, h; uint8_t color; }; struct Text { int16_t x, y; const char* content; uint8_t color; }; struct Line { int16_t x1, y1, x2, y2; uint8_t color; }; struct Freehand { int16_t x, y; const char** lines; uint8_t line_count; uint8_t color; };

static inline void moveCursor(int16_t x, int16_t y) { Serial.print("["); Serial.print(y + 1); Serial.print(";"); Serial.print(x + 1); Serial.print("H"); }

static inline void setColor(uint8_t color) { if (color == 0) { Serial.print("[0m"); return; } if (color >= 40) { Serial.print("[1;"); Serial.print(color - 10); } else { Serial.print("[0;"); Serial.print(color); } Serial.print("m"); }

static inline void clearScreen() { Serial.print("[2J[H"); }

// [[SCREEN_FUNCTIONS_PLACEHOLDER]]

void setup() { Serial.begin(115200); while (!Serial) { delay(10); } delay(200); Serial.print("[?25l"); // Hide cursor clearScreen(); // [[INITIAL_SCREEN_CALL_PLACEHOLDER]] }

void loop() { delay(100); } """

==============================================================================

2) DRAWABLE OBJECTS (dataclasses + strong typing)

==============================================================================

class Color(Enum): WHITE = 37 RED = 31 GREEN = 32 YELLOW = 33 BLUE = 34 MAGENTA = 35 CYAN = 36

COLOR_ORDER = [Color.WHITE, Color.RED, Color.GREEN, Color.YELLOW, Color.BLUE, Color.MAGENTA, Color.CYAN]

@dataclass class Box: x: int y: int w: int h: int color: Color = Color.WHITE

@dataclass class Text: x: int y: int content: str color: Color = Color.WHITE

@dataclass class Line: x1: int y1: int x2: int y2: int color: Color = Color.WHITE

@dataclass class Freehand: x: int y: int lines: List[str] color: Color = Color.WHITE

Drawable = Union[Box, Text, Line, Freehand]

==============================================================================

3) CODEGEN HELPERS

==============================================================================

def cpp_escape(s: str) -> str: return ( s.replace("", "\") .replace(""", "\"") .replace(" ", "\n") .replace(" ", "\r") )

re_cpp_ident = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")

def sanitize_ident(s: str) -> str: return re.sub(r"[^a-zA-Z0-9_]", "_", s)

def cpp_declaration(name: str, obj: Drawable) -> str: match obj: case Box(x, y, w, h, color): return f"  Box {name} = {{{x}, {y}, {w}, {h}, {color.value}}};" case Text(x, y, content, color): return f'  Text {name} = {{{x}, {y}, "{cpp_escape(content)}", {color.value}}};' case Line(x1, y1, x2, y2, color): return f"  Line {name} = {{{x1}, {y1}, {x2}, {y2}, {color.value}}};" case Freehand(x, y, lines, color): arr = f"{name}_lines" esc = ", ".join([f'"{cpp_escape(l)}"' for l in lines]) return ( f"  const char* {arr}[] = {{{esc}}}; " f"  Freehand {name} = {{{x}, {y}, {arr}, {len(lines)}, {color.value}}};" )

def cpp_draw_call(name: str) -> str: return f"  draw({name});"

==============================================================================

4) CURSES DESIGNER (interactive)

==============================================================================

class DesignMode(Enum): NAVIGATE = auto() PROMPT = auto() DRAW_BOX_START = auto() DRAW_BOX_END = auto() DRAW_LINE_START = auto() DRAW_LINE_END = auto() GET_TEXT = auto() GET_FREEHAND = auto()

HELP = { DesignMode.NAVIGATE: ( "Draw: (b)ox (l)ine (t)ext (f)reehand | Move: arrows | " "Select: <TAB> | (c)olor (d)elete (+/-)layer | Save: (s) | Quit: (q)" ), DesignMode.DRAW_BOX_START: "Box: move to start point, ENTER to set, ESC to cancel", DesignMode.DRAW_BOX_END:   "Box: move to end point, ENTER to finish, ESC to cancel", DesignMode.DRAW_LINE_START: "Line: move to start point, ENTER to set, ESC to cancel", DesignMode.DRAW_LINE_END:   "Line: move to end point, ENTER to finish, ESC to cancel", DesignMode.GET_TEXT:       "Typing text... ENTER to accept", DesignMode.GET_FREEHAND:   "Freehand: type lines; enter 'END' on a new prompt to finish", }

class Designer: def init(self, stdscr): self.stdscr = stdscr self.mode = DesignMode.NAVIGATE self.cursor_x, self.cursor_y = 0, 0 # objects: list of (name, Drawable) self.objects: list[tuple[str, Drawable]] = [] self.selected: int = -1 self.temp: dict[str, int] = {} self.status = HELP[self.mode]

# --------------------- main loop ---------------------
def run(self):
    curses.start_color(); curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_WHITE, -1)
    curses.init_pair(2, curses.COLOR_RED, -1)
    curses.init_pair(3, curses.COLOR_GREEN, -1)
    curses.init_pair(4, curses.COLOR_YELLOW, -1)
    curses.init_pair(5, curses.COLOR_BLUE, -1)
    curses.init_pair(6, curses.COLOR_MAGENTA, -1)
    curses.init_pair(7, curses.COLOR_CYAN, -1)
    self._redraw()
    while True:
        key = self.stdscr.getch()
        if not self._handle_key(key):
            break
        self._redraw()

# --------------------- input handling ---------------------
def _handle_key(self, key: int) -> bool:
    if key in (10, 13, curses.KEY_ENTER):  # ENTER
        return self._handle_enter()
    if key == 27:  # ESC
        return self._handle_esc()

    if self.mode in (DesignMode.DRAW_BOX_START, DesignMode.DRAW_BOX_END, DesignMode.DRAW_LINE_START, DesignMode.DRAW_LINE_END, DesignMode.NAVIGATE):
        if key in (curses.KEY_UP, curses.KEY_DOWN, curses.KEY_LEFT, curses.KEY_RIGHT):
            self._move_cursor_or_object(key)
            return True

    if self.mode != DesignMode.NAVIGATE:
        return True

    # NAVIGATE-only hotkeys
    if key == ord('q'):
        return False
    if key == ord('s'):
        self._save()
        return True
    if key == ord('	'):
        self._cycle_selection()
        return True
    if key in (curses.KEY_DC, ord('d')):
        self._delete_selected()
        return True
    if key == ord('c'):
        self._cycle_color()
        return True
    if key == ord('+'):
        self._change_layer(+1)
        return True
    if key == ord('-'):
        self._change_layer(-1)
        return True
    if key == ord('b'):
        self._start_box()
        return True
    if key == ord('l'):
        self._start_line()
        return True
    if key == ord('t'):
        self._add_text()
        return True
    if key == ord('f'):
        self._add_freehand()
        return True
    return True

def _handle_enter(self) -> bool:
    if self.mode == DesignMode.DRAW_BOX_START:
        self.mode = DesignMode.DRAW_BOX_END
        self.temp['x1'], self.temp['y1'] = self.cursor_x, self.cursor_y
        self._set_status()
        return True
    if self.mode == DesignMode.DRAW_BOX_END:
        x1, y1 = self.temp['x1'], self.temp['y1']
        x2, y2 = self.cursor_x, self.cursor_y
        x, y = min(x1, x2), min(y1, y2)
        w, h = abs(x2 - x1) + 1, abs(y2 - y1) + 1
        name = self._ask_ident("box")
        if name:
            self.objects.append((name, Box(x, y, w, h)))
            self.selected = len(self.objects) - 1
        self.mode = DesignMode.NAVIGATE
        self.temp.clear(); self._set_status()
        return True
    if self.mode == DesignMode.DRAW_LINE_START:
        self.mode = DesignMode.DRAW_LINE_END
        self.temp['x1'], self.temp['y1'] = self.cursor_x, self.cursor_y
        self._set_status()
        return True
    if self.mode == DesignMode.DRAW_LINE_END:
        x1, y1 = self.temp['x1'], self.temp['y1']
        x2, y2 = self.cursor_x, self.cursor_y
        name = self._ask_ident("line")
        if name:
            self.objects.append((name, Line(x1, y1, x2, y2)))
            self.selected = len(self.objects) - 1
        self.mode = DesignMode.NAVIGATE
        self.temp.clear(); self._set_status()
        return True
    return True

def _handle_esc(self) -> bool:
    if self.mode in (DesignMode.DRAW_BOX_START, DesignMode.DRAW_BOX_END, DesignMode.DRAW_LINE_START, DesignMode.DRAW_LINE_END, DesignMode.GET_FREEHAND, DesignMode.GET_TEXT):
        self.mode = DesignMode.NAVIGATE
        self.temp.clear()
        self._set_status("Cancelled.")
        return True
    # Deselect in NAVIGATE
    self.selected = -1
    self._set_status()
    return True

# --------------------- actions ---------------------
def _move_cursor_or_object(self, key: int) -> None:
    dx = dy = 0
    if key == curses.KEY_UP: dy = -1
    elif key == curses.KEY_DOWN: dy = 1
    elif key == curses.KEY_LEFT: dx = -1
    elif key == curses.KEY_RIGHT: dx = 1
    if self.selected != -1 and self.mode == DesignMode.NAVIGATE:
        name, obj = self.objects[self.selected]
        match obj:
            case Box(x, y, w, h, color):
                self.objects[self.selected] = (name, replace(obj, x=x+dx, y=y+dy))
            case Text(x, y, content, color):
                self.objects[self.selected] = (name, replace(obj, x=x+dx, y=y+dy))
            case Line(x1, y1, x2, y2, color):
                self.objects[self.selected] = (name, replace(obj, x1=x1+dx, y1=y1+dy, x2=x2+dx, y2=y2+dy))
            case Freehand(x, y, lines, color):
                self.objects[self.selected] = (name, replace(obj, x=x+dx, y=y+dy))
    else:
        self.cursor_x = max(0, self.cursor_x + dx)
        self.cursor_y = max(0, self.cursor_y + dy)

def _cycle_selection(self) -> None:
    if not self.objects:
        self.selected = -1; return
    self.selected = (self.selected + 1) % len(self.objects)

def _delete_selected(self) -> None:
    if 0 <= self.selected < len(self.objects):
        del self.objects[self.selected]
        self.selected = -1

def _cycle_color(self) -> None:
    if 0 <= self.selected < len(self.objects):
        name, obj = self.objects[self.selected]
        def next_color(c: Color) -> Color:
            idx = COLOR_ORDER.index(c)
            return COLOR_ORDER[(idx + 1) % len(COLOR_ORDER)]
        match obj:
            case Box(_, _, _, _, color):
                self.objects[self.selected] = (name, replace(obj, color=next_color(color)))
            case Text(_, _, _, color):
                self.objects[self.selected] = (name, replace(obj, color=next_color(color)))
            case Line(_, _, _, _, color):
                self.objects[self.selected] = (name, replace(obj, color=next_color(color)))
            case Freehand(_, _, _, color):
                self.objects[self.selected] = (name, replace(obj, color=next_color(color)))

def _change_layer(self, direction: int) -> None:
    if not (0 <= self.selected < len(self.objects)): return
    new_idx = self.selected + direction
    if 0 <= new_idx < len(self.objects):
        item = self.objects.pop(self.selected)
        self.objects.insert(new_idx, item)
        self.selected = new_idx

def _start_box(self) -> None:
    self.selected = -1
    self.mode = DesignMode.DRAW_BOX_START
    self.temp.clear(); self._set_status()

def _start_line(self) -> None:
    self.selected = -1
    self.mode = DesignMode.DRAW_LINE_START
    self.temp.clear(); self._set_status()

def _add_text(self) -> None:
    content = self._prompt("Enter text: ")
    if not content:
        self._set_status("Empty text; cancelled."); return
    name = self._ask_ident("text")
    if not name: return
    self.objects.append((name, Text(self.cursor_x, self.cursor_y, content)))
    self.selected = len(self.objects) - 1
    self._set_status()

def _add_freehand(self) -> None:
    lines: List[str] = []
    while True:
        line = self._prompt(f"Freehand line {len(lines)+1} (END to finish): ")
        if line.upper() == "END":
            break
        lines.append(line)
    if not lines:
        self._set_status("No lines entered."); return
    name = self._ask_ident("freehand")
    if not name: return
    self.objects.append((name, Freehand(self.cursor_x, self.cursor_y, lines)))
    self.selected = len(self.objects) - 1
    self._set_status()

# --------------------- UI helpers ---------------------
def _set_status(self, extra: str | None = None) -> None:
    base = HELP.get(self.mode, "")
    self.status = f"{base}" if not extra else f"{base} | {extra}"

def _prompt(self, prompt_text: str) -> str:
    self.mode = DesignMode.PROMPT
    h, w = self.stdscr.getmaxyx()
    self.stdscr.addstr(h - 1, 0, prompt_text.ljust(w - 1), curses.A_REVERSE)
    editwin = curses.newwin(1, max(1, w - len(prompt_text) - 2), h - 1, len(prompt_text) + 1)
    self.stdscr.refresh()
    box = textpad.Textbox(editwin, insert_mode=True)
    def validator(k):
        if k in (10, 13):
            return 7  # exit textpad
        return k
    try:
        box.edit(validator)
    except curses.error:
        pass
    text = box.gather().strip()
    self.mode = DesignMode.NAVIGATE
    self._set_status()
    return text

def _ask_ident(self, base: str) -> str | None:
    raw = self._prompt(f"Name for new {base} (blank = auto): ")
    if raw and not _re_cpp_ident.match(raw):
        self._prompt("Invalid C++ identifier. Press ENTER.")
        return None
    if raw:
        return raw
    # auto-name
    base = sanitize_ident(base)
    taken = {n for n, _ in self.objects}
    i = 1
    while f"{base}{i}" in taken:
        i += 1
    return f"{base}{i}"

# --------------------- rendering ---------------------
def _draw_objects(self) -> None:
    for idx, (name, obj) in enumerate(self.objects):
        selected = (idx == self.selected)
        attr = curses.A_BOLD if selected else curses.A_NORMAL
        pair = self._pair_for_color(obj)
        try:
            match obj:
                case Box(x, y, w, h, _):
                    # corners
                    self.stdscr.addch(y, x, '+', curses.color_pair(pair) | attr)
                    self.stdscr.addch(y, x + w - 1, '+', curses.color_pair(pair) | attr)
                    self.stdscr.addch(y + h - 1, x, '+', curses.color_pair(pair) | attr)
                    self.stdscr.addch(y + h - 1, x + w - 1, '+', curses.color_pair(pair) | attr)
                    # edges
                    for i in range(1, max(0, w - 1)):
                        self.stdscr.addch(y, x + i, '-', curses.color_pair(pair) | attr)
                        self.stdscr.addch(y + h - 1, x + i, '-', curses.color_pair(pair) | attr)
                    for i in range(1, max(0, h - 1)):
                        self.stdscr.addch(y + i, x, '|', curses.color_pair(pair) | attr)
                        self.stdscr.addch(y + i, x + w - 1, '|', curses.color_pair(pair) | attr)
                case Text(x, y, content, _):
                    self.stdscr.addstr(y, x, content, curses.color_pair(pair) | attr)
                case Line(x1, y1, x2, y2, _):
                    dx, sx = abs(x2 - x1), 1 if x1 < x2 else -1
                    dy, sy = -abs(y2 - y1), 1 if y1 < y2 else -1
                    err = dx + dy
                    x, y = x1, y1
                    while True:
                        self.stdscr.addch(y, x, '#', curses.color_pair(pair) | attr)
                        if x == x2 and y == y2: break
                        e2 = 2 * err
                        if e2 >= dy: err += dy; x += sx
                        if e2 <= dx: err += dx; y += sy
                case Freehand(x, y, lines, _):
                    for i, line in enumerate(lines):
                        self.stdscr.addstr(y + i, x, line, curses.color_pair(pair) | attr)
        except curses.error:
            # Off-screen drawing safely ignored
            pass

def _pair_for_color(self, obj: Drawable) -> int:
    c = (obj.color if hasattr(obj, 'color') else Color.WHITE)
    mapping = {
        Color.WHITE: 1,
        Color.RED: 2,
        Color.GREEN: 3,
        Color.YELLOW: 4,
        Color.BLUE: 5,
        Color.MAGENTA: 6,
        Color.CYAN: 7,
    }
    return mapping.get(c, 1)

def _draw_preview(self) -> None:
    if self.mode == DesignMode.DRAW_BOX_END and {'x1','y1'} <= self.temp.keys():
        y1, x1 = self.temp['y1'], self.temp['x1']
        y2, x2 = self.cursor_y, self.cursor_x
        try:
            textpad.rectangle(self.stdscr, min(y1, y2), min(x1, x2), max(y1, y2), max(x1, x2))
            self.stdscr.addch(y1, x1, 'X', curses.A_BOLD | curses.color_pair(2))
        except curses.error:
            pass
    elif self.mode == DesignMode.DRAW_LINE_END and {'x1','y1'} <= self.temp.keys():
        # temporary line preview
        _, obj = ("temp", Line(self.temp['x1'], self.temp['y1'], self.cursor_x, self.cursor_y))
        name = "temp"
        idx = -1
        selected = True
        pair = 2
        try:
            dx, sx = abs(obj.x2 - obj.x1), 1 if obj.x1 < obj.x2 else -1
            dy, sy = -abs(obj.y2 - obj.y1), 1 if obj.y1 < obj.y2 else -1
            err = dx + dy
            x, y = obj.x1, obj.y1
            while True:
                self.stdscr.addch(y, x, '#', curses.A_BOLD | curses.color_pair(pair))
                if x == obj.x2 and y == obj.y2: break
                e2 = 2 * err
                if e2 >= dy: err += dy; x += sx
                if e2 <= dx: err += dx; y += sy
            self.stdscr.addch(obj.y1, obj.x1, 'X', curses.A_BOLD | curses.color_pair(pair))
        except curses.error:
            pass
    elif self.mode in (DesignMode.DRAW_BOX_START, DesignMode.DRAW_LINE_START):
        try:
            self.stdscr.addch(self.cursor_y, self.cursor_x, 'X', curses.A_BOLD | curses.color_pair(2))
        except curses.error:
            pass

def _redraw(self) -> None:
    self.stdscr.clear()
    self._draw_objects()
    self._draw_preview()
    h, w = self.stdscr.getmaxyx()
    pos = f"Pos:({self.cursor_x},{self.cursor_y}) | {self.status}"
    try:
        self.stdscr.addstr(h - 1, 0, pos.ljust(w - 1), curses.A_REVERSE)
        curses.curs_set(1 if self.mode not in (DesignMode.PROMPT,) else 0)
        if self.mode != DesignMode.PROMPT:
            self.stdscr.move(self.cursor_y, self.cursor_x)
    except curses.error:
        pass
    self.stdscr.refresh()

# --------------------- saving / codegen ---------------------
def _save(self) -> None:
    if not self.objects:
        self._set_status("Nothing to save."); return
    code = self._generate_code()
    Path("ui_generated.ino").write_text(code, encoding="utf-8")
    self._set_status("✅ Saved to ui_generated.ino")

def _generate_code(self) -> str:
    decls: list[str] = []
    draws: list[str] = []
    for name, obj in self.objects:
        decls.append(cpp_declaration(name, obj))
        draws.append(cpp_draw_call(name))
    body = "

".join(decls + ["", *draws]) func = f"void drawScreen_main() {{ {body} }}

" code = CPP_TEMPLATE.replace("// [[SCREEN_FUNCTIONS_PLACEHOLDER]]", func) code = code.replace("// [[INITIAL_SCREEN_CALL_PLACEHOLDER]]", "drawScreen_main();") return code

==============================================================================

5) MAIN

==============================================================================

if name == "main": print("Starting Arduino Serial UI Designer (modernized, interactive)...") try: curses.wrapper(lambda stdscr: Designer(stdscr).run()) print(" Designer closed. If saved, 'ui_generated.ino' is ready.") except curses.error as e: print(f" Curses error: {e}") print("Your terminal may be too small or lacks full curses support.") except Exception as e: print(f" Error: {e}")

