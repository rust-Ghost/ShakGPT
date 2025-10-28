import socket
import time
import os
from PIL import Image
import tkinter as tk
from tkinter import simpledialog
from constants import IP, PORT, CHUNK_SIZE
from encrypt import Encryption

CREDENTIALS_FILE = "credentials.txt"

class Client:
    def __init__(self):
        self.decrypted_list_paths = [
            r"C:\Users\Cyber_User\Documents\School\Final Project - Maria\Summer Project\alin\aa.jpg"
        ]
        self.usual_images = [
            r"C:\Users\Cyber_User\Documents\School\Final Project - Maria\Summer Project\alin\bb.jpg",
            r"C:\Users\Cyber_User\Documents\School\Final Project - Maria\Summer Project\alin\cc.jpg",
            r"C:\Users\Cyber_User\Documents\School\Final Project - Maria\Summer Project\alin\dd.jpg"
        ]
        self.client_socket = None
        self.encryptor = Encryption()

    def connect_to_server(self):
        self.client_socket = socket.socket()
        self.client_socket.connect((IP, PORT))
        print("Connected to server")

    def get_credentials(self):
        if os.path.exists(CREDENTIALS_FILE):
            with open(CREDENTIALS_FILE, "r") as f:
                username, password = f.read().strip().split(",")
                return username, password

        # אם אין קובץ – מציגים UI פשוט
        root = tk.Tk()
        root.withdraw()
        username = simpledialog.askstring("Login", "Enter username:", parent=root)
        password = simpledialog.askstring("Login", "Enter password:", show="*", parent=root)
        root.destroy()

        with open(CREDENTIALS_FILE, "w") as f:
            f.write(f"{username},{password}")

        return username, password

    def login(self):
        username, password = self.get_credentials()

        prompt = self.encryptor.receive_encrypted_message(self.client_socket)
        print(prompt)
        self.encryptor.send_encrypted_message(self.client_socket, username)

        prompt = self.encryptor.receive_encrypted_message(self.client_socket)
        print(prompt)
        self.encryptor.send_encrypted_message(self.client_socket, password)

        response = self.encryptor.receive_encrypted_message(self.client_socket)
        print(response)

    def receive_menu(self):
        menu = None
        while not menu:
            try:
                menu = self.encryptor.receive_encrypted_message(self.client_socket)
            except Exception as e:
                print(f"Error receiving menu: {e}")
            if not menu:
                time.sleep(0.1)
        print("\nMenu from server:\n", menu)
        return menu

    def handle_hide_option(self):
        print("\nYou chose to hide data.")
        media_menu = self.encryptor.receive_encrypted_message(self.client_socket)
        print("\nAvailable media to hide data in:\n", media_menu)
        
        selected_media_id = input("Enter the ID of the media you want to hide data in: ")
        self.encryptor.send_encrypted_message(self.client_socket, selected_media_id)

        print("Available files to hide:")
        for i, path in enumerate(self.usual_images):
            print(f"{i + 1}: {path}")
        file_index = int(input("Choose a file by number: ")) - 1

        data_to_hide_path = self.usual_images[file_index]
        print("Data to hide:", data_to_hide_path)
        if not os.path.exists(data_to_hide_path):
            print("File does not exist. Returning to menu.")
            return

        with open(data_to_hide_path, "rb") as file:
            data_to_hide = file.read()

        self.encryptor.send_encrypted_message(self.client_socket, str(len(data_to_hide)))
        self.client_socket.sendall(data_to_hide)

        response = self.encryptor.receive_encrypted_message(self.client_socket)
        print("Server response:", response)

        hidden_media_path = response.split("in ")[-1].strip()
        if os.path.exists(hidden_media_path):
            img = Image.open(hidden_media_path)
            img.show()

    def handle_decode_option(self):
        print("\nYou chose to decode data.")
        media_path = input("Enter full path of file to decode: ").strip()
        if not os.path.exists(media_path):
            print("File does not exist. Returning to menu.")
            return

        with open(media_path, "rb") as file:
            data = file.read()

        self.encryptor.send_encrypted_message(self.client_socket, str(len(data)))
        self.client_socket.sendall(data)

        while True:
            response = self.encryptor.receive_encrypted_message(self.client_socket).strip()
            if response.isdigit():
                num_images = int(response)
                break
            else:
                print("Received unexpected response:", response)
                return

        print(f"Found {num_images} hidden images.")

        for i in range(num_images):
            image_size_str = self.encryptor.receive_encrypted_message(self.client_socket).strip()
            if not image_size_str.isdigit():
                print("Unexpected image size:", image_size_str)
                return
            image_size = int(image_size_str)

            self.encryptor.send_encrypted_message(self.client_socket, "ACK")

            image_data = b''
            while len(image_data) < image_size:
                image_data += self.client_socket.recv(4096)

            decoded_file_path = f"decoded_image_{i + 1}.jpg"
            with open(decoded_file_path, "wb") as file:
                file.write(image_data)
            print(f"Decoded image saved at {decoded_file_path}")
            img = Image.open(decoded_file_path)
            img.show()

    def handle_encrypt_option(self):
        print("\n--- Text Encryptor ---")
        text = input("Enter the text to encrypt: ").strip()
        if not text:
            print("No text entered. Returning to menu.")
            return

        encryption_methods = {
            1: "Reverse Text",
            2: "Caesar Cipher (+3 shift)",
            3: "Simple XOR with key 42"
        }

        print("\nAvailable encryption methods:")
        for num, name in encryption_methods.items():
            print(f"{num}: {name}")

        while True:
            try:
                choice = int(input("Choose an encryption method by number: "))
                if choice in encryption_methods:
                    break
                else:
                    print("Invalid choice, try again.")
            except ValueError:
                print("Please enter a valid number.")

        if choice == 1:
            encrypted_text = text[::-1]
        elif choice == 2:
            encrypted_text = "".join(
                chr((ord(c) - 32 + 3) % 95 + 32) if 32 <= ord(c) <= 126 else c
                for c in text
            )
        elif choice == 3:
            encrypted_text = "".join(chr(ord(c) ^ 42) for c in text)

        print(f"\nEncrypted text ({encryption_methods[choice]}):\n{encrypted_text}\n")

    def run(self):
        self.connect_to_server()
        self.login()

        while True:
            menu = self.receive_menu()
            option = input("Choose an option (1-hide, 2-decode, 3-encryptor, 4-logout): ")
            self.encryptor.send_encrypted_message(self.client_socket, option)

            if option == "1":
                self.handle_hide_option()
            elif option == "2":
                self.handle_decode_option()
            elif option == "3":
                self.handle_encrypt_option()
            elif option == "4":
                print("Logging out...")
                break
            else:
                print("Invalid option, try again.")

        self.client_socket.close()

if __name__ == "__main__":
    client = Client()
    client.run()
