import socket
import os
import random
from PIL import Image
from constants import IP, PORT, CHUNK_SIZE
from encrypt import Encryption

class Client:
    def __init__(self):
        self.decrypted_list_paths = [
            r"C:\Users\maria\OneDrive\Dokumenti\סייבר חומרים\stegonagraphy\mail_photo.jpg"
        ]
        self.usual_images = [
            r"C:\Users\maria\OneDrive\Pictures\chateau\IMG_3495.jpg",
            r"C:\Users\maria\OneDrive\Pictures\chateau\REST1.png",
            r"C:\Users\maria\OneDrive\Pictures\mitzperamon3.jpg"
        ]
        self.client_socket = None
        self.encryptor = Encryption()

    def connect_to_server(self):
        try:
            self.client_socket = socket.socket()
            self.client_socket.connect((IP, PORT))
            print("Connected to server")
        except Exception as e:
            print(f"Error connecting to server: {e}")
            self.client_socket = None

    def send_client_id(self):
        client_id = str(random.randint(1, 6))
        print("The client id ", client_id)
        self.encryptor.send_encrypted_message(self.client_socket, client_id)
        server_response = self.encryptor.receive_encrypted_message(self.client_socket)
        print(server_response)

    def receive_menu(self):
        try:
            menu = self.encryptor.receive_encrypted_message(self.client_socket)
            print("\nOptions from server:\n")
            print(menu)
            return menu
        except Exception as e:
            print(f"Error receiving menu: {e}")
            return None

    def handle_hide_option(self):
        print("\nYou chose to hide data.")
        
        # Receive media menu
        media_menu = self.encryptor.receive_encrypted_message(self.client_socket)
        if "No media options available." in media_menu:
            print("No media options available to hide data. Returning to menu.")
            return

        print("\nAvailable media to hide data in:\n")
        print(media_menu)

        # Select media and inform server
        selected_media_id = str(random.randint(1, 4))
        self.encryptor.send_encrypted_message(self.client_socket, selected_media_id)

        data_to_hide_path = random.choice(self.usual_images)
        print("Data to hide:", data_to_hide_path)

        if not os.path.exists(data_to_hide_path):
            print("File to hide does not exist. Returning to menu.")
            return

        # Read binary file content
        with open(data_to_hide_path, "rb") as file:
            data_to_hide = file.read()

        # Send file size (encrypted)
        self.encryptor.send_encrypted_message(self.client_socket, str(len(data_to_hide)))

        # Send file content (raw, unencrypted)
        self.client_socket.sendall(data_to_hide)

        # Receive server response (encrypted)
        response = self.encryptor.receive_encrypted_message(self.client_socket)
        print(response)

        hidden_media_path = response.split("in ")[-1].strip()
        if os.path.exists(hidden_media_path):
            try:
                img = Image.open(hidden_media_path)
                img.show()
            except Exception as e:
                print(f"Error opening the hidden media: {e}")

    def handle_decode_option(self):
        print("\nYou chose to decode data.")
        media_path = random.choice(self.decrypted_list_paths)
        print("Decrypted file chosen:", media_path)

        if not os.path.exists(media_path):
            print("File does not exist. Returning to menu.")
            return

        with open(media_path, "rb") as file:
            data = file.read()

        # Send length encrypted
        self.encryptor.send_encrypted_message(self.client_socket, str(len(data)))

        # Send raw binary data (unencrypted)
        self.client_socket.sendall(data)

        # Receive results
        num_images = int(self.encryptor.receive_encrypted_message(self.client_socket))
        print(f"Found {num_images} hidden images.")

        for i in range(num_images):
            image_size = int(self.encryptor.receive_encrypted_message(self.client_socket))
            self.encryptor.send_encrypted_message(self.client_socket, "ACK")

            image_data = b''
            while len(image_data) < image_size:
                image_data += self.client_socket.recv(4096)

            decoded_file_path = f"decoded_image_{i + 1}.jpg"
            with open(decoded_file_path, "wb") as file:
                file.write(image_data)

            print(f"Decoded image saved at {decoded_file_path}")
            if os.path.exists(decoded_file_path):
                try:
                    img = Image.open(decoded_file_path)
                    img.show()
                except Exception as e:
                    print(f"Error opening the decoded image: {e}")

    def run(self):
        self.connect_to_server()
        if not self.client_socket:
            return

        self.send_client_id()

        while True:
            menu = self.receive_menu()
            if not menu:
                break

            option = str(random.randint(1, 3))
            print("Chosen option:", option)
            self.encryptor.send_encrypted_message(self.client_socket, option)

            if option == "1":
                self.handle_hide_option()
            elif option == "2":
                self.handle_decode_option()
            elif option == "3":
                print("Logging out...")
                break
            else:
                print("Invalid option chosen.")

        self.client_socket.close()

if __name__ == "__main__":
    client = Client()
    client.run()