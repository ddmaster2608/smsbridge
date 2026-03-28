package com.example.smsbridge

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import org.json.JSONObject
import java.io.OutputStreamWriter
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.HttpURLConnection
import java.net.InetAddress
import java.net.URL
import kotlin.concurrent.thread

class SmsForwardService : Service() {
    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        createChannel()
        startForeground(NOTIFICATION_ID, buildForegroundNotification())
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
            return START_NOT_STICKY
        }

        val smsText = intent?.getStringExtra(EXTRA_SMS_TEXT)
        if (!smsText.isNullOrBlank()) {
            thread {
                forwardSms(smsText)
            }
        }
        return START_STICKY
    }

    private fun forwardSms(smsText: String) {
        val serverUrl = AppPrefs.getServerUrl(this).trim()
        val sendMode = AppPrefs.getSendMode(this)
        val directEnabled = sendMode == AppPrefs.MODE_DIRECT
        val broadcastEnabled = sendMode == AppPrefs.MODE_BROADCAST

        val aesKey = AppPrefs.getAesKey(this).trim()
        if (aesKey.isBlank()) return
        if (directEnabled && serverUrl.isBlank()) return

        val token = AppPrefs.getToken(this).trim()
        val udpPort = AppPrefs.getUdpPort(this)
        val code = SmsParser.extractCode(smsText)
        val plainPayload = JSONObject().apply {
            put("text", smsText)
            if (token.isNotBlank()) put("token", token)
            if (!code.isNullOrBlank()) put("codeHint", code)
        }

        val transportPayload = CryptoUtils.encryptPayload(plainPayload, aesKey).toString()

        if (directEnabled && serverUrl.isNotBlank()) {
            sendHttp(serverUrl, token, transportPayload)
        }
        if (broadcastEnabled) {
            sendUdpBroadcast(udpPort, transportPayload)
        }
    }

    private fun sendHttp(serverUrl: String, token: String, payload: String) {
        val connection = (URL(serverUrl).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 5000
            readTimeout = 5000
            doOutput = true
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
            if (token.isNotBlank()) setRequestProperty("X-Token", token)
        }
        try {
            OutputStreamWriter(connection.outputStream, Charsets.UTF_8).use {
                it.write(payload)
                it.flush()
            }
            connection.responseCode
        } catch (_: Exception) {
        } finally {
            connection.disconnect()
        }
    }

    private fun sendUdpBroadcast(port: Int, payload: String) {
        var socket: DatagramSocket? = null
        try {
            val data = payload.toByteArray(Charsets.UTF_8)
            val address = InetAddress.getByName("255.255.255.255")
            val packet = DatagramPacket(data, data.size, address, port)
            socket = DatagramSocket().apply {
                broadcast = true
            }
            socket.send(packet)
        } catch (_: Exception) {
        } finally {
            socket?.close()
        }
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val channel = NotificationChannel(
            CHANNEL_ID,
            getString(R.string.notif_channel_name),
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            description = getString(R.string.notif_channel_desc)
        }
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.createNotificationChannel(channel)
    }

    private fun buildForegroundNotification(): Notification {
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_notify_sync)
            .setContentTitle(getString(R.string.notif_running_title))
            .setContentText(getString(R.string.notif_running_text))
            .setOngoing(true)
            .build()
    }

    companion object {
        const val CHANNEL_ID = "sms_forward_channel"
        const val NOTIFICATION_ID = 1011
        const val EXTRA_SMS_TEXT = "extra_sms_text"
        const val ACTION_STOP = "action_stop"

        fun start(context: Context) {
            val intent = Intent(context, SmsForwardService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun stop(context: Context) {
            val intent = Intent(context, SmsForwardService::class.java).apply {
                action = ACTION_STOP
            }
            context.startService(intent)
        }

        fun enqueueSms(context: Context, smsText: String) {
            val intent = Intent(context, SmsForwardService::class.java).apply {
                putExtra(EXTRA_SMS_TEXT, smsText)
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }
    }
}
