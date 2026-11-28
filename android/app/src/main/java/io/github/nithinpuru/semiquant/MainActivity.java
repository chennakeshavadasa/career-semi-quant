package io.github.nithinpuru.semiquant;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.BroadcastReceiver;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.provider.Settings;
import android.util.Base64;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.webkit.JavascriptInterface;
import android.webkit.URLUtil;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * Semi Quant Terminal for Android: a full-screen WebView on the web edition
 * (chennakeshavadasa.github.io/career-semi-quant/app/, published by this repo). The page does all the work: live
 * prices stream from Yahoo, analytics come from the data published every 15
 * minutes, and the service worker keeps the last data for offline use. This
 * activity adds what a browser normally provides: file downloads, the share
 * sheet, opening outside links in the browser, and the back button.
 */
public class MainActivity extends Activity {

    static final String HOST = "chennakeshavadasa.github.io";
    static final String APP_PATH = "/career-semi-quant/app";
    static final String HOME = "https://" + HOST + APP_PATH + "/";
    static final String OFFLINE = "file:///android_asset/offline.html";
    static final int BG = 0xFF000000;
    static final String RELEASE = "https://github.com/chennakeshavadasa/career-semi-quant/releases/download/android/";
    static final long AUTO_CHECK_MS = 6L * 3600 * 1000; // check for a new app build at most every 6 hours

    /**
     * Injected after each page load. Downloads made by the page (CSV, Excel, chart PNG)
     * are blob: or data: links with a download attribute, which a WebView cannot save on
     * its own: hand their bytes to the app instead. Also provides navigator.share.
     */
    static final String HOOK =
        "(function(){" +
        "if(window.__sqAndroid)return;window.__sqAndroid=true;" +
        "function grab(a){var href=a.href||'';if(!a.hasAttribute('download')||!/^(blob:|data:)/.test(href))return false;" +
        " var name=a.getAttribute('download')||'download';" +
        " fetch(href).then(function(r){return r.blob();}).then(function(b){var fr=new FileReader();" +
        "  fr.onload=function(){var s=String(fr.result);SQAndroid.save(name,b.type||'application/octet-stream',s.slice(s.indexOf(',')+1));};" +
        "  fr.readAsDataURL(b);}).catch(function(e){SQAndroid.toast('Download failed: '+e);});" +
        " return true;}" +
        "var click=HTMLAnchorElement.prototype.click;" +
        "HTMLAnchorElement.prototype.click=function(){if(grab(this))return;return click.apply(this,arguments);};" +
        "document.addEventListener('click',function(e){var a=e.target&&e.target.closest&&e.target.closest('a[download]');" +
        " if(a&&grab(a))e.preventDefault();},true);" +
        "navigator.share=function(d){d=d||{};SQAndroid.share(d.title||document.title,d.text||'',d.url||location.href);return Promise.resolve();};" +
        "})();";

