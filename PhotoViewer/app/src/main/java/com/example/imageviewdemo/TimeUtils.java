package com.example.imageviewdemo;

import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 서버의 ISO-8601 시각("2026-10-16T21:49:49.123+09:00")을 "3분 전" 같은 상대 시간으로 바꾼다.
 * java.time은 API 26+ 이므로(minSdk 24) 직접 파싱한다.
 */
public final class TimeUtils {
    private static final Pattern ISO = Pattern.compile(
            "(\\d{4})-(\\d{2})-(\\d{2})T(\\d{2}):(\\d{2}):(\\d{2})(?:\\.\\d+)?(Z|[+-]\\d{2}:?\\d{2})?");
    private static final long MINUTE = 60_000L;
    private static final long HOUR = 60 * MINUTE;
    private static final long DAY = 24 * HOUR;

    private TimeUtils() {
    }

    /** ISO-8601 → epoch millis. 형식이 맞지 않으면 -1 */
    public static long parseIso(String iso) {
        if (iso == null) {
            return -1;
        }
        Matcher m = ISO.matcher(iso.trim());
        if (!m.matches()) {
            return -1;
        }
        Calendar calendar = Calendar.getInstance(TimeZone.getTimeZone("UTC"));
        calendar.clear();
        calendar.set(Integer.parseInt(m.group(1)), Integer.parseInt(m.group(2)) - 1, Integer.parseInt(m.group(3)),
                Integer.parseInt(m.group(4)), Integer.parseInt(m.group(5)), Integer.parseInt(m.group(6)));
        long millis = calendar.getTimeInMillis();
        String offset = m.group(7);
        if (offset != null && !offset.equals("Z")) {
            String digits = offset.substring(1).replace(":", "");
            int minutes = Integer.parseInt(digits.substring(0, 2)) * 60 + Integer.parseInt(digits.substring(2, 4));
            millis -= (offset.charAt(0) == '-' ? -1 : 1) * minutes * MINUTE;
        }
        return millis;
    }

    public static String relative(String iso) {
        return relative(iso, System.currentTimeMillis(), TimeZone.getDefault());
    }

    /** 1분 미만 "방금 전", 1시간 미만 "N분 전", 하루 미만 "N시간 전", 일주일 미만 "N일 전", 그 이상은 날짜 */
    public static String relative(String iso, long now, TimeZone zone) {
        long time = parseIso(iso);
        if (time < 0) {
            return "";
        }
        long diff = now - time;
        if (diff < MINUTE) {
            return "방금 전";
        }
        if (diff < HOUR) {
            return (diff / MINUTE) + "분 전";
        }
        if (diff < DAY) {
            return (diff / HOUR) + "시간 전";
        }
        if (diff < 7 * DAY) {
            return (diff / DAY) + "일 전";
        }
        SimpleDateFormat format = new SimpleDateFormat("yyyy.MM.dd", Locale.KOREA);
        format.setTimeZone(zone);
        return format.format(new Date(time));
    }
}
