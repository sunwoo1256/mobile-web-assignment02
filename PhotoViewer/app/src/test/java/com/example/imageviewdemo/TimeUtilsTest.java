package com.example.imageviewdemo;

import static org.junit.Assert.assertEquals;

import org.junit.Test;

import java.util.TimeZone;

public class TimeUtilsTest {
    private static final TimeZone SEOUL = TimeZone.getTimeZone("Asia/Seoul");
    // 2026-10-16T12:00:00Z
    private static final long NOW = TimeUtils.parseIso("2026-10-16T12:00:00Z");

    @Test
    public void parsesOffsetAndFractionalSeconds() {
        assertEquals(NOW, TimeUtils.parseIso("2026-10-16T21:00:00+09:00"));
        assertEquals(NOW, TimeUtils.parseIso("2026-10-16T21:00:00.982694+09:00"));
        assertEquals(NOW, TimeUtils.parseIso("2026-10-16T07:30:00-0430"));
    }

    @Test
    public void invalidTextReturnsMinusOneAndEmptyRelative() {
        assertEquals(-1, TimeUtils.parseIso("어제"));
        assertEquals(-1, TimeUtils.parseIso(null));
        assertEquals("", TimeUtils.relative("", NOW, SEOUL));
    }

    @Test
    public void relativeTimeBuckets() {
        assertEquals("방금 전", TimeUtils.relative("2026-10-16T20:59:30+09:00", NOW, SEOUL));
        assertEquals("5분 전", TimeUtils.relative("2026-10-16T20:55:00+09:00", NOW, SEOUL));
        assertEquals("3시간 전", TimeUtils.relative("2026-10-16T18:00:00+09:00", NOW, SEOUL));
        assertEquals("2일 전", TimeUtils.relative("2026-10-14T21:00:00+09:00", NOW, SEOUL));
    }

    @Test
    public void olderThanAWeekShowsDateInGivenZone() {
        // 2026-10-01T23:30+09:00 = 서울 기준 10월 1일
        assertEquals("2026.10.01", TimeUtils.relative("2026-10-01T23:30:00+09:00", NOW, SEOUL));
    }

    @Test
    public void futureTimeIsTreatedAsJustNow() {
        assertEquals("방금 전", TimeUtils.relative("2026-10-16T21:05:00+09:00", NOW, SEOUL));
    }
}
