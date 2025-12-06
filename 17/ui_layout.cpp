#include "ui_layout.h"

// --- PROGMEM Definitions ---
const char art_3_L0[] PROGMEM = "().()";
const char* const art_3_arr[] PROGMEM = { art_3_L0 };
const char art_4_L0[] PROGMEM = "()o()";
const char* const art_4_arr[] PROGMEM = { art_4_L0 };

// --- Draw Function ---
void drawScreen_Main(SerialUI& ui) {
    ui.drawBox(3, 2, 15, 7, UI_Color::GREEN); // box_0
    ui.drawBox(8, 5, 24, 6, UI_Color::YELLOW); // box_2
    ui.drawBox(21, 1, 17, 7, UI_Color::RED); // box_1
    ui.drawFreehand(21, 8, art_3_arr, 1, UI_Color::BLUE); // art_3
    ui.drawFreehand(10, 7, art_4_arr, 1, UI_Color::WHITE); // art_4
}