import threading
import socket
import struct
import json
import time

HOST = "127.0.0.1"
PORT = 9921

print_lock = threading.Lock()   # mutex for clean console printing


# ---------- Communication Helpers ----------
def send_json(sock, obj):
    data = json.dumps(obj).encode("utf-8")
    header = struct.pack(">I", len(data))
    sock.sendall(header + data)


def recv_json(sock):
    header = sock.recv(4)
    if len(header) < 4:
        return None
    msg_len = struct.unpack(">I", header)[0]
    data = b""
    while len(data) < msg_len:
        part = sock.recv(msg_len - len(data))
        if not part:
            return None
        data += part
    return json.loads(data.decode("utf-8"))


# ---------- Single Test Client Logic ----------
def test_client(idx):
    username = f"user_{idx}"
    password = "1234"

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((HOST, PORT))

        # --- REGISTER ---
        send_json(sock, {
            "command": "register",
            "username": username,
            "password": password,
            "email": f"{username}@example.com"
        })
        resp = recv_json(sock)

        with print_lock:
            print(f"[Thread {idx}] REGISTER RESPONSE -> {resp}")

        sock.close()
        time.sleep(0.1)

        # reconnect for login
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((HOST, PORT))

        # --- LOGIN ---
        send_json(sock, {
            "command": "login",
            "username": username,
            "password": password
        })
        resp = recv_json(sock)

        with print_lock:
            print(f"[Thread {idx}] LOGIN RESPONSE -> {resp}")

        if not resp or resp.get("status") != "ok":
            with print_lock:
                print(f"[Thread {idx}] LOGIN FAILED. STOPPING.")
            return

        session_token = resp["session_token"]

        # --- ASK AI ---
        send_json(sock, {
            "command": "ask_ai",
            "session_token": session_token,
            "message": "print hello world"
        })

        resp = recv_json(sock)

        with print_lock:
            print(f"[Thread {idx}] AI RESPONSE -> {resp}")

        sock.close()

    except Exception as e:
        with print_lock:
            print(f"[Thread {idx}] ERROR: {e}")


# ---------- Main ----------
if __name__ == "__main__":
    threads = []

    # Create 20 concurrent threads
    for i in range(1, 21):
        t = threading.Thread(target=test_client, args=(i,))
        threads.append(t)
        t.start()

    # Wait for all threads to finish
    for t in threads:
        t.join()

    print("\n=== TEST COMPLETED ===")
