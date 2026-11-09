"""HTTP 요청 원문 저장용 소켓 서버

Django 서버 대신 이 서버를 같은 포트(기본 8000)에서 실행하면, 안드로이드 앱이 보낸
HTTP 요청을 헤더 + 바디(multipart 포함) 그대로 request/YYYY-MM-DD-HH-MM-SS.bin 으로 저장하고
response.bin 내용을 그대로 응답한다.

실행: python socket_server.py [port]      (종료: Ctrl+C)
"""
import datetime
import os
import socket
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REQUEST_DIR = os.path.join(BASE_DIR, 'request')
RESPONSE_FILE = os.path.join(BASE_DIR, 'response.bin')
HOST = '0.0.0.0'
DEFAULT_PORT = 8000
RECV_TIMEOUT = 10  # 클라이언트가 바디를 다 보내지 않을 때 기다리는 최대 시간(초)


def parse_headers(head):
    """헤더 부분(bytes)에서 {소문자 헤더명: 값} 딕셔너리를 만든다"""
    headers = {}
    for line in head.split(b'\r\n')[1:]:
        name, _, value = line.partition(b':')
        headers[name.strip().lower().decode('latin-1')] = value.strip().decode('latin-1')
    return headers


def receive_request(conn):
    """헤더 끝(빈 줄)까지 받은 뒤 Content-Length(또는 chunked 종료)만큼 바디를 끝까지 받는다"""
    data = b''
    while b'\r\n\r\n' not in data:
        chunk = conn.recv(65536)
        if not chunk:
            return data
        data += chunk

    head, _, body = data.partition(b'\r\n\r\n')
    headers = parse_headers(head)
    if 'content-length' in headers:
        remaining = int(headers['content-length']) - len(body)
        while remaining > 0:
            chunk = conn.recv(min(65536, remaining))
            if not chunk:
                break
            data += chunk
            remaining -= len(chunk)
    elif headers.get('transfer-encoding', '').lower() == 'chunked':
        while not data.endswith(b'0\r\n\r\n'):
            chunk = conn.recv(65536)
            if not chunk:
                break
            data += chunk
    return data


def save_request(data):
    """request/YYYY-MM-DD-HH-MM-SS.bin 으로 저장 (같은 초에 여러 요청이면 _1, _2 ... 를 붙임)"""
    os.makedirs(REQUEST_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
    path = os.path.join(REQUEST_DIR, f'{stamp}.bin')
    count = 1
    while os.path.exists(path):
        path = os.path.join(REQUEST_DIR, f'{stamp}_{count}.bin')
        count += 1
    with open(path, 'wb') as f:
        f.write(data)
    return path


def serve(port):
    with open(RESPONSE_FILE, 'rb') as f:
        response = f.read()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, port))
        server.listen()
        # Windows에서는 accept() 대기 중 Ctrl+C가 먹지 않으므로 1초마다 깨어나게 한다
        server.settimeout(1.0)
        print(f'소켓 서버 실행: {HOST}:{port}  (에뮬레이터에서는 http://10.0.2.2:{port})')
        print(f'요청 저장 위치: {REQUEST_DIR}')
        print('종료: Ctrl+C\n')

        while True:
            try:
                conn, addr = server.accept()
            except socket.timeout:
                continue
            with conn:
                conn.settimeout(RECV_TIMEOUT)
                try:
                    data = receive_request(conn)
                except socket.timeout:
                    data = b''
                    print(f'[{addr[0]}] 수신 시간 초과')
                if not data:
                    continue
                path = save_request(data)
                conn.sendall(response)
                request_line = data.split(b'\r\n', 1)[0].decode('latin-1')
                print(f'[{addr[0]}] {request_line}  ({len(data)} bytes) -> {os.path.relpath(path, BASE_DIR)}')


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    port = int(argv[0]) if argv else DEFAULT_PORT
    try:
        serve(port)
    except KeyboardInterrupt:
        print('\n종료')
    except OSError as e:
        print(f'{port} 포트를 열 수 없습니다: {e}\nDjango 서버(runserver)가 같은 포트에서 실행 중이면 먼저 종료하세요.')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
