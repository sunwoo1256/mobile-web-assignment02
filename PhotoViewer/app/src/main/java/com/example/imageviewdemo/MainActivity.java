package com.example.imageviewdemo;

import android.content.Intent;
import android.os.AsyncTask;
import android.os.Bundle;
import android.util.Log;
import android.view.View;
import android.widget.PopupMenu;
import android.widget.TextView;
import android.widget.Toast;

import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.appcompat.app.AppCompatActivity;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout;

import com.google.android.material.appbar.MaterialToolbar;
import com.google.android.material.dialog.MaterialAlertDialogBuilder;
import com.google.android.material.snackbar.Snackbar;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

/** 피드: 서버 게시물을 동기화해 카드 목록으로 보여준다 */
public class MainActivity extends AppCompatActivity implements PostAdapter.Listener {
    private static final String TAG = "PhotoViewer";

    TextView textView;
    RecyclerView recyclerView;
    SwipeRefreshLayout swipeRefresh;
    View emptyView;
    PostAdapter adapter;
    CloadImage taskDownload;

    // 업로드 성공(RESULT_OK)으로 돌아오면 목록을 다시 동기화한다
    private final ActivityResultLauncher<Intent> uploadLauncher = registerForActivityResult(
            new ActivityResultContracts.StartActivityForResult(), result -> {
                if (result.getResultCode() == RESULT_OK) {
                    onClickDownload(null);
                }
            });

    // 상세 화면에서 돌아오면 조회수·좋아요·댓글 수가 바뀌었으므로 다시 동기화한다
    private final ActivityResultLauncher<Intent> detailLauncher = registerForActivityResult(
            new ActivityResultContracts.StartActivityForResult(), result -> onClickDownload(null));

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        if (!ApiConfig.isLoggedIn(this)) {
            openLogin();
            return;
        }
        setContentView(R.layout.activity_main);

        MaterialToolbar toolbar = findViewById(R.id.toolbar);
        toolbar.setSubtitle(getString(R.string.toolbar_subtitle, ApiConfig.getUsername(this),
                ApiConfig.serverLabel(ApiConfig.getBaseUrl(this))));
        toolbar.setOnMenuItemClickListener(item -> {
            if (item.getItemId() == R.id.action_sync) {
                onClickDownload(null);
                return true;
            }
            if (item.getItemId() == R.id.action_logout) {
                ApiConfig.logout(this);
                openLogin();
                return true;
            }
            return false;
        });

        textView = findViewById(R.id.textView);
        emptyView = findViewById(R.id.emptyView);
        swipeRefresh = findViewById(R.id.swipeRefresh);
        swipeRefresh.setColorSchemeResources(R.color.gradient_center, R.color.gradient_start, R.color.gradient_end);
        swipeRefresh.setOnRefreshListener(() -> onClickDownload(null));

        adapter = new PostAdapter(this, getResources().getDisplayMetrics().widthPixels);
        recyclerView = findViewById(R.id.recyclerView);
        recyclerView.setLayoutManager(new LinearLayoutManager(this));
        recyclerView.setAdapter(adapter);

