#!/usr/bin/env python3
"""
EarlyBird VPS Automated Deployment Script
Uses sshpass to automate SSH password authentication
"""

import os
import sys
import subprocess
import getpass

# Configuration
VPS_IP = "31.220.73.226"
VPS_USER = "root"
VPS_DIR = "/root/earlybird"
ZIP_FILE = "earlybird_deploy.zip"
LOCAL_DIR = "/home/linux/Earlybird_Github"


def run_command(cmd, check=True):
    """Execute a command and return the result"""
    print(f"\n🔧 Executing: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(f"⚠️  Error output: {result.stderr}")
    if check and result.returncode != 0:
        print(f"❌ Command failed with exit code {result.returncode}")
        sys.exit(1)
    return result


def main():
    print("=" * 60)
    print("🦅 EarlyBird VPS Automated Deployment")
    print("=" * 60)
    print()

    # Ask for SSH password
    password = getpass.getpass("🔐 Inserisci la password SSH per root@31.220.73.226: ")

    # Change to local directory
    os.chdir(LOCAL_DIR)

    # Step 1: Check if zip file exists
    print("\n[1/8] 🔍 Verificando file zip...")
    if not os.path.exists(ZIP_FILE):
        print(f"❌ File {ZIP_FILE} non trovato!")
        sys.exit(1)
    size = os.path.getsize(ZIP_FILE) / (1024 * 1024)
    print(f"✅ File {ZIP_FILE} trovato ({size:.1f} MB)")

    # Step 2: Create directory on VPS
    print("\n[2/8] 📁 Creazione directory sulla VPS...")
    cmd = f"sshpass -p '{password}' ssh -o StrictHostKeyChecking=no {VPS_USER}@{VPS_IP} 'mkdir -p {VPS_DIR} && echo Directory creata con successo'"
    run_command(cmd)

    # Step 3: Transfer zip file to VPS
    print("\n[3/8] 📤 Trasferimento file zip sulla VPS...")
    cmd = f"sshpass -p '{password}' scp -o StrictHostKeyChecking=no {ZIP_FILE} {VPS_USER}@{VPS_IP}:{VPS_DIR}/"
    run_command(cmd)

    # Step 4: Extract zip file on VPS
    print("\n[4/8] 📦 Estrazione file zip sulla VPS...")
    cmd = f"sshpass -p '{password}' ssh -o StrictHostKeyChecking=no {VPS_USER}@{VPS_IP} 'cd {VPS_DIR} && unzip -o {ZIP_FILE} && rm {ZIP_FILE} && echo File estratto con successo'"
    run_command(cmd)

    # Step 5: Create .env file if not exists
    print("\n[5/8] ⚙️  Verifica file .env...")
    cmd = f"sshpass -p '{password}' ssh -o StrictHostKeyChecking=no {VPS_USER}@{VPS_IP} 'cd {VPS_DIR} && if [ ! -f .env ]; then cp .env.template .env && echo File .env creato da template; else echo File .env esistente; fi'"
    run_command(cmd)

    # Step 6: Setup Telegram session (optional)
    print("\n[6/8] 🔐 Setup sessione Telegram (opzionale)...")
    setup_telegram = input("Vuoi configurare la sessione Telegram ora? (y/n): ").strip().lower()
    if setup_telegram == "y":
        print("⚠️  NOTA: La sessione Telegram richiede input interattivo.")
        print("⚠️  Dovrai inserire il numero e il codice OTP nel terminale VPS.")
        cmd = f"sshpass -p '{password}' ssh -o StrictHostKeyChecking=no {VPS_USER}@{VPS_IP} 'cd {VPS_DIR} && python3 setup_telegram_auth.py'"
        run_command(cmd, check=False)  # Don't fail if user cancels
    else:
        print("⚠️  Sessione Telegram non configurata (50% funzionalità)")

    # Step 7: Setup dependencies on VPS
    print("\n[7/8] 🛠️  Setup dipendenze sulla VPS...")
    print("⚠️  Questo potrebbe richiedere 10-15 minuti...")
    cmd = f"sshpass -p '{password}' ssh -o StrictHostKeyChecking=no {VPS_USER}@{VPS_IP} 'cd {VPS_DIR} && bash setup_vps.sh'"
    run_command(cmd, check=False)  # Don't fail on warnings

    # Step 8: Start bot
    print("\n[8/8] 🚀 Avvio del bot...")
    print("⚠️  Il bot verrà avviato in tmux")
    cmd = f"sshpass -p '{password}' ssh -o StrictHostKeyChecking=no {VPS_USER}@{VPS_IP} 'cd {VPS_DIR} && bash start_system.sh'"
    run_command(cmd, check=False)

    print("\n" + "=" * 60)
    print("✅ DEPLOY COMPLETATO!")
    print("=" * 60)
    print("\n📖 Comandi utili:")
    print(f"   • Connessione VPS:     ssh {VPS_USER}@{VPS_IP}")
    print(f"   • Directory bot:       cd {VPS_DIR}")
    print(f"   • View logs:           tail -f {VPS_DIR}/earlybird.log")
    print("   • Attach tmux:         tmux attach -t earlybird")
    print("   • Detach tmux:         Ctrl+B poi d")
    print("   • Stop bot:            tmux kill-session -t earlybird")
    print()


if __name__ == "__main__":
    main()
