package com.example.imageviewdemo;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.UUID;

/**
 * multipart/form-data 요청 바디를 만든다.
 * 텍스트 값은 DataOutputStream.writeBytes()가 아닌 UTF-8 바이트로 기록해야 한글이 깨지지 않는다.
 */
public class MultipartBody {
    private static final String CRLF = "\r\n";

    private final String boundary;
    private final ByteArrayOutputStream out = new ByteArrayOutputStream();

    public MultipartBody() {
        this("----PhotoViewer" + UUID.randomUUID().toString().replace("-", ""));
    }

    public MultipartBody(String boundary) {
        this.boundary = boundary;
    }

    public String getContentType() {
        return "multipart/form-data; boundary=" + boundary;
    }

    public MultipartBody addText(String name, String value) throws IOException {
        write("--" + boundary + CRLF);
        write("Content-Disposition: form-data; name=\"" + name + "\"" + CRLF + CRLF);
        write(value + CRLF);
        return this;
    }

    public MultipartBody addFile(String name, String fileName, String contentType, byte[] content)
            throws IOException {
        write("--" + boundary + CRLF);
        write("Content-Disposition: form-data; name=\"" + name + "\"; filename=\"" + fileName + "\"" + CRLF);
        write("Content-Type: " + contentType + CRLF + CRLF);
        out.write(content);
        write(CRLF);
        return this;
    }

    /** 마지막 경계(--boundary--)를 붙여 바디를 완성한다 */
    public byte[] build() throws IOException {
        write("--" + boundary + "--" + CRLF);
        return out.toByteArray();
    }

    private void write(String text) throws IOException {
        out.write(text.getBytes(StandardCharsets.UTF_8));
    }
}
