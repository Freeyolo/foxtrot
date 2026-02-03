import streamlit as st
import pandas as pd
import geopandas as gpd

# ------------------------------------------------------------
# 0. CONSTANTS & FUNCTIONS
# ------------------------------------------------------------

# Probabilities Dict
LAGER_FREKVENSER = {
    "Armert betong": 5e-5,
    "Betongiglo": 1.5e-5,
    "Fjell-lager": 1e-6,
    "Nisjelager": 1.5e-4,
    "Stålcontainer": 1.5e-4
}

def calculate_detonation_prob(row):
    """
    Calculates probability based on storage type and NEI.
    Formula: Base Frequency + (1.5e-10 * NEI)
    """
    lager_type = row.get("Type", "Stålcontainer")
    nei = row.get("NEI (kg)", 0)
    
    # Get base frequency, default to Stålcontainer if type not found
    freq = LAGER_FREKVENSER.get(lager_type, 1.5e-4)
    
    return freq + (1.5e-10 * nei)

# ------------------------------------------------------------
# 1. PAGE SETUP
# ------------------------------------------------------------
st.set_page_config(
    page_title="QRA Parametere",
    page_icon=":material/settings:",
)

st.title("Definer QRA Parametere")
st.write("Her definerer du detaljer for lageret og eksponeringsfaktorer for de valgte objektene.")
st.session_state
# ------------------------------------------------------------
# 2. STATE CHECKS
# ------------------------------------------------------------
if "qra_selected_gdf" not in st.session_state or st.session_state["qra_selected_gdf"] is None:
    st.warning("Ingen objekter er valgt. Gå tilbake til kart-analysen.")
    st.page_link("pages/2_QD_analyse.py", label="Gå til kart", icon=":material/map:")
    st.stop()

if "last_calc_inputs" not in st.session_state:
    st.error("Mangler inngangsverdier (Nord/Øst). Start på forsiden.")
    st.page_link("pages/1_Input.py", label="Gå til forsiden", icon=":material/home:")
    st.stop()

df_inputs = st.session_state["last_calc_inputs"]
qra_sel = st.session_state["qra_selected_gdf"].copy()

# ------------------------------------------------------------
# 3. LAGER (SOURCE)
# ------------------------------------------------------------
st.subheader("1. Lagerkonfigurasjon")
st.info("Beskriv lagringsenhetene. Sannsynlighet for detonasjon beregnes automatisk basert på type og mengde.")
