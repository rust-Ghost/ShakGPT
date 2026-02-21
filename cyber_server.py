"""
cyber_server.py  –  Cyber AI Server
All inference is LOCAL via llama.cpp — no data ever leaves this machine.
Encrypted with SSL/TLS for the client connection.
"""

import socket, threading, json, struct, uuid, ssl, hashlib, time, traceback, os
from collections import defaultdict
from typing import Dict, Optional, Tuple
import tkinter as tk
from tkinter import scrolledtext

import bcrypt
from db_manager import DatabaseManager
from create_tables import create_all_tables, seed_models
from constants import DB_CONFIG, IP, PORT, MODELS_DIR, N_THREADS, N_CTX

# ─────────────────────────────────────────────────────────────────
#  Local AI via llama.cpp
#  Install:  pip install llama-cpp-python
#  Models:   drop .gguf files into MODELS_DIR
# ─────────────────────────────────────────────────────────────────
try:
    from llama_cpp import Llama
    LLAMA_OK = True
    print("[INFO] llama-cpp-python available")
except ImportError:
    LLAMA_OK = False
    print("[WARN] llama-cpp-python not installed — AI will echo back prompts")
    print("       Run:  pip install llama-cpp-python")

_model_cache: Dict = {}   # model_key -> Llama instance
_model_lock = threading.Lock()


def _load_model(model_key: str, gguf_filename: str) -> Optional[object]:
    """Load (or return cached) a llama.cpp model."""
    with _model_lock:
        if model_key in _model_cache:
            return _model_cache[model_key]

        path = os.path.join(MODELS_DIR, gguf_filename)
        if not os.path.exists(path):
            print(f"[WARN] Model file not found: {path}")
            print(f"       Download it and place it in '{MODELS_DIR}/'")
            return None

        print(f"[INFO] Loading '{model_key}' from {path} ...")
        llm = Llama(
            model_path=path,
            n_threads=N_THREADS,
            n_ctx=N_CTX,
            n_batch=512,
            verbose=False,
        )
        _model_cache[model_key] = llm
        print(f"[INFO] '{model_key}' ready.")
        return llm


def generate_response(model_key: str, gguf_filename: str,
                       max_new_tokens: int, prompt: str) -> Tuple[str, int]:
    """Run local inference. Returns (response_text, latency_ms)."""
    if not LLAMA_OK:
        return f"[AI stub — install llama-cpp-python] You asked: {prompt}", 0

    llm = _load_model(model_key, gguf_filename)
    if llm is None:
        return (
            f"Model file '{gguf_filename}' not found in '{MODELS_DIR}'.\n"
            "Please download the GGUF file and restart the server.",
            0,
        )

    # Chat-ML style prompt — works for TinyLlama, Mistral, Phi-2
    formatted = (
        "<|system|>\nYou are Cyber AI, a helpful and concise assistant.</s>\n"
        f"<|user|>\n{prompt}</s>\n"
        "<|assistant|>\n"
    )

    t0 = time.time()
    output = llm(
        formatted,
        max_tokens=max_new_tokens,
        temperature=0.7,
        top_p=0.9,
        repeat_penalty=1.1,
        stop=["</s>", "<|user|>", "<|system|>"],
        echo=False,
    )
    latency_ms = int((time.time() - t0) * 1000)
    text = output["choices"][0]["text"].strip()
    return text, latency_ms


# ─────────────────────────────────────────────────────────────────
#  DDoS / Rate-limit protection
# ─────────────────────────────────────────────────────────────────
MAX_CONNS_PER_IP        = 8
MAX_REQUESTS_PER_MIN    = 60
BLACKLIST_RPM_THRESHOLD = 120
BLACKLIST_DURATION_S    = 300

_ddos_lock              = threading.Lock()
_ip_conns: Dict         = defaultdict(int)
_ip_req_times: Dict     = defaultdict(list)
_ip_blacklist: Dict     = {}


def _conn_check(ip: str) -> Tuple[bool, str]:
    now = time.time()
    with _ddos_lock:
        bl = _ip_blacklist.get(ip)
        if bl:
            if now < bl: return False, "IP temporarily blocked"
            del _ip_blacklist[ip]
        if _ip_conns[ip] >= MAX_CONNS_PER_IP:
            return False, "Too many concurrent connections"
        _ip_conns[ip] += 1
    return True, ""


def _conn_release(ip: str):
    with _ddos_lock:
        if _ip_conns[ip] > 0: _ip_conns[ip] -= 1


