# app.py
# -*- coding: utf-8 -*-
"""
App Streamlit : simulation export commande BOSS + envoi SFTP
- Modes d'état : Unique / Cyclique / Aléatoire par ligne
- Bouton pour lancer la cron (URL fournie)
- Gestion de ligne partielle (duplication des lignes avec quantités/états distincts)
"""

import os
import re
import time
import random
import requests
import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import datetime
import paramiko

# =============================
# Config SFTP (secrets ou env)
# =============================
def get_sftp_config():
    """Récupère la config SFTP depuis st.secrets['sftp'] ou variables d'environnement."""
    try:
        sftp_conf = st.secrets["sftp"]
        return {
            "host": sftp_conf.get("host"),
            "user": sftp_conf.get("user"),
            "pass": sftp_conf.get("pass"),
            "dir": sftp_conf.get("dir", "refonteTest"),
            "port": int(sftp_conf.get("port", 22)),
        }
    except Exception:
        return {
            "host": os.environ.get("SFTP_HOST"),
            "user": os.environ.get("SFTP_USER"),
            "pass": os.environ.get("SFTP_PASS"),
            "dir": os.environ.get("SFTP_DIR", "refonteTest"),
            "port": int(os.environ.get("SFTP_PORT", 22)),
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
    "En traitement",
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
# URL CRON à lancer
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
# Génération CSV par commande
# =============================
def generer_csv_par_commande(
    df: pd.DataFrame,
    etats: list,
    transporteurs: list,
    mode_etat: str,             # "unique" | "cyclique" | "aleatoire"
    nb_max=None,
    partiel_active: bool = False,
    partiel_qte: int = 1,
    partiel_etat_a: str | None = None,
    partiel_etat_b: str | None = None,
):
    """
    Construit des CSV d'export par commande :
    - Découpe des colonnes pipe ("|")
    - Attribution d'état selon le mode paramétré
    - Gestion de ligne partielle si activée
    - Retourne une liste (nom_fichier, buffer_csv)
    """
    no_commande_base = 1873036
    num_commande = no_commande_base
    fichiers = []
    commandes_generees = 0

    # Filtrer les lignes sans Code Mistral
    if "Code Mistral" in df.columns:
        df = df[df["Code Mistral"].notna()]
        df = df[df["Code Mistral"].astype(str).str.strip() != ""]

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
            return int(float(str(val).replace(",", ".").strip
