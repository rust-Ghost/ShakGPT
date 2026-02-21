"""
cyber_client.py — SHAKGPT Client

Upgrades in this version:
  • Music: exact pygame pattern from old server's play_audio()
      – intro.mp3 plays first, then background.mp3 is queued to loop forever
      – Falls back to any single music.* file if named files not found
      – Pre-initialised at 44100 Hz / 16-bit stereo / buffer 512 (from testing.py)
  • Mute button (🔊 / 🔇) in the top bar — toggles without losing volume state
  • Volume slider (0–100%) in the top bar
  • Big-screen / fullscreen: launches maximised, sidebar wider, message text
      wraps to actual window width, fonts scale up slightly
  • Animated welcome screen, live clock, AI thinking spinner — all preserved
"""

import socket, struct, json, ssl, threading, os, time
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, scrolledtext

# ═════════════════════════════════════════════════════════════════
#  Pygame — pre-initialise BEFORE init() exactly as in testing.py
# ═════════════════════════════════════════════════════════════════
try:
    import pygame
    pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=512)
    pygame.mixer.init()
    PYGAME_OK = True
except Exception:
    PYGAME_OK = False

HOST = "127.0.0.1"
PORT = 9921

# ── Music file search ──────────────────────────────────────────────
_SEARCH_DIRS = [
    os.path.dirname(os.path.abspath(__file__)),
    os.getcwd(),
]

def _find(name):
    for d in _SEARCH_DIRS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return None

def _find_any(*names):
    for name in names:
        p = _find(name)
        if p:
            return p
    return None


# ═════════════════════════════════════════════════════════════════
#  Colour palette
# ═════════════════════════════════════════════════════════════════
C = {
    "bg":           "#FFFFFF",
    "sidebar":      "#F9FAFB",
    "panel":        "#F3F4F6",
    "border":       "#E5E7EB",
    "text":         "#111827",
    "text_dim":     "#6B7280",
    "text_light":   "#9CA3AF",
    "accent":       "#10A37F",
    "accent_hover": "#0D8A6B",
    "user_bubble":  "#F3F4F6",
    "ai_bubble":    "#FFFFFF",
    "danger":       "#EF4444",
}


# ═════════════════════════════════════════════════════════════════
#  Network helpers
# ═════════════════════════════════════════════════════════════════
def _send(s, obj):
    d = json.dumps(obj).encode()
    s.sendall(struct.pack(">I", len(d)) + d)

def _recv(s):
    h = s.recv(4)
    if len(h) < 4:
        return None
    n = struct.unpack(">I", h)[0]
    d = b""
    while len(d) < n:
        p = s.recv(n - len(d))
        if not p:
            return None
        d += p
    return json.loads(d.decode())


# ═════════════════════════════════════════════════════════════════
#  Model help texts
# ═════════════════════════════════════════════════════════════════
MODEL_HELP = {
    "tinyllama": ("TinyLlama — Fast General Chat",
        "Quick responses for everyday questions:\n"
        "• General knowledge and trivia\n"
        "• Simple explanations\n"
        "• Creative writing prompts\n\n"
        "Try: 'Explain quantum physics simply'"),
    "mistral-7b": ("Mistral 7B — High Quality",
        "Better reasoning and detailed answers:\n"
        "• In-depth analysis\n"
        "• Complex problem solving\n"
        "• Professional writing\n\n"
        "Try: 'Write a business proposal outline'"),
    "phi2": ("Phi-2 — Reasoning & Code",
        "Strong at logic and programming:\n"
        "• Step-by-step solutions\n"
        "• Math and science\n"
        "• Code generation\n\n"
        "Try: 'Write a Python binary search'"),
}


