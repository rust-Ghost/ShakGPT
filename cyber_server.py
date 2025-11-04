# cyber_server.py
import socket
import threading
import json
import uuid
import struct
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch
from db_manager import DatabaseManager
from create_tables import create_all_tables

HOST = "127.0.0.1"
PORT = 9921

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "Kroykan339&&",
    "database": "private_ai_db"
}

# Initialize DB
DB = DatabaseManager(
    host=DB_CONFIG["host"],
    user=DB_CONFIG["user"],
    password=DB_CONFIG["password"]
)

def init_db():
    DB.create_database(DB_CONFIG["database"])
    DB.reconnect(DB_CONFIG["database"])
    create_all_tables(DB)

# Load a more powerful code-generation model
print("Loading code generation AI model...")
tokenizer = AutoTokenizer.from_pretrained("Salesforce/codegen-350M-mono")
model = AutoModelForCausalLM.from_pretrained("Salesforce/codegen-350M-mono")
model.eval()
print("AI model loaded!")

# Helper functions for length-prefixed JSON
def recv_json(conn):
    header = conn.recv(4)
    if len(header) < 4:
        return None
    msg_len = struct.unpack(">I", header)[0]
    data = b""
    while len(data) < msg_len:
        part = conn.recv(msg_len - len(data))
        if not part:
            raise ConnectionError("Connection closed while reading message")
        data += part
    return json.loads(data.decode("utf-8"))

def send_json(conn, obj):
    data = json.dumps(obj).encode("utf-8")
    header = struct.pack(">I", len(data))
    conn.sendall(header + data)

# Generate Python code with validation
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
    # Try to validate syntax
    try:
        compile(code, "<string>", "exec")
    except SyntaxError as e:
        code += f"\n# SyntaxError detected: {e}"
    return code

# Handle client connection
def handle_client(conn, addr):
    print(f"New connection: {addr}")
    try:
        while True:
            try:
                message = recv_json(conn)
            except ConnectionError:
                break
            except json.JSONDecodeError:
                print(f"[{addr}] Invalid JSON received")
                send_json(conn, {"status": "error", "message": "Invalid JSON"})
                continue

            response = {"status": "error", "message": "Unknown command"}
            command = message.get("command")

            if command == "ping":
                response = {"status": "ok", "message": "pong"}

            elif command == "list_clients":
                clients = DB.get_all_rows("clients")
                response = {"status": "ok", "clients": clients}

            elif command == "add_client":
                username = message.get("username")
                email = message.get("email", "")
                password_hash = message.get("password_hash", "")
                client_id = str(uuid.uuid4())

                DB.insert_row(
                    "clients",
                    "(id, username, email, password_hash)",
                    "(%s, %s, %s, %s)",
                    (client_id, username, email, password_hash)
                )
                response = {"status": "ok", "message": "Client added.", "id": client_id}

            elif command == "ask_ai":
                user_message = message.get("message", "")
                print(f"[{addr}] AI Code Request: {user_message}")

                # Generate Python code
                ai_response = generate_code(user_message)
                print(f"[{addr}] AI Code Response:\n{ai_response}")

                response = {
                    "status": "ok",
                    "request": user_message,
                    "response": ai_response
                }

            send_json(conn, response)

    except Exception as e:
        print(f"Error with client {addr}: {e}")
    finally:
        conn.close()
        print(f"Connection closed: {addr}")

# Start server
def start_server():
    init_db()
    print(f"Server listening on {HOST}:{PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

if __name__ == "__main__":
    start_server()
