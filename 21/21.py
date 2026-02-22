#!/usr/bin/env python3
from __future__ import annotations
import curses
import re
import threading
import queue
import json
import time
import sys
import tkinter as tk
from tkinter import scrolledtext, ttk, simpledialog
from enum import Enum, auto
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict, Any, Optional

# ------------------------------
# Minimal C header snippet for generator
# ------------------------------
SERIAL_UI_HEADER = r"""
#ifndef SERIAL_UI_H
#define SERIAL_UI_H
#include <Arduino.h>
#include <avr/pgmspace.h>
#include <stdarg.h>

enum class UI_Color {
    BLACK=30, RED=31, GREEN=32, YELLOW=33, BLUE=34, MAGENTA=35, CYAN=36, WHITE=37,
    B_BLACK=90, B_RED=91, B_GREEN=92, B_YELLOW=93, B_BLUE=94, B_MAGENTA=95, B_CYAN=96, B_WHITE=97,
    BG_BLACK=40, BG_RED=41, BG_GREEN=42, BG_YELLOW=43, BG_BLUE=44, BG_MAGENTA=45, BG_CYAN=46, BG_WHITE=47,
    BG_B_BLACK=100, BG_B_RED=101, BG_B_GREEN=102, BG_B_YELLOW=103, BG_B_BLUE=104, BG_B_MAGENTA=105, BG_B_CYAN=106, BG_B_WHITE=107
};
struct UI_Box { int16_t x, y, w, h; UI_Color color; };
struct UI_Text { int16_t x, y; const char* content; UI_Color color; };
struct UI_Line { int16_t x1, y1, x2, y2; UI_Color color; };
struct UI_Freehand { int16_t x, y; const char* const* lines; uint8_t count; UI_Color color; };

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
        Serial.print("\x1b["); Serial.print((int)color); Serial.print("m");
    }

    void moveCursor(int x, int y) {
        Serial.print("\x1b["); Serial.print(y + 1); Serial.print(";"); Serial.print(x + 1); Serial.print("H");
    }

    // --- DRAWING METHODS ---
    void draw(const UI_Text& t) {
        setColor(t.color); moveCursor(t.x, t.y); Serial.print(t.content); resetAttr();
    }

    void draw(const UI_Box& b) {
        setColor(b.color);
        for (int i = 0; i < b.w; i++) { moveCursor(b.x + i, b.y); Serial.print("-"); moveCursor(b.x + i, b.y + b.h - 1); Serial.print("-"); }
        for (int i = 0; i < b.h; i++) { moveCursor(b.x, b.y + i); Serial.print("|"); moveCursor(b.x + b.w - 1, b.y + i); Serial.print("|"); }
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

    // --- DEVELOPER HELPER METHODS ---
    void drawText(int16_t x, int16_t y, const char* text, UI_Color color) {
        setColor(color);
        moveCursor(x, y);
        Serial.print(text);
        resetAttr();
    }

    void printfText(const UI_Text& text, ...) {
        char buffer[128]; // Be mindful of stack size
        va_list args;
        va_start(args, text);
        vsnprintf(buffer, sizeof(buffer), text.content, args);
        va_end(args);
        drawText(text.x, text.y, buffer, text.color);
    }
};
#endif
"""

# ------------------------------
# Data model
# ------------------------------
class Color(Enum):
    BLACK=30; RED=31; GREEN=32; YELLOW=33; BLUE=34; MAGENTA=35; CYAN=36; WHITE=37
    B_BLACK=90; B_RED=91; B_GREEN=92; B_YELLOW=93; B_BLUE=94; B_MAGENTA=95; B_CYAN=96; B_WHITE=97
    BG_BLACK=40; BG_RED=41; BG_GREEN=42; BG_YELLOW=43; BG_BLUE=44; BG_MAGENTA=45; BG_CYAN=46; BG_WHITE=47
    BG_B_BLACK=100; BG_B_RED=101; BG_B_GREEN=102; BG_B_YELLOW=103; BG_B_BLUE=104; BG_B_MAGENTA=105; BG_B_CYAN=106; BG_B_WHITE=107

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
        if t == "META":
            children = []
            for co in d.get('children', []):
                ce = UIElement.from_dict(co)
                if ce: children.append(ce)
            return MetaObject(
                name=str(d.get('name', 'group')),
                color=color,
                children=children,
                x=int(d.get('x', 0)),
                y=int(d.get('y', 0)),
                layer=layer
            )
        return None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['color'] = self.color.name
        if hasattr(self, 'children'):
            d['children'] = [c.to_dict() for c in getattr(self, 'children')]
        return d

@dataclass
class MetaObject(UIElement):
    x: int = 0; y: int = 0
    children: List[UIElement] = field(default_factory=list)
    type: str = "META"
    def cpp_struct_init(self) -> str:
        # For C++, we might just treat it as a container or flatten it.
        # Roadmap says generator provides layout data.
        return f'{{ {self.x}, {self.y} }}' # Simple placeholder for now

@dataclass
class Box(UIElement):
    x: int = 0; y: int = 0; w: int = 0; h: int = 0
    type: str = "BOX"
    def cpp_struct_init(self) -> str:
        return f'{{ {self.x}, {self.y}, {self.w}, {self.h}, UI_Color::{self.color.name} }}'

def c_escape(s: str) -> str:
    return s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\x1b', '\\x1b')

@dataclass
class Text(UIElement):
    x: int = 0; y: int = 0; content: str = ""
    type: str = "TEXT"
    def cpp_struct_init(self) -> str:
        return f'{{ {self.x}, {self.y}, "{c_escape(self.content)}", UI_Color::{self.color.name} }}'

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

