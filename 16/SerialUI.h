
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
