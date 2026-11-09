package com.example.imageviewdemo;

import android.content.ContentResolver;
import android.database.Cursor;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Matrix;
import android.media.ExifInterface;
import android.net.Uri;
import android.os.AsyncTask;
import android.os.Bundle;
import android.provider.OpenableColumns;
import android.text.Editable;
import android.text.TextWatcher;
import android.util.Log;
import android.view.View;
import android.view.inputmethod.InputMethodManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.TextView;
import android.widget.Toast;

import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.PickVisualMediaRequest;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.appcompat.app.AppCompatActivity;

import com.google.android.material.appbar.MaterialToolbar;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

/** Post 필드(title, text, image)를 입력받아 서버에 업로드하는 화면 */
public class UploadActivity extends AppCompatActivity {
    private static final String TAG = "PhotoViewer";
    private static final String STATE_IMAGE_URI = "image_uri";
    private static final int MAX_IMAGE_SIDE = 1600;
    private static final int JPEG_QUALITY = 85;

    private EditText editTitle;
    private EditText editText;
    private View imageCard;
    private View imagePlaceholder;
    private View chipChangeImage;
    private Button btnUpload;
    private ImageView imagePreview;
    private View progressBar;
    private TextView textStatus;

    private Uri selectedImageUri;
    // AsyncTask 상태는 onPostExecute 중에도 FINISHED가 아니므로 별도 플래그로 관리한다
    private boolean uploading;

