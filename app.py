import streamlit as st

st.set_page_config(page_title="📦 Envoi états de commande", page_icon="📤", layout="wide")

pg_envoi_cmd = st.Page("pages/1_📦 Envoi états de commande.py", title="📦 Envoi états de commande")
pg_facture   = st.Page("pages/2_📑 Envoi facture.py",        title="📑 Envoi facture")

nav = st.navigation([pg_envoi_cmd, pg_facture])
nav.run()

