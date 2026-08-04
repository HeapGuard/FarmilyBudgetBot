#!/usr/bin/env python3
"""
🚀 Automated One-Click Deploy Script for Family Budget Bot
Usage:
    python deploy.py "Commit message"
    OR simply:
    python deploy.py
"""

import sys
import os
import subprocess
import socket
import paramiko

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HOSTNAME = os.getenv("VPS_HOST", "89.169.53.163")
USERNAME = os.getenv("VPS_USER", "root")
PASSWORD = os.getenv("VPS_PASSWORD", "")
SSH_KEY_PATH = os.getenv("VPS_SSH_KEY", os.path.expanduser("~/.ssh/id_rsa"))

def get_local_physical_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.168.1.1", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "192.168.1.3"

def run_local(cmd):
    print(f"\n💻 [LOCAL] {cmd}")
    res = subprocess.run(cmd, shell=True)
    if res.returncode != 0:
        print(f"⚠️ Warning: Command '{cmd}' exited with code {res.returncode}")

def run_ssh(client, cmd):
    print(f"\n☁️ [VPS] {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd, get_pty=True)
    while True:
        line = stdout.readline()
        if not line:
            break
        print(line, end="")
    return stdout.channel.recv_exit_status()

def main():
    commit_msg = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "feat: update and deploy to VPS"

    print("=======================================================")
    print("🚀 STARTING AUTOMATED DEPLOYMENT TO VPS")
    print("=======================================================")

    # Step 1: Git Add, Commit, Push
    run_local("git add .")
    run_local(f'git commit -m "{commit_msg}"')
    run_local("git push origin main")

    # Step 2: Connect to VPS
    local_ip = get_local_physical_ip()
    print(f"\n📡 Connecting to VPS {HOSTNAME} (bound to physical IP {local_ip})...")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((local_ip, 0))
    except Exception:
        sock.bind(("0.0.0.0", 0))
    sock.connect((HOSTNAME, 22))

    transport = paramiko.Transport(sock)
    transport.start_client()
    authenticated = False
    if os.path.exists(SSH_KEY_PATH):
        try:
            key = paramiko.RSAKey.from_private_key_file(SSH_KEY_PATH)
            transport.auth_publickey(USERNAME, key)
            if transport.is_authenticated():
                authenticated = True
                print("🔑 Authenticated using SSH Private Key!")
        except Exception as e:
            print(f"ℹ️ SSH key auth skipped: {e}")
    if not authenticated and PASSWORD:
        try:
            transport.auth_password(USERNAME, PASSWORD)
            if transport.is_authenticated():
                authenticated = True
                print("🔑 Authenticated using Password from VPS_PASSWORD env!")
        except Exception as e:
            print(f"ℹ️ Password auth failed: {e}")

    if not authenticated:
        print("❌ Authentication failed! Please set VPS_PASSWORD in your local .env file or setup an SSH Key.")
        sys.exit(1)

    print("✅ Authenticated via SSH!")
    client = paramiko.SSHClient()
    client._transport = transport

    # Step 3: Pull latest code and rebuild Docker container on VPS
    run_ssh(client, "cd /root/app/FarmilyBudgetBot && git fetch origin main && git reset --hard origin/main")

    # Step 4: Ensure DEBUG=false on production (critical for auth security)
    run_ssh(client, "cd /root/app/FarmilyBudgetBot && sed -i 's/^DEBUG=true/DEBUG=false/' .env && grep '^DEBUG=' .env")

    # Step 5: Rebuild and restart Docker containers without using stale Docker layer cache
    run_ssh(client, "cd /root/app/FarmilyBudgetBot && docker compose --profile web build --no-cache app && docker compose --profile web up -d --force-recreate")
    run_ssh(client, "docker ps")

    transport.close()
    print("\n=======================================================")
    print("🎉 DEPLOYMENT COMPLETE!")
    print("🌐 Web App URL: https://89-169-53-163.sslip.io/app")
    print("=======================================================")

if __name__ == "__main__":
    main()
