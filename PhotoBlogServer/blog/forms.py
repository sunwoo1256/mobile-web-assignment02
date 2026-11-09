from django import forms
from .models import Post

class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ('title', 'text', 'image',)
        # ClearableFileInput의 "지우기" 체크박스를 쓰면 image가 빈 값이 되어
        # 목록의 post.image.url에서 오류가 나므로 단순 파일 입력만 제공
        widgets = {'image': forms.FileInput}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 새 글에서 이미지를 고르지 않으면 모델 기본값(default_error.png),
        # 수정 시 고르지 않으면 기존 이미지 유지
        self.fields['image'].required = False
