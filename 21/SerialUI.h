
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
        int c = (int)color;
        if (c >= 90 && c <= 97) { Serial.print("\x1b[1;"); Serial.print(c-60); Serial.print("m"); }
        else if (c >= 30 && c <= 37) { Serial.print("\x1b[0;"); Serial.print(c); Serial.print("m"); }
        else if (c >= 40 && c <= 47) { Serial.print("\x1b["); Serial.print(c); Serial.print("m"); }
        else if (c >= 100 && c <= 107) { Serial.print("\x1b[1;"); Serial.print(c-60); Serial.print("m"); }
        else { Serial.print("\x1b[0m"); }
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