        onClickDownload(null); // 앱 시작 시 자동 동기화
    }

    /** 동기화 (툴바 버튼 · 당겨서 새로고침 · 자동) */
    public void onClickDownload(View v) {
        if (taskDownload != null && taskDownload.getStatus() == AsyncTask.Status.RUNNING) {
            taskDownload.cancel(true);
        }
        swipeRefresh.setRefreshing(true);
        textView.setText(R.string.text_syncing);
        taskDownload = new CloadImage(ApiConfig.getBaseUrl(this), ApiConfig.getToken(this));
        taskDownload.execute(ApiConfig.POSTS_PATH);
    }

    /** 새로운 이미지 게시 (FAB) */
    public void onClickUpload(View v) {
        uploadLauncher.launch(new Intent(this, UploadActivity.class));
    }

    /** 게시물 목록(JSON)을 받아 Post 목록으로 만든다. 이미지는 카드마다 ImageLoader가 따로 받는다 */
    private class CloadImage extends AsyncTask<String, Void, List<Post>> {
        private final String baseUrl;
        private final String token;
        private String errorMessage;
        private boolean unauthorized;

        CloadImage(String baseUrl, String token) {
            this.baseUrl = baseUrl;
            this.token = token;
        }

        @Override
        protected List<Post> doInBackground(String... paths) {
            List<Post> postList = new ArrayList<>();
            try {
                ApiClient.Response response = ApiClient.request(baseUrl, token, "GET", paths[0], null, null);
                if (response.isUnauthorized()) {
                    unauthorized = true;
                    return postList;
                }
                if (!response.isSuccessful()) {
                    errorMessage = "서버 응답 오류: " + ApiClient.errorMessage(response);
                    return postList;
                }
                JSONArray posts = new JSONArray(response.body);
                for (int i = 0; i < posts.length() && !isCancelled(); i++) {
                    JSONObject post = posts.getJSONObject(i);
                    postList.add(Post.fromJson(post));
                }
            } catch (Exception e) {
                Log.e(TAG, "동기화 실패", e);
                errorMessage = "동기화 실패: " + e.getMessage();
            }
            return postList;
        }

        @Override
        protected void onPostExecute(List<Post> posts) {
            swipeRefresh.setRefreshing(false);
            if (unauthorized) {
                sessionExpired();
                return;
            }
            if (errorMessage != null) {
                textView.setText(errorMessage);
                emptyView.setVisibility(adapter.getItemCount() == 0 ? View.VISIBLE : View.GONE);
                return;
            }
            adapter.submit(posts);
            if (posts.isEmpty()) {
                textView.setText(R.string.text_no_images);
            } else {
                textView.setText(getString(R.string.text_load_success, posts.size()));
            }
            emptyView.setVisibility(posts.isEmpty() ? View.VISIBLE : View.GONE);
        }
    }

    // ------------------------------------------------------------ 카드 이벤트

    @Override
    public void onOpen(Post post, boolean focusComment) {
        Intent intent = new Intent(this, DetailActivity.class)
                .putExtra(DetailActivity.EXTRA_POST_ID, post.id)
                .putExtra(DetailActivity.EXTRA_FOCUS_COMMENT, focusComment);
        detailLauncher.launch(intent);
    }

    /** 기능 2. 좋아요 — 화면을 먼저 바꾸고(낙관적 업데이트) 실패하면 되돌린다 */
    @Override
    public void onSetLiked(Post post, boolean liked) {
        boolean beforeLiked = post.liked;
        int beforeCount = post.likeCount;
        post.liked = liked;
        post.likeCount = Math.max(0, beforeCount + (liked ? 1 : -1));
        adapter.refreshStats(post);

        String path = ApiConfig.POSTS_PATH + post.id + "/like/";
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
                if (response != null && response.isUnauthorized()) {
                    sessionExpired();
                    return;
                }
                Snackbar.make(recyclerView, R.string.error_like_failed, Snackbar.LENGTH_SHORT).show();
            }
            adapter.refreshStats(post);
        });
    }

    /** 내 글의 더보기(⋮) 또는 길게 누르기 → 삭제 */
    @Override
    public void onMore(Post post, View anchor) {
        PopupMenu menu = new PopupMenu(this, anchor);
        menu.getMenu().add(R.string.action_delete);
        menu.setOnMenuItemClickListener(item -> {
            confirmDelete(post);
            return true;
        });
        menu.show();
    }

    /** 기능 5. 삭제 — 확인 후 DELETE, 성공하면 카드를 목록에서 뺀다 */
    private void confirmDelete(Post post) {
        new MaterialAlertDialogBuilder(this)
                .setTitle(R.string.delete_post_title)
                .setMessage(R.string.delete_post_message)
                .setNegativeButton(R.string.cancel, null)
                .setPositiveButton(R.string.action_delete, (dialog, which) -> deletePost(post))
                .show();
    }

    private void deletePost(Post post) {
        Async.run(() -> ApiClient.delete(this, ApiConfig.POSTS_PATH + post.id + "/"), (response, error) -> {
            if (isFinishing()) {
                return;
            }
            if (error == null && response.isSuccessful()) {
                adapter.remove(post);
                int count = adapter.getItemCount();
                textView.setText(count == 0 ? getString(R.string.text_no_images)
                        : getString(R.string.text_load_success, count));
                emptyView.setVisibility(count == 0 ? View.VISIBLE : View.GONE);
                Snackbar.make(recyclerView, R.string.post_deleted, Snackbar.LENGTH_SHORT).show();
            } else {
                String reason = error != null ? error.getMessage() : ApiClient.errorMessage(response);
                Snackbar.make(recyclerView, getString(R.string.error_delete_failed, reason), Snackbar.LENGTH_LONG).show();
            }
        });
    }

    private void sessionExpired() {
        ApiConfig.logout(this);
        Toast.makeText(this, R.string.session_expired, Toast.LENGTH_LONG).show();
        openLogin();
    }

    private void openLogin() {
        startActivity(new Intent(this, LoginActivity.class).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TASK
                | Intent.FLAG_ACTIVITY_NEW_TASK));
        finish();
    }
}
