"""photoblog_api.py(API 검증 엔진) 자동 테스트

- 단위 테스트: 서버 없이 실행. urllib.request.urlopen을 FakeServer로 대체한다.
- 통합 테스트: 실제 서버 대상. 환경변수 PHOTOBLOG_BASE_URL / PHOTOBLOG_USER /
  PHOTOBLOG_PASSWORD(+선택 PHOTOBLOG_AUTHOR)가 없거나 서버에 연결할 수 없으면 skip.

실행: python test_photoblog_api.py
"""
import contextlib
import io
import json
import os
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
import uuid
from unittest import mock

from photoblog_api import (
    ApiError, PhotoBlogApi, StepResult, encode_multipart, format_results, main, minimal_png,
)

BASE_URL = 'http://testserver'


def make_post(post_id=1, **overrides):
    post = {
        'id': post_id,
        'author': 1,
        'title': '제목',
        'text': '본문',
        'created_date': '2026-10-16T00:00:00+09:00',
        'published_date': '2026-10-16T00:00:00+09:00',
        'image': f'{BASE_URL}/media/images/2026/10/16/{post_id}.png',
    }
    post.update(overrides)
    return post


def respond(url, status, body):
    """urlopen의 반환값(2xx) 또는 HTTPError(4xx/5xx)를 흉내 낸다"""
    # DRF처럼 한글을 \uXXXX로 이스케이프하지 않고 UTF-8 그대로 보낸다
    data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode('utf-8')
    if status >= 400:
        raise urllib.error.HTTPError(url, status, 'error', {}, io.BytesIO(data))
    response = mock.MagicMock()
    response.status = status
    response.read.return_value = data
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


class FakeServer:
    """포토 블로그 서버처럼 동작하는 가짜 urlopen. 받은 요청은 requests에 기록한다"""

    def __init__(self):
        self.posts = []
        self.next_id = 1
        self.requests = []
        self.overrides = {}          # (method, path) -> (status, body)
        self.anonymous_status = 401  # 토큰 없는 요청에 대한 응답 코드
        self.hide_created = False    # True면 업로드한 글이 목록에 나타나지 않음

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        method = request.get_method()
        path = urllib.parse.urlsplit(request.full_url).path
        url = request.full_url
        if (method, path) in self.overrides:
            return respond(url, *self.overrides[(method, path)])
        if path == '/api-token-auth/':
            return respond(url, 200, {'token': 'abc123'})
        if request.get_header('Authorization') is None:
            if self.anonymous_status == 200:
                return respond(url, 200, self.posts)
            return respond(url, self.anonymous_status, {'detail': '인증 정보가 없습니다.'})
        if method == 'GET':
            return respond(url, 200, [] if self.hide_created else self.posts)
        if method == 'POST':
            post = make_post(self.next_id)
            self.next_id += 1
            self.posts.append(post)
            return respond(url, 201, post)
        post_id = int(path.rstrip('/').split('/')[-1])
        self.posts = [p for p in self.posts if p['id'] != post_id]
        return respond(url, 204, b'')


class FakeServerTestCase(unittest.TestCase):
    """urlopen을 FakeServer로 바꾸고, 업로드용 임시 PNG 파일을 준비한다"""

    def setUp(self):
        self.server = FakeServer()
        patcher = mock.patch('urllib.request.urlopen', side_effect=self.server)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.api = PhotoBlogApi(BASE_URL, token='abc123')
        fd, self.image_path = tempfile.mkstemp(suffix='.png')
        os.write(fd, minimal_png())
        os.close(fd)

    def tearDown(self):
        os.remove(self.image_path)

    def last_request(self):
        return self.server.requests[-1]


# ---------------------------------------------------------------- 단위 테스트