# ------------------------------
# GuiManager (Tk in background thread)
# ------------------------------
class GuiManager:
    """
    Threaded Tk GUI. Provides:
      - queue: GUI -> Designer commands (button presses)
      - update_state(help_text, screen_names, active_screen): Designer calls to update lists & help text.
      - edit_text_blocking(initial, title) -> str | None
      - edit_props_blocking(obj) -> dict | None
    """

    def __init__(self, update_interval: float = 0.2):
        self.queue: "queue.Queue[tuple]" = queue.Queue()
        self._root: Optional[tk.Tk] = None
        self._lst_screens: Optional[tk.Listbox] = None
        self._lst_assets: Optional[tk.Listbox] = None
        self._help_text_widget: Optional[scrolledtext.ScrolledText] = None
        self.ready = threading.Event()
        self._lock = threading.Lock()
        self._last_update = 0.0
        self._last_screens: List[str] = []
        self._last_help: str = ""
        self._last_active: str = ""
        self._update_interval = update_interval
        # start thread
        self._thr = threading.Thread(target=self._run_tk, daemon=True)
        self._thr.start()

    def _run_tk(self):
        try:
            root = tk.Tk()
            self._root = root
            root.title("UI Helper")
            root.geometry("460x540")
            try:
                root.attributes('-topmost', True)
            except Exception:
                pass

            nb = ttk.Notebook(root)
            nb.pack(fill="both", expand=True)

            # Help tab
            f_help = tk.Frame(nb)
            nb.add(f_help, text="Help & Status")
            self._help_text_widget = scrolledtext.ScrolledText(f_help, font=("Consolas", 10), wrap="word", state="disabled", bg="#f0f0f0")
            self._help_text_widget.pack(fill="both", expand=True, padx=6, pady=6)

            # Screens
            f_scr = tk.Frame(nb)
            nb.add(f_scr, text="Screens")
            self._lst_screens = tk.Listbox(f_scr, height=8, exportselection=False)
            self._lst_screens.pack(fill="x", padx=6, pady=6)
            bf = tk.Frame(f_scr); bf.pack(fill="x", pady=4)
            tk.Button(bf, text="Switch To", command=lambda: self._emit("SWITCH_SCREEN")).pack(side="left", padx=6)
            tk.Button(bf, text="New Screen", command=lambda: self._emit("ADD_SCREEN")).pack(side="left")
            tk.Button(bf, text="Rename", command=lambda: self._emit("RENAME_SCREEN")).pack(side="left", padx=6)

            # Assets
            f_assets = tk.Frame(nb)
            nb.add(f_assets, text="Asset Library")
            self._lst_assets = tk.Listbox(f_assets, exportselection=False)
            self._lst_assets.pack(fill="both", expand=True, padx=6, pady=6)
            af = tk.Frame(f_assets); af.pack(fill="x", pady=4)
            tk.Button(af, text="Insert Selected", bg="#ddffdd", command=lambda: self._emit("INSERT_ASSET")).pack(side="left", padx=6)
            tk.Button(af, text="Delete Asset", command=self._delete_asset).pack(side="right", padx=6)

            # Bottom buttons
            bf2 = tk.Frame(root); bf2.pack(fill="x", side="bottom", padx=6, pady=6)
            tk.Button(bf2, text="COMPILE (Generate C++)", bg="#ccffcc", font=("Arial", 10, "bold"), command=lambda: self._emit("COMPILE")).pack(fill="x", pady=2)
            tk.Button(bf2, text="Save Selected Object to Library", bg="#ffeebb", command=lambda: self._emit("SAVE_ASSET")).pack(fill="x", pady=2)

            # mark ready and start Tk mainloop
            self.ready.set()
            self._refresh_assets()
            root.mainloop()
        except Exception as e:
            # If Tk cannot start (some platforms require main thread), signal ready and print error
            self.ready.set()
            print("Tk failed to initialize:", e)

    # small helpers
    def _listbox_items(self, lb: tk.Listbox) -> List[str]:
        try:
            return list(lb.get(0, tk.END))
        except Exception:
            return []

    def _emit(self, cmd: str):
        """Called on Tk thread by widget callbacks to send command to Designer"""
        data = None
        try:
            if cmd == "SWITCH_SCREEN":
                sel = self._lst_screens.curselection();
                if not sel: return
                data = self._lst_screens.get(sel[0])
            elif cmd == "ADD_SCREEN":
                data = simpledialog.askstring("New Screen", "Name:", parent=self._root)
            elif cmd == "RENAME_SCREEN":
                sel = self._lst_screens.curselection();
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
        # only push meaningful commands
        if data is not None or cmd == "SAVE_ASSET":
            try:
                self.queue.put((cmd, data))
            except Exception:
                pass

    # Asset helpers
    def _lib_path(self) -> Path:
        return Path("library.json")

    def _load_lib(self) -> Dict[str, Any]:
        try:
            p = self._lib_path()
            if not p.exists(): return {}
            txt = p.read_text(encoding="utf-8")
            return json.loads(txt) if txt else {}
        except Exception:
            return {}

    def _write_lib(self, lib: Dict[str, Any]):
        try:
            self._lib_path().write_text(json.dumps(lib, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _delete_asset(self):
        try:
            sel = self._lst_assets.curselection()
            if not sel: return
            key = self._lst_assets.get(sel[0])
            lib = self._load_lib()
            if key in lib:
                del lib[key]; self._write_lib(lib)
            self._refresh_assets()
        except Exception:
            pass

    def _refresh_assets(self):
        """Non-destructive asset list refresh on Tk thread"""
        if not self._root or not self._lst_assets:
            return
        try:
            lib = self._load_lib()
            keys = sorted(lib.keys())
            cur = self._listbox_items(self._lst_assets)
            if cur != keys:
                prev = None
                sel = self._lst_assets.curselection()
                if sel:
                    try: prev = self._lst_assets.get(sel[0])
                    except Exception: prev = None
                self._lst_assets.delete(0, tk.END)
                for k in keys: self._lst_assets.insert(tk.END, k)
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

    # Public API: update_state called by Designer
    def update_state(self, help_text: str, screens: List[str], active_screen: str):
        """
        Non-blocking: schedules a safe GUI update on Tk thread, rate-limited.
        Designer can call frequently; updates will be applied at most once per self._update_interval.
        """
        with self._lock:
            now = time.time()
            # quickly store requested values; apply on Tk thread
            self._last_help = help_text
            self._last_screens = list(screens)
            self._last_active = active_screen
            # if enough time passed, schedule an immediate update
            if now - self._last_update >= self._update_interval:
                self._last_update = now
                if self._root:
                    try:
                        self._root.after(0, self._apply_update)
                    except Exception:
                        pass
            else:
                # otherwise schedule a deferred update after the remaining time (only schedule one)
                delay = int((self._update_interval - (now - self._last_update)) * 1000)
                if self._root:
                    try:
                        self._root.after(delay, self._apply_update)
                        self._last_update = now + (delay / 1000.0)
                    except Exception:
                        pass

    def _apply_update(self):
        """Runs on Tk thread; apply the last requested state in a non-destructive, focus-aware way."""
        try:
            if not self._root:
                return
            # help text
            try:
                if self._help_text_widget:
                    self._help_text_widget.configure(state="normal")
                    self._help_text_widget.delete("1.0", tk.END)
                    self._help_text_widget.insert("1.0", self._last_help)
                    self._help_text_widget.configure(state="disabled")
            except Exception:
                pass

            # screens list: update only if different and if user is not actively focused on the list
            try:
                if self._lst_screens:
                    cur = self._listbox_items(self._lst_screens)
                    focused = (self._root.focus_get() is self._lst_screens)
                    if cur != self._last_screens and not focused:
                        # preserve selected name if possible
                        prev_sel = None
                        sel = self._lst_screens.curselection()
                        if sel:
                            try: prev_sel = self._lst_screens.get(sel[0])
                            except Exception: prev_sel = None
                        self._lst_screens.delete(0, tk.END)
                        for n in self._last_screens:
                            self._lst_screens.insert(tk.END, n)
                        # try to select active_screen if present
                        try:
                            if self._last_active in self._last_screens:
                                idx = self._last_screens.index(self._last_active)
                            else:
                                idx = 0 if self._last_screens else None
                            if idx is not None:
                                self._lst_screens.selection_clear(0, tk.END)
                                self._lst_screens.selection_set(idx)
                                self._lst_screens.see(idx)
                        except Exception:
                            pass
                    else:
                        # if same items but active changed, update selection if not focused
                        if cur == self._last_screens and not focused and self._last_screens:
                            try:
                                if self._last_active in self._last_screens:
                                    idx = self._last_screens.index(self._last_active)
                                else:
                                    idx = 0
                                self._lst_screens.selection_clear(0, tk.END)
                                self._lst_screens.selection_set(idx)
                                self._lst_screens.see(idx)
                            except Exception:
                                pass
            except Exception:
                pass

            # assets list refresh (it preserves selection internally)
            try:
                self._refresh_assets()
            except Exception:
                pass

        except Exception:
            pass

    def _setup_ansi_tags(self, txt):
        palette = {
            "0":"#000000", "1":"#aa0000", "2":"#00aa00", "3":"#aa5500", "4":"#0000aa", "5":"#aa00aa", "6":"#00aaaa", "7":"#aaaaaa",
            "8":"#555555", "9":"#ff5555", "10":"#55ff55", "11":"#ffff55", "12":"#5555ff", "13":"#ff55ff", "14":"#55ffff", "15":"#ffffff"
        }
        for i, h in palette.items():
            txt.tag_configure(f"ansi_fg_{i}", foreground=h)
            txt.tag_configure(f"ansi_bg_{i}", background=h)
        txt.tag_configure("ansi_bold", font=("Courier", 10, "bold"))
        txt.tag_configure("ansi_dim", foreground="#666666")
        txt.tag_configure("ansi_italic", font=("Courier", 10, "italic"))
        txt.tag_configure("ansi_underline", underline=True)
        txt.tag_configure("ansi_blink", overstrike=True)
        txt.tag_configure("ansi_code", elide=True, foreground="#777777")

    def _apply_ansi_highlight(self, txt):
        content = txt.get("1.0", "end-1c")
        for tag in txt.tag_names():
            if tag.startswith("ansi"): txt.tag_remove(tag, "1.0", tk.END)

        ms = list(re.finditer(r'\x1b\[([0-9;]*)m', content))
        cfg, cbg = "15", None
        cb, cd, ci, cu, cbl = False, False, False, False, False

        if not ms or ms[0].start() > 0:
            end_pos = ms[0].start() if ms else len(content)
            txt.tag_add("ansi_fg_15", "1.0", f"1.0 + {end_pos} chars")

        for i, m in enumerate(ms):
            txt.tag_add("ansi_code", f"1.0 + {m.start()} chars", f"1.0 + {m.end()} chars")
            for c in m.group(1).split(';'):
                if c == "0" or c == "":
                    cfg, cbg = "15", None
                    cb, cd, ci, cu, cbl = False, False, False, False, False
                elif c == "1": cb = True
                elif c == "2": cd = True
                elif c == "3": ci = True
                elif c == "4": cu = True
                elif c == "5": cbl = True
                elif "30"<=c<="37": cfg = str(int(c)-30)
                elif "90"<=c<="97": cfg = str(int(c)-90+8)
                elif "40"<=c<="47": cbg = str(int(c)-40)
                elif "100"<=c<="107": cbg = str(int(c)-100+8)

            ts, te = m.end(), (ms[i+1].start() if i+1 < len(ms) else len(content))
            if ts < te:
                ids, ide = f"1.0 + {ts} chars", f"1.0 + {te} chars"
                txt.tag_add(f"ansi_fg_{cfg}", ids, ide)
                if cbg: txt.tag_add(f"ansi_bg_{cbg}", ids, ide)
                if cb: txt.tag_add("ansi_bold", ids, ide)
                if cd: txt.tag_add("ansi_dim", ids, ide)
                if ci: txt.tag_add("ansi_italic", ids, ide)
                if cu: txt.tag_add("ansi_underline", ids, ide)
                if cbl: txt.tag_add("ansi_blink", ids, ide)

    def _smart_ins(self, txt, code):
        try:
            if txt.tag_ranges(tk.SEL):
                start, end = txt.index(tk.SEL_FIRST), txt.index(tk.SEL_LAST)
                txt.insert(end, "\x1b[0m")
                txt.insert(start, code)
            else:
                # Check if we are right after another escape code to avoid piling
                cur = txt.index(tk.INSERT)
                prev_text = txt.get(f"{cur}-10c", cur)
                m = re.search(r'\x1b\[[0-9;]*m$', prev_text)
                if m:
                    # Replace previous code if it was just there
                    txt.delete(f"{cur}-{len(m.group(0))}c", cur)
                txt.insert(tk.INSERT, code)
        except Exception:
            txt.insert(tk.INSERT, code)
        self._apply_ansi_highlight(txt)

    def _create_ansi_toolbar(self, parent, text_widget):
        frame = tk.Frame(parent)
        nb = ttk.Notebook(frame)
        nb.pack(fill="x", expand=True)

        palette_fg = ["BLACK", "RED", "GREEN", "YELLOW", "BLUE", "MAGENTA", "CYAN", "WHITE"]
        palette_hex = ["#000000", "#aa0000", "#00aa00", "#aa5500", "#0000aa", "#aa00aa", "#00aaaa", "#aaaaaa"]
        bright_hex = ["#555555", "#ff5555", "#55ff55", "#ffff55", "#5555ff", "#ff55ff", "#55ffff", "#ffffff"]

        attr_names = ["Normal (0)", "Bold (1)", "Dim (2)", "Italic (3)", "Underline (4)", "Blink (5)"]
        for attr_idx in range(6):
            tab = tk.Frame(nb); nb.add(tab, text=attr_names[attr_idx])
            for row_idx, (start_code, hex_list, label) in enumerate([
                (30, palette_hex, "FG"), (40, palette_hex, "BG"),
                (90, bright_hex, "FG-B"), (100, bright_hex, "BG-B")
            ]):
                r = tk.Frame(tab); r.pack(fill="x")
                tk.Label(r, text=label+":", width=4, font=("Arial", 6)).pack(side="left")
                for i in range(8):
                    code = f"\x1b[{attr_idx};{start_code+i}m"
                    bg_c = hex_list[i]
                    fg_c = "#ffffff" if bg_c in ("#000000", "#aa0000", "#0000aa", "#555555") else "#000000"
                    tk.Button(r, bg=bg_c, fg=fg_c, text=str(i), width=1, height=1, font=("Arial", 6),
                              command=lambda c=code: self._smart_ins(text_widget, c)).pack(side="left", padx=1)

        ctrl = tk.Frame(frame); ctrl.pack(fill="x", pady=2)
        tk.Button(ctrl, text="RESET (\\e[0m)", font=("Arial", 7, "bold"), command=lambda: self._smart_ins(text_widget, "\x1b[0m")).pack(side="left", padx=4)
        tk.Button(ctrl, text="Re-Highlight", font=("Arial", 7), command=lambda: self._apply_ansi_highlight(text_widget)).pack(side="right")
        return frame

    # Blocking editors (Designer calls)
    def edit_text_blocking(self, initial: str = "", title: str = "Edit Text") -> Optional[str]:
        """Open modal multiline text editor on Tk thread; return str or None."""
        if not self.ready.is_set() or not self._root: return initial
        result: Dict[str, Optional[str]] = {"value": None}
        ev = threading.Event()

        def open_dialog():
            dlg = tk.Toplevel(self._root); dlg.title(title); dlg.geometry("700x540"); dlg.transient(self._root)
            nb = ttk.Notebook(dlg); nb.pack(fill="both", expand=True, padx=6, pady=6)

            # Visual Tab
            f_v = tk.Frame(nb); nb.add(f_v, text="Visual Editor")
            txt_v = scrolledtext.ScrolledText(f_v, wrap="none", font=("Courier", 10), bg="#222222", fg="#ffffff", insertbackground="white")
            self._setup_ansi_tags(txt_v)
            txt_v.bind("<KeyRelease>", lambda e: self._apply_ansi_highlight(txt_v))
            txt_v.bind("<<Paste>>", lambda e: self._root.after(10, lambda: self._apply_ansi_highlight(txt_v)))
            self._create_ansi_toolbar(f_v, txt_v).pack(fill="x")
            txt_v.pack(fill="both", expand=True); txt_v.insert("1.0", initial); self._apply_ansi_highlight(txt_v)

            # Raw Tab
            f_r = tk.Frame(nb); nb.add(f_r, text="Raw Code (Paste Art Here)")
            txt_r = scrolledtext.ScrolledText(f_r, wrap="none", font=("Courier", 10))
            txt_r.pack(fill="both", expand=True)

            def sync(to_visual):
                if to_visual:
                    c = txt_r.get("1.0", "end-1c")
                    txt_v.delete("1.0", tk.END); txt_v.insert("1.0", c); self._apply_ansi_highlight(txt_v)
                else:
                    c = txt_v.get("1.0", "end-1c")
                    txt_r.delete("1.0", tk.END); txt_r.insert("1.0", c)

            nb.bind("<<NotebookTabChanged>>", lambda e: sync(nb.index(nb.select())==0))

            def ok():
                sync(False) # Ensure raw has latest
                try: result["value"] = txt_r.get("1.0", "end-1c")
                except Exception: result["value"] = ""
                try: dlg.grab_release()
                except Exception: pass
                dlg.destroy(); ev.set()

            def cancel():
                result["value"] = None
                try: dlg.grab_release()
                except Exception: pass
                dlg.destroy(); ev.set()

            dlg.protocol("WM_DELETE_WINDOW", cancel)
            btnf = tk.Frame(dlg); btnf.pack(fill="x", padx=6, pady=6)
            tk.Button(btnf, text="OK", command=ok).pack(side="left", padx=6)
            tk.Button(btnf, text="Cancel", command=cancel).pack(side="left", padx=6)

            try:
                dlg.grab_set(); dlg.focus_force()
            except Exception:
                pass

        # schedule
        try:
            self._root.after(0, open_dialog)
        except Exception:
            return None
        # wait until dialog sets event
        ev.wait()
        return result["value"]

    def edit_props_blocking(self, obj: UIElement) -> Optional[Dict[str, Any]]:
        """Open properties editor on Tk thread; return props dict or None."""
        if not self.ready.is_set() or not self._root:
            return None
        result: Dict[str, Optional[Dict[str, Any]]] = {"props": None}
        ev = threading.Event()

        def open_dialog():
            dlg = tk.Toplevel(self._root)
            dlg.title(f"Edit: {obj.name} ({obj.type})")
            dlg.geometry("460x360")
            dlg.transient(self._root)

            frm = tk.Frame(dlg); frm.pack(fill="both", expand=True, padx=6, pady=6)
            entries: Dict[str, tk.Entry] = {}
            row = 0

            def add_entry(label_text: str, key: str, init_val: str):
                nonlocal row
                tk.Label(frm, text=label_text).grid(row=row, column=0, sticky="w")
                ent = tk.Entry(frm)
                ent.grid(row=row, column=1, sticky="ew", padx=4, pady=2)
                ent.insert(0, str(init_val))
                entries[key] = ent
                row += 1

            add_entry("Name", "name", obj.name)
            add_entry("Layer", "layer", obj.layer)
            tk.Label(frm, text="Color").grid(row=row, column=0, sticky="w")
            color_var = tk.StringVar(value=obj.color.name if hasattr(obj, "color") else "WHITE")
            color_combo = ttk.Combobox(frm, values=Color.names(), textvariable=color_var, state="readonly")
            color_combo.grid(row=row, column=1, sticky="ew", padx=4, pady=2)
            row += 1

            if isinstance(obj, Box):
                add_entry("X", "x", obj.x); add_entry("Y", "y", obj.y)
                add_entry("W", "w", obj.w); add_entry("H", "h", obj.h)
            elif isinstance(obj, Line):
                add_entry("X1", "x1", obj.x1); add_entry("Y1", "y1", obj.y1)
                add_entry("X2", "x2", obj.x2); add_entry("Y2", "y2", obj.y2)
            elif isinstance(obj, (Text, Freehand)):
                tk.Label(frm, text="Content" if isinstance(obj, Text) else "Lines").grid(row=row, column=0, sticky="nw")
                nb_inner = ttk.Notebook(frm); nb_inner.grid(row=row, column=1, sticky="ew", padx=4, pady=2)
                # Visual
                f_v = tk.Frame(nb_inner); nb_inner.add(f_v, text="Visual")
                txt_v = scrolledtext.ScrolledText(f_v, height=10, width=40, font=("Courier", 10), bg="#222222", fg="#ffffff", insertbackground="white")
                self._setup_ansi_tags(txt_v)
                txt_v.bind("<KeyRelease>", lambda e: self._apply_ansi_highlight(txt_v))
                txt_v.bind("<<Paste>>", lambda e: self._root.after(10, lambda: self._apply_ansi_highlight(txt_v)))
                self._create_ansi_toolbar(f_v, txt_v).pack(fill="x")
                txt_v.pack(fill="both", expand=True)
                # Raw
                f_r = tk.Frame(nb_inner); nb_inner.add(f_r, text="Raw")
                txt_r = scrolledtext.ScrolledText(f_r, height=10, width=40, font=("Courier", 10))
                txt_r.pack(fill="both", expand=True)

                init_content = obj.content if isinstance(obj, Text) else "\n".join(obj.lines)
                txt_v.insert("1.0", init_content); self._apply_ansi_highlight(txt_v)

                def sync_inner(to_v):
                    if to_v:
                        c = txt_r.get("1.0", "end-1c")
                        txt_v.delete("1.0", tk.END); txt_v.insert("1.0", c); self._apply_ansi_highlight(txt_v)
                    else:
                        c = txt_v.get("1.0", "end-1c")
                        txt_r.delete("1.0", tk.END); txt_r.insert("1.0", c)

                nb_inner.bind("<<NotebookTabChanged>>", lambda e: sync_inner(nb_inner.index(nb_inner.select())==0))
                row += 1

            frm.grid_columnconfigure(1, weight=1)

            def on_ok():
                props: Dict[str, Any] = {}
                try: props['name'] = entries.get('name').get().strip() if 'name' in entries else obj.name
                except Exception: props['name'] = obj.name
                try: props['layer'] = int(entries['layer'].get()) if 'layer' in entries else obj.layer
                except Exception: pass
                props['color'] = color_var.get()
                try:
                    if isinstance(obj, Box):
                        props['x'] = int(entries['x'].get()); props['y'] = int(entries['y'].get())
                        props['w'] = int(entries['w'].get()); props['h'] = int(entries['h'].get())
                    elif isinstance(obj, Line):
                        props['x1'] = int(entries['x1'].get()); props['y1'] = int(entries['y1'].get())
                        props['x2'] = int(entries['x2'].get()); props['y2'] = int(entries['y2'].get())
                    elif isinstance(obj, (Text, Freehand)):
                        sync_inner(False)
                        raw = txt_r.get("1.0", "end-1c")
                        if isinstance(obj, Text): props['content'] = raw
                        else: props['lines'] = [ln.rstrip("\n") for ln in raw.splitlines()]
                except Exception: pass
                result['props'] = props
                try: dlg.grab_release()
                except Exception: pass
                dlg.destroy(); ev.set()

            def on_cancel():
                result['props'] = None
                try: dlg.grab_release()
                except Exception: pass
                dlg.destroy(); ev.set()

            dlg.protocol("WM_DELETE_WINDOW", on_cancel)
            btnf = tk.Frame(dlg); btnf.pack(fill="x", padx=6, pady=6)
            tk.Button(btnf, text="OK", command=on_ok).pack(side="left", padx=6)
            tk.Button(btnf, text="Cancel", command=on_cancel).pack(side="left", padx=6)

            try:
                dlg.grab_set(); dlg.focus_force()
            except Exception:
                pass

        # schedule and wait
        try:
            self._root.after(0, open_dialog)
        except Exception:
            return None
        ev.wait()
        return result["props"]

# ------------------------------
# ProjectManager: save/load/generate
# ------------------------------
class ProjectManager:
    H_FILE = "ui_layout.h"
    CPP_FILE = "ui_layout.cpp"
    LIB_FILE = "SerialUI.h"

    def __init__(self, project_file: str = "project.uiproj"):
        self.project_file = project_file

    def ensure_lib(self):
        try:
            Path(self.LIB_FILE).write_text(SERIAL_UI_HEADER, encoding="utf-8")
        except Exception:
            pass

    def _flatten(self, objs: List[UIElement], bx=0, by=0, prefix="") -> List[UIElement]:
        res = []
        for o in objs:
            if isinstance(o, MetaObject):
                res.extend(self._flatten(o.children, bx+o.x, by+o.y, prefix+o.name+"_"))
            else:
                import copy
                no = copy.copy(o); no.name = prefix+o.name
                if hasattr(no, 'x'): no.x += bx; no.y += by
                if hasattr(no, 'x1'): no.x1 += bx; no.y1 += by; no.x2 += bx; no.y2 += by
                res.append(no)
        return res

    def save_project(self, screens: List[Screen]):
        self.ensure_lib()
        try:
            h = ['#ifndef UI_LAYOUT_H', '#define UI_LAYOUT_H', '#include "SerialUI.h"', '']
            all_flat = {s.name: self._flatten(s.objects) for s in screens}
            for s_name, objs in all_flat.items():
                h.append(f'struct Layout_{s_name} {{')
                for o in objs:
                    h.append(f'    static const UI_{o.type.capitalize()} {o.name};')
                h.append('};'); h.append(f'void drawScreen_{s_name}(SerialUI& ui);'); h.append('')
            h.append('#endif')
            Path(self.H_FILE).write_text("\n".join(h), encoding="utf-8")

            cpp = ['#include "ui_layout.h"', '', '// RESOURCES']
            processed_fh = set()
            for objs in all_flat.values():
                for o in objs:
                    if isinstance(o, Freehand) and o.name not in processed_fh:
                        processed_fh.add(o.name)
                        for i, line in enumerate(o.lines):
                            cpp.append(f'const char RES_{o.name}_L{i}[] PROGMEM = "{c_escape(line)}";')
                        arr = ", ".join([f"RES_{o.name}_L{i}" for i in range(len(o.lines))])
                        cpp.append(f'const char* const RES_{o.name}_ARR[] PROGMEM = {{ {arr} }};\n')
            cpp.append('// IMPLEMENTATION')
            for s_name, objs in all_flat.items():
                for o in objs:
                    cpp.append(f'const UI_{o.type.capitalize()} Layout_{s_name}::{o.name} = {o.cpp_struct_init()};')
                cpp.append(f'\nvoid drawScreen_{s_name}(SerialUI& ui) {{')
                for o in objs:
                    cpp.append(f'    ui.draw(Layout_{s_name}::{o.name});')
                cpp.append('}\n')
            Path(self.CPP_FILE).write_text("\n".join(cpp), encoding="utf-8")
        except Exception as e: raise

    def load_project(self) -> List[Screen]:
        try:
            p = Path(self.project_file)
            if not p.exists(): return [Screen("Main")]
            txt = p.read_text(encoding="utf-8")
            data = json.loads(txt) if txt else []
            screens: List[Screen] = []
            for s in data:
                scr = Screen(s.get('name', 'Main'))
                for o in s.get('objects', []):
                    elem = UIElement.from_dict(o)
                    if elem:
                        scr.objects.append(elem)
                screens.append(scr)
            return screens if screens else [Screen("Main")]
        except Exception:
            return [Screen("Main")]

    def save_json_state(self, screens: List[Screen]):
        try:
            data = [{'name': s.name, 'objects': [o.to_dict() for o in s.objects]} for s in screens]
            Path(self.project_file).write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

# ------------------------------
# Designer (curses)
# ------------------------------
class Mode(Enum):
    NAV = auto(); BOX_1 = auto(); BOX_2 = auto(); LINE_1 = auto(); LINE_2 = auto(); RESIZE = auto(); GROUP = auto()

class Designer:
    def __init__(self, stdscr, project_file: str):
        self.stdscr = stdscr
        self.pm = ProjectManager(project_file)
        self.screens = self.pm.load_project()
        self.act_idx = 0
        self.mode = Mode.NAV
        self.cx = 5; self.cy = 5
        self.sel_idx = -1
        self.edit_stack: List[MetaObject] = []
        self.group_selection: set[int] = set()
        self.temp: Dict[str, int] = {}
        self.gui = GuiManager(update_interval=0.20)
        self.gui.ready.wait(3)
        self.msg = "Welcome."
        if not self.screens:
            self.screens = [Screen("Main")]

    @property
    def cur_screen(self) -> Screen:
        if 0 <= self.act_idx < len(self.screens):
            return self.screens[self.act_idx]
        self.act_idx = 0
        return self.screens[0]

    @property
    def cur_objs(self) -> List[UIElement]:
        if self.edit_stack:
            return self.edit_stack[-1].children
        return self.cur_screen.objects

    def _valid_sel(self) -> bool:
        return 0 <= self.sel_idx < len(self.cur_objs)

    def _get_detailed_help(self) -> str:
        h = [f"STATUS: {self.msg}", ""]
        if self.mode == Mode.NAV:
            h.append("--- NAVIGATION MODE ---")
            h.append("Arrows: Move cursor")
            h.append("Tab: Cycle selection")
            h.append("b / l / t: Create Box / Line / Text")
            if self._valid_sel():
                o = self.cur_objs[self.sel_idx]
                h.append(f"\nSELECTED: {o.name} ({o.type})")
                h.append("  Arrows: Move object")
                h.append("  e: Edit properties (Tk window)")
                h.append("  n: Rename object")
                h.append("  c: Cycle color")
                h.append("  d: Delete selected")
                h.append("  r: Resize mode")
                h.append("  + / - or [ / ]: Change Layer (order)")
                h.append("  g: Start Grouping with this item")
                if isinstance(o, MetaObject):
                    h.append("  u: Ungroup")
                    h.append("  o: Open group for internal editing")
            h.append("\ns: Save Project")
            h.append("q: Quit")
        elif self.mode == Mode.GROUP:
            h.append("--- GROUPING MODE ---")
            h.append("Tab: Cycle selection")
            h.append("Space: Toggle item in group")
            h.append("Enter: Confirm Group")
            h.append("Esc: Cancel")
        elif self.mode == Mode.RESIZE:
            h.append("--- RESIZE MODE ---")
            h.append("Arrows: Resize selected object")
            h.append("Esc: Finish/Cancel")
        elif self.mode in (Mode.BOX_1, Mode.BOX_2, Mode.LINE_1, Mode.LINE_2):
            h.append("--- CREATION MODE ---")
            h.append("Arrows: Move cursor")
            h.append("Enter: Set point")
            h.append("Esc: Cancel")

        if self.edit_stack:
            h.append("")
            h.append("--- META EDITING ---")
            h.append(f"Inside: {self.edit_stack[-1].name}")
            h.append("Esc: Exit to parent")
        return "\n".join(h)

    def _update_gui(self):
        try:
            self.gui.update_state(self._get_detailed_help(), [s.name for s in self.screens], self.cur_screen.name)
        except Exception:
            pass

    def _clamp_sel(self):
        if not self.cur_objs:
            self.sel_idx = -1
        elif self.sel_idx >= len(self.cur_objs):
            self.sel_idx = len(self.cur_objs) - 1
        elif self.sel_idx < 0:
            self.sel_idx = -1

    def run(self):
        curses.start_color(); curses.use_default_colors()
        try: curses.curs_set(1)
        except Exception: pass
        for i, c in enumerate(Color, 1):
            try:
                cn = c.name; fg, bg = curses.COLOR_WHITE, -1
                if cn.startswith("BG_B_"): bg = getattr(curses, f"COLOR_{cn[5:]}", curses.COLOR_BLACK)
                elif cn.startswith("BG_"): bg = getattr(curses, f"COLOR_{cn[3:]}", curses.COLOR_BLACK)
                elif cn.startswith("B_"): fg = getattr(curses, f"COLOR_{cn[2:]}", curses.COLOR_WHITE)
                else: fg = getattr(curses, f"COLOR_{cn}", curses.COLOR_WHITE)
                curses.init_pair(i, fg, bg)
            except Exception: pass
        self.stdscr.nodelay(True)

        # initial GUI sync
        self._update_gui()

        while True:
            self._clamp_sel()
            self._draw()
            self._process_gui_queue()
            try: key = self.stdscr.getch()
            except Exception:
                key = -1
            if key == -1:
                curses.napms(20)
                continue
            if not self._handle_key(key):
                break
            self._update_gui()

    def _process_gui_queue(self):
        try:
            while True:
                cmd, data = self.gui.queue.get_nowait()
                if cmd == "SWITCH_SCREEN":
                    for i, s in enumerate(self.screens):
                        if s.name == data:
                            self.act_idx = i; self.sel_idx = -1; self.msg = f"Switched to {s.name}"
                elif cmd == "ADD_SCREEN":
                    if data:
                        safe = re.sub(r'[^a-zA-Z0-9_]', '', data) or "Screen"
                        self.screens.append(Screen(safe)); self.act_idx = len(self.screens)-1; self.sel_idx = -1; self.msg = f"Added {safe}"
                elif cmd == "RENAME_SCREEN":
                    if data:
                        old, new = data
                        safe = re.sub(r'[^a-zA-Z0-9_]', '', new) or old
                        for s in self.screens:
                            if s.name == old:
                                s.name = safe; self.msg = f"Renamed {old}->{safe}"
                elif cmd == "SAVE_ASSET":
                    if self._valid_sel() and data:
                        o = self.cur_objs[self.sel_idx]; lib = self.gui._load_lib()
                        d = o.to_dict(); d['name'] = data; lib[data] = d; self.gui._write_lib(lib)
                        if self.gui._root:
                            try: self.gui._root.after(0, self.gui._refresh_assets)
                            except Exception: pass
                        self.msg = f"Saved asset '{data}'"
                elif cmd == "COMPILE":
                    try:
                        self.pm.save_project(self.screens); self.pm.save_json_state(self.screens)
                        self.msg = "Project COMPILED and Saved"
                    except Exception as e:
                        self.msg = f"Compile error: {e}"
                elif cmd == "INSERT_ASSET":
                    lib = self.gui._load_lib()
                    if data in lib:
                        new_obj = UIElement.from_dict(lib[data])
                        if new_obj:
                            if hasattr(new_obj, 'x') and hasattr(new_obj, 'y'):
                                new_obj.x = self.cx; new_obj.y = self.cy
                            if isinstance(new_obj, Line):
                                w = new_obj.x2 - new_obj.x1; h = new_obj.y2 - new_obj.y1
                                new_obj.x1 = self.cx; new_obj.y1 = self.cy; new_obj.x2 = self.cx + w; new_obj.y2 = self.cy + h
                            if isinstance(new_obj, Freehand):
                                new_obj.x = self.cx; new_obj.y = self.cy
                            # unique name
                            base = new_obj.name or "asset"; used = {o.name for o in self.cur_objs}; cnt = 1
                            while new_obj.name in used or not new_obj.name:
                                new_obj.name = f"{base}_{cnt}"; cnt += 1
                            self.cur_objs.append(new_obj); self.sel_idx = len(self.cur_objs)-1; self.msg = f"Inserted {new_obj.name}"
                self._update_gui()
        except queue.Empty:
            pass

    def _handle_key(self, k: int) -> bool:
        if k == 27:
            if self.edit_stack:
                self.edit_stack.pop(); self.sel_idx = -1; self.msg = "Returned"
            else:
                self.mode = Mode.NAV; self.sel_idx = -1; self.msg = "Cancelled"
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
            elif self.mode == Mode.RESIZE and self._valid_sel():
                o = self.cur_objs[self.sel_idx]
                if isinstance(o, Box):
                    o.w = max(1, o.w + dx)
                    o.h = max(1, o.h + dy)
                elif isinstance(o, Line):
                    o.x2 += dx
                    o.y2 += dy
            else:
                self.cx += dx; self.cy += dy
                h, w = self.stdscr.getmaxyx()
                self.cx = max(0, min(w-1, self.cx)); self.cy = max(0, min(h-2, self.cy))
            return True

        if self.mode == Mode.NAV:
            if k == ord('q'): return False
            if k == ord('s'):
                try:
                    self.pm.save_project(self.screens); self.pm.save_json_state(self.screens); self.msg = "Saved project"
                except Exception as e:
                    self.msg = f"Save failed: {e}"
                return True
            if k == 9:  # Tab
                if self.cur_objs:
                    self.sel_idx = 0 if self.sel_idx < 0 else (self.sel_idx + 1) % len(self.cur_objs)
            if k == ord('b'):
                self.mode = Mode.BOX_1; self.msg = "Box: set start -> Enter"
            if k == ord('l'):
                self.mode = Mode.LINE_1; self.msg = "Line: set start -> Enter"
            if k == ord('t'):
                self._create_text()
            if k == ord('r') and self._valid_sel():
                self.mode = Mode.RESIZE
                self.msg = "RESIZE mode: Arrows to resize, ESC to exit"
            if k == ord('d') and self._valid_sel():
                try: self.cur_objs.pop(self.sel_idx)
                except Exception: pass
                self.sel_idx = -1; self.msg = "Deleted object"
            if k == ord('c') and self._valid_sel():
                o = self.cur_objs[self.sel_idx]; cl = list(Color)
                try: idx = cl.index(o.color)
                except Exception: idx = 0
                o.color = cl[(idx + 1) % len(cl)]; self.msg = "Color changed"
            if k == ord('n') and self._valid_sel():
                self._rename_obj()
            if k == ord('e') and self._valid_sel():
                target = self.cur_objs[self.sel_idx]
                try:
                    target.layer = self.sel_idx
                    props = self.gui.edit_props_blocking(target)
                except Exception:
                    props = None
                if props is not None:
                    try:
                        nm = props.get('name', target.name); nm_safe = re.sub(r'[^a-zA-Z0-9_]', '', nm) or target.name
                        target.name = nm_safe
                        target.color = Color.from_str(props.get('color', target.color.name))
                        if 'layer' in props:
                            new_layer = max(0, min(len(self.cur_objs)-1, int(props['layer'])))
                            if new_layer != self.sel_idx:
                                obj = self.cur_objs.pop(self.sel_idx)
                                self.cur_objs.insert(new_layer, obj)
                                self.sel_idx = new_layer
                        if isinstance(target, Box):
                            target.x = int(props.get('x', target.x)); target.y = int(props.get('y', target.y))
                            target.w = max(1, int(props.get('w', target.w))); target.h = max(1, int(props.get('h', target.h)))
                        if isinstance(target, Line):
                            target.x1 = int(props.get('x1', target.x1)); target.y1 = int(props.get('y1', target.y1))
                            target.x2 = int(props.get('x2', target.x2)); target.y2 = int(props.get('y2', target.y2))
                        if isinstance(target, Text):
                            target.content = str(props.get('content', target.content))
                        if isinstance(target, Freehand):
                            lines = props.get('lines', target.lines)
                            if isinstance(lines, list): target.lines = lines
                            else: target.lines = str(lines).splitlines()
                        self.msg = f"Updated {target.name}"
                    except Exception as e:
                        self.msg = f"Edit failed: {e}"
            # grouping
            if k == ord('g'):
                self.mode = Mode.GROUP; self.group_selection = {self.sel_idx} if self._valid_sel() else set()
                self.msg = "GROUP mode: SPACE to toggle, ENTER to confirm, ESC to cancel"
            if k == ord('u') and self._valid_sel():
                self._do_ungroup()

            if (k == ord('+') or k == ord('=')) and self._valid_sel() and self.sel_idx < len(self.cur_objs) - 1:
                idx = self.sel_idx
                self.cur_objs[idx], self.cur_objs[idx+1] = self.cur_objs[idx+1], self.cur_objs[idx]
                self.sel_idx += 1; self.msg = "Layer UP"
            if (k == ord('-') or k == ord('_')) and self._valid_sel() and self.sel_idx > 0:
                idx = self.sel_idx
                self.cur_objs[idx], self.cur_objs[idx-1] = self.cur_objs[idx-1], self.cur_objs[idx]
                self.sel_idx -= 1; self.msg = "Layer DOWN"
            if k == ord('o') and self._valid_sel():
                o = self.cur_objs[self.sel_idx]
                if isinstance(o, MetaObject):
                    self.edit_stack.append(o); self.sel_idx = -1; self.msg = f"Editing {o.name}"
            # layer controls
            if k == ord('[') and self._valid_sel() and self.sel_idx > 0:
                self.cur_objs[self.sel_idx - 1], self.cur_objs[self.sel_idx] = self.cur_objs[self.sel_idx], self.cur_objs[self.sel_idx - 1]
                self.sel_idx -= 1; self.msg = "Moved back"
            if k == ord(']') and self._valid_sel() and self.sel_idx < len(self.cur_objs) - 1:
                self.cur_objs[self.sel_idx + 1], self.cur_objs[self.sel_idx] = self.cur_objs[self.sel_idx], self.cur_objs[self.sel_idx + 1]
                self.sel_idx += 1; self.msg = "Moved forward"

            return True

        if self.mode == Mode.GROUP:
            if k == ord(' '):
                if self.sel_idx in self.group_selection: self.group_selection.remove(self.sel_idx)
                else: self.group_selection.add(self.sel_idx)
            elif k in (10, 13):
                self._do_group()
            elif k == 9: # Tab
                if self.cur_objs: self.sel_idx = (self.sel_idx + 1) % len(self.cur_objs)
            return True

        # creation flows
        if self.mode == Mode.BOX_1 and k in (10, 13):
            self.temp = {'x': self.cx, 'y': self.cy}; self.mode = Mode.BOX_2; self.msg = "Box: set end -> Enter"
        elif self.mode == Mode.BOX_2 and k in (10, 13):
            x = min(self.temp['x'], self.cx); y = min(self.temp['y'], self.cy)
            w = abs(self.temp['x'] - self.cx) + 1; h = abs(self.temp['y'] - self.cy) + 1
            name = f"box_{len(self.cur_objs)}"
            new = Box(name=name, color=Color.WHITE, x=x, y=y, w=w, h=h, layer=len(self.cur_objs))
            self.cur_objs.append(new); self.sel_idx = len(self.cur_objs) - 1; self.mode = Mode.NAV; self.msg = f"Created {name}"
        elif self.mode == Mode.LINE_1 and k in (10, 13):
            self.temp = {'x': self.cx, 'y': self.cy}; self.mode = Mode.LINE_2; self.msg = "Line: set end -> Enter"
        elif self.mode == Mode.LINE_2 and k in (10, 13):
            name = f"line_{len(self.cur_objs)}"
            new = Line(name=name, color=Color.WHITE, x1=self.temp['x'], y1=self.temp['y'], x2=self.cx, y2=self.cy, layer=len(self.cur_objs))
            self.cur_objs.append(new); self.sel_idx = len(self.cur_objs) - 1; self.mode = Mode.NAV; self.msg = f"Created {name}"

        return True

    def _create_text(self):
        try:
            txt = self.gui.edit_text_blocking("", title="New multiline Text")
        except Exception:
            txt = None
        if txt is None:
            self.msg = "Text creation cancelled"
            return
        name = f"txt_{len(self.cur_objs)}"
        new = Text(name=name, color=Color.WHITE, x=self.cx, y=self.cy, content=str(txt), layer=len(self.cur_objs))
        self.cur_objs.append(new); self.sel_idx = len(self.cur_objs) - 1; self.msg = f"Added {name}"

    def _rename_obj(self):
        curses.echo()
        try:
            self.stdscr.addstr(0, 0, "New Name: "); t = self.stdscr.getstr().decode('utf-8')
        except Exception:
            t = ""
        finally:
            curses.noecho()
        if t and self._valid_sel():
            safe = re.sub(r'[^a-zA-Z0-9_]', '', t)
            if safe:
                self.cur_objs[self.sel_idx].name = safe; self.msg = f"Renamed to {safe}"

    def _add_ansi_str(self, y: int, x: int, s: str, default_attr: int):
        parts = re.split(r'(\x1b\[[0-9;]*m)', s)
        cur_x, cur_attr = x, default_attr
        for part in parts:
            if not part: continue
            if part.startswith('\x1b['):
                m = re.match(r'\x1b\[([0-9;]*)m', part)
                if m:
                    codes = m.group(1).split(';')
                    if '0' in codes or not m.group(1):
                        cur_attr = default_attr
                    for c in codes:
                        if c == "1": cur_attr |= curses.A_BOLD
                        elif c == "2": cur_attr |= curses.A_DIM
                        elif c == "4": cur_attr |= curses.A_UNDERLINE
                        elif c == "5": cur_attr |= curses.A_BLINK
                        try:
                            if c == "3": cur_attr |= curses.A_ITALIC
                        except: pass
                        try:
                            v = int(c)
                            if (30<=v<=37) or (40<=v<=47) or (90<=v<=97) or (100<=v<=107):
                                for col in Color:
                                    if col.value == v:
                                        color_idx = list(Color).index(col) + 1
                                        cur_attr = (cur_attr & ~curses.A_COLOR) | curses.color_pair(color_idx)
                                        break
                        except: pass
            else:
                try:
                    self.stdscr.addstr(y, cur_x, part, cur_attr)
                    cur_x += len(part)
                except curses.error: break

    def _do_group(self):
        if not self.group_selection:
            self.mode = Mode.NAV; self.msg = "No items selected"; return
        objs = [self.cur_objs[i] for i in sorted(self.group_selection)]
        min_x = min_y = 999
        for o in objs:
            if hasattr(o, 'x'): min_x = min(min_x, o.x); min_y = min(min_y, o.y)
            if hasattr(o, 'x1'): min_x = min(min_x, o.x1, o.x2); min_y = min(min_y, o.y1, o.y2)
        if min_x == 999: min_x = min_y = 0
        for o in objs:
            if hasattr(o, 'x'): o.x -= min_x; o.y -= min_y
            if hasattr(o, 'x1'): o.x1 -= min_x; o.y1 -= min_y; o.x2 -= min_x; o.y2 -= min_y
        name = f"group_{len(self.cur_objs)}"
        new_meta = MetaObject(name=name, color=Color.WHITE, x=min_x, y=min_y, children=objs)
        for i in sorted(self.group_selection, reverse=True): self.cur_objs.pop(i)
        self.cur_objs.append(new_meta); self.sel_idx = len(self.cur_objs)-1
        self.group_selection = set(); self.mode = Mode.NAV; self.msg = f"Created {name}"

    def _do_ungroup(self):
        o = self.cur_objs[self.sel_idx]
        if not isinstance(o, MetaObject): self.msg = "Not a group"; return
        for c in o.children:
            if hasattr(c, 'x'): c.x += o.x; c.y += o.y
            if hasattr(c, 'x1'): c.x1 += o.x; c.y1 += o.y; c.x2 += o.x; c.y2 += o.y
        idx = self.sel_idx; self.cur_objs.pop(idx)
        for c in reversed(o.children): self.cur_objs.insert(idx, c)
        self.sel_idx = -1; self.msg = f"Ungrouped {o.name}"

    def _draw_obj(self, o: UIElement, bx: int, by: int, is_sel: bool, is_in_group: bool = False):
        try:
            attr = curses.color_pair(list(Color).index(o.color) + 1)
            if o.color.name.startswith("B_") or "_B_" in o.color.name: attr |= curses.A_BOLD
        except Exception: attr = curses.A_NORMAL
        if is_sel: attr |= (curses.A_BOLD | curses.A_REVERSE)
        if is_in_group: attr |= curses.A_DIM

        try:
            if isinstance(o, Box):
                x, y = bx+o.x, by+o.y
                self.stdscr.addch(y, x, '+', attr)
                self.stdscr.addch(y + o.h - 1, x + o.w - 1, '+', attr)
                for k in range(1, max(1, o.w - 1)):
                    self.stdscr.addch(y, x + k, '-', attr)
                    self.stdscr.addch(y + o.h - 1, x + k, '-', attr)
                for k in range(1, max(1, o.h - 1)):
                    self.stdscr.addch(y + k, x, '|', attr)
                    self.stdscr.addch(y + k, x + o.w - 1, '|', attr)
            elif isinstance(o, Text):
                for r, ln in enumerate(o.content.splitlines() or [""]):
                    self._add_ansi_str(by + o.y + r, bx + o.x, ln, attr)
            elif isinstance(o, Line):
                x1, y1, x2, y2 = bx+o.x1, by+o.y1, bx+o.x2, by+o.y2
                dx, sx = abs(x2-x1), (1 if x1<x2 else -1)
                dy, sy = -abs(y2-y1), (1 if y1<y2 else -1)
                err, cx, cy = dx+dy, x1, y1
                while True:
                    self.stdscr.addch(cy, cx, '#', attr)
                    if cx == x2 and cy == y2: break
                    e2 = 2*err
                    if e2 >= dy: err += dy; cx += sx
                    if e2 <= dx: err += dx; cy += sy
            elif isinstance(o, Freehand):
                for r, ln in enumerate(o.lines):
                    self._add_ansi_str(by + o.y + r, bx + o.x, ln, attr)
            elif isinstance(o, MetaObject):
                for c in o.children:
                    self._draw_obj(c, bx + o.x, by + o.y, False, is_sel)
        except curses.error: pass

    def _draw(self):
        self.stdscr.clear()
        if not self.edit_stack:
            for i, o in enumerate(self.cur_objs):
                is_sel = (i == self.sel_idx)
                is_in_group = (i in self.group_selection)
                self._draw_obj(o, 0, 0, is_sel, is_in_group)
        else:
            path = " > ".join([m.name for m in self.edit_stack])
            self.stdscr.addstr(0, 0, f"EDIT: {path}", curses.A_BOLD | curses.A_UNDERLINE)
            for i, o in enumerate(self.cur_objs):
                self._draw_obj(o, 0, 0, i == self.sel_idx, False)

        h, w = self.stdscr.getmaxyx()
        sel_name = ""
        if self._valid_sel():
            try: sel_name = f" | Sel: {self.cur_objs[self.sel_idx].name}"
            except Exception: sel_name = ""
        ctx_name = self.cur_screen.name if not self.edit_stack else self.edit_stack[-1].name
        stat = f"[{ctx_name}] {self.msg}{sel_name} | Pos:{self.cx},{self.cy} (e:edit t:text b:box l:line r:resize o:open)"
        try:
            self.stdscr.addstr(h - 1, 0, stat[:w - 1], curses.A_REVERSE)
            self.stdscr.move(max(0, min(h - 2, self.cy)), max(0, min(w - 1, self.cx)))
        except Exception:
            pass
        self.stdscr.refresh()

# ------------------------------
# Entrypoint
# ------------------------------
def main():
    project_file = "project.uiproj"
    compile_only = False
    args = sys.argv[1:]
    if "--compile" in args:
        compile_only = True; args.remove("--compile")
    if args: project_file = args[0]
    if compile_only:
        pm = ProjectManager(project_file)
        try:
            scrs = pm.load_project(); pm.save_project(scrs)
            print(f"Compiled {project_file} to C++.")
        except Exception as e: print(f"Failed: {e}")
        return
    try:
        curses.wrapper(lambda scr: Designer(scr, project_file).run())
    except Exception as e:
        try: curses.nocbreak()
        except Exception: pass
        try: curses.echo()
        except Exception: pass
        try: curses.endwin()
        except Exception: pass
        print("Critical Error:", e)

if __name__ == "__main__":
    main()
