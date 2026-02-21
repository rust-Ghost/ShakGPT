from OpenSSL import crypto

CERT_FILE = "cert.pem"
KEY_FILE = "key.pem"

k = crypto.PKey()
k.generate_key(crypto.TYPE_RSA, 4096)

cert = crypto.X509()
cert.get_subject().C = "IL"
cert.get_subject().ST = "Tel Aviv"
cert.get_subject().L = "Tel Aviv"
cert.get_subject().O = "CyberAI"
cert.get_subject().OU = "Dev"
cert.get_subject().CN = "localhost"
cert.set_serial_number(1000)
cert.gmtime_adj_notBefore(0)
cert.gmtime_adj_notAfter(365*24*60*60)  
cert.set_issuer(cert.get_subject())
cert.set_pubkey(k)
cert.sign(k, "sha256")

with open(CERT_FILE, "wb") as f:
    f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))

with open(KEY_FILE, "wb") as f:
    f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, k))

print(f"Created {CERT_FILE} and {KEY_FILE} successfully.")
