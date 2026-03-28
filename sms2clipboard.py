import argparse
import base64
import hashlib
import html
import json
import logging
import re
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

try:
    from win11toast import toast as win11_toast
except Exception:
    win11_toast = None


CODE_PATTERN = re.compile(r"(?<!\d)(\d{4,8})(?!\d)")
PREFERRED_CONTEXT = re.compile(r"(验证码|校验码|动态码|otp|code)", re.IGNORECASE)
PROVIDER_PATTERNS = {
    "阿里系": re.compile(r"(淘宝|天猫|支付宝|阿里)", re.IGNORECASE),
    "腾讯系": re.compile(r"(微信|腾讯|QQ|财付通)", re.IGNORECASE),
    "字节系": re.compile(r"(抖音|今日头条|字节)", re.IGNORECASE),
    "京东": re.compile(r"(京东|JD)", re.IGNORECASE),
    "美团": re.compile(r"(美团|点评)", re.IGNORECASE),
    "银行金融": re.compile(r"(银行|信用卡|支付|转账|贷款|证券)", re.IGNORECASE),
    "运营商": re.compile(r"(中国移动|中国联通|中国电信|运营商)", re.IGNORECASE),
}
TYPE_PATTERNS = {
    "支付确认码": re.compile(r"(支付|付款|转账|扣款|交易)", re.IGNORECASE),
    "注册验证码": re.compile(r"(注册|开户|激活)", re.IGNORECASE),
    "重置验证码": re.compile(r"(重置|找回|修改密码|安全验证)", re.IGNORECASE),
    "登录验证码": re.compile(r"(登录|验证码|校验码|动态码|otp|code)", re.IGNORECASE),
}


def extract_sms_text(payload: object) -> str:
    if isinstance(payload, str):
        return payload.strip()
    if not isinstance(payload, dict):
        return ""

    for key in ("sms", "body", "content", "message", "text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def extract_code(sms_text: str) -> Optional[str]:
    matches = list(CODE_PATTERN.finditer(sms_text))
    if not matches:
        return None

    prioritized = []
    for m in matches:
        start = max(0, m.start() - 12)
        end = min(len(sms_text), m.end() + 12)
        chunk = sms_text[start:end]
        if PREFERRED_CONTEXT.search(chunk):
            prioritized.append(m.group(1))
    if prioritized:
        return prioritized[0]
    return matches[0].group(1)


def classify_sms(sms_text: str) -> tuple[str, str]:
    sms_type = "其他验证码"
    provider = "未识别服务商"
    for type_name, pattern in TYPE_PATTERNS.items():
        if pattern.search(sms_text):
            sms_type = type_name
            break
    for provider_name, pattern in PROVIDER_PATTERNS.items():
        if pattern.search(sms_text):
            provider = provider_name
            break
    return sms_type, provider


def emit_sms_event(sms_text: str, code: str, copied: bool, status: str) -> None:
    sms_type, provider = classify_sms(sms_text)
    event = {
        "event": "sms_code",
        "time": int(time.time()),
        "provider": provider,
        "type": sms_type,
        "code": code,
        "copied": copied,
        "status": status,
    }
    logging.info("SMS_EVENT %s", json.dumps(event, ensure_ascii=False))


def copy_to_clipboard(text: str) -> bool:
    cmd = [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        "Set-Clipboard -Value @'\n" + text + "\n'@",
    ]
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
        return completed.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def notify_popup(title: str, body: str) -> None:
    if win11_toast is not None:
        try:
            win11_toast(title, body, duration="short")
            return
        except Exception as ex:
            logging.warning("win11toast 通知失败: %s", ex)

    xml_title = html.escape(title)
    xml_body = html.escape(body)
    xml_payload = (
        "<toast>"
        "<visual>"
        "<binding template='ToastGeneric'>"
        f"<text>{xml_title}</text>"
        f"<text>{xml_body}</text>"
        "</binding>"
        "</visual>"
        "</toast>"
    )
    safe_xml = xml_payload.replace("'", "''")
    toast_script_base = (
        "$ErrorActionPreference='Stop'; "
        "[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime] > $null; "
        "[Windows.Data.Xml.Dom.XmlDocument,Windows.Data.Xml.Dom.XmlDocument,ContentType=WindowsRuntime] > $null; "
        f"$xml='{safe_xml}'; "
        "$doc=New-Object Windows.Data.Xml.Dom.XmlDocument; "
        "$doc.LoadXml($xml); "
        "$toast=[Windows.UI.Notifications.ToastNotification]::new($doc); "
    )
    script = toast_script_base + "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Microsoft.Windows.Explorer').Show($toast)"
    startup_info = subprocess.STARTUPINFO()
    startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup_info.wShowWindow = 0
    create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    detached = getattr(subprocess, "DETACHED_PROCESS", 0)
    cmd = [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-WindowStyle",
        "Hidden",
        "-Command",
        script,
    ]
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=8,
            startupinfo=startup_info,
            creationflags=(create_no_window | detached),
        )
    except (subprocess.SubprocessError, OSError):
        logging.warning("通知发送失败: %s", title)
        return
    if completed.returncode == 0:
        return
    stderr = (completed.stderr or "").strip()
    if stderr:
        logging.warning("通知尝试失败: %s", stderr[:300])
    logging.warning("通知发送失败: %s", title)


