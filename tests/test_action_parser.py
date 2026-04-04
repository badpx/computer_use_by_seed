import unittest

from computer_use.action_parser import parse_action


class ActionParserCoordinateTests(unittest.TestCase):
    def test_parse_float_point_coordinates(self):
        parsed = parse_action(
            "Thought: click\nAction: click(point='<point>0.25 0.75</point>')"
        )

        self.assertEqual(parsed['action_type'], 'click')
        self.assertEqual(parsed['action_inputs']['start_box'], [0.25, 0.75])

    def test_parse_float_drag_coordinates(self):
        parsed = parse_action(
            "Action: drag(start_point='<start_point>0.1 0.2</start_point>', "
            "end_point='<end_point>0.8 0.9</end_point>')"
        )

        self.assertEqual(parsed['action_type'], 'drag')
        self.assertEqual(parsed['action_inputs']['start_box'], [0.1, 0.2])
        self.assertEqual(parsed['action_inputs']['end_box'], [0.8, 0.9])

    def test_parse_numeric_xy_params_as_float(self):
        parsed = parse_action("Action: click(x=0.25, y=0.75)")

        self.assertEqual(parsed['action_inputs']['x'], 0.25)
        self.assertEqual(parsed['action_inputs']['y'], 0.75)


if __name__ == '__main__':
    unittest.main()
