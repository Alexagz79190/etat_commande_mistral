# pages/2_📑 Envoi facture.py
# -*- coding: utf-8 -*-

import streamlit as st
from io import BytesIO
from datetime import datetime
import os
import paramiko

# =============================
# Config SFTP (identique à ta 1re page)
# =============================
def get_sftp_config():
    try:
        sftp_conf = st.secrets["sftp"]
        return {
            "host": sftp_conf.get("host"),
            "user": sftp_conf.get("user"),
            "pass": sftp_conf.get("pass"),
            "dir":  sftp_conf.get("dir", "refonteTest")
        }
    except Exception:
        return {
            "host": os.environ.get("SFTP_HOST"),
            "user": os.environ.get("SFTP_USER"),
            "pass": os.environ.get("SFTP_PASS"),
            "dir":  os.environ.get("SFTP_DIR", "refonteTest")
        }

SFTP_CFG = get_sftp_config()

def upload_sftp_blobs(named_blobs, sftp_cfg):
    """
    named_blobs: liste de tuples (remote_filename, BytesIO)
    """
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

        # s'assure que le dir existe (best effort)
        try:
            sftp.listdir(dir_remote)
        except IOError:
            try:
                sftp.mkdir(dir_remote)
            except Exception:
                pass

        for nom, buffer in named_blobs:
            buffer.seek(0)
            remote_path = f"{dir_remote}/{nom}"
            sftp.putfo(buffer, remote_path)

        sftp.close()
        transport.close()
        return True, f"{len(named_blobs)} fichier(s) envoyé(s) sur {dir_remote}"
    except Exception as e:
        return False, str(e)

# =============================
# UI
# =============================
st.title("🧾 Envoi de facture (PDF) → SFTP")

# État session pour l’étape suivante
if "facture_ok" not in st.session_state:
    st.session_state.facture_ok = False
if "facture_msg" not in st.session_state:
    st.session_state.facture_msg = ""
if "dernier_pdf_nom" not in st.session_state:
    st.session_state.dernier_pdf_nom = None

st.markdown("""
Cette page permet de déposer une facture PDF reliée à une commande, puis de
générer le **fichier de contrôle** attendu par le traitement BOSS, et d'envoyer le tout en **SFTP**.
""")

col1, col2 = st.columns(2)
with col1:
    num_commande = st.text_input("🧩 Numéro de commande", placeholder="Ex : 4753073")
with col2:
    num_facture = st.text_input("🧾 Numéro de facture", placeholder="Ex : F2025-00123")

pdf_file = st.file_uploader("📄 Charger le PDF de la facture", type=["pdf"])

# Bouton d'envoi
if st.button("📤 Envoyer la facture sur SFTP", type="primary"):
    st.session_state.facture_ok = False
    st.session_state.facture_msg = ""
    st.session_state.dernier_pdf_nom = None

    # Validations
    if not num_commande.strip():
        st.error("Merci de saisir un **numéro de commande**.")
        st.stop()
    if not num_facture.strip():
        st.error("Merci de saisir un **numéro de facture**.")
        st.stop()
    if pdf_file is None:
        st.error("Merci de charger un **fichier PDF**.")
        st.stop()

    # Date du jour
    today = datetime.now().strftime("%Y%m%d")

    # Nom du PDF renommé
    pdf_remote_name = f"FACT_{num_commande}_{today}_{num_facture}.pdf"

    # Nom du fichier de contrôle (sans extension)
    # Contenu attendu : "numcommande;nomfichieravecext"
    ctrl_remote_name = f"OU_FACT_{num_commande}_{today}_{num_facture}"
    ctrl_content = f"{num_commande};{pdf_remote_name}"

    # Prépare les blobs en mémoire
    # 1) PDF renommé
    pdf_bytes = pdf_file.read()
    pdf_blob = BytesIO(pdf_bytes)

    # 2) Fichier de contrôle (texte)
    ctrl_blob = BytesIO(ctrl_content.encode("latin-1", errors="ignore"))

    # Envoi SFTP des 2 fichiers
    ok, msg = upload_sftp_blobs(
        [(pdf_remote_name, pdf_blob), (ctrl_remote_name, ctrl_blob)],
        SFTP_CFG
    )
    st.session_state.facture_ok = bool(ok)
    st.session_state.facture_msg = msg
    st.session_state.dernier_pdf_nom = pdf_remote_name if ok else None

    if ok:
        st.success(msg)
        st.info(f"PDF renommé : **{pdf_remote_name}**")
        st.info(f"Fichier contrôle : **{ctrl_remote_name}** (contenu : `{ctrl_content}`)")
    else:
        st.error("❌ Erreur SFTP : " + msg)

st.markdown("---")

# Étape suivante : ouvrir la cron (LDAP)
if st.session_state.facture_ok:
    st.markdown("### 🕐 Étape suivante")
    CRON_FACTURE_URL = (
        "https://admin-refonte.agrizone.net/?crudAction=launch&"
        "crudControllerFqcn=Boss%5CSchedulerBundle%5CController%5CSchedulerCrudController&"
        "entityFqcn=App%5CEntity%5CScheduler%5CScheduler&"
        "message=App%5CMessageHandler%5CScheduler%5CMistralRecupFactureHandler"
    )

    st.link_button(
        "✅ Ouvrir la cron MistralRecupFacture (login LDAP)",
        CRON_FACTURE_URL,
        use_container_width=True
    )
