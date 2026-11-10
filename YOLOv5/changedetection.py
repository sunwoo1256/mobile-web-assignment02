"""
객체 변화 감지 후 PhotoBlog 서버(Django REST API)로 검출 이미지를 업로드한다.

기본 모드  : 강의자료 방식. 이전 프레임에 없던 클래스가 나타나면 전송한다.
구역 모드  : ZONE 환경변수가 있으면 객체를 추적해 구역 '진입'/'배회' 이벤트만 전송한다 (tracking.py).
전송은 두 모드 모두 디스크 업로드 큐 + 백그라운드 스레드로 처리한다 (upload_queue.py).

환경변수
  PHOTOBLOG_HOST      서버 주소 (기본 http://127.0.0.1:8000)
  PHOTOBLOG_USERNAME  업로드에 사용할 계정
  PHOTOBLOG_PASSWORD  계정 비밀번호
  ZONE                침입 구역 다각형, 0~1 비율 좌표 (예: 0.5,0;1,0;1,1;0.5,1). 없으면 기본 모드
  TRACK_CLASSES       구역 모드에서 추적할 클래스 (기본 person, 쉼표 구분)
  LOITER_SEC          배회로 판단할 체류 시간(초) (기본 5)
  TRACK_MIN_HITS      트랙 확정에 필요한 연속 검출 프레임 수 (기본 3)
  TRACK_MAX_AGE       트랙을 유지할 최대 미검출 프레임 수 (기본 15)
  UPLOAD_QUEUE_DIR    업로드 큐 폴더 (기본 upload_queue)
"""

import atexit
import os
import pathlib
import time
from datetime import datetime

import cv2
import requests

from tracking import Tracker, ZoneMonitor, draw_overlay, parse_zone
from upload_queue import UploadQueue


def log(msg):
    print(f"[ChangeDetection] {msg}", flush=True)


class ChangeDetection:
    result_prev = []
    HOST = None
    token = None
    title = ""
    text = ""

    def __init__(self, names, queue=None, clock=time.monotonic):
        env = os.environ
        self.HOST = env.get("PHOTOBLOG_HOST", "http://127.0.0.1:8000").rstrip("/")
        self.username = env.get("PHOTOBLOG_USERNAME", "")
        self.password = env.get("PHOTOBLOG_PASSWORD", "")

        # 최신 YOLOv5의 names는 {0: 'person', ...} 형태의 dict이므로 리스트로 맞춘다
        self.names = list(names.values()) if isinstance(names, dict) else list(names)
        self.result_prev = [0 for _ in range(len(self.names))]

        if queue is None:
            self.token = self.get_token()
            queue_dir = pathlib.Path(os.getcwd()) / env.get("UPLOAD_QUEUE_DIR", "upload_queue")
            queue = UploadQueue(self.HOST, queue_dir, self.get_token)
            queue.token = self.token
            queue.start()
            atexit.register(queue.close)
        self.queue = queue

        self.zone = parse_zone(env["ZONE"]) if env.get("ZONE", "").strip() else None
        self.events = []
        if self.zone is not None:
            wanted = [c.strip() for c in env.get("TRACK_CLASSES", "person").split(",") if c.strip()]
            unknown = [c for c in wanted if c not in self.names]
            if unknown:
                log(f"알 수 없는 TRACK_CLASSES 무시: {', '.join(unknown)}")
            self.track_ids = {self.names.index(c) for c in wanted if c in self.names}
            self.tracker = Tracker(
                min_hits=int(env.get("TRACK_MIN_HITS", "3")), max_age=int(env.get("TRACK_MAX_AGE", "15"))
            )
            self.monitor = ZoneMonitor(self.zone, loiter_sec=float(env.get("LOITER_SEC", "5")), clock=clock)
            log(f"구역 모드: zone={self.zone}, 대상={sorted(self.names[i] for i in self.track_ids)}")

    def get_token(self):
        if not self.username or not self.password:
            log("PHOTOBLOG_USERNAME / PHOTOBLOG_PASSWORD 환경변수가 없어 업로드하지 않습니다")
            return None
        try:
            res = requests.post(
                self.HOST + "/api-token-auth/",
                data={"username": self.username, "password": self.password},
                timeout=5,
            )
            res.raise_for_status()
            token = res.json()["token"]
            log(f"토큰 발급 성공 ({self.HOST}, {self.username})")
            return token
        except requests.HTTPError as e:
            log(f"토큰 발급 실패: {e.response.status_code if e.response is not None else e} (계정/비밀번호 확인)")
        except requests.RequestException as e:
            log(f"토큰 발급 실패: 서버 연결 불가 ({type(e).__name__})")
        except (KeyError, ValueError) as e:
            log(f"토큰 발급 실패: 응답 형식 오류 ({e})")
        return None

    def track(self, boxes, image):
        """구역 모드: 박스 [x1, y1, x2, y2, conf, cls]로 트랙을 갱신하고 이벤트를 모은 뒤 영상에 표시한다"""
        if self.zone is None:
            return
        dets = [[float(v) for v in b] for b in boxes]
        dets = [d for d in dets if int(d[5]) in self.track_ids]
        tracks = self.tracker.update(dets)
        h, w = image.shape[:2]
        self.events.extend(self.monitor.update(tracks, w, h))
        draw_overlay(image, self.zone, tracks, self.monitor, len(self.queue))

    def add(self, names, detected_current, save_dir, image):
        self.title = ""
        self.text = ""

        if self.zone is not None:
            self.result_prev = detected_current[:]
            if self.events:
                labels = [e.label(self.names) for e in self.events]
                self.events = []
                self.title = labels[0]
                self.text = "\n".join(labels)
                self.send(save_dir, image)
            return

        change_flag = 0  # 신규 객체 탐지 여부
        for i in range(len(self.result_prev)):
            # 이전 프레임에 없던 객체가 이번 프레임에 나타난 경우
            if self.result_prev[i] == 0 and detected_current[i] == 1:
                change_flag = 1
                self.title = self.names[i]
                self.text += self.names[i] + ", "

        self.result_prev = detected_current[:]  # 객체 검출 상태 저장

        if change_flag == 1:
            self.send(save_dir, image)

    def send(self, save_dir, image):
        now = datetime.now()
        save_path = (
            pathlib.Path(os.getcwd()) / save_dir / "detected" / str(now.year) / str(now.month) / str(now.day)
        )
        save_path.mkdir(parents=True, exist_ok=True)
        full_path = save_path / f"{now.hour}-{now.minute}-{now.second}-{now.microsecond}.jpg"

        dst = cv2.resize(image, dsize=(320, 240), interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(full_path), dst)

        # 전송은 업로드 큐의 백그라운드 스레드가 맡는다 (검출 루프는 기다리지 않음)
        ok, encoded = cv2.imencode(".jpg", dst)
        if not ok:
            log("이미지 인코딩 실패로 전송 생략")
            return
        self.queue.put(self.title, self.text, now, encoded.tobytes())
        log(f"큐에 추가: {self.title} ({len(self.queue)}건 대기)")
