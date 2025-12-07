# Review of Version 0.13

Version 0.13 is a major enhancement to the interactive editor, building upon the foundation of `0.12.py`. It introduces a host of new features that make the design process more flexible and powerful, including object selection, manipulation, and styling.

## Key Changes and New Features

- **Object Selection and Manipulation**: This is the most significant new feature. Users can now select objects (`Tab` key), move them around with the arrow keys, and delete them.
- **Color Support**: The editor now supports colors. Each object can have a color, which is reflected in the `curses` interface and the generated C++ code. The C++ template has been updated to include ANSI color codes.
- **Line Drawing is Back**: The ability to draw lines has been reintroduced into the interactive editor.
- **Layer Control**: Selected objects can be moved forward or backward in the drawing order (Z-ordering), which is essential for managing overlapping elements.
- **Improved C++ Code**: The C++ template now uses a faster baud rate (115200) and includes an example of a simple screen manager in the `loop()` function. The `draw` function for boxes has been optimized to reduce the number of `moveCursor` calls.
- **Enhanced Status Bar**: The status bar is now context-aware, showing different commands depending on whether an object is selected.
- **Better Screen Management**: A menu for switching between screens has been added, making it easier to work on different parts of a multi-screen UI.
- **Enum for Modes**: The `DesignMode` `Enum` makes the code for managing the editor's state cleaner and less error-prone.

## Bugs and Limitations

- **No Resizing**: While objects can be moved, they still can't be resized after creation.
- **Limited Color Palette**: The color palette is fixed and relatively small.
- **Basic Screen Switching Example**: The screen switching logic in the generated C++ is just an example and would need to be properly implemented by the user.

## Overall Assessment

Version 0.13 transforms the project from a simple GUI builder into a more serious design tool. The ability to select, move, delete, and re-layer objects is a game-changer for the editor's usability. The addition of colors makes the UIs that can be created much more expressive. The codebase is also maturing, with improvements like the `DesignMode` enum and optimized C++ drawing functions. This version is a very polished and capable iteration of the tool.
