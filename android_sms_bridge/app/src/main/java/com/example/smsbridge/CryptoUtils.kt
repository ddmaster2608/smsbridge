package com.example.smsbridge

import android.util.Base64
import org.json.JSONObject
import java.security.MessageDigest
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

object CryptoUtils {
    private const val TRANSFORMATION = "AES/GCM/NoPadding"
    private const val AAD_TEXT = "smsbridge-v1"

    fun encryptPayload(plainPayload: JSONObject, keyText: String): JSONObject {
        val nonce = ByteArray(12)
        SecureRandom().nextBytes(nonce)
        val keyBytes = MessageDigest.getInstance("SHA-256").digest(keyText.toByteArray(Charsets.UTF_8))
        val cipher = Cipher.getInstance(TRANSFORMATION)
        val keySpec = SecretKeySpec(keyBytes, "AES")
        val gcmSpec = GCMParameterSpec(128, nonce)
        cipher.init(Cipher.ENCRYPT_MODE, keySpec, gcmSpec)
        cipher.updateAAD(AAD_TEXT.toByteArray(Charsets.UTF_8))
        val encrypted = cipher.doFinal(plainPayload.toString().toByteArray(Charsets.UTF_8))
        return JSONObject().apply {
            put("enc", "aes-gcm")
            put("nonce", Base64.encodeToString(nonce, Base64.NO_WRAP))
            put("ciphertext", Base64.encodeToString(encrypted, Base64.NO_WRAP))
        }
    }
}