def _rate_check(ip: str) -> Tuple[bool, str]:
    now = time.time()
    with _ddos_lock:
        times = [t for t in _ip_req_times[ip] if now - t < 60.0]
        _ip_req_times[ip] = times
        if len(times) >= BLACKLIST_RPM_THRESHOLD:
            _ip_blacklist[ip] = now + BLACKLIST_DURATION_S
            return False, "Rate limit exceeded – IP blacklisted"
        if len(times) >= MAX_REQUESTS_PER_MIN:
            return False, "Rate limit exceeded – slow down"
        _ip_req_times[ip].append(now)
    return True, ""


# ─────────────────────────────────────────────────────────────────
#  Session store
# ─────────────────────────────────────────────────────────────────
_SESSIONS: Dict    = {}
_SESS_LOCK         = threading.Lock()

def _sess_add(tok, uid):
    with _SESS_LOCK: _SESSIONS[tok] = uid
def _sess_get(tok) -> Optional[str]:
    with _SESS_LOCK: return _SESSIONS.get(tok)
def _sess_del(tok):
    with _SESS_LOCK: _SESSIONS.pop(tok, None)


# ─────────────────────────────────────────────────────────────────
#  Server monitoring & stats
# ─────────────────────────────────────────────────────────────────
_MONITOR_WINDOW = None
_STATS_LOCK = threading.Lock()
_SERVER_STATS = {
    "total_requests": 0,
    "active_connections": 0,
    "online_users": 0,
    "blacklisted_ips": 0,
}

def _update_stat(key, value):
    with _STATS_LOCK:
        _SERVER_STATS[key] = value

def _increment_stat(key):
    with _STATS_LOCK:
        _SERVER_STATS[key] += 1

def _get_stats():
    with _STATS_LOCK:
        return _SERVER_STATS.copy()

def _log_activity(msg):
    if _MONITOR_WINDOW:
        _MONITOR_WINDOW.log(msg)


def _hash_user(u: str) -> str:
    return hashlib.sha256(u.strip().lower().encode()).hexdigest()


def _make_db() -> DatabaseManager:
    db = DatabaseManager(host=DB_CONFIG["host"], user=DB_CONFIG["user"],
                          password=DB_CONFIG["password"])
    if DB_CONFIG.get("database"):
        db.reconnect(DB_CONFIG["database"])
    return db


def _recv(conn):
    try:
        h = conn.recv(4)
        if len(h) < 4: return None
        n = struct.unpack(">I", h)[0]
        if n > 10*1024*1024: return None
        d = b""
        while len(d) < n:
            p = conn.recv(min(4096, n-len(d)))
            if not p: return None
            d += p
        return json.loads(d.decode())
    except: return None


def _send(conn, obj):
    try:
        d = json.dumps(obj).encode()
        conn.sendall(struct.pack(">I", len(d)) + d)
    except Exception as e:
        print(f"[WARN] send: {e}")


