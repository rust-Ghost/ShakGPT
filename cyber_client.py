import socket
import struct
import json
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

HOST = "127.0.0.1"
PORT = 9921

def send_json(sock, obj):
    data = json.dumps(obj).encode("utf-8")
    sock.sendall(struct.pack(">I", len(data)) + data)

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

class CyberClientApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Cyber Client")
        self.sock = None
        self.session_token = None
        self.login_window()

    def connect(self):
        if self.sock:
            self.sock.close()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((HOST, PORT))

    def login_window(self):
        self.frame = ttk.Frame(self.root, padding=10)
        self.frame.pack(fill="both", expand=True)

        ttk.Label(self.frame, text="Username:").grid(row=0, column=0)
        self.username_entry = ttk.Entry(self.frame)
        self.username_entry.grid(row=0, column=1)

        ttk.Label(self.frame, text="Password:").grid(row=1, column=0)
        self.password_entry = ttk.Entry(self.frame, show="*")
        self.password_entry.grid(row=1, column=1)

        ttk.Button(self.frame, text="Login", command=self.login).grid(row=2, column=0)
        ttk.Button(self.frame, text="Register", command=self.register).grid(row=2, column=1)

    def login(self):
        try:
            self.connect()
            username = self.username_entry.get().strip()
            password = self.password_entry.get().strip()
            if not username or not password:
                messagebox.showerror("Error", "Username and password required")
                return
            send_json(self.sock, {"command":"login","username":username,"password":password})
            resp = recv_json(self.sock)
            if resp["status"]=="ok":
                self.session_token = resp["session_token"]
                messagebox.showinfo("Login","Logged in successfully!")
                self.show_main_window()
            else:
                messagebox.showerror("Login Failed", resp.get("message"))
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def register(self):
        try:
            self.connect()
            username = self.username_entry.get().strip()
            password = self.password_entry.get().strip()
            if not username or not password:
                messagebox.showerror("Error", "Username and password required")
                return
            send_json(self.sock, {
                "command":"register",
                "username":username,
                "password":password,
                "email":f"{username}@example.com"
            })
            resp = recv_json(self.sock)
            if resp["status"]=="ok":
                messagebox.showinfo("Register","Registered successfully! You can now login.")
            else:
                messagebox.showerror("Register Failed", resp.get("message"))
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def show_main_window(self):
        self.frame.destroy()
        self.frame = ttk.Frame(self.root, padding=10)
        self.frame.pack(fill="both", expand=True)

        ttk.Label(self.frame, text=f"Session: {self.session_token[:8]}...").pack(anchor="w")
        ttk.Label(self.frame, text="Ask AI a question:").pack(anchor="w", pady=(10,0))
        self.ai_input = scrolledtext.ScrolledText(self.frame, height=4)
        self.ai_input.pack(fill="x", pady=5)
        ttk.Button(self.frame, text="Send to AI", command=self.ask_ai).pack(pady=5)
        ttk.Label(self.frame, text="AI Response:").pack(anchor="w", pady=(10,0))
        self.ai_output = scrolledtext.ScrolledText(self.frame, height=12)
        self.ai_output.pack(fill="both", expand=True)

    def ask_ai(self):
        try:
            question = self.ai_input.get(1.0,"end").strip()
            if not question: return
            send_json(self.sock, {"command":"ask_ai","message":question,"session_token":self.session_token})
            resp = recv_json(self.sock)
            self.ai_output.delete(1.0,"end")
            if resp["status"]=="ok":
                self.ai_output.insert("end", f"Request: {resp['request']}\n\nResponse:\n{resp['response']}")
            else:
                self.ai_output.insert("end", f"Error: {resp.get('message')}")
        except Exception as e:
            self.ai_output.insert("end", f"Error: {e}")

if __name__=="__main__":
    root = tk.Tk()
    app = CyberClientApp(root)
    root.mainloop()