def derive_key_bytes(key_text: str) -> bytes:
    return hashlib.sha256(key_text.encode("utf-8")).digest()


def decrypt_encrypted_payload(payload: dict[str, Any], aes_key: str) -> Optional[dict[str, Any]]:
    if not aes_key:
        return None
    if payload.get("enc") != "aes-gcm":
        return None
    nonce_b64 = payload.get("nonce")
    cipher_b64 = payload.get("ciphertext")
    if not isinstance(nonce_b64, str) or not isinstance(cipher_b64, str):
        return None
    try:
        nonce = base64.b64decode(nonce_b64)
        ciphertext = base64.b64decode(cipher_b64)
        aesgcm = AESGCM(derive_key_bytes(aes_key))
        plaintext = aesgcm.decrypt(nonce, ciphertext, b"smsbridge-v1")
        decoded = json.loads(plaintext.decode("utf-8"))
        if isinstance(decoded, dict):
            return decoded
    except Exception:
        return None
    return None


def parse_sms_payload(payload: object, aes_key: str) -> tuple[str, str, str]:
    if isinstance(payload, str):
        if aes_key:
            return "", "", "encrypted_payload_required"
        return payload.strip(), "", ""
    if not isinstance(payload, dict):
        return "", "", "invalid_payload"

    decrypted = decrypt_encrypted_payload(payload, aes_key)
    if isinstance(decrypted, dict):
        sms_text = extract_sms_text(decrypted)
        token = decrypted.get("token", "")
        if not isinstance(token, str):
            token = ""
        return sms_text, token.strip(), ""

    if aes_key:
        return "", "", "invalid_encrypted_payload"

    sms_text = extract_sms_text(payload)
    token = payload.get("token", "")
    if not isinstance(token, str):
        token = ""
    return sms_text, token.strip(), ""


def process_sms_text(sms_text: str) -> tuple[int, dict[str, Any]]:
    if not sms_text:
        return 400, {"ok": False, "error": "sms_text_required"}

    code = extract_code(sms_text)
    if not code:
        notify_popup("短信已收到", "未识别到验证码，请手动查看")
        return 200, {"ok": True, "copied": False, "reason": "code_not_found"}

    copied = copy_to_clipboard(code)
    if copied:
        emit_sms_event(sms_text, code, True, "copied")
        notify_popup("验证码已复制", f"{code}（右键粘贴即可）")
        return 200, {"ok": True, "copied": True, "code": code}

    emit_sms_event(sms_text, code, False, "clipboard_failed")
    notify_popup("验证码识别成功", f"{code}（复制失败，请手动复制）")
    return 500, {"ok": False, "copied": False, "code": code, "error": "clipboard_failed"}


def create_http_server(host: str, port: int, token: str, aes_key: str) -> ThreadingHTTPServer:
    SMSHandler.token = token
    SMSHandler.aes_key = aes_key
    return ThreadingHTTPServer((host, port), SMSHandler)


class SMSHandler(BaseHTTPRequestHandler):
    token: str = ""
    aes_key: str = ""

    def _send_json(self, code: int, payload: dict) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def do_GET(self) -> None:
        if self.path.startswith("/health"):
            self._send_json(200, {"ok": True})
            return
        self._send_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/sms":
            self._send_json(404, {"ok": False, "error": "not_found"})
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length).decode("utf-8", errors="ignore")
        content_type = self.headers.get("Content-Type", "")
        sms_text = ""
        payload_token = ""
        parse_error = ""

        if "application/json" in content_type:
            try:
                payload = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                self._send_json(400, {"ok": False, "error": "invalid_json"})
                return
            sms_text, payload_token, parse_error = parse_sms_payload(payload, self.aes_key)
        else:
            if self.aes_key:
                self._send_json(400, {"ok": False, "error": "encrypted_payload_required"})
                return
            sms_text = raw.strip()
        if parse_error:
            self._send_json(400, {"ok": False, "error": parse_error})
            return

        query = parse_qs(parsed.query)
        query_token = (query.get("token") or [""])[0]
        header_token = self.headers.get("X-Token", "")
        final_token = (header_token or query_token or payload_token).strip()
        if self.token and final_token != self.token:
            self._send_json(401, {"ok": False, "error": "invalid_token"})
            return

        code, resp = process_sms_text(sms_text)
        self._send_json(code, resp)

    def log_message(self, fmt: str, *args: object) -> None:
        logging.info("%s - %s", self.address_string(), fmt % args)


