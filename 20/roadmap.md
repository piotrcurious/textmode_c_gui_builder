# Version 20 Development Roadmap

## Philosophical Goal

Transform the tool from a static drawing utility into a dynamic layout and data-binding framework for microcontroller GUIs. The layout designed in the editor should function as a semantic guide for the C++ application, allowing it to dynamically render data and manage state based on the structure of the UI, rather than just drawing static shapes. **The generator's role is to provide the layout data, not to generate application logic.**

---

## Pillar 1: Component-Based Design (Meta-Objects)

The next major leap for the editor is to allow the creation of reusable, hierarchical components (Meta-Objects) that encapsulate a group of `UIElement`s. This is the foundation for building complex, reusable widgets.

### 1.1. Grouping and Ungrouping
-   **Curses Editor**: Implement `g` (group) and `u` (ungroup) commands.
    -   When `g` is pressed, allow the user to select multiple objects.
    -   When selection is confirmed, create a new `Meta-Object` containing the selected items.
-   **Data Model**: Introduce a `MetaObject(UIElement)` class. It will contain a list of child `UIElement`s and define a bounding box based on its children.

### 1.2. Asset Library for Meta-Objects
-   **Asset Manager**: The `tkinter` Asset Manager should be updated to fully support `Meta-Object`s.
-   **Serialization**: `project.json` and `library.json` must be updated to serialize and deserialize these hierarchical objects.

### 1.3. Editing Meta-Objects
-   **Instance vs. Asset**: Differentiate between editing an *instance* of a `Meta-Object` on a screen (which just moves the whole group) and editing the *master asset* (which opens a dedicated editor to change its internal layout).
-   **Meta-Object Editor**: Create a new editor mode, possibly in a `tkinter` window, that allows for the editing of a `Meta-Object`'s internal structure.

---

## Pillar 2: Dynamic C++ Framework (Corrected Philosophy)

The C++ framework will be enhanced to empower the developer, not to automate their logic. The layout provides the "what" and "where"; the developer's `.ino` code provides the "how".

### 2.1. `printf`-style Helper Functions in `SerialUI.h`
-   **Goal**: Empower the developer to easily bind their data to the UI.
-   **Action**: Add new, overloaded helper functions to the `SerialUI` class in `SerialUI.h`.
    -   `void printfText(const UI_Text& text, ...)`: This function will take a `UI_Text` struct (e.g., `Layout_Main::statusText`) and a variable number of arguments. It will use the `content` field of the struct as a `printf`-compatible format string.
    -   `void printfText(int16_t x, int16_t y, UI_Color color, const char* fmt, ...)`: A lower-level version for more direct control.

### 2.2. The Layout as a Data Contract
-   **Concept**: The `content` field of a `Text` object should be treated as a format string by the developer. The designer and developer agree on a contract: a `Text` object named `temperature_float_C` will contain a `printf`-compatible string like `Temp: %.2f C`.
-   **No Generator Logic**: The Python generator will **not** parse or modify this content. It will be saved as a standard `const char*` in the C++ struct.

### 2.3. Updated `example.ino`
-   **Action**: The `example.ino` must be updated to provide a clear, canonical example of this philosophy.
-   **Example Code**:
    ```cpp
    #include "ui_layout.h"

    SerialUI ui;
    float tempC = 25.4;

    void setup() {
        ui.begin();
        drawScreen_Main(ui); // Draw static parts
    }

    void loop() {
        // Use the new helper to dynamically print the temperature
        // The position, color, and format string are all defined in the layout
        ui.printfText(Layout_Main::temperature_float_C, tempC);

        delay(1000);
        tempC += 0.1;
    }
    ```

---

## Pillar 3: Enhanced Visuals & Editing

The editor should be made more powerful and visually expressive.

### 3.1. ANSI Colors in Freehand
-   **Editor**: The `tkinter` editor for `Freehand` objects should be enhanced to support the insertion of ANSI color codes.
-   **Parser/Renderer**: The `curses` renderer needs to be able to parse and display these ANSI codes in the preview.
-   **C++ Generation**: The C++ code generation for `PROGMEM` strings needs to correctly embed these ANSI escape codes.

### 3.2. Extended Palette
-   **Data Model**: The `Color` enum should be extended to include more colors, such as bold and background colors.
-   **`SerialUI.h`**: The C++ `SerialUI` class needs to be updated to support these new color codes.
-   **Curses UI**: The `c` (color) key should cycle through the new, extended palette.

### 3.3. Resizing Objects
-   **Editor**: Implement a "resize" mode in the `curses` editor (e.g., activated by pressing `r` on a selected object). In this mode, the arrow keys would resize the object. This would apply to `Box`es and `Line`s.

---

## Pillar 4: Quality of Life Improvements

### 4.1. Formal Project File
-   **`.uiproj` File**: Instead of relying on a loose `project.json`, create a formal project file (e.g., `my_ui.uiproj`) that contains the project data. The tool would be launched with this file as an argument (`python 19.py my_ui.uiproj`).

### 4.2. Command-Line Arguments
-   Implement basic command-line arguments for specifying the project file, and perhaps for running in a non-interactive "compile-only" mode.

### 4.3. Improved Error Handling
-   Continue to improve the error handling, especially around file I/O and the `curses`/`tkinter` interface, to make the tool more robust.
