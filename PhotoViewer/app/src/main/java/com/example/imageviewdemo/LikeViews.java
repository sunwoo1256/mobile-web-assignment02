package com.example.imageviewdemo;

import android.content.res.ColorStateList;
import android.view.View;
import android.view.animation.OvershootInterpolator;
import android.widget.ImageButton;
import android.widget.TextView;

import androidx.core.content.ContextCompat;

import com.google.android.material.color.MaterialColors;

/** 좋아요 버튼 표시와 하트 애니메이션 (피드·상세 공용) */
public final class LikeViews {
    private LikeViews() {
    }

    /** 채운 빨간 하트 / 빈 하트 + 개수 */
    public static void bind(ImageButton button, TextView count, boolean liked, int likeCount) {
        button.setImageResource(liked ? R.drawable.ic_heart : R.drawable.ic_heart_outline);
        int color = liked
                ? ContextCompat.getColor(button.getContext(), R.color.heart)
                : MaterialColors.getColor(button, com.google.android.material.R.attr.colorOnSurface);
        button.setImageTintList(ColorStateList.valueOf(color));
        button.setContentDescription(button.getContext().getString(R.string.like) + (liked ? " 취소" : ""));
        count.setText(String.valueOf(likeCount));
    }

    /** 누르면 살짝 줄었다가 튀어나오는 효과 */
    public static void bounce(View view) {
        view.animate().cancel();
        view.setScaleX(0.6f);
        view.setScaleY(0.6f);
        view.animate().scaleX(1f).scaleY(1f).setDuration(320)
                .setInterpolator(new OvershootInterpolator(3f)).start();
    }

    /** 사진 더블탭: 가운데 큰 하트가 커졌다가 사라진다 */
    public static void burst(View heart) {
        heart.animate().cancel();
        heart.setAlpha(0.95f);
        heart.setScaleX(0.3f);
        heart.setScaleY(0.3f);
        heart.animate().scaleX(1f).scaleY(1f).setDuration(260)
                .setInterpolator(new OvershootInterpolator(2.5f))
                .withEndAction(() -> heart.animate().alpha(0f).setStartDelay(350).setDuration(250)
                        .withEndAction(() -> heart.animate().setStartDelay(0)).start())
                .start();
    }
}
