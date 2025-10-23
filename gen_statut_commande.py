# -*- coding: utf-8 -*-
"""
Created on Thu Oct 23 16:34:05 2025

@author: mathon.alexis
"""

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
import requests

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
# Cron
# =============================
CRON_URL = (
    "https://admin-refonte.agrizone.net/?crudAction=launch&"
    "crudControllerFqcn=Boss%5CSchedulerBundle%5CController%5CSchedulerCrudController&"
    "entityFqcn=App%5CEntity%5CScheduler%5CScheduler&"
    "logical_filter=%7B%22andx%22:%7B%221%22:%7B%22property%22:%22name%22,%22condition%22:%22contient%22,"
    "%22widget%22:%22recup%22%7D%7D%7D&"
    "message=App%5CMessageHandler%5CScheduler%5CMistralRecupCommandeHandler"
)


# =============================
# Fonction génération fichiers commande
# =============================
def generer_csv_par_commande(
    df,
    etats: list,
    transporteurs: list,
    mode_etat: str,             # "unique" | "cyclique" | "aleatoire"
    nb_max=None,
    partiel_active=False,       # True/False
    partiel_qte=1,              # quantité pour la ligne partielle
    partiel_etat_a=None,        # état pour la partie partielle
    partiel_etat_b=None         # état pour le reliquat
):
    import re

    no_commande_base = 1873036
    num_commande = no_commande_base
    fichiers = []
    commandes_generees = 0

    # Filtre "Code Mistral" vide
    if "Code Mistral" in df.columns:
        df = df[df["Code Mistral"].notna()]
        df = df[df["Code Mistral"].astype(str).str.strip() != ""]

    # Helpers
    def split_strip(x):
        if pd.isna(x):
            return []
        return [p.strip() for p in str(x).split("|")]

    def at(lst, i):
        return lst[i] if i < len(lst) else ""

    def to_float_safe(val):
        s = str(val).strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
        try:
            return float(s)
        except Exception:
            return 0.0

    def format_price(val):
        try:
            return str(round(to_float_safe(val) / 100, 2)).replace(".", ",")
        except Exception:
            return ""

    def to_int_safe(val):
        try:
            return int(float(str(val).replace(",", ".").strip()))
        except Exception:
            return 0

    # Sélection de l'état selon le mode choisi
    line_counter = 0
    def pick_etat():
        nonlocal line_counter
        if not etats:
            return ""
        if mode_etat == "unique":
            return etats[0]
        elif mode_etat == "cyclique":
            e = etats[line_counter % len(etats)]
            line_counter += 1
            return e
        else:  # "aleatoire"
            return random.choice(etats)

    for idx, ligne in df.iterrows():
        if nb_max and commandes_generees >= nb_max:
            break

        # Tourniquet transporteur
        t = transporteurs[commandes_generees % len(transporteurs)]
        transporteur_id = t["id"]
        tracking_default = t["tracking"]

        # Découpe des champs (pipe)
        details = split_strip(ligne.get("Reference", ""))
        qtes    = split_strip(ligne.get("Quantité", ""))
        pv      = split_strip(ligne.get("prixUnitHt", ""))
        pa      = split_strip(ligne.get("prixAchatHt", ""))
        codes   = split_strip(ligne.get("Code Mistral", ""))
        libs    = split_strip(ligne.get("Libellé", ""))

        n = max(len(details), len(qtes), len(pv), len(pa), len(codes), len(libs)) if any([details, qtes, pv, pa, codes, libs]) else 0

        lignes_export = []
        no_ligne = 1

        for i in range(n):
            code_i = at(codes, i)
            if not str(code_i).strip():
                continue

            # Quantité d'origine
            qte_full = to_int_safe(at(qtes, i)) if at(qtes, i) != "" else 0
            if qte_full <= 0:
                qte_full = 1  # fallback

            # Prix
            pv_val = format_price(at(pv, i)) if at(pv, i) != "" else ""
            pa_val = format_price(at(pa, i)) if at(pa, i) != "" else ""

            # Référence transaction pour nommage
            no_transaction = at(details, i) or (details[0] if details else str(idx))

            # Fonction pour créer une ligne (avec tracking si "En cours de livraison")
            def build_line(_etat, _qte):
                tracking = tracking_default if _etat == "En cours de livraison" else ""
                return {
                    "No Transaction": no_transaction,
                    "No Ligne": _next_no_ligne(),
                    "No Commande Client": num_commande,
                    "Etat": _etat,
                    "No Tracking": tracking,
                    "No Transporteur": transporteur_id,
                    "Code article": code_i,
                    "Désignation": at(libs, i),
                    "Quantité": str(_qte),
                    "PV net": pv_val,
                    "PA net": pa_val
                }

            # Compteur No Ligne
            def _next_no_ligne():
                nonlocal no_ligne
                cur = no_ligne
                no_ligne += 1
                return cur

            # === LOGIQUE PARTIELLE ===
            if partiel_active and qte_full > partiel_qte:
                # États dédiés pour partiel/reliquat (sinon on pioche via mode)
                etat_a = partiel_etat_a or pick_etat()
                etat_b = partiel_etat_b or pick_etat()
                qte_a = partiel_qte
                qte_b = qte_full - partiel_qte

                lignes_export.append(build_line(etat_a, qte_a))
                lignes_export.append(build_line(etat_b, qte_b))
            else:
                etat = pick_etat()
                lignes_export.append(build_line(etat, qte_full))

        if not lignes_export:
            continue

        df_export = pd.DataFrame(lignes_export)

        # Nom de fichier
        horodatage = datetime.now().strftime("%Y%m%d%H%M%S")
        ref_for_name = details[0] if details else str(idx)
        ref_for_name = re.sub(r'[^A-Za-z0-9._-]+', '_', ref_for_name)
        fichier_nom = f"OU_EXP_{ref_for_name}_{horodatage}.csv"

        # Buffer
        buffer = BytesIO()
        df_export = df_export.astype(str)
        df_export.to_csv(buffer, sep=";", index=False, encoding="latin-1")
        buffer.seek(0)

        fichiers.append((fichier_nom, buffer))
        commandes_generees += 1
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

