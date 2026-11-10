# PhotoBlog YOLO — 침입자 감시 시스템

모바일/웹서비스 프로젝트 공통평가 02 — Chapter 08. Django와 YOLO를 이용한 침입자 감시 시스템

- **Edge (YOLOv5)**: 웹캠 영상에서 객체를 검출하고, 새 객체가 나타나면 검출 이미지를 블로그 서버에 자동 업로드
- **Server (Django + DRF)**: 토큰 인증 REST API로 검출 이미지를 게시물로 저장
- **Client (Android, PhotoViewer)**: 서버의 검출 이미지 목록 조회
- **배포**: https://sunwoo.pythonanywhere.com
- **레포**: https://github.com/sunwoo1256/mobile-web-assignment02

## 시스템 구성

```
[웹캠]
   │ 프레임
   ▼
[YOLOv5 detect.py] ─ changedetection.py ─┬─ tracking.py      (편의 기능 1: 추적·침입 구역)
   │                                     └─ upload_queue.py  (편의 기능 2: 오프라인 큐)
   │ POST /api_root/Post/  (Authorization: Token, 이미지 + 제목/본문)
   ▼
[Django 블로그 서버]  로컬 http://127.0.0.1:8000  /  클라우드 https://sunwoo.pythonanywhere.com
   │ GET /api_root/Post/  (JSON + 이미지 URL)
   ▼
[Android 앱 PhotoViewer]  검출 이미지 목록 조회
```

1. `detect.py`가 프레임마다 객체를 검출한다.
2. `changedetection.py`가 이전 프레임에 없던 객체(기본 모드) 또는 침입 구역 진입·배회(구역 모드)를 감지한다.
3. 감지되면 검출 이미지(320×240)와 제목·본문·시각을 업로드 큐에 넣고, 백그라운드 스레드가 서버로 전송한다.
4. 앱과 웹 블로그에서 검출 이미지 목록을 확인한다.

## 폴더 구조

```
ROOT/
├── PhotoBlogServer/        # Django 서버 (manage.py 위치)
│   ├── mysite/             #   settings, urls, wsgi
│   ├── blog/               #   Post·Comment·Like 모델, REST API, 웹 템플릿, 테스트
│   ├── api_test_engine/    #   API 검증 엔진 (공통평가 01)
│   └── requirements.txt
├── PhotoViewer/            # Android 앱 (package: com.example.imageviewdemo)
├── YOLOv5/                 # Edge 검출기 (ultralytics/yolov5 + 아래 파일 추가)
│   ├── detect.py           #   검출 루프 — `# added` 주석 줄만 수정
│   ├── changedetection.py  #   변화 감지 + 서버 업로드
│   ├── tracking.py         #   편의 기능 1: 객체 추적 + 침입 구역
│   ├── upload_queue.py     #   편의 기능 2: 오프라인 업로드 큐
│   └── tests/test_edge_*.py#   편의 기능 테스트 102개
├── .gitignore
├── README.md
└── 모바일웹서비스 프로젝트_공통평가 02_수행 결과 보고서.docx
```

## 실행 방법 (로컬)

Python **3.12 이상**이 필요하다 (Django 6.1). 아래 명령은 Windows PowerShell 기준이며, `activate`가 막히면 먼저 `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`를 실행한다.

### 1. 서버

```powershell
cd PhotoBlogServer
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser          # 관리자 계정
python manage.py createsuperuser          # YOLO 업로드용 계정 (예: yolo)
python manage.py runserver 0.0.0.0:8000
```

| 주소 | 설명 |
|---|---|
| http://127.0.0.1:8000/ | 웹 블로그 목록 (제목·본문·검출 이미지) |
| http://127.0.0.1:8000/api_root/Post/ | 게시물 API (우상단 **Log in** 후 확인) |
| http://127.0.0.1:8000/api-token-auth/ | 아이디/비밀번호 → 토큰 발급 (POST) |
| http://127.0.0.1:8000/admin/ | 관리자 |

실기기에서 PC 서버에 접속하려면 PC의 IP를 허용한다: `$env:DJANGO_ALLOWED_HOSTS = "192.168.0.10"` (쉼표로 여러 개)

### 2. YOLOv5 검출기

```powershell
cd YOLOv5
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

