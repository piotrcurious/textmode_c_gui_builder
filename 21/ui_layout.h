#ifndef UI_LAYOUT_H
#define UI_LAYOUT_H
#include "SerialUI.h"

struct Layout_Main {
    static const UI_Box box_0;
    static const UI_Box box_1;
    static const UI_Text temperature_float_C;
};
void drawScreen_Main(SerialUI& ui);

struct Layout_settings {
    static const UI_Box red_box;
    static const UI_Text txt_1;
};
void drawScreen_settings(SerialUI& ui);

#endif