#include "ui_layout.h"

SerialUI ui;
float tempC = 25.4;

void setup() {
//    ui.begin(230400);
//    ui.begin(500000); 
    ui.begin(1000000); 

    // Draw the entire static layout, including titles and ASCII art
    //drawScreen_Main(ui);
    drawScreen_settings(ui);
}

void loop() {
    // Use the layout as a template for a developer-defined function
    //ui.printfText(Layout_Main::temperature_float_C, tempC);

    // The developer could also choose to draw a static status icon
    // by uncommenting the draw call in the generated drawScreen_Main function
    // and commenting out a dynamic call here.

    delay(1000);
    tempC += 0.1;
}
