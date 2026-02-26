#include "ui_layout.h"

// RESOURCES
// IMPLEMENTATION
const UI_Box Layout_Main::box_0 = { 3, 2, 18, 4, UI_Color::WHITE };
const UI_Box Layout_Main::box_1 = { 6, 4, 27, 4, UI_Color::RED };
const UI_Text Layout_Main::temperature_float_C = { 17, 6, "%0.1f C", UI_Color::WHITE };

void drawScreen_Main(SerialUI& ui) {
    ui.draw(Layout_Main::box_0);
    ui.draw(Layout_Main::box_1);
    ui.draw(Layout_Main::temperature_float_C);
}

const UI_Box Layout_Dashboard::header_box = { 0, 0, 60, 3, UI_Color::BLUE };
const UI_Text Layout_Dashboard::title = { 20, 1, "SYSTEM DASHBOARD", UI_Color::WHITE };
const UI_Text Layout_Dashboard::status_label = { 2, 5, "Status:", UI_Color::CYAN };
const UI_Text Layout_Dashboard::status_val = { 10, 5, "ONLINE", UI_Color::GREEN };
const UI_Box Layout_Dashboard::progress_bg = { 2, 8, 22, 3, UI_Color::WHITE };
const UI_Line Layout_Dashboard::progress_fill = { 3, 9, 3, 9, UI_Color::MAGENTA };

void drawScreen_Dashboard(SerialUI& ui) {
    ui.draw(Layout_Dashboard::header_box);
    ui.draw(Layout_Dashboard::title);
    ui.draw(Layout_Dashboard::status_label);
    ui.draw(Layout_Dashboard::status_val);
    ui.draw(Layout_Dashboard::progress_bg);
    ui.draw(Layout_Dashboard::progress_fill);
}

// USER FUNCTIONS IMPLEMENTATION
void update_temp(SerialUI& ui, float t) {
    ui.printfText(Layout_Main::temperature_float_C, "%0.1f C", t);
}

void set_online(SerialUI& ui, bool online) {
    if (online) {
        ui.drawText(Layout_Dashboard::status_val.x, Layout_Dashboard::status_val.y, "ONLINE ", UI_Color::GREEN);
    } else {
        ui.drawText(Layout_Dashboard::status_val.x, Layout_Dashboard::status_val.y, "OFFLINE", UI_Color::RED);
    }
}
