package io.github.gelinzhankai.androidcoolnet.clipboard;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.os.Bundle;
import android.util.Base64;
import android.widget.TextView;
import java.nio.charset.StandardCharsets;

/** Foreground clipboard bridge. No network, storage, accessibility or root permissions. */
public final class ClipboardActivity extends Activity {
    private TextView result;
    private boolean handled;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        result = new TextView(this);
        result.setId(android.R.id.text1);
        result.setText("AndroidCoolNet: 等待窗口获得焦点…");
        result.setTextSize(12);
        result.setPadding(16, 48, 16, 16);
        setContentView(result);
    }

    @Override public void onWindowFocusChanged(boolean focused) {
        super.onWindowFocusChanged(focused);
        if (!focused || handled) return;
        handled = true;
        result.postDelayed(this::exchange, 150);
    }

    private void exchange() {
        String nonce = getIntent().getStringExtra("nonce");
        if (nonce == null || !nonce.matches("[a-f0-9]{24}")) {
            result.setText("ACN:INVALID_REQUEST");
            return;
        }
        try {
            ClipboardManager clipboard = getSystemService(ClipboardManager.class);
            String operation = getIntent().getStringExtra("operation");
            String requested = null;
            if ("write".equals(operation)) {
                String encoded = getIntent().getStringExtra("payload");
                if (encoded == null || encoded.length() > 48000) throw new IllegalArgumentException();
                requested = new String(Base64.decode(encoded, Base64.NO_WRAP), StandardCharsets.UTF_8);
                clipboard.setPrimaryClip(ClipData.newPlainText("AndroidCoolNet", requested));
            } else if (!"read".equals(operation)) {
                throw new IllegalArgumentException();
            }
            ClipData data = clipboard.getPrimaryClip();
            CharSequence value = data == null || data.getItemCount() == 0 ? null : data.getItemAt(0).getText();
            String text = value == null ? "" : value.toString();
            if (text.length() > 36000 || (requested != null && !requested.equals(text))) {
                throw new IllegalStateException();
            }
            String encoded = Base64.encodeToString(text.getBytes(StandardCharsets.UTF_8), Base64.NO_WRAP);
            result.setText("AndroidCoolNet\n剪贴板已准备，请等待电脑继续配置。");
            result.setContentDescription("ACN:" + nonce + ":OK:" + encoded);
        } catch (RuntimeException error) {
            // No clipboard content or exception details in logcat.
            result.setText("AndroidCoolNet\n剪贴板操作失败，请查看电脑上的提示。");
            result.setContentDescription("ACN:" + nonce + ":ERROR");
        }
    }
}
