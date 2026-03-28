import json
import logging
import queue
import threading
from collections import defaultdict
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

import pystray
from PIL import Image, ImageDraw

from sms2clipboard import SmsBridgeServer
from sms_ui_components import Card, DARK_THEME, LIGHT_THEME, StatusBadge, ThemeController


APP_DIR = Path.home() / "AppData" / "Roaming" / "SMSBridge"
CONFIG_PATH = APP_DIR / "config.json"


def load_config() -> dict:
    default = {
        "host": "0.0.0.0",
        "port": 9527,
        "enable_udp_broadcast": True,
        "udp_port": 19527,
        "token": "",
        "aes_key": "",
        "theme": "浅色",
    }
    if not CONFIG_PATH.exists():
        return default
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {
                "host": str(data.get("host", default["host"])),
                "port": int(data.get("port", default["port"])),
                "enable_udp_broadcast": bool(data.get("enable_udp_broadcast", default["enable_udp_broadcast"])),
                "udp_port": int(data.get("udp_port", default["udp_port"])),
                "token": str(data.get("token", default["token"])),
                "aes_key": str(data.get("aes_key", default["aes_key"])),
                "theme": str(data.get("theme", default["theme"])),
            }
    except Exception:
        pass
    return default


def save_config(config: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


class TextQueueHandler(logging.Handler):
    def __init__(self, log_queue: "queue.Queue[str]") -> None:
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record: logging.LogRecord) -> None:
        self.log_queue.put(self.format(record))


class SmsBridgeDesktopApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("SMS Bridge")
        self.root.geometry("900x610")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close_window)

        self.server: SmsBridgeServer | None = None
        self.tray_icon: pystray.Icon | None = None
        self.tray_thread: threading.Thread | None = None
        self.exiting = False
        self.provider_stats: dict[str, int] = defaultdict(int)
        self.type_stats: dict[str, int] = defaultdict(int)
        self.event_count = 0
        self.last_code = "--"
        self.last_provider = "未识别服务商"
        self.last_type = "登录验证码"

        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self._init_logging()
        self.theme_controller = ThemeController(self.root)

        cfg = load_config()
        self.host_var = tk.StringVar(value=cfg["host"])
        self.port_var = tk.StringVar(value=str(cfg["port"]))
        self.udp_enabled_var = tk.BooleanVar(value=cfg["enable_udp_broadcast"])
        self.udp_port_var = tk.StringVar(value=str(cfg["udp_port"]))
        self.token_var = tk.StringVar(value=cfg["token"])
        self.aes_key_var = tk.StringVar(value=cfg["aes_key"])
        self.theme_var = tk.StringVar(value=cfg["theme"] if cfg["theme"] in ("浅色", "深色") else "浅色")
        self.state_var = tk.StringVar(value="准备就绪")

        self._build_ui()
        self._apply_theme(self.theme_var.get(), animate=False)
        self._start_log_poller()
        self._ensure_tray()

    def _init_logging(self) -> None:
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        queue_handler = TextQueueHandler(self.log_queue)
        queue_handler.setFormatter(formatter)
        logger.handlers = [queue_handler]

    def _build_ui(self) -> None:
        self.main = ttk.Frame(self.root, style="App.TFrame", padding=10)
        self.main.pack(fill=tk.BOTH, expand=True)
        self.main.columnconfigure(0, weight=3)
        self.main.columnconfigure(1, weight=2)
        self.main.rowconfigure(1, weight=1)
        self.main.rowconfigure(2, weight=0)

        header_card = Card(self.main, LIGHT_THEME, "SMS Bridge", "短信验证码转发服务")
        self.status_card = header_card
        header_card.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        header_card.body.columnconfigure(0, weight=1)
        top_left = tk.Frame(header_card.body, bg=LIGHT_THEME.glass)
        top_left.grid(row=0, column=0, sticky="w")
        self.status_badge = StatusBadge(top_left, LIGHT_THEME, "未运行", ok=False)
        self.status_badge.pack(side=tk.LEFT)
        self.status_text = tk.Label(top_left, textvariable=self.state_var, bg=LIGHT_THEME.glass, fg=LIGHT_THEME.subtext, font=("Segoe UI", 9))
        self.status_text.pack(side=tk.LEFT, padx=(8, 8))
        self.addr_badge = tk.Label(top_left, text="0.0.0.0:9527", bg=LIGHT_THEME.panel_alt, fg=LIGHT_THEME.primary, font=("Segoe UI", 10, "bold"), padx=12, pady=4)
        self.addr_badge.pack(side=tk.LEFT, padx=(10, 8))
        self.udp_badge = tk.Label(top_left, text="UDP 开启", bg=LIGHT_THEME.panel_alt, fg=LIGHT_THEME.primary, font=("Segoe UI", 10, "bold"), padx=12, pady=4)
        self.udp_badge.pack(side=tk.LEFT)

        toolbar = ttk.Frame(header_card.body, style="Card.TFrame")
        toolbar.grid(row=0, column=1, sticky="e")
        ttk.Button(toolbar, text="保存", style="Ghost.TButton", command=self.save_settings).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(toolbar, text="重启", style="Primary.TButton", command=self.start_service).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(toolbar, text="停止", style="Danger.TButton", command=self.stop_service).pack(side=tk.LEFT, padx=(0, 6))
        self.tray_btn = ttk.Button(toolbar, text="托盘", style="Ghost.TButton", command=self.hide_to_tray)
        self.tray_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.theme_box = ttk.Combobox(toolbar, textvariable=self.theme_var, values=["浅色", "深色"], state="readonly", width=6, style="Theme.TCombobox")
        self.theme_box.pack(side=tk.LEFT)
        self.theme_box.bind("<<ComboboxSelected>>", lambda _: self._on_theme_change())

        self.net_card = Card(self.main, LIGHT_THEME, "连接配置", "监听、安全与广播设置")
        self.net_card.grid(row=1, column=0, rowspan=2, sticky="nsew", padx=(0, 6))
        self._build_form(self.net_card.body)

        self.insight_card = Card(self.main, LIGHT_THEME, "运行概览", "状态、统计与最近消息")
        self.insight_card.grid(row=1, column=1, sticky="nsew", padx=(6, 0), pady=(0, 6))
        self._build_collection(self.insight_card.body)

        self.action_card = Card(self.main, LIGHT_THEME, "快速操作", "")
        self.action_card.grid(row=2, column=1, sticky="ew", padx=(6, 0))
        self._build_actions(self.action_card.body)

    def _build_form(self, parent: tk.Frame) -> None:
        parent.columnconfigure(1, weight=1)
        tk.Label(parent, text="监听地址", font=("Segoe UI", 10, "bold"), anchor="w").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.host_entry = ttk.Entry(parent, textvariable=self.host_var, style="Input.TEntry")
        self.host_entry.grid(row=0, column=1, sticky="ew", pady=(0, 6), padx=(8, 0))

        tk.Label(parent, text="HTTP 端口", font=("Segoe UI", 10, "bold"), anchor="w").grid(row=1, column=0, sticky="w", pady=6)
        self.port_entry = ttk.Entry(parent, textvariable=self.port_var, style="Input.TEntry")
        self.port_entry.grid(row=1, column=1, sticky="ew", pady=6, padx=(8, 0))

        tk.Label(parent, text="安全 Token", font=("Segoe UI", 10, "bold"), anchor="w").grid(row=2, column=0, sticky="w", pady=6)
        self.token_entry = ttk.Entry(parent, textvariable=self.token_var, style="Input.TEntry")
        self.token_entry.grid(row=2, column=1, sticky="ew", pady=6, padx=(8, 0))

        tk.Label(parent, text="AES 密钥", font=("Segoe UI", 10, "bold"), anchor="w").grid(row=3, column=0, sticky="w", pady=6)
        self.aes_entry = ttk.Entry(parent, textvariable=self.aes_key_var, style="Input.TEntry", show="●")
        self.aes_entry.grid(row=3, column=1, sticky="ew", pady=6, padx=(8, 0))

        self.udp_check = ttk.Checkbutton(parent, text="启用局域网 UDP 广播接收", variable=self.udp_enabled_var, style="Switch.TCheckbutton")
        self.udp_check.grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 4))

        tk.Label(parent, text="UDP 端口", font=("Segoe UI", 10, "bold"), anchor="w").grid(row=5, column=0, sticky="w", pady=(2, 0))
        self.udp_entry = ttk.Entry(parent, textvariable=self.udp_port_var, style="Input.TEntry")
        self.udp_entry.grid(row=5, column=1, sticky="ew", pady=(2, 0), padx=(8, 0))

    def _build_actions(self, parent: tk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)
        ttk.Button(parent, text="启动", style="Primary.TButton", command=self.start_service).grid(row=0, column=0, sticky="ew", pady=(0, 6), padx=(0, 4))
        ttk.Button(parent, text="停止", style="Danger.TButton", command=self.stop_service).grid(row=0, column=1, sticky="ew", pady=(0, 6), padx=(4, 0))
        ttk.Button(parent, text="保存", style="Ghost.TButton", command=self.save_settings).grid(row=1, column=0, sticky="ew", pady=(0, 6), padx=(0, 4))
        ttk.Button(parent, text="重启", style="Ghost.TButton", command=self.start_service).grid(row=1, column=1, sticky="ew", pady=(0, 6), padx=(4, 0))
        self.quick_theme_btn = ttk.Button(parent, text="主题", style="Ghost.TButton", command=self._toggle_theme)
        self.quick_theme_btn.grid(row=2, column=0, sticky="ew", padx=(0, 4))
        self.quick_hide_btn = ttk.Button(parent, text="托盘", style="Ghost.TButton", command=self.hide_to_tray)
        self.quick_hide_btn.grid(row=2, column=1, sticky="ew", padx=(4, 0))

    def _build_collection(self, parent: tk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)

        self.total_event_label = tk.Label(parent, text="累计验证码", font=("Segoe UI", 10))
        self.total_event_label.grid(row=0, column=0, sticky="w")
        self.total_event_value = tk.Label(parent, text="0", font=("Segoe UI", 24, "bold"))
        self.total_event_value.grid(row=1, column=0, sticky="w", pady=(0, 6))

        self.today_label = tk.Label(parent, text="今日接收", font=("Segoe UI", 10))
        self.today_label.grid(row=0, column=1, sticky="w")
        self.today_value = tk.Label(parent, text="0", font=("Segoe UI", 24, "bold"))
        self.today_value.grid(row=1, column=1, sticky="w", pady=(0, 6))

        self.last_code_title = tk.Label(parent, text="最近验证码", font=("Segoe UI", 10))
        self.last_code_title.grid(row=2, column=0, sticky="w", pady=(2, 0))
        self.last_code_value = tk.Label(parent, text="--", font=("Segoe UI", 26, "bold"))
        self.last_code_value.grid(row=3, column=0, columnspan=2, sticky="w")

        self.last_meta_value = tk.Label(parent, text="服务商：未识别服务商  |  类型：登录验证码", font=("Segoe UI", 9))
        self.last_meta_value.grid(row=4, column=0, columnspan=2, sticky="w", pady=(1, 4))

        self.provider_title = tk.Label(parent, text="服务商 TOP3", font=("Segoe UI", 10))
        self.provider_title.grid(row=5, column=0, sticky="w")
        self.provider_list = tk.Listbox(parent, height=2, bd=0, highlightthickness=1)
        self.provider_list.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(2, 0))

        self.collection_widgets = [
            self.total_event_label,
            self.total_event_value,
            self.today_label,
            self.today_value,
            self.last_code_title,
            self.last_code_value,
            self.last_meta_value,
            self.provider_title,
            self.provider_list,
        ]

    def _set_entries_palette(self) -> None:
        palette = self.theme_controller.palette
        self.status_text.configure(bg=palette.glass, fg=palette.subtext)
        self.addr_badge.configure(bg=palette.panel_alt, fg=palette.primary)
        self.udp_badge.configure(bg=palette.panel_alt, fg=palette.primary)
        text_labels = []
        for child in self.net_card.body.winfo_children():
            if isinstance(child, tk.Label):
                text_labels.append(child)
        for label in text_labels:
            label.configure(bg=palette.glass, fg=palette.text)
        for widget in self.collection_widgets:
            if isinstance(widget, tk.Label):
                widget.configure(bg=palette.glass, fg=palette.text if widget not in (self.last_meta_value,) else palette.subtext)
        self.provider_list.configure(
            bg=palette.panel_alt,
            fg=palette.text,
            highlightbackground=palette.glass_edge,
            highlightcolor=palette.glass_edge,
            selectbackground=palette.primary,
            selectforeground="#FFFFFF",
        )

    def _apply_theme(self, theme_name: str, animate: bool = True) -> None:
        palette = DARK_THEME if theme_name == "深色" else LIGHT_THEME
        self.theme_controller.apply(palette)
        self.status_card.apply_palette(palette)
        self.net_card.apply_palette(palette)
        self.action_card.apply_palette(palette)
        self.insight_card.apply_palette(palette)
        self.status_badge.update(palette, self.status_badge.label.cget("text"), self.server is not None)
        self._set_entries_palette()
        if animate:
            self._pulse_card(self.status_card)

    def _pulse_card(self, card: Card) -> None:
        palette = self.theme_controller.palette
        start = palette.primary
        end = palette.glass_edge
        steps = 8
        rgbs = []
        for idx in range(steps):
            p = idx / (steps - 1)
            sr = int(start[1:3], 16)
            sg = int(start[3:5], 16)
            sb = int(start[5:7], 16)
            er = int(end[1:3], 16)
            eg = int(end[3:5], 16)
            eb = int(end[5:7], 16)
            nr = int(sr + (er - sr) * p)
            ng = int(sg + (eg - sg) * p)
            nb = int(sb + (eb - sb) * p)
            rgbs.append(f"#{nr:02x}{ng:02x}{nb:02x}")
        seq = rgbs + list(reversed(rgbs))
        def animate(i: int = 0) -> None:
            if i >= len(seq):
                card.panel.configure(highlightbackground=palette.glass_edge, highlightcolor=palette.glass_edge)
                return
            card.panel.configure(highlightbackground=seq[i], highlightcolor=seq[i])
            self.root.after(36, lambda: animate(i + 1))
        animate()

    def _on_theme_change(self) -> None:
        self._apply_theme(self.theme_var.get())
        cfg = self._safe_read_settings()
        if cfg:
            save_config(cfg)

    def _toggle_theme(self) -> None:
        self.theme_var.set("深色" if self.theme_var.get() == "浅色" else "浅色")
        self._on_theme_change()

    def _start_log_poller(self) -> None:
        def poll() -> None:
            while True:
                try:
                    line = self.log_queue.get_nowait()
                except queue.Empty:
                    break
                self._parse_sms_event(line)
            self.root.after(160, poll)
        poll()

    def _parse_sms_event(self, line: str) -> None:
        if "SMS_EVENT " not in line:
            return
        payload = line.split("SMS_EVENT ", 1)[1].strip()
        try:
            event = json.loads(payload)
        except Exception:
            return
        if not isinstance(event, dict):
            return
        provider = str(event.get("provider", "未识别服务商"))
        sms_type = str(event.get("type", "其他验证码"))
        code = str(event.get("code", ""))
        self.provider_stats[provider] += 1
        self.type_stats[sms_type] += 1
        self.event_count += 1
        self.last_code = code or "--"
        self.last_provider = provider
        self.last_type = sms_type
        self.total_event_value.configure(text=str(self.event_count))
        self.today_value.configure(text=str(self.event_count))
        self.last_code_value.configure(text=self.last_code)
        self.last_meta_value.configure(text=f"服务商：{self.last_provider}  |  类型：{self.last_type}")
        self._refresh_collection_lists()

    def _refresh_collection_lists(self) -> None:
        self.provider_list.delete(0, tk.END)
        for key, count in sorted(self.provider_stats.items(), key=lambda kv: kv[1], reverse=True)[:3]:
            self.provider_list.insert(tk.END, f"{key}  ·  {count}")

    def _ensure_tray(self) -> None:
        if self.tray_icon is not None:
            return
        image = self._create_tray_image()
        self.tray_icon = pystray.Icon(
            "smsbridge",
            image,
            "SMS Bridge",
            menu=pystray.Menu(
                pystray.MenuItem("显示窗口", self._tray_show),
                pystray.MenuItem("启动服务", self._tray_start),
                pystray.MenuItem("停止服务", self._tray_stop),
                pystray.MenuItem("切换主题", self._tray_toggle_theme),
                pystray.MenuItem("退出程序", self._tray_exit),
            ),
        )
        self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        self.tray_thread.start()

    def _create_tray_image(self) -> Image.Image:
        image = Image.new("RGBA", (64, 64), (15, 24, 42, 255))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((7, 7, 57, 57), radius=12, fill=(49, 130, 246, 255))
        draw.rounded_rectangle((16, 17, 48, 46), radius=6, fill=(255, 255, 255, 235))
        draw.rectangle((22, 24, 42, 28), fill=(49, 130, 246, 255))
        draw.rectangle((22, 34, 35, 37), fill=(49, 130, 246, 255))
        return image

    def _tray_show(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        self.root.after(0, self.show_window)

    def _tray_start(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        self.root.after(0, self.start_service)

    def _tray_stop(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        self.root.after(0, self.stop_service)

    def _tray_toggle_theme(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        self.root.after(0, self._toggle_theme)

    def _tray_exit(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        self.root.after(0, self.exit_app)

    def _safe_read_settings(self) -> dict | None:
        try:
            return self.read_settings()
        except ValueError:
            return None

    def read_settings(self) -> dict:
        host = self.host_var.get().strip() or "0.0.0.0"
        token = self.token_var.get().strip()
        aes_key = self.aes_key_var.get().strip()
        try:
            port = int(self.port_var.get().strip())
            udp_port = int(self.udp_port_var.get().strip())
        except ValueError:
            raise ValueError("端口必须是数字")
        if port < 1 or port > 65535 or udp_port < 1 or udp_port > 65535:
            raise ValueError("端口范围必须是 1-65535")
        if not aes_key:
            raise ValueError("AES 密钥不能为空")
        return {
            "host": host,
            "port": port,
            "enable_udp_broadcast": self.udp_enabled_var.get(),
            "udp_port": udp_port,
            "token": token,
            "aes_key": aes_key,
            "theme": self.theme_var.get(),
        }

    def _set_state(self, text: str, ok: bool) -> None:
        self.state_var.set(text)
        self.status_badge.update(self.theme_controller.palette, "运行中" if ok else "未运行", ok)
        self.addr_badge.configure(text=f"{self.host_var.get().strip() or '0.0.0.0'}:{self.port_var.get().strip() or '9527'}")
        self.udp_badge.configure(text="UDP 开启" if self.udp_enabled_var.get() else "UDP 关闭")
        self._pulse_card(self.status_card)

    def save_settings(self) -> None:
        try:
            cfg = self.read_settings()
        except ValueError as ex:
            messagebox.showerror("配置错误", str(ex))
            return
        save_config(cfg)
        self._set_state("配置已保存", self.server is not None)

    def start_service(self) -> None:
        if self.server is not None:
            self._set_state("服务已在运行", True)
            return
        try:
            cfg = self.read_settings()
        except ValueError as ex:
            messagebox.showerror("配置错误", str(ex))
            return
        save_config(cfg)
        try:
            self.server = SmsBridgeServer(
                host=cfg["host"],
                port=cfg["port"],
                token=cfg["token"],
                aes_key=cfg["aes_key"],
                enable_udp_broadcast=cfg["enable_udp_broadcast"],
                udp_port=cfg["udp_port"],
            )
            self.server.start()
            self._set_state("服务运行中，已开始监听短信", True)
        except Exception as ex:
            self.server = None
            messagebox.showerror("启动失败", str(ex))
            self._set_state("启动失败", False)

    def stop_service(self) -> None:
        if self.server is None:
            self._set_state("服务未运行", False)
            return
        try:
            self.server.stop()
        finally:
            self.server = None
        self._set_state("服务已停止", False)

    def hide_to_tray(self) -> None:
        self.root.withdraw()
        self._set_state("窗口已隐藏到系统托盘", self.server is not None)

    def show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def on_close_window(self) -> None:
        self.hide_to_tray()

    def exit_app(self) -> None:
        if self.exiting:
            return
        self.exiting = True
        try:
            self.stop_service()
        except Exception:
            pass
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    app = SmsBridgeDesktopApp()
    app.run()


if __name__ == "__main__":
    main()