# ═════════════════════════════════════════════════════════════════
#  Animated Welcome Canvas
# ═════════════════════════════════════════════════════════════════
class WelcomeCanvas(tk.Canvas):
    ACCENT   = "#10A37F"
    ACCENT2  = "#0EA5E9"
    BG_TOP   = "#0D1117"
    N_PARTICLES = 14
    ORBIT_R     = 120

    def __init__(self, master, on_start):
        super().__init__(master, bg=self.BG_TOP, highlightthickness=0, bd=0)
        self._on_start  = on_start
        self._alive     = True
        self._t         = 0.0

        import math, random
        self._particles = []
        for i in range(self.N_PARTICLES):
            angle  = (2 * math.pi / self.N_PARTICLES) * i
            speed  = random.uniform(0.35, 0.85)
            r      = self.ORBIT_R + random.uniform(-30, 30)
            colour = self.ACCENT if i % 2 == 0 else self.ACCENT2
            size   = random.uniform(3, 7)
            self._particles.append([angle, speed, r, colour, size])

        self._part_ids = []
        self._logo_id  = None
        self._title_id = None
        self._sub_id   = None
        self._clock_id = None
        self._built    = False

        self.bind("<Configure>", self._on_resize)
        self._draw_frame()

    def _on_resize(self, _e=None):
        if not self._built:
            self._built = True
            self._build_static()

    def _build_static(self):
        w, h = self.winfo_width(), self.winfo_height()
        cx, cy = w // 2, h // 2

        for i in range(50):
            ratio = i / 50
            r = int(0x0D + (0x0A - 0x0D) * ratio)
            g = int(0x11 + (0x16 - 0x11) * ratio)
            b = int(0x17 + (0x28 - 0x17) * ratio)
            y0, y1 = h * i // 50, h * (i + 1) // 50
            self.create_rectangle(0, y0, w, y1, fill=f"#{r:02x}{g:02x}{b:02x}", outline="")

        self.create_oval(cx - self.ORBIT_R, cy - self.ORBIT_R,
                         cx + self.ORBIT_R, cy + self.ORBIT_R,
                         outline="#1F2937", width=1, dash=(4, 6))

        self._logo_id  = self.create_text(cx, cy, text="🌸", font=("Segoe UI", 80))
        self._title_id = self.create_text(cx, cy + 130, text="SHAKGPT",
                                           fill="#E5E7EB", font=("Segoe UI", 42, "bold"))
        self._sub_id   = self.create_text(cx, cy + 182,
                                           text="Your private AI assistant",
                                           fill="#6B7280", font=("Segoe UI", 14))
        self._clock_id = self.create_text(w - 18, h - 14, text="",
                                           fill="#374151", font=("Segoe UI", 10),
                                           anchor="se")
        for _ in self._particles:
            self._part_ids.append(
                self.create_oval(0, 0, 1, 1, fill=self.ACCENT, outline=""))

        self.after(900, self._add_button)

    def _add_button(self):
        if not self._alive:
            return
        w, h = self.winfo_width(), self.winfo_height()
        btn = tk.Button(self, text="Get Started →", command=self._start,
                        bg=self.ACCENT, fg="white",
                        font=("Segoe UI", 14, "bold"),
                        relief="flat", cursor="hand2",
                        bd=0, padx=36, pady=14,
                        activebackground=C["accent_hover"],
                        activeforeground="white")
        self.create_window(w // 2, h // 2 + 250, window=btn)

    def _start(self):
        self._alive = False
        self._on_start()

    def _draw_frame(self):
        if not self._alive:
            return
        import math
        try:
            w, h = self.winfo_width(), self.winfo_height()
            if w < 10 or h < 10:
                self.after(30, self._draw_frame)
                return
            cx, cy = w // 2, h // 2
        except Exception:
            return

        self._t += 0.033

        if self._logo_id:
            sz = int(80 + 5 * math.sin(self._t * 1.5))
            self.itemconfigure(self._logo_id, font=("Segoe UI", sz))

        for i, (angle, speed, r, colour, size) in enumerate(self._particles):
            self._particles[i][0] += speed * 0.022
            a  = self._particles[i][0]
            px = cx + r * math.cos(a)
            py = cy + 0.55 * r * math.sin(a)
            s2 = size + 1.5 * math.sin(self._t * 2 + i)
            if i < len(self._part_ids):
                self.coords(self._part_ids[i], px - s2, py - s2, px + s2, py + s2)
                self.itemconfigure(self._part_ids[i], fill=colour)

        if self._sub_id:
            v = int(107 + 20 * math.sin(self._t * 0.8))
            self.itemconfigure(self._sub_id, fill=f"#{v:02x}{v:02x}{v:02x}")

        if self._clock_id:
            self.itemconfigure(self._clock_id,
                               text=time.strftime("  %H:%M:%S   %a %d %b %Y  "))
            try:
                self.coords(self._clock_id, w - 18, h - 14)
            except Exception:
                pass

        self.after(33, self._draw_frame)

    def destroy_anim(self):
        self._alive = False


# ═════════════════════════════════════════════════════════════════
#  Thinking Indicator
# ═════════════════════════════════════════════════════════════════
class ThinkingIndicator(tk.Frame):
    SPINNER = ["◐", "◓", "◑", "◒"]

    def __init__(self, master, **kw):
        super().__init__(master, bg=C["ai_bubble"], **kw)
        self._alive  = False
        self._t0     = 0.0
        self._spin_i = 0
        self._lbl    = tk.Label(self, bg=C["ai_bubble"], fg=C["accent"],
                                font=("Segoe UI", 12))
        self._lbl.pack(anchor="w", padx=20, pady=10)

    def start(self):
        self._alive  = True
        self._t0     = time.time()
        self._spin_i = 0
        self._tick()

    def stop(self):
        self._alive = False
        try:
            self.pack_forget()
        except Exception:
            pass

    def _tick(self):
        if not self._alive:
            return
        elapsed      = int(time.time() - self._t0)
        mins, secs   = divmod(elapsed, 60)
        icon         = self.SPINNER[self._spin_i % len(self.SPINNER)]
        self._spin_i += 1
        self._lbl.config(
            text=f"SHAKGPT is thinking…  {icon}  {mins:02d}:{secs:02d}")
        try:
            self.winfo_toplevel().after(250, self._tick)
        except Exception:
            pass


# ═════════════════════════════════════════════════════════════════
#  Main Application
# ═════════════════════════════════════════════════════════════════
class App:
    _MUSIC_VOLUME = 0.35

    def __init__(self, root):
        self.root = root
        self.root.title("SHAKGPT")
        self.root.configure(bg=C["bg"])

        # Launch maximised
        try:
            self.root.state("zoomed")
        except Exception:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            self.root.geometry(f"{sw}x{sh}+0+0")
        self.root.minsize(1024, 660)
        self.root.update_idletasks()

        self.sock               = None
        self.token              = None
        self.display_name       = ""
        self.user_id            = ""
        self.role               = 1
        self.models             = []
        self.chats              = []
        self.current_chat_id    = None
        self.selected_model_idx = 0
        self._thinking          = None
        self._music_muted       = False
        self._mute_btn          = None
        self._vol_var           = None

        self._init_music()
        self._show_welcome()

    # ═══════════════════════════════════════════════════════════
    #  MUSIC  (mirrors old server play_audio() pattern)
    # ═══════════════════════════════════════════════════════════
    def _init_music(self):
        """
        1. Load intro.mp3 → play once (no loop)
        2. Queue background.mp3 → auto-plays when intro ends
        3. After intro finishes, reload background with -1 so it loops forever
        Falls back to any music.* file if intro/background not found.
        """
        if not PYGAME_OK:
            return

        intro_path = _find_any("intro.mp3", "intro.wav", "intro.ogg")
        bg_path    = _find_any("background.mp3", "montana skies.mp3",
                               "music.mp3", "music.wav", "music.ogg")

        if not intro_path and not bg_path:
            return   # no music files found, skip silently

        try:
            if intro_path:
                pygame.mixer.music.load(intro_path)
                pygame.mixer.music.set_volume(self._MUSIC_VOLUME)
                pygame.mixer.music.play()               # play intro once

                if bg_path:
                    pygame.mixer.music.queue(bg_path)   # queue background after intro
                    # Poll until intro ends, then loop background
                    self.root.after(500, lambda: self._loop_bg_when_ready(bg_path))
            else:
                # No intro — loop background directly
                pygame.mixer.music.load(bg_path)
                pygame.mixer.music.set_volume(self._MUSIC_VOLUME)
                pygame.mixer.music.play(-1)
        except Exception as e:
            print(f"[Music] Could not start: {e}")

    def _loop_bg_when_ready(self, bg_path):
        """Poll every 500 ms; once intro ends, reload bg track in loop mode."""
        if not PYGAME_OK:
            return
        try:
            if not pygame.mixer.music.get_busy():
                # Intro has finished → reload bg with -1 loop
                pygame.mixer.music.load(bg_path)
                pygame.mixer.music.set_volume(
                    self._vol_var.get() / 100 if self._vol_var else self._MUSIC_VOLUME)
                pygame.mixer.music.play(-1)
            else:
                self.root.after(500, lambda: self._loop_bg_when_ready(bg_path))
        except Exception:
            pass

    def _toggle_mute(self):
        if not PYGAME_OK:
            return
        self._music_muted = not self._music_muted
        try:
            pygame.mixer.music.set_volume(
                0.0 if self._music_muted
                else (self._vol_var.get() / 100 if self._vol_var else self._MUSIC_VOLUME))
        except Exception:
            pass
        if self._mute_btn:
            self._mute_btn.config(text="🔇" if self._music_muted else "🔊")

    def _on_volume_change(self, _val=None):
        if not PYGAME_OK or not self._vol_var or self._music_muted:
            return
        try:
            pygame.mixer.music.set_volume(self._vol_var.get() / 100)
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════
    #  Network helpers
    # ═══════════════════════════════════════════════════════════
    def _connect(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        ctx.check_hostname = False
        ctx.verify_mode    = ssl.CERT_NONE
        self.sock = ctx.wrap_socket(raw, server_hostname="localhost")
        self.sock.settimeout(10)
        self.sock.connect((HOST, PORT))

    def _cmd(self, obj):
        try:
            _send(self.sock, obj)
            return _recv(self.sock)
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _clear(self):
        for w in self.root.winfo_children():
            w.destroy()

    # ═══════════════════════════════════════════════════════════
    #  WELCOME SCREEN
    # ═══════════════════════════════════════════════════════════
    def _show_welcome(self):
        self._clear()
        self._welcome_canvas = WelcomeCanvas(self.root, on_start=self._show_auth)
        self._welcome_canvas.pack(fill="both", expand=True)

    # ═══════════════════════════════════════════════════════════
    #  AUTH SCREEN
    # ═══════════════════════════════════════════════════════════
    def _show_auth(self):
        if hasattr(self, "_welcome_canvas"):
            self._welcome_canvas.destroy_anim()
        self._clear()

        outer = tk.Frame(self.root, bg=C["bg"])
        outer.pack(fill="both", expand=True)
        card  = tk.Frame(outer, bg=C["sidebar"])
        card.place(relx=0.5, rely=0.5, anchor="center")
        inner = tk.Frame(card, bg=C["sidebar"], padx=56, pady=44)
        inner.pack()

        tk.Label(inner, text="Welcome to SHAKGPT", bg=C["sidebar"], fg=C["text"],
                 font=("Segoe UI", 28, "bold")).pack(pady=(0, 36))

        def field(label, show=None):
            tk.Label(inner, text=label, bg=C["sidebar"], fg=C["text_dim"],
                     font=("Segoe UI", 11)).pack(anchor="w", pady=(0, 4))
            e = tk.Entry(inner, bg="white", fg=C["text"],
                         insertbackground=C["text"],
                         font=("Segoe UI", 12), relief="solid", bd=1,
                         width=34, show=show or "")
            e.pack(pady=(0, 16), ipady=11)
            return e

        self._disp_e = field("Display Name (optional)")
        self._user_e = field("Username")
        self._pass_e = field("Password", show="•")

        btn_row = tk.Frame(inner, bg=C["sidebar"])
        btn_row.pack(pady=(10, 0))
        tk.Button(btn_row, text="Sign In", command=self._do_login,
                  bg=C["accent"], fg="white", font=("Segoe UI", 12, "bold"),
                  relief="flat", cursor="hand2", bd=0,
                  padx=28, pady=12).pack(side="left", padx=(0, 10))
        tk.Button(btn_row, text="Register", command=self._do_register,
                  bg=C["panel"], fg=C["text"], font=("Segoe UI", 12, "bold"),
                  relief="flat", cursor="hand2", bd=0,
                  padx=28, pady=12).pack(side="left")

        self._status_lbl = tk.Label(inner, text="", bg=C["sidebar"],
                                    fg=C["text_dim"], font=("Segoe UI", 10))
        self._status_lbl.pack(pady=(18, 0))
        self._user_e.focus()

    def _set_status(self, msg, col=None):
        if hasattr(self, "_status_lbl"):
            self._status_lbl.config(text=msg, fg=col or C["text_dim"])
            self.root.update_idletasks()

    def _do_login(self):
        u = self._user_e.get().strip()
        p = self._pass_e.get().strip()
        if not u or not p:
            self._set_status("Username and password required", C["danger"]); return
        self._set_status("Connecting…")
        try:
            self._connect()
            r = self._cmd({"command": "login", "username": u, "password": p})
            if r and r.get("status") == "ok":
                self.token        = r["session_token"]
                self.display_name = r.get("display_name", u)
                self.user_id      = r.get("user_id", "")
                self.role         = r.get("role", 1)
                self._post_login()
            else:
                self._set_status(r.get("message", "Login failed"), C["danger"])
        except Exception as e:
            self._set_status(f"Error: {e}", C["danger"])

    def _do_register(self):
        d = self._disp_e.get().strip()
        u = self._user_e.get().strip()
        p = self._pass_e.get().strip()
        if not u or not p:
            self._set_status("Username and password required", C["danger"]); return
        self._set_status("Registering…")
        try:
            self._connect()
            r = self._cmd({"command": "register", "username": u,
                           "password": p, "display_name": d or u})
            if r and r.get("status") == "ok":
                self._set_status("✓ Registered! You can now sign in.", C["accent"])
            else:
                self._set_status(r.get("message", "Failed"), C["danger"])
        except Exception as e:
            self._set_status(f"Error: {e}", C["danger"])

    def _post_login(self):
        r = self._cmd({"command": "get_models"})
        self.models = r.get("models", []) if r else []
        self._fetch_chats()
        self._show_main()

    def _fetch_chats(self):
        r = self._cmd({"command": "get_chats", "session_token": self.token})
        self.chats = r.get("chats", []) if r else []

    # ═══════════════════════════════════════════════════════════
    #  MAIN INTERFACE
    # ═══════════════════════════════════════════════════════════
    def _show_main(self):
        self._clear()
        sw = self.root.winfo_width()

        # ── TOP BAR ─────────────────────────────────────────────
        topbar = tk.Frame(self.root, bg="white", height=64)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)
        tk.Frame(topbar, bg=C["border"], height=1).pack(fill="x", side="bottom")

        tk.Label(topbar, text="🌸  SHAKGPT", bg="white", fg=C["accent"],
                 font=("Segoe UI", 17, "bold")).pack(side="left", padx=24)

        self._topbar_clock = tk.Label(topbar, text="", bg="white",
                                       fg=C["text_light"], font=("Segoe UI", 10))
        self._topbar_clock.pack(side="left", padx=6)
        self._tick_clock()

        if self.role == 2:
            tk.Button(topbar, text="📊 Admin", command=self._show_admin_panel,
                      bg=C["accent"], fg="white", font=("Segoe UI", 11, "bold"),
                      relief="flat", cursor="hand2", bd=0,
                      padx=14, pady=4).pack(side="left", padx=6)

        # Right side: logout, username, volume slider, mute button
        tk.Button(topbar, text="Log out", command=self._logout,
                  bg="white", fg=C["text_dim"], font=("Segoe UI", 11),
                  relief="flat", cursor="hand2", bd=0).pack(side="right", padx=18)

        tk.Label(topbar, text=self.display_name, bg="white", fg=C["text_dim"],
                 font=("Segoe UI", 11)).pack(side="right", padx=6)

        if PYGAME_OK:
            # Volume slider
            self._vol_var = tk.DoubleVar(value=self._MUSIC_VOLUME * 100)
            vol_slider = ttk.Scale(topbar, from_=0, to=100,
                                   orient="horizontal", length=110,
                                   variable=self._vol_var,
                                   command=self._on_volume_change)
            vol_slider.pack(side="right", padx=(0, 4))
            tk.Label(topbar, text="Vol", bg="white", fg=C["text_dim"],
                     font=("Segoe UI", 9)).pack(side="right", padx=(8, 0))

            # Mute button — stores ref so toggle can update the icon
            self._mute_btn = tk.Button(
                topbar, text="🔊", command=self._toggle_mute,
                bg="white", fg=C["text"], font=("Segoe UI", 16),
                relief="flat", cursor="hand2", bd=0, padx=4)
            self._mute_btn.pack(side="right", padx=(8, 2))
        else:
            tk.Label(topbar, text="(no audio — pip install pygame)",
                     bg="white", fg=C["text_light"],
                     font=("Segoe UI", 9)).pack(side="right", padx=10)

        # ── BODY ────────────────────────────────────────────────
        body = tk.Frame(self.root, bg=C["bg"])
        body.pack(fill="both", expand=True)

        # Sidebar — width scales with screen
        sidebar_w = max(280, min(360, sw // 5))
        sidebar = tk.Frame(body, bg=C["sidebar"], width=sidebar_w)
        sidebar.pack(fill="y", side="left")
        sidebar.pack_propagate(False)
        tk.Frame(sidebar, bg=C["border"], width=1).pack(fill="y", side="right")

        sb_top = tk.Frame(sidebar, bg=C["sidebar"])
        sb_top.pack(fill="x", padx=14, pady=14)
        tk.Button(sb_top, text="+ New chat", command=self._new_chat_dialog,
                  bg=C["accent"], fg="white", font=("Segoe UI", 12, "bold"),
                  relief="flat", cursor="hand2", bd=0).pack(fill="x", ipady=10)

        list_canvas = tk.Canvas(sidebar, bg=C["sidebar"], highlightthickness=0)
        list_canvas.pack(fill="both", expand=True, pady=8)
        self._chat_list = tk.Frame(list_canvas, bg=C["sidebar"])
        list_canvas.create_window((0, 0), window=self._chat_list,
                                   anchor="nw", width=sidebar_w - 2)
        self._chat_list.bind("<Configure>", lambda e:
            list_canvas.configure(scrollregion=list_canvas.bbox("all")))
        self._render_sidebar()

        # Chat area
        chat_area = tk.Frame(body, bg=C["bg"])
        chat_area.pack(fill="both", expand=True)

        # Model bar
        mbar = tk.Frame(chat_area, bg=C["panel"], height=52)
        mbar.pack(fill="x")
        mbar.pack_propagate(False)
        tk.Frame(mbar, bg=C["border"], height=1).pack(fill="x", side="bottom")
        tk.Label(mbar, text="Model:", bg=C["panel"], fg=C["text_dim"],
                 font=("Segoe UI", 11)).pack(side="left", padx=(18, 8))
        self._model_var = tk.StringVar()
        names = [m["display_name"] for m in self.models] or ["No models"]
        self._mdl_combo = ttk.Combobox(mbar, textvariable=self._model_var,
                                        values=names, state="readonly",
                                        width=26, font=("Segoe UI", 11))
        self._mdl_combo.pack(side="left", padx=4)
        if names[0] != "No models":
            self._mdl_combo.current(0)
            self._on_model_change()
        self._mdl_combo.bind("<<ComboboxSelected>>", lambda e: self._on_model_change())
        tk.Button(mbar, text="❓ Help", command=self._show_help,
                  bg=C["panel"], fg=C["text_dim"], font=("Segoe UI", 11),
                  relief="flat", cursor="hand2", bd=0).pack(side="left", padx=10)

        # Messages
        msg_outer = tk.Frame(chat_area, bg=C["bg"])
        msg_outer.pack(fill="both", expand=True)
        self._msg_canvas = tk.Canvas(msg_outer, bg=C["bg"], highlightthickness=0)
        self._msg_canvas.pack(fill="both", expand=True, side="left")
        vsb = tk.Scrollbar(msg_outer, command=self._msg_canvas.yview, bg=C["bg"])
        vsb.pack(fill="y", side="right")
        self._msg_canvas.configure(yscrollcommand=vsb.set)
        self._msg_inner = tk.Frame(self._msg_canvas, bg=C["bg"])
        self._msg_canvas.create_window((0, 0), window=self._msg_inner, anchor="nw")
        self._msg_inner.bind("<Configure>", lambda e:
            self._msg_canvas.configure(scrollregion=self._msg_canvas.bbox("all")))
        # Responsive wrap width
        self._msg_canvas.bind("<Configure>", self._on_canvas_resize)
        self._msg_wrap = 800

        # Thinking indicator
        self._thinking = ThinkingIndicator(self._msg_inner)

        # Input area
        inp_outer = tk.Frame(chat_area, bg=C["bg"])
        inp_outer.pack(fill="x", side="bottom")
        inp_box = tk.Frame(inp_outer, bg="white", bd=1, relief="solid")
        inp_box.pack(fill="x", padx=48, pady=18)
        self._inp = tk.Text(inp_box, height=2, bg="white", fg=C["text"],
                            insertbackground=C["text"],
                            font=("Segoe UI", 13), relief="flat",
                            wrap="word", padx=14, pady=12, bd=0)
        self._inp.pack(side="left", fill="both", expand=True)
        self._inp.bind("<Return>", self._on_enter)
        self._inp.bind("<Shift-Return>", lambda e: None)
        self._send_btn = tk.Button(inp_box, text="↑", command=self._send_msg,
                                    bg=C["accent"], fg="white",
                                    font=("Segoe UI", 18, "bold"),
                                    relief="flat", cursor="hand2",
                                    width=2, bd=0)
        self._send_btn.pack(side="right", padx=8, pady=8)

        if self.current_chat_id:
            self._load_history(self.current_chat_id)

    def _on_canvas_resize(self, event):
        self._msg_wrap = max(400, int(event.width * 0.85))
        for bubble in self._msg_inner.winfo_children():
            for widget in bubble.winfo_children():
                if isinstance(widget, tk.Label) and widget.cget("wraplength"):
                    widget.config(wraplength=self._msg_wrap)

    # ── Clock ────────────────────────────────────────────────────
    def _tick_clock(self):
        if not hasattr(self, "_topbar_clock"):
            return
        try:
            self._topbar_clock.config(text=time.strftime("  %H:%M:%S"))
            self.root.after(1000, self._tick_clock)
        except Exception:
            pass

    # ── Sidebar ──────────────────────────────────────────────────
    def _render_sidebar(self):
        for w in self._chat_list.winfo_children():
            w.destroy()
        for ch in sorted(self.chats,
                         key=lambda c: c.get("updated_at", ""), reverse=True):
            self._sidebar_item(ch)

    def _sidebar_item(self, ch):
        cid    = ch["id"]
        title  = ch.get("title", "Untitled")[:44]
        is_sel = cid == self.current_chat_id

        item = tk.Frame(self._chat_list,
                        bg=C["panel"] if is_sel else C["sidebar"],
                        cursor="hand2", bd=1,
                        relief="solid" if is_sel else "flat")
        item.pack(fill="x", padx=8, pady=2)
        row = tk.Frame(item, bg=item["bg"])
        row.pack(fill="x", padx=10, pady=9)

        tk.Label(row, text=title, bg=item["bg"], fg=C["text"],
                 font=("Segoe UI", 11), anchor="w").pack(
            side="left", fill="x", expand=True)

        acts = tk.Frame(row, bg=item["bg"])
        acts.pack(side="right")
        for txt, cmd in [("✏", lambda c=ch: self._rename_chat(c)),
                          ("🗑", lambda c=ch: self._delete_chat(c))]:
            btn = tk.Label(acts, text=txt, bg=item["bg"],
                           fg=C["text_dim"], font=("Segoe UI", 11),
                           cursor="hand2")
            btn.pack(side="left", padx=2)
            btn.bind("<Button-1>", lambda e, fn=cmd: fn())
        for w in (item, row):
            w.bind("<Button-1>", lambda e, c=cid: self._select_chat(c))

    def _select_chat(self, cid):
        self.current_chat_id = cid
        self._render_sidebar()
        self._load_history(cid)

    def _new_chat_dialog(self):
        if not self.models:
            messagebox.showwarning("No Models", "No models available"); return
        win = tk.Toplevel(self.root)
        win.title("New Chat")
        win.geometry("400x210")
        win.configure(bg=C["sidebar"])
        win.grab_set()
        tk.Label(win, text="New Chat", bg=C["sidebar"], fg=C["text"],
                 font=("Segoe UI", 15, "bold")).pack(pady=(22, 16))
        mv = tk.StringVar()
        cb = ttk.Combobox(win, textvariable=mv,
                          values=[m["display_name"] for m in self.models],
                          state="readonly", width=34, font=("Segoe UI", 11))
        cb.current(self.selected_model_idx)
        cb.pack(padx=20, pady=(0, 20))

        def create():
            idx = [m["display_name"] for m in self.models].index(mv.get())
            mid = self.models[idx]["id"]
            r = self._cmd({"command": "new_chat", "session_token": self.token,
                           "model_id": mid, "title": "New Chat"})
            if r and r.get("status") == "ok":
                self._fetch_chats()
                self.current_chat_id = r["session_id"]
                self._render_sidebar()
                self._clear_msgs()
                win.destroy()

        tk.Button(win, text="Create", command=create,
                  bg=C["accent"], fg="white", font=("Segoe UI", 12, "bold"),
                  relief="flat", cursor="hand2", bd=0,
                  padx=22, pady=10).pack()

    def _rename_chat(self, ch):
        new = simpledialog.askstring("Rename", "New name:",
                                     initialvalue=ch.get("title", ""))
        if not new or not new.strip():
            return
        r = self._cmd({"command": "rename_chat", "session_token": self.token,
                       "chat_session_id": ch["id"], "title": new.strip()})
        if r and r.get("status") == "ok":
            for c in self.chats:
                if c["id"] == ch["id"]:
                    c["title"] = new.strip(); break
            self._render_sidebar()

    def _delete_chat(self, ch):
        if not messagebox.askyesno("Delete",
                                    f"Delete '{ch.get('title', 'this chat')}'?"):
            return
        r = self._cmd({"command": "delete_chat", "session_token": self.token,
                       "chat_session_id": ch["id"]})
        if r and r.get("status") == "ok":
            self.chats = [c for c in self.chats if c["id"] != ch["id"]]
            if self.current_chat_id == ch["id"]:
                self.current_chat_id = None
                self._clear_msgs()
            self._render_sidebar()

    def _on_model_change(self):
        if not self.models:
            return
        name = self._model_var.get()
        for i, m in enumerate(self.models):
            if m["display_name"] == name:
                self.selected_model_idx = i; break

    def _show_help(self):
        mk = (self.models[self.selected_model_idx].get("model_key", "")
              if self.models and self.selected_model_idx < len(self.models) else "")
        title, body = MODEL_HELP.get(mk, ("Help",
            "Select a model to see what you can ask it."))
        win = tk.Toplevel(self.root)
        win.title("Help")
        win.geometry("480x300")
        win.configure(bg=C["sidebar"])
        win.grab_set()
        tk.Label(win, text=title, bg=C["sidebar"], fg=C["text"],
                 font=("Segoe UI", 14, "bold")).pack(pady=(22, 12), padx=22, anchor="w")
        tk.Label(win, text=body, bg=C["sidebar"], fg=C["text_dim"],
                 font=("Segoe UI", 11), justify="left",
                 wraplength=440).pack(padx=22, pady=(0, 22), anchor="w")
        tk.Button(win, text="Close", command=win.destroy,
                  bg=C["panel"], fg=C["text"], font=("Segoe UI", 11, "bold"),
                  relief="flat", cursor="hand2", bd=0,
                  padx=18, pady=8).pack(pady=(0, 18))

    # ── Messages ─────────────────────────────────────────────────
    def _clear_msgs(self):
        for w in self._msg_inner.winfo_children():
            w.destroy()
        self._thinking = ThinkingIndicator(self._msg_inner)

    def _append_msg(self, role, content):
        wrap   = getattr(self, "_msg_wrap", 800)
        bubble = tk.Frame(self._msg_inner,
                          bg=C["user_bubble"] if role == "user" else C["ai_bubble"],
                          bd=0)
        bubble.pack(fill="x", padx=48, pady=8)
        tk.Label(bubble,
                 text="You" if role == "user" else "SHAKGPT",
                 bg=bubble["bg"], fg=C["accent"],
                 font=("Segoe UI", 11, "bold")).pack(
            anchor="w", padx=18, pady=(14, 4))
        tk.Label(bubble, text=content, bg=bubble["bg"], fg=C["text"],
                 font=("Segoe UI", 12), wraplength=wrap,
                 justify="left").pack(anchor="w", padx=18, pady=(0, 14))
        self._msg_canvas.update_idletasks()
        self._msg_canvas.yview_moveto(1.0)

    def _load_history(self, cid):
        self._clear_msgs()
        r = self._cmd({"command": "get_history", "session_token": self.token,
                       "chat_session_id": cid})
        if r and r.get("status") == "ok":
            for m in r.get("messages", []):
                self._append_msg(m["role"], m["content"])

    def _on_enter(self, e):
        if not (e.state & 0x1):
            self._send_msg(); return "break"

    def _send_msg(self):
        if not self.current_chat_id:
            messagebox.showwarning("No Chat", "Create a chat first"); return
        prompt = self._inp.get(1.0, "end").strip()
        if not prompt:
            return
        self._inp.delete(1.0, "end")
        self._append_msg("user", prompt)

        self._send_btn.config(state="disabled", text="⋯")
        self._thinking.pack(fill="x", padx=48, pady=4)
        self._thinking.start()
        self._msg_canvas.update_idletasks()
        self._msg_canvas.yview_moveto(1.0)

        def worker():
            try:
                self.sock.settimeout(None)
            except Exception:
                pass
            r = self._cmd({"command": "ask_ai",
                           "session_token": self.token,
                           "chat_session_id": self.current_chat_id,
                           "message": prompt})
            try:
                self.sock.settimeout(10)
            except Exception:
                pass
            self.root.after(0, lambda: self._on_response(r))

        threading.Thread(target=worker, daemon=True).start()

    def _on_response(self, r):
        self._thinking.stop()
        self._send_btn.config(state="normal", text="↑")
        if r and r.get("status") == "ok":
            ms   = r.get("latency_ms", 0)
            text = r.get("response", "")
            if ms:
                text += f"\n\n⏱ {ms / 1000:.1f}s"
            self._append_msg("assistant", text)
            self._fetch_chats()
            self._render_sidebar()
        else:
            self._append_msg("assistant",
                              "⚠ " + (r.get("message", "Unknown error")
                                       if r else "No response"))

    # ── Admin Panel ──────────────────────────────────────────────
    def _show_admin_panel(self):
        r = self._cmd({"command": "get_server_stats",
                       "session_token": self.token})
        if not r or r.get("status") != "ok":
            messagebox.showerror("Error",
                                  r.get("message", "Failed") if r else "Error")
            return
        win = tk.Toplevel(self.root)
        win.title("Admin Panel")
        win.geometry("860x580")
        win.configure(bg=C["bg"])
        win.grab_set()
        tk.Label(win, text="📊  Server Monitor", bg=C["bg"], fg=C["text"],
                 font=("Segoe UI", 17, "bold")).pack(pady=22)
        stats = r.get("stats", {})
        sf = tk.Frame(win, bg=C["bg"])
        sf.pack(fill="x", padx=22)
        for label, key in [("Total Requests",     "total_requests"),
                            ("Active Connections", "active_connections"),
                            ("Online Users",       "online_users"),
                            ("Blacklisted IPs",    "blacklisted_ips")]:
            card = tk.Frame(sf, bg=C["sidebar"], bd=1, relief="solid")
            card.pack(side="left", fill="both", expand=True, padx=4)
            tk.Label(card, text=label, bg=C["sidebar"], fg=C["text_dim"],
                     font=("Segoe UI", 10)).pack(pady=(14, 2))
            tk.Label(card, text=str(stats.get(key, 0)), bg=C["sidebar"],
                     fg=C["accent"], font=("Segoe UI", 24, "bold")).pack(pady=(0, 14))
        tk.Label(win, text="Users", bg=C["bg"], fg=C["text"],
                 font=("Segoe UI", 14, "bold")).pack(
            anchor="w", padx=22, pady=(22, 8))
        uf = tk.Frame(win, bg="white", bd=1, relief="solid")
        uf.pack(fill="both", expand=True, padx=22, pady=(0, 22))
        ut = scrolledtext.ScrolledText(uf, bg="white", fg=C["text"],
                                        font=("Segoe UI", 11), relief="flat")
        ut.pack(fill="both", expand=True, padx=14, pady=14)
        for u in r.get("users", []):
            role_lbl = "👑 ADMIN" if u["role"] == 2 else "👤 User"
            ut.insert("end", f"{role_lbl}  {u['display_name']}\n")
        ut.config(state="disabled")
        tk.Button(win, text="Close", command=win.destroy,
                  bg=C["panel"], fg=C["text"], font=("Segoe UI", 12, "bold"),
                  relief="flat", cursor="hand2", bd=0,
                  padx=22, pady=10).pack(pady=(0, 22))

    def _logout(self):
        try:
            self._cmd({"command": "logout", "session_token": self.token})
        except Exception:
            pass
        self.token = None
        self._show_welcome()


# ═════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()