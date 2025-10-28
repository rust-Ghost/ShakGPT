# server.py
import socket
import threading
import tkinter as tk
from tkinter import Label, scrolledtext, Toplevel, Listbox, Button
from constants import IP, PORT
from db_manager import DatabaseManager
from create_tables import create_all_tables, populate_media_menu
from hide_png import DataHider
from decode_png import ImageExtractor
from datetime import datetime
from PIL import Image, ImageTk
import os
import pygame
import time
from encrypt import Encryption
import random

class Server:
    def __init__(self):
        self.db_manager = DatabaseManager("localhost", "root", "Kroykan339&&", "mysql")
        create_all_tables(self.db_manager)
        populate_media_menu(self.db_manager)
        self.encryptor = Encryption()
        self.root = tk.Tk()
        self.root.withdraw()
        self.log_text = None
        self.client_listbox = None
        self.bg_image = None
        self.client_details_images = {}

    def play_audio(self):
        try:
            pygame.mixer.init()
            pygame.mixer.music.load(r"C:\Users\Cyber_User\Documents\School\Final Project - Maria\Summer Project\alin\intro.mp3")
            pygame.mixer.music.play()
            pygame.mixer.music.queue(r"C:\Users\Cyber_User\Documents\School\Final Project - Maria\Summer Project\alin\montana skies.mp3")
        except:
            return

    def update_gui_log(self, message):
        if not self.log_text:
            return
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.config(state=tk.DISABLED)
        self.log_text.yview(tk.END)

    def update_client_list(self):
        if not self.client_listbox:
            return
        self.client_listbox.delete(0, tk.END)
        clients = self.db_manager.get_rows_with_value("clients", "1", "1")
        for client in clients:
            self.client_listbox.insert(tk.END, client[0])

    def show_client_details(self, client_id):
        client_data = self.db_manager.get_rows_with_value("clients", "client_id", client_id)
        if not client_data:
            return
        client = client_data[0]
        details_window = Toplevel()
        details_window.title(f"Client {client_id} Details")
        details_window.geometry("400x350")
        try:
            bg_image = ImageTk.PhotoImage(Image.open(r"C:\Users\Cyber_User\Documents\School\Final Project - Maria\Summer Project\alin\logo_cyber.jpeg"))
            bg_label = Label(details_window, image=bg_image)
            bg_label.image = bg_image
            bg_label.place(relwidth=1, relheight=1)
        except:
            pass
        details = [
            f"ID: {client[0]}",
            f"IP: {client[1]}",
            f"Port: {client[2]}",
            f"Last Seen: {client[3]}",
            f"Total Actions: {client[5]}",
            f"Status: {'Existing' if client[5] > 0 else 'New'}"
        ]
        for detail in details:
            lbl = Label(details_window, text=detail, fg='white', bg='black')
            lbl.pack(anchor="w", padx=10, pady=2)
        history_button = Button(details_window, text="History", command=lambda: self.show_client_history(client_id), bg='gray', fg='white')
        history_button.pack(pady=10)

    def show_client_history(self, client_id):
        history_window = Toplevel()
        history_window.title(f"Client {client_id} - History")
        history_window.geometry("600x400")
        try:
            bg_image = ImageTk.PhotoImage(Image.open(r"C:\Users\Cyber_User\Documents\School\Final Project - Maria\Summer Project\alin\logo_cyber.jpeg"))
            bg_label = Label(history_window, image=bg_image)
            bg_label.image = bg_image
            bg_label.place(relwidth=1, relheight=1)
        except:
            pass
        history_label = Label(history_window, text=f"Client {client_id} Image History", font=("Arial", 12, "bold"), fg="white", bg="black")
        history_label.pack(pady=5)
        image_listbox = Listbox(history_window, height=15, width=80, bg="black", fg="white", selectbackground="gray")
        image_listbox.pack(padx=10, pady=5, expand=True, fill="both")
        images = self.db_manager.get_rows_with_value("decrypted_media", "user_id", client_id)
        if not images:
            image_listbox.insert(tk.END, "No images found for this client.")
        else:
            image_paths = [img[2] for img in images]
            for path in image_paths:
                image_listbox.insert(tk.END, path)
            def open_selected_image(event):
                selected_index = image_listbox.curselection()
                if selected_index:
                    selected_path = image_paths[selected_index[0]]
                    os.system(f'"{selected_path}"')
            image_listbox.bind("<Double-Button-1>", open_selected_image)

    def handle_client(self, client_socket, addr):
        client_id = None
        try:
            self.encryptor.send_encrypted_message(client_socket, "USERNAME?")
            username = self.encryptor.receive_encrypted_message(client_socket).strip()
            self.encryptor.send_encrypted_message(client_socket, "PASSWORD?")
            password = self.encryptor.receive_encrypted_message(client_socket).strip()
            existing_client = self.db_manager.get_rows_with_value("clients", "username", username)
            if existing_client:
                stored_password = existing_client[0][7]
                if stored_password != password:
                    self.encryptor.send_encrypted_message(client_socket, "AUTH_FAILED")
                    client_socket.close()
                    return
                else:
                    self.encryptor.send_encrypted_message(client_socket, "WELCOME_BACK")
                    client_id = existing_client[0][0]
            else:
                client_id = str(random.randint(1000, 9999))
                self.db_manager.insert_row(
                    "clients",
                    "(client_id, client_ip, client_port, last_seen, ddos_status, total_sent_media, username, password)",
                    "(%s, %s, %s, %s, %s, %s, %s, %s)",
                    (client_id, addr[0], addr[1], datetime.now(), False, 0, username, password)
                )
                self.encryptor.send_encrypted_message(client_socket, "WELCOME_NEW")
            while True:
                menu_text = "\n1: Hide Data\n2: Decode Data\n3: Encryptor\n4: Statistics\n5: Logout"
                self.update_gui_log(f"Sending menu to client {username}: {menu_text}")
                self.encryptor.send_encrypted_message(client_socket, menu_text)
                option = self.encryptor.receive_encrypted_message(client_socket)
                self.update_gui_log(f"Client {username} chose option: {option}")
                if option == "1":
                    try:
                        hider = DataHider(client_socket, self.db_manager, client_id)
                        result = hider.run()
                        if result:
                            media_id, media_type_id, path = result
                            self.db_manager.insert_decrypted_media(client_id, media_type_id, path)
                            self.encryptor.send_encrypted_message(client_socket, f"Task completed: Data hidden in {path}")
                    except Exception as e:
                        try:
                            self.encryptor.send_encrypted_message(client_socket, f"Error during hiding data: {e}")
                        except:
                            pass
                elif option == "2":
                    try:
                        extractor = ImageExtractor(client_socket, self.db_manager, client_id)
                        media_type_id, path = extractor.run()
                        if path:
                            self.db_manager.insert_decrypted_media(client_id, media_type_id, path)
                            self.encryptor.send_encrypted_message(client_socket, "Task completed: Data decoded (1 image found)")
                        else:
                            self.encryptor.send_encrypted_message(client_socket, "Task completed: No hidden images found")
                    except Exception as e:
                        try:
                            self.encryptor.send_encrypted_message(client_socket, f"Task failed during decoding: {e}")
                        except:
                            pass
                elif option == "3":
                    try:
                        self.encryptor.send_encrypted_message(client_socket, "ENCRYPTOR_READY")
                    except:
                        pass
                elif option == "4":
                    try:
                        stats = self.db_manager.get_rows_with_value("clients", "client_id", client_id)[0]
                        total_actions = stats[5]
                        last_seen = stats[3]
                        msg = f"--- Statistics ---\nTotal Actions: {total_actions}\nLast Seen: {last_seen}\nRecommended: "
                        msg += "Hide data next" if total_actions % 2 == 0 else "Decode hidden images next"
                        self.encryptor.send_encrypted_message(client_socket, msg)
                    except:
                        try:
                            self.encryptor.send_encrypted_message(client_socket, "ERROR_FETCH_STATS")
                        except:
                            pass
                elif option == "5":
                    try:
                        self.encryptor.send_encrypted_message(client_socket, "Logging out...")
                    except:
                        pass
                    break
                else:
                    try:
                        self.encryptor.send_encrypted_message(client_socket, "INVALID_OPTION")
                    except:
                        pass
        except Exception as e:
            self.update_gui_log(f"Error with client {addr}: {e}")
        finally:
            try:
                client_socket.close()
            except:
                pass
            self.update_gui_log(f"Connection with client {addr} closed")

    def start_server(self):
        server_socket = socket.socket()
        server_socket.bind((IP, PORT))
        server_socket.listen()
        self.update_gui_log(f"Server started on {IP}:{PORT}")
        while True:
            client_socket, addr = server_socket.accept()
            threading.Thread(target=self.handle_client, args=(client_socket, addr), daemon=True).start()

    def create_gui(self):
        self.play_audio()
        splash = Toplevel()
        splash.geometry("400x400")
        splash.overrideredirect(True)
        try:
            logo = Image.open(r"C:\Users\Cyber_User\Documents\School\Final Project - Maria\Summer Project\alin\poke.jpg").resize((400, 400))
            logo_photo = ImageTk.PhotoImage(logo)
            label = Label(splash, image=logo_photo)
            label.image = logo_photo
            label.pack()
        except:
            pass
        splash.update()
        time.sleep(2)
        splash.destroy()
        self.root.destroy()
        self.root = tk.Tk()
        self.root.title("Server GUI")
        self.root.geometry("600x600")
        try:
            self.bg_image = ImageTk.PhotoImage(Image.open(r"C:\Users\Cyber_User\Documents\School\Final Project - Maria\Summer Project\alin\mizperamon1.png"))
            bg_label = Label(self.root, image=self.bg_image)
            bg_label.place(relwidth=1, relheight=1)
        except:
            pass
        self.log_text = scrolledtext.ScrolledText(self.root, state=tk.DISABLED, wrap=tk.WORD, height=15, bg='black', fg='white')
        self.log_text.pack(expand=True, fill='both', padx=10, pady=5)
        Label(self.root, text="MASKER Customers", font=("Arial", 14, "bold"), fg="white", bg="black").pack(pady=5)
        self.client_listbox = Listbox(self.root, bg='black', fg='white')
        self.client_listbox.pack(expand=True, fill='both', padx=10, pady=5)
        self.client_listbox.bind("<Double-Button-1>", lambda event: self.show_client_details(self.client_listbox.get(self.client_listbox.curselection())))
        threading.Thread(target=self.start_server, daemon=True).start()
        self.root.mainloop()

if __name__ == "__main__":
    server = Server()
    server.create_gui()
