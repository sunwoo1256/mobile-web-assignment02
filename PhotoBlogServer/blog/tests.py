"""blog 앱 서버 측 테스트 (Django TestCase / DRF APITestCase — 모두 unittest.TestCase 기반)

실행: python manage.py test blog -v 2
"""
import io
import shutil
import tempfile
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from .models import Post

TEMP_MEDIA_ROOT = tempfile.mkdtemp()
POSTS_URL = '/api_root/Post/'


def make_image(name='test.jpg'):
    buffer = io.BytesIO()
    Image.new('RGB', (10, 10), 'red').save(buffer, 'JPEG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/jpeg')


class TempMediaMixin:
    """업로드한 테스트 이미지가 실제 media/ 폴더에 쌓이지 않게 임시 폴더를 쓴다"""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class PostApiTest(TempMediaMixin, APITestCase):
    def setUp(self):
        self.user = User.objects.create_user('sunwoo', password='pw-12345!')
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        self.post = Post.objects.create(author=self.user, title='기존 글', text='본문',
                                        published_date=timezone.now())

    def upload(self, **overrides):
        data = {'author': self.user.id, 'title': '새 글', 'text': '본문', 'image': make_image()}
        data.update(overrides)
        return self.client.post(POSTS_URL, data, format='multipart')

    def test_get_posts_with_token_returns_json_array(self):
        response = self.client.get(POSTS_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.json(), list)
        self.assertEqual(len(response.json()), 1)

    def test_post_fields_keep_original_order_and_add_social_fields(self):
        post = self.client.get(POSTS_URL).json()[0]
        self.assertEqual(list(post), ['id', 'author', 'title', 'text', 'created_date', 'published_date',
                                      'image', 'author_name', 'view_count', 'like_count',
                                      'comment_count', 'is_liked', 'is_mine'])
        self.assertTrue(post['image'].startswith('http://testserver/media/'))

    def test_multipart_post_creates_post_with_image(self):
        response = self.upload(title='한글 제목')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Post.objects.count(), 2)
        self.assertEqual(response.json()['title'], '한글 제목')
        self.assertIn('/media/images/', response.json()['image'])

    def test_published_date_is_filled_when_not_given(self):
        before = timezone.now()
        response = self.upload()
        created = Post.objects.get(pk=response.json()['id'])
        self.assertIsNotNone(created.published_date)
        self.assertGreaterEqual(created.published_date, before)

    def test_published_date_is_kept_when_given(self):
        given = timezone.now() - timedelta(days=3)
        response = self.upload(published_date=given.isoformat())
        created = Post.objects.get(pk=response.json()['id'])
        self.assertEqual(created.published_date, given)

    def test_request_without_token_is_rejected_with_401(self):
        self.client.credentials()
        response = self.client.get(POSTS_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response['WWW-Authenticate'], 'Token')

    def test_request_with_wrong_token_is_rejected_with_401(self):
        self.client.credentials(HTTP_AUTHORIZATION='Token wrong')
        self.assertEqual(self.client.get(POSTS_URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_post_without_required_fields_is_rejected_with_400(self):
        response = self.client.post(POSTS_URL, {'text': '제목 없음'}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('title', response.json())
        self.assertNotIn('author', response.json())  # author는 서버가 채우므로 필수 아님
        self.assertEqual(Post.objects.count(), 1)

    def test_get_single_post_by_id(self):
        response = self.client.get(f'{POSTS_URL}{self.post.pk}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['title'], '기존 글')

    def test_delete_post_returns_204_and_removes_post(self):
        response = self.client.delete(f'{POSTS_URL}{self.post.pk}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Post.objects.filter(pk=self.post.pk).exists())

    def test_post_uploaded_by_api_appears_in_web_post_list(self):
        self.upload(title='API로 올린 글')
        self.assertContains(self.client.get(reverse('post_list')), 'API로 올린 글')

    def test_allow_header_contains_get_and_post(self):
        allow = self.client.get(POSTS_URL)['Allow']
        self.assertIn('GET', allow)
        self.assertIn('POST', allow)


class TokenAuthTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user('sunwoo', password='pw-12345!')

    def test_token_is_issued_with_correct_password(self):
        response = self.client.post('/api-token-auth/', {'username': 'sunwoo', 'password': 'pw-12345!'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['token'], Token.objects.get(user=self.user).key)

    def test_token_is_not_issued_with_wrong_password(self):
        response = self.client.post('/api-token-auth/', {'username': 'sunwoo', 'password': 'wrong'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Token.objects.exists())

    def test_issued_token_can_read_post_list(self):
        token = self.client.post('/api-token-auth/', {'username': 'sunwoo', 'password': 'pw-12345!'}).json()['token']
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token}')
        self.assertEqual(self.client.get(POSTS_URL).status_code, status.HTTP_200_OK)

    def test_login_response_includes_user_id_and_username(self):
        response = self.client.post('/api-token-auth/', {'username': 'sunwoo', 'password': 'pw-12345!'})
        self.assertEqual(response.json()['user_id'], self.user.id)
        self.assertEqual(response.json()['username'], 'sunwoo')


# ---------------------------------------------------------------- Task 8: 편의 기능 (로그인·삭제·조회수·좋아요·댓글)

class SocialApiTestCase(TempMediaMixin, APITestCase):
    """작성자(sunwoo)와 다른 사용자(friend) 두 계정으로 테스트한다"""

    def setUp(self):
        self.owner = User.objects.create_user('sunwoo', password='pw-12345!')
        self.friend = User.objects.create_user('friend', password='pw-12345!')
        self.post = Post.objects.create(author=self.owner, title='내 글', text='본문',
                                        published_date=timezone.now())
        self.login_as(self.owner)

    def login_as(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def detail_url(self, post=None):
        return f'{POSTS_URL}{(post or self.post).pk}/'


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class LoginAuthorTest(SocialApiTestCase):
    """기능 1. 로그인 — 업로드한 사용자가 author로 자동 지정된다"""

    def test_author_is_set_to_logged_in_user(self):
        self.login_as(self.friend)
        response = self.client.post(POSTS_URL, {'title': 't', 'text': 't', 'image': make_image()},
                                    format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()['author'], self.friend.id)
        self.assertEqual(response.json()['author_name'], 'friend')

    def test_author_sent_by_client_is_ignored(self):
        self.login_as(self.friend)
        response = self.client.post(POSTS_URL, {'author': self.owner.id, 'title': 't', 'text': 't',
                                                'image': make_image()}, format='multipart')
        self.assertEqual(Post.objects.get(pk=response.json()['id']).author, self.friend)

    def test_is_mine_depends_on_logged_in_user(self):
        self.assertTrue(self.client.get(self.detail_url()).json()['is_mine'])
        self.login_as(self.friend)
        self.assertFalse(self.client.get(self.detail_url()).json()['is_mine'])

    def test_post_list_is_ordered_newest_first(self):
        Post.objects.create(author=self.owner, title='옛날 글', text='t',
                            published_date=timezone.now() - timedelta(days=1))
        Post.objects.create(author=self.owner, title='새 글', text='t',
                            published_date=timezone.now() + timedelta(seconds=1))
        titles = [post['title'] for post in self.client.get(POSTS_URL).json()]
        self.assertEqual(titles, ['새 글', '내 글', '옛날 글'])


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class DeletePermissionTest(SocialApiTestCase):
    """기능 5. 삭제 — 작성자만 수정·삭제할 수 있다"""

    def test_author_can_delete_own_post(self):
        self.assertEqual(self.client.delete(self.detail_url()).status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Post.objects.filter(pk=self.post.pk).exists())

    def test_other_user_cannot_delete_post(self):
        self.login_as(self.friend)
        response = self.client.delete(self.detail_url())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Post.objects.filter(pk=self.post.pk).exists())

    def test_other_user_cannot_edit_post(self):
        self.login_as(self.friend)
        response = self.client.patch(self.detail_url(), {'title': '바꿈'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.post.refresh_from_db()
        self.assertEqual(self.post.title, '내 글')

    def test_other_user_can_still_read_post(self):
        self.login_as(self.friend)
        self.assertEqual(self.client.get(self.detail_url()).status_code, status.HTTP_200_OK)


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class ViewCountTest(SocialApiTestCase):
    """기능 4. 조회수 — 상세 조회할 때마다 1 증가"""

    def test_new_post_has_zero_views(self):
        self.assertEqual(self.client.get(POSTS_URL).json()[0]['view_count'], 0)

    def test_detail_view_increments_view_count(self):
        self.assertEqual(self.client.get(self.detail_url()).json()['view_count'], 1)
        self.assertEqual(self.client.get(self.detail_url()).json()['view_count'], 2)
        self.post.refresh_from_db()
        self.assertEqual(self.post.view_count, 2)

    def test_list_does_not_increment_view_count(self):
        self.client.get(POSTS_URL)
        self.post.refresh_from_db()
        self.assertEqual(self.post.view_count, 0)

    def test_view_count_cannot_be_changed_by_client(self):
        self.client.patch(self.detail_url(), {'view_count': 999})
        self.post.refresh_from_db()
        self.assertEqual(self.post.view_count, 0)

    def test_detail_of_missing_post_returns_404(self):
        self.assertEqual(self.client.get(f'{POSTS_URL}999/').status_code, status.HTTP_404_NOT_FOUND)


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class LikeTest(SocialApiTestCase):
    """기능 2. 좋아요 — POST로 좋아요, DELETE로 취소. 사용자당 1회"""

    def like_url(self):
        return f'{self.detail_url()}like/'

    def test_like_post(self):
        self.login_as(self.friend)
        response = self.client.post(self.like_url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {'is_liked': True, 'like_count': 1})

    def test_like_twice_counts_once(self):
        self.client.post(self.like_url())
        self.assertEqual(self.client.post(self.like_url()).json()['like_count'], 1)
        self.assertEqual(self.post.likes.count(), 1)

    def test_unlike_post(self):
        self.client.post(self.like_url())
        response = self.client.delete(self.like_url())
        self.assertEqual(response.json(), {'is_liked': False, 'like_count': 0})

    def test_unlike_without_like_is_harmless(self):
        self.assertEqual(self.client.delete(self.like_url()).json()['like_count'], 0)

    def test_like_count_and_is_liked_are_per_user(self):
        self.client.post(self.like_url())
        self.login_as(self.friend)
        post = self.client.get(POSTS_URL).json()[0]
        self.assertEqual(post['like_count'], 1)
        self.assertFalse(post['is_liked'])
        self.client.post(self.like_url())
        post = self.client.get(POSTS_URL).json()[0]
        self.assertEqual((post['like_count'], post['is_liked']), (2, True))

    def test_like_requires_login(self):
        self.client.credentials()
        self.assertEqual(self.client.post(self.like_url()).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_like_missing_post_returns_404(self):
        self.assertEqual(self.client.post(f'{POSTS_URL}999/like/').status_code, status.HTTP_404_NOT_FOUND)

    def test_like_str_shows_user_and_post(self):
        self.client.post(self.like_url())
        self.assertEqual(str(self.post.likes.get()), 'sunwoo ♥ 내 글')

    def test_likes_are_deleted_with_post(self):
        self.client.post(self.like_url())
        self.client.delete(self.detail_url())
        self.assertEqual(User.objects.get(pk=self.owner.pk).likes.count(), 0)


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class CommentTest(SocialApiTestCase):
    """기능 3. 댓글 — 게시물별 목록·작성, 작성자만 삭제"""

    def comments_url(self):
        return f'{self.detail_url()}comments/'

    def write(self, text='좋은 사진이네요'):
        return self.client.post(self.comments_url(), {'text': text})

    def test_comment_list_is_empty_at_first(self):
        response = self.client.get(self.comments_url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), [])

    def test_write_comment(self):
        self.login_as(self.friend)
        response = self.write('멋져요!')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        comment = response.json()
        self.assertEqual(comment['text'], '멋져요!')
        self.assertEqual(comment['author_name'], 'friend')
        self.assertTrue(comment['is_mine'])
        self.assertEqual(list(comment), ['id', 'post', 'author', 'author_name', 'text',
                                         'created_date', 'is_mine'])

    def test_comments_are_listed_oldest_first(self):
        self.write('첫 댓글')
        self.login_as(self.friend)
        self.write('두 번째 댓글')
        comments = self.client.get(self.comments_url()).json()
        self.assertEqual([c['text'] for c in comments], ['첫 댓글', '두 번째 댓글'])
        self.assertEqual([c['is_mine'] for c in comments], [False, True])

    def test_empty_comment_is_rejected(self):
        self.assertEqual(self.write('   ').status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.post.comments.count(), 0)

    def test_comment_count_is_shown_in_post(self):
        self.write()
        self.write()
        self.assertEqual(self.client.get(POSTS_URL).json()[0]['comment_count'], 2)

    def test_author_can_delete_own_comment(self):
        comment_id = self.write().json()['id']
        response = self.client.delete(f'/api_root/Comment/{comment_id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.post.comments.count(), 0)

    def test_other_user_cannot_delete_comment(self):
        comment_id = self.write().json()['id']
        self.login_as(self.friend)
        response = self.client.delete(f'/api_root/Comment/{comment_id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.post.comments.count(), 1)

    def test_friend_can_comment_on_others_post(self):
        self.login_as(self.friend)
        self.assertEqual(self.write().status_code, status.HTTP_201_CREATED)

    def test_comments_require_login(self):
        self.client.credentials()
        self.assertEqual(self.client.get(self.comments_url()).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_comments_are_deleted_with_post(self):
        self.write()
        self.client.delete(self.detail_url())
        self.assertEqual(User.objects.get(pk=self.owner.pk).comments.count(), 0)

    def test_comment_str_shows_author_and_text(self):
        comment_id = self.write('짧은 댓글').json()['id']
        comment = self.post.comments.get(pk=comment_id)
        self.assertEqual(str(comment), 'sunwoo: 짧은 댓글')


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class WebViewTest(TempMediaMixin, TestCase):
    def setUp(self):
        self.user = User.objects.create_user('sunwoo', password='pw-12345!')

    def login(self):
        self.client.login(username='sunwoo', password='pw-12345!')

    def test_post_list_shows_only_published_posts(self):
        Post.objects.create(author=self.user, title='공개 글', text='t', published_date=timezone.now())
        Post.objects.create(author=self.user, title='임시 글', text='t')
        Post.objects.create(author=self.user, title='예약 글', text='t',
                            published_date=timezone.now() + timedelta(days=1))
        response = self.client.get(reverse('post_list'))
        self.assertContains(response, '공개 글')
        self.assertNotContains(response, '임시 글')
        self.assertNotContains(response, '예약 글')

    def test_post_detail_shows_title_and_image(self):
        post = Post.objects.create(author=self.user, title='상세 글', text='t', image=make_image())
        response = self.client.get(reverse('post_detail', args=[post.pk]))
        self.assertContains(response, '상세 글')
        self.assertContains(response, post.image.url)

    def test_post_detail_of_missing_post_returns_404(self):
        self.assertEqual(self.client.get(reverse('post_detail', args=[999])).status_code, 404)

    def test_anonymous_user_is_redirected_to_login_for_new_and_edit(self):
        post = Post.objects.create(author=self.user, title='t', text='t')
        for url in [reverse('post_new'), reverse('post_edit', args=[post.pk])]:
            response = self.client.get(url)
            self.assertRedirects(response, f'/api-auth/login/?next={url}', fetch_redirect_response=False)

    def test_new_post_form_is_shown_with_image_field(self):
        self.login()
        response = self.client.get(reverse('post_new'))
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, 'name="image"')

    def test_new_post_with_image_is_saved_and_published(self):
        self.login()
        response = self.client.post(reverse('post_new'), {'title': '웹 글', 'text': 't', 'image': make_image()})
        post = Post.objects.get(title='웹 글')
        self.assertRedirects(response, reverse('post_detail', args=[post.pk]))
        self.assertEqual(post.author, self.user)
        self.assertIsNotNone(post.published_date)
        self.assertTrue(post.image.name.startswith('images/'))

    def test_new_post_without_image_uses_default_image(self):
        self.login()
        self.client.post(reverse('post_new'), {'title': '이미지 없음', 'text': 't'})
        self.assertEqual(Post.objects.get(title='이미지 없음').image.name, 'images/default_error.png')

    def test_new_post_without_title_is_not_saved(self):
        self.login()
        response = self.client.post(reverse('post_new'), {'title': '', 'text': 't'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Post.objects.exists())

    def test_edit_form_is_prefilled(self):
        self.login()
        post = Post.objects.create(author=self.user, title='원래 제목', text='t')
        self.assertContains(self.client.get(reverse('post_edit', args=[post.pk])), '원래 제목')

    def test_edit_without_new_image_keeps_existing_image(self):
        self.login()
        post = Post.objects.create(author=self.user, title='원래 제목', text='t', image=make_image())
        old_image = post.image.name
        self.client.post(reverse('post_edit', args=[post.pk]), {'title': '바뀐 제목', 'text': 't'})
        post.refresh_from_db()
        self.assertEqual(post.title, '바뀐 제목')
        self.assertEqual(post.image.name, old_image)

    def test_js_test_page_is_rendered(self):
        self.assertContains(self.client.get(reverse('js_test')), 'Number guessing game')


class PostModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('sunwoo', password='pw-12345!')
        self.post = Post.objects.create(author=self.user, title='모델 글', text='t')

    def test_str_returns_title(self):
        self.assertEqual(str(self.post), '모델 글')

    def test_publish_sets_published_date(self):
        self.assertIsNone(self.post.published_date)
        self.post.publish()
        self.post.refresh_from_db()
        self.assertIsNotNone(self.post.published_date)

    def test_default_image_is_default_error_png(self):
        self.assertEqual(self.post.image.name, 'images/default_error.png')
