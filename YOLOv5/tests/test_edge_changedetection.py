"""ChangeDetection 통합 테스트: 기본 모드(강의자료 로직) / 구역 모드 / 업로드 큐 연동

실행 (YOLOv5 폴더에서): python -m unittest discover -s tests -p "test_edge_*.py" -v
"""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import cv2
import numpy as np
import requests

from changedetection import ChangeDetection

NAMES = {0: "person", 1: "bicycle", 2: "car", 15: "cat"}  # dict 형태 (최신 YOLOv5)
NAME_LIST = ["person", "bicycle", "car", "cat"]
W, H = 640, 480
BASE_ENV = {"PHOTOBLOG_USERNAME": "", "PHOTOBLOG_PASSWORD": "", "ZONE": ""}


class FakeQueue:
    def __init__(self):
        self.items = []

    def put(self, title, text, created, image_bytes):
        self.items.append({"title": title, "text": text, "created": created, "image": image_bytes})

    def __len__(self):
        return len(self.items)


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def frame():
    return np.zeros((H, W, 3), dtype=np.uint8)


def person_at(cx, foot_y=400, cls=0):
    return [cx - 40, foot_y - 200, cx + 40, foot_y, 0.9, cls]


class ChangeDetectionTestCase(unittest.TestCase):
    env = {}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.save_dir = Path(self.tmp.name) / "runs" / "exp"
        self.queue = FakeQueue()
        self.clock = FakeClock()
        patcher = mock.patch.dict(os.environ, {**BASE_ENV, **self.env})
        patcher.start()
        self.addCleanup(patcher.stop)
        with redirect_stdout(io.StringIO()) as out:
            self.cd = ChangeDetection(NAMES, queue=self.queue, clock=self.clock)
        self.init_log = out.getvalue()

    def tearDown(self):
        self.tmp.cleanup()

    def run_frame(self, *boxes, sec=0.5):
        """detect.py와 같은 순서로 호출: track() → add()"""
        self.clock.t += sec
        detected = [0] * len(NAME_LIST)
        for b in boxes:
            detected[int(b[5])] = 1
        image = frame()
        with redirect_stdout(io.StringIO()):
            self.cd.track(list(boxes), image)
            self.cd.add(NAMES, detected, self.save_dir, image)
        return image

    def titles(self):
        return [item["title"] for item in self.queue.items]


class BasicModeTest(ChangeDetectionTestCase):
    def test_names_dict_converted_to_list(self):
        self.assertEqual(self.cd.names, NAME_LIST)
        self.assertEqual(self.cd.result_prev, [0, 0, 0, 0])
        self.assertIsNone(self.cd.zone)

    def test_new_class_triggers_send(self):
        self.run_frame(person_at(100, cls=0), person_at(300, cls=2))
        (item,) = self.queue.items
        self.assertEqual(item["title"], "car")  # 마지막으로 새로 나타난 클래스
        self.assertEqual(item["text"], "person, car, ")

    def test_persisting_object_sent_once(self):
        for _ in range(5):
            self.run_frame(person_at(100))
        self.assertEqual(self.titles(), ["person"])

    def test_reappearing_object_sent_again(self):
        self.run_frame(person_at(100))
        self.run_frame()
        self.run_frame(person_at(100))
        self.assertEqual(self.titles(), ["person", "person"])

    def test_only_newly_appeared_classes_in_text(self):
        self.run_frame(person_at(100))
        self.run_frame(person_at(100), person_at(300, cls=3))
        self.assertEqual(self.queue.items[1]["text"], "cat, ")

    def test_no_detection_no_send(self):
        for _ in range(3):
            self.run_frame()
        self.assertEqual(self.queue.items, [])

    def test_track_is_noop_without_zone(self):
        image = self.run_frame(person_at(400))
        self.assertFalse(image.any())  # 구역·트랙 표시를 그리지 않음

    def test_send_saves_resized_image_and_queues_jpeg(self):
        self.run_frame(person_at(100))
        saved = list((self.save_dir / "detected").rglob("*.jpg"))
        self.assertEqual(len(saved), 1)
        self.assertEqual(cv2.imread(str(saved[0])).shape, (240, 320, 3))

        item = self.queue.items[0]
        decoded = cv2.imdecode(np.frombuffer(item["image"], np.uint8), cv2.IMREAD_COLOR)
        self.assertEqual(decoded.shape, (240, 320, 3))
        self.assertEqual(saved[0].parent.name, str(item["created"].day))


class TokenTest(ChangeDetectionTestCase):
    def test_no_credentials_returns_none_without_request(self):
        with mock.patch("changedetection.requests.post") as post, redirect_stdout(io.StringIO()):
            self.assertIsNone(self.cd.get_token())
        post.assert_not_called()

    def test_token_success(self):
        self.cd.username, self.cd.password = "yolo", "pw"
        res = mock.Mock(status_code=200)
        res.json.return_value = {"token": "abc"}
        with mock.patch("changedetection.requests.post", return_value=res) as post, redirect_stdout(io.StringIO()):
            self.assertEqual(self.cd.get_token(), "abc")
        self.assertEqual(post.call_args.args[0], "http://127.0.0.1:8000/api-token-auth/")
        self.assertEqual(post.call_args.kwargs["data"], {"username": "yolo", "password": "pw"})

    def test_token_server_down_returns_none(self):
        self.cd.username, self.cd.password = "yolo", "pw"
        with mock.patch("changedetection.requests.post", side_effect=requests.ConnectionError()), redirect_stdout(
            io.StringIO()
        ) as out:
            self.assertIsNone(self.cd.get_token())
        self.assertIn("서버 연결 불가 (ConnectionError)", out.getvalue())

    def test_token_wrong_password_returns_none(self):
        self.cd.username, self.cd.password = "yolo", "bad"
        res = mock.Mock(status_code=400)
        res.raise_for_status.side_effect = requests.HTTPError("400", response=res)
        with mock.patch("changedetection.requests.post", return_value=res), redirect_stdout(io.StringIO()) as out:
            self.assertIsNone(self.cd.get_token())
        self.assertIn("400 (계정/비밀번호 확인)", out.getvalue())

    def test_token_bad_response_returns_none(self):
        self.cd.username, self.cd.password = "yolo", "pw"
        res = mock.Mock(status_code=200)
        res.json.return_value = {"no_token": 1}
        with mock.patch("changedetection.requests.post", return_value=res), redirect_stdout(io.StringIO()) as out:
            self.assertIsNone(self.cd.get_token())
        self.assertIn("응답 형식 오류", out.getvalue())


