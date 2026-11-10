"""편의 기능 2(오프라인 업로드 큐 + 비동기 전송) 단위 테스트

실행 (YOLOv5 폴더에서): python -m unittest discover -s tests -p "test_edge_*.py" -v
"""

import io
import json
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path

import requests

from upload_queue import EMPTY, FAILED, RETRY, SENT, UploadQueue, next_delay

HOST = "http://server:8000"
T0 = datetime(2026, 11, 10, 9, 30, 0, 123456)


class FakeResponse:
    def __init__(self, status_code, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}


class FakeSession:
    """responses: FakeResponse / 예외 인스턴스 목록. 다 쓰면 마지막 것을 반복한다"""

    def __init__(self, *responses):
        self.responses = list(responses) or [FakeResponse(201)]
        self.calls = []
        self.lock = threading.Lock()

    def post(self, url, data=None, files=None, headers=None, timeout=None):
        with self.lock:
            self.calls.append(
                {"url": url, "data": dict(data), "image": files["image"].read(), "headers": headers, "timeout": timeout}
            )
            res = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(res, Exception):
            raise res
        return res


class TokenProvider:
    def __init__(self, *tokens):
        self.tokens = list(tokens) or ["tok"]
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.tokens.pop(0) if len(self.tokens) > 1 else self.tokens[0]


class QueueTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "queue"

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, *responses, tokens=("tok",), **kwargs):
        self.session = FakeSession(*responses)
        self.tokens = TokenProvider(*tokens)
        return UploadQueue(HOST, self.dir, self.tokens, session=self.session, **kwargs)


class PutTest(QueueTestCase):
    def test_put_writes_image_and_metadata(self):
        q = self.make()
        meta_path = q.put("[진입] person #1", "[진입] person #1", T0, b"JPEG")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        self.assertEqual(meta["title"], "[진입] person #1")
        self.assertEqual(meta["created_date"], "2026-11-10T09:30:00.123456")
        self.assertEqual((self.dir / meta["image"]).read_bytes(), b"JPEG")
        self.assertEqual(len(q), 1)

    def test_put_leaves_no_temp_file(self):
        q = self.make()
        q.put("a", "a", T0, b"x")
        self.assertEqual(list(self.dir.glob("*.tmp")), [])

    def test_pending_is_ordered_oldest_first(self):
        q = self.make()
        q.put("later", "", T0 + timedelta(seconds=5), b"2")
        q.put("earlier", "", T0, b"1")
        titles = [json.loads(p.read_text(encoding="utf-8"))["title"] for p in q.pending()]
        self.assertEqual(titles, ["earlier", "later"])

    def test_same_timestamp_does_not_collide(self):
        q = self.make()
        q.put("a", "", T0, b"1")
        q.put("b", "", T0, b"2")
        self.assertEqual(len(q), 2)

    def test_creates_queue_dir(self):
        self.assertFalse(self.dir.exists())
        self.make()
        self.assertTrue(self.dir.is_dir())


