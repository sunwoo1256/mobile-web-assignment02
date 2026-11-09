package com.example.imageviewdemo;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public class MultipartBodyTest {
    private static final byte[] IMAGE = {(byte) 0xFF, (byte) 0xD8, 0x00, 0x01, (byte) 0xFF, (byte) 0xD9};

    @Test
    public void contentTypeContainsBoundary() {
        assertEquals("multipart/form-data; boundary=XYZ", new MultipartBody("XYZ").getContentType());
    }

    @Test
    public void bodyHasTextPartsFilePartAndClosingBoundaryInOrder() throws IOException {
        byte[] body = new MultipartBody("XYZ")
                .addText("title", "hello")
                .addFile("image", "a.jpg", "image/jpeg", IMAGE)
                .build();

        ByteArrayOutputStream expected = new ByteArrayOutputStream();
        expected.write(("--XYZ\r\n"
                + "Content-Disposition: form-data; name=\"title\"\r\n\r\n"
                + "hello\r\n"
                + "--XYZ\r\n"
                + "Content-Disposition: form-data; name=\"image\"; filename=\"a.jpg\"\r\n"
                + "Content-Type: image/jpeg\r\n\r\n").getBytes(StandardCharsets.UTF_8));
        expected.write(IMAGE);
        expected.write("\r\n--XYZ--\r\n".getBytes(StandardCharsets.UTF_8));
        assertArrayEquals(expected.toByteArray(), body);
    }

    @Test
    public void koreanTextIsWrittenAsUtf8() throws IOException {
        byte[] body = new MultipartBody("XYZ").addText("title", "한글 제목").build();
        String decoded = new String(body, StandardCharsets.UTF_8);
        assertTrue(decoded.contains("name=\"title\"\r\n\r\n한글 제목\r\n"));
        // "한" = ED 95 9C (UTF-8 3바이트). writeBytes()였다면 하위 1바이트(0x5C)만 기록된다
        assertTrue(indexOf(body, new byte[]{(byte) 0xED, (byte) 0x95, (byte) 0x9C}) >= 0);
    }

    @Test
    public void koreanFileNameIsWrittenAsUtf8() throws IOException {
        byte[] body = new MultipartBody("XYZ").addFile("image", "피자.jpg", "image/jpeg", IMAGE).build();
        assertTrue(new String(body, StandardCharsets.UTF_8).contains("filename=\"피자.jpg\""));
    }

    @Test
    public void defaultBoundaryIsRandomAndUsedInBody() throws IOException {
        MultipartBody first = new MultipartBody();
        MultipartBody second = new MultipartBody();
        String boundary = first.getContentType().split("boundary=")[1];
        assertTrue(boundary.length() > 20);
        assertTrue(!first.getContentType().equals(second.getContentType()));
        assertTrue(new String(first.addText("a", "b").build(), StandardCharsets.UTF_8)
                .startsWith("--" + boundary + "\r\n"));
    }

    private static int indexOf(byte[] haystack, byte[] needle) {
        outer:
        for (int i = 0; i <= haystack.length - needle.length; i++) {
            for (int j = 0; j < needle.length; j++) {
                if (haystack[i + j] != needle[j]) {
                    continue outer;
                }
            }
            return i;
        }
        return -1;
    }
}
