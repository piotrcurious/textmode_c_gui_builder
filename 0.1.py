import curses import sys

class DrawableObject: def init(self, obj_type, data): self.obj_type = obj_type self.data = data

def to_cpp(self):
    if self.obj_type == "box":
        x, y, w, h = self.data
        return f"  drawBox({x}, {y}, {w}, {h});"
    elif self.obj_type == "line":
        x1, y1, x2, y2 = self.data
        return f"  drawLine({x1}, {y1}, {x2}, {y2});"
    elif self.obj_type == "circle":
        x, y, r = self.data
        return f"  drawCircle({x}, {y}, {r});"
    elif self.obj_type == "arc":
        x, y, r, start, end = self.data
        return f"  drawArc({x}, {y}, {r}, {start}, {end});"
    elif self.obj_type == "text":
        x, y, txt = self.data
        return f"  drawText({x}, {y}, \"{txt}\");"
    elif self.obj_type == "free":
        pts = ", ".join([f"{{{px},{py}}}" for px, py in self.data])
        return f"  drawFreehand(new Point[]{{{pts}}}, {len(self.data)});"
    return ""

objects = []

cpp_code = """ #include <Arduino.h>

struct Point { int x; int y; };

// Primitive rendering functions (ASCII/VT102 over Serial) void moveCursor(int x, int y) { Serial.print("\033["); Serial.print(y); Serial.print(";"); Serial.print(x); Serial.print("H"); }

void drawBox(int x, int y, int w, int h) { for (int i = 0; i < w; i++) { moveCursor(x+i, y); Serial.print("-"); moveCursor(x+i, y+h-1); Serial.print("-"); } for (int j = 0; j < h; j++) { moveCursor(x, y+j); Serial.print("|"); moveCursor(x+w-1, y+j); Serial.print("|"); } }

void drawLine(int x1, int y1, int x2, int y2) { int dx = abs(x2-x1), sx = x1<x2 ? 1 : -1; int dy = -abs(y2-y1), sy = y1<y2 ? 1 : -1; int err = dx+dy, e2; while (true) { moveCursor(x1,y1); Serial.print(""); if (x1==x2 && y1==y2) break; e2 = 2err; if (e2 >= dy) { err += dy; x1 += sx; } if (e2 <= dx) { err += dx; y1 += sy; } } }

void drawCircle(int x0, int y0, int r) { int x = r, y = 0, err = 0; while (x >= y) { moveCursor(x0 + x, y0 + y); Serial.print("o"); moveCursor(x0 + y, y0 + x); Serial.print("o"); moveCursor(x0 - y, y0 + x); Serial.print("o"); moveCursor(x0 - x, y0 + y); Serial.print("o"); moveCursor(x0 - x, y0 - y); Serial.print("o"); moveCursor(x0 - y, y0 - x); Serial.print("o"); moveCursor(x0 + y, y0 - x); Serial.print("o"); moveCursor(x0 + x, y0 - y); Serial.print("o"); y += 1; if (err <= 0) { err += 2y + 1; } if (err > 0) { x -= 1; err -= 2x + 1; } } }

void drawArc(int x, int y, int r, int start, int end) { // Simplified: placeholder draws quarter circle drawCircle(x,y,r); }

void drawText(int x, int y, const char* t) { moveCursor(x,y); Serial.print(t); }

void drawFreehand(Point* pts, int n) { for (int i=0; i<n-1; i++) drawLine(pts[i].x, pts[i].y, pts[i+1].x, pts[i+1].y); }

void renderUI() { """

cpp_footer = """ }

void setup() { Serial.begin(9600); delay(1000); Serial.print("\033[2J"); // clear screen renderUI(); }

void loop() {} """

def compile_to_cpp(filename="ui_generated.ino"): with open(filename, "w") as f: f.write(cpp_code) for obj in objects: f.write(obj.to_cpp()+"\n") f.write(cpp_footer) print(f"Arduino C++ code written to {filename}")

Minimal CLI interface for testing

def main(stdscr): curses.curs_set(0) stdscr.addstr(0,0,"VT102 ASCII GUI Builder for Arduino Serial - Press q to quit, c to compile") while True: key = stdscr.getch() if key == ord('q'): break elif key == ord('b'): objects.append(DrawableObject("box", (10,5,20,10))) elif key == ord('l'): objects.append(DrawableObject("line", (0,0,30,15))) elif key == ord('t'): objects.append(DrawableObject("text", (5,20,"Hello"))) elif key == ord('c'): compile_to_cpp()

if name == "main": curses.wrapper(main)

