import re
from pathlib import Path

from django.test import SimpleTestCase

APP = Path(__file__).resolve().parent.parent
CSS_FILE = APP / "static" / "terminal" / "app.css"


class DesignSystemTests(SimpleTestCase):
    def test_no_inline_styles_or_handlers(self):  # UI-1
        for template in (APP / "templates").rglob("*.html"):
            text = template.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"\sstyle=", template.name)
            self.assertNotRegex(text, r"\son[a-z]+=", template.name)

    def test_tokens_and_button_states(self):  # UI-2
        css = CSS_FILE.read_text(encoding="utf-8")
        tokens = ["--color-bg", "--color-ready", "--color-running", "--color-paused", "--color-waiting",
                  "--color-error", "--tap-primary", "--tap-min", "--gap"]  # fmt: skip
        for token in tokens:
            self.assertIn(f"{token}:", css, token)
        self.assertRegex(css, r"--tap-primary:\s*(6[4-9]|[7-9]\d)px")
        self.assertRegex(css, r"--tap-min:\s*(4[8-9]|[5-9]\d)px")
        for state in (":hover", ":active", ":focus-visible", ":disabled"):
            self.assertRegex(css, r"\.btn[^{]*" + re.escape(state), state)
