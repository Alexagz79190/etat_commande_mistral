# app.py
import streamlit as st

st.set_page_config(page_title="📦 Envoi états de commande", page_icon="📤", layout="wide")

# Définis tes pages explicitement (ordre et libellés maîtrisés)
pg_envoi_cmd = st.Page("pages/1_envoi_etats_de_commande.py", title="📦 Envoi états de commande")
pg_facture   = st.Page("pages/2_envoi_facture.py",        title="📑 Envoi facture")

# Barre latérale = seulement ces pages (plus de “app”)
nav = st.navigation([pg_envoi_cmd, pg_facture])
nav.run()
