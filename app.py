import os, pathlib, streamlit as st
root = pathlib.Path(__file__).parent
st.sidebar.write("📂 pages/:", [f for f in os.listdir(root / "pages")] if (root / "pages").exists() else "—")


import streamlit as st
st.set_page_config(page_title="📦 Envoi états de commande", page_icon="📤", layout="wide")

st.title("📦 Envoi états de commande")
st.write("Bienvenue. Utilise le menu de gauche pour naviguer.")
