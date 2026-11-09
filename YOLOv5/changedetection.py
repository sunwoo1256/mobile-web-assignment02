"""
객체 변화 감지 후 PhotoBlog 서버(Django REST API)로 검출 이미지를 업로드한다.

환경변수
  PHOTOBLOG_HOST      서버 주소 (기본 http://127.0.0.1:8000)
  PHOTOBLOG_USERNAME  업로드에 사용할 계정
  PHOTOBLOG_PASSWORD  계정 비밀번호
"""

import os
import pathlib
from datetime import datetime

import cv2
import requests

HOST = os.environ.get("PHOTOBLOG_HOST", "http://127.0.0.1:8000").rstrip("/")
USERNAME = os.environ.get("PHOTOBLOG_USERNAME", "")
PASSWORD = os.environ.get("PHOTOBLOG_PASSWORD", "")


def log(msg):
    print(f"[ChangeDetection] {msg}", flush=True)


class ChangeDetection:
    result_prev = []
    HOST = HOST
    token = None
    title = ""
    text = ""

    def __init__(self, names):
        # 최신 YOLOv5의 names는 {0: 'person', ...} 형태의 dict이므로 리스트로 맞춘다
        self.names = list(names.values()) if isinstance(names, dict) else list(names)
        self.result_prev = [0 for _ in range(len(self.names))]
        self.token = self.get_token()

    def get_token(self):
        if not USERNAME or not PASSWORD:
            log("PHOTOBLOG_USERNAME / PHOTOBLOG_PASSWORD 환경변수가 없어 업로드하지 않습니다")
            return None
        try:
            res = requests.post(
                self.HOST + "/api-token-auth/",
                data={"username": USERNAME, "password": PASSWORD},
                timeout=5,
            )
            res.raise_for_status()
            token = res.json()["token"]
            log(f"토큰 발급 성공 ({self.HOST}, {USERNAME})")
            return token
        except (requests.RequestException, KeyError, ValueError) as e:
            log(f"토큰 발급 실패: {e}")
            return None

    def add(self, names, detected_current, save_dir, image):
        self.title = ""
        self.text = ""
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

        if self.token is None:
            self.token = self.get_token()
            if self.token is None:
                log(f"토큰이 없어 전송 생략 (이미지만 저장: {full_path})")
                return

        headers = {"Authorization": "Token " + self.token, "Accept": "application/json"}
        data = {
            "title": self.title,
            "text": self.text,
            "created_date": now.isoformat(),
            "published_date": now.isoformat(),
        }
        try:
            with open(full_path, "rb") as f:
                res = requests.post(
                    self.HOST + "/api_root/Post/", data=data, files={"image": f}, headers=headers, timeout=10
                )
            if res.status_code == 201:
                log(f"전송 성공: {self.title} ({self.text.rstrip(', ')})")
            else:
                log(f"전송 실패: HTTP {res.status_code} {res.text[:200]}")
                if res.status_code == 401:
                    self.token = None  # 다음 전송 때 토큰 재발급
        except requests.RequestException as e:
            log(f"전송 실패: {e}")
