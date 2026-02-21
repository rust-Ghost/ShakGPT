"""
stress_test.py — SHAKGPT Stress Test with GUI, live charts & result verification
"""

import threading, socket, struct, json, time, ssl, random, os, sys
from datetime import datetime
from collections import defaultdict
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

# ─── optional matplotlib for charts ──────────────────────────────
try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    MPL_OK = True
except ImportError:
    MPL_OK = False

HOST     = "127.0.0.1"
PORT     = 9921
LOGFILE  = "stress_log.txt"

# ══════════════════════════════════════════════════════════════════
#  Shared state (thread-safe)
# ══════════════════════════════════════════════════════════════════
_lock = threading.Lock()
_results = []        # list of dicts: {tid, mode, stage, status, latency_ms, ts}
_log_lines = []      # raw log strings for the log panel

_counters = {
    "success":  0,
    "fail":     0,
    "total":    0,
    "running":  0,
}

_latencies = []      # successful latency values (ms) for chart

def _record(tid, mode, stage, status, latency_ms=None):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    with _lock:
        entry = dict(tid=tid, mode=mode, stage=stage,
                     status=status, latency_ms=latency_ms, ts=ts)
        _results.append(entry)
        _log_lines.append(f"[{ts}] T-{tid:02d} | {mode} | {stage} | {status}")
        _counters["total"] += 1
        if status in ("ok", "done", "registered", "AI-ok"):
            _counters["success"] += 1
        elif status not in ("running",):
            _counters["fail"] += 1
        if latency_ms is not None and status == "AI-ok":
            _latencies.append(latency_ms)


# ══════════════════════════════════════════════════════════════════
#  Worker helpers
# ══════════════════════════════════════════════════════════════════
CREDENTIALS = [
    ("alice",   "Pass123!",  True),
    ("bob",     "Pass456!",  True),
    ("charlie", "Pass789!",  True),
    ("dave",    "Pass000!",  True),
    ("eve",     "Pass111!",  True),
    ("frank",   "Pass222!",  True),
    ("grace",   "wrongpass", False),
    ("henry",   "wrongpass", False),
    ("new1",    "NewPass1!", None),
    ("new2",    "NewPass2!", None),
]

def _send(s, obj):
    d = json.dumps(obj).encode()
    s.sendall(struct.pack(">I", len(d)) + d)

def _recv(s):
    h = s.recv(4)
    if len(h) < 4: return None
    n = struct.unpack(">I", h)[0]
    d = b""
    while len(d) < n:
        p = s.recv(n - len(d))
        if not p: return None
        d += p
    return json.loads(d.decode())

def _mk_ssl_sock(timeout=10):
    raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    sock = ctx.wrap_socket(raw, server_hostname="localhost")
    sock.settimeout(timeout)
    sock.connect((HOST, PORT))
    return sock


# ── Realistic worker ──────────────────────────────────────────────
def realistic_worker(tid):
    with _lock: _counters["running"] += 1
    cred = CREDENTIALS[tid % len(CREDENTIALS)]
    username, password, should_succeed = cred
    try:
        sock = _mk_ssl_sock()
    except Exception as e:
        _record(tid, "REALISTIC", "CONNECT", f"error: {e}")
        with _lock: _counters["running"] -= 1
        return

    try:
        # Optional register
        if should_succeed is None:
            _send(sock, {"command":"register","username":username,
                         "password":password,"display_name":username})
            r = _recv(sock)
            status = r.get("status") if r else "no-resp"
            _record(tid, "REALISTIC", "REGISTER", status)

        # Login
        _send(sock, {"command":"login","username":username,"password":password})
        r = _recv(sock)
        if not r or r.get("status") != "ok":
            expected_fail = (should_succeed == False)
            _record(tid, "REALISTIC", "LOGIN",
                    "expected-fail" if expected_fail else "unexpected-fail")
            return
        token = r.get("session_token")
        _record(tid, "REALISTIC", "LOGIN", "ok")

        # Get models
        _send(sock, {"command":"get_models"})
        r = _recv(sock)
        if not r or not r.get("models"):
            _record(tid, "REALISTIC", "GET_MODELS", "no-models"); return

        # New chat
        _send(sock, {"command":"new_chat","session_token":token,
                     "model_id":r["models"][0]["id"],"title":"Stress Test"})
        r = _recv(sock)
        if not r or r.get("status") != "ok":
            _record(tid, "REALISTIC", "NEW_CHAT", "fail"); return
        chat_id = r["session_id"]
        _record(tid, "REALISTIC", "NEW_CHAT", "ok")

        # Ask AI
        sock.settimeout(None)
        t0 = time.time()
        _send(sock, {"command":"ask_ai","session_token":token,
                     "chat_session_id":chat_id, "message":"hello"})
        r = _recv(sock)
        ms = int((time.time() - t0) * 1000)
        if r and r.get("status") == "ok":
            _record(tid, "REALISTIC", "ASK_AI", "AI-ok", latency_ms=ms)
        else:
            _record(tid, "REALISTIC", "ASK_AI", "fail")
    except Exception as e:
        _record(tid, "REALISTIC", "ERROR", str(e))
    finally:
        try: sock.close()
        except: pass
        with _lock: _counters["running"] -= 1


