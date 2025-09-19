# app.py
# -*- coding: utf-8 -*-
"""
App Streamlit : simulation export commande BOSS + envoi SFTP
"""

import streamlit as st
import pandas as pd
import random
from datetime import datetime
from io import BytesIO
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
# États possibles
# =============================
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
# Transporteurs possibles
# =============================
TRANSPORTEURS = [
    {"nom": "Chronopost", "id": "1220", "tracking": "XR475205445TS"},
    {"nom": "Colissimo",  "id": "1524", "tracking": "6A03567806597"},
    {"nom": "Dachser",    "id": "4414", "tracking": "AG01868943"},
    {"nom": "Geodis",     "id": "2187", "tracking": "1G4T32SZTQL4"},
]

# =============================
# Fonction génération fichiers commande
# =============================
def generer_csv_par_commande(df, etats, transporteurs, mixte, nb_max=None):
    no_commande_base = 1873036
    num_commande = no_commande_base
    fichiers = []
    commandes_generees = 0

    # ⚡ Filtrage des lignes où Code Mistral est vide
    if "Code Mistral" in df.columns:
        df = df[df["Code Mistral"].notna()]
        df = df[df["Code Mistral"].astype(str).str.strip() != ""]

    for idx, ligne in df.iterrows():
        if nb_max and commandes_generees >= nb_max:
            break

        # État
        etat = random.choice(etats) if mixte else etats[0]

        # Transporteur (tourniquet)
        t = transporteurs[commandes_generees % len(transporteurs)]
        transporteur_id = t["id"]
        tracking_default = t["tracking"]

        # Découpage des champs PIPE
        details = str(ligne.get("Reference", "")).split("|")
        qtes    = str(ligne.get("Quantité", "")).split("|")
        pv      = str(ligne.get("prixUnitHt", "")).split("|")
        pa      = str(ligne.get("prixAchatHt", "")).split("|")
        codes   = str(ligne.get("Code Mistral", "")).split("|")
        libs    = str(ligne.get("Libellé", "")).split("|")

        lignes_export = []
        no_ligne = 1

        for i in range(len(details)):
            if i >= len(codes) or not str(codes[i]).strip():
                continue

            tracking = tracking_default if etat == "En cours de livraison" else ""

            def format_price(val):
                try:
                    return str(round(float(val) / 100, 2)).replace(".", ",")
                except:
                    return ""

            pv_val = format_price(pv[i]) if i < len(pv) else ""
            pa_val = format_price(pa[i]) if i < len(pa) else ""

            lignes_export.append({
                "No Transaction": details[i] if i < len(details) else "",
                "No Ligne": no_ligne,
                "No Commande Client": num_commande,
                "Etat": etat,
                "No Tracking": tracking,
                "No Transporteur": transporteur_id,
                "Code article": codes[i],
                "Désignation": libs[i] if i < len(libs) else "",
                "Quantité": qtes[i] if i < len(qtes) else "",
                "PV net": pv_val,
                "PA net": pa_val
            })
            no_ligne += 1

        if not lignes_export:
            continue

        df_export = pd.DataFrame(lignes_export)

        # Nom fichier
        horodatage = datetime.now().strftime("%Y%m%d%H%M%S")
        ref_for_name = details[0] if details else str(idx)
        fichier_nom = f"OU_EXP_{ref_for_name}_{horodatage}.csv"

        # Buffer mémoire
        buffer = BytesIO()
        df_export = df_export.applymap(lambda x: str(x).encode("latin-1", errors="replace").decode("latin-1"))
        df_export.to_csv(buffer, sep=";", index=False, encoding="latin-1")
        buffer.seek(0)

        fichiers.append((fichier_nom, buffer))
        commandes_generees += 1

        if etat == "En cours de livraison":
            num_commande += 1

    return fichiers

# =============================
# Fonction upload SFTP
# =============================
def upload_sftp(fichiers, sftp_cfg):
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

        for nom, buffer in fichiers:
            buffer.seek(0)
            remote_path = f"{dir_remote}/{nom}"
            sftp.putfo(buffer, remote_path)
            st.write(f"✅ Upload {remote_path}")

        sftp.close()
        transport.close()
        return True, f"{len(fichiers)} fichier(s) envoyé(s) en SFTP vers {dir_remote}"
    except Exception as e:
        return False, str(e)

# =============================
# Interface Streamlit
# =============================
st.title("📦 Simulation export commande BOSS + Envoi SFTP")

st.markdown("""
### 📑 Fichier source attendu (Export Commande → BOSS)
Filtrer les commandes **Date de validation** pour ne pas avoir d’anciennes commandes  
et choisir les états : *Commande validée* - *Commande en préparation*  

| Champ source       | Bloc |
|--------------------|-------------|
| **Reference**      | Commande |
| **Quantité**       | Détail de commande - détails |
| **prixUnitHt**     | Détail de commande - détails |
| **prixAchatHt**    | Détail de commande - détails |
| **Code Mistral**   | Détail de commande - détails |
| **Libellé**        | Détail de commande - détails |
""")

# Upload fichier source
fichier_source = st.file_uploader("📂 Charger le fichier CSV source", type=["csv"])

if fichier_source:
    try:
        fichier_source.seek(0)  # 🔑 reset curseur
        df_preview = pd.read_csv(fichier_source, sep=",", encoding="utf-8")
        st.markdown("### 👀 Aperçu du fichier source (5 premières lignes)")
        st.dataframe(df_preview.head())
    except Exception as e:
        st.error(f"Erreur lecture CSV: {e}")

# Options
etats_selectionnes = st.multiselect("📌 Choisir les états de commande :", ETATS, default=[ETATS[0]])
transporteurs_selectionnes = st.multiselect("🚚 Choisir les transporteurs :", [t["nom"] for t in TRANSPORTEURS])
nb_max = st.number_input("🔢 Nombre max de commandes (0 = toutes)", min_value=0, value=0, step=1)
mixte = st.checkbox("🎲 Mélanger les états (aléatoire)", value=False)

# Bouton
if st.button("▶️ Générer et envoyer sur SFTP"):
    if not fichier_source:
        st.error("Merci de charger le fichier source.")
    elif not etats_selectionnes:
        st.error("Merci de sélectionner au moins un état.")
    elif not transporteurs_selectionnes:
        st.error("Merci de choisir au moins un transporteur.")
    else:
        try:
            fichier_source.seek(0)  # 🔑 reset avant 2e lecture
            df = pd.read_csv(fichier_source, sep=",", encoding="utf-8")
        except Exception as e:
            st.error(f"Erreur lecture CSV: {e}")
            st.stop()

        transporteurs_utilises = [t for t in TRANSPORTEURS if t["nom"] in transporteurs_selectionnes]

        fichiers = generer_csv_par_commande(
            df,
            etats_selectionnes,
            transporteurs_utilises,
            mixte,
            nb_max if nb_max > 0 else None
        )

        st.info(f"{len(fichiers)} fichier(s) généré(s), tentative d'envoi SFTP...")

        ok, msg = upload_sftp(fichiers, SFTP_CFG)
        if ok:
            st.success(msg)
            st.download_button("⬇️ Télécharger le 1er fichier généré", fichiers[0][1], file_name=fichiers[0][0])
        else:
            st.error("Erreur SFTP : " + msg)