class TestMinimalPngAndMultipart(unittest.TestCase):
    def test_minimal_png_starts_with_png_signature_and_ends_with_iend(self):
        png = minimal_png()
        self.assertTrue(png.startswith(b'\x89PNG\r\n\x1a\n'))
        self.assertIn(b'IHDR', png)
        self.assertTrue(png.endswith(b'IEND\xaeB`\x82'))

    def test_encode_multipart_contains_text_fields_and_file_part(self):
        body, content_type = encode_multipart(
            [('title', 'hello')], [('image', 'a.png', b'PNGDATA', 'image/png')], boundary='XYZ')
        self.assertEqual(content_type, 'multipart/form-data; boundary=XYZ')
        self.assertIn(b'--XYZ\r\nContent-Disposition: form-data; name="title"\r\n\r\nhello\r\n', body)
        self.assertIn(b'Content-Disposition: form-data; name="image"; filename="a.png"\r\n'
                      b'Content-Type: image/png\r\n\r\nPNGDATA\r\n', body)
        self.assertTrue(body.endswith(b'--XYZ--\r\n'))

    def test_encode_multipart_writes_korean_text_as_utf8(self):
        body, _ = encode_multipart([('title', '한글 제목')], [], boundary='XYZ')
        self.assertIn('한글 제목'.encode('utf-8'), body)

    def test_encode_multipart_generates_boundary_when_not_given(self):
        body, content_type = encode_multipart([('title', 't')], [])
        boundary = content_type.split('boundary=')[1]
        self.assertGreater(len(boundary), 10)
        self.assertTrue(body.startswith(f'--{boundary}\r\n'.encode()))


class TestValidatePost(unittest.TestCase):
    def setUp(self):
        self.api = PhotoBlogApi(BASE_URL)
        self.post = make_post()

    def test_valid_post_has_no_problems(self):
        self.assertEqual(self.api.validate_post(self.post), [])

    def test_published_date_may_be_null(self):
        self.post['published_date'] = None
        self.assertEqual(self.api.validate_post(self.post), [])

    def test_missing_key_is_reported(self):
        del self.post['title']
        self.assertEqual(self.api.validate_post(self.post), ['필수 키 누락: title'])

    def test_image_that_is_not_url_is_reported(self):
        self.post['image'] = 'images/a.png'
        problems = self.api.validate_post(self.post)
        self.assertEqual(len(problems), 1)
        self.assertIn('image가 URL이 아님', problems[0])

    def test_wrong_types_are_reported(self):
        self.post['author'] = '1'
        self.post['title'] = 123
        self.post['published_date'] = 20261016
        problems = self.api.validate_post(self.post)
        self.assertIn('author 타입 오류: str', problems)
        self.assertIn('title 타입 오류: int', problems)
        self.assertIn('published_date 타입 오류: int', problems)

    def test_boolean_author_is_reported_even_though_bool_is_int(self):
        self.post['author'] = True
        self.assertEqual(self.api.validate_post(self.post), ['author 타입 오류: bool'])

    def test_post_that_is_not_dict_is_reported(self):
        self.assertEqual(self.api.validate_post(['not', 'dict']), ['게시물이 객체(dict)가 아님'])


class TestValidatePostList(unittest.TestCase):
    def setUp(self):
        self.api = PhotoBlogApi(BASE_URL)

    def test_valid_list_has_no_problems(self):
        self.assertEqual(self.api.validate_post_list([make_post(1), make_post(2)]), [])

    def test_empty_list_is_valid(self):
        self.assertEqual(self.api.validate_post_list([]), [])

    def test_response_that_is_not_list_is_reported(self):
        self.assertEqual(self.api.validate_post_list({'detail': 'x'}), ['응답이 배열(list)이 아님'])

    def test_mixed_list_reports_index_of_invalid_post(self):
        invalid = make_post(2)
        del invalid['image']
        self.assertEqual(self.api.validate_post_list([make_post(1), invalid]),
                         ['[1] 필수 키 누락: image'])


