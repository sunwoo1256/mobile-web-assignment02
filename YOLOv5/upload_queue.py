"""
편의 기능 2: 오프라인 업로드 큐 + 비동기 전송

검출 루프는 put()으로 이미지와 메타데이터를 디스크(queue_dir)에 저장만 하고 바로 돌아간다.
백그라운드 스레드가 오래된 항목부터 서버로 전송한다.

  201                 → 큐에서 삭제
  연결 실패 / 5xx / 429 → 남겨 두고 1 → 2 → 4 … → max_delay 초 간격으로 재시도 (Retry-After 헤더 우선)
  401                 → 토큰을 다시 발급받아 재시도
  그 밖의 4xx          → queue_dir/failed/ 로 옮기고 사유(.err)를 남긴다

항목은 디스크에 있으므로 서버가 꺼져 있거나 프로그램을 재시작해도 사라지지 않는다.
"""

import itertools
import json
import os
import shutil
import threading
import time
from pathlib import Path

import requests

POSTS_PATH = "/api_root/Post/"

EMPTY = "empty"
SENT = "sent"
RETRY = "retry"
FAILED = "failed"


def log(msg):
    print(f"[UploadQueue] {msg}", flush=True)


def next_delay(prev, base=1.0, maximum=60.0):
    """지수 백오프: 0 → base → 2·base → 4·base … (최대 maximum)"""
    return min(maximum, base if prev <= 0 else prev * 2)


