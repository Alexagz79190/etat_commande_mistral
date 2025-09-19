# explorer_sftp.py
# -*- coding: utf-8 -*-
"""
App Streamlit : diagnostic SFTP (affiche répertoire courant et contenu)
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
            "dir": sftp_conf.get("dir", None)
        }
    except Exception:
        return {
            "host": os.environ.get("SFTP_HOST"),
            "user": os.environ.get("SFTP_USER"),
            "pass": os.environ.get("SFTP_PASS"),
            "dir": os.environ.get("SFTP_DIR", None)
        }

SFTP_CFG = get_sftp_config()

# =============================
# Fonction d'exploration
# =============================
def explore_sftp(sftp_cfg):
    host = sftp_cfg.get("host")
    user = sftp_cfg.get("user")
    pwd  = sftp_cfg.get("pass")

    if not host or not user or not pwd:
        return False, "Identifiants SFTP manquants"

    try:
        transport = paramiko.Transport((host, 22))
        transport.connect(username=user, password=pwd)
        sftp = paramiko.SFTPClient.from_transport(transport)

        cwd = sftp.getcwd()
        contenu = sftp.listdir()

        sftp.close()
        transport.close()

        return True, {"cwd": cwd, "contenu": contenu}
    except Exception as e:
        return False, str(e)

# =============================
# Interface Streamlit
# =============================
st.title("🔎 Diagnostic connexion SFTP")

if st.button("Explorer SFTP"):
    ok, result = explore_sftp(SFTP_CFG)
    if ok:
        st.success(f"Répertoire courant : {result['cwd']}")
        st.write("📋 Contenu du répertoire :")
        st.json(result['contenu'])
    else:
        st.error("Erreur SFTP : " + result)
