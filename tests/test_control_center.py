"""Tests for VDL Control Center HTTP and SSE Server."""

import json
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/vdl-verified-development-loop/scripts"))
import control_center as cc
import vdl_events as ve


def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class ControlCenterServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

        self.port = get_free_port()
        self.hub = cc.ControlCenterHub(default_root=self.root)
        cc.ControlCenterHandler.hub = self.hub

        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), cc.ControlCenterHandler)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        time.sleep(0.1)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_ui_html_endpoint(self):
        url = f"http://127.0.0.1:{self.port}/"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            content = resp.read().decode("utf-8")
            self.assertIn("Trung tâm Điều khiển VDL", content)
            self.assertIn("Sơ đồ Chu trình Workflow", content)
            self.assertIn("workflowSvg", content)
            self.assertIn('qa:          { cx:', content)
            self.assertIn('id: "review->qa"', content)
            self.assertIn('id: "qa->complete"', content)

    def test_api_projects_and_state(self):
        # 1. Check projects endpoint
        url = f"http://127.0.0.1:{self.port}/api/projects"
        with urllib.request.urlopen(url) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(any(p["root"] == str(self.root) for p in data["projects"]))

        # 2. Check state endpoint (initially empty)
        state_url = f"http://127.0.0.1:{self.port}/api/state"
        with urllib.request.urlopen(state_url) as resp:
            self.assertEqual(resp.status, 200)
            state = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(len(state["steps"]), 13)
            self.assertEqual(state["steps"][0]["id"], "raw_prompt")

    def test_cross_origin_requests_cannot_read_or_write_events(self):
        base = f"http://127.0.0.1:{self.port}"
        foreign = {"Origin": "https://example.org"}
        for url in ("/api/projects", "/api/state", "/api/events", "/api/stream"):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(urllib.request.Request(base + url, headers=foreign), timeout=2)
            self.assertEqual(caught.exception.code, 403)
            self.assertIsNone(caught.exception.headers.get("Access-Control-Allow-Origin"))
        request = urllib.request.Request(base + "/api/events", data=b"{}", headers=foreign, method="POST")
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=2)
        self.assertEqual(caught.exception.code, 403)
        self.assertFalse((self.root / ".vdl/events.jsonl").exists())

    def test_post_event_and_sse_broadcast(self):
        # Test event post
        ev_data = {
            "event_id": "test-sse-1",
            "project_id": self.hub.register_project(self.root),
            "session_id": "sess-test",
            "event_type": "verification.passed",
            "status": "COMPLETED",
            "source": "script",
            "evidence_reference": ".verified-development-loop/evidence/t1/v1.md",
            "data": {"status": "PASS"},
        }

        post_url = f"http://127.0.0.1:{self.port}/api/events"
        req = urllib.request.Request(
            post_url,
            data=json.dumps(ev_data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 201)
            res = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(res["event_id"], "test-sse-1")

        # Verify state updated
        state_url = f"http://127.0.0.1:{self.port}/api/state"
        with urllib.request.urlopen(state_url) as resp:
            state = json.loads(resp.read().decode("utf-8"))
            step_map = {s["id"]: s for s in state["steps"]}
            self.assertEqual(step_map["verification"]["status"], "COMPLETED")
            self.assertEqual(state["verification"]["status"], "PASS")

        # Verify events query endpoint
        events_url = f"http://127.0.0.1:{self.port}/api/events"
        with urllib.request.urlopen(events_url) as resp:
            evs = json.loads(resp.read().decode("utf-8"))["events"]
            self.assertEqual(len(evs), 1)
            self.assertEqual(evs[0]["event_id"], "test-sse-1")


if __name__ == "__main__":
    unittest.main()
