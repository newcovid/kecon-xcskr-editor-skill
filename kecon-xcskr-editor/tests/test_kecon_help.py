from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "kecon_help.py"

TOPIC_HTML = """<html><head><meta http-equiv="Content-Type" content="text/html; charset=gb2312">
<title>chassis topic</title></head><body>
<h1>八差速底盘</h1>
<p>底盘运动分解功能块，根据线速度和角速度解算左右轮速度。</p>
<table>
<tr><td>参数名</td><td>类型</td><td>描述</td></tr>
<tr><td>V_lin</td><td>REAL</td><td>线速度，单位：m/s</td></tr>
<tr><td>V_ang</td><td>REAL</td><td>角速度，单位：rad/s</td></tr>
</table>
<script>var ignored = 1;</script>
</body></html>"""

OTHER_HTML = """<html><head><meta http-equiv="Content-Type" content="text/html; charset=gb2312">
<title>modbus topic</title></head><body>
<p>MODBUS 主站配置说明，勾选控制器 RS485 端口，选择工作模式为主站，
再通过端口配置设置波特率、数据位、校验方式和停止位，然后在串行总线上添加从站。</p>
</body></html>"""

STUB_HTML = """<html><head><meta http-equiv="Content-Type" content="text/html; charset=gb2312">
</head><body><p>x</p></body></html>"""

HHC = """<HTML><BODY>
<UL><LI><OBJECT type="text/sitemap">
<param name="Name" value="基本功能块库">
<param name="Local" value="outline_0.htm">
</OBJECT>
<UL><LI><OBJECT type="text/sitemap">
<param name="Name" value="八差速/舵轮总成底盘">
<param name="Local" value="outline_1.htm">
</OBJECT>
</UL>
<LI><OBJECT type="text/sitemap">
<param name="Name" value="MODBUS 主站配置">
<param name="Local" value="outline_2.htm">
</OBJECT>
</UL>
</BODY></HTML>"""


def run_tool(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=check,
        text=True,
        encoding="utf-8",
        capture_output=True,
    )


class KeconHelpTests(unittest.TestCase):
    def test_search_finds_curated_help_topic(self) -> None:
        result = run_tool("search", "CAN", "--source", "kb")

        self.assertIn("CAN", result.stdout)
        self.assertIn("功能块", result.stdout)
        self.assertIn("原文", result.stdout)

    def make_help_tree(self, root: Path) -> Path:
        source = root / "decompiled"
        source.mkdir()
        (source / "outline_0.htm").write_text(STUB_HTML, encoding="gb2312")
        (source / "outline_1.htm").write_text(TOPIC_HTML, encoding="gb2312")
        (source / "outline_2.htm").write_text(OTHER_HTML, encoding="gb2312")
        (source / "help.hhc").write_text(HHC, encoding="gb2312")
        images = source / "outline_1.files"
        images.mkdir()
        (images / "image001.htm").write_text(TOPIC_HTML, encoding="gb2312")
        return source

    def test_index_extracts_topics_and_toc(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.make_help_tree(root)
            cache = root / "cache"

            built = run_tool("index", "--from-dir", str(source), "--cache-dir", str(cache))
            self.assertIn("HELP_INDEX=OK", built.stdout)
            # The stub page is below the text threshold and the .files tree is skipped.
            self.assertIn("Topics=2", built.stdout)

            listed = run_tool("list", "--cache-dir", str(cache))
            self.assertIn("八差速_舵轮总成底盘", listed.stdout)
            self.assertIn("基本功能块库 > 八差速/舵轮总成底盘", listed.stdout)

            status = run_tool("status", "--cache-dir", str(cache))
            self.assertIn("LocalIndex=OK topics=2", status.stdout)

    def test_search_and_show_use_the_local_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.make_help_tree(root)
            cache = root / "cache"
            run_tool("index", "--from-dir", str(source), "--cache-dir", str(cache))

            found = run_tool("search", "线速度 解算", "--cache-dir", str(cache), "--source", "local")
            self.assertIn("八差速/舵轮总成底盘", found.stdout)
            self.assertNotIn("MODBUS", found.stdout)

            shown = run_tool("show", "八差速_舵轮总成底盘", "--cache-dir", str(cache))
            # Table rows survive as pipe separated lines, and script content does not.
            self.assertIn("V_lin | REAL | 线速度，单位：m/s", shown.stdout)
            self.assertIn("目录: 基本功能块库 > 八差速/舵轮总成底盘", shown.stdout)
            self.assertNotIn("ignored", shown.stdout)

            missing = run_tool("show", "no-such-topic", "--cache-dir", str(cache), check=False)
            self.assertEqual(missing.returncode, 1)

    def test_search_without_local_index_points_at_index_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp) / "empty-cache"
            result = run_tool("search", "CAN", "--cache-dir", str(cache), check=False)
            self.assertIn("index --chm", result.stdout)


if __name__ == "__main__":
    unittest.main()
