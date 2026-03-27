import unittest
import json
from pathlib import Path
import os
import sys

# Add the parent directory to the sys.path to allow imports from 20.py
sys.path.append(str(Path(__file__).parent))

from twenty import UIElement, Box, Line, Text, MetaObject, ProjectManager, Screen, Color

class TestProjectGeneration(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("test_project")
        self.test_dir.mkdir(exist_ok=True)
        self.project_path = self.test_dir / "project.json"

    def tearDown(self):
        for f in self.test_dir.glob("*"):
            f.unlink()
        self.test_dir.rmdir()

    def test_project_loading(self):
        project_data = [
            {
                "name": "Main",
                "objects": [
                    {
                        "name": "box_0",
                        "color": "WHITE",
                        "type": "BOX",
                        "x": 5,
                        "y": 2,
                        "w": 8,
                        "h": 7
                    }
                ]
            }
        ]
        self.project_path.write_text(json.dumps(project_data, indent=2))

        pm = ProjectManager(self.project_path)
        screens = pm.load_project()

        self.assertEqual(len(screens), 1)
        self.assertEqual(screens[0].name, "Main")
        self.assertEqual(len(screens[0].objects), 1)
        self.assertIsInstance(screens[0].objects[0], Box)
        self.assertEqual(screens[0].objects[0].name, "box_0")

    def test_grouping_logic(self):
        box1 = Box(name="box1", x=0, y=0, w=5, h=5)
        box2 = Box(name="box2", x=10, y=10, w=5, h=5)
        line1 = Line(name="line1", x1=2, y1=2, x2=8, y2=8)

        children = [box1, box2, line1]

        min_x = float('inf')
        min_y = float('inf')
        for o in children:
            if hasattr(o, 'x'):
                min_x = min(min_x, o.x)
                min_y = min(min_y, o.y)
            elif hasattr(o, 'x1'):
                min_x = min(min_x, o.x1, o.x2)
                min_y = min(min_y, o.y1, o.y2)

        meta = MetaObject(name="meta", x=int(min_x), y=int(min_y), children=children)

        self.assertEqual(meta.x, 0)
        self.assertEqual(meta.y, 0)
        self.assertEqual(len(meta.children), 3)

    def test_code_generation(self):
        screens = [
            Screen(name="Main", objects=[
                Box(name="my_box", x=1, y=1, w=10, h=10, color=Color.RED),
                MetaObject(name="my_group", x=5, y=5, children=[
                    Line(name="line_a", x1=6, y1=6, x2=9, y2=9, color=Color.BLUE),
                    Text(name="text_b", x=7, y=7, content="Hello", color=Color.GREEN)
                ])
            ])
        ]

        pm = ProjectManager(self.project_path)
        pm.save_project(screens)

        h_file = self.test_dir / "ui_layout.h"
        cpp_file = self.test_dir / "ui_layout.cpp"

        self.assertTrue(h_file.exists())
        self.assertTrue(cpp_file.exists())

        h_content = h_file.read_text()
        self.assertIn("struct Layout_Main", h_content)
        self.assertIn("static const UI_Box my_box;", h_content)
        self.assertIn("static const UI_Line line_a;", h_content)
        self.assertIn("static const UI_Text text_b;", h_content)
        self.assertNotIn("my_group", h_content)

        cpp_content = cpp_file.read_text()
        self.assertIn("const UI_Box Layout_Main::my_box = { 1, 1, 10, 10, UI_Color::RED };", cpp_content)
        self.assertIn("const UI_Line Layout_Main::line_a = { 6, 6, 9, 9, UI_Color::BLUE };", cpp_content)
        self.assertIn('const UI_Text Layout_Main::text_b = { 7, 7, "Hello", UI_Color::GREEN };', cpp_content)
        self.assertIn("ui.draw(Layout_Main::my_box);", cpp_content)
        self.assertIn("ui.draw(Layout_Main::line_a);", cpp_content)
        self.assertIn("ui.draw(Layout_Main::text_b);", cpp_content)

if __name__ == '__main__':
    unittest.main()
