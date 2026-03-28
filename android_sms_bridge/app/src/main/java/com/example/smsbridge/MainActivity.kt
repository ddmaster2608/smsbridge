package com.example.smsbridge

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

class MainActivity : AppCompatActivity() {
    private lateinit var etServerUrl: EditText
    private lateinit var etToken: EditText
    private lateinit var etAesKey: EditText
    private lateinit var etUdpPort: EditText
    private lateinit var rgSendMode: RadioGroup
    private lateinit var rbDirect: RadioButton
    private lateinit var rbBroadcast: RadioButton
    private lateinit var tvModeHint: TextView
    private lateinit var tvState: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        etServerUrl = findViewById(R.id.etServerUrl)
        etToken = findViewById(R.id.etToken)
        etAesKey = findViewById(R.id.etAesKey)
        etUdpPort = findViewById(R.id.etUdpPort)
        rgSendMode = findViewById(R.id.rgSendMode)
        rbDirect = findViewById(R.id.rbDirect)
        rbBroadcast = findViewById(R.id.rbBroadcast)
        tvModeHint = findViewById(R.id.tvModeHint)
        tvState = findViewById(R.id.tvState)
        val btnSave: Button = findViewById(R.id.btnSave)
        val btnStart: Button = findViewById(R.id.btnStart)
        val btnStop: Button = findViewById(R.id.btnStop)

        etServerUrl.setText(AppPrefs.getServerUrl(this))
        etToken.setText(AppPrefs.getToken(this))
        etAesKey.setText(AppPrefs.getAesKey(this))
        etUdpPort.setText(AppPrefs.getUdpPort(this).toString())
        val mode = AppPrefs.getSendMode(this)
        if (mode == AppPrefs.MODE_BROADCAST) rbBroadcast.isChecked = true else rbDirect.isChecked = true
        applyModeUi(mode)
        updateState(AppPrefs.isEnabled(this))
        requestPermissionsIfNeeded()

        rgSendMode.setOnCheckedChangeListener { _, checkedId ->
            if (checkedId == R.id.rbBroadcast) {
                applyModeUi(AppPrefs.MODE_BROADCAST)
            } else {
                applyModeUi(AppPrefs.MODE_DIRECT)
            }
        }

        btnSave.setOnClickListener {
            val url = etServerUrl.text?.toString()?.trim().orEmpty()
            val token = etToken.text?.toString()?.trim().orEmpty()
            val aesKey = etAesKey.text?.toString()?.trim().orEmpty()
            val mode = if (rbBroadcast.isChecked) AppPrefs.MODE_BROADCAST else AppPrefs.MODE_DIRECT
            val udpPortText = etUdpPort.text?.toString()?.trim().orEmpty()
            val udpPort = udpPortText.toIntOrNull() ?: -1
            if (mode == AppPrefs.MODE_DIRECT && (!url.startsWith("http://") && !url.startsWith("https://"))) {
                Toast.makeText(this, "定向模式下请填写有效的电脑接收地址", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            if (udpPort !in 1..65535) {
                Toast.makeText(this, "广播端口范围应为 1~65535", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            if (aesKey.isBlank()) {
                Toast.makeText(this, "请填写 AES 密钥", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            AppPrefs.setServerUrl(this, if (mode == AppPrefs.MODE_DIRECT) url else "")
            AppPrefs.setToken(this, token)
            AppPrefs.setAesKey(this, aesKey)
            AppPrefs.setUdpPort(this, udpPort)
            AppPrefs.setSendMode(this, mode)
            Toast.makeText(this, "配置已保存", Toast.LENGTH_SHORT).show()
        }

        btnStart.setOnClickListener {
            if (!hasSmsPermission()) {
                requestPermissionsIfNeeded()
                Toast.makeText(this, "请先授予短信权限", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            try {
                AppPrefs.setEnabled(this, true)
                SmsForwardService.start(this)
                updateState(true)
            } catch (e: Exception) {
                AppPrefs.setEnabled(this, false)
                updateState(false)
                Toast.makeText(this, "启动失败：${e.message ?: "请检查权限与系统设置"}", Toast.LENGTH_LONG).show()
            }
        }

        btnStop.setOnClickListener {
            try {
                AppPrefs.setEnabled(this, false)
                SmsForwardService.stop(this)
                updateState(false)
            } catch (e: Exception) {
                Toast.makeText(this, "停止失败：${e.message ?: "请稍后重试"}", Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun updateState(enabled: Boolean) {
        tvState.text = if (enabled) getString(R.string.forwarding_on) else getString(R.string.forwarding_off)
    }

    private fun applyModeUi(mode: String) {
        val direct = mode == AppPrefs.MODE_DIRECT
        etServerUrl.isEnabled = direct
        etServerUrl.alpha = if (direct) 1f else 0.45f
        tvModeHint.text = if (direct) getString(R.string.mode_hint_direct) else getString(R.string.mode_hint_broadcast)
    }

    private fun hasSmsPermission(): Boolean {
        val receive = ContextCompat.checkSelfPermission(
            this,
            Manifest.permission.RECEIVE_SMS
        ) == PackageManager.PERMISSION_GRANTED
        val read = ContextCompat.checkSelfPermission(
            this,
            Manifest.permission.READ_SMS
        ) == PackageManager.PERMISSION_GRANTED
        return receive && read
    }

    private fun requestPermissionsIfNeeded() {
        val permissions = mutableListOf(
            Manifest.permission.RECEIVE_SMS,
            Manifest.permission.READ_SMS
        )
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            permissions += Manifest.permission.POST_NOTIFICATIONS
        }
        val missing = permissions.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, missing.toTypedArray(), 1001)
        }
    }
}
