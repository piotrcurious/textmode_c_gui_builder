#include "SerialUI.h"
#include "ui_layout.h"
SerialUI ui;

void setup() {
   ui.begin();
   drawScreen_Main(ui); // Show main
   delay(2000);
   ui.clearScreen();
   drawScreen_Settings(ui); // Show settings
}
void loop() {}
