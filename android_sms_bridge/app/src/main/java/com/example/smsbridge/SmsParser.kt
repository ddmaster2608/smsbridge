package com.example.smsbridge

object SmsParser {
    private val codeRegex = Regex("(?<!\\d)(\\d{4,8})(?!\\d)")
    private val contextRegex = Regex("(验证码|校验码|动态码|otp|code)", RegexOption.IGNORE_CASE)

    fun extractCode(smsText: String): String? {
        val matches = codeRegex.findAll(smsText).toList()
        if (matches.isEmpty()) return null

        val prioritized = matches.firstOrNull { match ->
            val start = (match.range.first - 12).coerceAtLeast(0)
            val end = (match.range.last + 12).coerceAtMost(smsText.lastIndex)
            val snippet = smsText.substring(start, end + 1)
            contextRegex.containsMatchIn(snippet)
        }

        return prioritized?.groupValues?.get(1) ?: matches.first().groupValues[1]
    }
}
