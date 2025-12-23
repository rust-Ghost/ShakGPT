import threading
import socket
import struct
import json
import time
from datetime import datetime

HOST = "127.0.0.1"
PORT = 9921
NUM_THREADS = 20
SOCKET_TIMEOUT = 8.0          # seconds per socket recv/send ops
LOGFILE = "stress_log.txt"

log_lock = threading.Lock()   # mutex for console + file logging


def timestamp():
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def thread_log(tid, stage, data):
    """Write a single line to logfile and print (thread-safe)."""
    line = f"{timestamp()} | Thread-{tid:02d} | {stage} | {data}\n"
    with log_lock:
        print(line, end="")
        with open(LOGFILE, "a", encoding="utf-8") as f:
            f.write(line)


# ---------- Networking helpers ----------
def send_json(sock, obj):
    data = json.dumps(obj).encode("utf-8")
    header = struct.pack(">I", len(data))
    sock.sendall(header + data)


def recv_json(sock):
    header = sock.recv(4)
    if len(header) < 4:
        return None
    length = struct.unpack(">I", header)[0]
    data = b""
    while len(data) < length:
        part = sock.recv(length - len(data))
        if not part:
            return None
        data += part
    return json.loads(data.decode("utf-8"))


# ---------- Worker ----------
def client_worker(tid):
    username = f"user_{tid}"
    password = "pass1234"
    sock = None

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(SOCKET_TIMEOUT)
        sock.connect((HOST, PORT))
    except Exception as e:
        thread_log(tid, "CONNECT-ERROR", repr(e))
        try:
            if sock:
                sock.close()
        except Exception:
            pass
        return

    try:
        # --- REGISTER ---
        try:
            send_json(sock, {
                "command": "register",
                "username": username,
                "password": password,
                "email": f"{username}@example.com"
            })
        except Exception as e:
            thread_log(tid, "SEND-REGISTER-ERROR", repr(e))
            raise

        try:
            resp = recv_json(sock)
        except Exception as e:
            resp = None
            thread_log(tid, "RECV-REGISTER-ERROR", repr(e))

        thread_log(tid, "REGISTER-RESPONSE", resp)

        # If server requires reconnect between commands, you could reconnect here.
        # We'll continue on same socket. If register failed, proceed to login attempt anyway.

        # --- LOGIN ---
        try:
            send_json(sock, {
                "command": "login",
                "username": username,
                "password": password
            })
        except Exception as e:
            thread_log(tid, "SEND-LOGIN-ERROR", repr(e))
            raise

        try:
            resp = recv_json(sock)
        except Exception as e:
            resp = None
            thread_log(tid, "RECV-LOGIN-ERROR", repr(e))

        thread_log(tid, "LOGIN-RESPONSE", resp)

        if not resp or resp.get("status") != "ok":
            thread_log(tid, "STOP", "Login failed — aborting ask_ai")
            return

        session_token = resp.get("session_token")

        # --- ASK AI ---
        try:
            send_json(sock, {
                "command": "ask_ai",
                "message": "print('hello world')",
                "session_token": session_token
            })
        except Exception as e:
            thread_log(tid, "SEND-AI-ERROR", repr(e))
            raise

        try:
            resp = recv_json(sock)
        except Exception as e:
            resp = None
            thread_log(tid, "RECV-AI-ERROR", repr(e))

        thread_log(tid, "AI-RESPONSE", resp)

    except Exception as exc:
        thread_log(tid, "UNHANDLED-EXC", repr(exc))

    finally:
        try:
            sock.close()
        except Exception:
            pass
        thread_log(tid, "DONE", "Connection closed")


# ---------- Main ----------
if __name__ == "__main__":
    # Clear or create logfile
    with open(LOGFILE, "w", encoding="utf-8") as f:
        f.write(f"STRESS TEST START {timestamp()}\n")

    threads = []
    for i in range(1, NUM_THREADS + 1):
        t = threading.Thread(target=client_worker, args=(i,), daemon=True)
        threads.append(t)
        t.start()
        # small stagger to avoid immediate burst — remove if you want maximal concurrency
        time.sleep(0.02)

    # Wait for threads
    for t in threads:
        t.join()

    with open(LOGFILE, "a", encoding="utf-8") as f:
        f.write(f"STRESS TEST END {timestamp()}\n")
    print("\n=== ALL THREADS FINISHED ===")