class UploadQueue:
    def __init__(self, host, queue_dir, token_provider, session=None, timeout=10, base_delay=1.0, max_delay=60.0):
        """
        token_provider : 토큰 문자열(실패 시 None)을 돌려주는 함수. 401을 받으면 다시 호출한다
        session        : requests.Session 호환 객체 (테스트에서 가짜 세션 주입)
        """
        self.host = host.rstrip("/")
        self.dir = Path(queue_dir)
        self.failed_dir = self.dir / "failed"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.token_provider = token_provider
        self.session = session or requests.Session()
        self.timeout = timeout
        self.base_delay = base_delay
        self.max_delay = max_delay

        self.token = None
        self.delay = 0.0  # 현재 재시도 대기 시간
        self.retry_after = None  # 서버가 Retry-After로 지정한 대기 시간
        self._seq = itertools.count()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = None

    # ------------------------------------------------------------ 큐 조작

    def put(self, title, text, created, image_bytes):
        """항목을 디스크에 저장하고 전송 스레드를 깨운다. 저장된 메타데이터 파일 경로를 반환한다"""
        stem = f"{created:%Y%m%d-%H%M%S-%f}-{next(self._seq):04d}"
        image_path = self.dir / f"{stem}.jpg"
        meta_path = self.dir / f"{stem}.json"
        image_path.write_bytes(image_bytes)
        meta = {"title": title, "text": text, "created_date": created.isoformat(), "image": image_path.name}
        # 메타데이터를 마지막에 원자적으로 만들어 '반쯤 쓰인 항목'이 전송되지 않게 한다
        tmp = meta_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, meta_path)
        self._wake.set()
        return meta_path

    def pending(self):
        """전송 대기 항목(메타데이터 파일)을 오래된 순서로"""
        return sorted(self.dir.glob("*.json"))

    def __len__(self):
        return len(self.pending())

    def _remove(self, meta_path, image_path):
        meta_path.unlink(missing_ok=True)
        if image_path is not None:
            image_path.unlink(missing_ok=True)

    def _move_to_failed(self, meta_path, image_path, reason):
        self.failed_dir.mkdir(exist_ok=True)
        for path in (meta_path, image_path):
            if path is not None and path.exists():
                shutil.move(str(path), str(self.failed_dir / path.name))
        (self.failed_dir / f"{meta_path.stem}.err").write_text(reason, encoding="utf-8")
        log(f"전송 포기 → failed/{meta_path.name}: {reason}")

    # ------------------------------------------------------------ 전송

    def _ensure_token(self):
        if self.token is None:
            self.token = self.token_provider()
        return self.token

    def process_one(self):
        """가장 오래된 항목 하나를 전송하고 결과(EMPTY/SENT/RETRY/FAILED)를 반환한다"""
        items = self.pending()
        if not items:
            return EMPTY
        meta_path = items[0]
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            image_path = self.dir / meta["image"]
        except (OSError, ValueError, KeyError) as e:
            self._move_to_failed(meta_path, None, f"메타데이터 손상: {e}")
            return FAILED
        if not image_path.exists():
            self._move_to_failed(meta_path, None, "이미지 파일 없음")
            return FAILED

        token = self._ensure_token()
        if token is None:
            log(f"토큰 없음 → 재시도 대기 ({len(items)}건 대기)")
            return RETRY

        data = {
            "title": meta["title"],
            "text": meta["text"],
            "created_date": meta["created_date"],
            "published_date": meta["created_date"],
        }
        headers = {"Authorization": "Token " + token, "Accept": "application/json"}
        try:
            with open(image_path, "rb") as f:
                res = self.session.post(
                    self.host + POSTS_PATH, data=data, files={"image": f}, headers=headers, timeout=self.timeout
                )
        except requests.RequestException as e:
            log(f"서버 연결 실패: {type(e).__name__} ({len(items)}건 대기)")
            return RETRY

        if res.status_code == 201:
            self._remove(meta_path, image_path)
            log(f"전송 성공: {meta['title']} ({len(items) - 1}건 대기)")
            return SENT
        if res.status_code == 401:
            log("토큰 만료/무효(401) → 재발급 후 재시도")
            self.token = None
            return RETRY
        if res.status_code == 429 or res.status_code >= 500:
            self.retry_after = _retry_after(res)
            log(f"서버 응답 {res.status_code} → 재시도 ({len(items)}건 대기)")
            return RETRY
        self._move_to_failed(meta_path, image_path, f"HTTP {res.status_code} {res.text[:300]}")
        return FAILED

    # ------------------------------------------------------------ 백그라운드 스레드

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="UploadQueue", daemon=True)
            self._thread.start()
            count = len(self)
            if count:
                log(f"이전 실행에서 남은 {count}건을 이어서 전송합니다")
        return self

    def stop(self, timeout=5):
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None

    def flush(self, timeout):
        """큐가 빌 때까지 최대 timeout초 기다린다. 비었으면 True"""
        deadline = time.monotonic() + timeout
        while len(self) and time.monotonic() < deadline:
            self._wake.set()
            time.sleep(0.05)
        return len(self) == 0

    def close(self, timeout=5):
        """프로그램 종료 시: 남은 항목을 잠시 더 보내 보고, 못 보낸 항목은 다음 실행으로 넘긴다"""
        if self._thread is not None and len(self):
            log(f"종료 전 남은 {len(self)}건 전송 시도 (최대 {timeout}초)")
            self.flush(timeout)
        self.stop()
        remaining = len(self)
        if remaining:
            log(f"미전송 {remaining}건은 {self.dir}에 보관 → 다음 실행 때 이어서 전송")

    def _run(self):
        while not self._stop.is_set():
            result = self.process_one()
            if result in (SENT, FAILED):
                self.delay = 0.0
            elif result == EMPTY:
                self.delay = 0.0
                self._wake.wait(timeout=5)
                self._wake.clear()
            else:  # RETRY
                self.delay = next_delay(self.delay, self.base_delay, self.max_delay)
                wait = self.retry_after if self.retry_after is not None else self.delay
                self.retry_after = None
                log(f"{wait:.0f}초 후 재시도")
                self._stop.wait(wait)


def _retry_after(res):
    try:
        return max(0.0, float(res.headers.get("Retry-After")))
    except (TypeError, ValueError):
        return None