$env:PHOTOBLOG_USERNAME = "yolo"
$env:PHOTOBLOG_PASSWORD = "<비밀번호>"
python detect.py --source 0               # 0 = 기본 웹캠
```

시작 로그에 `[ChangeDetection] 토큰 발급 성공`이 나오고, 새 객체가 나타날 때마다 `큐에 추가` → `[UploadQueue] 전송 성공`이 출력된다. 가중치(`yolov5s.pt`)는 첫 실행 때 자동으로 내려받는다.

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `PHOTOBLOG_HOST` | `http://127.0.0.1:8000` | 업로드할 서버 주소 |
| `PHOTOBLOG_USERNAME` / `PHOTOBLOG_PASSWORD` | 없음 | 업로드 계정 (없으면 업로드하지 않음) |

비밀번호는 코드에 넣지 않고 환경변수로만 전달한다. Windows가 미리 정의한 `USERNAME`과 겹치지 않도록 `PHOTOBLOG_` 접두어를 쓴다. 편의 기능용 환경변수는 [편의 기능](#편의-기능) 참고.

### 3. Android 앱

1. `PhotoViewer/`를 Android Studio로 열고 실행한다 (compileSdk 34, minSdk 24).
2. 로그인 화면에서 서버를 고르고 서버 계정으로 로그인한다.
   - 에뮬레이터 → 로컬: **로컬 서버** (`http://10.0.2.2:8000`)
   - 실기기 → 로컬: **직접 입력**에 `http://<PC IP>:8000` (서버는 `0.0.0.0:8000`, `DJANGO_ALLOWED_HOSTS` 설정)
   - 클라우드: **클라우드 서버** (`https://sunwoo.pythonanywhere.com`)
3. 피드에 YOLO가 올린 검출 이미지가 최신순으로 표시된다.

서버 주소 상수는 [`ApiConfig.java`](PhotoViewer/app/src/main/java/com/example/imageviewdemo/ApiConfig.java)의 `LOCAL_URL`, `CLOUD_URL` 한 곳에 있다. 로컬 HTTP는 [`network_security_config.xml`](PhotoViewer/app/src/main/res/xml/network_security_config.xml)에서 허용한다.

## 검출기 코드 수정 (강의자료 p.8~11)

[`changedetection.py`](YOLOv5/changedetection.py)의 `ChangeDetection` 클래스가 강의자료 로직을 구현한다.

- `__init__`: 클래스 수만큼 `result_prev = [0, ...]`, `/api-token-auth/`로 토큰 발급
- `add()`: 이전 프레임 0 → 현재 1로 바뀐 클래스가 있으면 `title = 클래스명`, `text += 클래스명 + ", "` 후 전송
- `send()`: `runs/detect/expN/detected/YYYY/M/D/H-M-S-us.jpg`로 320×240 저장 후 `POST /api_root/Post/`

강의자료 대비 바꾼 점: 접속 정보를 환경변수로 받음, `Authorization: Token` 헤더(DRF authtoken), 경로를 `pathlib`·`str()`로 처리, 시각은 `isoformat()` 문자열, 파일은 `with open`으로 닫음, 요청 실패가 검출 루프를 멈추지 않도록 예외 처리, 최신 YOLOv5의 `names`(dict)를 리스트로 변환.

[`detect.py`](YOLOv5/detect.py)는 줄 번호가 아니라 위치를 기준으로 삽입했다 (강의자료의 줄 번호는 2022년 버전 기준).

| 위치 | 추가한 줄 |
|---|---|
| import 영역 | `from changedetection import ChangeDetection  # added` |
| 모델 로드 후 `names` 정의 직후 | `cd = ChangeDetection(names)  # added` |
| `for i, det in enumerate(pred):` 안, `if len(det):` 앞 | `detected = [0 for _ in range(len(names))]  # added` |
| `for *xyxy, conf, cls in reversed(det):` 안 | `detected[int(cls)] = 1  # added` |
| `if view_img:` 바로 앞 | `cd.add(names, detected, save_dir, im0)  # added` |

편의 기능을 위해 `# added (편의기능)` 3줄(`boxes = []`, `boxes.append(...)`, `cd.track(boxes, im0)`)을 더 추가했다. 그 밖의 원본 코드는 수정하지 않았다.

## 편의 기능

두 기능 모두 YOLO(Edge) 쪽에서 동작하며 서버·앱은 수정하지 않는다.

### 기능 1. 침입 구역 기반 객체 추적 및 배회 감지 — [`tracking.py`](YOLOv5/tracking.py)

**정의**: 영상 안에 다각형 침입 구역을 설정하고, 검출된 객체마다 고유 ID를 부여해 추적한다. 객체가 구역에 **진입**하거나 구역 안에 일정 시간 이상 **머무를(배회)** 때만 게시물을 등록한다.

**설명**: 기본 검출기는 "이전 프레임에 없던 클래스"만 보므로, 감시가 필요 없는 곳을 지나가는 사람도 기록되고, 검출이 한 프레임만 끊겨도 같은 사람이 반복 등록되며, 한두 프레임짜리 오탐도 업로드되고, 같은 클래스의 여러 객체를 구분하지 못한다. 이 기능은 객체 단위 추적과 위치 기반 판단으로 "누가, 언제, 감시 구역에 들어왔고, 얼마나 머물렀는지"를 기록한다. `ZONE`을 지정하지 않으면 기존 방식 그대로 동작한다.

**동작 방식**:

1. **객체 추적 (직접 구현)**: 이전 트랙과 현재 박스를 같은 클래스끼리 IoU가 큰 쌍부터 짝짓는다. 저FPS(CPU)에서 박스가 크게 움직여 IoU가 0이 되는 경우를 위해, 남은 박스는 중심점 거리(트랙 박스 대각선 이내)로 한 번 더 짝짓는다. 새 객체는 연속 `TRACK_MIN_HITS`프레임 검출돼야 확정되고, 확정 전에 놓치면 오탐으로 버린다. 확정된 객체는 `TRACK_MAX_AGE`프레임까지 가려져도 같은 ID를 유지한다.
2. **구역 판정**: 구역은 화면 크기에 대한 비율 좌표라 해상도와 무관하다. 박스 하단 중앙(발 위치)이 다각형 안에 있는지를 레이 캐스팅으로 판정한다(오목 다각형 지원).
3. **이벤트**: 구역 밖 → 안이면 `[진입] person #3`, 구역 안에 `LOITER_SEC`초 이상이면 `[배회] person #3 (7s)` 게시물을 등록한다. 종류별로 객체당 한 번만 발생하고, 구역을 벗어나면 체류 시간이 초기화된다. 같은 프레임의 여러 이벤트는 게시물 하나로 묶는다.
4. **화면 표시**: 구역(반투명 빨강), 객체 `#ID`(구역 밖 초록 / 안 빨강 + 체류 시간), 상단 상태줄(추적 수·업로드 대기 수). 업로드 이미지에도 같은 표시가 들어간다.

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `ZONE` | 없음 (기본 모드) | 침입 구역, 0~1 비율 좌표 `x,y;x,y;...` (예: 오른쪽 절반 `0.5,0;1,0;1,1;0.5,1`) |
| `TRACK_CLASSES` | `person` | 추적 대상 클래스 (쉼표 구분) |
| `LOITER_SEC` | `5` | 배회 판단 체류 시간(초) |
| `TRACK_MIN_HITS` | `3` | 객체 확정에 필요한 연속 검출 프레임 수 |
| `TRACK_MAX_AGE` | `15` | 객체를 유지할 최대 미검출 프레임 수 |

**시연 방법**:

```powershell
$env:ZONE = "0.5,0;1,0;1,1;0.5,1"
$env:LOITER_SEC = "5"
python detect.py --source 0
```

1. 화면 왼쪽(구역 밖)에 있으면 초록색 `#1`만 표시되고 게시물은 올라가지 않는다.
2. 오른쪽(빨간 구역)으로 이동하면 `#1 0s`(빨강)로 바뀌고 `[진입] person #1`이 전송된다.
3. 5초 머물면 `[배회] person #1 (5s)`가 전송되고, 이후 계속 있어도 추가로 올라가지 않는다.
4. 블로그 목록에서 진입·배회 게시물과 구역이 표시된 이미지를 확인한다.

### 기능 2. 오프라인 업로드 큐 및 비동기 전송 — [`upload_queue.py`](YOLOv5/upload_queue.py)

**정의**: 검출 결과(이미지·제목·본문·검출 시각)를 디스크 큐에 먼저 저장하고, 백그라운드 스레드가 서버로 전송한다. 서버·네트워크 장애 중에는 보관했다가 복구되면 자동으로 재전송한다.

**설명**: 기본 검출기는 검출 루프 안에서 HTTP 요청을 보내므로, 서버가 느리면 영상 처리가 멈추고(감시 공백), 서버가 꺼져 있으면 그동안의 검출 결과가 사라지며, 토큰이 무효가 되면 재시작할 때까지 업로드가 실패한다. 침입 감시에서는 장애 중의 기록이 가장 중요할 수 있으므로, 전송을 검출과 분리하고 디스크에 남겨 감시가 멈추지 않고 기록도 유실되지 않게 한다.

**동작 방식**:

1. **큐 저장**: 이벤트가 생기면 이미지(.jpg)와 메타데이터(.json)를 `upload_queue/`에 저장하고 바로 다음 프레임으로 넘어간다. 메타데이터는 임시 파일에 쓴 뒤 이름을 바꾸는 원자적 쓰기로 저장해, 저장 도중 종료돼도 반쯤 쓰인 항목이 전송되지 않는다. 파일 이름이 검출 시각이라 이름순이 곧 시간순이다.
2. **전송**: 백그라운드 스레드가 가장 오래된 항목부터 보낸다.
   - 201: 큐에서 삭제
   - 연결 실패·시간 초과·5xx·429: 남겨 두고 1 → 2 → 4 → … → 최대 60초 간격으로 재시도 (서버의 `Retry-After` 우선)
   - 401: 토큰을 다시 발급받아 재시도
   - 그 밖의 4xx: `failed/`로 옮기고 사유(.err)를 남김 — 다음 항목을 막지 않음
3. **시각 보존**: `created_date`에 전송 시각이 아니라 검출 시각을 넣어, 늦게 올라가도 실제 순서대로 기록된다.
4. **종료·재시작**: 종료할 때 최대 5초 동안 남은 항목을 마저 보내고, 못 보낸 항목은 디스크에 보관했다가 다음 실행 때 이어서 보낸다.

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `UPLOAD_QUEUE_DIR` | `upload_queue` | 큐 폴더. 로컬·클라우드 시연을 번갈아 할 때는 서버별로 다르게 지정한다 (큐 항목에는 대상 서버가 저장되지 않음) |

**시연 방법**:

1. 서버를 끈 상태에서 YOLO를 실행하고 구역에 들어간다 → `큐에 추가 (N건 대기)`, `서버 연결 불가`, `1초 후 재시도` → `2초` → `4초`… 가 출력되고 상단 `queue:` 숫자가 늘어난다. 영상은 멈추지 않는다.
2. YOLO를 켜 둔 채 서버를 다시 켠다 → 다음 재시도 때 `전송 성공 ... (0건 대기)`가 연달아 출력된다.
3. 블로그를 새로고침하면 서버가 꺼져 있던 동안의 게시물이 검출 시각 순서대로 올라와 있다.
4. (재시작) 서버가 꺼진 상태에서 YOLO를 종료하면 `미전송 N건은 ... 다음 실행 때 이어서 전송`, 서버를 켜고 다시 실행하면 `이전 실행에서 남은 N건을 이어서 전송합니다`가 출력된다.

클라우드 서버로 시연할 때는 서버를 끄는 대신 PC의 Wi-Fi를 10~20초 끄면 된다.

## 테스트

| 대상 | 개수 | 실행 |
|---|---|---|
| 편의 기능 1 — 추적·구역 (`test_edge_tracking.py`) | 44 | `YOLOv5`에서 `python -m unittest discover -s tests -p "test_edge_*.py" -v` |
| 편의 기능 2 — 업로드 큐 (`test_edge_upload_queue.py`) | 34 | ↑ 같은 명령 |
| `ChangeDetection` 통합 (`test_edge_changedetection.py`) | 24 | ↑ 같은 명령 |
| 서버 `blog` 앱 | 63 | `PhotoBlogServer`에서 `python manage.py test blog` |
| API 검증 엔진 (공통평가 01) | 46 | `PhotoBlogServer/api_test_engine`에서 `..\venv\Scripts\python test_photoblog_api.py` |

편의 기능 테스트는 표준 `unittest`만 쓰고, 가짜 시계·가짜 HTTP 세션을 주입해 네트워크와 실제 시간 없이 결정적으로 실행된다. 커버리지: `tracking.py` 100%, `upload_queue.py` 100%, 전체 99%.

```powershell
cd YOLOv5
pip install coverage
python -m coverage run --include="tracking.py,upload_queue.py,changedetection.py" -m unittest discover -s tests -p "test_edge_*.py"
python -m coverage report -m
```

주요 검증 내용:

- **추적·구역**: IoU, 오목 다각형 판정, 구역 좌표 오류, ID 유지·재사용 금지, 깜빡임 오탐 제거, 가려짐 후 ID 유지, 빠른 이동, 진입·배회 1회 발생, 구역 이탈 시 체류 시간 초기화
- **업로드 큐**: 원자적 저장, 오래된 순서 전송, 응답 코드별 처리(201·401·429·5xx·4xx), 토큰 재발급, 손상 항목 격리, 재시작 후 복원, 느린 서버에도 검출 루프가 막히지 않음, 오프라인→복구 시 전체 전송, 종료 처리
- **통합**: 기본 모드 변화 감지 유지, 토큰 발급 실패 처리, 구역 모드 진입→배회 흐름, 대상 외 클래스 무시, 동시 이벤트 병합

## PythonAnywhere 배포

`<id>` = PythonAnywhere 사용자명 (`sunwoo`). Django 6.1은 Python 3.12 이상이 필요하다.

**1. Bash 콘솔 — 코드·가상환경**

```bash
git clone https://github.com/sunwoo1256/mobile-web-assignment02.git ~/PhotoBlogYOLO
mkvirtualenv --python=python3.13 photoblogyolo     # 없으면 python3.12
pip install -r ~/PhotoBlogYOLO/PhotoBlogServer/requirements.txt
```

**2. DB·계정·정적 파일**

```bash
cd ~/PhotoBlogYOLO/PhotoBlogServer
python manage.py migrate
python manage.py createsuperuser                   # 관리자, YOLO 업로드용 계정
python manage.py collectstatic --noinput
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

**3. Web 탭** — Manual configuration (이미 웹앱이 있으면 경로만 변경)

- Source code / Working directory: `/home/<id>/PhotoBlogYOLO/PhotoBlogServer`
- Virtualenv: `/home/<id>/.virtualenvs/photoblogyolo`

**4. WSGI 파일** — 전체를 아래로 교체

```python
import os
import sys

path = '/home/<id>/PhotoBlogYOLO/PhotoBlogServer'
if path not in sys.path:
    sys.path.insert(0, path)

os.environ['DJANGO_SETTINGS_MODULE'] = 'mysite.settings'
os.environ['DJANGO_DEBUG'] = 'False'
os.environ['DJANGO_SECRET_KEY'] = '<2단계에서 출력된 문자열>'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

**5. Static files 매핑** — `/media/`가 빠지면 이미지가 표시되지 않는다 (`DEBUG=False`에서는 Django가 media를 제공하지 않음)

| URL | Directory |
|---|---|
| `/static/` | `/home/<id>/PhotoBlogYOLO/PhotoBlogServer/staticfiles` |
| `/media/` | `/home/<id>/PhotoBlogYOLO/PhotoBlogServer/media` |

**6. Reload** 후 `https://<id>.pythonanywhere.com/`, `/api_root/Post/` 확인. `ALLOWED_HOSTS`에는 `.pythonanywhere.com`이 이미 들어 있다.

**코드 수정 후 재배포**

```bash
cd ~/PhotoBlogYOLO && git pull
workon photoblogyolo
cd PhotoBlogServer && python manage.py migrate && python manage.py collectstatic --noinput
```

→ Web 탭 **Reload**.

### YOLO → 클라우드 서버로 업로드

로컬 PC(웹캠)에서 실행하고 전송 대상만 바꾼다. 로컬 서버는 켤 필요 없다.

```powershell
cd YOLOv5
venv\Scripts\activate
$env:PHOTOBLOG_HOST = "https://sunwoo.pythonanywhere.com"
$env:PHOTOBLOG_USERNAME = "yolo"
$env:PHOTOBLOG_PASSWORD = "<클라우드 계정 비밀번호>"
$env:UPLOAD_QUEUE_DIR = "upload_queue_cloud"      # 로컬용 큐와 분리
python detect.py --source 0
```

시작 로그 `토큰 발급 성공 (https://sunwoo.pythonanywhere.com, yolo)`로 대상 서버를 확인할 수 있다.

### 문제 해결

| 증상 | 확인할 것 |
|---|---|
| `토큰 발급 실패: 서버 연결 불가` | 서버 실행 여부, `PHOTOBLOG_HOST` |
| `토큰 발급 실패: 400 (계정/비밀번호 확인)` | 해당 서버에 계정이 있는지 (로컬·클라우드 DB는 별개) |
| `DisallowedHost` / 400 | `ALLOWED_HOSTS` — 실기기는 `DJANGO_ALLOWED_HOSTS`에 PC IP 추가 |
| 웹은 되는데 이미지가 안 뜸 | PythonAnywhere Static files의 `/media/` 매핑 |
| 500 Internal Server Error | Web 탭의 Error log |
| 움직일 때 트랙 ID가 자주 바뀜 | 천천히 이동 (CPU 처리 속도가 1초에 5~7장 정도) |
| 오탐이 잦음 | `TRACK_MIN_HITS`를 5 정도로 올림 |

## 서버 API 요약

모든 API는 인증이 필요하다 (`Authorization: Token <TOKEN>` 또는 브라우저 세션 로그인). 인증 없이 요청하면 `401`.

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api-token-auth/` | `username`, `password` → `{"token", "user_id", "username"}` |
| GET | `/api_root/Post/` | 게시물 목록 (최신순, `image`는 절대 URL) |
| POST | `/api_root/Post/` | 게시물 작성 (multipart: `title`, `text`, `image`, 선택 `created_date`·`published_date`). `author`는 로그인한 사용자로 자동 지정 |
| GET | `/api_root/Post/<id>/` | 상세 (조회수 +1) |
| PUT / PATCH / DELETE | `/api_root/Post/<id>/` | 수정·삭제 — 작성자만 |
| POST / DELETE | `/api_root/Post/<id>/like/` | 좋아요 / 취소 |
| GET / POST | `/api_root/Post/<id>/comments/` | 댓글 목록 / 작성 |
| DELETE | `/api_root/Comment/<id>/` | 댓글 삭제 — 작성자만 |

앱의 로그인·좋아요·댓글·조회수·삭제 기능은 공통평가 01에서 구현한 것을 그대로 사용한다.
