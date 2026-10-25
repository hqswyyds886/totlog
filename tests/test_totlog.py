#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""totlog 的最小自测。合成日志，不含任何真实用户数据。

跑：python tests/test_totlog.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import totlog  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample.log")


class TestTotlog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rep = totlog.parse_log(FIXTURE)

    def test_engine_detected(self):
        """引擎行没有时间戳前缀，必须在通用行解析之前提取。"""
        self.assertEqual(self.rep.meta.engine, "4.27.1-260801+release-7-1")
        self.assertEqual(self.rep.meta.build, "release-7-1-CL-260801")

    def test_timestamps_parsed(self):
        """时间戳带毫秒段，解析不能返回 None。"""
        self.assertIsNotNone(self.rep.meta.first_ts)
        self.assertIsNotNone(self.rep.meta.last_ts)
        self.assertGreater(self.rep.meta.span_seconds, 0)

    def test_eac_sessions(self):
        """两段 BeginSession/EndSession，且 Mode 被正确读到。"""
        self.assertEqual(len(self.rep.eac), 2)
        self.assertTrue(self.rep.eac[0].begin_ok)
        self.assertTrue(self.rep.eac[0].closed)
        self.assertEqual(self.rep.eac[0].mode, 1)
        self.assertEqual(self.rep.eac[1].mode, 0)
        self.assertAlmostEqual(self.rep.eac[0].duration, 3600.0, delta=1.0)

    def test_map_switch_vs_streaming(self):
        """Browse 是关卡切换；>>> 是 streaming 子关卡，不能混。"""
        self.assertEqual(self.rep.map_sequence, ["Global/MainMenu", "Resort/Resort_Persistent"])
        self.assertEqual(len(self.rep.streamed), 3)

    def test_spawns(self):
        self.assertEqual(len(self.rep.spawns), 3)
        local = [s for s in self.rep.spawns if s.who == "local"]
        self.assertEqual(len(local), 1)
        self.assertAlmostEqual(local[0].x, 562.2, places=1)

    def test_regions(self):
        self.assertIn("us-east-1", self.rep.regions)
        self.assertEqual(self.rep.auto_region, "us-east-1")

    def test_redact_path(self):
        """导出路径不能带真实用户名。用注入的环境变量测，不依赖跑测试的机器。"""
        old_home = os.environ.get("USERPROFILE")
        old_local = os.environ.get("LOCALAPPDATA")
        try:
            # 造一个固定的假家目录，Windows 和 Linux 都要能替换
            os.environ["USERPROFILE"] = r"C:\Users\testuser"
            os.environ["LOCALAPPDATA"] = r"C:\Users\testuser\AppData\Local"

            for raw in (
                r"C:\Users\testuser\AppData\Local\OPP\Saved\Logs\OPP.log",
                "C:/Users/testuser/AppData/Local/OPP/Saved/Logs/OPP.log",  # Linux/macOS 风格
            ):
                out = totlog.redact_path(raw)
                self.assertNotIn("testuser", out, f"未脱敏: {out}")
                self.assertIn("%", out, f"没打上占位符: {out}")
        finally:
            for k, v in (("USERPROFILE", old_home), ("LOCALAPPDATA", old_local)):
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_redact_can_be_disabled(self):
        """--no-redact 时要保留原路径。"""
        old = totlog.REDACT
        try:
            totlog.REDACT = False
            raw = r"C:\Users\testuser\OPP.log"
            self.assertEqual(totlog.redact_path(raw), raw)
        finally:
            totlog.REDACT = old


if __name__ == "__main__":
    unittest.main(verbosity=2)