# État initial (évite NameError)
if "sftp_ok" not in st.session_state:
    st.session_state.sftp_ok = False
if "sftp_msg" not in st.session_state:
    st.session_state.sftp_msg = ""
if "dernier_fichier" not in st.session_state:
    st.session_state.dernier_fichier = None  # (name, BytesIO)

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

# Options — États
etats_selectionnes = st.multiselect("📌 Choisir les états de commande :", ETATS, default=[ETATS[0]])

# Mode d’attribution d’état
mode_etat_label = st.radio(
    "🎛️ Mode d’attribution des états :",
    ["Unique (tout pareil)", "Cyclique (1,2,3…)", "Aléatoire par ligne"],
    index=0
)
mode_etat = {
    "Unique (tout pareil)": "unique",
    "Cyclique (1,2,3…)": "cyclique",
    "Aléatoire par ligne": "aleatoire"
}[mode_etat_label]

# Gestion des lignes partielles
with st.expander("✂️ Gestion de ligne partielle"):
    partiel_active = st.checkbox("Activer la gestion de ligne partielle", value=False)
    partiel_qte = 1
    etat_partiel_a = None
    etat_partiel_b = None
    if partiel_active:
        partiel_qte = st.number_input("Quantité pour la partie partielle (A)",
                                      min_value=1, value=1, step=1)
        if etats_selectionnes:
            etat_partiel_a = st.selectbox("État pour la partie partielle (A)",
                                          etats_selectionnes, index=0, key="etat_a")
            idx_b = 1 if len(etats_selectionnes) > 1 else 0
            etat_partiel_b = st.selectbox("État pour le reliquat (B)",
                                          etats_selectionnes, index=idx_b, key="etat_b")
        else:
            st.warning("Sélectionne au moins un état pour configurer la ligne partielle.")

