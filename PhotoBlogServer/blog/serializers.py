from blog.models import Comment, Post
from rest_framework import serializers


class CurrentUserMixin:
    def current_user(self):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        return user if user is not None and user.is_authenticated else None


class PostSerializer(CurrentUserMixin, serializers.ModelSerializer):
    author_name = serializers.CharField(source='author.username', read_only=True)
    like_count = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()
    is_mine = serializers.SerializerMethodField()

    class Meta:
        model = Post
        # 앞의 7개는 기존 순서 유지(앱·검증 엔진 호환), 뒤는 편의 기능용
        fields = ('id', 'author', 'title', 'text', 'created_date', 'published_date', 'image',
                  'author_name', 'view_count', 'like_count', 'comment_count', 'is_liked', 'is_mine')
        # author는 로그인한 사용자로 서버가 지정하고, 조회수는 상세 조회로만 증가한다
        read_only_fields = ('author', 'view_count')

    # 목록에서는 get_queryset의 annotate 값을 쓰고, 생성 직후처럼 없으면 직접 센다
    def get_like_count(self, post):
        count = getattr(post, 'num_likes', None)
        return post.likes.count() if count is None else count

    def get_comment_count(self, post):
        count = getattr(post, 'num_comments', None)
        return post.comments.count() if count is None else count

    def get_is_liked(self, post):
        user = self.current_user()
        return user is not None and post.likes.filter(user=user).exists()

    def get_is_mine(self, post):
        user = self.current_user()
        return user is not None and post.author_id == user.id


class CommentSerializer(CurrentUserMixin, serializers.ModelSerializer):
    author_name = serializers.CharField(source='author.username', read_only=True)
    is_mine = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = ('id', 'post', 'author', 'author_name', 'text', 'created_date', 'is_mine')
        read_only_fields = ('post', 'author', 'created_date')

    def get_is_mine(self, comment):
        user = self.current_user()
        return user is not None and comment.author_id == user.id
