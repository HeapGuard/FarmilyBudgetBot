import os
import socket
import paramiko
from dotenv import load_dotenv

load_dotenv()

hostname = os.getenv("VPS_HOST", "89.169.53.163")
username = os.getenv("VPS_USER", "root")
password = os.getenv("VPS_PASSWORD", "")

def get_local_physical_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.168.1.1", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "192.168.1.3"

local_ip = get_local_physical_ip()
print(f"Connecting to {hostname} (bound to physical IP {local_ip})...")

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    sock.bind((local_ip, 0))
except Exception:
    sock.bind(("0.0.0.0", 0))
sock.connect((hostname, 22))

transport = paramiko.Transport(sock)
transport.start_client()
transport.auth_password(username, password)

client = paramiko.SSHClient()
client._transport = transport

print("Fetching logs...")
stdin, stdout, stderr = client.exec_command("curl -I -k https://144-31-148-179.sslip.io/app")
out_text = stdout.read().decode("utf-8", errors="replace")
print(out_text.encode("ascii", errors="replace").decode("ascii"))

client.close()
