"""포토 블로그 REST API 검증 엔진

포토 블로그 서버의 REST API(/api_root/Post/)를 호출하고 응답을 검증한다.
HTTP는 표준 라이브러리(urllib.request)만 사용하며, multipart/form-data 바디도
안드로이드 앱의 업로드 로직과 같은 방식으로 직접 구성한다.

CLI:
    python photoblog_api.py --base-url http://127.0.0.1:8000 --user <id> --password <pw> [--author <user id>]
"""
import argparse
import collections
import json
import mimetypes
import os
import struct
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zlib

POSTS_PATH = '/api_root/Post/'
TOKEN_PATH = '/api-token-auth/'
REQUIRED_POST_KEYS = ('author', 'title', 'text', 'created_date', 'published_date', 'image')
# published_date는 null 허용이라 별도로 검사
EXPECTED_TYPES = {'author': int, 'title': str, 'text': str, 'created_date': str, 'image': str}

StepResult = collections.namedtuple('StepResult', 'name passed detail')


class ApiError(Exception):
    """API가 기대한 상태코드로 응답하지 않았을 때 발생. status는 HTTP 상태코드(연결 실패 시 None)"""

    def __init__(self, status, message=''):
        super().__init__(f'HTTP {status}: {message}')
        self.status = status
        self.message = message


class ScenarioError(Exception):
    """시나리오 단계의 검증 실패"""


def minimal_png():
    """Pillow 없이 만든 1x1 빨간 픽셀 PNG 바이트"""
    def chunk(kind, data):
        return (struct.pack('>I', len(data)) + kind + data
                + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff))

    ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)  # 1x1, 8bit, RGB
    idat = zlib.compress(b'\x00\xff\x00\x00')            # 필터 0 + 빨간 픽셀
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', idat) + chunk(b'IEND', b'')


def encode_multipart(fields, files, boundary=None):
    """multipart/form-data 바디와 Content-Type 헤더 값을 만든다

    fields: [(name, value)], files: [(name, filename, content_bytes, content_type)]
    텍스트는 UTF-8로 기록한다(한글 깨짐 방지).
    """
    boundary = boundary or uuid.uuid4().hex
    body = bytearray()
    for name, value in fields:
        body += f'--{boundary}\r\n'.encode()
        body += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        body += str(value).encode('utf-8') + b'\r\n'
    for name, filename, content, content_type in files:
        body += f'--{boundary}\r\n'.encode()
        body += f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode('utf-8')
        body += f'Content-Type: {content_type}\r\n\r\n'.encode()
        body += content + b'\r\n'
    body += f'--{boundary}--\r\n'.encode()
    return bytes(body), f'multipart/form-data; boundary={boundary}'


