package elchupacabrsoft.stud.sssu

import android.annotation.SuppressLint
import android.app.*
import android.content.*
import android.graphics.Bitmap
import android.net.ConnectivityManager
import android.net.NetworkInfo
import android.net.Uri
import android.os.*
import android.text.Html
import android.view.KeyEvent
import android.view.View
import android.webkit.*
import android.widget.Button
import android.widget.ProgressBar
import android.widget.RelativeLayout
import android.widget.Toast
import androidx.annotation.RequiresApi
import androidx.appcompat.app.AppCompatDelegate
import androidx.core.app.NotificationCompat
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
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

    private var fileChooserCallback: ValueCallback<Array<Uri>>? = null
    private val FILE_CHOOSER_REQUEST_CODE = 1001

    private val prefsName = "webview_prefs"
    private val lastUrlKey = "last_url"

    /** Разрешенные расширения для скачивания **/
    private val allowedExtensions = listOf(
        "pdf","doc","docx","xls","xlsx","ppt","pptx",
        "zip","rar","7z",
        "png","jpg","jpeg","gif","bmp",
        "txt"
    )

    private fun isAllowedFile(name: String): Boolean {
        val ext = name.substringAfterLast('.', "").toLowerCase(Locale.getDefault())
        return allowedExtensions.contains(ext)
    }

    @RequiresApi(Build.VERSION_CODES.O)
    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        mContext = this

        swipeRefreshLayout = findViewById(R.id.swipe_containers)
        swipeRefreshLayout.setOnRefreshListener { mWebView.reload() }

        AppCompatDelegate.setCompatVectorFromResourcesEnabled(true)

        mWebView = findViewById(R.id.webview)
        prgs = findViewById(R.id.progressBar)
        btnTryAgain = findViewById(R.id.btn_try_again)
        layoutWebview = findViewById(R.id.layout_webview)

        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(mWebView, true)

        val prefs = getSharedPreferences(prefsName, Context.MODE_PRIVATE)
        currentURL = prefs.getString(lastUrlKey, defaultURL)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            createNotificationChannels()
        }

        val openUrl = intent.getStringExtra("open_url")
        if (!openUrl.isNullOrEmpty()) {
            currentURL = openUrl
        }
        requestForWebview()

        checkNotifications()


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
            Handler(Looper.getMainLooper()).postDelayed({
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
        }

        val authPrefs = getSharedPreferences("auth", MODE_PRIVATE)
        val savedCookies = authPrefs.getString("cookies", null)
        val login = authPrefs.getString("login", "")
        val password = authPrefs.getString("password", "")

        // Подставляем куки перед загрузкой страницы
        val cookieManager = CookieManager.getInstance()
        cookieManager.setAcceptCookie(true)
        if (!savedCookies.isNullOrEmpty()) {
            cookieManager.setCookie(currentURL, savedCookies)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) cookieManager.flush()
        }

        if (internetCheck(mContext)) {
            mWebView.loadUrl(currentURL!!)
        } else {
            Toast.makeText(this, "Нет соединения с интернетом", Toast.LENGTH_LONG).show()
        }

        mWebView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, url: String?): Boolean {
                if (internetCheck(mContext)) view.loadUrl(url!!)
                else Toast.makeText(mContext, "Нет интернет-соединения", Toast.LENGTH_SHORT).show()
                return true
            }

            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {
                swipeRefreshLayout.isRefreshing = true
                prgs.visibility = View.VISIBLE
            }

            override fun onPageFinished(view: WebView, url: String) {
                swipeRefreshLayout.isRefreshing = false
                prgs.visibility = View.GONE
                mLoaded = true

                currentURL = url
                getSharedPreferences(prefsName, MODE_PRIVATE)
                    .edit().putString(lastUrlKey, url).apply()

                // JS автозаполнение если куки нет
                if (savedCookies.isNullOrEmpty() && !login.isNullOrEmpty() && !password.isNullOrEmpty()) {
                    mWebView.evaluateJavascript("""
                        (function waitForLogin(){
                            var l=document.querySelector('input[type=text], input[name*=login], input[id*=login]');
                            var p=document.querySelector('input[type=password]');
                            var b=document.querySelector('button[type=submit], input[type=submit]');
                            if(l && p){
                                l.value='$login';
                                p.value='$password';
                                if(b) b.click();
                            } else setTimeout(waitForLogin,500);
                        })();
                    """.trimIndent(), null)
                }

                // Сохраняем куки после входа
                val newCookies = cookieManager.getCookie(url)
                if (!newCookies.isNullOrEmpty()) {
                    authPrefs.edit().putString("cookies", newCookies).apply()
                }
            }
        }

        /** file chooser **/
        mWebView.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(
                webView: WebView?,
                filePathCallback: ValueCallback<Array<Uri>>,
                fileChooserParams: FileChooserParams
            ): Boolean {

                fileChooserCallback?.onReceiveValue(null)
                fileChooserCallback = filePathCallback

                return try {
                    startActivityForResult(
                        fileChooserParams.createIntent(),
                        FILE_CHOOSER_REQUEST_CODE
                    )
                    true
                } catch (e: Exception) {
                    Toast.makeText(this@MainActivity, "Невозможно открыть выбор файла", Toast.LENGTH_LONG).show()
                    false
                }
            }
        }

        /** download listener **/
        mWebView.setDownloadListener { url, userAgent, contentDisposition, mimetype, _ ->

            try {
                // Определяем имя файла
                var filename = URLUtil.guessFileName(url, contentDisposition, mimetype)

                if (!contentDisposition.isNullOrEmpty()) {
                    val utf = Regex("filename\\*=UTF-8''(.+)")
                    val m1 = utf.find(contentDisposition)
                    filename = if (m1 != null) Uri.decode(m1.groupValues[1])
                    else {
                        val reg = Regex("filename=\"([^\"]+)\"")
                        val m2 = reg.find(contentDisposition)
                        if (m2 != null) m2.groupValues[1] else filename
                    }
                }

                // fallback: имя из URL
                if (filename.isBlank() || filename.endsWith(".bin")) {
                    filename = Uri.parse(url).lastPathSegment ?: "file_${System.currentTimeMillis()}"
                }

                // добавить расширение по MIME, если нет
                if (!filename.contains(".") && !mimetype.isNullOrEmpty()) {
                    val ext = android.webkit.MimeTypeMap.getSingleton().getExtensionFromMimeType(mimetype)
                    if (!ext.isNullOrEmpty()) filename += ".$ext"
                }

                val safeFilename = filename.replace("[\\\\/:*?\"<>|]".toRegex(), "_")

                // Сначала спрашиваем пользователя
                AlertDialog.Builder(this)
                    .setTitle("Скачать файл")
                    .setMessage("Скачать \"$safeFilename\"?")
                    .setPositiveButton("Да") { _, _ ->

                        // Диалог с прогрессбаром
                        val dialogView = layoutInflater.inflate(R.layout.dialog_download_progress, null)
                        val progressBar = dialogView.findViewById<ProgressBar>(R.id.progressBar)
                        val progressDialog = AlertDialog.Builder(this)
                            .setTitle("Загрузка файла")
                            .setView(dialogView)
                            .setCancelable(false)
                            .create()
                        progressDialog.show()

                        // Настройка DownloadManager
                        val request = DownloadManager.Request(Uri.parse(url))
                        val cookie = CookieManager.getInstance().getCookie(url)
                        request.addRequestHeader("Cookie", cookie)
                        request.addRequestHeader("User-Agent", userAgent)
                        request.setTitle(safeFilename)
                        request.setDescription("Скачивание...")
                        request.setDestinationInExternalFilesDir(this, Environment.DIRECTORY_DOWNLOADS, safeFilename)
                        request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE)

                        val dm = getSystemService(DOWNLOAD_SERVICE) as DownloadManager
                        val downloadId = dm.enqueue(request)

                        val handler = Handler(Looper.getMainLooper())
                        handler.post(object : Runnable {
                            override fun run() {
                                val query = DownloadManager.Query().setFilterById(downloadId)
                                val cursor = dm.query(query)
                                if (cursor != null && cursor.moveToFirst()) {
                                    val bytesDownloaded = cursor.getInt(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_BYTES_DOWNLOADED_SO_FAR))
                                    val bytesTotal = cursor.getInt(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_TOTAL_SIZE_BYTES))
                                    if (bytesTotal > 0) {
                                        progressBar.progress = (bytesDownloaded * 100L / bytesTotal).toInt()
                                    }

                                    val status = cursor.getInt(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS))
                                    if (status == DownloadManager.STATUS_SUCCESSFUL) {
                                        cursor.close()
                                        progressDialog.dismiss()

                                        // Диалог после завершения
                                        AlertDialog.Builder(this@MainActivity)
                                            .setTitle("Загрузка завершена")
                                            .setMessage("Файл \"$safeFilename\" успешно загружен")
                                            .setPositiveButton("Открыть файл") { _, _ ->
                                                val fileUri = dm.getUriForDownloadedFile(downloadId)
                                                val openIntent = Intent(Intent.ACTION_VIEW)
                                                openIntent.setDataAndType(fileUri, mimetype ?: "*/*")
                                                openIntent.flags = Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK
                                                startActivity(Intent.createChooser(openIntent, "Открыть с помощью"))
                                            }
                                            .setNegativeButton("OK", null)
                                            .show()

                                        return
                                    } else if (status == DownloadManager.STATUS_FAILED) {
                                        cursor.close()
                                        progressDialog.dismiss()
                                        Toast.makeText(this@MainActivity, "Ошибка скачивания", Toast.LENGTH_LONG).show()
                                        return
                                    }
                                }
                                cursor?.close()
                                handler.postDelayed(this, 500)
                            }
                        })
                    }
                    .setNegativeButton("Нет", null)
                    .show()

            } catch (e: Exception) {
                Toast.makeText(this, "Ошибка: ${e.message}", Toast.LENGTH_LONG).show()
            }
        }

    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        if (requestCode == FILE_CHOOSER_REQUEST_CODE) {
            var results: Array<Uri>? = null
            if (resultCode == RESULT_OK && data?.data != null)
                results = arrayOf(data.data!!)
            fileChooserCallback?.onReceiveValue(results)
            fileChooserCallback = null
        }
        super.onActivityResult(requestCode, resultCode, data)
    }

    private fun downloadFile(url: String, filename: String, userAgent: String) {
        try {
            val request = DownloadManager.Request(Uri.parse(url))
            val cookie = CookieManager.getInstance().getCookie(url)

            request.addRequestHeader("Cookie", cookie)
            request.addRequestHeader("User-Agent", userAgent)
            request.setTitle(filename)
            request.setDescription("Скачивание...")
            request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, filename)

            (getSystemService(DOWNLOAD_SERVICE) as DownloadManager).enqueue(request)

            Toast.makeText(this, "Началась загрузка: $filename", Toast.LENGTH_SHORT).show()
        } catch (e: Exception) {
            Toast.makeText(this, "Ошибка загрузки: ${e.message}", Toast.LENGTH_LONG).show()
        }
    }

    private fun checkUpdate() {
        Thread {
            try {
                val url = URL("https://raw.githubusercontent.com/elchupacabr/studapp/refs/heads/main/latest_version.txt")
                val c = url.openConnection() as HttpURLConnection
                val latest = BufferedReader(InputStreamReader(c.inputStream)).readLine().trim()
                c.disconnect()

                if (BuildConfig.VERSION_NAME != latest) {
                    runOnUiThread {
                        val prefs = getSharedPreferences("update_prefs", MODE_PRIVATE)
                        val postponedVersion = prefs.getString("postponed_version", "")

                        // Если пользователь уже откладывал эту версию, не показываем снова
                        if (postponedVersion == latest) return@runOnUiThread

                        AlertDialog.Builder(this)
                            .setTitle("Доступно обновление")
                            .setMessage("Доступна новая версия v$latest. Хотите скачать и установить её?")
                            .setPositiveButton("Да") { _, _ -> downloadApk(latest) }
                            .setNeutralButton("Отложить") { _, _ ->
                                // Запоминаем, что пользователь отложил эту версию
                                prefs.edit().putString("postponed_version", latest).apply()
                            }
                            .setNegativeButton("Нет", null)
                            .show()
                    }
                }
            } catch (_: Exception) {}
        }.start()
    }


    private fun downloadApk(version: String) {
        val apkUrl = "https://github.com/elchupacabr/studapp/releases/download/v.$version/app-debug.apk"
        val filename = "studapp_v$version.apk"

        try {
            val req = DownloadManager.Request(Uri.parse(apkUrl))
            req.setTitle("Загрузка обновления")
            req.setDescription("Скачивание версии $version")
            req.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, filename)
            req.setMimeType("application/vnd.android.package-archive")
            req.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)

            val dm = getSystemService(DOWNLOAD_SERVICE) as DownloadManager
            val id = dm.enqueue(req)

            val br = object : BroadcastReceiver() {
                override fun onReceive(context: Context?, intent: Intent?) {
                    val uri = dm.getUriForDownloadedFile(id)
                    val install = Intent(Intent.ACTION_VIEW)
                    install.setDataAndType(uri, "application/vnd.android.package-archive")
                    install.flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_GRANT_READ_URI_PERMISSION
                    startActivity(install)
                    unregisterReceiver(this)
                }
            }

            registerReceiver(br, IntentFilter(DownloadManager.ACTION_DOWNLOAD_COMPLETE))

            Toast.makeText(this, "Началась загрузка обновления", Toast.LENGTH_SHORT).show()
        } catch (e: Exception) {
            Toast.makeText(this, "Ошибка загрузки: ${e.message}", Toast.LENGTH_LONG).show()
        }
    }

    private val PREFS_NOTIF = "notifications_prefs"
    private val KEY_LAST_OBJECT_ID = "last_object_id"

    @RequiresApi(Build.VERSION_CODES.O)
    private fun createNotificationChannels() {
        val nm = getSystemService(NotificationManager::class.java)

        val mailChannel = NotificationChannel(
            CHANNEL_MAIL,
            "📬 Почта",
            NotificationManager.IMPORTANCE_DEFAULT
        ).apply {
            description = "Уведомления о новых письмах"
        }

        val feedChannel = NotificationChannel(
            CHANNEL_FEED,
            "📰 Лента",
            NotificationManager.IMPORTANCE_DEFAULT
        ).apply {
            description = "Уведомления из ленты событий"
        }

        nm.createNotificationChannel(mailChannel)
        nm.createNotificationChannel(feedChannel)
    }

    @RequiresApi(Build.VERSION_CODES.M)
    private fun checkNotifications() {
        Thread {
            try {
                val authPrefs = getSharedPreferences("auth", MODE_PRIVATE)
                val cookies = authPrefs.getString("cookies", null) ?: ""

                val feedUrl = "https://stud.sssu.ru/api/Feed?userID=-83263"
                val mailUrl = "https://stud.sssu.ru/api/Mail/CheckMail"

                // --- Лента ---
                val feedConnection = URL(feedUrl).openConnection() as HttpURLConnection
                feedConnection.setRequestProperty("Cookie", cookies)
                feedConnection.setRequestProperty("User-Agent", "Mozilla/5.0")
                feedConnection.connectTimeout = 5000
                feedConnection.readTimeout = 5000

                val feedResponse = feedConnection.inputStream.bufferedReader().use { it.readText() }
                feedConnection.disconnect()

                val feedJson = org.json.JSONObject(feedResponse)
                val feedData = feedJson.getJSONObject("data")
                val feedArray = feedData.getJSONArray("feed")
                val lastNotificationId = getSharedPreferences("notifications", MODE_PRIVATE)
                    .getInt("last_notification_id", 0)

                for (i in 0 until feedArray.length()) {
                    val item = feedArray.getJSONObject(i)
                    val notificationID = item.getInt("notificationID")
                    val isNew = item.optBoolean("isNew", false)

                    if (notificationID > lastNotificationId && isNew) {
                        val text = item.optString("text", null)
                        val html = item.optString("html", null)
                        val message = text ?: html ?: "Новое уведомление"
                        showNotification(
                            CHANNEL_FEED,
                            "\uD83D\uDCF0 Лента",
                            message,
                            "https://stud.sssu.ru/WebApp/#/Feed"
                        )


                        // Сохраняем последний ID
                        getSharedPreferences("notifications", MODE_PRIVATE)
                            .edit().putInt("last_notification_id", notificationID).apply()
                    }
                }

                // --- Почта ---
                val mailConnection = URL(mailUrl).openConnection() as HttpURLConnection
                mailConnection.setRequestProperty("Cookie", cookies)
                mailConnection.setRequestProperty("User-Agent", "Mozilla/5.0")
                mailConnection.connectTimeout = 5000
                mailConnection.readTimeout = 5000

                val mailResponse = mailConnection.inputStream.bufferedReader().use { it.readText() }
                mailConnection.disconnect()

                val mailJson = org.json.JSONObject(mailResponse)
                val mailData = mailJson.getJSONObject("data")
                val messageIDs = mailData.getJSONArray("messagesIDs")
                val mailCount = mailData.getInt("count")

                if (mailCount > 0) {
                    showNotification(
                        CHANNEL_MAIL,
                        "\uD83D\uDCEC Почта",
                        "У вас $mailCount новых сообщений",
                        "https://stud.sssu.ru/WebApp/#/mail/all"
                    )

                }

            } catch (e: Exception) {
                e.printStackTrace()
            }
        }.start()
    }

    @RequiresApi(Build.VERSION_CODES.M)
    private fun showNotification(
        channelId: String,
        title: String,
        message: String,
        url: String
    ) {
        val intent = Intent(this, MainActivity::class.java).apply {
            putExtra("open_url", url)
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }

        val pendingIntent = PendingIntent.getActivity(
            this,
            (System.currentTimeMillis() % Int.MAX_VALUE).toInt(),
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notification = NotificationCompat.Builder(this, channelId)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(title)
            .setContentText(message)
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .build()

        val nm = getSystemService(NotificationManager::class.java)
        nm.notify(Random().nextInt(), notification)
    }



    override fun onKeyDown(keyCode: Int, event: KeyEvent): Boolean {
        if (keyCode == KeyEvent.KEYCODE_BACK) {
            val mainHost = Uri.parse(defaultURL).host
            val currentHost = Uri.parse(mWebView.url ?: "").host

            // Если находимся на стороннем сайте — возвращаем на основной
            if (currentHost != null && mainHost != null && currentHost != mainHost) {
                mWebView.loadUrl(defaultURL)
                return true
            }

            // Если можно идти назад в истории WebView — идём назад
            if (mWebView.canGoBack()) {
                mWebView.goBack()
                return true
            }

            // Двойное нажатие для выхода
            if (doubleBackToExitPressedOnce) return super.onKeyDown(keyCode, event)
            doubleBackToExitPressedOnce = true
            Toast.makeText(this, "Нажмите ещё раз, чтобы выйти", Toast.LENGTH_SHORT).show()
            Handler(Looper.getMainLooper()).postDelayed({ doubleBackToExitPressedOnce = false }, 500)
            return true
        }
        return super.onKeyDown(keyCode, event)
    }


    companion object {
        fun internetCheck(context: Context): Boolean {
            val cm = context.getSystemService(CONNECTIVITY_SERVICE) as ConnectivityManager
            val net = cm.allNetworkInfo
            return net?.any { it.state == NetworkInfo.State.CONNECTED } ?: false
        }

        private const val CHANNEL_FEED = "stud_feed"
        private const val CHANNEL_MAIL = "stud_mail"
    }
}