class TestGetPosts(FakeServerTestCase):
    def test_get_posts_returns_json_array(self):
        self.server.posts = [make_post(1), make_post(2)]
        posts = self.api.get_posts()
        self.assertEqual([p['id'] for p in posts], [1, 2])

    def test_get_posts_sends_token_header_to_post_list_url(self):
        self.api.get_posts()
        request = self.last_request()
        self.assertEqual(request.get_method(), 'GET')
        self.assertEqual(request.full_url, 'http://testserver/api_root/Post/')
        self.assertEqual(request.get_header('Authorization'), 'Token abc123')

    def test_get_posts_without_token_sends_no_authorization_header(self):
        anonymous = PhotoBlogApi(BASE_URL)
        with self.assertRaises(ApiError):
            anonymous.get_posts()
        self.assertIsNone(self.last_request().get_header('Authorization'))

    def test_get_posts_raises_api_error_with_status_on_401(self):
        self.api.token = None
        with self.assertRaises(ApiError) as cm:
            self.api.get_posts()
        self.assertEqual(cm.exception.status, 401)
        self.assertIn('인증 정보가 없습니다.', cm.exception.message)

    def test_get_posts_raises_api_error_on_500(self):
        self.server.overrides[('GET', '/api_root/Post/')] = (500, b'Server Error')
        with self.assertRaises(ApiError) as cm:
            self.api.get_posts()
        self.assertEqual(cm.exception.status, 500)
        self.assertEqual(str(cm.exception), 'HTTP 500: Server Error')

    def test_get_posts_raises_api_error_when_response_is_not_json(self):
        self.server.overrides[('GET', '/api_root/Post/')] = (200, b'<html>not json</html>')
        with self.assertRaises(ApiError) as cm:
            self.api.get_posts()
        self.assertEqual(cm.exception.status, 200)
        self.assertIn('JSON', cm.exception.message)

    def test_base_url_trailing_slash_is_ignored(self):
        PhotoBlogApi(BASE_URL + '/', token='abc123').get_posts()
        self.assertEqual(self.last_request().full_url, 'http://testserver/api_root/Post/')

    def test_connection_failure_raises_api_error_without_status(self):
        with mock.patch('urllib.request.urlopen',
                        side_effect=urllib.error.URLError('connection refused')):
            with self.assertRaises(ApiError) as cm:
                self.api.get_posts()
        self.assertIsNone(cm.exception.status)
        self.assertIn('connection refused', cm.exception.message)


class TestGetToken(FakeServerTestCase):
    def test_get_token_stores_and_returns_token(self):
        api = PhotoBlogApi(BASE_URL)
        self.assertEqual(api.get_token('sunwoo', 'pw'), 'abc123')
        self.assertEqual(api.token, 'abc123')
        request = self.last_request()
        self.assertEqual(request.get_method(), 'POST')
        self.assertEqual(request.full_url, 'http://testserver/api-token-auth/')
        self.assertEqual(urllib.parse.parse_qs(request.data.decode()),
                         {'username': ['sunwoo'], 'password': ['pw']})
        self.assertIsNone(request.get_header('Authorization'))

    def test_get_token_raises_api_error_on_wrong_password(self):
        self.server.overrides[('POST', '/api-token-auth/')] = (400, {'non_field_errors': ['x']})
        with self.assertRaises(ApiError) as cm:
            self.api.get_token('sunwoo', 'wrong')
        self.assertEqual(cm.exception.status, 400)

    def test_get_token_raises_api_error_when_token_missing_in_response(self):
        self.server.overrides[('POST', '/api-token-auth/')] = (200, {'detail': 'no token'})
        with self.assertRaises(ApiError):
            self.api.get_token('sunwoo', 'pw')


