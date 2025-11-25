import socket
import threading
import json
import struct
import uuid
from datetime import datetime
import bcrypt
from db_manager import DatabaseManager
from create_tables import create_all_tables
from constants import DB_CONFIG, IP, PORT
from transformers import AutoTokenizer, AutoModelForCausalLM

# ----------------- Database Init -----------------
DB = DatabaseManager(
    host=DB_CONFIG["host"],
    user=DB_CONFIG["user"],
    password=DB_CONFIG["password"]
)

def init_db():
    DB.create_database(DB_CONFIG["database"])
    DB.reconnect(DB_CONFIG["database"])
    create_all_tables(DB)
    print("Database ready!")

# ----------------- Load AI -----------------
print("Loading AI model...")
tokenizer = AutoTokenizer.from_pretrained("Salesforce/codegen-350M-mono")
model = AutoModelForCausalLM.from_pretrained("Salesforce/codegen-350M-mono")
model.eval()
print("AI model loaded!")

# ----------------- Session Store -----------------
SESSIONS = {}  # session_token -> user_id

# ----------------- Helpers -----------------
def recv_json(conn):
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

def send_json(conn, obj):
    data = json.dumps(obj).encode("utf-8")
    header = struct.pack(">I", len(data))
    conn.sendall(header + data)

def authenticate(session_token):
    return SESSIONS.get(session_token)

def generate_code(prompt, max_length=200):
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
    try:
        compile(code, "<string>", "exec")
    except SyntaxError as e:
        code += f"\n# SyntaxError detected: {e}"
    return code

# ----------------- Client Handler -----------------
def handle_client(conn, addr):
    print(f"New connection: {addr}")
    try:
        while True:
            message = recv_json(conn)
            if not message:
                break

            command = message.get("command")
            response = {"status": "error", "message": "Unknown command"}

            # ---------- REGISTER ----------
            if command == "register":
                username = message.get("username", "").strip()
                password = message.get("password", "").strip()
                email = message.get("email", f"{username}@example.com").strip()

                if not username or not password:
                    response = {"status": "error", "message": "Username and password required"}
                else:
                    existing = DB.get_rows_from_table_with_value("clients", "username", username)
                    if existing:
                        response = {"status": "error", "message": "Username already exists"}
                    else:
                        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
                        client_id = str(uuid.uuid4())
                        DB.insert_row(
                            "clients",
                            "(id, username, email, password_hash)",
                            "(%s, %s, %s, %s)",
                            (client_id, username, email, password_hash)
                        )
                        response = {"status": "ok", "message": "Registered successfully", "id": client_id}

            # ---------- LOGIN ----------
            elif command == "login":
                username = message.get("username", "").strip()
                password = message.get("password", "").strip()
                if not username or not password:
                    response = {"status": "error", "message": "Username and password required"}
                else:
                    rows = DB.get_rows_from_table_with_value("clients", "username", username)
                    if not rows:
                        response = {"status": "error", "message": "User not found"}
                    else:
                        user = rows[0]
                        stored_hash = user[4]
                        if bcrypt.checkpw(password.encode(), stored_hash.encode()):
                            user_id = user[0]
                            session_token = str(uuid.uuid4())
                            SESSIONS[session_token] = user_id
                            DB.conn.cursor().execute(
                                "UPDATE clients SET last_login_at=%s WHERE id=%s",
                                (datetime.now(), user_id)
                            )
                            DB.conn.commit()
                            response = {"status": "ok", "message": "Login successful", "session_token": session_token}
                        else:
                            response = {"status": "error", "message": "Invalid password"}

            # ---------- ASK AI ----------
            elif command == "ask_ai":
                session_token = message.get("session_token")
                user_id = authenticate(session_token)
                if not user_id:
                    response = {"status": "error", "message": "You must login first"}
                else:
                    user_message = message.get("message", "")
                    ai_response = generate_code(user_message)
                    response = {"status": "ok", "request": user_message, "response": ai_response}

            send_json(conn, response)

    except Exception as e:
        print(f"Error with client {addr}: {e}")
    finally:
        conn.close()
        print(f"Connection closed: {addr}")

# ----------------- Server -----------------
def start_server():
    init_db()
    print(f"Server listening on {IP}:{PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((IP, PORT))
        s.listen()
        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

if __name__ == "__main__":
    start_server()
