#ifndef UI_LAYOUT_H
#define UI_LAYOUT_H
#include "SerialUI.h"

struct Layout_Main {
    static const UI_Box box_0;
    static const UI_Box box_1;
    static const UI_Text temperature_float_C;
};
void drawScreen_Main(SerialUI& ui);

struct Layout_Dashboard {
    static const UI_Box header_box;
    static const UI_Text title;
    static const UI_Text status_label;
    static const UI_Text status_val;
    static const UI_Box progress_bg;
    static const UI_Line progress_fill;
};
void drawScreen_Dashboard(SerialUI& ui);

// USER FUNCTIONS
void update_temp(SerialUI& ui, float t);
void set_online(SerialUI& ui, bool online);

#endif