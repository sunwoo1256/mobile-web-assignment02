package com.example.imageviewdemo;

import android.content.Context;
import android.content.SharedPreferences;

/**
 * 서버 주소와 로그인 정보(토큰·사용자)를 한 곳에서 관리한다 (SharedPreferences).
 * 토큰은 로그인 화면에서 발급받아 저장하므로 코드나 빌드 설정에 하드코딩하지 않는다.
 */
public final class ApiConfig {
    public static final String POSTS_PATH = "/api_root/Post/";
    public static final String COMMENTS_PATH = "/api_root/Comment/";
    public static final String LOGIN_PATH = "/api-token-auth/";

    public static final String LOCAL_URL = "http://10.0.2.2:8000";
    public static final String CLOUD_URL = "https://sunwoo.pythonanywhere.com";

    private static final String PREFS = "photoblog";
    private static final String KEY_BASE_URL = "base_url";
    private static final String KEY_TOKEN = "token";
    private static final String KEY_USER_ID = "user_id";
    private static final String KEY_USERNAME = "username";

    private ApiConfig() {
    }

    private static SharedPreferences prefs(Context context) {
        return context.getApplicationContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    public static String getBaseUrl(Context context) {
        return normalizeUrl(prefs(context).getString(KEY_BASE_URL, BuildConfig.DEFAULT_BASE_URL));
    }

    public static String getToken(Context context) {
        return prefs(context).getString(KEY_TOKEN, "");
    }

    public static String getUsername(Context context) {
        return prefs(context).getString(KEY_USERNAME, "");
    }

    public static boolean isLoggedIn(Context context) {
        return !getToken(context).isEmpty();
    }

    public static void saveLogin(Context context, String baseUrl, String token, int userId, String username) {
        prefs(context).edit()
                .putString(KEY_BASE_URL, normalizeUrl(baseUrl))
                .putString(KEY_TOKEN, token)
                .putInt(KEY_USER_ID, userId)
                .putString(KEY_USERNAME, username)
                .apply();
    }

    /** 로그아웃: 토큰과 사용자 정보만 지우고 서버 주소는 다음 로그인을 위해 남긴다 */
    public static void logout(Context context) {
        prefs(context).edit().remove(KEY_TOKEN).remove(KEY_USER_ID).remove(KEY_USERNAME).apply();
    }

    public static String getPostsUrl(Context context) {
        return getBaseUrl(context) + POSTS_PATH;
    }

    /** "로컬 서버" / "클라우드 서버" / 호스트 이름 */
    public static String serverLabel(String baseUrl) {
        String url = normalizeUrl(baseUrl);
        if (url.equals(LOCAL_URL)) {
            return "로컬 서버";
        }
        if (url.equals(CLOUD_URL)) {
            return "클라우드 서버";
        }
        return url.replaceFirst("^https?://", "");
    }

    /** 앞뒤 공백·끝의 '/' 제거, 스킴이 없으면 http:// 를 붙인다 */
    public static String normalizeUrl(String url) {
        String result = url == null ? "" : url.trim();
        while (result.endsWith("/")) {
            result = result.substring(0, result.length() - 1);
        }
        if (!result.isEmpty() && !result.matches("^[a-zA-Z][a-zA-Z0-9+.-]*://.*")) {
            result = "http://" + result;
        }
        return result;
    }
}
