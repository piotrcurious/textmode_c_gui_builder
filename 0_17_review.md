# Review of Version 17

Version 17 introduces several major features that significantly enhance the tool's capabilities, particularly for professional microcontroller development. The focus is on memory optimization, asset management, and improved editor functionality.

## Key Architectural Changes

- **`PROGMEM` for C++ Code Generation**: The C++ code generation for `Freehand` objects has been completely rewritten to use `PROGMEM`. This is a critical optimization for Arduino and other microcontrollers with limited RAM, as it stores the large string data in flash memory instead of RAM.
- **Smarter C++ Parser**: To support the more complex `PROGMEM` code, the project parser in `ProjectManager` is now much more sophisticated. It performs a multi-pass parse, first identifying all the `PROGMEM` string and array definitions and then parsing the function calls that use them. This is a far more robust approach than the previous line-by-line regex parsing.
- **Asset Library**: A new `AssetLibrary` class has been introduced, which can save and load `Freehand` assets to a `library.json` file. This allows for the creation of reusable art and design components.

## Feature Enhancements

- **Asset Manager GUI**: The `tkinter` helper GUI now features a full-fledged Asset Manager. This allows users to view, edit, save, and import `Freehand` assets from the `library.json` file into their designs.
- **Layering Control is Back**: The ability to change the Z-order of objects using the `+` and `-` keys has been reintroduced into the `curses` editor. This is a crucial feature for managing complex UIs with overlapping elements.
- **Improved GUI Layout**: The `tkinter` window now uses a tabbed interface, which provides a better user experience and makes the GUI more scalable for future additions.

## Regressions and Limitations

- **Still No Multi-Screen Support**: The single biggest missing feature continues to be multi-screen management. All the new features are still focused on designing a single screen.
- **Complexity**: The `PROGMEM` code generation and parsing logic, while powerful, adds another layer of complexity to the codebase.

## Overall Assessment

Version 17 is a very strong release that adds professional-grade features to the tool. The `PROGMEM` support is a must-have for any serious microcontroller GUI development, and the Asset Library is a fantastic addition for creating reusable and maintainable designs. The reintroduction of layering control also fills a significant gap from previous versions. While the lack of multi-screen support is still a major limitation, the new features in this version make the tool much more powerful and practical for its intended purpose.
