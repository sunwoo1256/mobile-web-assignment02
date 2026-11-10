"""편의 기능 1(객체 추적 + 침입 구역) 단위 테스트

실행 (YOLOv5 폴더에서): python -m unittest discover -s tests -p "test_edge_*.py" -v
"""

import unittest

import numpy as np

from tracking import (
    ENTER,
    LOITER,
    Tracker,
    ZoneEvent,
    ZoneMonitor,
    bottom_center,
    center,
    diagonal,
    draw_overlay,
    iou,
    parse_zone,
    point_in_polygon,
)

PERSON, CAT = 0, 1
NAMES = ["person", "cat"]
W, H = 640, 480
RIGHT_HALF = [(0.5, 0.0), (1.0, 0.0), (1.0, 1.0), (0.5, 1.0)]


def det(x1, y1, x2, y2, cls=PERSON, conf=0.9):
    return [x1, y1, x2, y2, conf, cls]


def box_at(cx, foot_y=400, w=80, h=200, cls=PERSON):
    """발 위치(박스 하단 중앙)가 (cx, foot_y)인 박스"""
    return det(cx - w / 2, foot_y - h, cx + w / 2, foot_y, cls)


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, sec):
        self.t += sec


class GeometryTest(unittest.TestCase):
    def test_iou_identical(self):
        self.assertAlmostEqual(iou((0, 0, 10, 10), (0, 0, 10, 10)), 1.0)

    def test_iou_disjoint(self):
        self.assertEqual(iou((0, 0, 10, 10), (20, 20, 30, 30)), 0.0)

    def test_iou_touching_edges_is_zero(self):
        self.assertEqual(iou((0, 0, 10, 10), (10, 0, 20, 10)), 0.0)

    def test_iou_partial(self):
        # 교집합 1, 합집합 4 + 4 - 1 = 7
        self.assertAlmostEqual(iou((0, 0, 2, 2), (1, 1, 3, 3)), 1 / 7)

    def test_iou_contained(self):
        self.assertAlmostEqual(iou((0, 0, 10, 10), (0, 0, 5, 10)), 0.5)

    def test_iou_is_symmetric(self):
        a, b = (0, 0, 4, 3), (2, 1, 7, 9)
        self.assertAlmostEqual(iou(a, b), iou(b, a))

    def test_center_bottom_center_diagonal(self):
        box = (10, 20, 50, 80)
        self.assertEqual(center(box), (30, 50))
        self.assertEqual(bottom_center(box), (30, 80))
        self.assertAlmostEqual(diagonal(box), (40**2 + 60**2) ** 0.5)

    def test_point_in_square(self):
        square = [(0, 0), (1, 0), (1, 1), (0, 1)]
        self.assertTrue(point_in_polygon((0.5, 0.5), square))
        self.assertFalse(point_in_polygon((1.5, 0.5), square))
        self.assertFalse(point_in_polygon((0.5, -0.1), square))

    def test_point_in_triangle(self):
        triangle = [(0, 0), (1, 0), (0, 1)]
        self.assertTrue(point_in_polygon((0.2, 0.2), triangle))
        self.assertFalse(point_in_polygon((0.8, 0.8), triangle))

    def test_point_in_concave_polygon(self):
        # L자 모양: 오른쪽 위 사분면이 빠진 다각형
        l_shape = [(0, 0), (0.5, 0), (0.5, 0.5), (1, 0.5), (1, 1), (0, 1)]
        self.assertTrue(point_in_polygon((0.25, 0.25), l_shape))
        self.assertTrue(point_in_polygon((0.75, 0.75), l_shape))
        self.assertFalse(point_in_polygon((0.75, 0.25), l_shape))  # 움푹 들어간 부분


class ParseZoneTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(parse_zone("0.5,0;1,0;1,1;0.5,1"), RIGHT_HALF)

    def test_spaces_and_trailing_semicolon(self):
        self.assertEqual(parse_zone(" 0,0 ; 1,0 ; 0,1 ;"), [(0, 0), (1, 0), (0, 1)])

    def test_too_few_points(self):
        with self.assertRaisesRegex(ValueError, "3개 이상"):
            parse_zone("0,0;1,1")

    def test_out_of_range(self):
        with self.assertRaisesRegex(ValueError, "0~1"):
            parse_zone("0,0;1.5,0;0,1")

    def test_bad_format(self):
        with self.assertRaisesRegex(ValueError, "형식 오류"):
            parse_zone("0,0;1;0,1")
        with self.assertRaisesRegex(ValueError, "형식 오류"):
            parse_zone("a,b;1,0;0,1")


