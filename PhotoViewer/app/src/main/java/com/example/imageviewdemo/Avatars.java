package com.example.imageviewdemo;

import android.content.res.ColorStateList;
import android.widget.TextView;

import java.util.Locale;

/** 사용자 이름 첫 글자를 담은 원형 아바타. 이름마다 색이 정해져 있어 누가 썼는지 한눈에 구분된다 */
public final class Avatars {
    private static final int[] COLORS = {
            0xFFE1306C, 0xFF833AB4, 0xFFF77737, 0xFF405DE6,
            0xFF0E9F6E, 0xFFC13584, 0xFF5851DB, 0xFFFD8D14,
    };

    private Avatars() {
    }

    public static void bind(TextView view, String name) {
        String safe = name == null || name.trim().isEmpty() ? "?" : name.trim();
        int firstChar = safe.codePointAt(0);
        view.setText(new String(Character.toChars(firstChar)).toUpperCase(Locale.ROOT));
        view.setBackgroundTintList(ColorStateList.valueOf(colorFor(safe)));
    }

    static int colorFor(String name) {
        return COLORS[Math.abs(name.hashCode() % COLORS.length)];
    }
}
