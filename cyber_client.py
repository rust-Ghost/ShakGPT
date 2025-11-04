# cyber_client.py
import socket
import struct
import json
import hashlib
from constants import IP, PORT

HOST = IP
PORT = PORT

def send_json(sock, obj):
    data = json.dumps(obj).encode("utf-8")
    header = struct.pack(">I", len(data))
    sock.sendall(header + data)

def recv_json(sock):
    header = b""
    while len(header) < 4:
        part = sock.recv(4 - len(header))
        if not part:
            return None
        header += part
    msg_len = struct.unpack(">I", header)[0]
    data = b""
    while len(data) < msg_len:
        part = sock.recv(min(4096, msg_len - len(data)))
        if not part:
            raise ConnectionError("Connection closed while reading message")
        data += part
    return json.loads(data.decode("utf-8"))

def print_response(resp):
    if resp["status"] != "ok":
        print(f"Error: {resp.get('message')}")
        return
    if "message" in resp:
        print(f"\nMessage: {resp['message']}\n")
    if "clients" in resp:
        clients = resp["clients"]
        if not clients:
            print("\nNo clients found.\n")
            return
        print("\n=== Clients ===")
        print(f"{'ID':36} | {'Username':15} | {'Email'}")
        print("-"*70)
        for c in clients:
            print(f"{c[0]:36} | {c[1]:15} | {c[2]}")
        print()
    if "request" in resp and "response" in resp:
        print("\n=== AI Response ===")
        print(f"Request: {resp['request']}")
        print(f"Answer : {resp['response']}\n")

def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((HOST, PORT))
        print(f"Connected to server {HOST}:{PORT}")

        while True:
            print("\n--- MENU ---")
            print("1. Add new client")
            print("2. List all clients")
            print("3. Ping")
            print("4. Exit")
            print("5. Ask AI")
            choice = input("Choose an option: ").strip()

            if choice == "1":
                username = input("Enter username: ")
                email = input("Enter email: ")
                password = input("Enter password: ")
                password_hash = hashlib.sha256(password.encode()).hexdigest()
                send_json(s, {"command": "add_client", "username": username, "email": email, "password_hash": password_hash})
                resp = recv_json(s)
                print_response(resp)

            elif choice == "2":
                send_json(s, {"command": "list_clients"})
                resp = recv_json(s)
                print_response(resp)

            elif choice == "3":
                send_json(s, {"command": "ping"})
                resp = recv_json(s)
                print_response(resp)

            elif choice == "4":
                print("Disconnecting")
                break

            elif choice == "5":
                message = input("Enter your question for AI: ")
                send_json(s, {"command": "ask_ai", "message": message})
                resp = recv_json(s)
                print_response(resp)

            else:
                print("Invalid choice")

if __name__ == "__main__":
    main()
