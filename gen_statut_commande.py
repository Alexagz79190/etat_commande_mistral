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
# Transporteurs
# =============================
TRANSPORTEURS = {
    "Chronopost": {"no": "1220", "tracking": "XR475205445TS"},
    "Colissimo": {"no": "1524", "tracking": "6A03567806597"},
    "Dachser":   {"no": "4414", "tracking": "AG01868943"},
    "Geodis":    {"no": "2187", "tracking": "1G4T32SZTQL4"},
}

# =============================
# Fonction génération fichiers commande
# =============================
def generer_csv_par_commande(df, etats, mixte, transporteur_cfg, nb_max=None):
    """
    Génère un ou plusieurs fichiers OU_EXP_xxx.csv en mémoire à partir du fichier source.
    - Filtre les lignes sans Code Mistral
    - Divise les prix par 100 et force la virgule comme séparateur décimal
    - Utilise transporteur sélectionné (No + Tracking)
    """
    no_commande_base = 1873036
    num_commande = no_commande_base
    fichiers = []

    # Filtrage Code Mistral vide
    if "Code Mistral" in df.columns:
        df = df[df["Code Mistral"].notna()]
        df = df[df["Code Mistral"].astype(str).str.strip() != ""]

    nb_gen = 0

    for idx, ligne in df.iterrows():
        if nb_max and nb_gen >= nb_max:
            break

        etat = random.choice(etats) if mixte else etats[0]

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

            # Tracking uniquement si état = En cours de livraison
            tracking = transporteur_cfg["tracking"] if etat == "En cours de livraison" else ""

            # Division des prix par 100 et format avec virgule
            try:
                pv_val = "{:.2f}".format(float(pv[i]) / 100).replace(".", ",") if i < len(pv) and pv[i] not in ["", None] else ""
            except ValueError:
                pv_val = ""

            try:
                pa_val = "{:.2f}".format(float(pa[i]) / 100).replace(".", ",") if i < len(pa) and pa[i] not in ["", None] else ""
            except ValueError:
                pa_val = ""

            ligne_export = {
                "No Transaction": details[i] if i < len(details) else "",
                "No Ligne": no_ligne,
                "No Commande Client": num_commande,
                "Etat": etat,
                "No Tracking": tracking,
                "No Transporteur": transporteur_cfg["no"],
                "Code article": codes[i],
                "Désignation": libs[i] if i < len(libs) else "",
                "Quantité": qtes[i] if i < len(qtes) else "",
                "PV net": pv_val,
                "PA net": pa_val
            }
            lignes_export.append(ligne_export)
            no_ligne += 1

        if not lignes_export:
            continue

        df_export = pd.DataFrame(lignes_export)

        horodatage = datetime.now().strftime("%Y%m%d%H%M%S")
        ref_for_name = details[0] if details else str(idx)
        fichier_nom = f"OU_EXP_{ref_for_name}_{horodatage}.csv"

        buffer = BytesIO()
        df_export = df_export.applymap(lambda x: str(x).encode("latin-1", errors="replace").decode("latin-1"))
        df_export.to_csv(buffer, sep=";", index=False, encoding="latin-1")
        buffer.seek(0)

        fichiers.append((fichier_nom, buffer))
        nb_gen += 1

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
Cette application permet de :
1. Charger un **fichier source ERP** (CSV)  
2. Générer un ou plusieurs fichiers **commande BOSS** au format attendu  
3. Les envoyer automatiquement sur le serveur **SFTP** (`refonteTest`)

---

### 📑 Fichier source attendu (Export Commande → BOSS)
Filtrer d'abord les commandes Date de validation pour ne pas avoir d'anciennes
commandes et choisir les états : **Commande validée** - **Commande en préparation**

| Champ source       | Bloc |
|--------------------|-------------|
| **Reference**      | Commande |
| **Quantité**       | Détail de commande - details |
| **prixUnitHt**     | Détail de commande - details |
| **prixAchatHt**    | Détail de commande - details |
| **Code Mistral**   | Détail de commande - details |
| **Libellé**        | Détail de commande - details |

---

### 📑 Fichier généré (application → BOSS)
| Champ sortie       | Règle / Source |
|--------------------|----------------|
| **No Transaction** | Colonne `Reference` |
| **No Ligne**       | N° de ligne incrémental |
| **No Commande Client** | Numéro de base `1873036` (incrément si état = "En cours de livraison") |
| **Etat**           | Choisi parmi la liste |
| **No Tracking**    | Automatique si état = "En cours de livraison" |
| **No Transporteur**| Selon transporteur choisi |
| **Code article**   | Colonne `Code Mistral` |
| **Désignation**    | Colonne `Libellé` |
| **Quantité**       | Colonne `Quantité` |
| **PV net**         | Colonne `prixUnitHt` ÷ 100 (virgule comme séparateur décimal) |
| **PA net**         | Colonne `prixAchatHt` ÷ 100 (virgule comme séparateur décimal) |
""")

# Upload fichier source
fichier_source = st.file_uploader("📂 Charger le fichier CSV source", type=["csv"])

# Prévisualisation
if fichier_source:
    try:
        df_preview = pd.read_csv(fichier_source, sep=",", encoding="utf-8")
        st.markdown("### 👀 Aperçu du fichier source (5 premières lignes)")
        st.dataframe(df_preview.head())
    except Exception as e:
        st.error(f"Erreur lecture CSV: {e}")

# Sélection options
etats_selectionnes = st.multiselect("📌 Choisir les états de commande :", ETATS, default=[ETATS[0]])
transporteur_nom = st.selectbox("🚚 Choisir le transporteur :", list(TRANSPORTEURS.keys()))
nb_max = st.number_input("🔢 Nombre max de commandes (0 = toutes)", min_value=0, value=0, step=1)
mixte = st.checkbox("🎲 Mélanger les états (aléatoire)", value=False)

# Bouton
if st.button("▶️ Générer et envoyer sur SFTP"):
    if not fichier_source:
        st.error("Merci de charger le fichier source.")
    elif not etats_selectionnes:
        st.error("Merci de sélectionner au moins un état.")
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
            TRANSPORTEURS[transporteur_nom],
            nb_max if nb_max > 0 else None
        )

        st.info(f"{len(fichiers)} fichier(s) généré(s), tentative d'envoi SFTP...")

        ok, msg = upload_sftp(fichiers, SFTP_CFG)
        if ok:
            st.success(msg)
            st.download_button("⬇️ Télécharger le 1er fichier généré", fichiers[0][1], file_name=fichiers[0][0])
        else:
            st.error("Erreur SFTP : " + msg)
