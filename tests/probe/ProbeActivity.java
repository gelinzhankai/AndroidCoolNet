package test.probe;

import android.app.Activity;
import android.os.Bundle;
import android.widget.TextView;
import java.net.HttpURLConnection;
import java.net.URL;
import java.io.InputStream;
import java.io.ByteArrayOutputStream;

/** Only calls an RFC5737 test address. The local mock proxy returns a marker. */
public class ProbeActivity extends Activity {
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        final TextView text = new TextView(this);
        text.setText("PROBE_PENDING");
        setContentView(text);
        new Thread(() -> {
            String result;
            try {
                HttpURLConnection c = (HttpURLConnection)new URL("http://198.51.100.1/probe").openConnection(java.net.Proxy.NO_PROXY);
                c.setConnectTimeout(5000);
                c.setReadTimeout(5000);
                c.setInstanceFollowRedirects(false);
                InputStream in = c.getInputStream();
                ByteArrayOutputStream b = new ByteArrayOutputStream();
                byte[] buf = new byte[1024];
                int count;
                while ((count = in.read(buf)) != -1 && b.size() < 4096) b.write(buf, 0, count);
                in.close();
                c.disconnect();
                result = new String(b.toByteArray(), "UTF-8");
            } catch (Exception e) {
                result = "PROBE_BLOCKED_NO_NETWORK";
            }
            final String output = result;
            runOnUiThread(() -> text.setText(output));
        }).start();
    }
}
