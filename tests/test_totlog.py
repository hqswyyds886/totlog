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
        """导出路径不能带真实用户名。"""
        p = os.path.join(os.environ.get("USERPROFILE", "C:\\Users\\x"), "OPP", "Saved", "Logs", "OPP.log")
        out = totlog.redact_path(p)
        self.assertNotIn(os.environ.get("USERPROFILE", "C:\\Users\\x"), out)
        self.assertIn("%USERPROFILE%", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