def run_udp_broadcast_listener(
    host: str,
    port: int,
    token: str,
    aes_key: str,
    stop_event: Optional[threading.Event] = None,
) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.settimeout(0.8)
    logging.info("UDP 广播监听已启动: %s:%s", host, port)

    while True:
        if stop_event and stop_event.is_set():
            break
        try:
            packet, addr = sock.recvfrom(65535)
            raw = packet.decode("utf-8", errors="ignore")
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = raw

            sms_text, payload_token, parse_error = parse_sms_payload(payload, aes_key)
            if parse_error:
                logging.warning("UDP payload 非法: %s %s", addr, parse_error)
                continue
            final_token = payload_token.strip()
            if token and final_token != token:
                logging.warning("UDP token 校验失败: %s", addr)
                continue

            status, resp = process_sms_text(sms_text)
            if status >= 400:
                logging.warning("UDP 消息处理失败: %s %s", addr, resp)
            else:
                logging.info("UDP 消息处理成功: %s", addr)
        except socket.timeout:
            continue
        except Exception as ex:
            logging.error("UDP 监听异常: %s", ex)
    try:
        sock.close()
    except OSError:
        pass


class SmsBridgeServer:
    def __init__(
        self,
        host: str,
        port: int,
        token: str,
        aes_key: str,
        enable_udp_broadcast: bool,
        udp_port: int,
    ) -> None:
        self.host = host
        self.port = port
        self.token = token
        self.aes_key = aes_key
        self.enable_udp_broadcast = enable_udp_broadcast
        self.udp_port = udp_port
        self.http_server: Optional[ThreadingHTTPServer] = None
        self.http_thread: Optional[threading.Thread] = None
        self.udp_thread: Optional[threading.Thread] = None
        self.udp_stop_event: Optional[threading.Event] = None

    def start(self) -> None:
        if self.http_server is not None:
            raise RuntimeError("server_already_running")
        self.http_server = create_http_server(self.host, self.port, self.token, self.aes_key)
        self.http_thread = threading.Thread(target=self.http_server.serve_forever, daemon=True)
        self.http_thread.start()
        logging.info("服务已启动: http://%s:%s", self.host, self.port)
        logging.info("接收地址: POST /sms?token=你的token")
        if self.enable_udp_broadcast:
            self.udp_stop_event = threading.Event()
            self.udp_thread = threading.Thread(
                target=run_udp_broadcast_listener,
                args=(self.host, self.udp_port, self.token, self.aes_key, self.udp_stop_event),
                daemon=True,
            )
            self.udp_thread.start()
            logging.info("广播接收: UDP %s:%s", self.host, self.udp_port)

    def stop(self) -> None:
        if self.udp_stop_event:
            self.udp_stop_event.set()
        if self.http_server:
            self.http_server.shutdown()
            self.http_server.server_close()
        if self.http_thread and self.http_thread.is_alive():
            self.http_thread.join(timeout=2)
        if self.udp_thread and self.udp_thread.is_alive():
            self.udp_thread.join(timeout=2)
        self.http_server = None
        self.http_thread = None
        self.udp_thread = None
        self.udp_stop_event = None


def main() -> None:
    parser = argparse.ArgumentParser(description="短信验证码转发到电脑剪贴板")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9527)
    parser.add_argument("--enable-udp-broadcast", action="store_true")
    parser.add_argument("--udp-port", type=int, default=19527)
    parser.add_argument("--token", default="", help="可选安全令牌，建议设置")
    parser.add_argument("--aes-key", default="", help="加密密钥（与安卓端一致）")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    bridge = SmsBridgeServer(
        host=args.host,
        port=args.port,
        token=args.token,
        aes_key=args.aes_key,
        enable_udp_broadcast=args.enable_udp_broadcast,
        udp_port=args.udp_port,
    )
    bridge.start()
    try:
        while True:
            threading.Event().wait(3600)
    except KeyboardInterrupt:
        bridge.stop()


if __name__ == "__main__":
    main()
