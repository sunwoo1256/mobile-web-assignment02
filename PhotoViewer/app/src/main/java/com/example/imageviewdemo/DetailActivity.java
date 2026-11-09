package com.example.imageviewdemo;

import android.annotation.SuppressLint;
import android.content.Intent;
import android.os.Bundle;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.GestureDetector;
import android.view.LayoutInflater;
import android.view.MenuItem;
import android.view.MotionEvent;
import android.view.View;
import android.view.inputmethod.InputMethodManager;
import android.widget.EditText;
import android.widget.ImageButton;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.widget.NestedScrollView;

import com.google.android.material.appbar.MaterialToolbar;
import com.google.android.material.dialog.MaterialAlertDialogBuilder;
import com.google.android.material.snackbar.Snackbar;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

/** 게시물 상세: 큰 사진, 본문, 좋아요, 조회수, 댓글(목록·작성·삭제), 내 글 삭제 */
public class DetailActivity extends AppCompatActivity {
    public static final String EXTRA_POST_ID = "post_id";
    public static final String EXTRA_FOCUS_COMMENT = "focus_comment";

    private int postId;
    private Post post;

    private MaterialToolbar toolbar;
    private View progressLoad;
    private NestedScrollView scroll;
    private View content;
    private TextView textAvatar;
    private TextView textAuthor;
    private TextView textDate;
    private ImageView imagePost;
    private ImageView imageHeartBurst;
    private ImageButton btnLike;
    private TextView textLikeCount;
    private TextView textCommentCount;
    private TextView textViewCount;
    private TextView textTitle;
    private TextView textBody;
    private TextView textCommentHeader;
    private LinearLayout commentContainer;
    private TextView textNoComments;
    private EditText editComment;
    private ImageButton btnSend;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_detail);
        postId = getIntent().getIntExtra(EXTRA_POST_ID, -1);

        toolbar = findViewById(R.id.toolbar);
        progressLoad = findViewById(R.id.progressLoad);
        scroll = findViewById(R.id.scroll);
        content = findViewById(R.id.content);
        textAvatar = findViewById(R.id.textAvatar);
        textAuthor = findViewById(R.id.textAuthor);
        textDate = findViewById(R.id.textDate);
        imagePost = findViewById(R.id.imagePost);
        imageHeartBurst = findViewById(R.id.imageHeartBurst);
        btnLike = findViewById(R.id.btnLike);
        textLikeCount = findViewById(R.id.textLikeCount);
        textCommentCount = findViewById(R.id.textCommentCount);
        textViewCount = findViewById(R.id.textViewCount);
        textTitle = findViewById(R.id.textTitle);
        textBody = findViewById(R.id.textBody);
        textCommentHeader = findViewById(R.id.textCommentHeader);
        commentContainer = findViewById(R.id.commentContainer);
        textNoComments = findViewById(R.id.textNoComments);
        editComment = findViewById(R.id.editComment);
        btnSend = findViewById(R.id.btnSend);

        setResult(RESULT_OK); // 상세를 열면 조회수가 바뀌므로 목록은 항상 다시 동기화
        toolbar.setNavigationOnClickListener(v -> finish());
        toolbar.setOnMenuItemClickListener(this::onMenuItem);
        Avatars.bind(findViewById(R.id.textMyAvatar), ApiConfig.getUsername(this));

        btnLike.setOnClickListener(v -> {
            if (post != null) {
                LikeViews.bounce(btnLike);
                setLiked(!post.liked);
            }
        });
        setupDoubleTapLike();

        editComment.addTextChangedListener(new TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence s, int start, int count, int after) {
            }

            @Override
            public void onTextChanged(CharSequence s, int start, int before, int count) {
            }

            @Override
            public void afterTextChanged(Editable s) {
                setSendEnabled(s.toString().trim().length() > 0);
            }
        });
        setSendEnabled(false);
        btnSend.setOnClickListener(v -> sendComment());

        loadPost();
        loadComments();
        if (getIntent().getBooleanExtra(EXTRA_FOCUS_COMMENT, false)) {
            editComment.requestFocus();
            editComment.post(() -> ((InputMethodManager) getSystemService(INPUT_METHOD_SERVICE))
                    .showSoftInput(editComment, InputMethodManager.SHOW_IMPLICIT));
        }
    }

    // ------------------------------------------------------------ 게시물 (기능 4. 조회수: 상세 조회 시 서버에서 +1)

    private void loadPost() {
        Async.run(() -> ApiClient.get(this, ApiConfig.POSTS_PATH + postId + "/"), (response, error) -> {
            if (isFinishing()) {
                return;
            }
            progressLoad.setVisibility(View.GONE);
            if (error == null && response.isSuccessful()) {
                try {
                    post = Post.fromJson(new JSONObject(response.body));
                    bindPost();
                } catch (Exception e) {
                    showLoadError(e.getMessage());
                }
            } else if (response != null && response.isUnauthorized()) {
                sessionExpired();
            } else {
                showLoadError(error != null ? error.getMessage() : ApiClient.errorMessage(response));
            }
        });
    }

    private void bindPost() {
        content.setVisibility(View.VISIBLE);
        Avatars.bind(textAvatar, post.authorName);
        textAuthor.setText(post.authorName);
        textDate.setText(TimeUtils.relative(post.date));
        ImageLoader.load(imagePost, post.image, getResources().getDisplayMetrics().widthPixels);
        textTitle.setText(post.title);
        textBody.setText(post.text);
        textBody.setVisibility(post.text.isEmpty() ? View.GONE : View.VISIBLE);
        toolbar.getMenu().findItem(R.id.action_delete).setVisible(post.mine);
        bindStats();
    }

    private void bindStats() {
        LikeViews.bind(btnLike, textLikeCount, post.liked, post.likeCount);
        textCommentCount.setText(String.valueOf(post.commentCount));
        textViewCount.setText(String.valueOf(post.viewCount));
    }

    private void showLoadError(String reason) {
        Toast.makeText(this, getString(R.string.error_load_post, reason), Toast.LENGTH_LONG).show();
        finish();
    }

    // ------------------------------------------------------------ 기능 2. 좋아요

    @SuppressLint("ClickableViewAccessibility")
    private void setupDoubleTapLike() {
        GestureDetector detector = new GestureDetector(this, new GestureDetector.SimpleOnGestureListener() {
            @Override
            public boolean onDown(@NonNull MotionEvent e) {
                return true;
            }

            @Override
            public boolean onDoubleTap(@NonNull MotionEvent e) {
                if (post != null) {
                    LikeViews.burst(imageHeartBurst);
                    if (!post.liked) {
                        LikeViews.bounce(btnLike);
                        setLiked(true);
                    }
                }
                return true;
            }
        });
        imagePost.setOnTouchListener((v, event) -> detector.onTouchEvent(event));
    }

    private void setLiked(boolean liked) {
        boolean beforeLiked = post.liked;
        int beforeCount = post.likeCount;
        post.liked = liked;
        post.likeCount = Math.max(0, beforeCount + (liked ? 1 : -1));
        bindStats();

        String path = ApiConfig.POSTS_PATH + postId + "/like/";
        Async.run(() -> ApiClient.request(this, liked ? "POST" : "DELETE", path, null, null), (response, error) -> {
            if (isFinishing()) {
                return;
            }
            if (error == null && response.isSuccessful()) {
                try {
                    JSONObject json = new JSONObject(response.body);
                    post.liked = json.getBoolean("is_liked");
                    post.likeCount = json.getInt("like_count");
                } catch (Exception ignored) {
                    // 화면 값 유지
                }
            } else {
                post.liked = beforeLiked;
                post.likeCount = beforeCount;
                Snackbar.make(scroll, R.string.error_like_failed, Snackbar.LENGTH_SHORT).show();
            }
            bindStats();
        });
    }

    // ------------------------------------------------------------ 기능 3. 댓글

    private void loadComments() {
        Async.run(() -> ApiClient.get(this, ApiConfig.POSTS_PATH + postId + "/comments/"), (response, error) -> {
            if (isFinishing() || error != null || !response.isSuccessful()) {
                return;
            }
            try {
                JSONArray array = new JSONArray(response.body);
                List<Comment> comments = new ArrayList<>();
                for (int i = 0; i < array.length(); i++) {
                    comments.add(Comment.fromJson(array.getJSONObject(i)));
                }
                renderComments(comments);
            } catch (Exception ignored) {
                // 댓글을 못 읽어도 게시물은 보여준다
            }
        });
    }

    private void renderComments(List<Comment> comments) {
        commentContainer.removeAllViews();
        LayoutInflater inflater = LayoutInflater.from(this);
        for (Comment comment : comments) {
            View row = inflater.inflate(R.layout.item_comment, commentContainer, false);
            Avatars.bind(row.findViewById(R.id.textAvatar), comment.authorName);
            ((TextView) row.findViewById(R.id.textAuthor)).setText(comment.authorName);
            ((TextView) row.findViewById(R.id.textDate)).setText(TimeUtils.relative(comment.date));
            ((TextView) row.findViewById(R.id.textComment)).setText(comment.text);
            View btnDelete = row.findViewById(R.id.btnDeleteComment);
            btnDelete.setVisibility(comment.mine ? View.VISIBLE : View.GONE);
            btnDelete.setOnClickListener(v -> confirmDeleteComment(comment));
            commentContainer.addView(row);
        }
        textCommentHeader.setText(getString(R.string.comment_header, comments.size()));
        textNoComments.setVisibility(comments.isEmpty() ? View.VISIBLE : View.GONE);
        if (post != null) {
            post.commentCount = comments.size();
            bindStats();
        }
    }

    /** 비활성일 때는 흐리게 보여서 누를 수 없음을 알 수 있게 한다 */
    private void setSendEnabled(boolean enabled) {
        btnSend.setEnabled(enabled);
        btnSend.setAlpha(enabled ? 1f : 0.35f);
    }

    private void sendComment() {
        String text = editComment.getText().toString().trim();
        if (text.isEmpty()) {
            return;
        }
        setSendEnabled(false);
        Async.run(() -> ApiClient.postForm(this, ApiConfig.POSTS_PATH + postId + "/comments/", "text", text),
                (response, error) -> {
                    if (isFinishing()) {
                        return;
                    }
                    if (error == null && response.isSuccessful()) {
                        editComment.setText("");
                        editComment.clearFocus();
                        ((InputMethodManager) getSystemService(INPUT_METHOD_SERVICE))
                                .hideSoftInputFromWindow(editComment.getWindowToken(), 0);
                        loadComments();
                        scroll.postDelayed(() -> scroll.fullScroll(View.FOCUS_DOWN), 300);
                    } else {
                        setSendEnabled(true);
                        String reason = error != null ? error.getMessage() : ApiClient.errorMessage(response);
                        Snackbar.make(scroll, getString(R.string.error_comment_failed, reason), Snackbar.LENGTH_LONG)
                                .show();
                    }
                });
    }

    private void confirmDeleteComment(Comment comment) {
        new MaterialAlertDialogBuilder(this)
                .setTitle(R.string.delete_comment_title)
                .setMessage(comment.text)
                .setNegativeButton(R.string.cancel, null)
                .setPositiveButton(R.string.action_delete, (dialog, which) ->
                        Async.run(() -> ApiClient.delete(this, ApiConfig.COMMENTS_PATH + comment.id + "/"),
                                (response, error) -> {
                                    if (isFinishing()) {
                                        return;
                                    }
                                    if (error == null && response.isSuccessful()) {
                                        loadComments();
                                    } else {
                                        String reason = error != null ? error.getMessage()
                                                : ApiClient.errorMessage(response);
                                        Snackbar.make(scroll, getString(R.string.error_delete_failed, reason),
                                                Snackbar.LENGTH_LONG).show();
                                    }
                                }))
                .show();
    }

    // ------------------------------------------------------------ 기능 5. 내 글 삭제

    private boolean onMenuItem(MenuItem item) {
        if (item.getItemId() == R.id.action_delete && post != null) {
            new MaterialAlertDialogBuilder(this)
                    .setTitle(R.string.delete_post_title)
                    .setMessage(R.string.delete_post_message)
                    .setNegativeButton(R.string.cancel, null)
                    .setPositiveButton(R.string.action_delete, (dialog, which) -> deletePost())
                    .show();
            return true;
        }
        return false;
    }

    private void deletePost() {
        Async.run(() -> ApiClient.delete(this, ApiConfig.POSTS_PATH + postId + "/"), (response, error) -> {
            if (isFinishing()) {
                return;
            }
            if (error == null && response.isSuccessful()) {
                Toast.makeText(this, R.string.post_deleted, Toast.LENGTH_SHORT).show();
                finish();
            } else {
                String reason = error != null ? error.getMessage() : ApiClient.errorMessage(response);
                Snackbar.make(scroll, getString(R.string.error_delete_failed, reason), Snackbar.LENGTH_LONG).show();
            }
        });
    }

    private void sessionExpired() {
        ApiConfig.logout(this);
        Toast.makeText(this, R.string.session_expired, Toast.LENGTH_LONG).show();
        startActivity(new Intent(this, LoginActivity.class)
                .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TASK | Intent.FLAG_ACTIVITY_NEW_TASK));
        finish();
    }
}