class ProcessOneTest(QueueTestCase):
    def test_empty(self):
        q = self.make()
        self.assertEqual(q.process_one(), EMPTY)
        self.assertEqual(self.session.calls, [])

    def test_success_sends_and_removes(self):
        q = self.make(FakeResponse(201))
        q.put("[진입] person #1", "[진입] person #1", T0, b"JPEG")
        self.assertEqual(q.process_one(), SENT)
        self.assertEqual(len(q), 0)
        self.assertEqual(list(self.dir.glob("*.jpg")), [])

        (call,) = self.session.calls
        self.assertEqual(call["url"], HOST + "/api_root/Post/")
        self.assertEqual(call["headers"]["Authorization"], "Token tok")
        self.assertEqual(call["image"], b"JPEG")
        self.assertEqual(
            call["data"],
            {
                "title": "[진입] person #1",
                "text": "[진입] person #1",
                "created_date": "2026-11-10T09:30:00.123456",
                "published_date": "2026-11-10T09:30:00.123456",
            },
        )
        self.assertIsNotNone(call["timeout"])

    def test_host_trailing_slash_is_trimmed(self):
        q = UploadQueue(HOST + "/", self.dir, TokenProvider(), session=FakeSession())
        q.put("a", "", T0, b"x")
        q.process_one()
        self.assertEqual(q.session.calls[0]["url"], HOST + "/api_root/Post/")

    def test_sends_oldest_first(self):
        q = self.make()
        q.put("second", "", T0 + timedelta(seconds=1), b"2")
        q.put("first", "", T0, b"1")
        q.process_one()
        q.process_one()
        self.assertEqual([c["data"]["title"] for c in self.session.calls], ["first", "second"])

    def test_connection_error_keeps_item(self):
        q = self.make(requests.ConnectionError("refused"))
        q.put("a", "", T0, b"x")
        self.assertEqual(q.process_one(), RETRY)
        self.assertEqual(len(q), 1)

    def test_timeout_keeps_item(self):
        q = self.make(requests.Timeout("slow"))
        q.put("a", "", T0, b"x")
        self.assertEqual(q.process_one(), RETRY)
        self.assertEqual(len(q), 1)

    def test_server_error_keeps_item(self):
        q = self.make(FakeResponse(503))
        q.put("a", "", T0, b"x")
        self.assertEqual(q.process_one(), RETRY)
        self.assertEqual(len(q), 1)
        self.assertIsNone(q.retry_after)

    def test_429_respects_retry_after(self):
        q = self.make(FakeResponse(429, headers={"Retry-After": "7"}))
        q.put("a", "", T0, b"x")
        self.assertEqual(q.process_one(), RETRY)
        self.assertEqual(q.retry_after, 7.0)

    def test_invalid_retry_after_is_ignored(self):
        q = self.make(FakeResponse(429, headers={"Retry-After": "Wed, 21 Oct 2026"}))
        q.put("a", "", T0, b"x")
        q.process_one()
        self.assertIsNone(q.retry_after)

    def test_401_refreshes_token_then_succeeds(self):
        q = self.make(FakeResponse(401), FakeResponse(201), tokens=("old", "new"))
        q.put("a", "", T0, b"x")
        self.assertEqual(q.process_one(), RETRY)
        self.assertIsNone(q.token)
        self.assertEqual(q.process_one(), SENT)
        self.assertEqual(self.tokens.calls, 2)
        self.assertEqual(
            [c["headers"]["Authorization"] for c in self.session.calls], ["Token old", "Token new"]
        )

    def test_token_is_cached_between_sends(self):
        q = self.make()
        for i in range(3):
            q.put(str(i), "", T0 + timedelta(seconds=i), b"x")
        for _ in range(3):
            q.process_one()
        self.assertEqual(self.tokens.calls, 1)

    def test_preset_token_is_used(self):
        q = self.make()
        q.token = "given"
        q.put("a", "", T0, b"x")
        q.process_one()
        self.assertEqual(self.tokens.calls, 0)
        self.assertEqual(self.session.calls[0]["headers"]["Authorization"], "Token given")

    def test_no_token_retries_without_request(self):
        q = self.make(tokens=(None,))
        q.put("a", "", T0, b"x")
        self.assertEqual(q.process_one(), RETRY)
        self.assertEqual(self.session.calls, [])
        self.assertEqual(len(q), 1)

    def test_client_error_moves_to_failed(self):
        q = self.make(FakeResponse(400, text='{"image": ["invalid"]}'))
        meta_path = q.put("a", "", T0, b"x")
        self.assertEqual(q.process_one(), FAILED)
        self.assertEqual(len(q), 0)
        failed = q.failed_dir
        self.assertTrue((failed / meta_path.name).exists())
        self.assertTrue((failed / meta_path.with_suffix(".jpg").name).exists())
        self.assertIn("HTTP 400", (failed / f"{meta_path.stem}.err").read_text(encoding="utf-8"))

    def test_failed_item_does_not_block_next(self):
        q = self.make(FakeResponse(400), FakeResponse(201))
        q.put("bad", "", T0, b"x")
        q.put("good", "", T0 + timedelta(seconds=1), b"y")
        self.assertEqual(q.process_one(), FAILED)
        self.assertEqual(q.process_one(), SENT)
        self.assertEqual(q.process_one(), EMPTY)

    def test_corrupt_metadata_moves_to_failed(self):
        q = self.make()
        self.dir.joinpath("20260101-000000-000000-0000.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(q.process_one(), FAILED)
        self.assertEqual(len(q), 0)
        self.assertIn("손상", next(q.failed_dir.glob("*.err")).read_text(encoding="utf-8"))

    def test_missing_image_moves_to_failed(self):
        q = self.make()
        meta_path = q.put("a", "", T0, b"x")
        meta_path.with_suffix(".jpg").unlink()
        self.assertEqual(q.process_one(), FAILED)
        self.assertEqual(self.session.calls, [])

    def test_items_survive_restart(self):
        """서버가 꺼진 상태에서 쌓인 항목은 프로그램을 다시 켜도 남아 있다가 전송된다"""
        offline = self.make(requests.ConnectionError())
        offline.put("a", "", T0, b"1")
        offline.put("b", "", T0 + timedelta(seconds=1), b"2")
        offline.process_one()

        restarted = self.make(FakeResponse(201))
        self.assertEqual(len(restarted), 2)
        self.assertEqual(restarted.process_one(), SENT)
        self.assertEqual(restarted.process_one(), SENT)
        self.assertEqual([c["image"] for c in self.session.calls], [b"1", b"2"])


class BackoffTest(unittest.TestCase):
    def test_exponential_with_cap(self):
        delays, d = [], 0.0
        for _ in range(9):
            d = next_delay(d, base=1, maximum=60)
            delays.append(d)
        self.assertEqual(delays, [1, 2, 4, 8, 16, 32, 60, 60, 60])

    def test_custom_base(self):
        self.assertEqual(next_delay(0, base=0.5, maximum=10), 0.5)
        self.assertEqual(next_delay(0.5, base=0.5, maximum=10), 1.0)


def wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


class BackgroundThreadTest(QueueTestCase):
    def test_worker_drains_queue(self):
        q = self.make(FakeResponse(201)).start()
        try:
            for i in range(3):
                q.put(str(i), "", T0 + timedelta(seconds=i), b"x")
            self.assertTrue(wait_until(lambda: len(q) == 0))
            self.assertEqual([c["data"]["title"] for c in self.session.calls], ["0", "1", "2"])
        finally:
            q.stop()

    def test_put_does_not_wait_for_slow_server(self):
        """서버가 느려도 put()은 즉시 반환된다 (검출 루프가 멈추지 않음)"""
        release = threading.Event()

        class SlowSession(FakeSession):
            def post(self, *args, **kwargs):
                release.wait(5)
                return super().post(*args, **kwargs)

        q = UploadQueue(HOST, self.dir, TokenProvider(), session=SlowSession()).start()
        try:
            q.put("first", "", T0, b"x")
            time.sleep(0.05)  # 스레드가 첫 항목 전송에 들어가 대기 중
            started = time.monotonic()
            for i in range(5):
                q.put(str(i), "", T0 + timedelta(seconds=i + 1), b"x")
            self.assertLess(time.monotonic() - started, 0.5)
            release.set()
            self.assertTrue(wait_until(lambda: len(q) == 0))
        finally:
            release.set()
            q.stop()

    def test_offline_then_recovers(self):
        """서버가 꺼져 있는 동안 재시도하다가 살아나면 밀린 항목을 모두 보낸다"""
        down = requests.ConnectionError("refused")
        q = self.make(down, down, down, FakeResponse(201), base_delay=0.01, max_delay=0.05).start()
        try:
            q.put("a", "", T0, b"1")
            q.put("b", "", T0 + timedelta(seconds=1), b"2")
            self.assertTrue(wait_until(lambda: len(q) == 0))
            self.assertEqual(len(self.session.calls), 5)  # 실패 3번 + 성공 2번
            self.assertEqual(q.delay, 0.0)  # 성공하면 백오프 초기화
        finally:
            q.stop()

    def test_resumes_items_left_from_previous_run(self):
        self.make().put("left over", "", T0, b"x")
        q = self.make(FakeResponse(201)).start()
        try:
            self.assertTrue(wait_until(lambda: len(q) == 0))
            self.assertEqual(self.session.calls[0]["data"]["title"], "left over")
        finally:
            q.stop()

    def test_stop_interrupts_long_backoff(self):
        q = self.make(requests.ConnectionError(), base_delay=30, max_delay=60).start()
        q.put("a", "", T0, b"x")
        self.assertTrue(wait_until(lambda: len(self.session.calls) >= 1))
        started = time.monotonic()
        q.stop()
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual(len(q), 1)  # 보내지 못한 항목은 디스크에 남는다

    def test_close_sends_remaining_before_exit(self):
        q = self.make(FakeResponse(201)).start()
        for i in range(3):
            q.put(str(i), "", T0 + timedelta(seconds=i), b"x")
        with redirect_stdout(io.StringIO()):
            q.close(timeout=5)
        self.assertEqual(len(q), 0)
        self.assertIsNone(q._thread)

    def test_close_keeps_unsent_items_when_offline(self):
        q = self.make(requests.ConnectionError(), base_delay=30).start()
        q.put("a", "", T0, b"x")
        started = time.monotonic()
        with redirect_stdout(io.StringIO()) as out:
            q.close(timeout=0.3)
        self.assertLess(time.monotonic() - started, 3)
        self.assertEqual(len(q), 1)
        self.assertIn("다음 실행", out.getvalue())

    def test_flush_returns_immediately_when_empty(self):
        q = self.make()
        self.assertTrue(q.flush(timeout=5))

    def test_start_is_idempotent(self):
        q = self.make()
        q.start()
        thread = q._thread
        q.start()
        self.assertIs(q._thread, thread)
        q.stop()


if __name__ == "__main__":
    unittest.main()