    private final ActivityResultLauncher<PickVisualMediaRequest> pickImage =
            registerForActivityResult(new ActivityResultContracts.PickVisualMedia(), uri -> {
                if (uri != null) {
                    setSelectedImage(uri);
                }
            });

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_upload);

        editTitle = findViewById(R.id.editTitle);
        editText = findViewById(R.id.editText);
        imageCard = findViewById(R.id.imageCard);
        imagePlaceholder = findViewById(R.id.imagePlaceholder);
        chipChangeImage = findViewById(R.id.chipChangeImage);
        btnUpload = findViewById(R.id.btnUpload);
        imagePreview = findViewById(R.id.imagePreview);
        progressBar = findViewById(R.id.progressBar);
        textStatus = findViewById(R.id.textStatus);

        ((MaterialToolbar) findViewById(R.id.toolbar)).setNavigationOnClickListener(v -> finish());
        // 사진 카드(또는 "사진 변경")를 누르면 Photo Picker
        View.OnClickListener pick = v -> pickImage.launch(new PickVisualMediaRequest.Builder()
                .setMediaType(ActivityResultContracts.PickVisualMedia.ImageOnly.INSTANCE)
                .build());
        imageCard.setOnClickListener(pick);
        chipChangeImage.setOnClickListener(pick);
        btnUpload.setOnClickListener(this::onClickUpload);
        TextWatcher inputWatcher = new TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence s, int start, int count, int after) {
            }

            @Override
            public void onTextChanged(CharSequence s, int start, int before, int count) {
            }

            @Override
            public void afterTextChanged(Editable s) {
                onInputChanged();
            }
        };
        editTitle.addTextChangedListener(inputWatcher);
        editText.addTextChangedListener(inputWatcher);

        if (savedInstanceState != null && savedInstanceState.getString(STATE_IMAGE_URI) != null) {
            setSelectedImage(Uri.parse(savedInstanceState.getString(STATE_IMAGE_URI)));
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        if (selectedImageUri != null) {
            outState.putString(STATE_IMAGE_URI, selectedImageUri.toString());
        }
    }

    private void setSelectedImage(Uri uri) {
        selectedImageUri = uri;
        imagePreview.setImageURI(uri);
        imagePreview.setVisibility(View.VISIBLE);
        imagePlaceholder.setVisibility(View.GONE);
        chipChangeImage.setVisibility(View.VISIBLE);
        // Photo Picker에서 돌아오면 입력칸 포커스로 키보드가 다시 올라와 업로드 버튼을 가리므로 내린다
        View focused = getCurrentFocus();
        if (focused != null) {
            focused.clearFocus();
            InputMethodManager imm = (InputMethodManager) getSystemService(INPUT_METHOD_SERVICE);
            imm.hideSoftInputFromWindow(focused.getWindowToken(), 0);
        }
        onInputChanged();
    }

    /** Post의 필수 필드(title, text, image)가 모두 채워졌는지 — 서버 모델에서 셋 다 빈 값 불가 */
    private boolean isInputComplete() {
        return !editTitle.getText().toString().trim().isEmpty()
                && !editText.getText().toString().trim().isEmpty()
                && selectedImageUri != null;
    }

    private void onInputChanged() {
        updateUploadButton();
        textStatus.setText(isInputComplete() ? R.string.status_ready : R.string.status_need_input);
    }

    private void updateUploadButton() {
        btnUpload.setEnabled(isInputComplete() && !uploading);
    }

    private void onClickUpload(View v) {
        if (!isInputComplete()) {
            Toast.makeText(this, R.string.status_need_input, Toast.LENGTH_SHORT).show();
            return;
        }
        if (uploading) {
            return; // 업로드 중 중복 클릭 방지
        }
        new PutPost(getContentResolver(), ApiConfig.getToken(this),
                editTitle.getText().toString().trim(), editText.getText().toString(), selectedImageUri)
                .execute(ApiConfig.getPostsUrl(this));
    }

    private void setUploading(boolean uploading) {
        this.uploading = uploading;
        progressBar.setVisibility(uploading ? View.VISIBLE : View.INVISIBLE);
        imageCard.setEnabled(!uploading);
        chipChangeImage.setEnabled(!uploading);
        editTitle.setEnabled(!uploading);
        editText.setEnabled(!uploading);
        updateUploadButton();
        if (uploading) {
            textStatus.setText(R.string.status_uploading);
        }
    }

    /** multipart/form-data로 게시물을 POST 한다 (슬라이드 19의 PutPost) */
    private class PutPost extends AsyncTask<String, Void, Boolean> {
        private final ContentResolver resolver;
        private final String token;
        private final String title;
        private final String text;
        private final Uri imageUri;
        private String resultMessage;

        PutPost(ContentResolver resolver, String token, String title, String text, Uri imageUri) {
            this.resolver = resolver;
            this.token = token;
            this.title = title;
            this.text = text;
            this.imageUri = imageUri;
        }

        @Override
        protected void onPreExecute() {
            setUploading(true);
        }

        @Override
        protected Boolean doInBackground(String... urls) {
            HttpURLConnection conn = null;
            try {
                byte[] imageBytes = loadResizedJpeg(resolver, imageUri);
                String fileName = jpegFileName(resolver, imageUri);

                MultipartBody multipart = new MultipartBody()
                        .addText("title", title)
                        .addText("text", text)
                        .addText("published_date", nowIso8601())
                        .addFile("image", fileName, "image/jpeg", imageBytes);
                byte[] bodyBytes = multipart.build();

                conn = (HttpURLConnection) new URL(urls[0]).openConnection();
                conn.setRequestMethod("POST");
                conn.setDoOutput(true);
                conn.setUseCaches(false);
                conn.setConnectTimeout(10000);
                conn.setReadTimeout(30000);
                conn.setRequestProperty("Authorization", "Token " + token);
                conn.setRequestProperty("Content-Type", multipart.getContentType());
                conn.setFixedLengthStreamingMode(bodyBytes.length);
                try (java.io.OutputStream os = conn.getOutputStream()) {
                    os.write(bodyBytes);
                }

                int responseCode = conn.getResponseCode();
                if (responseCode == HttpURLConnection.HTTP_CREATED) {
                    resultMessage = "업로드 성공!";
                    return true;
                }
                InputStream error = conn.getErrorStream();
                String errorBody = error == null ? ""
                        : new String(ImageUtils.readAll(error), StandardCharsets.UTF_8);
                resultMessage = "업로드 실패 (HTTP " + responseCode + ")\n" + errorBody;
                Log.w(TAG, resultMessage);
                return false;
            } catch (Exception e) {
                Log.e(TAG, "업로드 실패", e);
                resultMessage = "업로드 실패: " + e.getMessage();
                return false;
            } finally {
                if (conn != null) {
                    conn.disconnect();
                }
            }
        }

        @Override
        protected void onPostExecute(Boolean success) {
            setUploading(false);
            Toast.makeText(UploadActivity.this, resultMessage, Toast.LENGTH_LONG).show();
            if (success) {
                setResult(RESULT_OK); // MainActivity가 목록을 다시 동기화
                finish();
            } else {
                textStatus.setText(resultMessage); // 서버 오류 본문을 그대로 보여준다
            }
        }
    }

    private static String nowIso8601() {
        SimpleDateFormat format = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US);
        format.setTimeZone(TimeZone.getTimeZone("UTC"));
        return format.format(new Date());
    }

    // ------------------------------------------------------------ 이미지 처리

    /** Uri의 원본 파일명에서 확장자를 .jpg로 바꾼다 (JPEG로 재압축하므로) */
    private static String jpegFileName(ContentResolver resolver, Uri uri) {
        String name = null;
        try (Cursor cursor = resolver.query(uri, new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null)) {
            if (cursor != null && cursor.moveToFirst()) {
                name = cursor.getString(0);
            }
        } catch (Exception e) {
            Log.w(TAG, "파일명 조회 실패", e);
        }
        if (name == null || name.isEmpty()) {
            name = "photo_" + System.currentTimeMillis();
        }
        int dot = name.lastIndexOf('.');
        String base = dot > 0 ? name.substring(0, dot) : name;
        return base.replace("\"", "") + ".jpg";
    }

    /** 긴 변을 MAX_IMAGE_SIDE 이하로 줄이고 EXIF 회전을 반영한 뒤 JPEG로 재압축한다 */
    private static byte[] loadResizedJpeg(ContentResolver resolver, Uri uri) throws IOException {
        // Uri → byte[] (InputStream.readAllBytes는 API 33+ 전용이므로 사용하지 않음)
        byte[] original;
        try (InputStream in = resolver.openInputStream(uri)) {
            if (in == null) {
                throw new IOException("이미지를 열 수 없습니다.");
            }
            original = ImageUtils.readAll(in);
        }

        BitmapFactory.Options options = new BitmapFactory.Options();
        options.inJustDecodeBounds = true;
        BitmapFactory.decodeByteArray(original, 0, original.length, options);
        int longSide = Math.max(options.outWidth, options.outHeight);
        options.inSampleSize = ImageUtils.calculateInSampleSize(longSide, MAX_IMAGE_SIDE);
        options.inJustDecodeBounds = false;
        Bitmap bitmap = BitmapFactory.decodeByteArray(original, 0, original.length, options);
        if (bitmap == null) {
            throw new IOException("이미지를 디코딩할 수 없습니다.");
        }

        Matrix matrix = new Matrix();
        float scale = Math.min(1f, (float) MAX_IMAGE_SIDE / Math.max(bitmap.getWidth(), bitmap.getHeight()));
        matrix.postScale(scale, scale);
        matrix.postRotate(exifRotation(original));
        Bitmap resized = Bitmap.createBitmap(bitmap, 0, 0, bitmap.getWidth(), bitmap.getHeight(), matrix, true);

        ByteArrayOutputStream out = new ByteArrayOutputStream();
        resized.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, out);
        if (resized != bitmap) {
            resized.recycle();
        }
        bitmap.recycle();
        return out.toByteArray();
    }

    /** 카메라 사진은 EXIF에 회전 정보만 있고 픽셀은 눕혀져 있으므로 각도를 읽어 바로 세운다 */
    private static int exifRotation(byte[] imageBytes) {
        try (InputStream in = new java.io.ByteArrayInputStream(imageBytes)) {
            int orientation = new ExifInterface(in).getAttributeInt(
                    ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL);
            switch (orientation) {
                case ExifInterface.ORIENTATION_ROTATE_90:
                    return 90;
                case ExifInterface.ORIENTATION_ROTATE_180:
                    return 180;
                case ExifInterface.ORIENTATION_ROTATE_270:
                    return 270;
                default:
                    return 0;
            }
        } catch (IOException e) {
            return 0;
        }
    }
}