# ─────────────────────────────────────────────────────────────────
#  Integrated Server Monitor (GUI)
# ─────────────────────────────────────────────────────────────────
class ServerMonitor:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Cyber AI — Server Monitor")
        self.root.geometry("800x600")
        self.root.configure(bg="#0D1117")
        self.running = True
        
        # Title
        title_frame = tk.Frame(self.root, bg="#161B22", height=50)
        title_frame.pack(fill="x")
        title_frame.pack_propagate(False)
        
        tk.Label(title_frame, text="⬡  Server Monitor", bg="#161B22",
                fg="#58A6FF", font=("Segoe UI",14,"bold")).pack(side="left", padx=16, pady=12)
        
        self.status_lbl = tk.Label(title_frame, text="● RUNNING", bg="#161B22",
                                   fg="#3FB950", font=("Segoe UI",10,"bold"))
        self.status_lbl.pack(side="right", padx=16)
        
        # Stats row
        stats_frame = tk.Frame(self.root, bg="#0D1117")
        stats_frame.pack(fill="x", padx=16, pady=16)
        
        self.stat_labels = {}
        for i, (key, label) in enumerate([
            ("total_requests", "Total Requests"),
            ("active_connections", "Active Connections"),
            ("online_users", "Online Users"),
            ("blacklisted_ips", "Blacklisted IPs")
        ]):
            card = tk.Frame(stats_frame, bg="#161B22", bd=1, relief="solid")
            card.pack(side="left", fill="both", expand=True, padx=4)
            
            tk.Label(card, text=label, bg="#161B22", fg="#8B949E",
                    font=("Segoe UI",9)).pack(pady=(8,2))
            
            val_lbl = tk.Label(card, text="0", bg="#161B22", fg="#C9D1D9",
                              font=("Segoe UI",20,"bold"))
            val_lbl.pack(pady=(0,8))
            self.stat_labels[key] = val_lbl
        
        # Activity log
        log_frame = tk.Frame(self.root, bg="#161B22", bd=1, relief="solid")
        log_frame.pack(fill="both", expand=True, padx=16, pady=(0,16))
        
        tk.Label(log_frame, text="Activity Log", bg="#161B22", fg="#C9D1D9",
                font=("Segoe UI",11,"bold"), anchor="w").pack(fill="x", padx=12, pady=8)
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame, bg="#0D1117", fg="#8B949E",
            font=("Consolas",9), relief="flat", wrap="word", state="disabled")
        self.log_text.pack(fill="both", expand=True, padx=8, pady=(0,8))
        
        self.log("[SERVER] Monitor initialized")
        
        # Start update loop
        self._update_loop()
        
        # Handle close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def log(self, msg):
        try:
            ts = time.strftime("%H:%M:%S")
            self.log_text.config(state="normal")
            self.log_text.insert("end", f"[{ts}] {msg}\n")
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        except:
            pass
    
    def _update_loop(self):
        if not self.running:
            return
        
        stats = _get_stats()
        for key, lbl in self.stat_labels.items():
            lbl.config(text=str(stats.get(key, 0)))
        
        # Count online users from sessions
        with _SESS_LOCK:
            online = len(_SESSIONS)
        self.stat_labels["online_users"].config(text=str(online))
        
        # Count blacklisted IPs
        with _ddos_lock:
            blacklisted = len(_ip_blacklist)
        self.stat_labels["blacklisted_ips"].config(text=str(blacklisted))
        
        self.root.after(1000, self._update_loop)
    
    def _on_close(self):
        self.running = False
        self.root.destroy()
    
    def run(self):
        self.root.mainloop()


