class Encryption:
    def send_encrypted_message(self, sock, message: str):
        sock.sendall(message[::-1].encode())

    def receive_encrypted_message(self, sock):
        data = sock.recv(4096)
        return data.decode()[::-1]  