class TrackerTest(unittest.TestCase):
    def test_new_detection_is_tentative_until_min_hits(self):
        tracker = Tracker(min_hits=3)
        for frame in range(2):
            (t,) = tracker.update([det(100, 100, 200, 300)])
            self.assertFalse(t.confirmed, f"frame {frame}")
            self.assertFalse(t.visible)
        (t,) = tracker.update([det(102, 100, 202, 300)])
        self.assertTrue(t.confirmed)
        self.assertTrue(t.visible)
        self.assertEqual(t.id, 1)
        self.assertEqual(t.hits, 3)

    def test_min_hits_one_confirms_immediately(self):
        (t,) = Tracker(min_hits=1).update([det(0, 0, 10, 10)])
        self.assertTrue(t.confirmed)

    def test_tentative_track_dropped_on_first_miss(self):
        """1~2프레임 깜빡 나타난 오탐은 확정되기 전에 사라진다"""
        tracker = Tracker(min_hits=3)
        tracker.update([det(100, 100, 200, 300)])
        tracker.update([det(100, 100, 200, 300)])
        self.assertEqual(tracker.update([]), [])

    def test_id_is_stable_while_moving(self):
        tracker = Tracker(min_hits=1)
        ids = set()
        for x in range(0, 200, 10):  # 프레임마다 10px씩 이동 (IoU 충분)
            (t,) = tracker.update([det(x, 100, x + 100, 300)])
            ids.add(t.id)
        self.assertEqual(ids, {1})

    def test_confirmed_track_survives_short_occlusion(self):
        tracker = Tracker(min_hits=1, max_age=3)
        tracker.update([det(100, 100, 200, 300)])
        for _ in range(3):
            (t,) = tracker.update([])
            self.assertFalse(t.visible)  # 유지는 되지만 이번 프레임에 보이지 않음
        (t,) = tracker.update([det(105, 100, 205, 300)])
        self.assertEqual(t.id, 1)
        self.assertTrue(t.visible)
        self.assertEqual(t.misses, 0)

    def test_confirmed_track_removed_after_max_age(self):
        tracker = Tracker(min_hits=1, max_age=3)
        tracker.update([det(100, 100, 200, 300)])
        for _ in range(3):
            self.assertEqual(len(tracker.update([])), 1)
        self.assertEqual(tracker.update([]), [])
        (t,) = tracker.update([det(100, 100, 200, 300)])
        self.assertEqual(t.id, 2)  # 삭제 후 다시 나타나면 새 ID

    def test_ids_are_never_reused(self):
        tracker = Tracker(min_hits=1, max_age=0)
        seen = []
        for _ in range(4):
            (t,) = tracker.update([det(0, 0, 10, 10)])
            seen.append(t.id)
            tracker.update([])
        self.assertEqual(seen, [1, 2, 3, 4])

    def test_two_objects_keep_their_ids(self):
        tracker = Tracker(min_hits=1)
        tracker.update([det(0, 100, 100, 300), det(400, 100, 500, 300)])
        for step in range(1, 10):
            # 입력 순서를 섞어도 위치로 짝지어진다
            tracks = tracker.update([det(400 - step * 5, 100, 500 - step * 5, 300), det(step * 5, 100, 100 + step * 5, 300)])
            by_id = {t.id: t for t in tracks}
            self.assertLess(by_id[1].box[0], by_id[2].box[0])
        self.assertEqual(len(tracker.tracks), 2)

    def test_different_classes_never_match(self):
        tracker = Tracker(min_hits=1)
        tracker.update([det(100, 100, 200, 300, cls=PERSON)])
        tracks = tracker.update([det(100, 100, 200, 300, cls=CAT)])
        self.assertEqual(sorted((t.id, t.cls) for t in tracks), [(1, PERSON), (2, CAT)])

    def test_fast_motion_matched_by_center_distance(self):
        """저FPS에서 박스가 겹치지 않을 만큼 움직여도 대각선 길이 이내면 같은 객체"""
        tracker = Tracker(min_hits=1, max_center_dist=1.0)
        tracker.update([det(100, 100, 200, 300)])  # 대각선 ≈ 224
        (t,) = tracker.update([det(250, 100, 350, 300)])  # IoU 0, 중심 거리 150
        self.assertEqual(t.id, 1)

    def test_too_far_creates_new_track(self):
        tracker = Tracker(min_hits=1, max_center_dist=1.0)
        tracker.update([det(0, 0, 100, 100)])  # 대각선 ≈ 141
        tracks = tracker.update([det(400, 400, 500, 500)])
        self.assertEqual(sorted(t.id for t in tracks), [1, 2])

    def test_greedy_prefers_highest_iou(self):
        tracker = Tracker(min_hits=1)
        tracker.update([det(100, 100, 200, 300)])
        tracks = tracker.update([det(150, 100, 250, 300), det(101, 100, 201, 300)])
        matched = next(t for t in tracks if t.id == 1)
        self.assertEqual(matched.box[0], 101)

    def test_conf_and_box_updated(self):
        tracker = Tracker(min_hits=1)
        tracker.update([det(0, 0, 100, 100, conf=0.5)])
        (t,) = tracker.update([det(5, 5, 105, 105, conf=0.8)])
        self.assertEqual(t.box, (5, 5, 105, 105))
        self.assertAlmostEqual(t.conf, 0.8)

    def test_repr(self):
        (t,) = Tracker(min_hits=1).update([det(0, 0, 10, 10)])
        self.assertEqual(repr(t), "Track(#1, cls=0, hits=1, misses=0)")
        self.assertEqual(repr(ZoneEvent(LOITER, t, 6.04)), "ZoneEvent(loiter, #1, 6.0s)")

    def test_accepts_tensor_like_values(self):
        """detect.py가 넘기는 torch 텐서처럼 float()/int() 변환이 되는 값을 받는다"""
        values = [np.float32(v) for v in (0, 0, 10, 10, 0.9, 0)]
        (t,) = Tracker(min_hits=1).update([values])
        self.assertEqual(t.cls, 0)
        self.assertIsInstance(t.box[0], float)