# Transporteurs & limites
transporteurs_selectionnes = st.multiselect(
    "🚚 Choisir les transporteurs :", [t["nom"] for t in TRANSPORTEURS]
)
nb_max = st.number_input("🔢 Nombre max de commandes (0 = toutes)", min_value=0, value=0, step=1)

# Bouton principal : Générer + SFTP
if st.button("▶️ Générer et envoyer sur SFTP", type="primary"):
    # Reset état d’exécution précédent
    st.session_state.sftp_ok = False
    st.session_state.sftp_msg = ""
    st.session_state.dernier_fichier = None

    # Validations
    if not fichier_source:
        st.error("Merci de charger le fichier source.")
        st.stop()
    if not etats_selectionnes:
        st.error("Merci de sélectionner au moins un état.")
        st.stop()
    if not transporteurs_selectionnes:
        st.error("Merci de choisir au moins un transporteur.")
        st.stop()

    # Lecture effective du CSV
    try:
        fichier_source.seek(0)
        df = pd.read_csv(fichier_source, sep=",", encoding="utf-8")
    except Exception as e:
        st.error(f"Erreur lecture CSV: {e}")
        st.stop()

    # Transporteurs retenus
    transporteurs_utilises = [t for t in TRANSPORTEURS if t["nom"] in transporteurs_selectionnes]
    if not transporteurs_utilises:
        st.error("Aucun transporteur valide après filtrage.")
        st.stop()

    # Génération
    fichiers = generer_csv_par_commande(
        df=df,
        etats=etats_selectionnes,
        transporteurs=transporteurs_utilises,
        mode_etat=mode_etat,
        nb_max=nb_max if nb_max > 0 else None,
        partiel_active=partiel_active,
        partiel_qte=partiel_qte,
        partiel_etat_a=etat_partiel_a,
        partiel_etat_b=etat_partiel_b
    )

    if not fichiers:
        st.warning("Aucune ligne valide à exporter (vérifie le fichier source).")
        st.stop()

    st.info(f"{len(fichiers)} fichier(s) généré(s), tentative d'envoi SFTP...")

    # Envoi SFTP
    ok, msg = upload_sftp(fichiers, SFTP_CFG)  # <- ok et msg TOUJOURS définis ici
    st.session_state.sftp_ok = bool(ok)
    st.session_state.sftp_msg = msg or ""
    # Mémoriser le 1er fichier pour le téléchargement
    try:
        st.session_state.dernier_fichier = fichiers[0]
    except Exception:
        st.session_state.dernier_fichier = None

    # Feedback immédiat
    if st.session_state.sftp_ok:
        st.success(st.session_state.sftp_msg)
    else:
        st.error("❌ Erreur SFTP : " + st.session_state.sftp_msg)

# ---- Zone de sortie (bas de page) ----
# Bouton de téléchargement (si un fichier est dispo)
if st.session_state.dernier_fichier is not None:
    nom, buffer = st.session_state.dernier_fichier
    try:
        st.download_button(
            "⬇️ Télécharger le 1er fichier généré",
            buffer,
            file_name=nom,
            key="download_1"
        )
    except Exception:
        st.info("Les fichiers ont été envoyés en SFTP. Aucun téléchargement local n'a été créé.")

# Bouton CRON (uniquement si SFTP OK) — affiché APRÈS le téléchargement
if st.session_state.sftp_ok:
    st.markdown("---")
    st.markdown("### 🕐 Étape suivante")

    # ✅ Bouton-lien vers la page cron (connexion LDAP)
    st.link_button(
        "✅ Ouvrir la page cron (login LDAP)",
        CRON_URL,
        use_container_width=True
    )
