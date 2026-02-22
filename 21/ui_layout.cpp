#include "ui_layout.h"

// RESOURCES
// IMPLEMENTATION
const UI_Box Layout_Main::box_0 = { 3, 2, 18, 4, UI_Color::WHITE };
const UI_Box Layout_Main::box_1 = { 6, 4, 27, 4, UI_Color::RED };
const UI_Text Layout_Main::temperature_float_C = { 17, 6, "%f.3", UI_Color::WHITE };

void drawScreen_Main(SerialUI& ui) {
    ui.draw(Layout_Main::box_0);
    ui.draw(Layout_Main::box_1);
    ui.draw(Layout_Main::temperature_float_C);
}

const UI_Box Layout_settings::red_box = { 4, 2, 35, 8, UI_Color::RED };
const UI_Text Layout_settings::txt_1 = { 17, 5, "<--OH-->\n<--AH-->", UI_Color::BLUE };

void drawScreen_settings(SerialUI& ui) {
    ui.draw(Layout_settings::red_box);
    ui.draw(Layout_settings::txt_1);
}
