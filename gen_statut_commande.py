# -*- coding: utf-8 -*-
"""
App Streamlit : génération de fichiers de simulation + envoi FTP
"""

import streamlit as st
import pandas as pd
import random
from datetime import datetime
from io import BytesIO
from ftplib import FTP_TLS

# =============================
# Paramètres FTP
# =============================
FTP_HOST = "ftp.agrizone.net"
FTP_USER = "mistral"
FTP_PASS = "c1secret"
FTP_DIR  = "refonteTest"

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
        details = str(ligne["Reference"]).split("|")
        qtes    = str(ligne["Quantité"]).split("|")
        pv      = str(ligne["prixUnitHt"]).split("|")
        pa      = str(ligne["prixAchatHt"]).split("|")
        codes   = str(ligne["Code Mistral"]).split("|")
        libs    = str(ligne["Libellé"]).split("|")

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
        fichier_nom = f"OU_EXP_{num_commande}_{horodatage}.csv"

        # Conversion en buffer mémoire
        buffer = BytesIO()
        df_export.to_csv(buffer, sep=";", index=False, encoding="latin-1")
        buffer.seek(0)

        fichiers.append((fichier_nom, buffer))

        # Incrémentation si état = en cours de livraison
        if etat == "En cours de livraison":
            num_commande += 1

    return fichiers

# =============================
# Fonction envoi FTP
# =============================
def upload_ftp(fichiers):
    try:
        ftps = FTP_TLS()
        ftps.connect(FTP_HOST, 21, timeout=15)
        ftps.auth()
        ftps.login(FTP_USER, FTP_PASS)
        ftps.prot_p()
        ftps.cwd(FTP_DIR)

        for nom, buffer in fichiers:
            buffer.seek(0)
            ftps.storbinary(f"STOR {nom}", buffer)
        ftps.quit()
        return True, f"{len(fichiers)} fichier(s) envoyé(s) sur {FTP_DIR}"
    except Exception as e:
        return False, str(e)

# =============================
# Interface Streamlit
# =============================
st.title("📦 Simulation états de livraison + Envoi FTP")

# Upload fichier source
fichier_source = st.file_uploader("Charger le fichier CSV source", type=["csv"])

# Sélection états
etats_selectionnes = st.multiselect("Choisir les états :", ETATS)

# Transporteur
transporteur = st.text_input("Nom du transporteur")

# Nb max commandes
nb_max = st.number_input("Nombre max de commandes (0 = toutes)", min_value=0, value=0)

# Mixte
mixte = st.checkbox("Mélanger les états", value=False)

if st.button("Générer et envoyer sur FTP"):
    if not fichier_source or not etats_selectionnes or not transporteur:
        st.error("Merci de remplir toutes les informations.")
    else:
        df = pd.read_csv(fichier_source, sep=",", encoding="utf-8")
        fichiers = generer_csv_par_commande(
            df, etats_selectionnes, mixte, transporteur, nb_max if nb_max > 0 else None
        )
        ok, msg = upload_ftp(fichiers)
        if ok:
            st.success(msg)
        else:
            st.error("Erreur FTP : " + msg)
