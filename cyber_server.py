# cyber_server.py
import socket
import threading
import json
import struct
import uuid
from datetime import datetime
import bcrypt
import traceback
from db_manager import DatabaseManager
from create_tables import create_all_tables
from constants import DB_CONFIG, IP, PORT

# Try to import transformers; if unavailable, we'll fallback to echo responses
USE_AI = True
try:
    from transformers import AutoTokenizer, AutoModelForCausalLM
    import torch
except Exception as e:
    print(f"[WARN] transformers/torch not available or failed to import: {e}")
    USE_AI = False

# ----------------- Server-wide helpers -----------------
# Session store + lock to protect it across threads
SESSIONS = {}             # session_token -> user_id
SESSIONS_LOCK = threading.Lock()

def add_session(token, user_id):
    with SESSIONS_LOCK:
        SESSIONS[token] = user_id

def get_session(token):
    with SESSIONS_LOCK:
        return SESSIONS.get(token)

def del_session(token):
    with SESSIONS_LOCK:
        SESSIONS.pop(token, None)

# ----------------- AI model (optional) -----------------
if USE_AI:
    try:
        print("Loading AI model (this may take time)...")
        tokenizer = AutoTokenizer.from_pretrained("Salesforce/codegen-350M-mono")
        model = AutoModelForCausalLM.from_pretrained("Salesforce/codegen-350M-mono")
        model.eval()
        # If GPU is available, you could call model.to('cuda') — optional
        print("AI model loaded.")
    except Exception as e:
        print(f"[WARN] Failed to load AI model: {e}\nFalling back to simple echo responses.")
        USE_AI = False

def generate_code(prompt, max_length=200):
    """
    Generate code with the model if available, otherwise return simple echo text.
    """
    if not USE_AI:
        return f"(AI stub) Echo: {prompt}"
    try:
        prompt_text = f"# Python code requested:\n# {prompt}\n"
        inputs = tokenizer(prompt_text, return_tensors="pt")
        outputs = model.generate(
            input_ids=inputs["input_ids"],
            attention_mask=inputs.get("attention_mask"),
            max_length=max_length,
            do_sample=True,
            temperature=0.7,
            top_p=0.95,
            no_repeat_ngram_size=2,
            pad_token_id=tokenizer.eos_token_id
        )
        code = tokenizer.decode(outputs[0], skip_special_tokens=True)
        # Try a simple compile check — if fails, include the compile error in returned string
        try:
            compile(code, "<string>", "exec")
        except SyntaxError as se:
            code += f"\n# SyntaxError detected: {se}"
        return code
    except Exception as e:
        # On generation failure, return an informative fallback
        return f"(AI generation error) {e}"