class ZoneMonitorTest(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.tracker = Tracker(min_hits=1)
        self.monitor = ZoneMonitor(RIGHT_HALF, loiter_sec=5, clock=self.clock)

    def step(self, *boxes, sec=0.5):
        self.clock.advance(sec)
        tracks = self.tracker.update(list(boxes))
        return self.monitor.update(tracks, W, H)

    def kinds(self, events):
        return [(e.kind, e.track.id) for e in events]

    def test_outside_produces_no_event(self):
        for _ in range(20):
            self.assertEqual(self.step(box_at(100)), [])

    def test_enter_once_then_loiter_once(self):
        for x in (100, 200, 300):  # 구역 밖에서 걸어 들어옴 (300 / 640 = 0.47)
            self.assertEqual(self.step(box_at(x)), [])
        events = self.step(box_at(400))
        self.assertEqual(self.kinds(events), [(ENTER, 1)])
        self.assertEqual(events[0].dwell, 0.0)

        # 4.5초 머무는 동안 추가 이벤트 없음
        for _ in range(9):
            self.assertEqual(self.step(box_at(400)), [])
        events = self.step(box_at(400))  # 체류 5.0초
        self.assertEqual(self.kinds(events), [(LOITER, 1)])
        self.assertAlmostEqual(events[0].dwell, 5.0)

        for _ in range(20):
            self.assertEqual(self.step(box_at(400)), [])

    def test_object_appearing_inside_counts_as_enter(self):
        self.assertEqual(self.kinds(self.step(box_at(500))), [(ENTER, 1)])

    def test_teleport_is_a_different_object(self):
        """한 프레임에 대각선 길이 이상 이동하면 다른 객체로 보고 새 ID로 진입 이벤트를 만든다"""
        self.step(box_at(100))
        self.assertEqual(self.kinds(self.step(box_at(500))), [(ENTER, 2)])

    def test_reenter_does_not_repeat_enter(self):
        self.step(box_at(400))
        self.step(box_at(250))  # 나감
        self.assertEqual(self.step(box_at(400)), [])

    def test_leaving_resets_dwell(self):
        self.step(box_at(400))
        for _ in range(6):  # 3초 체류
            self.step(box_at(400))
        self.step(box_at(250))  # 나감 → 체류 시간 초기화
        self.assertEqual(self.monitor.dwell(1), 0.0)
        self.step(box_at(400))  # 다시 들어옴
        for _ in range(9):  # 4.5초
            self.assertEqual(self.step(box_at(400)), [])
        self.assertEqual(self.kinds(self.step(box_at(400))), [(LOITER, 1)])

    def test_dwell_reports_time_inside(self):
        self.step(box_at(400))
        self.step(box_at(400), sec=2.5)
        self.assertAlmostEqual(self.monitor.dwell(1), 2.5)
        self.assertEqual(self.monitor.dwell(99), 0.0)

    def test_foot_position_decides_inside(self):
        # 박스 대부분은 왼쪽(구역 밖)이지만 발이 구역 안
        wide = det(100, 100, 560, 400)  # 하단 중앙 x = 330 → 0.52
        self.assertEqual(self.kinds(self.step(wide)), [(ENTER, 1)])

    def test_unconfirmed_tracks_are_ignored(self):
        tracker = Tracker(min_hits=3)
        tracks = tracker.update([box_at(400)])
        self.assertEqual(self.monitor.update(tracks, W, H), [])
        tracks = tracker.update([box_at(400)])
        self.assertEqual(self.monitor.update(tracks, W, H), [])
        tracks = tracker.update([box_at(400)])
        self.assertEqual([e.kind for e in self.monitor.update(tracks, W, H)], [ENTER])

    def test_brief_occlusion_keeps_dwell(self):
        self.step(box_at(400))
        self.step(sec=2)  # 가려짐 (트랙 유지, 상태 유지)
        self.step(sec=2)
        events = self.step(box_at(400), sec=1)
        self.assertEqual(self.kinds(events), [(LOITER, 1)])

    def test_state_removed_with_track_and_new_track_gets_events(self):
        self.tracker = Tracker(min_hits=1, max_age=1)
        self.step(box_at(400))
        self.step()
        self.step()  # 트랙 1 삭제
        self.assertNotIn(1, self.monitor.states)
        self.assertEqual(self.kinds(self.step(box_at(400))), [(ENTER, 2)])

    def test_multiple_objects_in_same_frame(self):
        events = self.step(box_at(400), box_at(550), box_at(100))
        self.assertEqual(sorted(self.kinds(events)), [(ENTER, 1), (ENTER, 2)])

    def test_event_labels(self):
        self.step(box_at(400))
        track = self.tracker.tracks[0]
        self.assertEqual(ZoneEvent(ENTER, track, 0).label(NAMES), "[진입] person #1")
        self.assertEqual(ZoneEvent(LOITER, track, 7.4).label(NAMES), "[배회] person #1 (7s)")
        track.cls = 99
        self.assertEqual(ZoneEvent(ENTER, track, 0).label(NAMES), "[진입] 99 #1")


class DrawOverlayTest(unittest.TestCase):
    def test_draws_in_place(self):
        image = np.zeros((H, W, 3), dtype=np.uint8)
        tracker = Tracker(min_hits=1)
        monitor = ZoneMonitor(RIGHT_HALF, clock=FakeClock())
        tracks = tracker.update([box_at(400), box_at(100)])
        monitor.update(tracks, W, H)
        same = image
        draw_overlay(image, RIGHT_HALF, tracks, monitor, queue_size=3)
        self.assertIs(image, same)
        self.assertEqual(image.shape, (H, W, 3))
        self.assertGreater(image[200, 600, 2], 0)  # 구역 내부가 빨갛게 칠해짐
        self.assertEqual(image[200, 50].tolist(), [0, 0, 0])  # 구역 밖 빈 곳은 그대로
        self.assertTrue(image[:30].any())  # 상단 상태줄


if __name__ == "__main__":
    unittest.main()
