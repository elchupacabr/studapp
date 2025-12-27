package elchupacabrsoft.stud.sssu

import android.annotation.SuppressLint
import android.app.Activity
import android.app.DownloadManager
import android.content.*
import android.net.ConnectivityManager
import android.net.NetworkInfo
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.os.Handler
import android.view.KeyEvent
import android.view.View
import android.webkit.*
import android.widget.Button
import android.widget.ProgressBar
import android.widget.RelativeLayout
import android.widget.Toast
import androidx.annotation.RequiresApi
import androidx.appcompat.app.AppCompatDelegate
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import elchupacabrsoft.stud.sssu.R.*
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLDecoder
import java.util.*

class MainActivity : Activity() {

    private lateinit var mContext: Context
    private var mLoaded = false
    private var defaultURL = "https://stud.sssu.ru/WebApp/#/Rasp/Group/26576"
    private var currentURL: String? = null
    private var doubleBackToExitPressedOnce = false

    private lateinit var btnTryAgain: Button
    private lateinit var mWebView: WebView
    private lateinit var swipeRefreshLayout: SwipeRefreshLayout
    private lateinit var prgs: ProgressBar
    private lateinit var layoutWebview: RelativeLayout

    private val prefsName = "webview_prefs"
    private val lastUrlKey = "last_url"

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(layout.activity_main)

        mContext = this
        swipeRefreshLayout = findViewById(id.swipe_containers)
        swipeRefreshLayout.setOnRefreshListener { mWebView.reload() }

        AppCompatDelegate.setCompatVectorFromResourcesEnabled(true)

        mWebView = findViewById<View>(id.webview) as WebView
        prgs = findViewById<View>(id.progressBar) as ProgressBar
        btnTryAgain = findViewById<View>(id.btn_try_again) as Button
        layoutWebview = findViewById<View>(id.layout_webview) as RelativeLayout

        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(mWebView, true)

        // ???????? ????????? URL
        val prefs = getSharedPreferences(prefsName, Context.MODE_PRIVATE)
        currentURL = prefs.getString(lastUrlKey, defaultURL)

        requestForWebview()

        btnTryAgain.setOnClickListener {
            mWebView.visibility = View.GONE
            prgs.visibility = View.VISIBLE
            swipeRefreshLayout.isRefreshing = true
            requestForWebview()
        }

