"""
편의 기능 1: 객체 추적 + 침입 구역(진입/배회) 감지

- Tracker      : IoU(겹침 비율) → 중심점 거리 순으로 프레임 간 박스를 짝지어 객체마다 고정 ID를 부여한다.
                 min_hits 프레임 연속 검출돼야 확정(오탐 억제), max_age 프레임 동안 안 보이면 삭제한다.
- ZoneMonitor  : 확정된 트랙의 발 위치(박스 하단 중앙)가 다각형 구역 안에 있는지 판정해
                 '진입'(구역 밖 → 안), '배회'(구역 안에 loiter_sec초 이상) 이벤트를 트랙당 한 번씩 만든다.
- draw_overlay : 구역·트랙 ID·체류 시간·업로드 대기 수를 영상에 그린다.

박스 형식은 [x1, y1, x2, y2, conf, cls] (픽셀 좌표), 구역은 화면 크기에 대한 비율 좌표 [(x, y), ...] 이다.
"""

import math
import time

ENTER = "enter"
LOITER = "loiter"


# ---------------------------------------------------------------- 기하 함수


def iou(a, b):
    """두 박스 (x1, y1, x2, y2)의 IoU(교집합/합집합). 겹치지 않으면 0"""
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter == 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter)


def center(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def bottom_center(box):
    """사람의 발 위치에 해당하는 박스 하단 중앙"""
    return ((box[0] + box[2]) / 2, box[3])


def diagonal(box):
    return math.hypot(box[2] - box[0], box[3] - box[1])


def point_in_polygon(point, polygon):
    """레이 캐스팅: 점에서 오른쪽으로 그은 반직선이 변과 홀수 번 만나면 내부"""
    x, y = point
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            x_cross = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_cross:
                inside = not inside
    return inside


def parse_zone(text):
    """'x1,y1;x2,y2;x3,y3' (0~1 비율 좌표) → [(x1, y1), ...]. 점이 3개 미만이거나 범위를 벗어나면 ValueError"""
    points = []
    for part in text.replace(" ", "").strip(";").split(";"):
        try:
            x, y = (float(v) for v in part.split(","))
        except ValueError:
            raise ValueError(f"구역 좌표 형식 오류: '{part}' (예: 0.5,0;1,0;1,1;0.5,1)") from None
        if not (0 <= x <= 1 and 0 <= y <= 1):
            raise ValueError(f"구역 좌표는 0~1 비율이어야 합니다: '{part}'")
        points.append((x, y))
    if len(points) < 3:
        raise ValueError("구역은 점이 3개 이상인 다각형이어야 합니다")
    return points


# ---------------------------------------------------------------- 추적기


class Track:
    def __init__(self, track_id, box, conf, cls):
        self.id = track_id
        self.box = box
        self.conf = conf
        self.cls = cls
        self.hits = 1  # 연속 검출 프레임 수
        self.misses = 0  # 연속 미검출 프레임 수
        self.confirmed = False

    @property
    def visible(self):
        """이번 프레임에 검출된 확정 트랙"""
        return self.confirmed and self.misses == 0

    def __repr__(self):
        return f"Track(#{self.id}, cls={self.cls}, hits={self.hits}, misses={self.misses})"


class Tracker:
    def __init__(self, iou_threshold=0.3, max_center_dist=1.0, min_hits=3, max_age=15):
        """
        iou_threshold   : 1차 매칭에 필요한 최소 IoU
        max_center_dist : 2차 매칭 허용 거리(트랙 박스 대각선 길이의 배수). 저FPS에서 박스가 크게 움직일 때 대비
        min_hits        : 확정에 필요한 연속 검출 프레임 수
        max_age         : 확정 트랙을 유지할 최대 연속 미검출 프레임 수
        """
        self.iou_threshold = iou_threshold
        self.max_center_dist = max_center_dist
        self.min_hits = min_hits
        self.max_age = max_age
        self.tracks = []
        self._next_id = 1

    def update(self, detections):
        """detections: [[x1, y1, x2, y2, conf, cls], ...] → 현재 유지 중인 트랙 목록"""
        dets = [(tuple(float(v) for v in d[:4]), float(d[4]), int(d[5])) for d in detections]
        unmatched_tracks = set(range(len(self.tracks)))
        unmatched_dets = set(range(len(dets)))

        # 1차: 같은 클래스끼리 IoU가 큰 쌍부터 짝짓기
        pairs = []
        for ti, t in enumerate(self.tracks):
            for di, (box, _, cls) in enumerate(dets):
                if t.cls == cls:
                    score = iou(t.box, box)
                    if score >= self.iou_threshold:
                        pairs.append((-score, ti, di))
        matches = self._greedy(pairs, unmatched_tracks, unmatched_dets)

        # 2차: 남은 것끼리 중심점 거리가 가까운 쌍부터 짝짓기 (빠르게 움직여 IoU가 0이 된 경우)
        pairs = []
        for ti in unmatched_tracks:
            t = self.tracks[ti]
            limit = self.max_center_dist * diagonal(t.box)
            for di in unmatched_dets:
                box, _, cls = dets[di]
                if t.cls == cls:
                    dist = math.dist(center(t.box), center(box))
                    if dist <= limit:
                        pairs.append((dist, ti, di))
        matches += self._greedy(pairs, unmatched_tracks, unmatched_dets)

        for ti, di in matches:
            t = self.tracks[ti]
            t.box, t.conf, _ = dets[di]
            t.hits += 1
            t.misses = 0
            if t.hits >= self.min_hits:
                t.confirmed = True

        survivors = []
        for ti, t in enumerate(self.tracks):
            if ti in unmatched_tracks:
                t.misses += 1
                # 확정 전 트랙은 한 번이라도 놓치면 오탐으로 보고 버린다
                if not t.confirmed or t.misses > self.max_age:
                    continue
            survivors.append(t)

        for di in sorted(unmatched_dets):
            box, conf, cls = dets[di]
            t = Track(self._next_id, box, conf, cls)
            self._next_id += 1
            t.confirmed = self.min_hits <= 1
            survivors.append(t)

        self.tracks = survivors
        return self.tracks

    @staticmethod
    def _greedy(pairs, unmatched_tracks, unmatched_dets):
        matches = []
        for _, ti, di in sorted(pairs):
            if ti in unmatched_tracks and di in unmatched_dets:
                matches.append((ti, di))
                unmatched_tracks.discard(ti)
                unmatched_dets.discard(di)
        return matches


# ---------------------------------------------------------------- 침입 구역


class ZoneEvent:
    def __init__(self, kind, track, dwell):
        self.kind = kind  # ENTER / LOITER
        self.track = track
        self.dwell = dwell  # 구역 안 체류 시간(초)

    def label(self, names):
        name = names[self.track.cls] if 0 <= self.track.cls < len(names) else str(self.track.cls)
        if self.kind == ENTER:
            return f"[진입] {name} #{self.track.id}"
        return f"[배회] {name} #{self.track.id} ({self.dwell:.0f}s)"

    def __repr__(self):
        return f"ZoneEvent({self.kind}, #{self.track.id}, {self.dwell:.1f}s)"


class _ZoneState:
    def __init__(self):
        self.inside = False
        self.since = None  # 이번에 구역에 들어온 시각
        self.enter_sent = False
        self.loiter_sent = False


class ZoneMonitor:
    def __init__(self, zone, loiter_sec=5.0, clock=time.monotonic):
        self.zone = zone
        self.loiter_sec = loiter_sec
        self.clock = clock
        self.states = {}  # track id → _ZoneState

    def is_inside(self, box, width, height):
        x, y = bottom_center(box)
        return point_in_polygon((x / width, y / height), self.zone)

    def dwell(self, track_id):
        state = self.states.get(track_id)
        if state is None or not state.inside:
            return 0.0
        return self.clock() - state.since

    def update(self, tracks, width, height):
        """이번 프레임에서 새로 발생한 이벤트 목록을 반환한다. 이벤트는 종류별로 트랙당 한 번만 발생한다"""
        now = self.clock()
        events = []
        alive = set()
        for t in tracks:
            alive.add(t.id)
            if not t.visible:  # 잠깐 놓친 프레임은 상태를 유지한다
                continue
            state = self.states.setdefault(t.id, _ZoneState())
            inside = self.is_inside(t.box, width, height)

            if inside and not state.inside:
                state.inside, state.since = True, now
                if not state.enter_sent:
                    state.enter_sent = True
                    events.append(ZoneEvent(ENTER, t, 0.0))
            elif not inside and state.inside:
                state.inside, state.since = False, None

            if state.inside and not state.loiter_sent and now - state.since >= self.loiter_sec:
                state.loiter_sent = True
                events.append(ZoneEvent(LOITER, t, now - state.since))

        for track_id in list(self.states):
            if track_id not in alive:
                del self.states[track_id]
        return events


# ---------------------------------------------------------------- 화면 표시


def draw_overlay(image, zone, tracks, monitor, queue_size):
    """구역(반투명 빨강), 트랙 ID·체류 시간, 상단 상태줄을 image에 직접 그린다"""
    import cv2
    import numpy as np

    h, w = image.shape[:2]
    pts = np.array([[int(x * w), int(y * h)] for x, y in zone], dtype=np.int32)
    overlay = image.copy()
    cv2.fillPoly(overlay, [pts], (0, 0, 255))
    cv2.addWeighted(overlay, 0.2, image, 0.8, 0, dst=image)
    cv2.polylines(image, [pts], True, (0, 0, 255), 2)

    visible = [t for t in tracks if t.visible]
    for t in visible:
        inside = monitor.is_inside(t.box, w, h)
        color = (0, 0, 255) if inside else (0, 200, 0)
        x1, y1 = int(t.box[0]), int(t.box[1])
        foot = tuple(int(v) for v in bottom_center(t.box))
        label = f"#{t.id}" + (f" {monitor.dwell(t.id):.0f}s" if inside else "")
        cv2.circle(image, foot, 6, color, -1)
        cv2.putText(image, label, (x1 + 4, y1 + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2, cv2.LINE_AA)

    status = f"ZONE  tracks:{len(visible)}  queue:{queue_size}"
    cv2.rectangle(image, (0, 0), (w, 30), (0, 0, 0), -1)
    cv2.putText(image, status, (8, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