class PhotoBlogApi:
    def __init__(self, base_url, token=None, timeout=10):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.timeout = timeout

    # ------------------------------------------------------------ HTTP

    def _request(self, method, path, data=None, headers=None, auth=True):
        """요청을 보내고 (상태코드, 바디 bytes)를 반환. 4xx/5xx도 예외 없이 반환한다"""
        headers = dict(headers or {})
        if auth and self.token:
            headers['Authorization'] = f'Token {self.token}'
        request = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except urllib.error.URLError as e:
            raise ApiError(None, f'연결 실패: {e.reason}')

    @staticmethod
    def _expect_json(status, body, expected_status):
        if status != expected_status:
            raise ApiError(status, body.decode('utf-8', 'replace'))
        try:
            return json.loads(body.decode('utf-8'))
        except ValueError:
            raise ApiError(status, '응답이 JSON 형식이 아님')

    # ------------------------------------------------------------ API

    def get_token(self, username, password):
        """아이디/비밀번호로 토큰을 발급받아 저장하고 반환"""
        data = urllib.parse.urlencode({'username': username, 'password': password}).encode()
        status, body = self._request('POST', TOKEN_PATH, data,
                                     {'Content-Type': 'application/x-www-form-urlencoded'}, auth=False)
        result = self._expect_json(status, body, 200)
        if 'token' not in result:
            raise ApiError(status, f'응답에 token 없음: {result}')
        self.token = result['token']
        return self.token

    def get_posts(self):
        """게시물 목록(JSON 배열)을 반환"""
        return self._expect_json(*self._request('GET', POSTS_PATH), 200)

    def create_post(self, title, text, image_path, author=None, published_date=None):
        """이미지를 포함한 게시물을 multipart/form-data로 업로드하고 생성된 게시물을 반환"""
        fields = [('title', title), ('text', text)]
        if author is not None:
            fields.append(('author', author))
        if published_date is not None:
            fields.append(('published_date', published_date))
        with open(image_path, 'rb') as f:
            content = f.read()
        content_type = mimetypes.guess_type(image_path)[0] or 'application/octet-stream'
        files = [('image', os.path.basename(image_path), content, content_type)]
        body, multipart_type = encode_multipart(fields, files)
        status, response = self._request('POST', POSTS_PATH, body, {'Content-Type': multipart_type})
        return self._expect_json(status, response, 201)

    def delete_post(self, post_id):
        status, body = self._request('DELETE', f'{POSTS_PATH}{post_id}/')
        if status != 204:
            raise ApiError(status, body.decode('utf-8', 'replace'))

    # ------------------------------------------------------------ 검증

    def validate_post(self, post):
        """게시물 하나의 스키마를 검사해 문제 목록을 반환 (빈 리스트면 정상)"""
        if not isinstance(post, dict):
            return ['게시물이 객체(dict)가 아님']
        problems = [f'필수 키 누락: {key}' for key in REQUIRED_POST_KEYS if key not in post]
        for key, expected in EXPECTED_TYPES.items():
            value = post.get(key)
            # bool은 int의 하위 클래스이므로 따로 걸러낸다
            if key in post and (not isinstance(value, expected) or isinstance(value, bool)):
                problems.append(f'{key} 타입 오류: {type(value).__name__}')
        published = post.get('published_date')
        if published is not None and not isinstance(published, str):
            problems.append(f'published_date 타입 오류: {type(published).__name__}')
        image = post.get('image')
        if isinstance(image, str) and not image.startswith(('http://', 'https://')):
            problems.append(f'image가 URL이 아님: {image}')
        return problems

    def validate_post_list(self, posts):
        """목록 응답이 배열인지, 각 게시물이 스키마를 만족하는지 검사"""
        if not isinstance(posts, list):
            return ['응답이 배열(list)이 아님']
        problems = []
        for index, post in enumerate(posts):
            problems += [f'[{index}] {problem}' for problem in self.validate_post(post)]
        return problems

    # ------------------------------------------------------------ 시나리오

    def run_scenario(self, username, password, image_path=None, author=None):
        """토큰 → 목록 → 업로드 → 반영 확인 → 삭제 → 인증 없는 요청 거부 순으로 검증

        단계가 실패하면 이후 단계는 실행하지 않는다(passed=None). 업로드한 글은 항상 정리한다.
        """
        state = {}
        temp_path = None
        if image_path is None:
            fd, temp_path = tempfile.mkstemp(suffix='.png')
            os.write(fd, minimal_png())
            os.close(fd)
            image_path = temp_path

        def issue_token():
            return f'token={self.get_token(username, password)[:8]}...'

        def check_list():
            posts = self.get_posts()
            problems = self.validate_post_list(posts)
            if problems:
                raise ScenarioError('; '.join(problems))
            return f'{len(posts)}건, 스키마 정상'

        def upload():
            title = f'scenario-{uuid.uuid4().hex[:8]}'
            created = self.create_post(title, '시나리오 테스트 본문', image_path, author=author)
            state['post_id'] = created.get('id')
            problems = self.validate_post(created)
            if problems:
                raise ScenarioError('; '.join(problems))
            return f"id={created['id']}, title={title}"

        def check_listed():
            if state['post_id'] not in [post.get('id') for post in self.get_posts()]:
                raise ScenarioError(f"업로드한 id={state['post_id']}가 목록에 없음")
            return f"id={state['post_id']} 목록에 있음"

        def delete():
            self.delete_post(state['post_id'])
            state['deleted'] = True
            return f"id={state['post_id']} 삭제(204)"

        def check_anonymous_rejected():
            try:
                PhotoBlogApi(self.base_url, timeout=self.timeout).get_posts()
            except ApiError as e:
                if e.status != 401:
                    raise ScenarioError(f'401이 아닌 {e.status} 응답')
                return '401 Unauthorized'
            raise ScenarioError('인증 없이도 목록이 조회됨')

        steps = [('토큰 발급', issue_token), ('목록 조회 및 스키마 검증', check_list),
                 ('게시물 업로드', upload), ('목록 반영 확인', check_listed),
                 ('게시물 삭제', delete), ('인증 없는 요청 거부', check_anonymous_rejected)]
        results = []
        failed = False
        try:
            for name, step in steps:
                if failed:
                    results.append(StepResult(name, None, '이전 단계 실패로 실행 안 함'))
                    continue
                try:
                    results.append(StepResult(name, True, step()))
                except (ApiError, ScenarioError) as e:
                    results.append(StepResult(name, False, str(e)))
                    failed = True
        finally:
            if state.get('post_id') is not None and not state.get('deleted'):
                try:
                    self.delete_post(state['post_id'])
                except ApiError:
                    pass
            if temp_path:
                os.remove(temp_path)
        return results


def format_results(results):
    labels = {True: 'PASS', False: 'FAIL', None: 'SKIP'}
    lines = []
    for number, result in enumerate(results, 1):
        line = f'[{labels[result.passed]}] {number}. {result.name}'
        if result.detail:
            line += f' - {result.detail}'
        lines.append(line)
    passed = sum(1 for result in results if result.passed)
    lines.append(f'결과: {passed}/{len(results)} 통과')
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description='포토 블로그 REST API 검증 시나리오 실행')
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--user', required=True)
    parser.add_argument('--password', required=True)
    parser.add_argument('--image', help='업로드할 이미지 경로 (없으면 1x1 PNG 자동 생성)')
    parser.add_argument('--author', type=int, help='게시물 author(사용자 id)')
    args = parser.parse_args(argv)

    api = PhotoBlogApi(args.base_url)
    results = api.run_scenario(args.user, args.password, image_path=args.image, author=args.author)
    print(f'대상 서버: {api.base_url}')
    print(format_results(results))
    return 0 if all(result.passed for result in results) else 1


if __name__ == '__main__':
    sys.exit(main())
