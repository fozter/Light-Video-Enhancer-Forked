import io
import logging
import unittest

from light_video_enhancer_forked._logging import get_logger, set_gui_handler
from light_video_enhancer_forked.log_i18n import translate_log_template


class RuntimeLogLocalizationTests(unittest.TestCase):
    def tearDown(self):
        set_gui_handler(None)

    def test_english_templates_pass_through(self):
        self.assertEqual(
            translate_log_template("Input: %dx%d @ %.3f fps, %s frames"),
            "Input: %dx%d @ %.3f fps, %s frames",
        )
        self.assertEqual(
            translate_log_template("RIFE interpolation multiplier must be at least 2"),
            "RIFE interpolation multiplier must be at least 2",
        )

    def test_handler_filter_keeps_formatted_records(self):
        output = io.StringIO()
        handler = logging.StreamHandler(output)
        handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        set_gui_handler(handler)

        get_logger("test").info("Input: %dx%d @ %.3f fps, %s frames", 1280, 720, 30.0, 15)

        self.assertEqual(
            output.getvalue().strip(),
            "[INFO] Input: 1280x720 @ 30.000 fps, 15 frames",
        )


if __name__ == "__main__":
    unittest.main()
