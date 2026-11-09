package com.example.imageviewdemo;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;

/** 스트림 읽기·이미지 다운샘플링 공용 함수 */
public final class ImageUtils {
    private ImageUtils() {
    }

    /** InputStream을 끝까지 읽는다 (InputStream.readAllBytes는 API 33+ 전용이므로 직접 구현) */
    public static byte[] readAll(InputStream in) throws IOException {
        try (InputStream input = in; ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192];
            int read;
            while ((read = input.read(buffer)) != -1) {
                out.write(buffer, 0, read);
            }
            return out.toByteArray();
        }
    }

    /** 원본 크기가 targetSize의 2배 이상이면 2의 거듭제곱으로 줄인다 (줄인 뒤에도 targetSize 이상 유지) */
    public static int calculateInSampleSize(int imageSize, int targetSize) {
        int inSampleSize = 1;
        if (targetSize <= 0) {
            return inSampleSize;
        }
        while (imageSize / (inSampleSize * 2) >= targetSize) {
            inSampleSize *= 2;
        }
        return inSampleSize;
    }

    /** 큰 이미지로 인한 OOM을 막기 위해 너비를 targetWidth에 맞춰 줄여서 디코딩한다 */
    public static Bitmap decodeSampled(byte[] bytes, int targetWidth) {
        BitmapFactory.Options options = new BitmapFactory.Options();
        options.inJustDecodeBounds = true;
        BitmapFactory.decodeByteArray(bytes, 0, bytes.length, options);
        options.inSampleSize = calculateInSampleSize(options.outWidth, targetWidth);
        options.inJustDecodeBounds = false;
        return BitmapFactory.decodeByteArray(bytes, 0, bytes.length, options);
    }
}