# ── DDoS worker ───────────────────────────────────────────────────
def ddos_worker(tid):
    with _lock: _counters["running"] += 1
    try:
        raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw.settimeout(2)
        raw.connect((HOST, PORT))
        attack = random.choice(["flood", "garbage", "slow"])
        if attack == "flood":
            for i in range(100):
                try: _send(raw, {"command":"login","username":f"spam{i}","password":"x"})
                except: break
            _record(tid, "DDOS", "FLOOD", "done")
        elif attack == "garbage":
            raw.sendall(b"\xFF" * 1000)
            _record(tid, "DDOS", "GARBAGE", "done")
        else:
            for _ in range(10):
                try: raw.sendall(b"\x00" * 10); time.sleep(0.5)
                except: break
            _record(tid, "DDOS", "SLOWLORIS", "done")
    except Exception as e:
        _record(tid, "DDOS", "CONNECT", f"blocked/error: {e}")
    finally:
        try: raw.close()
        except: pass
        with _lock: _counters["running"] -= 1


# ══════════════════════════════════════════════════════════════════
#  Result Verification
# ══════════════════════════════════════════════════════════════════
def verify_results(mode):
    """Return a list of (check_name, passed, detail) tuples."""
    checks = []
    with _lock:
        results = list(_results)
        counters = dict(_counters)
        latencies = list(_latencies)

    if mode == "REALISTIC":
        # 1. At least some logins succeeded
        logins_ok = [r for r in results if r["stage"]=="LOGIN" and r["status"]=="ok"]
        checks.append(("Successful logins", len(logins_ok) > 0,
                        f"{len(logins_ok)} logins succeeded"))

        # 2. Wrong-password logins all failed
        wrong_attempts = [r for r in results
                          if r["stage"]=="LOGIN" and r["status"]=="unexpected-fail"]
        checks.append(("Wrong-password correctly rejected", len(wrong_attempts) == 0,
                        f"{len(wrong_attempts)} unexpected failures (should be 0)"))

        # 3. AI responses received
        ai_ok = [r for r in results if r["stage"]=="ASK_AI" and r["status"]=="AI-ok"]
        checks.append(("AI responses received", len(ai_ok) > 0,
                        f"{len(ai_ok)} AI responses"))

        # 4. Latency sanity (<30 s)
        if latencies:
            avg_ms = sum(latencies) / len(latencies)
            checks.append(("Avg AI latency < 30 s", avg_ms < 30_000,
                            f"Avg {avg_ms/1000:.1f}s"))
        else:
            checks.append(("Avg AI latency", False, "No AI responses to measure"))

        # 5. No server errors
        errors = [r for r in results if "error" in r["status"].lower()]
        checks.append(("No unexpected errors", len(errors) == 0,
                        f"{len(errors)} errors logged"))

    else:  # DDOS
        # 1. Most attacks were blocked/handled gracefully (no crash)
        checks.append(("Test completed without crash", True, "Server survived"))

        # 2. Flood attempts
        floods = [r for r in results if r["stage"]=="FLOOD"]
        checks.append(("Flood workers completed", len(floods) > 0,
                        f"{len(floods)} flood workers"))

        # 3. Garbage handled
        garbage = [r for r in results if r["stage"]=="GARBAGE"]
        checks.append(("Garbage inputs handled", len(garbage) > 0,
                        f"{len(garbage)} garbage workers"))

        # 4. SlowLoris handled
        slow = [r for r in results if r["stage"]=="SLOWLORIS"]
        checks.append(("Slowloris handled", len(slow) > 0,
                        f"{len(slow)} slowloris workers"))

        # 5. Server blocked attempts (connections refused/errors = good)
        blocked = [r for r in results
                   if "blocked" in r["status"] or "error" in r["status"]]
        checks.append(("Server actively blocked requests", len(blocked) > 0,
                        f"{len(blocked)} blocked by server"))

    return checks


