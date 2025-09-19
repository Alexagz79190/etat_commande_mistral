# app_sftp.py
# -*- coding: utf-8 -*-
"""
App Streamlit : test d'upload de fichier en SFTP avec paramiko
"""

import streamlit as st
import paramiko
import os

# =============================
# Charger les secrets SFTP
# =============================
def get_sftp_config():
    try:
        sftp_conf = st.secrets["sftp"]
        return {
            "host": sftp_conf.get("host"),
            "user": sftp_conf.get("user"),
            "pass": sftp_conf.get("pass"),
            "dir": sftp_conf.get("dir", "refonteTest")
        }
    except Exception:
        return {
            "host": os.environ.get("SFTP_HOST"),
            "user": os.environ.get("SFTP_USER"),
            "pass": os.environ.get("SFTP_PASS"),
            "dir": os.environ.get("SFTP_DIR", "refonteTest")
        }

SFTP_CFG = get_sftp_config()

# =============================
# Fonction d'upload
# =============================
def upload_sftp(file, sftp_cfg):
    host = sftp_cfg.get("host")
    user = sftp_cfg.get("user")
    pwd  = sftp_cfg.get("pass")
    dir_remote = sftp_cfg.get("dir", "refonteTest")

    if not host or not user or not pwd:
        return False, "Identifiants SFTP manquants"

    try:
        transport = paramiko.Transport((host, 22))
        transport.connect(username=user, password=pwd)
        sftp = paramiko.SFTPClient.from_transport(transport)

        # Vérifier le dossier
        try:
            sftp.chdir(dir_remote)
        except IOError:
            try:
                sftp.mkdir(dir_remote)
                sftp.chdir(dir_remote)
            except Exception as e:
                sftp.close()
                transport.close()
                return False, f"Impossible d'accéder/créer le dossier distant : {e}"

        remote_path = f"{dir_remote}/{file.name}"
        sftp.putfo(file, remote_path)

        sftp.close()
        transport.close()
        return True, f"📤 Fichier {file.name} envoyé en SFTP dans {dir_remote}"
    except Exception as e:
        return False, str(e)

# =============================
# Interface Streamlit
# =============================
st.title("🔐 Test upload SFTP (paramiko)")

st.markdown("⚠️ Les identifiants SFTP sont lus depuis `st.secrets['sftp']` ou les variables d'environnement.")

uploaded_file = st.file_uploader("Choisir un fichier à envoyer")

if st.button("Envoyer en SFTP"):
    if not uploaded_file:
        st.error("Merci de choisir un fichier.")
    else:
        ok, msg = upload_sftp(uploaded_file, SFTP_CFG)
        if ok:
            st.success(msg)
        else:
            st.error("Erreur SFTP : " + msg)