class TestCreatePost(FakeServerTestCase):
    def test_create_post_returns_created_post_on_201(self):
        created = self.api.create_post('제목', '본문', self.image_path)
        self.assertEqual(created['id'], 1)
        self.assertEqual(len(self.server.posts), 1)

    def test_create_post_sends_multipart_body_with_all_fields(self):
        self.api.create_post('한글 제목', '본문입니다', self.image_path,
                             author=1, published_date='2026-10-16T00:00:00+09:00')
        request = self.last_request()
        self.assertEqual(request.get_method(), 'POST')
        self.assertEqual(request.get_header('Authorization'), 'Token abc123')
        self.assertTrue(request.get_header('Content-type').startswith('multipart/form-data; boundary='))
        body = request.data
        for name, value in [('title', '한글 제목'), ('text', '본문입니다'), ('author', '1'),
                            ('published_date', '2026-10-16T00:00:00+09:00')]:
            self.assertIn(f'name="{name}"\r\n\r\n{value}\r\n'.encode('utf-8'), body)
        filename = os.path.basename(self.image_path)
        self.assertIn(f'name="image"; filename="{filename}"\r\nContent-Type: image/png'.encode(), body)
        self.assertIn(minimal_png(), body)

    def test_create_post_omits_optional_fields_when_not_given(self):
        self.api.create_post('제목', '본문', self.image_path)
        body = self.last_request().data
        self.assertNotIn(b'name="author"', body)
        self.assertNotIn(b'name="published_date"', body)

    def test_create_post_uses_octet_stream_for_unknown_extension(self):
        fd, path = tempfile.mkstemp(suffix='.unknownext')
        os.write(fd, b'data')
        os.close(fd)
        self.addCleanup(os.remove, path)
        self.api.create_post('제목', '본문', path)
        self.assertIn(b'Content-Type: application/octet-stream', self.last_request().data)

    def test_create_post_raises_api_error_on_400(self):
        self.server.overrides[('POST', '/api_root/Post/')] = (400, {'title': ['이 필드는 필수 항목입니다.']})
        with self.assertRaises(ApiError) as cm:
            self.api.create_post('', '본문', self.image_path)
        self.assertEqual(cm.exception.status, 400)
        self.assertIn('필수 항목', cm.exception.message)


class TestDeletePost(FakeServerTestCase):
    def test_delete_post_sends_delete_request_and_accepts_204(self):
        self.server.posts = [make_post(7)]
        self.api.delete_post(7)
        request = self.last_request()
        self.assertEqual(request.get_method(), 'DELETE')
        self.assertEqual(request.full_url, 'http://testserver/api_root/Post/7/')
        self.assertEqual(self.server.posts, [])

    def test_delete_post_raises_api_error_on_404(self):
        self.server.overrides[('DELETE', '/api_root/Post/99/')] = (404, {'detail': 'Not found.'})
        with self.assertRaises(ApiError) as cm:
            self.api.delete_post(99)
        self.assertEqual(cm.exception.status, 404)


