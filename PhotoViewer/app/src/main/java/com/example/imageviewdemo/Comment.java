package com.example.imageviewdemo;

import org.json.JSONObject;

/** 댓글 하나 (/api_root/Post/{id}/comments/ 응답의 원소) */
public class Comment {
    public final int id;
    public final String authorName;
    public final String text;
    public final String date;
    public final boolean mine;

    private Comment(JSONObject json) {
        id = json.optInt("id");
        authorName = Post.string(json, "author_name");
        text = Post.string(json, "text");
        date = Post.string(json, "created_date");
        mine = json.optBoolean("is_mine");
    }

    public static Comment fromJson(JSONObject json) {
        return new Comment(json);
    }
}
