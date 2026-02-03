import streamlit as st
import pandas as pd
import geopandas as gpd

# ------------------------------------------------------------
# 0. CONSTANTS & FUNCTIONS
# ------------------------------------------------------------

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
    # Note: We must use the column name as it exists in the editing DataFrame
    nei = row.get("NEI (kg)", 0) 
    
    freq = LAGER_FREKVENSER.get(lager_type, 1.5e-4)
    return freq + (1.5e-10 * nei)

# ------------------------------------------------------------
# 1. PAGE SETUP
# ------------------------------------------------------------
st.set_page_config(
    page_title="QRA Parametere",
    page_icon=":material/settings:",
)

# ------------------------------------------------------------
# 2. STATE CHECKS & DATA LOADING
# ------------------------------------------------------------
if "gdf_anlegg" not in st.session_state or not st.session_state["gdf_anlegg"]:
    st.warning("Ingen anleggsdata funnet. Gå tilbake til kart-analysen.")
    # Stop execution if data is missing
    st.stop()

# ------------------------------------------------------------
# 3. INITIALIZE EDITABLE DATAFRAME
# ------------------------------------------------------------
# We only create 'df_lager' once. If it exists in session_state, 
# we skip this block to preserve user edits.
if "df_lager" not in st.session_state:
    
    gdf_source = st.session_state["gdf_anlegg"]
    
    # We iterate through the source GDF to create the initial lager DataFrame.
    # This handles cases where gdf_anlegg might have 1 row or multiple rows.
    lager_list = []
    
    for idx, row in gdf_source.iterrows():
        nei_val = row["NEI"]
        
        lager_list.append({
            "Navn": "Hovedlager", 
            "Type": "Stålcontainer",
            "Prob. det": 0.0, # Will calculate immediately below
            "NEI (kg)": nei_val,
            "Bruttovekt": 1.1 * nei_val,
            "Bygningsmasse (tonn)": 6.0
        })
    
    df_init = pd.DataFrame(lager_list)
    
    # Calculate the initial probability based on the default 'Stålcontainer'
    df_init["Prob. det"] = df_init.apply(calculate_detonation_prob, axis=1)
    
    # Save to session state
    st.session_state["df_lager"] = df_init

# ------------------------------------------------------------
# 4. DATA EDITOR
# ------------------------------------------------------------
st.subheader("Rediger Lagerdata")

st.page_link("pages/1_Input.py", label="Gå til forside for å endre netto eksplosivinnhold", icon=":material/home:", width="stretch")
st.info("Sannsynlighet er automatisk utregnet basert på lagertype og NEI, kan også settes manuelt")
# Using st.data_editor to allow interaction
edited_df = st.data_editor(
    st.session_state["df_lager"],
    num_rows="fixed",
    column_config={
        "Type": st.column_config.SelectboxColumn(
            "Lagertype",
            help="Velg type lager for å oppdatere sannsynlighet",
            width="medium",
            options=list(LAGER_FREKVENSER.keys()),
            required=True
        ),
        "Prob. det": st.column_config.NumberColumn(
            "Sannsynlighet",
            help="Kalkuleres automatisk basert på Type og NEI",
            format="%.3e", # Scientific notation
            disabled=False   # Read-only for the user
        ),
        "Bygningsmasse (tonn)": st.column_config.NumberColumn(
            "Bygningsmasse (tonn)",
            min_value=0.0,
            step=0.5,
            format="%.1f"
        ),
        "NEI (kg)": st.column_config.NumberColumn(
            "NEI (kg)",
            format="%.0f",
            disabled=True # Usually fixed from input, change to False if you want it editable
        ),
        "Bruttovekt": st.column_config.NumberColumn(
            format="%.1f"
        )
    },
    hide_index=True
)

# ------------------------------------------------------------
# 5. REACTIVE UPDATE LOGIC
# ------------------------------------------------------------

# 1. Recalculate probabilities based on the CURRENT state of the editor (edited_df)
#    This catches if the user changed the "Type" dropdown.
recalculated_probs = edited_df.apply(calculate_detonation_prob, axis=1)

# 2. Check for changes in Probability (Triggered by Type change)
#    We compare the calculated values with what is currently inside the dataframe.
if not recalculated_probs.equals(edited_df["Prob. det"]):
    # Apply new calculation
    edited_df["Prob. det"] = recalculated_probs
    
    # Update Session State
    st.session_state["df_lager"] = edited_df
    
    # Rerun to force the editor to display the new Number
    st.rerun()

# 3. Check for other manual changes (e.g., Bygningsmasse)
#    If the user typed a number, we must save it to session state so it sticks.
elif not edited_df.equals(st.session_state["df_lager"]):
    st.session_state["df_lager"] = edited_df

st.divider()
st.subheader("Definer parametere for utsatte objekter")
st.session_state
st.write("testing")