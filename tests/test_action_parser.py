import unittest

from computer_use.action_parser import parse_action, parse_actions


class ActionParserCoordinateTests(unittest.TestCase):
    def test_parse_float_point_coordinates(self):
        parsed = parse_action(
            "Thought: click\nAction: click(point='<point>0.25 0.75</point>')"
        )

        self.assertEqual(parsed['action_type'], 'click')
        self.assertEqual(parsed['action_inputs']['point'], [0.25, 0.75])

    def test_parse_float_drag_coordinates(self):
        parsed = parse_action(
            "Action: drag(start_point='<start_point>0.1 0.2</start_point>', "
            "end_point='<end_point>0.8 0.9</end_point>')"
        )

        self.assertEqual(parsed['action_type'], 'drag')
        self.assertEqual(parsed['action_inputs']['start_point'], [0.1, 0.2])
        self.assertEqual(parsed['action_inputs']['end_point'], [0.8, 0.9])

    def test_parse_drag_coordinates_with_point_tags(self):
        parsed = parse_action(
            "Action: drag(start_point='<point>236 470</point>', "
            "end_point='<point>544 470</point>')"
        )

        self.assertEqual(parsed['action_type'], 'drag')
        self.assertEqual(parsed['action_inputs']['start_point'], [236.0, 470.0])
        self.assertEqual(parsed['action_inputs']['end_point'], [544.0, 470.0])

    def test_parse_numeric_xy_params_as_float(self):
        parsed = parse_action("Action: click(x=0.25, y=0.75)")

        self.assertEqual(parsed['action_inputs']['x'], 0.25)
        self.assertEqual(parsed['action_inputs']['y'], 0.75)

    def test_parse_click_point_without_xml_tags(self):
        parsed = parse_action("Action: click(point='1000 0')")

        self.assertEqual(parsed['action_type'], 'click')
        self.assertEqual(parsed['action_inputs']['point'], [1000.0, 0.0])

    def test_parse_drag_points_without_xml_tags(self):
        parsed = parse_action(
            "Action: drag(start_point='236 470', end_point='544 470')"
        )

        self.assertEqual(parsed['action_type'], 'drag')
        self.assertEqual(parsed['action_inputs']['start_point'], [236.0, 470.0])
        self.assertEqual(parsed['action_inputs']['end_point'], [544.0, 470.0])

    def test_parse_swipe_coordinates_with_optional_duration(self):
        parsed = parse_action(
            "Action: swipe(start_point='<point>236 470</point>', "
            "end_point='<point>544 470</point>', duration=800)"
        )

        self.assertEqual(parsed['action_type'], 'swipe')
        self.assertEqual(parsed['action_inputs']['start_point'], [236.0, 470.0])
        self.assertEqual(parsed['action_inputs']['end_point'], [544.0, 470.0])
        self.assertEqual(parsed['action_inputs']['duration'], 800.0)

    def test_extract_finished_action_from_natural_language_response(self):
        parsed = parse_action(
            "太好了！现在，多余的中间横线已经擦掉了，完全符合要求，任务完成！"
            " finished(content='已在浏览器的在线画板中间完成回字的正确绘制')"
        )

        self.assertEqual(parsed['action_type'], 'finished')
        self.assertEqual(
            parsed['action_inputs']['content'],
            '已在浏览器的在线画板中间完成回字的正确绘制',
        )

    def test_parse_finished_content_with_embedded_apostrophe_and_comma(self):
        parsed = parse_action(
            "Action: finished(content='上海城中希尔顿酒店的地址是：上海市长宁区延安西路488号"
            "（英文：长宁区488WestYan'anRoad, Shanghai）。')"
        )

        self.assertEqual(parsed['action_type'], 'finished')
        self.assertEqual(
            parsed['action_inputs']['content'],
            "上海城中希尔顿酒店的地址是：上海市长宁区延安西路488号"
            "（英文：长宁区488WestYan'anRoad, Shanghai）。",
        )

    def test_parse_wait_seconds_as_float(self):
        parsed = parse_action("Action: wait(seconds=12)")

        self.assertEqual(parsed['action_type'], 'wait')
        self.assertEqual(parsed['action_inputs']['seconds'], 12.0)

    def test_parse_multiple_actions_from_multiline_action_block(self):
        parsed = parse_actions(
            "Thought: replace text\n"
            "Action:\n"
            "hotkey(key='ctrl a')\n"
            "hotkey(key='backspace')\n"
            "type(content='hello\\n')"
        )

        self.assertEqual(
            [action['action_type'] for action in parsed],
            ['hotkey', 'hotkey', 'type'],
        )
        self.assertEqual(parsed[0]['action_inputs']['key'], 'ctrl a')
        self.assertEqual(parsed[1]['action_inputs']['key'], 'backspace')
        self.assertEqual(parsed[2]['action_inputs']['content'], 'hello\\n')

    def test_parse_multiple_actions_from_semicolon_separated_action_line(self):
        parsed = parse_actions(
            "Thought: submit\n"
            "Action: type(content='hello, world'); hotkey(key='enter')"
        )

        self.assertEqual(
            [action['action_type'] for action in parsed],
            ['type', 'hotkey'],
        )
        self.assertEqual(parsed[0]['action_inputs']['content'], 'hello, world')
        self.assertEqual(parsed[1]['action_inputs']['key'], 'enter')

    def test_parse_action_keeps_backward_compatible_first_action(self):
        parsed = parse_action(
            "Thought: replace text\n"
            "Action:\n"
            "hotkey(key='ctrl a')\n"
            "type(content='hello')"
        )

        self.assertEqual(parsed['action_type'], 'hotkey')
        self.assertEqual(parsed['action_inputs']['key'], 'ctrl a')

    def test_parse_multiple_actions_from_function_call_wrapper(self):
        parsed = parse_actions(
            '<|FunctionCallBegin|>'
            '[{"name":"type","parameters":{"content":"hello, world"}},'
            '{"name":"hotkey","parameters":{"key":"enter"}}]'
            '<|FunctionCallEnd|>'
        )

        self.assertEqual(
            [action['action_type'] for action in parsed],
            ['type', 'hotkey'],
        )
        self.assertEqual(parsed[0]['action_inputs']['content'], 'hello, world')
        self.assertEqual(parsed[1]['action_inputs']['key'], 'enter')

    def test_extract_open_app_action_from_natural_language_response(self):
        parsed = parse_action(
            "先打开设置应用。下一步执行 open_app(app_name='com.android.settings')"
        )

        self.assertEqual(parsed['action_type'], 'open_app')
        self.assertEqual(
            parsed['action_inputs']['app_name'],
            'com.android.settings',
        )

    def test_extract_press_home_action_from_natural_language_response(self):
        parsed = parse_action(
            "当前页面卡住了，先回到桌面 press_home()"
        )

        self.assertEqual(parsed['action_type'], 'press_home')
        self.assertEqual(parsed['action_inputs'], {})


if __name__ == '__main__':
    unittest.main()
