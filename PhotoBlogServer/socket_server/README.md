# Socket Server — 요청 메시지 검증

안드로이드 앱이 서버로 보내는 HTTP 요청을 **원문 그대로(헤더 + 바디)** 파일로 저장해 확인하기 위한 간단한 소켓 서버.

```
socket_server/
├── request/            # 수신한 요청 원문 (YYYY-MM-DD-HH-MM-SS.bin)
├── response.bin        # 모든 요청에 그대로 돌려줄 HTTP 응답 원문
├── socket_server.py
└── README.md
```

## 동작

1. `0.0.0.0:8000`(기본)에서 연결을 기다린다. 포트는 인자로 변경 가능.
2. 헤더 끝(빈 줄)까지 받은 뒤 `Content-Length`만큼(또는 `Transfer-Encoding: chunked`의 종료 표시까지) 바디를 **끝까지** 받는다. 이미지가 포함된 multipart 업로드 요청도 잘리지 않는다.
3. 받은 바이트 전체를 `request/YYYY-MM-DD-HH-MM-SS.bin`으로 저장한다. 같은 초에 여러 요청이 오면 `_1`, `_2`를 붙인다.
4. `response.bin`을 그대로 응답한다. 기본값은 빈 JSON 배열이라 앱의 동기화가 멈추지 않는다.
   ```
   HTTP/1.1 200 OK
   Content-Type: application/json
   Content-Length: 2
   Connection: close

   []
   ```
5. 콘솔에 요청 라인, 크기, 저장 파일명을 출력한다.

## 사용법

**Django 서버(runserver)를 먼저 끈다.** 같은 포트를 쓰기 때문에 앱 설정을 바꾸지 않고 그대로 요청을 받을 수 있다.

```powershell
cd PhotoBlogServer\socket_server
..\venv\Scripts\python socket_server.py          # 8000 포트
..\venv\Scripts\python socket_server.py 8001     # 다른 포트
```

```
소켓 서버 실행: 0.0.0.0:8000  (에뮬레이터에서는 http://10.0.2.2:8000)
요청 저장 위치: ...\PhotoBlogServer\socket_server\request
종료: Ctrl+C

[127.0.0.1] GET /api_root/Post/ HTTP/1.1  (217 bytes) -> request\2026-10-16-02-42-03.bin
```

- 앱에서 **동기화** → GET 요청, **새로운 이미지 게시** → multipart POST 요청이 저장된다.
- 처음 실행 시 Windows 방화벽 허용 창이 뜨면 "허용"한다(에뮬레이터 접속용).
- 업로드 요청에 대해서도 `200 OK`를 돌려주므로, 앱은 201이 아니라서 "업로드 실패"로 표시한다. 요청 원문을 받는 것이 목적이므로 정상이다.
- 확인이 끝나면 Ctrl+C로 종료하고 Django 서버를 다시 실행한다.

## 저장 파일 보기

`request/*.bin`을 VSCode로 연다. 이미지가 들어간 업로드 요청은 VSCode가 "바이너리 파일" 경고를 띄우는데, **"그래도 열기(Open Anyway)"** → 텍스트 편집기를 고르면 헤더와 multipart 경계, 텍스트 파트를 볼 수 있다(이미지 바이트 부분만 깨져 보인다).

`request/`의 `.bin`은 보고서 증빙용이므로 커밋한다. `.gitattributes`에서 `*.bin`을 binary로 지정해 CRLF가 변환되지 않게 했다.