class TestRunScenario(FakeServerTestCase):
    STEP_NAMES = ['토큰 발급', '목록 조회 및 스키마 검증', '게시물 업로드',
                  '목록 반영 확인', '게시물 삭제', '인증 없는 요청 거부']

    def run_scenario(self, image_path=None):
        api = PhotoBlogApi(BASE_URL)
        return api.run_scenario('sunwoo', 'pw', image_path=image_path, author=1)

    def test_all_steps_pass_against_normal_server(self):
        results = self.run_scenario(self.image_path)
        self.assertEqual([r.name for r in results], self.STEP_NAMES)
        self.assertEqual([r.passed for r in results], [True] * 6)
        self.assertEqual(self.server.posts, [])  # 업로드한 글은 정리됨

    def test_temporary_image_is_created_and_removed_when_image_path_not_given(self):
        with mock.patch('os.remove', wraps=os.remove) as remove:
            results = self.run_scenario()
        self.assertTrue(all(r.passed for r in results))
        removed = remove.call_args[0][0]
        self.assertTrue(removed.endswith('.png'))
        self.assertFalse(os.path.exists(removed))

    def test_token_failure_stops_scenario_and_skips_remaining_steps(self):
        self.server.overrides[('POST', '/api-token-auth/')] = (400, {'detail': 'bad'})
        results = self.run_scenario(self.image_path)
        self.assertEqual([r.passed for r in results], [False, None, None, None, None, None])
        self.assertIn('HTTP 400', results[0].detail)

    def test_invalid_post_list_schema_fails_second_step(self):
        self.server.posts = [make_post(1, image='not-url')]
        results = self.run_scenario(self.image_path)
        self.assertEqual([r.passed for r in results][:3], [True, False, None])
        self.assertIn('image가 URL이 아님', results[1].detail)

    def test_upload_failure_fails_third_step(self):
        self.server.overrides[('POST', '/api_root/Post/')] = (400, {'image': ['필수']})
        results = self.run_scenario(self.image_path)
        self.assertEqual([r.passed for r in results][:4], [True, True, False, None])

    def test_invalid_uploaded_post_fails_third_step_and_is_cleaned_up(self):
        self.server.overrides[('POST', '/api_root/Post/')] = (201, make_post(5, image='x'))
        results = self.run_scenario(self.image_path)
        self.assertFalse(results[2].passed)
        self.assertEqual(self.last_request().get_method(), 'DELETE')
        self.assertEqual(self.last_request().full_url, 'http://testserver/api_root/Post/5/')

    def test_uploaded_post_missing_from_list_fails_fourth_step_and_is_cleaned_up(self):
        self.server.hide_created = True
        results = self.run_scenario(self.image_path)
        self.assertEqual([r.passed for r in results][:5], [True, True, True, False, None])
        self.assertEqual(self.server.posts, [])

    def test_delete_failure_fails_fifth_step_and_cleanup_error_is_ignored(self):
        self.server.overrides[('DELETE', '/api_root/Post/1/')] = (500, b'error')
        results = self.run_scenario(self.image_path)
        self.assertEqual([r.passed for r in results], [True, True, True, True, False, None])

    def test_server_that_allows_anonymous_request_fails_last_step(self):
        self.server.anonymous_status = 200
        results = self.run_scenario(self.image_path)
        self.assertFalse(results[5].passed)
        self.assertIn('인증 없이', results[5].detail)

    def test_server_that_rejects_anonymous_with_403_fails_last_step(self):
        self.server.anonymous_status = 403
        results = self.run_scenario(self.image_path)
        self.assertFalse(results[5].passed)
        self.assertIn('403', results[5].detail)


class TestFormatResultsAndMain(FakeServerTestCase):
    def test_format_results_shows_each_step_and_summary(self):
        text = format_results([StepResult('A', True, 'ok'), StepResult('B', False, 'bad'),
                               StepResult('C', None, '')])
        self.assertIn('[PASS] 1. A - ok', text)
        self.assertIn('[FAIL] 2. B - bad', text)
        self.assertIn('[SKIP] 3. C', text)
        self.assertIn('결과: 1/3 통과', text)

    def run_main(self, *extra):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(['--base-url', BASE_URL, '--user', 'sunwoo', '--password', 'pw',
                         '--image', self.image_path, *extra])
        return code, out.getvalue()

    def test_main_returns_0_and_prints_results_when_all_steps_pass(self):
        code, out = self.run_main('--author', '1')
        self.assertEqual(code, 0)
        self.assertIn('결과: 6/6 통과', out)

    def test_main_returns_1_when_any_step_fails(self):
        self.server.anonymous_status = 200
        code, out = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn('[FAIL]', out)


# ---------------------------------------------------------------- 통합 테스트

LIVE_BASE_URL = os.environ.get('PHOTOBLOG_BASE_URL')
LIVE_USER = os.environ.get('PHOTOBLOG_USER')
LIVE_PASSWORD = os.environ.get('PHOTOBLOG_PASSWORD')
LIVE_AUTHOR = os.environ.get('PHOTOBLOG_AUTHOR', '1')


