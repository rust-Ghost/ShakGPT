CHUNK_SIZE = 4096
IP = "127.0.0.1"
PORT = 9921

DB_CONFIG = {
    "host":     "localhost",
    "user":     "root",
    "password": "Kroykan339&&",
    "database": "mysql"
}

# ── Local AI via llama.cpp (fast CPU inference) ───────────────────────────────
# llama.cpp runs quantized GGUF models at 10-30 tokens/sec on CPU.
# This keeps ALL data private — nothing ever leaves your machine.
#
# SETUP (one time):
#   pip install llama-cpp-python
#
# Then download a GGUF model, e.g.:
#   https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF
#   https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF  (better quality)
#   https://huggingface.co/TheBloke/phi-2-GGUF
#
# Put the .gguf files anywhere and set the paths below.
# Use Q4_K_M quantization — best speed/quality tradeoff on CPU.

MODELS_DIR = "./models"   # folder where your .gguf files live

# How many CPU threads to use for inference (set to your core count)
N_THREADS = 4

# Context window size (tokens). 2048 is safe for low RAM, 4096 for more quality.
N_CTX = 2048