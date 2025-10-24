import streamlit as st

st.set_page_config(page_title="📦 Envoi états de commande", page_icon="📤", layout="wide")

# ⚠️ Redirection automatique vers la page 1 (une seule fois)
if "did_redirect" not in st.session_state:
    st.session_state.did_redirect = True
    try:
        # Nom ASCII recommandé
        st.switch_page("pages/1_envoi_etats_de_commande.py")
    except Exception:
        # Fallback si ton fichier a encore des emojis/espaces
        st.switch_page("pages/1_📦 Envoi états de commande.py")

# (Contenu de secours si la redirection ne se fait pas)
st.title("📦 Envoi états de commande")
st.write("Redirection automatique activée. Utilise le menu de gauche si besoin.")