# ─────────────────────────────────────────────────────────────────
#  Client handler
# ─────────────────────────────────────────────────────────────────
def handle_client(conn, addr):
    ip = addr[0]
    print(f"[INFO] Connected: {addr}")
    _increment_stat("active_connections")
    _log_activity(f"Connection from {ip}")
    db = None
    try:
        db = _make_db()
        while True:
            ok, reason = _rate_check(ip)
            if not ok:
                _send(conn, {"status":"error","message":reason})
                _log_activity(f"Rate limit: {ip}")
                break
            
            _increment_stat("total_requests")

            msg = _recv(conn)
            if msg is None: break
            if not isinstance(msg, dict):
                _send(conn, {"status":"error","message":"Invalid format"}); continue

            cmd  = msg.get("command","")
            resp = {"status":"error","message":"Unknown command"}

            try:
                # ── REGISTER ──────────────────────────────────
                if cmd == "register":
                    u = msg.get("username","").strip()
                    p = msg.get("password","").strip()
                    dn = msg.get("display_name", u).strip() or u
                    if not u or not p:
                        resp = {"status":"error","message":"Username and password required"}
                    else:
                        uh = _hash_user(u)
                        if db.get_rows_from_table_with_value("clients","username_hash",uh):
                            resp = {"status":"error","message":"Username already exists"}
                        else:
                            ph = bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()
                            cid = str(uuid.uuid4())
                            db.insert_row("clients",
                                ["id","username_hash","display_name","password_hash"],
                                [cid, uh, dn, ph])
                            resp = {"status":"ok","message":"Registered successfully"}

                # ── LOGIN ──────────────────────────────────────
                elif cmd == "login":
                    u = msg.get("username","").strip()
                    p = msg.get("password","").strip()
                    if not u or not p:
                        resp = {"status":"error","message":"Username and password required"}
                    else:
                        uh   = _hash_user(u)
                        rows = db.get_rows_from_table_with_value("clients","username_hash",uh)
                        if not rows:
                            resp = {"status":"error","message":"User not found"}
                        else:
                            row = rows[0]
                            if bcrypt.checkpw(p.encode(), row[3].encode()):
                                tok = str(uuid.uuid4())
                                _sess_add(tok, row[0])
                                _log_activity(f"Login: {row[2]} (role={row[4]})")
                                resp = {"status":"ok","session_token":tok,
                                        "display_name":row[2],"user_id":row[0],"role":row[4]}
                            else:
                                resp = {"status":"error","message":"Incorrect password"}

                # ── GET MODELS ─────────────────────────────────
                elif cmd == "get_models":
                    rows = db.get_all_rows("Model_Versions")
                    resp = {"status":"ok","models":[
                        {"id":r[0],"model_key":r[1],"display_name":r[2],"description":r[4]}
                        for r in rows if r[6]]}

                # ── NEW CHAT ───────────────────────────────────
                elif cmd == "new_chat":
                    uid = _sess_get(msg.get("session_token"))
                    if not uid:
                        resp = {"status":"error","message":"Invalid session"}
                    else:
                        mid = msg.get("model_id"); title = msg.get("title","New Chat")
                        if not mid:
                            resp = {"status":"error","message":"model_id required"}
                        else:
                            sid = str(uuid.uuid4())
                            db.insert_row("Chat_Sessions",
                                ["id","user_id","model_version_id","title"],
                                [sid, uid, mid, title])
                            resp = {"status":"ok","session_id":sid,"title":title}

                # ── GET CHATS ──────────────────────────────────
                elif cmd == "get_chats":
                    uid = _sess_get(msg.get("session_token"))
                    if not uid:
                        resp = {"status":"error","message":"Invalid session"}
                    else:
                        rows = db.get_rows_from_table_with_value("Chat_Sessions","user_id",uid)
                        resp = {"status":"ok","chats":[
                            {"id":r[0],"model_id":r[2],"title":r[3],
                             "updated_at":str(r[5]) if r[5] else str(r[4])}
                            for r in rows]}

                # ── RENAME CHAT ────────────────────────────────
                elif cmd == "rename_chat":
                    uid = _sess_get(msg.get("session_token"))
                    if not uid:
                        resp = {"status":"error","message":"Invalid session"}
                    else:
                        cid = msg.get("chat_session_id")
                        new_title = msg.get("title","").strip()
                        if not cid or not new_title:
                            resp = {"status":"error","message":"chat_session_id and title required"}
                        else:
                            rows = db.get_rows_from_table_with_value("Chat_Sessions","id",cid)
                            if not rows or rows[0][1] != uid:
                                resp = {"status":"error","message":"Chat not found"}
                            else:
                                c = db.conn.cursor()
                                c.execute("UPDATE Chat_Sessions SET title=%s WHERE id=%s",(new_title,cid))
                                db.conn.commit()
                                resp = {"status":"ok","title":new_title}

                # ── DELETE CHAT ────────────────────────────────
                elif cmd == "delete_chat":
                    uid = _sess_get(msg.get("session_token"))
                    if not uid:
                        resp = {"status":"error","message":"Invalid session"}
                    else:
                        cid = msg.get("chat_session_id")
                        rows = db.get_rows_from_table_with_value("Chat_Sessions","id",cid)
                        if not rows or rows[0][1] != uid:
                            resp = {"status":"error","message":"Chat not found"}
                        else:
                            c = db.conn.cursor()
                            c.execute("DELETE FROM Chat_Messages WHERE session_id=%s",(cid,))
                            c.execute("DELETE FROM Chat_Sessions WHERE id=%s",(cid,))
                            db.conn.commit()
                            resp = {"status":"ok"}

                # ── GET HISTORY ────────────────────────────────
                elif cmd == "get_history":
                    uid = _sess_get(msg.get("session_token"))
                    if not uid:
                        resp = {"status":"error","message":"Invalid session"}
                    else:
                        cid = msg.get("chat_session_id")
                        rows = db.get_rows_from_table_with_value("Chat_Messages","session_id",cid)
                        resp = {"status":"ok","messages":[
                            {"role":r[2],"content":r[3],"created_at":str(r[5])} for r in rows]}

                # ── ASK AI ─────────────────────────────────────
                elif cmd == "ask_ai":
                    uid = _sess_get(msg.get("session_token"))
                    if not uid:
                        resp = {"status":"error","message":"Invalid session"}
                    else:
                        cid    = msg.get("chat_session_id")
                        prompt = msg.get("message","").strip()
                        if not prompt:
                            resp = {"status":"error","message":"Empty message"}
                        elif not cid:
                            resp = {"status":"error","message":"chat_session_id required"}
                        else:
                            sr = db.get_rows_from_table_with_value("Chat_Sessions","id",cid)
                            if not sr:
                                resp = {"status":"error","message":"Chat session not found"}
                            else:
                                mr = db.get_rows_from_table_with_value("Model_Versions","id",sr[0][2])
                                if not mr:
                                    resp = {"status":"error","message":"Model not found"}
                                else:
                                    m = mr[0]
                                    # m: id, model_key, display_name, gguf_filename, description, max_new_tokens, ...
                                    model_key      = m[1]
                                    gguf_filename  = m[3]
                                    max_new_tokens = m[5]

                                    # Save user message
                                    db.insert_row("Chat_Messages",
                                        ["id","session_id","role","content"],
                                        [str(uuid.uuid4()), cid, "user", prompt])

                                    # Run local inference (this is the slow part on CPU)
                                    ai_text, latency_ms = generate_response(
                                        model_key, gguf_filename, max_new_tokens, prompt)

                                    # Save assistant reply
                                    db.insert_row("Chat_Messages",
                                        ["id","session_id","role","content","latency_ms"],
                                        [str(uuid.uuid4()), cid, "assistant", ai_text, latency_ms])

                                    # Auto-title first message
                                    if sr[0][3] == "New Chat":
                                        t = prompt[:45] + ("…" if len(prompt) > 45 else "")
                                        c = db.conn.cursor()
                                        c.execute("UPDATE Chat_Sessions SET title=%s WHERE id=%s",(t,cid))
                                        db.conn.commit()

                                    resp = {"status":"ok","request":prompt,
                                            "response":ai_text,"latency_ms":latency_ms}

                # ── GET SERVER STATS (admin only) ──────────────
                elif cmd == "get_server_stats":
                    uid = _sess_get(msg.get("session_token"))
                    if not uid:
                        resp = {"status":"error","message":"Invalid session"}
                    else:
                        # Check user role
                        rows = db.get_rows_from_table_with_value("clients", "id", uid)
                        if not rows or rows[0][4] != 2:  # role must be 2
                            resp = {"status":"error","message":"Unauthorized - admin access required"}
                        else:
                            stats = _get_stats()
                            with _SESS_LOCK:
                                stats["online_users"] = len(_SESSIONS)
                            with _ddos_lock:
                                stats["blacklisted_ips"] = len(_ip_blacklist)
                            
                            # Get all users
                            all_users = db.get_all_rows("clients")
                            users_list = [
                                {"display_name": u[2], "role": u[4], 
                                 "created_at": str(u[6]), "is_active": bool(u[5])}
                                for u in all_users
                            ]
                            
                            resp = {"status":"ok","stats":stats,"users":users_list}

                # ── LOGOUT ─────────────────────────────────────
                elif cmd == "logout":
                    _sess_del(msg.get("session_token"))
                    resp = {"status":"ok"}

            except Exception as inner:
                traceback.print_exc()
                resp = {"status":"error","message":f"Server error: {inner}"}

            _send(conn, resp)

    except Exception as exc:
        print(f"[ERROR] {addr}: {exc}")
    finally:
        _conn_release(ip)
        _update_stat("active_connections", _get_stats()["active_connections"] - 1)
        _log_activity(f"Disconnected: {ip}")
        try: conn.close()
        except: pass
        if db:
            try: db.close()
            except: pass
        print(f"[INFO] Closed: {addr}")


