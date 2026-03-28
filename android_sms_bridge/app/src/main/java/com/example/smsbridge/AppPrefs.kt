package com.example.smsbridge

import android.content.Context

object AppPrefs {
    private const val PREFS = "sms_bridge_prefs"
    private const val KEY_SERVER_URL = "server_url"
    private const val KEY_TOKEN = "token"
    private const val KEY_AES_KEY = "aes_key"
    private const val KEY_UDP_PORT = "udp_port"
    private const val KEY_DIRECT_ENABLED = "direct_enabled"
    private const val KEY_BROADCAST_ENABLED = "broadcast_enabled"
    private const val KEY_SEND_MODE = "send_mode"
    private const val KEY_ENABLED = "enabled"
    const val MODE_DIRECT = "direct"
    const val MODE_BROADCAST = "broadcast"

    fun getServerUrl(context: Context): String {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_SERVER_URL, "") ?: ""
    }

    fun setServerUrl(context: Context, value: String) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_SERVER_URL, value)
            .apply()
    }

    fun getToken(context: Context): String {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_TOKEN, "") ?: ""
    }

    fun setToken(context: Context, value: String) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_TOKEN, value)
            .apply()
    }

    fun getAesKey(context: Context): String {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_AES_KEY, "") ?: ""
    }

    fun setAesKey(context: Context, value: String) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_AES_KEY, value)
            .apply()
    }

    fun getUdpPort(context: Context): Int {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getInt(KEY_UDP_PORT, 19527)
    }

    fun setUdpPort(context: Context, value: Int) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putInt(KEY_UDP_PORT, value)
            .apply()
    }

    fun isDirectEnabled(context: Context): Boolean {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getBoolean(KEY_DIRECT_ENABLED, true)
    }

    fun setDirectEnabled(context: Context, value: Boolean) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(KEY_DIRECT_ENABLED, value)
            .apply()
    }

    fun isBroadcastEnabled(context: Context): Boolean {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getBoolean(KEY_BROADCAST_ENABLED, false)
    }

    fun setBroadcastEnabled(context: Context, value: Boolean) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(KEY_BROADCAST_ENABLED, value)
            .apply()
    }

    fun getSendMode(context: Context): String {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val mode = prefs.getString(KEY_SEND_MODE, null)
        if (mode == MODE_DIRECT || mode == MODE_BROADCAST) {
            return mode
        }
        return if (isBroadcastEnabled(context) && !isDirectEnabled(context)) MODE_BROADCAST else MODE_DIRECT
    }

    fun setSendMode(context: Context, mode: String) {
        val target = if (mode == MODE_BROADCAST) MODE_BROADCAST else MODE_DIRECT
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_SEND_MODE, target)
            .putBoolean(KEY_DIRECT_ENABLED, target == MODE_DIRECT)
            .putBoolean(KEY_BROADCAST_ENABLED, target == MODE_BROADCAST)
            .apply()
    }

    fun isEnabled(context: Context): Boolean {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getBoolean(KEY_ENABLED, false)
    }

    fun setEnabled(context: Context, value: Boolean) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(KEY_ENABLED, value)
            .apply()
    }
}
