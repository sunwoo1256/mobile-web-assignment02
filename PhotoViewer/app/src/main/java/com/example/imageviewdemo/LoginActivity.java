package com.example.imageviewdemo;

import android.content.Intent;
import android.os.Bundle;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.View;
import android.view.inputmethod.EditorInfo;

import androidx.appcompat.app.AppCompatActivity;

import com.google.android.material.button.MaterialButton;
import com.google.android.material.chip.ChipGroup;
import com.google.android.material.textfield.TextInputEditText;
import com.google.android.material.textfield.TextInputLayout;

import org.json.JSONObject;

import android.widget.TextView;

/** 기능 1. 로그인 — 아이디·비밀번호로 토큰을 발급받아 저장하고, 접속할 서버를 고른다 */
public class LoginActivity extends AppCompatActivity {
    private TextInputLayout layoutUsername;
    private TextInputLayout layoutPassword;
    private TextInputEditText editUsername;
    private TextInputEditText editPassword;
    private TextInputEditText editServerUrl;
    private ChipGroup chipGroupServer;
    private TextView textError;
    private MaterialButton btnLogin;
    private View progressLogin;
    // 칩을 눌러 주소를 채울 때는 TextWatcher가 "직접 입력"으로 바꾸지 않도록 한다
    private boolean fillingUrl;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        if (ApiConfig.isLoggedIn(this)) { // 자동 로그인
            openMain();
            return;
        }
        setContentView(R.layout.activity_login);

        layoutUsername = findViewById(R.id.layoutUsername);
        layoutPassword = findViewById(R.id.layoutPassword);
        editUsername = findViewById(R.id.editUsername);
        editPassword = findViewById(R.id.editPassword);
        editServerUrl = findViewById(R.id.editServerUrl);
        chipGroupServer = findViewById(R.id.chipGroupServer);
        textError = findViewById(R.id.textError);
        btnLogin = findViewById(R.id.btnLogin);
        progressLogin = findViewById(R.id.progressLogin);

        String savedUrl = ApiConfig.getBaseUrl(this);
        setServerUrl(savedUrl);
        chipGroupServer.check(chipFor(savedUrl));
        chipGroupServer.setOnCheckedStateChangeListener((group, checkedIds) -> {
            if (checkedIds.isEmpty()) {
                return;
            }
            int checked = checkedIds.get(0);
            if (checked == R.id.chipLocal) {
                setServerUrl(ApiConfig.LOCAL_URL);
            } else if (checked == R.id.chipCloud) {
                setServerUrl(ApiConfig.CLOUD_URL);
            } else {
                editServerUrl.requestFocus();
            }
        });
        editServerUrl.addTextChangedListener(new TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence s, int start, int count, int after) {
            }

            @Override
            public void onTextChanged(CharSequence s, int start, int before, int count) {
            }

            @Override
            public void afterTextChanged(Editable s) {
                if (!fillingUrl) {
                    chipGroupServer.check(chipFor(s.toString()));
                }
            }
        });

        editPassword.setOnEditorActionListener((v, actionId, event) -> {
            if (actionId == EditorInfo.IME_ACTION_DONE) {
                login();
                return true;
            }
            return false;
        });
        btnLogin.setOnClickListener(v -> login());
    }

    private int chipFor(String url) {
        String normalized = ApiConfig.normalizeUrl(url);
        if (normalized.equals(ApiConfig.LOCAL_URL)) {
            return R.id.chipLocal;
        }
        if (normalized.equals(ApiConfig.CLOUD_URL)) {
            return R.id.chipCloud;
        }
        return R.id.chipCustom;
    }

    private void setServerUrl(String url) {
        fillingUrl = true;
        editServerUrl.setText(url);
        fillingUrl = false;
    }

    private void login() {
        String username = text(editUsername);
        String password = text(editPassword);
        String baseUrl = ApiConfig.normalizeUrl(text(editServerUrl));
        layoutUsername.setError(username.isEmpty() ? getString(R.string.error_required) : null);
        layoutPassword.setError(password.isEmpty() ? getString(R.string.error_required) : null);
        if (username.isEmpty() || password.isEmpty() || baseUrl.isEmpty()) {
            return;
        }

        setLoading(true);
        Async.run(() -> ApiClient.request(baseUrl, null, "POST", ApiConfig.LOGIN_PATH,
                ApiClient.formBody("username", username, "password", password), ApiClient.FORM), (response, error) -> {
            if (isFinishing()) {
                return;
            }
            setLoading(false);
            if (error != null) {
                showError(getString(R.string.error_server_unreachable, baseUrl));
            } else if (response.isSuccessful()) {
                try {
                    JSONObject json = new JSONObject(response.body);
                    ApiConfig.saveLogin(this, baseUrl, json.getString("token"),
                            json.optInt("user_id"), json.optString("username", username));
                    openMain();
                } catch (Exception e) {
                    showError("로그인 응답을 해석하지 못했습니다.");
                }
            } else if (response.code == 400) {
                showError(getString(R.string.error_login_failed));
            } else {
                showError("로그인 실패: " + ApiClient.errorMessage(response));
            }
        });
    }

    private void setLoading(boolean loading) {
        progressLogin.setVisibility(loading ? View.VISIBLE : View.INVISIBLE);
        btnLogin.setEnabled(!loading);
        if (loading) {
            textError.setVisibility(View.GONE);
        }
    }

    private void showError(String message) {
        textError.setText(message);
        textError.setVisibility(View.VISIBLE);
    }

    private void openMain() {
        startActivity(new Intent(this, MainActivity.class));
        finish();
    }

    private static String text(TextInputEditText edit) {
        return edit.getText() == null ? "" : edit.getText().toString().trim();
    }
}
