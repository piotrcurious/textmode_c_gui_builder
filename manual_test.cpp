#include "21/ui_layout.h"
int main() {
    SerialUI ui;
    ui.begin();
    update_temp(ui, 27.5f);
    set_online(ui, true);
    return 0;
}
