#include "ui_layout.h"

// === RESOURCES ===
// === IMPLEMENTATION ===
const UI_Box Layout_Main::box_0 = { 5, 2, 8, 7, UI_Color::WHITE };
const UI_Box Layout_Main::box_1 = { 8, 4, 9, 6, UI_Color::RED };

void drawScreen_Main(SerialUI& ui) {
    ui.draw(Layout_Main::box_0);
    ui.draw(Layout_Main::box_1);
}

const UI_Box Layout_settings::box2_1 = { 4, 1, 8, 7, UI_Color::GREEN };
const UI_Box Layout_settings::box2 = { 7, 3, 8, 7, UI_Color::WHITE };

void drawScreen_settings(SerialUI& ui) {
    ui.draw(Layout_settings::box2_1);
    ui.draw(Layout_settings::box2);
}
