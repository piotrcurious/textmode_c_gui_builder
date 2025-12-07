#include "ui_layout.h"

SerialUI ui;
float tempC = 25.4;

void setup() {
    ui.begin();
    // Draw the entire static layout, including titles and ASCII art
    drawScreen_Main(ui);
}

void loop() {
    // Use the layout as a template for a developer-defined function
    // Note: In a real app, you might have a dedicated text object for this.
    // Here we reuse 'main_title' for demonstration.
    // The C++ code might define a specific UI_Text for dynamic data,
    // e.g., Layout_Main::temperature_float_C
    // For this example, let's imagine 'temperature_reading' is a text object
    // defined in our layout with content "Temp: %.1f C".
    // ui.printfText(Layout_Main::temperature_reading, tempC);

    // To make this example runnable, we'll just print at a fixed location.
    ui.moveCursor(2, 2);
    Serial.print("Temp: ");
    Serial.print(tempC);

    delay(1000);
    tempC += 0.1;
}