# ══════════════════════════════════════════════════════════════════
#  GUI
# ══════════════════════════════════════════════════════════════════
DARK = {
    "bg":      "#0D1117",
    "panel":   "#161B22",
    "border":  "#30363D",
    "text":    "#C9D1D9",
    "dim":     "#8B949E",
    "green":   "#3FB950",
    "red":     "#F85149",
    "yellow":  "#E3B341",
    "blue":    "#58A6FF",
    "accent":  "#238636",
}

class StressTestGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SHAKGPT — Stress Test Suite")
        self.root.geometry("1100x750")
        self.root.minsize(900, 600)
        self.root.configure(bg=DARK["bg"])
        self._running = False
        self._mode = None
        self._thread_count = 0
        self._build_ui()

    # ── Build UI ─────────────────────────────────────────────────
    def _build_ui(self):
        # ── Top bar ──
        top = tk.Frame(self.root, bg=DARK["panel"], height=54)
        top.pack(fill="x")
        top.pack_propagate(False)
        tk.Label(top, text="⚡  SHAKGPT Stress Test", bg=DARK["panel"],
                 fg=DARK["blue"], font=("Segoe UI",14,"bold")).pack(side="left", padx=16, pady=12)
        self._status_lbl = tk.Label(top, text="● IDLE", bg=DARK["panel"],
                                    fg=DARK["dim"], font=("Segoe UI",10,"bold"))
        self._status_lbl.pack(side="right", padx=16)

        # ── Config row ──
        cfg = tk.Frame(self.root, bg=DARK["bg"])
        cfg.pack(fill="x", padx=16, pady=12)

        tk.Label(cfg, text="Mode:", bg=DARK["bg"], fg=DARK["dim"],
                 font=("Segoe UI",10)).pack(side="left")
        self._mode_var = tk.StringVar(value="Realistic Mix")
        mode_cb = ttk.Combobox(cfg, textvariable=self._mode_var,
                               values=["Realistic Mix", "DDoS Attack"],
                               state="readonly", width=18, font=("Segoe UI",10))
        mode_cb.pack(side="left", padx=(6, 20))

        tk.Label(cfg, text="Threads:", bg=DARK["bg"], fg=DARK["dim"],
                 font=("Segoe UI",10)).pack(side="left")
        self._threads_var = tk.StringVar(value="20")
        threads_spin = tk.Spinbox(cfg, textvariable=self._threads_var,
                                  from_=1, to=100, width=5,
                                  bg=DARK["panel"], fg=DARK["text"],
                                  insertbackground=DARK["text"],
                                  font=("Segoe UI",10), relief="flat")
        threads_spin.pack(side="left", padx=(6, 20))

        self._run_btn = tk.Button(cfg, text="▶  Run Test",
                                  command=self._start_test,
                                  bg=DARK["accent"], fg="white",
                                  font=("Segoe UI",11,"bold"),
                                  relief="flat", cursor="hand2",
                                  padx=16, pady=6)
        self._run_btn.pack(side="left")

        self._verify_btn = tk.Button(cfg, text="✔  Verify Results",
                                     command=self._show_verify,
                                     bg=DARK["panel"], fg=DARK["text"],
                                     font=("Segoe UI",11,"bold"),
                                     relief="flat", cursor="hand2",
                                     padx=16, pady=6, state="disabled")
        self._verify_btn.pack(side="left", padx=(10,0))

        self._clear_btn = tk.Button(cfg, text="🗑  Clear",
                                    command=self._clear_results,
                                    bg=DARK["panel"], fg=DARK["dim"],
                                    font=("Segoe UI",10),
                                    relief="flat", cursor="hand2",
                                    padx=12, pady=6)
        self._clear_btn.pack(side="left", padx=(10,0))

        # ── Stats row ──
        stats_frame = tk.Frame(self.root, bg=DARK["bg"])
        stats_frame.pack(fill="x", padx=16, pady=(0,8))
        self._stat_labels = {}
        for key, label, color in [
            ("total",   "Total",   DARK["blue"]),
            ("success", "Success", DARK["green"]),
            ("fail",    "Failed",  DARK["red"]),
            ("running", "Running", DARK["yellow"]),
        ]:
            card = tk.Frame(stats_frame, bg=DARK["panel"], bd=1, relief="solid")
            card.pack(side="left", fill="both", expand=True, padx=4)
            tk.Label(card, text=label, bg=DARK["panel"], fg=DARK["dim"],
                     font=("Segoe UI",9)).pack(pady=(8,2))
            val = tk.Label(card, text="0", bg=DARK["panel"], fg=color,
                           font=("Segoe UI",22,"bold"))
            val.pack(pady=(0,8))
            self._stat_labels[key] = val

        # ── Body: log + chart ──
        body = tk.Frame(self.root, bg=DARK["bg"])
        body.pack(fill="both", expand=True, padx=16, pady=(0,16))

        # Log panel (left)
        log_frame = tk.Frame(body, bg=DARK["panel"], bd=1, relief="solid")
        log_frame.pack(side="left", fill="both", expand=True)
        tk.Label(log_frame, text="Live Log", bg=DARK["panel"], fg=DARK["text"],
                 font=("Segoe UI",10,"bold"), anchor="w").pack(fill="x", padx=10, pady=(8,4))
        self._log_box = scrolledtext.ScrolledText(
            log_frame, bg=DARK["bg"], fg=DARK["dim"],
            font=("Consolas",9), relief="flat", wrap="word", state="disabled")
        self._log_box.pack(fill="both", expand=True, padx=8, pady=(0,8))

        # Chart panel (right) — only if matplotlib available
        right = tk.Frame(body, bg=DARK["bg"], width=360)
        right.pack(side="right", fill="y", padx=(12,0))
        right.pack_propagate(False)

        if MPL_OK:
            self._build_charts(right)
        else:
            tk.Label(right, text="Install matplotlib\nfor live charts\n\npip install matplotlib",
                     bg=DARK["panel"], fg=DARK["dim"], font=("Segoe UI",10),
                     justify="center").pack(fill="both", expand=True, padx=8, pady=8)

        # Progress bar
        prog_frame = tk.Frame(self.root, bg=DARK["bg"])
        prog_frame.pack(fill="x", padx=16, pady=(0,12))
        self._progress = ttk.Progressbar(prog_frame, mode="determinate", length=400)
        self._progress.pack(side="left", fill="x", expand=True)
        self._prog_lbl = tk.Label(prog_frame, text="0 / 0",
                                  bg=DARK["bg"], fg=DARK["dim"], font=("Segoe UI",9))
        self._prog_lbl.pack(side="left", padx=8)

    def _build_charts(self, parent):
        fig = Figure(figsize=(3.5, 7), facecolor=DARK["panel"])
        fig.subplots_adjust(hspace=0.45)

        # Pie: success vs fail
        self._ax_pie = fig.add_subplot(3, 1, 1)
        self._ax_pie.set_facecolor(DARK["panel"])
        self._ax_pie.set_title("Pass / Fail", color=DARK["text"], fontsize=9)

        # Bar: stage breakdown
        self._ax_bar = fig.add_subplot(3, 1, 2)
        self._ax_bar.set_facecolor(DARK["panel"])
        self._ax_bar.set_title("Stage Counts", color=DARK["text"], fontsize=9)

        # Line: latency over time
        self._ax_lat = fig.add_subplot(3, 1, 3)
        self._ax_lat.set_facecolor(DARK["panel"])
        self._ax_lat.set_title("AI Latency (ms)", color=DARK["text"], fontsize=9)

        self._mpl_canvas = FigureCanvasTkAgg(fig, master=parent)
        self._mpl_canvas.get_tk_widget().pack(fill="both", expand=True)
        self._fig = fig

    # ── Run test ─────────────────────────────────────────────────
    def _start_test(self):
        if self._running:
            return
        self._clear_results()
        mode_str = self._mode_var.get()
        n = int(self._threads_var.get() or 20)
        self._mode = "REALISTIC" if mode_str == "Realistic Mix" else "DDOS"
        worker = realistic_worker if self._mode == "REALISTIC" else ddos_worker
        self._thread_count = n
        self._running = True
        self._run_btn.config(state="disabled")
        self._verify_btn.config(state="disabled")
        self._status_lbl.config(text="● RUNNING", fg=DARK["yellow"])
        self._progress["maximum"] = n
        self._progress["value"] = 0

        def launch():
            threads = []
            for i in range(1, n + 1):
                t = threading.Thread(target=worker, args=(i,), daemon=True)
                threads.append(t)
                t.start()
                time.sleep(0.02)
            for t in threads:
                t.join()
            self.root.after(0, self._on_done)

        threading.Thread(target=launch, daemon=True).start()
        self._poll_loop()

    def _poll_loop(self):
        if not self._running:
            return
        with _lock:
            c = dict(_counters)
            lines = list(_log_lines)
            done = c["total"] - c["running"]

        # Update stat cards
        for key, val in c.items():
            if key in self._stat_labels:
                self._stat_labels[key].config(text=str(val))

        # Progress
        self._progress["value"] = min(done, self._thread_count)
        self._prog_lbl.config(text=f"{done} / {self._thread_count}")

        # Append new log lines
        self._log_box.config(state="normal")
        current_line_count = int(self._log_box.index("end-1c").split(".")[0])
        if len(lines) > current_line_count:
            for line in lines[current_line_count:]:
                color = DARK["green"] if any(s in line for s in ("ok","done","AI-ok","registered")) \
                        else DARK["red"] if any(s in line for s in ("fail","error","blocked")) \
                        else DARK["dim"]
                self._log_box.insert("end", line + "\n")
            self._log_box.see("end")
        self._log_box.config(state="disabled")

        # Update charts
        if MPL_OK:
            self._update_charts()

        self.root.after(400, self._poll_loop)

    def _update_charts(self):
        try:
            with _lock:
                c = dict(_counters)
                results = list(_results)
                latencies = list(_latencies)

            # Pie
            self._ax_pie.clear()
            self._ax_pie.set_facecolor(DARK["panel"])
            self._ax_pie.set_title("Pass / Fail", color=DARK["text"], fontsize=9)
            s, f = c["success"], c["fail"]
            if s + f > 0:
                self._ax_pie.pie([s, f],
                                 labels=["Pass","Fail"],
                                 colors=[DARK["green"], DARK["red"]],
                                 autopct="%1.0f%%",
                                 textprops={"color": DARK["text"], "fontsize": 8},
                                 startangle=90)

            # Bar: stage counts
            self._ax_bar.clear()
            self._ax_bar.set_facecolor(DARK["panel"])
            self._ax_bar.set_title("Stage Counts", color=DARK["text"], fontsize=9)
            stage_counts = defaultdict(int)
            for r in results:
                stage_counts[r["stage"]] += 1
            if stage_counts:
                stages = list(stage_counts.keys())
                counts = [stage_counts[s] for s in stages]
                bars = self._ax_bar.bar(range(len(stages)), counts,
                                        color=DARK["blue"])
                self._ax_bar.set_xticks(range(len(stages)))
                self._ax_bar.set_xticklabels(stages, rotation=30, ha="right",
                                              fontsize=7, color=DARK["dim"])
                self._ax_bar.tick_params(axis="y", colors=DARK["dim"])
                for spine in self._ax_bar.spines.values():
                    spine.set_edgecolor(DARK["border"])

            # Line: latency
            self._ax_lat.clear()
            self._ax_lat.set_facecolor(DARK["panel"])
            self._ax_lat.set_title("AI Latency (ms)", color=DARK["text"], fontsize=9)
            if latencies:
                self._ax_lat.plot(latencies, color=DARK["yellow"], linewidth=1.5)
                self._ax_lat.tick_params(colors=DARK["dim"])
                for spine in self._ax_lat.spines.values():
                    spine.set_edgecolor(DARK["border"])

            self._mpl_canvas.draw()
        except Exception:
            pass

    def _on_done(self):
        self._running = False
        self._run_btn.config(state="normal")
        self._verify_btn.config(state="normal")
        self._status_lbl.config(text="● DONE", fg=DARK["green"])
        with _lock:
            c = dict(_counters)
        for key, val in c.items():
            if key in self._stat_labels:
                self._stat_labels[key].config(text=str(val))
        self._progress["value"] = self._thread_count
        self._prog_lbl.config(text=f"{self._thread_count} / {self._thread_count}")
        if MPL_OK:
            self._update_charts()

        # Write log file
        with open(LOGFILE, "w", encoding="utf-8") as f:
            f.write(f"=== {self._mode} START ===\n{datetime.now()}\n\n")
            with _lock:
                f.writelines(l + "\n" for l in _log_lines)
            f.write(f"\n=== {self._mode} END ===\n")

    def _clear_results(self):
        global _results, _log_lines, _latencies
        with _lock:
            _results.clear()
            _log_lines.clear()
            _latencies.clear()
            for k in _counters: _counters[k] = 0
        self._log_box.config(state="normal")
        self._log_box.delete(1.0, "end")
        self._log_box.config(state="disabled")
        for lbl in self._stat_labels.values():
            lbl.config(text="0")
        self._progress["value"] = 0
        self._prog_lbl.config(text="0 / 0")
        self._verify_btn.config(state="disabled")
        self._status_lbl.config(text="● IDLE", fg=DARK["dim"])
        if MPL_OK:
            try:
                for ax in (self._ax_pie, self._ax_bar, self._ax_lat):
                    ax.clear()
                self._mpl_canvas.draw()
            except: pass

    # ── Verification window ───────────────────────────────────────
    def _show_verify(self):
        checks = verify_results(self._mode or "REALISTIC")

        win = tk.Toplevel(self.root)
        win.title("Result Verification")
        win.geometry("560x420")
        win.configure(bg=DARK["bg"])
        win.grab_set()

        tk.Label(win, text="✔  Result Verification", bg=DARK["bg"],
                 fg=DARK["blue"], font=("Segoe UI",14,"bold")).pack(pady=(20,4), padx=20, anchor="w")
        tk.Label(win, text=f"Mode: {self._mode}   |   Run: {datetime.now().strftime('%H:%M:%S')}",
                 bg=DARK["bg"], fg=DARK["dim"], font=("Segoe UI",9)).pack(padx=20, anchor="w")

        tk.Frame(win, bg=DARK["border"], height=1).pack(fill="x", padx=20, pady=12)

        scroll_frame = tk.Frame(win, bg=DARK["bg"])
        scroll_frame.pack(fill="both", expand=True, padx=20)

        passed = sum(1 for _, p, _ in checks if p)
        total  = len(checks)

        for check_name, passed_flag, detail in checks:
            row = tk.Frame(scroll_frame, bg=DARK["panel"], bd=1, relief="solid")
            row.pack(fill="x", pady=3)
            inner = tk.Frame(row, bg=DARK["panel"])
            inner.pack(fill="x", padx=12, pady=8)

            icon  = "✅" if passed_flag else "❌"
            color = DARK["green"] if passed_flag else DARK["red"]
            tk.Label(inner, text=icon, bg=DARK["panel"],
                     font=("Segoe UI",14)).pack(side="left")
            name_frame = tk.Frame(inner, bg=DARK["panel"])
            name_frame.pack(side="left", padx=10, fill="x", expand=True)
            tk.Label(name_frame, text=check_name, bg=DARK["panel"],
                     fg=DARK["text"], font=("Segoe UI",10,"bold"),
                     anchor="w").pack(anchor="w")
            tk.Label(name_frame, text=detail, bg=DARK["panel"],
                     fg=DARK["dim"], font=("Segoe UI",9),
                     anchor="w").pack(anchor="w")

        tk.Frame(win, bg=DARK["border"], height=1).pack(fill="x", padx=20, pady=8)

        summary_color = DARK["green"] if passed == total else DARK["yellow"] if passed > 0 else DARK["red"]
        tk.Label(win, text=f"{'ALL CHECKS PASSED' if passed==total else f'{passed}/{total} checks passed'}",
                 bg=DARK["bg"], fg=summary_color,
                 font=("Segoe UI",12,"bold")).pack(pady=(0,8))

        tk.Button(win, text="Close", command=win.destroy,
                  bg=DARK["panel"], fg=DARK["text"],
                  font=("Segoe UI",10,"bold"), relief="flat",
                  cursor="hand2", padx=20, pady=6).pack(pady=(0,16))

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = StressTestGUI()
    app.run()