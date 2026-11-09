package com.example.imageviewdemo;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.UnsupportedEncodingException;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;

/** 포토 블로그 REST API 호출 (HttpURLConnection). 백그라운드 스레드에서 호출해야 한다 */
public final class ApiClient {
    private static final int CONNECT_TIMEOUT_MS = 10000;
    private static final int READ_TIMEOUT_MS = 20000;
    public static final String FORM = "application/x-www-form-urlencoded; charset=UTF-8";

    public static final class Response {
        public final int code;
        public final String body;

        Response(int code, String body) {
            this.code = code;
            this.body = body;
        }

        public boolean isSuccessful() {
            return code >= 200 && code < 300;
        }

        public boolean isUnauthorized() {
            return code == HttpURLConnection.HTTP_UNAUTHORIZED;
        }
    }

    private ApiClient() {
    }

    public static Response request(String baseUrl, String token, String method, String path,
                                   byte[] body, String contentType) throws IOException {
        HttpURLConnection conn = (HttpURLConnection) new URL(baseUrl + path).openConnection();
        try {
            conn.setRequestMethod(method);
            conn.setConnectTimeout(CONNECT_TIMEOUT_MS);
            conn.setReadTimeout(READ_TIMEOUT_MS);
            conn.setRequestProperty("Accept", "application/json");
            if (token != null && !token.isEmpty()) {
                conn.setRequestProperty("Authorization", "Token " + token);
            }
            if (body != null) {
                conn.setDoOutput(true);
                conn.setRequestProperty("Content-Type", contentType);
                conn.setFixedLengthStreamingMode(body.length);
                try (OutputStream out = conn.getOutputStream()) {
                    out.write(body);
                }
            }
            int code = conn.getResponseCode();
            InputStream in = code >= 400 ? conn.getErrorStream() : conn.getInputStream();
            String text = in == null ? "" : new String(ImageUtils.readAll(in), StandardCharsets.UTF_8);
            return new Response(code, text);
        } finally {
            conn.disconnect();
        }
    }

    /** 저장된 서버 주소·토큰으로 요청 */
    public static Response request(Context context, String method, String path, byte[] body, String contentType)
            throws IOException {
        return request(ApiConfig.getBaseUrl(context), ApiConfig.getToken(context), method, path, body, contentType);
    }

    public static Response get(Context context, String path) throws IOException {
        return request(context, "GET", path, null, null);
    }

    public static Response delete(Context context, String path) throws IOException {
        return request(context, "DELETE", path, null, null);
    }

    public static Response postForm(Context context, String path, String... keyValues) throws IOException {
        return request(context, "POST", path, formBody(keyValues), FORM);
    }

    /** key1, value1, key2, value2 ... → UTF-8 URL 인코딩된 폼 바디 */
    public static byte[] formBody(String... keyValues) {
        StringBuilder sb = new StringBuilder();
        try {
            for (int i = 0; i + 1 < keyValues.length; i += 2) {
                if (sb.length() > 0) {
                    sb.append('&');
                }
                sb.append(URLEncoder.encode(keyValues[i], "UTF-8"))
                        .append('=')
                        .append(URLEncoder.encode(keyValues[i + 1], "UTF-8"));
            }
        } catch (UnsupportedEncodingException e) {
            throw new IllegalStateException(e); // UTF-8은 항상 지원된다
        }
        return sb.toString().getBytes(StandardCharsets.UTF_8);
    }

    /** DRF 오류 응답({"detail": ...} 또는 {"field": ["..."]})에서 사람이 읽을 메시지를 뽑는다 */
    public static String errorMessage(Response response) {
        try {
            JSONObject json = new JSONObject(response.body);
            if (json.has("detail")) {
                return json.getString("detail");
            }
            Iterator<String> keys = json.keys();
            if (keys.hasNext()) {
                Object value = json.get(keys.next());
                if (value instanceof JSONArray && ((JSONArray) value).length() > 0) {
                    return ((JSONArray) value).getString(0);
                }
                return String.valueOf(value);
            }
        } catch (Exception ignored) {
            // JSON이 아니면 상태코드로 표시
        }
        return "HTTP " + response.code;
    }
}
