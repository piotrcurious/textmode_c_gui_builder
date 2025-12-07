#ifndef UI_LAYOUT_H
#define UI_LAYOUT_H
#include "SerialUI.h"

// === LAYOUT ANCHORS ===
// Access these in your code: Layout_Main::myBox.x
struct Layout_Main {
    static const UI_Box box_0;
    static const UI_Box box_1;
};
void drawScreen_Main(SerialUI& ui);

struct Layout_settings {
    static const UI_Box box2_1;
    static const UI_Box box2;
};
void drawScreen_settings(SerialUI& ui);

#endif