# ----------------- Database helper -----------------
def make_db_connection():
    """
    Create and return a fresh DatabaseManager connected to the target database.
    Each thread should call this to get its own DB connection.
    """
    db = DatabaseManager(
        host=DB_CONFIG["host"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"]
    )
    # Ensure we're connected to the right database
    if DB_CONFIG.get("database"):
        try:
            db.reconnect(DB_CONFIG["database"])
        except Exception:
            # If reconnect fails, it will raise and the caller will handle it
            raise
    return db

# ----------------- Socket JSON helpers -----------------
def recv_json(conn):
    """Receive a length-prefixed JSON object. Return None if connection closed or invalid."""
    try:
        header = conn.recv(4)
        if len(header) < 4:
            return None
        msg_len = struct.unpack(">I", header)[0]
        data = b""
        while len(data) < msg_len:
            part = conn.recv(msg_len - len(data))
            if not part:
                return None
            data += part
        return json.loads(data.decode("utf-8"))
    except Exception:
        return None

def send_json(conn, obj):
    """Send a JSON response; swallow errors but log them."""
    try:
        data = json.dumps(obj).encode("utf-8")
        header = struct.pack(">I", len(data))
        conn.sendall(header + data)
    except Exception as e:
        # If sending fails, there's not much the server can do — log and move on.
        print(f"[WARN] send_json failed: {e}")

# ----------------- Main client handler (per-thread) -----------------
def handle_client(conn, addr):
    """
    Each client handler gets its own DB connection (db).
    Any exceptions produce an error response to the client, so client never sees `None`.
    """
    print(f"[INFO] New connection from {addr}")
    db = None
    try:
        # Create per-thread DB connection
        try:
            db = make_db_connection()
        except Exception as e:
            print(f"[ERROR] Could not create DB connection for {addr}: {e}")
            send_json(conn, {"status": "error", "message": f"DB connection error: {e}"})
            return

        while True:
            message = recv_json(conn)
            if message is None:
                # Client closed connection or invalid message
                break

            # Defensive: ensure message is a dict
            if not isinstance(message, dict):
                send_json(conn, {"status": "error", "message": "Invalid message format"})
                continue

            try:
                cmd = message.get("command")
                # Default response if nothing matches
                response = {"status": "error", "message": "Unknown command"}

                # ---------- REGISTER ----------
                if cmd == "register":
                    username = message.get("username", "").strip()
                    password = message.get("password", "").strip()
                    email = message.get("email", f"{username}@example.com").strip()

                    if not username or not password:
                        response = {"status": "error", "message": "Username and password required"}
                    else:
                        try:
                            existing = db.get_rows_from_table_with_value("clients", "username", username)
                        except Exception as e:
                            # Provide DB error back to client
                            response = {"status": "error", "message": f"DB query error: {e}"}
                        else:
                            if existing:
                                response = {"status": "error", "message": "Username already exists"}
                            else:
                                try:
                                    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
                                    client_id = str(uuid.uuid4())
                                    db.insert_row(
                                        "clients",
                                        "(id, username, email, password_hash)",
                                        "(%s, %s, %s, %s)",
                                        (client_id, username, email, password_hash)
                                    )
                                    response = {"status": "ok", "message": "Registered successfully", "id": client_id}
                                except Exception as e:
                                    response = {"status": "error", "message": f"DB insert error: {e}"}

                # ---------- LOGIN ----------
                elif cmd == "login":
                    username = message.get("username", "").strip()
                    password = message.get("password", "").strip()
                    if not username or not password:
                        response = {"status": "error", "message": "Username and password required"}
                    else:
                        try:
                            rows = db.get_rows_from_table_with_value("clients", "username", username)
                        except Exception as e:
                            response = {"status": "error", "message": f"DB query error: {e}"}
                        else:
                            if not rows:
                                response = {"status": "error", "message": "User not found"}
                            else:
                                user = rows[0]
                                stored_hash = user[4]  # password_hash column
                                try:
                                    if bcrypt.checkpw(password.encode(), stored_hash.encode()):
                                        user_id = user[0]
                                        session_token = str(uuid.uuid4())
                                        add_session(session_token, user_id)
                                        # update last login
                                        try:
                                            db.conn.cursor().execute(
                                                "UPDATE clients SET last_login_at=%s WHERE id=%s",
                                                (datetime.now(), user_id)
                                            )
                                            db.conn.commit()
                                        except Exception as e:
                                            # Non-fatal: log but still return success
                                            print(f"[WARN] Could not update last_login_at for {username}: {e}")
                                        response = {"status": "ok", "message": "Login successful", "session_token": session_token}
                                    else:
                                        response = {"status": "error", "message": "Invalid password"}
                                except Exception as e:
                                    response = {"status": "error", "message": f"Password check error: {e}"}

                # ---------- ASK AI ----------
                elif cmd == "ask_ai":
                    token = message.get("session_token")
                    if not token:
                        response = {"status": "error", "message": "session_token required"}
                    else:
                        user_id = get_session(token)
                        if not user_id:
                            response = {"status": "error", "message": "Invalid or expired session_token; please login"}
                        else:
                            user_message = message.get("message", "")
                            # generate code or fallback text
                            try:
                                ai_out = generate_code(user_message)
                                response = {"status": "ok", "request": user_message, "response": ai_out}
                            except Exception as e:
                                response = {"status": "error", "message": f"AI error: {e}"}

                # ---------- PING (simple health check) ----------
                elif cmd == "ping":
                    response = {"status": "ok", "message": "pong"}

                # ---------- LIST CLIENTS (requires login) ----------
                elif cmd == "list_clients":
                    token = message.get("session_token")
                    user_id = get_session(token)
                    if not user_id:
                        response = {"status": "error", "message": "Login required"}
                    else:
                        try:
                            clients = db.get_all_rows("clients")
                            response = {"status": "ok", "clients": clients}
                        except Exception as e:
                            response = {"status": "error", "message": f"DB error: {e}"}

                # Send response (always)
                send_json(conn, response)

            except Exception as inner:
                # Catch handler-level exceptions and send to client
                traceback.print_exc()
                send_json(conn, {"status": "error", "message": f"Server handler error: {inner}"})

    except Exception as e:
        print(f"[ERROR] Unhandled exception for client {addr}: {e}")
        traceback.print_exc()
    finally:
        try:
            conn.close()
        except Exception:
            pass
        if db:
            try:
                db.close()
            except Exception:
                pass
        print(f"[INFO] Connection closed: {addr}")

# ----------------- Startup / main loop -----------------
def init_db_once():
    # Create initial DB (only once)
    try:
        # Use a temporary connection to initialize schema
        temp_db = make_db_connection()
        try:
            temp_db.create_database(DB_CONFIG["database"])
        except Exception:
            # ignore if exists or if create fails (next reconnect will ensure)
            pass
        temp_db.reconnect(DB_CONFIG["database"])
        create_all_tables(temp_db)
        temp_db.close()
        print("[INFO] Database initialized.")
    except Exception as e:
        print(f"[ERROR] Failed to initialize DB: {e}")
        raise

def start_server():
    init_db_once()
    print(f"[INFO] Server listening on {IP}:{PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((IP, PORT))
        s.listen()
        try:
            while True:
                conn, addr = s.accept()
                t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
                t.start()
        except KeyboardInterrupt:
            print("[INFO] Server shutting down (KeyboardInterrupt).")

if __name__ == "__main__":
    start_server()
