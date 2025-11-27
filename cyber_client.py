import socket
import struct
import json
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

HOST = "127.0.0.1"
PORT = 9921


# ---------------- Networking Helpers ----------------
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


# ---------------- GUI App ----------------
class CyberClientApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Cyber AI Client")
        self.root.geometry("500x420")
        self.root.configure(bg="#1e1e1e")
        self.sock = None
        self.session_token = None

        self.setup_styles()
        self.login_window()

    # ---------------- Styling ----------------
    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure(
            "TFrame",
            background="#1e1e1e"
        )

        style.configure(
            "TLabel",
            background="#1e1e1e",
            foreground="white",
            font=("Segoe UI", 11)
        )

        style.configure(
            "TButton",
            font=("Segoe UI", 11),
            padding=6,
            background="#3A7FF6",
            foreground="white"
        )

        style.map(
            "TButton",
            background=[("active", "#1f5fd6")]
        )

        style.configure(
            "TEntry",
            padding=5,
            font=("Segoe UI", 11)
        )

    def connect(self):
        if self.sock:
            self.sock.close()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((HOST, PORT))

    # ---------------- Login Window ----------------
    def login_window(self):
        self.frame = ttk.Frame(self.root, padding=20)
        self.frame.pack(expand=True)

        ttk.Label(self.frame, text="Welcome to Cyber AI", font=("Segoe UI", 16, "bold")).pack(pady=(0, 20))

        # Username
        ttk.Label(self.frame, text="Username:").pack(anchor="w")
        self.username_entry = ttk.Entry(self.frame, width=30)
        self.username_entry.pack(pady=5)

        # Password
        ttk.Label(self.frame, text="Password:").pack(anchor="w")
        self.password_entry = ttk.Entry(self.frame, width=30, show="*")
        self.password_entry.pack(pady=5)

        # Buttons
        btn_frame = ttk.Frame(self.frame)
        btn_frame.pack(pady=15)

        ttk.Button(btn_frame, text="Login", width=12, command=self.login).grid(row=0, column=0, padx=5)
        ttk.Button(btn_frame, text="Register", width=12, command=self.register).grid(row=0, column=1, padx=5)

    def login(self):
        try:
            self.connect()
            username = self.username_entry.get().strip()
            password = self.password_entry.get().strip()

            if not username or not password:
                messagebox.showerror("Error", "Username and password required")
                return

            send_json(self.sock, {"command": "login", "username": username, "password": password})
            resp = recv_json(self.sock)

            if resp["status"] == "ok":
                self.session_token = resp["session_token"]
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
                "command": "register",
                "username": username,
                "password": password,
                "email": f"{username}@example.com"
            })
            resp = recv_json(self.sock)

            if resp["status"] == "ok":
                messagebox.showinfo("Register", "Registered successfully! You can now login.")
            else:
                messagebox.showerror("Register Failed", resp.get("message"))

        except Exception as e:
            messagebox.showerror("Error", str(e))

    # ---------------- Main Window ----------------
    def show_main_window(self):
        self.frame.destroy()
        self.root.geometry("700x600")

        self.frame = ttk.Frame(self.root, padding=15)
        self.frame.pack(fill="both", expand=True)

        ttk.Label(self.frame, text=f"Session Token: {self.session_token[:10]}...", font=("Segoe UI", 10)).pack(anchor="w")

        ttk.Label(self.frame, text="Ask the AI:", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(10, 5))

        self.ai_input = scrolledtext.ScrolledText(self.frame, height=4, font=("Consolas", 11))
        self.ai_input.pack(fill="x", pady=5)

        ttk.Button(self.frame, text="Send", command=self.ask_ai).pack(pady=8)

        ttk.Label(self.frame, text="AI Response:", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(10, 5))
        self.ai_output = scrolledtext.ScrolledText(self.frame, height=15, font=("Consolas", 11))
        self.ai_output.pack(fill="both", expand=True)

    def ask_ai(self):
        try:
            question = self.ai_input.get(1.0, "end").strip()
            if not question:
                return

            send_json(self.sock, {
                "command": "ask_ai",
                "message": question,
                "session_token": self.session_token
            })

            resp = recv_json(self.sock)
            self.ai_output.delete(1.0, "end")

            if resp["status"] == "ok":
                self.ai_output.insert("end", f">>> {resp['request']}\n\n{resp['response']}")
            else:
                self.ai_output.insert("end", f"Error: {resp.get('message')}")

        except Exception as e:
            self.ai_output.insert("end", f"Error: {e}")


# ---------------- Run App ----------------
if __name__ == "__main__":
    root = tk.Tk()
    app = CyberClientApp(root)
    root.mainloop()
