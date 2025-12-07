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

## Pillar 2: Dynamic C++ Framework (Final Philosophy)

The C++ framework will empower the developer to use the generated layout in flexible ways. The layout provides the static data (positions, colors, strings); the developer's `.ino` code provides the dynamic behavior.

### 2.1. The Dual Nature of Text
-   **Concept**: A `Text` or `Freehand` object is a container for string data. The developer has complete freedom to decide how to use this data.
    -   **Static Asset**: The object can be rendered directly using `ui.draw()`. This is ideal for labels, titles, or static ASCII art with ANSI colors (e.g., status indicators).
    -   **Dynamic Data Template**: The `content` of the object can be used as a format string for a custom, developer-written function.

### 2.2. Developer-Driven Logic
-   **Goal**: The framework should not impose a single method for data binding. Instead, it should provide the tools for the developer to build their own.
-   **Example `printfText` Helper**: To demonstrate this, an *example* helper function like `printfText` can be added to `SerialUI.h`.
    ```cpp
    // In SerialUI.h - An EXAMPLE of a developer-centric helper
    void printfText(const UI_Text& text, ...) {
        char buffer[128]; // Or other appropriate size
        va_list args;
        va_start(args, text);
        vsnprintf(buffer, sizeof(buffer), text.content, args);
        va_end(args);
        drawText(text.x, text.y, buffer, text.color);
    }
    ```
-   **No Generator Logic**: The Python generator remains completely agnostic to this. It simply generates the static `Layout_` structs. The developer is encouraged to write their own, more complex functions (e.g., `drawStatusBar(const UI_Box& container, const char* status, int batteryLevel)`) that use the layout structs as a reference.

### 2.3. Updated `example.ino`
-   **Action**: The `example.ino` must be updated to clearly demonstrate both uses of `Text` objects.
-   **Example Code**:
    ```cpp
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
        ui.printfText(Layout_Main::temperature_float_C, tempC);

        // The developer could also choose to draw a static status icon
        // by uncommenting the draw call in the generated drawScreen_Main function
        // and commenting out a dynamic call here.

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
