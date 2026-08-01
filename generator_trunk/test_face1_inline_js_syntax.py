from pathlib import Path
import re
import shutil
import subprocess

import pytest


def test_original_face_inline_javascript_is_syntactically_valid(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    html = (Path(__file__).resolve().parent / "intake" / "face1.html").read_text(encoding="utf-8")
    blocks = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", html, flags=re.DOTALL | re.IGNORECASE)
    target = tmp_path / "face1-inline.js"
    target.write_text("\n".join(blocks), encoding="utf-8")
    result = subprocess.run([node, "--check", str(target)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
