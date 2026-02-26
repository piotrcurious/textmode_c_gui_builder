#include "ui_layout.h"

// RESOURCES
// IMPLEMENTATION
const UI_Box Layout_Dashboard::bg = { 0, 0, 80, 24, UI_Color::BLUE };
const UI_Box Layout_Dashboard::temp_gauge = { 2, 2, 20, 3, UI_Color::WHITE };
const UI_Text Layout_Dashboard::temp_label = { 4, 1, "TEMPERATURE", UI_Color::CYAN };
const UI_Text Layout_Dashboard::temp_val = { 23, 3, "%0.1f C", UI_Color::YELLOW };
const UI_Box Layout_Dashboard::status_box = { 40, 2, 30, 5, UI_Color::MAGENTA };
const UI_Text Layout_Dashboard::status_text = { 42, 4, "SYSTEM: INITIALIZING", UI_Color::WHITE };

void drawScreen_Dashboard(SerialUI& ui) {
    ui.draw(Layout_Dashboard::bg);
    ui.draw(Layout_Dashboard::temp_gauge);
    ui.draw(Layout_Dashboard::temp_label);
    ui.draw(Layout_Dashboard::temp_val);
    ui.draw(Layout_Dashboard::status_box);
    ui.draw(Layout_Dashboard::status_text);
}

// USER FUNCTIONS IMPLEMENTATION
void update_dashboard(SerialUI& ui, float temp, bool ok) {
    ui.drawProgressBar(Layout_Dashboard::temp_gauge, temp, temp > 80 ? UI_Color::RED : UI_Color::GREEN);
    ui.printfText(Layout_Dashboard::temp_val, "%0.1f C", temp);
    if (ok) {
        ui.drawText(Layout_Dashboard::status_text.x, Layout_Dashboard::status_text.y, "SYSTEM: OK          ", UI_Color::GREEN);
    } else {
        ui.drawText(Layout_Dashboard::status_text.x, Layout_Dashboard::status_text.y, "SYSTEM: ERROR       ", UI_Color::B_RED);
    }
}
