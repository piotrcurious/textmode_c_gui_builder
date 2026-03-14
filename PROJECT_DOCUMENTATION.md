# Project Documentation: Serial UI Designer

## 1. Philosophy
The Serial UI Designer is built on the principle of **"Layout as Data."** Its primary goal is to empower microcontroller developers to create rich, interactive, and visually appealing text-mode user interfaces without the overhead of manually calculating coordinates or escaping ANSI codes.

### Core Tenets:
*   **Separation of Concerns**: The tool generates layout data (positions, sizes, static content) while leaving application logic and dynamic data binding to the developer's C++ code.
*   **Hybrid Workflow**: By combining a terminal-based `curses` editor (for true-to-life previews) with a `tkinter` GUI (for complex property editing), the tool provides the "best of both worlds."
*   **Microcontroller First**: Efficiency is paramount. The generator uses `PROGMEM` to store large string assets and generates minimal, type-safe C++ structs to ensure a low memory footprint.
*   **Developer Autonomy**: The tool doesn't impose a rigid framework. It provides helper functions (like `printfText`) but encourages developers to write their own logic using the generated layout constants.

---

## 2. Evolution & Version History

### The Early Days (v0.1 - v0.14)
*   **v0.1**: A proof-of-concept `curses` script that could draw hardcoded shapes and generate an Arduino `.ino` file.
*   **v0.11 - v0.13**: Introduction of a template-driven approach, multi-screen support, object selection/manipulation, and ANSI color support.
*   **v0.14**: A major architectural refactor, introducing Python `dataclasses` for UI elements and more robust state management.

### Professionalization (v0.15 - v0.18)
*   **v0.15**: Introduced the `SerialUI.h` library and "Round-Trip Engineering," allowing the tool to parse its own generated C++ to reload projects.
*   **v16**: The birth of the **Hybrid UI**. Added a `tkinter` helper window for easier text editing and property management alongside the `curses` preview.
*   **v17**: Memory optimization focus. Introduced `PROGMEM` for Freehand assets and the **Asset Library** for reusable components.
*   **v18**: Reintroduced multi-screen support with an improved GUI manager and resource deduplication to save flash memory.

### Modern Era (v19 - v21)
*   **v19**: Architectural pivot to **JSON as the Source of Truth**. Replaced brittle C++ parsing with a robust `project.json` format. Introduced static C++ `Layout_` structs for type-safe element access.
*   **v20**: Focused on the "Dynamic Framework" philosophy, adding grouping (Meta-Objects) and refining the relationship between generated code and user logic.
*   **v21 (Current)**: Introduction of the **Function Lab**. Added a built-in C++ simulation environment, template-based function generation, and a "True Terminal" ANSI renderer for logic verification.

---

## 3. Core Capabilities

### Hybrid Editor
*   **Curses Editor**: Provides a 1:1 preview of the terminal output. Supports keyboard-driven layout, resizing, and layering.
*   **Tkinter Manager**: Handles multi-line text input, detailed property editing (colors, names, layers), and project-level management (screens, assets).

### UI Elements
*   **Box**: Draw outlines with customizable borders.
*   **Line**: Connect points with various styles.
*   **Text**: Support for multi-line strings with embedded ANSI styling.
*   **Freehand**: Complex ASCII art stored efficiently in `PROGMEM`.
*   **Meta-Objects**: Hierarchical groups that can be moved as a unit and edited internally.

### ANSI Styling & Colors
*   Full support for the 16-color ANSI palette (Normal and Bright).
*   Background color support for all elements.
*   Text attributes: **Bold**, *Italic*, _Underline_, Dim, and Blinking.
*   A dedicated ANSI toolbar in the text editor for WYSIWYG styling.

### Function Lab & Testing
*   **Template Library**: Generate boilerplate C++ for common tasks (e.g., updating a sensor value or a progress bar).
*   **Test Runner**: Compiles user-defined C++ functions using `g++` and simulates their output in an integrated 80x24 ANSI terminal.

---

## 4. Technical Architecture

### Data Model
The project uses a hierarchical Python data model:
*   **`Project`**: The root container, holding a list of `Screen`s and `UserFunction`s.
*   **`Screen`**: A collection of `UIElement`s.
*   **`UIElement`**: Base class for all drawable objects (Box, Text, Line, Freehand, MetaObject).

### C++ Generation Strategy
The tool generates two primary files:
1.  **`ui_layout.h`**: Contains static `Layout_` structs for each screen. UI elements are exposed as `const` members, allowing for syntax like `ui.draw(Layout_Main::header_box)`.
2.  **`ui_layout.cpp`**: Contains the actual data definitions and the `drawScreen_...` functions.

### Simulation & Mocking
To enable the **Function Lab**, the `SerialUI.h` header includes a cross-platform mock of the Arduino `Serial` and `millis()` APIs. This allows the same C++ code to be compiled and tested on a PC using standard compilers (`g++`) before being deployed to an actual microcontroller.

---
*Generated for Version 21.*
