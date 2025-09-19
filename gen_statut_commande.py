# app.py
# -*- coding: utf-8 -*-
"""
App Streamlit : génération de fichiers de simulation + envoi FTPS
"""

import streamlit as st
import pandas as pd
import random
from datetime import datetime
from io import BytesIO
from ftplib import FTP_TLS
import os

# =============================
# Charger les secrets FTP (Streamlit secrets ou variables d'environnement)
# =============================
def get_ftp_config():
    # Format recommandé dans Streamlit Cloud: [ftp] host = "...", user = "...", pass = "...", dir = "..."
    try:
        ftp_conf = st.secrets["ftp"]
        return {
            "host": ftp_conf.get("host"),
            "user": ftp_conf.get("user"),
            "pass": ftp_conf.get("pass"),
            "dir": ftp_conf.get("dir", "refonteTest")
        }
    except Exception:
        # Fallback sur variables d'environnement (pratique en dev local)
        return {
            "host": os.environ.get("FTP_HOST"),
            "user": os.environ.get("FTP_USER"),
            "pass": os.environ.get("FTP_PASS"),
            "dir": os.environ.get("FTP_DIR", "refonteTest")
        }

FTP_CFG = get_ftp_config()

# États
ETATS = [
    "Delete",
    "En attente de paiement",
    "En cours de preparation",
    "En cours de reapprovisionnement",
    "En cours de traitement",
    "En cours de livraison",
    "En traitement"
]

# =============================
# Fonction de génération
# =============================
def generer_csv_par_commande(df, etats, mixte, transporteur, nb_max=None):
    no_commande_base = 1873036
    num_commande = no_commande_base

    fichiers = []

    for idx, ligne in df.iterrows():
        if nb_max and idx >= nb_max:
            break

        # État
        etat = random.choice(etats) if mixte else etats[0]

        # Split des détails
        details = str(ligne.get("Reference", "")).split("|")
        qtes    = str(ligne.get("Quantité", "")).split("|")
        pv      = str(ligne.get("prixUnitHt", "")).split("|")
        pa      = str(ligne.get("prixAchatHt", "")).split("|")
        codes   = str(ligne.get("Code Mistral", "")).split("|")
        libs    = str(ligne.get("Libellé", "")).split("|")

        lignes_export = []
        no_ligne = 1

        for i in range(len(details)):
            # Tracking uniquement si "En cours de livraison"
            tracking = "XR475205445TS" if etat == "En cours de livraison" else ""

            ligne_export = {
                "No Transaction": details[i],
                "No Ligne": no_ligne,
                "No Commande Client": num_commande,
                "Etat": etat,
                "No Tracking": tracking,
                "No Transporteur": transporteur,
                "Code article": codes[i] if i < len(codes) else "",
                "Désignation": libs[i] if i < len(libs) else "",
                "Quantité": qtes[i] if i < len(qtes) else "",
                "PV net": pv[i] if i < len(pv) else "",
                "PA net": pa[i] if i < len(pa) else ""
            }
            lignes_export.append(ligne_export)
            no_ligne += 1

        df_export = pd.DataFrame(lignes_export)

        # Nom de fichier
        horodatage = datetime.now().strftime("%Y%m%d%H%M%S")
        # J'utilise la 1ère référence comme identifiant de fichier (comme demandé auparavant)
        ref_for_name = details[0] if details else str(idx)
        fichier_nom = f"OU_EXP_{ref_for_name}_{horodatage}.csv"

        # Conversion en buffer mémoire (latin-1 ; remplacement des caractères non-encodables)
        buffer = BytesIO()
        # on force replacement pour éviter UnicodeEncodeError
        df_export = df_export.applymap(lambda x: str(x).encode("latin-1", errors="replace").decode("latin-1"))
        df_export.to_csv(buffer, sep=";", index=False, encoding="latin-1")
        buffer.seek(0)

        fichiers.append((fichier_nom, buffer))

        # Incrémentation si état = en cours de livraison
        if etat == "En cours de livraison":
            num_commande += 1

    return fichiers

# =============================
# Fonction envoi FTPS
# =============================
def upload_ftp(fichiers, ftp_cfg, timeout=20):
    host = ftp_cfg.get("host")
    user = ftp_cfg.get("user")
    pwd  = ftp_cfg.get("pass")
    dir_remote = ftp_cfg.get("dir", "refonteTest")

    if not host or not user or not pwd:
        return False, "Identifiants FTP manquants (vérifier st.secrets ou variables d'environnement)."

    try:
        ftps = FTP_TLS()
        ftps.connect(host, 21, timeout=timeout)
        ftps.auth()               # AUTH TLS
        ftps.login(user, pwd)
        ftps.prot_p()
        ftps.set_pasv(True)

        # Essayer d'aller dans le dossier, sinon tenter de le créer
        try:
            ftps.cwd(dir_remote)
        except Exception:
            try:
                ftps.mkd(dir_remote)
                ftps.cwd(dir_remote)
            except Exception as e:
                ftps.quit()
                return False, f"Impossible d'accéder/créer le dossier distant '{dir_remote}': {e}"

        for nom, buffer in fichiers:
            buffer.seek(0)
            ftps.storbinary(f"STOR {nom}", buffer)
        ftps.quit()
        return True, f"{len(fichiers)} fichier(s) envoyé(s) sur {dir_remote}"
    except Exception as e:
        return False, str(e)

# =============================
# Interface Streamlit
# =============================
st.title("📦 Simulation états de livraison + Envoi FTPS (secrets)")

st.markdown("⚠️ Les identifiants FTP sont lus depuis `st.secrets['ftp']` ou depuis les variables d'environnement. Ne les mettez pas dans le code.")

# Upload fichier source
fichier_source = st.file_uploader("Charger le fichier CSV source", type=["csv"])

# Sélection états
etats_selectionnes = st.multiselect("Choisir les états :", ETATS, default=[ETATS[0]])

# Transporteur
transporteur = st.text_input("Nom du transporteur", value="")

# Nb max commandes
nb_max = st.number_input("Nombre max de commandes (0 = toutes)", min_value=0, value=0, step=1)

# Mixte
mixte = st.checkbox("Mélanger les états", value=False)

# Bouton
if st.button("Générer et envoyer sur FTPS"):
    if not fichier_source:
        st.error("Merci de charger le fichier source.")
    elif not etats_selectionnes:
        st.error("Merci de sélectionner au moins un état.")
    elif not transporteur:
        st.error("Merci de renseigner le transporteur.")
    else:
        try:
            df = pd.read_csv(fichier_source, sep=",", encoding="utf-8")
        except Exception as e:
            st.error(f"Erreur lecture CSV: {e}")
            st.stop()

        fichiers = generer_csv_par_commande(
            df,
            etats_selectionnes,
            mixte,
            transporteur,
            nb_max if nb_max > 0 else None
        )

        st.info(f"{len(fichiers)} fichier(s) généré(s) en mémoire, tentative d'envoi FTPS...")

        ok, msg = upload_ftp(fichiers, FTP_CFG)
        if ok:
            st.success(msg)
        else:
            st.error("Erreur FTPS : " + msg)

        # proposer le téléchargement local (zip ou fichiers) — optionnel
        if ok:
            st.download_button("Télécharger le 1er fichier généré", fichiers[0][1], file_name=fichiers[0][0])
