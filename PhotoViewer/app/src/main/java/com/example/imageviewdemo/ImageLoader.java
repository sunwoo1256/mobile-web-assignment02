package com.example.imageviewdemo;

import android.graphics.Bitmap;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.util.LruCache;
import android.widget.ImageView;

import java.net.HttpURLConnection;
import java.net.URL;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * 이미지를 백그라운드에서 내려받아 ImageView에 표시한다.
 * - 메모리 캐시(LruCache, 앱 메모리의 1/8): 목록 새로고침·상세 화면 이동 시 다시 받지 않는다
 * - 재활용된 RecyclerView 항목에 이전 요청의 이미지가 늦게 들어가지 않도록 URL 태그로 확인한다
 */
public final class ImageLoader {
    private static final String TAG = "PhotoViewer";
    private static final LruCache<String, Bitmap> CACHE =
            new LruCache<String, Bitmap>((int) (Runtime.getRuntime().maxMemory() / 1024 / 8)) {
                @Override
                protected int sizeOf(String key, Bitmap bitmap) {
                    return bitmap.getByteCount() / 1024;
                }
            };
    private static final ExecutorService EXECUTOR = Executors.newFixedThreadPool(3);
    private static final Handler MAIN = new Handler(Looper.getMainLooper());

    private ImageLoader() {
    }

    public static void load(ImageView view, String url, int targetWidth) {
        view.setTag(R.id.tag_image_url, url);
        Bitmap cached = url == null ? null : CACHE.get(url);
        if (cached != null) {
            view.setImageBitmap(cached);
            return;
        }
        view.setImageDrawable(null);
        if (url == null || url.isEmpty()) {
            return;
        }
        EXECUTOR.execute(() -> {
            Bitmap bitmap = download(url, targetWidth);
            if (bitmap != null) {
                CACHE.put(url, bitmap);
            }
            MAIN.post(() -> {
                if (bitmap != null && url.equals(view.getTag(R.id.tag_image_url))) {
                    view.setAlpha(0f);
                    view.setImageBitmap(bitmap);
                    view.animate().alpha(1f).setDuration(220).start();
                }
            });
        });
    }

    private static Bitmap download(String imageUrl, int targetWidth) {
        HttpURLConnection conn = null;
        try {
            conn = (HttpURLConnection) new URL(imageUrl).openConnection();
            conn.setConnectTimeout(10000);
            conn.setReadTimeout(20000);
            if (conn.getResponseCode() != HttpURLConnection.HTTP_OK) {
                Log.w(TAG, "이미지 응답 오류 " + conn.getResponseCode() + ": " + imageUrl);
                return null;
            }
            return ImageUtils.decodeSampled(ImageUtils.readAll(conn.getInputStream()), targetWidth);
        } catch (Exception e) {
            Log.w(TAG, "이미지 다운로드 실패: " + imageUrl, e);
            return null;
        } finally {
            if (conn != null) {
                conn.disconnect();
            }
        }
    }
}
