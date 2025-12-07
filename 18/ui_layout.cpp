#include "ui_layout.h"

// === SHARED RESOURCES (PROGMEM) ===
// === SCREEN FUNCTIONS ===
void drawScreen_Main(SerialUI& ui) {
    ui.drawBox(7, 2, 14, 12, UI_Color::WHITE); // box_0
    ui.drawBox(9, 5, 19, 11, UI_Color::RED); // box_1
}

void drawScreen_settings(SerialUI& ui) {
    ui.drawBox(5, 2, 20, 12, UI_Color::WHITE); // box_0
}