        checkUpdate()
    }

    private fun requestForWebview() {
        if (!mLoaded) {
            requestWebView()
            Handler().postDelayed({
                swipeRefreshLayout.isRefreshing = true
                prgs.visibility = View.VISIBLE
                mWebView.visibility = View.VISIBLE
            }, 200)
        } else {
            mWebView.visibility = View.VISIBLE
            prgs.visibility = View.GONE
            swipeRefreshLayout.isRefreshing = false
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    @RequiresApi(Build.VERSION_CODES.LOLLIPOP)
    private fun requestWebView() {
        mWebView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            cacheMode = WebSettings.LOAD_DEFAULT
            mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
            setSupportMultipleWindows(false)
        }

        if (internetCheck(mContext)) {
            mWebView.visibility = View.VISIBLE
            mWebView.loadUrl(currentURL!!)
        } else {
            Toast.makeText(this, "No internet connection", Toast.LENGTH_LONG).show()
        }

        mWebView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, url: String?): Boolean {
                if (internetCheck(mContext)) view.loadUrl(url!!)
                else Toast.makeText(mContext, "No internet", Toast.LENGTH_SHORT).show()
                return true
            }

            override fun onPageStarted(view: WebView, url: String, favicon: android.graphics.Bitmap?) {
                super.onPageStarted(view, url, favicon)
                swipeRefreshLayout.isRefreshing = true
                if (prgs.visibility == View.GONE) prgs.visibility = View.VISIBLE
            }

            override fun onPageFinished(view: WebView, url: String) {
                super.onPageFinished(view, url)
                mLoaded = true
                swipeRefreshLayout.isRefreshing = false
                if (prgs.visibility == View.VISIBLE) prgs.visibility = View.GONE

                currentURL = url
                val prefs = getSharedPreferences(prefsName, Context.MODE_PRIVATE)
                prefs.edit().putString(lastUrlKey, url).apply()

                // ???? ????
                val authPrefs = getSharedPreferences("auth", Context.MODE_PRIVATE)
                val login = authPrefs.getString("login", "")
                val password = authPrefs.getString("password", "")

                if (!login.isNullOrEmpty() && !password.isNullOrEmpty()) {
                    mWebView.evaluateJavascript("""
                        (function waitForLogin() {
                            var loginField = document.querySelector('input[type="text"], input[name*="login"], input[id*="login"]');
                            var passField = document.querySelector('input[type="password"]');
                            var loginButton = document.querySelector('button[type="submit"], input[type="submit"]');
                            if (loginField && passField) {
                                loginField.value = '$login';
                                passField.value = '$password';
                                if(loginButton) loginButton.click();
                            } else setTimeout(waitForLogin, 500);
                        })();
                    """.trimIndent(), null)
                }
            }
        }

        // ????????? ?????? ? ???????? ???????
        mWebView.setDownloadListener { url, userAgent, contentDisposition, mimetype, _ ->
            try {
                var filename = URLUtil.guessFileName(url, contentDisposition, mimetype)

                if (!contentDisposition.isNullOrEmpty()) {
                    val regexUtf = Regex("filename\\*=UTF-8''(.+)")
                    val matchUtf = regexUtf.find(contentDisposition)
                    if (matchUtf != null) {
                        filename = Uri.decode(matchUtf.groupValues[1])
                    } else {
                        val regex = Regex("filename=\"([^\"]+)\"")
                        val match = regex.find(contentDisposition)
                        if (match != null) filename = match.groupValues[1]
                    }
                }

                if (filename.isBlank() || filename.toLowerCase(Locale.getDefault()) == "download") { filename = "file_" + System.currentTimeMillis() }

                val safeFilename = filename.replace("[\\\\/:*?\"<>|]".toRegex(), "_")

                val request = DownloadManager.Request(Uri.parse(url))
                val cookie = CookieManager.getInstance().getCookie(url)
                request.addRequestHeader("Cookie", cookie)
                request.addRequestHeader("User-Agent", userAgent)
                request.setTitle(filename)
                request.setDescription("Downloading file...")
                request.allowScanningByMediaScanner()
                request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, safeFilename)

                val dm = getSystemService(DOWNLOAD_SERVICE) as DownloadManager
                dm.enqueue(request)

                Toast.makeText(this, filename, Toast.LENGTH_LONG).show()
            } catch (e: Exception) {
                Toast.makeText(this, "Error downloading: ${e.message}", Toast.LENGTH_LONG).show()
            }
        }
    }

    /** ?????????????? **/
    private fun checkUpdate() {
        Thread {
            try {
                val versionUrl = "https://raw.githubusercontent.com/elchupacabr/studapp/refs/heads/main/latest_version.txt"
                val url = URL(versionUrl)
                val connection = url.openConnection() as HttpURLConnection
                connection.requestMethod = "GET"
                connection.connectTimeout = 5000
                connection.readTimeout = 5000

                val reader = BufferedReader(InputStreamReader(connection.inputStream))
                val latestVersion = reader.readLine().trim()
                reader.close()
                connection.disconnect()

                val currentVersion = BuildConfig.VERSION_NAME
                if (currentVersion != latestVersion) {
                    runOnUiThread {
                        Toast.makeText(this, "A new version is available v$latestVersion", Toast.LENGTH_LONG).show()
                        downloadApk(latestVersion)
                    }
                }
            } catch (e: Exception) {
                runOnUiThread {
                    Toast.makeText(this, "Error checking update: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
        }.start()
    }

    private fun downloadApk(version: String) {
        try {
            val apkUrl = "https://github.com/elchupacabr/studapp/releases/download/v.$version/app-debug.apk"
            val filename = "studapp_v$version.apk"

            val request = DownloadManager.Request(Uri.parse(apkUrl))
            request.setTitle("Downloading update")
            request.setDescription("Downloading version $version")
            request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, filename)
            request.setMimeType("application/vnd.android.package-archive")
            request.setAllowedOverMetered(true)
            request.setAllowedOverRoaming(true)

            val dm = getSystemService(DOWNLOAD_SERVICE) as DownloadManager
            val downloadId = dm.enqueue(request)
            Toast.makeText(this, "Started downloading update", Toast.LENGTH_SHORT).show()

            val onComplete = object : BroadcastReceiver() {
                override fun onReceive(context: Context, intent: Intent) {
                    val uri = dm.getUriForDownloadedFile(downloadId)
                    val installIntent = Intent(Intent.ACTION_VIEW)
                    installIntent.setDataAndType(uri, "application/vnd.android.package-archive")
                    installIntent.flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_GRANT_READ_URI_PERMISSION
                    startActivity(installIntent)
                    unregisterReceiver(this)
                }
            }
            registerReceiver(onComplete, IntentFilter(DownloadManager.ACTION_DOWNLOAD_COMPLETE))
        } catch (e: Exception) {
            Toast.makeText(this, "Error downloading update: ${e.message}", Toast.LENGTH_LONG).show()
        }
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent): Boolean {
        when (keyCode) {
            KeyEvent.KEYCODE_BACK -> {
                if (mWebView.canGoBack()) {
                    mWebView.goBack()
                    return true
                }
                if (doubleBackToExitPressedOnce) return super.onKeyDown(keyCode, event)
                doubleBackToExitPressedOnce = true
                Toast.makeText(this, "Please press Back to Exit", Toast.LENGTH_SHORT).show()
                Handler().postDelayed({ doubleBackToExitPressedOnce = false }, 500)
                return true
            }
            else -> return super.onKeyDown(keyCode, event) // Volume ? ????????? ?????? ?????????????? ????????
        }
    }


    companion object {
        fun internetCheck(context: Context): Boolean {
            val connectivity = context.getSystemService(CONNECTIVITY_SERVICE) as ConnectivityManager
            val networkInfo = connectivity.allNetworkInfo
            return networkInfo?.any { it.state == NetworkInfo.State.CONNECTED } ?: false
        }
    }
}
