#include "SerialUI.h"
#include "ui_layout.h"

SerialUI ui;

void showSettingsList() {
    // PIGGY-BACKING: Access the layout data directly!
    UI_Box area = Layout_Main::settings_panel; 

    // Now use 'area.x', 'area.y', 'area.w' to draw dynamic content
    for(int i=0; i<5; i++) {
        ui.moveCursor(area.x + 1, area.y + 1 + i);
        Serial.print("Setting "); Serial.print(i);
    }
}

void setup() {
    ui.begin();
    drawScreen_Main(ui); // Draws the borders/static text
    showSettingsList();  // Draws dynamic content inside the anchor
}
