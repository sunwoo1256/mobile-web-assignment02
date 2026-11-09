package com.example.imageviewdemo;

import org.json.JSONObject;

/** 서버 Post 하나 (/api_root/Post/ 응답의 원소) */
public class Post {
    public final int id;
    public final String authorName;
    public final String title;
    public final String text;
    public final String image;
    public final String date;
    public final boolean mine;
    public int viewCount;
    public int likeCount;
    public int commentCount;
    public boolean liked;

    private Post(JSONObject json) {
        id = json.optInt("id");
        String name = string(json, "author_name");
        authorName = name.isEmpty() ? "사용자 " + json.optInt("author") : name;
        title = string(json, "title");
        text = string(json, "text");
        image = string(json, "image");
        String published = string(json, "published_date");
        date = published.isEmpty() ? string(json, "created_date") : published;
        mine = json.optBoolean("is_mine");
        viewCount = json.optInt("view_count");
        likeCount = json.optInt("like_count");
        commentCount = json.optInt("comment_count");
        liked = json.optBoolean("is_liked");
    }

    public static Post fromJson(JSONObject json) {
        return new Post(json);
    }

    /** optString은 JSON null을 문자열 "null"로 돌려주므로 빈 문자열로 바꾼다 */
    static String string(JSONObject json, String key) {
        return json.isNull(key) ? "" : json.optString(key, "");
    }
}
