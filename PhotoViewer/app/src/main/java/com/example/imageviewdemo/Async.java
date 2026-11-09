package com.example.imageviewdemo;

import android.os.Handler;
import android.os.Looper;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** 네트워크 작업을 백그라운드에서 실행하고 결과를 메인 스레드로 돌려준다 (ExecutorService + Handler) */
public final class Async {
    public interface Task<T> {
        T run() throws Exception;
    }

    public interface Callback<T> {
        /** 성공하면 error == null, 실패하면 result == null */
        void onDone(T result, Exception error);
    }

    private static final ExecutorService EXECUTOR = Executors.newFixedThreadPool(4);
    private static final Handler MAIN = new Handler(Looper.getMainLooper());

    private Async() {
    }

    public static <T> void run(Task<T> task, Callback<T> callback) {
        EXECUTOR.execute(() -> {
            T result = null;
            Exception error = null;
            try {
                result = task.run();
            } catch (Exception e) {
                error = e;
            }
            final T finalResult = result;
            final Exception finalError = error;
            MAIN.post(() -> callback.onDone(finalResult, finalError));
        });
    }
}
