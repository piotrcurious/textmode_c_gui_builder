# Serial UI Designer (v21)

A powerful, hybrid terminal/GUI tool for designing text-based user interfaces for Arduino and other microcontrollers. It generates efficient C++ code that renders UI elements over a Serial connection using ANSI escape codes.

## Features

- **Hybrid Editor**: Uses `curses` for a true-to-life terminal preview and `tkinter` for advanced property editing and asset management.
- **Rich Elements**: Supports Boxes, Lines, Multi-line Text, and complex ASCII art (Freehand).
- **ANSI Styling**: Full support for 16 foreground/background colors and attributes (Bold, Dim, Italic, Underline, Blink).
- **Meta-Objects**: Hierarchical grouping of elements for reusable components.
- **Layering**: Adjust the drawing order of objects.
- **Asset Library**: Save and reuse UI components across projects.
- **Function Lab**: Generate, edit, and test C++ functions that interact with your UI, all within the designer using a built-in mock environment and compiler.

## Quick Start

1. **Launch the Designer**:
   ```bash
   python3 21.py project.uiproj
   ```
2. **Design your UI**: Use the keyboard shortcuts in the terminal and the Tkinter window to build your layout.
3. **Save and Compile**: Press `s` in the terminal or click **COMPILE** in the Tkinter window to generate `ui_layout.h` and `ui_layout.cpp`.
4. **Arduino Integration**: Include `ui_layout.h` in your sketch and use the generated `drawScreen_...` functions.

## Keyboard Shortcuts (Terminal)

| Key | Action |
|-----|--------|
| `Arrows` | Move cursor / Move selected object |
| `Tab` | Cycle through objects |
| `b` | Create a new **Box** |
| `l` | Create a new **Line** |
| `t` | Create a new **Text** object (opens Tkinter editor) |
| `e` | Edit properties of selected object (Tkinter) |
| `r` | Enter **Resize Mode** (use arrows to resize) |
| `n` | Rename selected object |
| `f` | **Generate Function** for selected object |
| `c` | Cycle through colors |
| `d` | Delete selected object |
| `+` / `-` | Move object up/down in layers |
| `[` / `]` | Move object back/forward in layers |
| `g` | Start **Grouping** (Space to toggle, Enter to confirm) |
| `u` | Ungroup Meta-Object |
| `o` | Open Meta-Object for internal editing |
| `s` | Save Project & Generate C++ |
| `q` | Quit |
| `Esc` | Cancel / Exit mode |

## Function Lab & C++ Integration

The Designer allows you to define "User Functions" that become part of your generated code. This is ideal for creating dynamic UI updates.

### Example: Dynamic Temperature Display

1. Create a Text object named `temp_val` with content `%0.1f C`.
2. In the **Function Lab** tab:
   - Click **New**, name it `updateTemp`, signature `float t`.
   - Edit the body:
     ```cpp
     ui.printfText(Layout_Main::temp_val, t);
     ```
3. Click **TEST/RUN**:
   - Enter `updateTemp(ui, 23.5);`
   - See the result in the **Visual Output** area!

### Integration in `.ino`:

```cpp
#include "ui_layout.h"

SerialUI ui;

void setup() {
    ui.begin(115200);
    drawScreen_Main(ui); // Draw static layout
}

void loop() {
    float currentTemp = readSensor();
    updateTemp(ui, currentTemp); // Call your generated function
    delay(1000);
}
```

## Advanced Examples

### Progress Bar (Meta-Object)
A progress bar can be created by grouping a Box (the border) and a Line or Text (the fill). You can then write a function `set_progress(int percent)` that calculates the length of the inner element.

### Status Indicators
Use the ANSI toolbar in the Text editor to create colored status icons (e.g., a green `[OK]` or a blinking red `[!]`).

## Mock Environment for PC

The generated `SerialUI.h` includes a mock environment. You can compile your UI and functions on a PC using `g++` to verify logic before uploading to hardware. The **Function Lab** does this automatically!

---
*Developed as part of Version 21.*
