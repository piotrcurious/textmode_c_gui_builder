#include "ui_layout.h"

void drawScreen_Main(SerialUI& ui) {
    const char* res_art_0[] = { "<---OH--->", "<---AH--->" };
    ui.drawFreehand(7, 6, res_art_0, 2, UI_Color::WHITE); // art_0
}