from datetime import datetime
from encrypt import Encryption
from steganography.steganography import Steganography
import os
import mimetypes

class DataHider:
    """
    A class to handle receiving data from a client and hiding it inside a base image using steganography.
    The output image remains a valid image that can be opened with PIL.
    """

    def __init__(self, client_socket, db_manager, user_id):
        """
        Initializes the DataHider with necessary resources.
        """
        self.client_socket = client_socket
        self.db_manager = db_manager
        self.user_id = user_id
        self.encryptor = Encryption()

    def fetch_media_menu(self):
        """
        Retrieves the media menu from the database and sends it to the client.
        :return: The selected media item as a row (tuple), or None if there's no available media.
        """
        media_menu = self.db_manager.get_all_rows("media_menu")
        if not media_menu:
            self.encryptor.send_encrypted_message(self.client_socket, "No media options available.")
            return None

        menu_str = "\n".join([f"{item[0]}: {item[1] or item[2] or item[3]}" for item in media_menu])
        self.encryptor.send_encrypted_message(self.client_socket, menu_str)

        selected_id = self.encryptor.receive_encrypted_message(self.client_socket)
        return next(item for item in media_menu if str(item[0]) == selected_id)

    def receive_data_to_hide(self):
        """
        Receives the size and actual binary data from the client.
        :return: Binary data sent by the client.
        """
        size = int(self.encryptor.receive_encrypted_message(self.client_socket))
        data = b''
        while len(data) < size:
            chunk = self.client_socket.recv(4096)
            if not chunk:
                break
            data += chunk
        return data

    def create_hidden_file(self, media_path, data_to_hide):
        mime_type, _ = mimetypes.guess_type(media_path)
        ext = os.path.splitext(media_path)[1]  # keep same extension
        output_path = f"hidden_{self.user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"

        with open(media_path, "rb") as media_file:
            media_data = media_file.read()

        with open(output_path, "wb") as output_file:
            output_file.write(media_data + data_to_hide)

        return output_path

    def run(self):
        """
        Orchestrates the hiding process.
        :return: Tuple with (media_id, media_type_id, output_path) or None if failed.
        """
        try:
            selected_media = self.fetch_media_menu()
            if not selected_media:
                self.encryptor.send_encrypted_message(self.client_socket, "No valid media selected.")
                return None

            data_to_hide = self.receive_data_to_hide()

            media_path = selected_media[1] or selected_media[2] or selected_media[3]
            if not media_path or not os.path.exists(media_path):
                self.encryptor.send_encrypted_message(self.client_socket, "Error: No valid media path found.")
                return None

            output_path = self.create_hidden_file(media_path, data_to_hide)

            media_type_id = 1  # default type id for images

            # Insert into DB
            self.db_manager.insert_decrypted_media(self.user_id, media_type_id, output_path)

            self.encryptor.send_encrypted_message(
                self.client_socket,
                f"Data successfully hidden in {output_path}"
            )

            return selected_media[0], media_type_id, output_path

        except Exception as e:
            self.encryptor.send_encrypted_message(self.client_socket, f"Hiding failed: {e}")
            return None
