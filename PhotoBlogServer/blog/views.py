from django.contrib.auth.decorators import login_required
from django.db.models import Count, F
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from .models import Comment, Like, Post
from .forms import PostForm
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import action
from rest_framework.response import Response
from .serializers import CommentSerializer, PostSerializer

def post_list(request):
    posts = Post.objects.filter(
        published_date__lte=timezone.now()
    ).order_by('published_date')
    return render(request, 'blog/post_list.html', {'posts': posts})

def post_detail(request, pk):
    post = get_object_or_404(Post, pk=pk)
    return render(request, 'blog/post_detail.html', {'post': post})

@login_required
def post_new(request):
    if request.method == "POST":
        form = PostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.published_date = timezone.now()
            post.save()
            return redirect('post_detail', pk=post.pk)
    else:
        form = PostForm()
    return render(request, 'blog/post_edit.html', {'form': form})

@login_required
def post_edit(request, pk):
    post = get_object_or_404(Post, pk=pk)
    if request.method == "POST":
        form = PostForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.published_date = timezone.now()
            post.save()
            return redirect('post_detail', pk=post.pk)
    else:
        form = PostForm(instance=post)
    return render(request, 'blog/post_edit.html', {'form': form})

def js_test(request):
    return render(request, 'blog/js_test.html', {})

class IsAuthorOrReadOnly(permissions.BasePermission):
    """조회는 누구나, 수정·삭제는 작성자만"""
    message = '작성자만 수정·삭제할 수 있습니다.'

    def has_object_permission(self, request, view, obj):
        return request.method in permissions.SAFE_METHODS or obj.author_id == request.user.id


class LoginToken(ObtainAuthToken):
    """아이디/비밀번호 → 토큰. 앱 표시용으로 사용자 id·이름도 함께 돌려준다"""

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        token, _ = Token.objects.get_or_create(user=user)
        return Response({'token': token.key, 'user_id': user.pk, 'username': user.username})


class BlogImages(viewsets.ModelViewSet):
    queryset = Post.objects.all()
    serializer_class = PostSerializer
    permission_classes = [permissions.IsAuthenticated, IsAuthorOrReadOnly]

    def get_queryset(self):
        # 최신 글이 먼저 오도록 정렬하고, 좋아요·댓글 수는 한 번의 쿼리로 함께 센다
        return (Post.objects.select_related('author')
                .annotate(num_likes=Count('likes', distinct=True),
                          num_comments=Count('comments', distinct=True))
                .order_by(F('published_date').desc(nulls_last=True), '-id'))

    def perform_create(self, serializer):
        # author는 로그인한 사용자로 지정한다(클라이언트가 보낸 값은 무시).
        # 웹 목록(post_list)은 published_date <= now 인 글만 보여주므로,
        # API로 올린 글에 published_date가 없으면 현재 시각으로 채운다
        extra = {'author': self.request.user}
        if serializer.validated_data.get('published_date') is None:
            extra['published_date'] = timezone.now()
        serializer.save(**extra)

    def retrieve(self, request, *args, **kwargs):
        # 상세 조회할 때마다 조회수 +1 (동시 요청에도 안전하도록 DB에서 증가)
        Post.objects.filter(pk=kwargs['pk']).update(view_count=F('view_count') + 1)
        return super().retrieve(request, *args, **kwargs)

    @action(detail=True, methods=['post', 'delete'], permission_classes=[permissions.IsAuthenticated])
    def like(self, request, pk=None):
        """POST: 좋아요, DELETE: 좋아요 취소. 남의 글에도 누를 수 있다"""
        post = self.get_object()
        if request.method == 'POST':
            Like.objects.get_or_create(post=post, user=request.user)
        else:
            Like.objects.filter(post=post, user=request.user).delete()
        return Response({'is_liked': request.method == 'POST', 'like_count': post.likes.count()})

    @action(detail=True, methods=['get', 'post'], permission_classes=[permissions.IsAuthenticated])
    def comments(self, request, pk=None):
        """GET: 댓글 목록(오래된 순), POST: 댓글 작성"""
        post = self.get_object()
        context = self.get_serializer_context()
        if request.method == 'GET':
            comments = post.comments.select_related('author')
            return Response(CommentSerializer(comments, many=True, context=context).data)
        serializer = CommentSerializer(data=request.data, context=context)
        serializer.is_valid(raise_exception=True)
        serializer.save(post=post, author=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CommentViewSet(mixins.RetrieveModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """댓글 단건 조회·삭제 (삭제는 작성자만)"""
    queryset = Comment.objects.select_related('author')
    serializer_class = CommentSerializer
    permission_classes = [permissions.IsAuthenticated, IsAuthorOrReadOnly]