from dataclasses import dataclass
import tkinter as tk
from tkinter import ttk


@dataclass
class ThemePalette:
    name: str
    bg: str
    bg_alt: str
    panel: str
    panel_alt: str
    glass: str
    glass_edge: str
    glow: str
    text: str
    subtext: str
    primary: str
    primary_active: str
    border: str
    danger: str
    success: str
    input_bg: str
    input_fg: str


LIGHT_THEME = ThemePalette(
    name="浅色",
    bg="#F1F4F9",
    bg_alt="#E5ECF6",
    panel="#FCFDFF",
    panel_alt="#F5F8FD",
    glass="#F9FBFF",
    glass_edge="#D2DCEA",
    glow="#EAF0F9",
    text="#1E293B",
    subtext="#607086",
    primary="#3D7BEB",
    primary_active="#2D67D2",
    border="#D9E1EC",
    danger="#EF4444",
    success="#10B981",
    input_bg="#FDFEFF",
    input_fg="#111827",
)


DARK_THEME = ThemePalette(
    name="深色",
    bg="#0C1119",
    bg_alt="#141D2A",
    panel="#111A28",
    panel_alt="#192435",
    glass="#162236",
    glass_edge="#2C3D56",
    glow="#1A263A",
    text="#E5EEFF",
    subtext="#94A7C6",
    primary="#6FA1F5",
    primary_active="#5A8FE8",
    border="#324764",
    danger="#F87171",
    success="#34D399",
    input_bg="#0E1930",
    input_fg="#EAF2FF",
)


class ThemeController:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.style = ttk.Style(root)
        self.style.theme_use("clam")
        self.palette = LIGHT_THEME
        self.apply(self.palette)

    def apply(self, palette: ThemePalette) -> None:
        self.palette = palette
        self.root.configure(bg=palette.bg)
        self.style.configure("App.TFrame", background=palette.bg)
        self.style.configure("Card.TFrame", background=palette.glass, borderwidth=0)
        self.style.configure("CardAlt.TFrame", background=palette.panel_alt, borderwidth=0)
        self.style.configure("Title.TLabel", background=palette.bg, foreground=palette.text, font=("Segoe UI", 16, "bold"))
        self.style.configure("SubTitle.TLabel", background=palette.bg, foreground=palette.subtext, font=("Segoe UI", 9))
        self.style.configure("Label.TLabel", background=palette.glass, foreground=palette.text, font=("Segoe UI", 9))
        self.style.configure("Hint.TLabel", background=palette.glass, foreground=palette.subtext, font=("Segoe UI", 9))
        self.style.configure("Input.TEntry", fieldbackground=palette.input_bg, foreground=palette.input_fg, bordercolor=palette.border, lightcolor=palette.border, darkcolor=palette.border, insertcolor=palette.input_fg)
        self.style.configure("Primary.TButton", background=palette.primary, foreground="#FFFFFF", borderwidth=0, focusthickness=0, font=("Segoe UI", 9, "bold"), padding=(12, 8))
        self.style.map("Primary.TButton", background=[("active", palette.primary_active), ("pressed", palette.primary_active)])
        self.style.configure("Ghost.TButton", background=palette.panel_alt, foreground=palette.text, bordercolor=palette.border, lightcolor=palette.border, darkcolor=palette.border, font=("Segoe UI", 9), padding=(12, 8))
        self.style.map("Ghost.TButton", background=[("active", palette.panel), ("pressed", palette.panel)])
        self.style.configure("Danger.TButton", background=palette.danger, foreground="#FFFFFF", borderwidth=0, font=("Segoe UI", 9, "bold"), padding=(12, 8))
        self.style.map("Danger.TButton", background=[("active", palette.danger), ("pressed", palette.danger)])
        self.style.configure("Switch.TCheckbutton", background=palette.panel, foreground=palette.text, font=("Segoe UI", 10))
        self.style.map("Switch.TCheckbutton", foreground=[("active", palette.text)])
        self.style.configure("Theme.TCombobox", fieldbackground=palette.input_bg, foreground=palette.input_fg, background=palette.input_bg, arrowcolor=palette.subtext, bordercolor=palette.border)
        self.style.configure("TNotebook", background=palette.glass, borderwidth=0, tabmargins=(0, 0, 0, 0))
        self.style.configure("TNotebook.Tab", background=palette.panel_alt, foreground=palette.subtext, padding=(12, 6), font=("Segoe UI", 9))
        self.style.map("TNotebook.Tab", background=[("selected", palette.glass)], foreground=[("selected", palette.text)])


class Card(tk.Frame):
    def __init__(self, master: tk.Misc, palette: ThemePalette, title: str, subtitle: str = "") -> None:
        super().__init__(master, bg=palette.bg, highlightthickness=0)
        self.palette = palette
        self.glow = tk.Frame(self, bg=palette.glow, highlightthickness=0)
        self.glow.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.panel = tk.Frame(self.glow, bg=palette.glass, highlightthickness=1, highlightbackground=palette.glass_edge, highlightcolor=palette.glass_edge)
        self.panel.pack(fill=tk.BOTH, expand=True)
        self.header = tk.Frame(self.panel, bg=palette.glass)
        self.header.pack(fill=tk.X, padx=14, pady=(12, 6))
        self.title_label = tk.Label(self.header, text=title, bg=palette.glass, fg=palette.text, font=("Segoe UI", 12, "bold"), anchor="w")
        self.title_label.pack(fill=tk.X)
        self.subtitle_label = tk.Label(self.header, text=subtitle, bg=palette.glass, fg=palette.subtext, font=("Segoe UI", 9), anchor="w")
        if subtitle:
            self.subtitle_label.pack(fill=tk.X, pady=(2, 0))
        self.body = tk.Frame(self.panel, bg=palette.glass)
        self.body.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 12))

    def apply_palette(self, palette: ThemePalette) -> None:
        self.palette = palette
        self.configure(bg=palette.bg)
        self.glow.configure(bg=palette.glow)
        self.panel.configure(bg=palette.glass, highlightbackground=palette.glass_edge, highlightcolor=palette.glass_edge)
        self.header.configure(bg=palette.glass)
        self.body.configure(bg=palette.glass)
        self.title_label.configure(bg=palette.glass, fg=palette.text)
        self.subtitle_label.configure(bg=palette.glass, fg=palette.subtext)


class StatusBadge(tk.Frame):
    def __init__(self, master: tk.Misc, palette: ThemePalette, text: str, ok: bool = True) -> None:
        color = palette.success if ok else palette.danger
        bg = palette.glass
        super().__init__(master, bg=bg)
        self.dot = tk.Canvas(self, width=10, height=10, bg=bg, bd=0, highlightthickness=0)
        self.dot.create_oval(1, 1, 9, 9, fill=color, outline=color)
        self.dot.pack(side=tk.LEFT, padx=(0, 8))
        self.label = tk.Label(self, text=text, bg=bg, fg=palette.text, font=("Segoe UI", 10, "bold"))
        self.label.pack(side=tk.LEFT)

    def update(self, palette: ThemePalette, text: str, ok: bool) -> None:
        color = palette.success if ok else palette.danger
        self.configure(bg=palette.glass)
        self.dot.configure(bg=palette.glass)
        self.dot.delete("all")
        self.dot.create_oval(1, 1, 9, 9, fill=color, outline=color)
        self.label.configure(text=text, bg=palette.glass, fg=palette.text)