    private WebView web;
    private boolean clearHistoryOnLoad = false;
    private long downloadId = -1;
    private String pendingApk = null; // waiting for "install unknown apps" permission
    private BroadcastReceiver downloadDone;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);

        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(BG);
        web = new WebView(this);
        web.setBackgroundColor(BG);
        root.addView(web, new FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(root);
        fitSystemBars(root);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);      // watchlists, settings, portfolio
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setSupportMultipleWindows(false); // target=_blank loads here, then goes to the browser
        s.setUserAgentString(s.getUserAgentString() + " SemiQuantAndroid/" + BuildConfig.VERSION_NAME);

        web.addJavascriptInterface(new Bridge(), "SQAndroid");
        web.setWebChromeClient(new WebChromeClient());
        web.setWebViewClient(new Client());
        web.setDownloadListener((url, ua, disposition, mime, length) -> {
            if (url.startsWith("data:")) {
                saveDataUrl(url, URLUtil.guessFileName(url, disposition, mime));
            } else if (url.startsWith("blob:")) {
                String name = URLUtil.guessFileName(url, disposition, mime);
                web.evaluateJavascript("(function(){var a=document.createElement('a');a.href=" + jsString(url)
                    + ";a.setAttribute('download'," + jsString(name) + ");a.click();})()", null);
            } else {
                openExternal(Uri.parse(url));
            }
        });

        downloadDone = new BroadcastReceiver() {
            @Override
            public void onReceive(Context ctx, Intent intent) {
                long id = intent.getLongExtra(DownloadManager.EXTRA_DOWNLOAD_ID, -1);
                if (id == downloadId) installDownloaded(id);
            }
        };
        IntentFilter f = new IntentFilter(DownloadManager.ACTION_DOWNLOAD_COMPLETE);
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(downloadDone, f, Context.RECEIVER_EXPORTED);
        else registerReceiver(downloadDone, f);

        SharedPreferences prefs = getSharedPreferences("sq", MODE_PRIVATE);
        if (System.currentTimeMillis() - prefs.getLong("lastUpdateCheck", 0) > AUTO_CHECK_MS) {
            prefs.edit().putLong("lastUpdateCheck", System.currentTimeMillis()).apply();
            checkForUpdate(false, false);
        }

        if (state != null && web.restoreState(state) != null) return;
        web.loadUrl(startUrl(getIntent()));
    }

    // ── app updates: version.json next to the APK in the "android" release ──
    // The app has two parts that update separately: this shell (the APK, rebuilt only when android/
    // changes) and the layout (the web edition, redeployed on every push to master).
    /**
     * manual = from the "Update app" button: also report "up to date" and errors.
     * reloadLayout = when this build is current, also reload the page so a newly deployed layout
     * shows. Current pages check their layout themselves (static.js) and call checkAppUpdate();
     * pages from before that only call checkUpdate(), which asks for the reload.
     */
    void checkForUpdate(boolean manual, boolean reloadLayout) {
        if (manual) toast("Checking for updates…");
        new Thread(() -> {
            try {
                JSONObject j = new JSONObject(fetch(RELEASE + "version.json"));
                int code = j.getInt("versionCode");
                String name = j.optString("versionName", String.valueOf(code));
                String apk = j.optString("apk", RELEASE + "SemiQuant.apk");
                String notes = j.optString("notes", "");
                if (code > BuildConfig.VERSION_CODE) runOnUiThread(() -> promptUpdate(name, notes, apk));
                else {
                    if (manual) toast("You have the latest app version (" + BuildConfig.VERSION_NAME + ")."
                        + (reloadLayout ? " Loading the newest layout…" : ""));
                    if (reloadLayout) reloadPage();
                }
            } catch (Exception e) {
                if (manual) toast("Could not check for updates: " + e.getMessage());
            }
        }).start();
    }

    /** Reload the web edition; a reload revalidates the page with the server, so a new layout loads. */
    private void reloadPage() {
        runOnUiThread(() -> {
            String url = web.getUrl();
            if (url != null && isApp(Uri.parse(url))) web.reload();
            else web.loadUrl(HOME); // e.g. on the offline page
        });
    }

    static String fetch(String url) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url + "?t=" + System.currentTimeMillis()).openConnection();
        c.setInstanceFollowRedirects(true); // GitHub answers with a redirect to its download host (https to https)
        c.setConnectTimeout(15000);
        c.setReadTimeout(15000);
        c.setRequestProperty("Cache-Control", "no-cache");
        if (c.getResponseCode() != 200) throw new Exception("HTTP " + c.getResponseCode());
        try (InputStream in = c.getInputStream(); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buf = new byte[8192];
            for (int n; (n = in.read(buf)) > 0; ) out.write(buf, 0, n);
            return out.toString("UTF-8");
        } finally {
            c.disconnect();
        }
    }

    private void promptUpdate(String name, String notes, String apk) {
        if (isFinishing()) return;
        new AlertDialog.Builder(this)
            .setTitle("Update available")
            .setMessage("Semi Quant " + name + " is ready (you have " + BuildConfig.VERSION_NAME + ")."
                + (notes.isEmpty() ? "" : "\n\n" + notes) + "\n\nYour watchlists and portfolio are kept.")
            .setPositiveButton("Update now", (d, w) -> startUpdate(apk))
            .setNegativeButton("Later", null)
            .show();
    }

    private void startUpdate(String apk) {
        if (Build.VERSION.SDK_INT >= 26 && !getPackageManager().canRequestPackageInstalls()) {
            pendingApk = apk; // resumed in onResume once allowed
            toast("Allow Semi Quant to install updates, then press back.");
            try {
                startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + getPackageName())));
            } catch (ActivityNotFoundException e) {
                openExternal(Uri.parse(apk));
            }
            return;
        }
        try {
            File dir = getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS);
            File old = new File(dir, "SemiQuant-update.apk");
            if (old.exists()) old.delete();
            DownloadManager dm = (DownloadManager) getSystemService(DOWNLOAD_SERVICE);
            DownloadManager.Request r = new DownloadManager.Request(Uri.parse(apk))
                .setTitle("Semi Quant update")
                .setMimeType("application/vnd.android.package-archive")
                .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE)
                .setDestinationInExternalFilesDir(this, Environment.DIRECTORY_DOWNLOADS, "SemiQuant-update.apk");
            downloadId = dm.enqueue(r);
            toast("Downloading the update…");
        } catch (Exception e) {
            toast("Download failed (" + e.getMessage() + "): opening it in the browser.");
            openExternal(Uri.parse(apk));
        }
    }

    private void installDownloaded(long id) {
        DownloadManager dm = (DownloadManager) getSystemService(DOWNLOAD_SERVICE);
        int status = -1;
        try (Cursor c = dm.query(new DownloadManager.Query().setFilterById(id))) {
            if (c != null && c.moveToFirst()) status = c.getInt(c.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS));
        } catch (Exception ignored) { }
        if (status != DownloadManager.STATUS_SUCCESSFUL) { toast("The update download failed; try again."); return; }
        Uri uri = dm.getUriForDownloadedFile(id);
        Intent i = new Intent(Intent.ACTION_VIEW)
            .setDataAndType(uri, "application/vnd.android.package-archive")
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
        try { startActivity(i); } catch (ActivityNotFoundException e) { toast("No installer found on this device."); }
    }

    // ── layout ───────────────────────────────────────────────────────────
    /** Draw behind the status and navigation bars (forced on Android 15) and pad the content clear of them and of the keyboard. */
    private void fitSystemBars(FrameLayout root) {
        if (Build.VERSION.SDK_INT < 30) return; // older versions lay out below the bars and resize for the keyboard
        getWindow().setDecorFitsSystemWindows(false);
        root.setOnApplyWindowInsetsListener((v, insets) -> {
            android.graphics.Insets i = insets.getInsets(WindowInsets.Type.systemBars()
                | WindowInsets.Type.displayCutout() | WindowInsets.Type.ime());
            v.setPadding(i.left, i.top, i.right, i.bottom);
            return WindowInsets.CONSUMED;
        });
    }

    // ── navigation ───────────────────────────────────────────────────────
    static boolean isApp(Uri u) {
        return u != null && "https".equals(u.getScheme()) && HOST.equals(u.getHost())
            && u.getPath() != null && u.getPath().startsWith(APP_PATH);
    }

    private String startUrl(Intent intent) {
        Uri data = intent == null ? null : intent.getData();
        return isApp(data) ? data.toString() : HOME;
    }

    private void openExternal(Uri u) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, u).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        } catch (ActivityNotFoundException e) {
            toast("No app can open this link.");
        }
    }

    private class Client extends WebViewClient {
        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest req) {
            Uri u = req.getUrl();
            String scheme = u.getScheme() == null ? "" : u.getScheme();
            if (isApp(u)) return false;
            if (scheme.equals("blob") || scheme.equals("data") || scheme.equals("about")) return false;
            openExternal(u); // news, SEC filings, GitHub, mailto: ...
            return true;
        }

        @Override
        public void onPageFinished(WebView view, String url) {
            if (url != null && url.startsWith("https://")) {
                view.evaluateJavascript(HOOK, null);
                if (clearHistoryOnLoad) { view.clearHistory(); clearHistoryOnLoad = false; }
            }
        }

        @Override
        public void onReceivedError(WebView view, WebResourceRequest req, WebResourceError err) {
            // Only reached when the app shell isn't cached yet (first launch offline).
            if (req.isForMainFrame() && isApp(req.getUrl())) {
                clearHistoryOnLoad = true;
                view.loadUrl(OFFLINE);
            }
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        if (intent.getData() != null && isApp(intent.getData())) web.loadUrl(intent.getData().toString());
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    // ── lifecycle ────────────────────────────────────────────────────────
    @Override
    protected void onResume() {
        super.onResume();
        web.onResume();
        web.resumeTimers();
        if (pendingApk != null && (Build.VERSION.SDK_INT < 26 || getPackageManager().canRequestPackageInstalls())) {
            String apk = pendingApk;
            pendingApk = null;
            startUpdate(apk);
        }
    }

    @Override
    protected void onPause() {
        web.onPause();      // page sees visibilitychange: the price stream pauses
        web.pauseTimers();
        super.onPause();
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
    }

    @Override
    protected void onDestroy() {
        try { unregisterReceiver(downloadDone); } catch (Exception ignored) { }
        web.destroy();
        super.onDestroy();
    }

    // ── files and sharing ────────────────────────────────────────────────
    private class Bridge {
        @JavascriptInterface
        public void save(String name, String mime, String base64) {
            try {
                byte[] bytes = Base64.decode(base64, Base64.DEFAULT);
                String where = writeDownload(safeName(name), mime, bytes);
                toast("Saved " + where);
            } catch (Exception e) {
                toast("Could not save " + name + ": " + e.getMessage());
            }
        }

        @JavascriptInterface
        public void share(String title, String text, String url) {
            runOnUiThread(() -> {
                Intent send = new Intent(Intent.ACTION_SEND).setType("text/plain");
                send.putExtra(Intent.EXTRA_SUBJECT, title);
                String body = text == null || text.isEmpty() ? url : text + "\n" + url;
                send.putExtra(Intent.EXTRA_TEXT, body);
                startActivity(Intent.createChooser(send, "Share"));
            });
        }

        @JavascriptInterface
        public void toast(String msg) {
            MainActivity.this.toast(msg);
        }

        /** "Update app" on pages from before the layout check: newest app build, then the newest layout. */
        @JavascriptInterface
        public void checkUpdate() {
            runOnUiThread(() -> checkForUpdate(true, true));
        }

        /** "Update app" on current pages, which reload into the newest layout themselves (static.js). */
        @JavascriptInterface
        public void checkAppUpdate() {
            runOnUiThread(() -> checkForUpdate(true, false));
        }

        @JavascriptInterface
        public String appVersion() {
            return BuildConfig.VERSION_NAME;
        }
    }

    private void saveDataUrl(String url, String name) {
        int comma = url.indexOf(',');
        if (comma < 0) return;
        String header = url.substring(5, comma); // after "data:"
        String mime = header.contains(";") ? header.substring(0, header.indexOf(';')) : header;
        try {
            byte[] bytes = header.endsWith(";base64")
                ? Base64.decode(url.substring(comma + 1), Base64.DEFAULT)
                : Uri.decode(url.substring(comma + 1)).getBytes("UTF-8");
            toast("Saved " + writeDownload(safeName(name), mime.isEmpty() ? "application/octet-stream" : mime, bytes));
        } catch (Exception e) {
            toast("Could not save " + name + ": " + e.getMessage());
        }
    }

    /** Writes to Downloads/SemiQuant (Android 10+) or the app's own Downloads folder (Android 8-9, no permission needed). */
    private String writeDownload(String name, String mime, byte[] bytes) throws Exception {
        if (Build.VERSION.SDK_INT >= 29) {
            ContentValues cv = new ContentValues();
            cv.put(MediaStore.MediaColumns.DISPLAY_NAME, name);
            cv.put(MediaStore.MediaColumns.MIME_TYPE, mime);
            cv.put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/SemiQuant");
            Uri uri = getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, cv);
            if (uri == null) throw new Exception("storage unavailable");
            try (OutputStream os = getContentResolver().openOutputStream(uri)) {
                if (os == null) throw new Exception("storage unavailable");
                os.write(bytes);
            }
            return "to Downloads/SemiQuant/" + name;
        }
        File dir = getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS);
        if (dir == null) dir = getFilesDir();
        File f = new File(dir, name);
        try (FileOutputStream os = new FileOutputStream(f)) { os.write(bytes); }
        return "to " + f.getAbsolutePath();
    }

    static String safeName(String name) {
        String n = name == null ? "" : name.replaceAll("[\\\\/:*?\"<>|\\x00-\\x1f]", "_").trim();
        return n.isEmpty() ? "semiquant-download" : n;
    }

    static String jsString(String s) {
        return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'";
    }

    private void toast(String msg) {
        runOnUiThread(() -> Toast.makeText(this, msg, Toast.LENGTH_LONG).show());
    }
}
