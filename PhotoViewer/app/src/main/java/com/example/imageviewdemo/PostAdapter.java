package com.example.imageviewdemo;

import android.annotation.SuppressLint;
import android.view.GestureDetector;
import android.view.LayoutInflater;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageButton;
import android.widget.ImageView;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;

import java.util.ArrayList;
import java.util.List;

/** 피드 카드 목록. 슬라이드의 List&lt;Bitmap&gt; 기반 ImageAdapter를 Post 객체 기반으로 확장했다 */
public class PostAdapter extends RecyclerView.Adapter<PostAdapter.PostViewHolder> {
    /** 좋아요·댓글·조회수만 다시 그릴 때 (이미지를 다시 그리지 않아 깜박이지 않음) */
    private static final Object PAYLOAD_STATS = new Object();

    public interface Listener {
        void onOpen(Post post, boolean focusComment);

        void onSetLiked(Post post, boolean liked);

        void onMore(Post post, View anchor);
    }

    private final List<Post> posts = new ArrayList<>();
    private final Listener listener;
    private final int imageWidth;

    public PostAdapter(Listener listener, int imageWidth) {
        this.listener = listener;
        this.imageWidth = imageWidth;
    }

    @SuppressLint("NotifyDataSetChanged")
    public void submit(List<Post> newPosts) {
        posts.clear();
        posts.addAll(newPosts);
        notifyDataSetChanged();
    }

    public void remove(Post post) {
        int index = posts.indexOf(post);
        if (index >= 0) {
            posts.remove(index);
            notifyItemRemoved(index);
        }
    }

    public void refreshStats(Post post) {
        int index = posts.indexOf(post);
        if (index >= 0) {
            notifyItemChanged(index, PAYLOAD_STATS);
        }
    }

    @Override
    public int getItemCount() {
        return posts.size();
    }

    @NonNull
    @Override
    public PostViewHolder onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View view = LayoutInflater.from(parent.getContext()).inflate(R.layout.item_post, parent, false);
        return new PostViewHolder(view);
    }

    @Override
    public void onBindViewHolder(@NonNull PostViewHolder holder, int position, @NonNull List<Object> payloads) {
        if (payloads.contains(PAYLOAD_STATS)) {
            holder.bindStats(posts.get(position));
        } else {
            super.onBindViewHolder(holder, position, payloads);
        }
    }

    @Override
    public void onBindViewHolder(@NonNull PostViewHolder holder, int position) {
        holder.bind(posts.get(position));
    }

    class PostViewHolder extends RecyclerView.ViewHolder {
        final TextView textAvatar;
        final TextView textAuthor;
        final TextView textDate;
        final ImageButton btnMore;
        final ImageView imagePost;
        final ImageView imageHeartBurst;
        final ImageButton btnLike;
        final TextView textLikeCount;
        final ImageButton btnComment;
        final TextView textCommentCount;
        final TextView textViewCount;
        final TextView textTitle;
        final TextView textBody;
        Post post;

        @SuppressLint("ClickableViewAccessibility")
        PostViewHolder(@NonNull View itemView) {
            super(itemView);
            textAvatar = itemView.findViewById(R.id.textAvatar);
            textAuthor = itemView.findViewById(R.id.textAuthor);
            textDate = itemView.findViewById(R.id.textDate);
            btnMore = itemView.findViewById(R.id.btnMore);
            imagePost = itemView.findViewById(R.id.imagePost);
            imageHeartBurst = itemView.findViewById(R.id.imageHeartBurst);
            btnLike = itemView.findViewById(R.id.btnLike);
            textLikeCount = itemView.findViewById(R.id.textLikeCount);
            btnComment = itemView.findViewById(R.id.btnComment);
            textCommentCount = itemView.findViewById(R.id.textCommentCount);
            textViewCount = itemView.findViewById(R.id.textViewCount);
            textTitle = itemView.findViewById(R.id.textTitle);
            textBody = itemView.findViewById(R.id.textBody);

            itemView.setOnClickListener(v -> listener.onOpen(post, false));
            itemView.setOnLongClickListener(v -> {
                if (post.mine) {
                    listener.onMore(post, btnMore);
                    return true;
                }
                return false;
            });
            btnMore.setOnClickListener(v -> listener.onMore(post, v));
            btnComment.setOnClickListener(v -> listener.onOpen(post, true));
            btnLike.setOnClickListener(v -> {
                LikeViews.bounce(btnLike);
                listener.onSetLiked(post, !post.liked);
            });

            // 사진: 한 번 탭하면 상세, 두 번 탭하면 좋아요(인스타그램 방식)
            GestureDetector detector = new GestureDetector(itemView.getContext(),
                    new GestureDetector.SimpleOnGestureListener() {
                        @Override
                        public boolean onDown(@NonNull MotionEvent e) {
                            return true;
                        }

                        @Override
                        public boolean onSingleTapConfirmed(@NonNull MotionEvent e) {
                            listener.onOpen(post, false);
                            return true;
                        }

                        @Override
                        public void onLongPress(@NonNull MotionEvent e) {
                            if (post.mine) {
                                listener.onMore(post, btnMore);
                            }
                        }

                        @Override
                        public boolean onDoubleTap(@NonNull MotionEvent e) {
                            LikeViews.burst(imageHeartBurst);
                            if (!post.liked) {
                                LikeViews.bounce(btnLike);
                                listener.onSetLiked(post, true);
                            }
                            return true;
                        }
                    });
            imagePost.setOnTouchListener((v, event) -> detector.onTouchEvent(event));
        }

        void bind(Post post) {
            this.post = post;
            Avatars.bind(textAvatar, post.authorName);
            textAuthor.setText(post.authorName);
            textDate.setText(TimeUtils.relative(post.date));
            btnMore.setVisibility(post.mine ? View.VISIBLE : View.GONE);
            imageHeartBurst.setAlpha(0f);
            ImageLoader.load(imagePost, post.image, imageWidth);
            textTitle.setText(post.title);
            textBody.setText(post.text);
            textBody.setVisibility(post.text.isEmpty() ? View.GONE : View.VISIBLE);
            bindStats(post);
        }

        void bindStats(Post post) {
            LikeViews.bind(btnLike, textLikeCount, post.liked, post.likeCount);
            textCommentCount.setText(String.valueOf(post.commentCount));
            textViewCount.setText(String.valueOf(post.viewCount));
        }
    }
}
