package ai.beanie.app

import android.Manifest
import android.annotation.SuppressLint
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.inputmethod.EditorInfo
import android.webkit.PermissionRequest
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.EditText
import android.widget.ImageButton
import android.widget.LinearLayout
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

/**
 * Beanie's Android companion (see android_app/README.md, ARCHITECTURE §11.7):
 * a full-screen WebView pointed at the WebUI of the PC running Beanie, with a
 * persistent host setting and runtime microphone permission for the page's
 * speech-recognition button.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var web: WebView
    private lateinit var hostField: EditText

    private val prefs by lazy { getSharedPreferences("beanie", MODE_PRIVATE) }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        hostField = EditText(this).apply {
            hint = "PC host, e.g. 192.168.1.20:8080"
            setText(prefs.getString("host", "") ?: "")
            inputType = EditorInfo.TYPE_CLASS_TEXT
            imeOptions = EditorInfo.IME_ACTION_GO
            setSingleLine()
        }
        val connect = ImageButton(this).apply { setImageResource(android.R.drawable.ic_menu_send) }
        val bar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            addView(hostField, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            addView(connect, LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT)
        }
        web = WebView(this)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(bar, LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
            addView(web, LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f)
        }
        setContentView(root)

        web.settings.javaScriptEnabled = true          // the WebUI is a JS page
        web.settings.mediaPlaybackRequiresUserGesture = false
        web.settings.domStorageEnabled = true
        web.webViewClient = WebViewClient()
        web.webChromeClient = object : WebChromeClient() {
            override fun onPermissionRequest(request: PermissionRequest) {
                // Speech recognition inside the page: grant once the runtime mic
                // permission exists — the same flow Chrome uses (see README).
                runOnUiThread {
                    if (hasMicPermission()) request.grant(request.resources)
                    else request.deny()
                }
            }
        }

        connect.setOnClickListener { openUrl() }
        hostField.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_GO) { openUrl(); true } else false
        }

        ensureMicPermission()
        savedInstanceState?.getString("url")?.let { web.loadUrl(it) } ?: openUrl()
    }

    private fun hasMicPermission(): Boolean =
        ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) ==
            PackageManager.PERMISSION_GRANTED

    private fun ensureMicPermission() {
        if (Build.VERSION.SDK_INT >= 23 && !hasMicPermission()) {
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.RECORD_AUDIO), 7)
        }
    }

    private fun openUrl() {
        val host = hostField.text.toString().trim()
        if (host.isEmpty()) return
        prefs.edit().putString("host", host).apply()
        web.loadUrl(if (host.startsWith("http")) host else "http://$host")
    }

    override fun onBackPressed() {
        if (this::web.isInitialized && web.canGoBack()) web.goBack() else super.onBackPressed()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        if (this::web.isInitialized) outState.putString("url", web.url)
    }
}
