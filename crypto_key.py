from cryptography.fernet import Fernet

SHARED_SECRET_KEY = Fernet.generate_key()
