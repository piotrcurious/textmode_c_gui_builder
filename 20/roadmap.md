# Version 20 Development Roadmap

## Philosophical Goal

Transform the tool from a static drawing utility into a dynamic layout and data-binding framework for microcontroller GUIs. The layout designed in the editor should function as a semantic guide for the C++ application, allowing it to dynamically render data and manage state based on the structure of the UI, rather than just drawing static shapes.

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

## Pillar 2: Dynamic C++ Framework

The generated C++ code needs to evolve from a simple drawing script into a more dynamic framework that supports data binding and state management.

### 2.1. Data-Binding Syntax
-   **Editor**: In the `tkinter` Properties Editor for `Text` objects, allow the use of a simple data-binding syntax in the `content` field. For example, `Temp: {{temp_c}} C`.
-   **Code Generation**: The generator should parse this syntax. Instead of generating a static `const char*`, it should generate a `printf`-style function call, e.g., `ui.drawText(x, y, "Temp: %d C", temp_c, color);`.

### 2.2. Dynamic `printf` in `SerialUI.h`
-   **`SerialUI` Class**: Create a new, overloaded `drawText` method in the `SerialUI` C++ class that accepts a format string and a variable number of arguments (variadic template or `...`). This function will be responsible for `snprintf`ing the data into a buffer before printing.

### 2.3. Layout as Data Guide
-   **Concept**: As described in the philosophical goal, the `Layout_` structs should be used as more than just drawing guides. The user's C++ code should be able to reference them to make decisions.
-   **Example (`example.ino`):** The `example.ino` should be updated to demonstrate this concept. For example, a "details" screen might have a larger box for temperature than the "main" screen. The C++ code would check the size of `Layout_Details::tempBox.w` to decide whether to show a detailed or a summary view.

---

## Pillar 3: Enhanced Visuals & Editing

The editor should be made more powerful and visually expressive.

### 3.1. ANSI Colors in Freehand
-   **Editor**: The `tkinter` editor for `Freehand` objects should be enhanced to support the insertion of ANSI color codes. This could be done with a simple right-click menu or a color picker.
-   **Parser/Renderer**: The `curses` renderer needs to be able to parse and display these ANSI codes in the preview.
-   **C++ Generation**: The C++ code generation for `PROGMEM` strings needs to correctly embed these ANSI escape codes.

### 3.2. Extended Palette
-   **Data Model**: The `Color` enum should be extended to include more colors, such as bold and background colors.
-   **`SerialUI.h`**: The C++ `SerialUI` class needs to be updated to support these new color codes.
-   **Curses UI**: The `c` (color) key should cycle through the new, extended palette.

### 3.3. Resizing Objects
-   **Editor**: Implement a "resize" mode in the `curses` editor (e.g., activated by pressing `r` on a selected object). In this mode, the arrow keys would resize the object instead of moving it. This would apply to `Box`es and `Line`s.

---

## Pillar 4: Quality of Life Improvements

### 4.1. Formal Project File
-   **`.uiproj` File**: Instead of relying on a loose `project.json`, create a formal project file (e.g., `my_ui.uiproj`) that contains the project data. The tool would be launched with this file as an argument (`python 19.py my_ui.uiproj`). This makes project management more explicit.

### 4.2. Command-Line Arguments
-   Implement basic command-line arguments for specifying the project file, and perhaps for running in a non-interactive "compile-only" mode.

### 4.3. Improved Error Handling
-   Continue to improve the error handling, especially around file I/O and the `curses`/`tkinter` interface, to make the tool more robust.
