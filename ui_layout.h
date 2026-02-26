#ifndef UI_LAYOUT_H
#define UI_LAYOUT_H
#include "SerialUI.h"

struct Layout_Dashboard {
    static const UI_Box bg;
    static const UI_Box temp_gauge;
    static const UI_Text temp_label;
    static const UI_Text temp_val;
    static const UI_Box status_box;
    static const UI_Text status_text;
};
void drawScreen_Dashboard(SerialUI& ui);

// USER FUNCTIONS
void update_dashboard(SerialUI& ui, float temp, bool ok);

#endif