def live_server_unavailable_reason():
    if not (LIVE_BASE_URL and LIVE_USER and LIVE_PASSWORD):
        return 'PHOTOBLOG_BASE_URL / PHOTOBLOG_USER / PHOTOBLOG_PASSWORD 환경변수 없음'
    try:
        urllib.request.urlopen(LIVE_BASE_URL.rstrip('/') + '/', timeout=3).close()
    except urllib.error.HTTPError:
        pass  # 서버가 응답은 함
    except (urllib.error.URLError, OSError) as e:
        return f'서버에 연결할 수 없음: {e}'
    return None


class TestPhotoBlogApiIntegration(unittest.TestCase):
    """실제 서버(로컬 runserver 또는 PythonAnywhere) 대상 테스트"""

    @classmethod
    def setUpClass(cls):
        reason = live_server_unavailable_reason()
        if reason:
            raise unittest.SkipTest(reason)

    def setUp(self):
        self.api = PhotoBlogApi(LIVE_BASE_URL)
        self.api.get_token(LIVE_USER, LIVE_PASSWORD)
        self.created_ids = []
        fd, self.image_path = tempfile.mkstemp(suffix='.png')
        os.write(fd, minimal_png())
        os.close(fd)

    def tearDown(self):
        for post_id in self.created_ids:
            try:
                self.api.delete_post(post_id)
            except ApiError:
                pass
        os.remove(self.image_path)

    def create(self, title):
        created = self.api.create_post(title, '통합 테스트 본문', self.image_path, author=LIVE_AUTHOR)
        self.created_ids.append(created['id'])
        return created

    def test_get_token_returns_40_character_token(self):
        self.assertEqual(len(self.api.token), 40)

    def test_post_list_is_json_array_that_passes_schema_validation(self):
        posts = self.api.get_posts()
        self.assertIsInstance(posts, list)
        self.assertEqual(self.api.validate_post_list(posts), [])

    def test_uploaded_post_appears_in_api_list_and_web_list(self):
        title = f'integration-{uuid.uuid4().hex[:8]}'
        created = self.create(title)
        self.assertEqual(self.api.validate_post(created), [])
        self.assertIsNotNone(created['published_date'])
        self.assertIn(created['id'], [p['id'] for p in self.api.get_posts()])
        with urllib.request.urlopen(LIVE_BASE_URL.rstrip('/') + '/', timeout=10) as response:
            self.assertIn(title, response.read().decode('utf-8'))

    def test_korean_title_is_saved_without_broken_characters(self):
        created = self.create('통합 테스트 한글 제목')
        self.assertEqual(created['title'], '통합 테스트 한글 제목')

    def test_request_without_token_is_rejected_with_401(self):
        with self.assertRaises(ApiError) as cm:
            PhotoBlogApi(LIVE_BASE_URL).get_posts()
        self.assertEqual(cm.exception.status, 401)

    def test_request_with_wrong_token_is_rejected_with_401(self):
        with self.assertRaises(ApiError) as cm:
            PhotoBlogApi(LIVE_BASE_URL, token='0' * 40).get_posts()
        self.assertEqual(cm.exception.status, 401)

    def test_post_without_title_is_rejected_with_400(self):
        with self.assertRaises(ApiError) as cm:
            self.api.create_post('', '본문', self.image_path, author=LIVE_AUTHOR)
        self.assertEqual(cm.exception.status, 400)

    def test_deleted_post_disappears_from_list(self):
        created = self.create(f'delete-{uuid.uuid4().hex[:8]}')
        self.api.delete_post(created['id'])
        self.created_ids.remove(created['id'])
        self.assertNotIn(created['id'], [p['id'] for p in self.api.get_posts()])

    def test_full_scenario_passes(self):
        results = self.api.run_scenario(LIVE_USER, LIVE_PASSWORD, author=LIVE_AUTHOR)
        self.assertTrue(all(r.passed for r in results), format_results(results))


if __name__ == '__main__':
    unittest.main()