class HostEnvTest(ChangeDetectionTestCase):
    env = {"PHOTOBLOG_HOST": "https://sunwoo.pythonanywhere.com/"}

    def test_host_from_env(self):
        self.assertEqual(self.cd.HOST, "https://sunwoo.pythonanywhere.com")


class ZoneModeTest(ChangeDetectionTestCase):
    env = {"ZONE": "0.5,0;1,0;1,1;0.5,1", "TRACK_CLASSES": "person", "LOITER_SEC": "5", "TRACK_MIN_HITS": "2"}

    def test_zone_config_loaded(self):
        self.assertEqual(len(self.cd.zone), 4)
        self.assertEqual(self.cd.track_ids, {0})
        self.assertIn("구역 모드", self.init_log)

    def test_enter_and_loiter_posts(self):
        self.run_frame(person_at(100))
        self.run_frame(person_at(100))  # 확정됐지만 구역 밖
        self.run_frame(person_at(250))  # 걸어오는 중 (250 / 640 = 0.39)
        self.assertEqual(self.queue.items, [])

        self.run_frame(person_at(450))  # 구역 진입
        self.assertEqual(self.titles(), ["[진입] person #1"])

        for _ in range(9):  # 4.5초 체류
            self.run_frame(person_at(450))
        self.assertEqual(len(self.queue), 1)
        self.run_frame(person_at(450))  # 5.0초
        self.assertEqual(self.titles(), ["[진입] person #1", "[배회] person #1 (5s)"])

        for _ in range(10):
            self.run_frame(person_at(450))
        self.assertEqual(len(self.queue), 2)

    def test_basic_class_change_not_sent_in_zone_mode(self):
        self.run_frame(person_at(100), person_at(100, cls=2))  # 새 클래스지만 구역 밖
        self.assertEqual(self.queue.items, [])
        self.assertEqual(self.cd.result_prev, [1, 0, 1, 0])

    def test_non_target_class_ignored(self):
        for _ in range(5):
            self.run_frame(person_at(450, cls=3))  # cat
        self.assertEqual(self.queue.items, [])

    def test_flicker_detection_ignored(self):
        """1프레임만 잡힌 오탐은 확정 전 사라져 전송되지 않는다 (TRACK_MIN_HITS=2)"""
        self.run_frame(person_at(450))
        self.run_frame()
        self.run_frame()
        self.assertEqual(self.queue.items, [])

    def test_simultaneous_events_combined_into_one_post(self):
        self.run_frame(person_at(400), person_at(550))
        self.run_frame(person_at(400), person_at(550))
        (item,) = self.queue.items
        self.assertEqual(item["title"], "[진입] person #1")
        self.assertEqual(item["text"].split("\n"), ["[진입] person #1", "[진입] person #2"])

    def test_overlay_drawn_on_uploaded_image(self):
        image = self.run_frame(person_at(450))
        self.assertTrue(image[:30].any())  # 상태줄
        self.assertGreater(image[100, 600, 2], 0)  # 구역 표시


class ZoneTargetClassesTest(ChangeDetectionTestCase):
    env = {"ZONE": "0,0;1,0;1,1;0,1", "TRACK_CLASSES": "person, cat, dragon", "TRACK_MIN_HITS": "1"}

    def test_multiple_classes_and_unknown_warning(self):
        self.assertEqual(self.cd.track_ids, {0, 3})
        self.assertIn("dragon", self.init_log)
        self.run_frame(person_at(300, cls=3))
        self.assertEqual(self.titles(), ["[진입] cat #1"])


class InvalidZoneTest(unittest.TestCase):
    def test_invalid_zone_raises(self):
        with mock.patch.dict(os.environ, {**BASE_ENV, "ZONE": "0,0;1,1"}), redirect_stdout(io.StringIO()):
            with self.assertRaises(ValueError):
                ChangeDetection(NAMES, queue=FakeQueue())


class DefaultQueueTest(unittest.TestCase):
    def test_creates_and_starts_disk_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            qdir = Path(tmp) / "q"
            env = {**BASE_ENV, "UPLOAD_QUEUE_DIR": str(qdir)}
            with mock.patch.dict(os.environ, env), redirect_stdout(io.StringIO()):
                cd = ChangeDetection(NAMES)
                try:
                    self.assertTrue(qdir.is_dir())
                    self.assertIsNotNone(cd.queue._thread)
                    self.assertIsNone(cd.queue.token)  # 계정이 없으면 토큰 없음
                finally:
                    cd.queue.stop()


if __name__ == "__main__":
    unittest.main()