# ─────────────────────────────────────────────────────────────────
#  Startup
# ─────────────────────────────────────────────────────────────────
def _init_db():
    os.makedirs(MODELS_DIR, exist_ok=True)
    db = _make_db()
    db.create_database(DB_CONFIG["database"])
    db.reconnect(DB_CONFIG["database"])
    create_all_tables(db)
    seed_models(db)
    db.close()
    print("[INFO] Database ready.")


def start_server():
    global _MONITOR_WINDOW
    _init_db()
    
    # Launch monitor GUI in separate thread
    def monitor_thread():
        global _MONITOR_WINDOW
        _MONITOR_WINDOW = ServerMonitor()
        _MONITOR_WINDOW.run()
    
    threading.Thread(target=monitor_thread, daemon=True).start()
    print("[INFO] Server monitor launched")
    time.sleep(0.5)  # Give monitor time to initialize
    
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile="cert.pem", keyfile="key.pem")
    print(f"[INFO] Cyber AI Server on {IP}:{PORT}  (SSL/TLS encrypted)")
    _log_activity("Server started")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((IP, PORT))
        s.listen(128)
        while True:
            cs, addr = s.accept()
            ip = addr[0]
            ok, reason = _conn_check(ip)
            if not ok:
                print(f"[DDOS] Rejected {addr}: {reason}")
                try: cs.close()
                except: pass
                continue
            try:
                ss = ctx.wrap_socket(cs, server_side=True)
            except ssl.SSLError as e:
                print(f"[WARN] SSL failed {addr}: {e}")
                _conn_release(ip)
                continue
            threading.Thread(target=handle_client, args=(ss,addr), daemon=True).start()


if __name__ == "__main__":
    start_server()