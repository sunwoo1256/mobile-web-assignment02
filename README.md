# PhotoBlog

모바일/웹서비스 프로젝트 공통평가 01 — Chapter 05. 모바일 앱으로 사용하는 기본 포토 블로그

- **Server**: Django + Django REST Framework 포토 블로그 (게시물 = 제목/본문/이미지) — [kiokahn/web_blog](https://github.com/kiokahn/web_blog) 기반
- **Client**: Android(Java) 앱 — 로그인 후 서버 게시물을 동기화해 카드 피드로 표시하고, 새 게시물 업로드·좋아요·댓글·삭제
- **배포**: https://sunwoo.pythonanywhere.com

## 폴더 구조

```
ROOT/
├── PhotoBlogServer/            # Django 서버 (manage.py 위치)
│   ├── mysite/  blog/  media/images/default_error.png
│   ├── requirements.txt        # + requirements-dev.txt (coverage)
│   ├── tools/                  # telnet 요청 원문 (telnet_request.txt)
│   ├── socket_server/          # 요청 메시지 검증용 소켓 서버 (request/, response.bin)
│   └── api_test_engine/        # API 검증 엔진 + unittest 자동 테스트
├── PhotoViewer/                # Android Studio 프로젝트 (package: com.example.imageviewdemo)
├── 모바일웹서비스 프로젝트_공통평가 01_수행 결과 보고서.docx
├── .gitattributes              # *.bin 등 HTTP 원문의 CRLF 보존
├── .gitignore
└── README.md
```

## 테스트 요약

| 대상 | 개수 | 결과 |
|---|---|---|
| API 검증 엔진 `photoblog_api.py` | 단위 46 + 통합 9 | 통과, 커버리지 **100%** (구문·분기) |
| 서버 `blog` 앱 | 63 | 통과, 커버리지 **100%** |
| Android JVM 단위 테스트 | 11 (MultipartBody 5, TimeUtils 5, 예제 1) | 통과 |

## 서버 실행 (로컬)

Python **3.12 이상** 필요 (Django 6.1). 모든 명령은 `PhotoBlogServer/`에서 실행한다.

```powershell
cd PhotoBlogServer

# 1. 가상환경 생성 및 활성화
python -m venv venv
.\venv\Scripts\Activate.ps1        # Windows PowerShell
# source venv/bin/activate          # macOS / Linux

# 2. 라이브러리 설치
pip install -r requirements.txt

# 3. DB 마이그레이션
python manage.py migrate

# 4. 관리자 계정 생성
python manage.py createsuperuser

# 5. 앱/telnet에서 사용할 토큰 생성 (아래 "토큰 생성" 참고)
python manage.py drf_create_token <username>

# 6. 서버 실행 (에뮬레이터에서 접속하려면 0.0.0.0으로 실행)
python manage.py runserver 0.0.0.0:8000
```

> PowerShell에서 `Activate.ps1` 실행이 막히면: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

| 주소 | 설명 |
|---|---|
| http://127.0.0.1:8000/ | 웹 블로그 목록 (로그인 시 우상단 `+`로 글쓰기, 이미지 첨부 가능) |
| http://127.0.0.1:8000/admin/ | 관리자 |
| http://127.0.0.1:8000/api_root/ | DRF API Root |
| http://127.0.0.1:8000/api_root/Post/ | 게시물 목록(GET) / 작성(POST) |
| http://127.0.0.1:8000/api-auth/login/ | 브라우저블 API 로그인 (우상단 "Log in"과 동일) |
| http://127.0.0.1:8000/api-token-auth/ | 아이디/비밀번호 → 토큰 발급(POST) |

안드로이드 에뮬레이터에서는 `127.0.0.1` 대신 `10.0.2.2`로 접속한다.

## API

모든 API는 **인증 필요**. 인증 없이 요청하면 `401 Unauthorized`.

- 앱/telnet: 헤더 `Authorization: Token <TOKEN>`
- 브라우저: `/api-auth/login/`에서 로그인(세션)

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api-token-auth/` | 로그인: `username`, `password` → `{"token", "user_id", "username"}` (인증 불필요) |
| GET | `/api_root/Post/` | 게시물 목록 — **최신순**, JSON 배열, `image`는 절대 URL |
| POST | `/api_root/Post/` | 게시물 작성 (multipart/form-data: `title`, `text`, `image`, 선택 `published_date`). **`author`는 로그인한 사용자로 자동 지정** |
| GET | `/api_root/Post/<id>/` | 게시물 상세 — 조회할 때마다 **조회수 +1** |
| PUT/PATCH | `/api_root/Post/<id>/` | 게시물 수정 — **작성자만** (다른 사용자는 403) |
| DELETE | `/api_root/Post/<id>/` | 게시물 삭제 — **작성자만** (다른 사용자는 403), 좋아요·댓글도 함께 삭제 |
| POST / DELETE | `/api_root/Post/<id>/like/` | 좋아요 / 좋아요 취소 → `{"is_liked", "like_count"}` (사용자당 1회) |
| GET / POST | `/api_root/Post/<id>/comments/` | 댓글 목록(오래된 순) / 댓글 작성(`text`) |
| DELETE | `/api_root/Comment/<id>/` | 댓글 삭제 — **작성자만** |

`published_date`를 보내지 않으면 서버가 현재 시각으로 채워, 웹 목록에도 바로 표시된다.

게시물 응답 예시 (앞의 7개 필드는 교수님 코드와 같은 순서, 뒤는 편의 기능용):

```json
[
  {
    "id": 1,
    "author": 1,
    "title": "첫 번째 사진",
    "text": "본문",
    "created_date": "2026-10-16T00:02:42.982694+09:00",
    "published_date": "2026-10-16T00:02:42.982554+09:00",
    "image": "http://127.0.0.1:8000/media/images/2026/10/16/a.jpg",
    "author_name": "sunwoo",
    "view_count": 12,
    "like_count": 3,
    "comment_count": 2,
    "is_liked": true,
    "is_mine": true
  }
]
```

`is_liked`(내가 좋아요를 눌렀는지), `is_mine`(내가 쓴 글인지)은 요청한 사용자 기준으로 계산된다.

### 브라우저에서 API로 게시물 작성 (보고서 ID 3)

1. `runserver` 실행 후 http://127.0.0.1:8000/api_root/Post/ 접속 → 우상단 **Log in**으로 로그인
2. 페이지 하단 **HTML form** 탭에서 Title/Text 입력, Image 파일 선택 → **POST** (Author는 로그인한 사용자로 자동 지정)
3. `HTTP 201 Created` 응답 화면 확인 → http://127.0.0.1:8000/ 웹 목록에도 표시됨

## 토큰 생성

방법 1 — 관리 명령 (토큰이 이미 있으면 기존 토큰 출력):

```powershell
python manage.py drf_create_token <username>
# Generated token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b for user admin
```

방법 2 — API (아이디/비밀번호로 발급):

```powershell
curl.exe -X POST -d "username=<id>&password=<pw>" http://127.0.0.1:8000/api-token-auth/
# {"token":"9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b","user_id":1,"username":"admin"}
```

방법 3 — 관리자 화면: http://127.0.0.1:8000/admin/ → **인증 토큰 > 토큰(들)**

토큰 재발급이 필요하면 `python manage.py drf_create_token -r <username>`.

## telnet / JSON Viewer 검증

안드로이드 앱이 보내는 것과 같은 HTTP 요청을 telnet으로 직접 보내 응답을 확인한다. 요청 원문은 [`PhotoBlogServer/tools/telnet_request.txt`](PhotoBlogServer/tools/telnet_request.txt)에 있다 (`<TOKEN>`을 실제 토큰으로 바꿔 사용).

```
GET /api_root/Post/ HTTP/1.1
Authorization: Token <TOKEN>
User-Agent: Dalvik/2.1.0 (Linux; U; Android 13; sdk_gphone64_arm64 Build/TPB4.220624.004)
Host: 10.0.2.2:8000
Connection: Keep-Alive
Accept-Encoding: gzip

```

- 헤더 끝을 알리는 **빈 줄(Enter 한 번 더)이 반드시 있어야** 서버가 응답한다.
- `Host`는 `ALLOWED_HOSTS`에 있는 값이어야 한다(아니면 400). `10.0.2.2:8000`으로 보내면 응답의 `image` URL도 `http://10.0.2.2:8000/...`로 만들어진다.
- `Accept-Encoding: gzip`이 있어도 Django 개발 서버는 압축하지 않으므로(GZipMiddleware 미사용) 응답 본문은 평문 JSON이다. 응답이 깨진 바이너리로 보이면 이 줄을 빼고 보낸다.

### Windows에서 Telnet Client 활성화

- 방법 1: 제어판 → 프로그램 → **Windows 기능 켜기/끄기** → **텔넷 클라이언트(Telnet Client)** 체크 → 확인
- 방법 2: **관리자 권한** PowerShell에서
  ```powershell
  Enable-WindowsOptionalFeature -Online -FeatureName TelnetClient
  ```
- macOS: `brew install telnet`

### 요청 보내기 (Windows)

```powershell
chcp 65001          # 응답의 한글(UTF-8)이 깨지지 않도록 콘솔 코드페이지 변경
telnet
```

telnet 프롬프트(`Microsoft Telnet>`)에서:

```
set localecho       # 입력한 내용이 화면에 보이도록 (기본은 안 보임)
open 127.0.0.1 8000
```

연결되면 화면이 지워진다. 이 상태에서 요청 원문(토큰 치환본)을 붙여넣고(Windows Terminal: `Ctrl+V` 또는 마우스 오른쪽 클릭) 마지막에 **Enter를 한 번 더** 눌러 빈 줄을 보낸다.
> **주의: telnet은 누른 키를 즉시 서버로 보낸다.** 방향키(↑)·백스페이스로 수정하면 그 제어 코드(`\u001b[A` 등)까지 전송되어 `405 Method Not Allowed`(메서드 `"\u001b[A...GET"`)가 나고 연결이 끊긴다. 연결 후에는 다른 키를 누르지 말고 붙여넣기만 하고, 잘못 입력했으면 `Ctrl + ]` → `quit` 후 다시 `open`한다.

`HTTP/1.1 200 OK` 헤더와 JSON 배열 본문이 출력된다. 토큰을 빼거나 틀리게 보내면 `401 Unauthorized`가 나온다.
종료: `Ctrl + ]` → `quit`

> `chcp 65001`을 해도 한글이 깨져 보이면 콘솔 표시 문제일 뿐 서버 응답은 정상(UTF-8)이다. 다음 단계의 JSON Viewer에서는 정상 표시된다.

### JSON Viewer로 응답 확인

1. telnet 응답에서 본문(`[` ~ `]`)만 복사
2. https://codebeautify.org/jsonviewer 왼쪽 입력창에 붙여넣기
3. **Beautify** / **Tree View**로 구조 확인

## API 검증 엔진 · 자동 테스트 · Coverage

강의자료 ch04(TDD) 방식으로 **엔진(실제 코드) ↔ 테스트 코드**를 짝으로 만들었다. 테스트는 표준 라이브러리 `unittest`만 사용한다.

| 파일 | 역할 |
|---|---|
| [`api_test_engine/photoblog_api.py`](PhotoBlogServer/api_test_engine/photoblog_api.py) | 엔진. 포토 블로그 REST API 호출·검증 클래스 `PhotoBlogApi` (`urllib`만 사용) |
| [`api_test_engine/test_photoblog_api.py`](PhotoBlogServer/api_test_engine/test_photoblog_api.py) | 엔진 테스트. 단위 46개(서버 없이 `FakeServer`로 HTTP 대체) + 통합 9개(실제 서버) = 55개 |
| [`blog/tests.py`](PhotoBlogServer/blog/tests.py) | Django 서버 측 테스트 63개 (API·토큰·웹 뷰·모델 + 편의 기능: 로그인/권한/조회수/좋아요/댓글) |

### 엔진 `PhotoBlogApi`

| 메서드 | 설명 |
|---|---|
| `get_token(username, password)` | `/api-token-auth/`로 토큰 발급 후 저장 |
| `get_posts()` | `GET /api_root/Post/` → JSON 배열 |
| `create_post(title, text, image_path, author=None, published_date=None)` | multipart/form-data 업로드 (바디 직접 구성, 텍스트 UTF-8) |
| `delete_post(post_id)` | `DELETE /api_root/Post/<id>/` (204 기대) |
| `validate_post(post)` / `validate_post_list(posts)` | 필수 키·타입·image URL 검사 → 문제 목록 (빈 리스트면 정상) |
| `run_scenario(...)` | 토큰 → 목록 → 업로드 → 반영 확인 → 삭제 → 인증 없는 요청 거부(401) 6단계 실행 |

기대한 상태코드가 아니면 `ApiError(status, message)`를 던진다(연결 실패 시 `status=None`).

CLI로 서버 하나를 통째로 검증할 수 있다 (로컬/PythonAnywhere 공용, 실패 시 exit code 1):

```powershell
cd PhotoBlogServer\api_test_engine
..\venv\Scripts\python photoblog_api.py --base-url http://127.0.0.1:8000 --user <id> --password <pw>
```
```
대상 서버: http://127.0.0.1:8000
[PASS] 1. 토큰 발급 - token=52ce898a...
[PASS] 2. 목록 조회 및 스키마 검증 - 0건, 스키마 정상
[PASS] 3. 게시물 업로드 - id=5, title=scenario-79bdc8a8
[PASS] 4. 목록 반영 확인 - id=5 목록에 있음
[PASS] 5. 게시물 삭제 - id=5 삭제(204)
[PASS] 6. 인증 없는 요청 거부 - 401 Unauthorized
결과: 6/6 통과
```

> 서버가 `author`를 로그인한 사용자로 자동 지정하므로 `--author`(선택)는 보내도 무시된다. 업로드한 글은 시나리오 끝에 삭제하지만, 서버의 `media/`에 이미지 파일은 남는다(Django는 행 삭제 시 파일을 지우지 않음).

### 테스트 실행

```powershell
cd PhotoBlogServer
pip install -r requirements-dev.txt          # coverage 설치

# 1) 엔진 테스트 — 서버 없이도 실행 가능 (통합 테스트는 skip)
cd api_test_engine
..\venv\Scripts\python test_photoblog_api.py

# 통합 테스트까지 실행하려면 runserver를 켠 상태에서 환경변수 지정
$env:PHOTOBLOG_BASE_URL = "http://127.0.0.1:8000"
$env:PHOTOBLOG_USER = "<id>"
$env:PHOTOBLOG_PASSWORD = "<pw>"
..\venv\Scripts\python test_photoblog_api.py

# 2) 서버 측 테스트 (임시 DB·임시 media 사용, 실제 데이터에 영향 없음)
cd ..
python manage.py test blog -v 2
```

### Code Coverage

```powershell
# 엔진 커버리지 (보고서 ID 6 메인)
cd PhotoBlogServer\api_test_engine
..\venv\Scripts\python -m coverage run test_photoblog_api.py
..\venv\Scripts\python -m coverage report -m
..\venv\Scripts\python -m coverage html      # → api_test_engine\htmlcov\index.html

# 서버 측 커버리지 (보조)
cd ..
python -m coverage run --source=blog manage.py test blog
python -m coverage report -m
python -m coverage html                      # → PhotoBlogServer\htmlcov\index.html
```

측정 결과:

| 대상 | 결과 |
|---|---|
| `photoblog_api.py` (엔진) | **100%** — 구문 203 / 분기 52, Miss 0 (`.coveragerc`에서 branch 측정) |
| `test_photoblog_api.py` | 서버 실행 시 98%, 미실행 시 87% (차이는 skip된 통합 테스트) |
| `blog` 앱 | **100%** — 568 구문, Miss 0 (편의 기능 포함 63개 테스트) |

`api_test_engine/.coveragerc`는 분기 커버리지를 켜고, CLI 진입점(`if __name__ == '__main__':`) 한 줄만 측정에서 제외한다(`main()`은 테스트에서 직접 호출해 검증).

### TDD 진행 기록

git 이력으로 확인할 수 있다.

1. `7bb57d2 test(engine): ...` — 테스트 먼저 작성, 엔진은 인터페이스만 → `FAILED (failures=9, errors=37, skipped=1)`
2. `15f2658 feat(engine): ...` — 엔진 구현 → `OK (skipped=1)`, 커버리지 100%

빨강 단계를 다시 보려면: `git stash; git checkout 7bb57d2 -- PhotoBlogServer/api_test_engine` → 실행 → `git checkout HEAD -- PhotoBlogServer/api_test_engine; git stash pop`

## Socket Server

앱이 보내는 HTTP 요청 원문(헤더 + multipart 바디)을 파일로 저장하는 소켓 서버. 자세한 내용은 [`PhotoBlogServer/socket_server/README.md`](PhotoBlogServer/socket_server/README.md).

```powershell
# Django 서버를 끈 뒤 같은 포트(8000)로 실행
cd PhotoBlogServer\socket_server
..\venv\Scripts\python socket_server.py
```

앱에서 동기화/업로드 → `socket_server/request/YYYY-MM-DD-HH-MM-SS.bin` 생성 → VSCode로 열어 확인.

## Android 앱 실행

`PhotoViewer/`를 Android Studio로 연다 (compileSdk/targetSdk 34, minSdk 24, Java 11).

### 로그인과 서버 선택

앱을 실행하면 **로그인 화면**이 나온다. 서버 계정(아이디·비밀번호)으로 로그인하면 토큰을 발급받아 저장하고, 다음 실행부터는 자동 로그인된다. 토큰을 코드나 빌드 설정에 적지 않는다.

- **서버**: `로컬`(`http://10.0.2.2:8000`) / `클라우드`(`https://sunwoo.pythonanywhere.com`) / `직접 입력` 중 선택. 에뮬레이터에서 PC의 `127.0.0.1`은 `10.0.2.2`이므로 Django는 `python manage.py runserver 0.0.0.0:8000`으로 실행한다.
- 계정은 서버에서 `python manage.py createsuperuser` 또는 관리자 화면(`/admin/` → 사용자 추가)으로 만든다.
- 로그아웃: 피드 우상단 ⋮ → 로그아웃.
- 서버 주소·토큰·사용자 이름은 [`ApiConfig`](PhotoViewer/app/src/main/java/com/example/imageviewdemo/ApiConfig.java)(SharedPreferences)에서 한 곳으로 관리한다.
- (선택) 로그인 화면의 서버 기본값은 `PhotoViewer/local.properties`(git 제외)로 바꿀 수 있다: `photoblog.baseUrl=http://10.0.2.2:8000`

### 빌드 (명령줄)

```powershell
cd PhotoViewer
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
.\gradlew assembleDebug        # → app\build\outputs\apk\debug\app-debug.apk
```

### 동기화

1. Django 서버 실행
2. 앱에서 **동기화** → `GET /api_root/Post/` (헤더 `Authorization: Token <토큰>`) → 각 게시물의 `image` URL에서 이미지 다운로드 → 목록 표시
3. "이미지 로드 성공!" 표시. 게시물이 없으면 "불러올 이미지가 없습니다.", 서버 오류면 상태코드/원인을 표시

### 업로드 — "상": Post에 따른 UI 제공

**새로운 이미지 게시** → `UploadActivity`. 화면 구성이 `Post` 모델 필드와 1:1로 대응한다.

| Post 필드 | 입력 UI | 비고 |
|---|---|---|
| `title` | 제목 EditText (최대 200자, 모델 `max_length=200`) | 필수 |
| `text` | 본문 EditText (여러 줄) | 필수 (모델이 빈 값 불가) |
| `image` | 이미지 선택 버튼(Photo Picker) + 미리보기 | 필수 |
| `author` | (자동) 서버가 로그인한 사용자로 지정 | 앱은 보내지 않음 |
| `published_date` | (자동) 현재 시각 ISO-8601 | 서버 보정과 이중 안전장치 |

- 세 필수 항목이 모두 채워져야 **게시하기** 버튼이 활성화되고, 상태 문구로 안내한다.
- 이미지 선택은 `ActivityResultContracts.PickVisualMedia`(Android Photo Picker) — 저장소 권한 불필요.
- 업로드 중에는 ProgressBar 표시, 입력칸·버튼 비활성화(중복 업로드 방지).
- `201 Created` → "업로드 성공!" 토스트 → 화면 종료 → 메인 목록 **자동 재동기화**.
- 실패 → 서버 오류 본문(`getErrorStream()`) 또는 연결 오류를 화면에 표시하고 다시 시도할 수 있게 버튼을 되살린다.

### 클라이언트 단위 테스트

Android 의존성이 없는 클래스는 JVM에서 테스트한다.

- `MultipartBodyTest` (5개): multipart 바디의 한글 UTF-8, 파트 순서·경계
- `TimeUtilsTest` (5개): ISO-8601 파싱(시간대·소수 초), "방금 전 / N분 전 / N시간 전 / N일 전 / 날짜" 변환

```powershell
cd PhotoViewer
.\gradlew testDebugUnitTest
```

## PythonAnywhere 배포

아래에서 `<id>`는 PythonAnywhere 사용자명이다. 배포 주소는 `https://<id>.pythonanywhere.com`.

### 0. 사전 준비

- 레포: https://github.com/sunwoo1256/mobile-web-assignment01 (PythonAnywhere에서 `git clone`)
- Django 6.1은 **Python 3.12 이상**이 필요하다. PythonAnywhere **Account → System image**가 3.12를 지원하는 이미지인지 확인한다.

### 1. Bash 콘솔 — 코드 받기·설치

PythonAnywhere **Consoles → Bash**:

```bash
git clone https://github.com/sunwoo1256/mobile-web-assignment01.git ~/PhotoBlog
mkvirtualenv --python=python3.12 photoblog        # 가상환경 생성 + 활성화 (프롬프트에 (photoblog))
pip install -r ~/PhotoBlog/PhotoBlogServer/requirements.txt
```

### 2. DB·관리자·토큰·정적 파일

```bash
cd ~/PhotoBlog/PhotoBlogServer
python manage.py migrate
python manage.py createsuperuser
python manage.py drf_create_token <username>      # 출력된 토큰을 앱 설정에 사용
python manage.py collectstatic --noinput          # → staticfiles/
```

### 3. Web 탭 — 웹 앱 생성

1. **Web → Add a new web app** → 도메인 확인 → **Manual configuration** (Django 자동 설정 아님) → **Python 3.12**
2. **Virtualenv**: `/home/<id>/.virtualenvs/photoblog`
3. **Source code**: `/home/<id>/PhotoBlog/PhotoBlogServer`

### 4. WSGI 파일

Web 탭의 **WSGI configuration file** 링크(`/var/www/<id>_pythonanywhere_com_wsgi.py`)를 열어 **전체를 아래로 교체**한다.

```python
import os
import sys

path = '/home/<id>/PhotoBlog/PhotoBlogServer'
if path not in sys.path:
    sys.path.insert(0, path)

os.environ['DJANGO_SETTINGS_MODULE'] = 'mysite.settings'
os.environ['DJANGO_DEBUG'] = 'False'
os.environ['DJANGO_SECRET_KEY'] = '<아래 명령으로 만든 임의의 긴 문자열>'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

SECRET_KEY 만들기 (Bash 콘솔, 가상환경 활성 상태):

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 5. Static files 매핑

Web 탭 **Static files**에 두 줄을 추가한다. **`/media/`를 빠뜨리면 앱과 웹에서 이미지가 뜨지 않는다** (`DEBUG=False`에서는 Django가 media를 직접 제공하지 않음).

| URL | Directory |
|---|---|
| `/static/` | `/home/<id>/PhotoBlog/PhotoBlogServer/staticfiles` |
| `/media/` | `/home/<id>/PhotoBlog/PhotoBlogServer/media` |

### 6. Reload 후 확인

Web 탭 **Reload** → 브라우저에서 확인:

- `https://<id>.pythonanywhere.com/` — 웹 목록
- `https://<id>.pythonanywhere.com/api_root/Post/` — 로그인 후 API (게시물 `image`가 `https://` 절대 URL인지)
- `https://<id>.pythonanywhere.com/admin/` — 관리자 로그인

API 검증 엔진으로 클라우드 서버 전체 시나리오를 한 번에 확인할 수 있다 (로컬 PC에서 실행):

```powershell
cd PhotoBlogServer\api_test_engine
..\venv\Scripts\python photoblog_api.py --base-url https://<id>.pythonanywhere.com --user <id> --password <pw>
```

### 7. 앱을 클라우드 서버에 연결

앱 로그인 화면에서 서버를 **클라우드**(또는 `직접 입력`에 `https://<id>.pythonanywhere.com`)로 고르고, 클라우드 서버의 계정으로 로그인한다. 다시 빌드할 필요가 없다. 이미 로그인되어 있으면 ⋮ → 로그아웃 후 서버를 바꾼다.

### 코드 수정 후 재배포

> Task 8(편의 기능)에서 모델이 추가되었으므로(`0005` 마이그레이션) 이전에 배포했다면 아래 절차를 꼭 실행한다.


```bash
cd ~/PhotoBlog && git pull
workon photoblog
cd PhotoBlogServer
python manage.py migrate
python manage.py collectstatic --noinput
```

→ Web 탭 **Reload**.

### 문제 해결

| 증상 | 확인할 것 |
|---|---|
| `DisallowedHost` / 400 | `ALLOWED_HOSTS`에 `.pythonanywhere.com` 있음. 도메인 철자 확인 |
| 웹은 되는데 이미지가 안 뜸 | Static files의 `/media/` 매핑 |
| 관리자 화면 CSS 깨짐 | `collectstatic` 실행 여부, `/static/` 매핑 |
| 500 Internal Server Error | Web 탭의 **Error log** |
| `ModuleNotFoundError: mysite` | WSGI 파일의 `path`가 `.../PhotoBlogServer`(manage.py가 있는 폴더)인지 |

## Client 편의 기능

포토 블로그에서 가장 직관적인 상호작용 5가지를 구현했다. 서버 수정이 필요한 기능은 서버/클라이언트를 나눠 적는다. 서버 API는 TDD(테스트 먼저 → 구현)로 만들었다 (`d083274` 빨강 → `66ac97a` 초록, `blog` 테스트 63개·커버리지 100%).

| # | 기능 | 한 줄 정의 |
|---|---|---|
| 1 | 로그인 | 아이디·비밀번호로 로그인하고, 내가 누구인지에 따라 글쓴이·좋아요·삭제 권한이 정해진다 |
| 2 | 좋아요 | 하트 버튼 또는 사진 더블탭으로 게시물에 좋아요를 누르고 취소한다 |
| 3 | 댓글 | 게시물 상세 화면에서 댓글을 읽고, 쓰고, 내 댓글을 지운다 |
| 4 | 조회수 | 게시물 상세를 열 때마다 조회수가 올라가고 목록·상세에 표시된다 |
| 5 | 삭제 | 내가 쓴 게시물만 확인 후 삭제할 수 있다 |

### 1. 로그인

- **정의**: 서버 계정으로 로그인해 토큰을 발급받아 저장하고, 이후 모든 요청에 사용한다. 하드코딩된 토큰을 없앴다.
- **서버**
  - `/api-token-auth/` 응답에 `user_id`, `username` 추가 (`LoginToken` 뷰)
  - 게시물 `author`를 **읽기 전용**으로 바꾸고 `perform_create`에서 `request.user`로 지정 → 클라이언트가 author를 보내도 무시
  - 응답에 `author_name`(작성자 이름), `is_mine`(내 글 여부) 추가
- **클라이언트**: `LoginActivity`(앱 시작 화면)
  - 아이디·비밀번호 입력(비밀번호 보기 토글), 서버 선택 칩(로컬/클라우드/직접 입력)
  - 성공 시 토큰·사용자 이름을 SharedPreferences에 저장 → 다음 실행부터 **자동 로그인**
  - 실패 메시지 구분: 아이디/비밀번호 오류(400) / 서버 연결 실패(주소 표시)
  - 피드 상단에 `@사용자 · 서버` 표시, ⋮ → **로그아웃**
  - 토큰이 만료·무효(401)면 자동으로 로그인 화면으로 이동
- **사용법**: 앱 실행 → 아이디/비밀번호 입력 → 서버 선택 → 로그인

### 2. 좋아요

- **정의**: 게시물마다 사용자당 한 번 좋아요를 누르거나 취소할 수 있고, 좋아요 수와 내가 눌렀는지가 보인다.
- **서버**: `Like` 모델(게시물·사용자 **unique**), `POST`/`DELETE /api_root/Post/<id>/like/` → `{"is_liked", "like_count"}`. 목록·상세에 `like_count`, `is_liked`(요청한 사용자 기준). 게시물 삭제 시 함께 삭제
- **클라이언트**
  - 카드·상세의 하트 버튼: 빈 하트 ↔ 빨간 하트, 누를 때 튀어 오르는 애니메이션
  - **사진 더블탭**으로 좋아요 + 사진 가운데 큰 하트가 커졌다 사라지는 효과(인스타그램 방식). 이미 누른 글은 다시 눌러도 취소되지 않음
  - 화면을 먼저 바꾸고(낙관적 업데이트) 서버 응답으로 개수를 맞추며, 실패하면 원래대로 되돌리고 안내
- **사용법**: 하트를 누르거나 사진을 두 번 탭한다. 다시 하트를 누르면 취소

### 3. 댓글

- **정의**: 게시물에 댓글을 남기고 다른 사용자의 댓글을 읽는다. 내 댓글은 지울 수 있다.
- **서버**: `Comment` 모델(게시물·작성자·내용·작성일), `GET`/`POST /api_root/Post/<id>/comments/`(오래된 순, 빈 댓글 400), `DELETE /api_root/Comment/<id>/`(작성자만, 다른 사용자는 403). 목록에 `comment_count`
- **클라이언트**: 상세 화면(`DetailActivity`) 아래 댓글 목록 — 작성자 아바타·이름·"N분 전"·내용, 내 댓글에만 "삭제". 화면 하단에 고정된 입력창과 보내기 버튼(입력이 없으면 비활성). 카드의 💬 버튼을 누르면 상세로 가서 입력창에 바로 포커스
- **사용법**: 게시물을 누르거나 💬 버튼 → 아래 "댓글 달기..."에 입력 → 보내기. 내 댓글의 "삭제" → 확인

### 4. 조회수

- **정의**: 게시물 상세를 볼 때마다 조회수가 1 늘고, 목록과 상세에 👁 숫자로 보인다.
- **서버**: `Post.view_count` 필드(마이그레이션 `0005`), 상세 조회(`GET /Post/<id>/`)에서 DB의 `F('view_count') + 1`로 증가(동시 요청에도 정확). 목록 조회는 증가하지 않으며, 클라이언트가 값을 바꿀 수 없다(읽기 전용)
- **클라이언트**: 카드 오른쪽 아래와 상세 화면에 👁 조회수. 상세에서 돌아오면 목록을 다시 동기화해 바뀐 조회수·좋아요·댓글 수를 반영
- **사용법**: 게시물을 열면 자동으로 반영된다

### 5. 삭제

- **정의**: 내가 쓴 게시물만 확인 창을 거쳐 삭제한다. 다른 사람 글에는 삭제 메뉴가 보이지 않는다.
- **서버**: `IsAuthorOrReadOnly` 권한 — 조회는 누구나, 수정·삭제는 작성자만(다른 사용자는 403). 게시물을 지우면 좋아요·댓글도 함께 삭제
- **클라이언트**: 내 글 카드에만 ⋮ 버튼(또는 카드 길게 누르기) → 삭제 → "게시물을 삭제할까요?" 확인 → 목록에서 바로 사라지고 "게시물을 삭제했습니다." 알림. 상세 화면 툴바의 🗑 버튼으로도 삭제
- **사용법**: 내 게시물의 ⋮ → 삭제 → 확인

### 함께 개선한 화면 (편의 기능 개수에는 포함하지 않음)

- **디자인 전면 개편** (Material 3): 보라→핑크→오렌지 그라데이션 브랜드 색, 카드형 피드(아바타·정사각형 사진·♥💬👁), 원본 비율 사진의 상세 화면, 사진부터 고르는 업로드 화면, 다크 모드 색상
- 당겨서 새로고침, 앱 시작 시 자동 동기화, 게시물이 없을 때 안내 화면
- 상대 시간 표시("방금 전", "3시간 전"), 이미지 메모리 캐시(LruCache)로 새로고침 시 다시 받지 않음

### 시연 팁

좋아요·댓글이 **사용자별로** 동작하는 것을 보이려면 계정이 두 개 필요하다. 관리자 화면(`/admin/` → 사용자 → 추가)에서 두 번째 계정을 만들고, 한 계정으로 글을 올린 뒤 다른 계정으로 로그인해 좋아요·댓글을 남긴다(다른 계정의 글에는 삭제 메뉴가 없음).

## 구현 노트

교수님 코드(`kiokahn/web_blog` main, `cfd84c0`)·슬라이드와 다르게 구현한 부분과 그 이유를 기록한다.

### 서버 (교수님 코드 수정 사항)

1. **모델/마이그레이션 불일치 정리** — 모델은 `upload_to='images/%Y/%m/%d/'`, `default='images/default_error.png'`인데 마지막 마이그레이션(0003)은 `intruder_image/...`로 남아 있었다. `makemigrations`로 `0004_alter_post_image.py`를 생성해 일치시켰다.
2. **API로 올린 글이 웹 목록에 보이도록** — 웹 `post_list`는 `published_date <= now`인 글만 보여주는데 API POST는 `published_date`가 null로 저장됐다. `BlogImages.perform_create`에서 값이 없으면 `timezone.now()`로 채운다. (값을 보내면 그대로 사용)
3. **토큰 인증 적용** — `REST_FRAMEWORK`에 인증 클래스가 없어 `Authorization: Token ...` 헤더가 무시됐다. `TokenAuthentication`, `SessionAuthentication` + `IsAuthenticated`를 기본값으로 지정했다.
   - **Token을 Session보다 앞에 둔다.** DRF는 첫 번째 인증 클래스로 401/403을 결정하므로, Session이 먼저면 인증 없는 요청이 403이 된다. Token을 먼저 두어 401 + `WWW-Authenticate: Token` 헤더로 응답하게 했다.
   - 브라우저블 API 로그인을 위해 `api-auth/`(`rest_framework.urls`)를 추가했다.
4. **`PAGE_SIZE: 10` 제거** — 페이지네이션 클래스가 없어 실제로는 무시되던 값이고 `manage.py check` 경고(W001)만 냈다. 페이지네이션을 켜면 응답이 JSON 배열이 아니게 되어 앱 파싱이 깨지므로 켜지 않고 제거했다.
5. **ViewSet 이름 변경** — `IntruderImage` → 슬라이드와 같은 `BlogImages`.
6. **serializer에 `id` 추가** — 앱의 삭제·상세 기능에서 게시물을 식별하기 위함. 기존 필드 순서는 유지했다.
7. **웹 글쓰기 폼 이미지 업로드 지원** — 웹 `+` 버튼으로도 이미지 포함 게시물을 쓸 수 있게 했다.
   - `PostForm`에 `image` 추가. 이미지 미선택 시 새 글은 모델 기본값(`default_error.png`), 수정은 기존 이미지 유지. "지우기" 체크박스(ClearableFileInput)는 image가 빈 값이 되어 목록의 `post.image.url`에서 오류가 나므로 `FileInput`을 사용했다.
   - `post_edit.html` 폼에 `enctype="multipart/form-data"`, 뷰에서 `request.FILES` 전달.
   - `post_new`/`post_edit`에 `@login_required` 적용 — 기존에는 비로그인 상태로 저장하면 `author=AnonymousUser`로 오류가 났다. 로그인 화면은 `LOGIN_URL = 'rest_framework:login'`(DRF 로그인 화면)을 재사용한다.
   - `post_detail.html`에 이미지 표시 추가 (목록 화면은 슬라이드 25와 같게 유지).
   - 보고서 ID 14(Client 편의 기능)에는 포함하지 않는다.

### 테스트

- 초록 단계 구현 중 테스트용 `FakeServer`가 `json.dumps` 기본값(`ensure_ascii=True`)으로 한글을 `\uXXXX`로 내보내 실패한 테스트 2건이 있었다. 실제 DRF 서버는 UTF-8 원문을 보내므로(telnet으로 확인) 가짜 서버를 `ensure_ascii=False`로 고쳤다.
- `blog/tests.py`는 Task 0에서 이미 구현한 서버 기능을 검증하므로 빨강 단계 없이 작성했다. 이후 서버 기능(Task 8)은 테스트를 먼저 추가한다.

### 배포

- `SECRET_KEY`, `DEBUG`는 환경변수 `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`에서 읽는다. 환경변수가 없으면 교수님 코드의 기존 값(로컬 개발용, `DEBUG=True`)을 그대로 쓴다.
- PythonAnywhere는 https 프록시 뒤에서 동작하므로 `SECURE_PROXY_SSL_HEADER`를 지정해 원래 요청이 https임을 인식하게 했다. 그래야 API 응답의 `image` URL이 `https://`로 만들어지고, 로그인 폼의 CSRF Origin 검사도 통과한다(`CSRF_TRUSTED_ORIGINS = ['https://*.pythonanywhere.com']`도 함께 지정).
- `manage.py check --deploy`의 HSTS / `SECURE_SSL_REDIRECT` / secure 쿠키 경고 4건은 적용하지 않았다. 과제용 서버이고, 에뮬레이터 앱이 로컬 http 서버와 같은 코드를 쓰기 때문이다.

> 알려진 동작(미수정): 교수님 코드의 `post_edit`은 수정할 때마다 `author`를 수정한 사용자로, `published_date`를 수정 시각으로 덮어쓴다. 과제 범위 밖이라 그대로 둔다.

### 클라이언트

- Android 프로젝트는 Groovy `build.gradle`이 아닌 Kotlin DSL(`build.gradle.kts`) + 버전 카탈로그(`gradle/libs.versions.toml`)를 사용한다. 의존성은 이 두 파일에 추가한다.
- 라이브러리 버전: `appcompat 1.7.0`, `material 1.12.0`, `activity 1.9.3`(compileSdk 34 호환), `recyclerview 1.3.2`, `swiperefreshlayout 1.1.0` 추가. 템플릿 버전으로도 빌드 문제는 없었으며 `resolutionStrategy.force`는 필요하지 않았다. (`coreKtx`는 Java 템플릿에 없어 추가하지 않음)
- **서버 주소·토큰 하드코딩 제거**: 슬라이드는 `MainActivity`에 `site_url`과 토큰을 직접 적지만, 서버 주소·토큰은 `ApiConfig`(SharedPreferences)에서 관리한다. Task 5~6에서는 `local.properties` → `BuildConfig` 기본 토큰을 썼고, Task 8에서 **로그인 화면으로 토큰을 발급받는 방식**으로 바꿔 빌드 설정의 토큰도 없앴다.
- 슬라이드 19의 `private class. CloadImage` 오타를 수정했다(`private class CloadImage`).
- 인증 헤더는 `Token <토큰>` 형식이다(서버가 DRF `TokenAuthentication` 사용).
- 이미지는 `BitmapFactory.Options.inJustDecodeBounds`로 크기를 먼저 읽고 화면 너비에 맞춰 `inSampleSize`로 줄여 디코딩한다(큰 사진의 OOM 방지). 이미지 요청에는 토큰을 붙이지 않는다(media는 인증 없이 제공).
- 네트워크 오류·HTTP 오류를 화면에 표시하고, 연결/읽기 타임아웃(10초/15초)을 둔다.
- 템플릿의 EdgeToEdge 코드는 루트 padding을 시스템 바 크기로 덮어써서 레이아웃 여백이 사라지는 문제가 있었다. Task 8 리디자인에서 EdgeToEdge를 쓰지 않고(targetSdk 34에서는 필수 아님) 상태바 색을 테마로 지정하는 방식으로 바꿨다.
- 앱 표시 이름을 `imageviewdemo`에서 `PhotoBlog`로 바꿨다(패키지명은 그대로 `com.example.imageviewdemo`).
- AsyncTask는 deprecated지만 수업 코드와의 일관성을 위해 사용했다.
- **업로드(`PutPost`)**: 슬라이드 19의 주석 부분을 별도 화면 `UploadActivity`로 구현했다.
  - multipart 바디는 `MultipartBody` 클래스로 분리했다. 텍스트를 `DataOutputStream.writeBytes()`로 쓰면 각 문자의 하위 1바이트만 기록되어 한글이 깨지므로 `getBytes(UTF_8)`로 기록한다(JVM 단위 테스트로 검증).
  - `setFixedLengthStreamingMode`로 `Content-Length`를 보낸다(소켓 서버에서 바디를 끝까지 받을 수 있음).
  - Uri → byte[]는 `openInputStream` + `ByteArrayOutputStream`(`readAllBytes`는 API 33+).
  - 긴 변 1600px로 줄이고 JPEG(품질 85)로 재압축한다. 카메라 사진은 픽셀이 눕혀진 채 EXIF에 회전값만 있으므로, `ExifInterface`로 회전을 읽어 픽셀에 반영한다(서버·웹에서도 바로 선 이미지). 파일명은 원본 이름에 확장자만 `.jpg`.
  - 검증: 3000×2000 + EXIF 90° 테스트 사진 → 서버에 1067×1600 JPEG로 저장됨을 확인.
- 업로드 중 판단을 `AsyncTask.getStatus()`로 하면 `onPostExecute` 실행 중에도 `FINISHED`가 아니라서, 실패 후 버튼이 비활성으로 남는 문제가 있어 별도 플래그로 관리한다.
- Photo Picker에서 돌아오면 입력칸 포커스로 키보드가 다시 올라와 업로드 버튼을 가리므로 이미지 선택 후 키보드를 내린다.
- 업로드 후 자동 재동기화 시 "업로드 성공!" 토스트가 가려지지 않게 했다(Task 8에서 "Download" 토스트는 새로고침 표시로 대체).

**Task 8 (편의 기능·리디자인)**

- **어댑터**: 슬라이드의 `List<Bitmap>` 기반 `ImageAdapter`를 게시물 정보(작성자·제목·본문·좋아요·댓글·조회수)를 담는 `Post` 객체 기반 `PostAdapter`로 확장했다.
- **동기화(`CloadImage`)**: 슬라이드처럼 목록 JSON을 받는 AsyncTask 이름을 유지하되, 이미지는 카드마다 `ImageLoader`가 따로 받는다(목록이 먼저 뜨고 사진이 순서대로 채워짐, LruCache로 재사용). 좋아요·댓글 등 새 API 호출은 `ExecutorService` + `Handler`(`Async`)로 구현했다.
- 시작 화면을 `LoginActivity`로 바꿨다(로그인되어 있으면 바로 피드). 401 응답을 받으면 저장된 토큰을 지우고 로그인 화면으로 보낸다.
- 좋아요는 화면을 먼저 바꾸고 서버 응답으로 확정하는 **낙관적 업데이트**. 좋아요·댓글 수만 바뀔 때는 RecyclerView payload로 해당 줄만 다시 그려 이미지가 깜박이지 않게 했다.
- 날짜는 `java.time`(API 26+)이 minSdk 24에서 쓸 수 없어 ISO-8601을 직접 파싱해 상대 시간으로 표시한다(`TimeUtils`, 단위 테스트).
- Material 3 그림자 카드는 primary 색을 섞어(elevation overlay) 핑크빛이 돌아서 `elevationOverlayEnabled=false`로 껐다. 툴바 로고는 Material 3 TextAppearance가 `app:fontFamily`를 우선하므로 `android:fontFamily`와 함께 지정했다.
- 에뮬레이터 확인: 두 계정(sunwoo, friend)으로 로그인·서버 직접 입력·좋아요(버튼/더블탭, 사용자별 상태)·댓글 작성·업로드(작성자 자동 지정)·내 글 삭제(남의 글엔 메뉴 없음)를 확인했다.
