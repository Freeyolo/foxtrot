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
# 2. STATE CHECKS & DATA LOADING (ANLEGG AND SELECTION)
# ------------------------------------------------------------
if "gdf_anlegg" not in st.session_state or st.session_state["gdf_anlegg"].empty:
    st.warning("Ingen anleggsdata funnet. Gå tilbake til input siden.")
    st.page_link("pages/1_Input.py", label="Gå til input side", icon=":material/home:", width="stretch")
    st.stop()

if "qra_selected_gdf" not in st.session_state or st.session_state["qra_selected_gdf"].empty:
    st.warning("Ingen objekter valgt for kvantitativ risikoanalyse (QRA)")
    st.page_link("pages/3_QRA_Seleksjon.py", label="Gå til QRA Seleksjon", icon=":material/home:", width="stretch")
    st.stop()
    
# ------------------------------------------------------------
# 3. INITIALIZE EDITABLE DATAFRAME (LAGER)
# ------------------------------------------------------------
if "df_lager" not in st.session_state:
    
    gdf_source = st.session_state["gdf_anlegg"]
    
    lager_list = []
    
    for idx, row in gdf_source.iterrows():
        nei_val = row["NEI"]
        
        lager_list.append({
            "Navn": "Hovedlager", 
            "Type": "Stålcontainer",
            "Prob. det": 0.0, 
            "NEI (kg)": nei_val,
            "Bruttovekt": 1.1 * nei_val,
            "Bygningsmasse (tonn)": 6.0
        })
    
    df_init = pd.DataFrame(lager_list)
    df_init["Prob. det"] = df_init.apply(calculate_detonation_prob, axis=1)
    
    st.session_state["df_lager"] = df_init

# ------------------------------------------------------------
# 4. DATA EDITOR (LAGER)
# ------------------------------------------------------------
st.subheader("Rediger Lagerdata")

st.page_link("pages/1_Input.py", label="Gå til forside for å endre netto eksplosivinnhold", icon=":material/home:", width="stretch")
st.info("Sannsynlighet er automatisk utregnet basert på lagertype og NEI, kan også settes manuelt")

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
            format="%.3e", 
            disabled=False   
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
            disabled=True 
        ),
        "Bruttovekt": st.column_config.NumberColumn(
            format="%.1f"
        )
    },
    hide_index=True
)

# ------------------------------------------------------------
# 5. REACTIVE UPDATE LOGIC (LAGER)
# ------------------------------------------------------------
recalculated_probs = edited_df.apply(calculate_detonation_prob, axis=1)

if not recalculated_probs.equals(edited_df["Prob. det"]):
    edited_df["Prob. det"] = recalculated_probs
    st.session_state["df_lager"] = edited_df
    st.rerun()

elif not edited_df.equals(st.session_state["df_lager"]):
    st.session_state["df_lager"] = edited_df

# ------------------------------------------------------------
# 6. EXPOSED OBJECTS SECTION
# ------------------------------------------------------------
st.divider()
st.subheader("Definer parametere for utsatte objekter")


if "qra_params_df" not in st.session_state:
    
    # 1. Get copy of selected data
    df_source = st.session_state["qra_selected_gdf"].copy()
    
    # 2. Reset index to get a clean 0, 1, 2... index for the table
    df_source = df_source.reset_index(drop=True)
    
    # 3. Set default Bygningstype (BN)
    df_source["Bygningstype"] = "BN"
    df_source["Geometritype"] = "PF"
    
    # 4. Set default Tilstedeværelse based on category
    def get_presence_default(cat):
        cat_lower = str(cat).lower()
        if "bolig" in cat_lower or "sårbar" in cat_lower:
            return 1.0
        return 0.0

    df_source["Tilstedeværelse"] = df_source["kategori"].apply(get_presence_default)
    
    # 5. Store only the columns we need for this view in session state
    # We keep 'kategori' hidden for logic if needed, but display the rest
    cols_to_keep = ["beskrivelse", "avstand_meter", "trykk_kPa", "Bygningstype","Geometritype", "Tilstedeværelse", "kategori"]
    st.session_state["qra_params_df"] = df_source[cols_to_keep]

# ------------------------------------------------------------
# 6.2 DATA EDITOR (PARAMS)
# ------------------------------------------------------------
st.markdown("Her defineres bygningstype og oppholdstid for de valgte objektene.")

# We use the session state DF as the "master"
df_params = st.session_state["qra_params_df"]

edited_params = st.data_editor(
    df_params,
    column_config={
        "beskrivelse": st.column_config.TextColumn(
            "Beskrivelse",
            disabled=True 
        ),
        "avstand_meter": st.column_config.NumberColumn(
            "Avstand (m)",
            format="%.1f",
            disabled=True
        ),
        "trykk_kPa": st.column_config.NumberColumn(
            "Trykk (kPa)",
            format="%.2f",
            disabled=True
        ),
        "Bygningstype": st.column_config.SelectboxColumn(
            "Bygningstype",
            help="BN: Normal, BL: Lett, BS: Forsterket",
            width="medium",
            options=["BN", "BL", "BS"],
            required=True
        ),
        "Geometritype": st.column_config.SelectboxColumn(
            "Geometritype",
            help="PF: punkt, AL: Areal, LR: Lineær",
            width="medium",
            options=["PF", "AL", "LR"],
            required=True
        ),
        "Tilstedeværelse": st.column_config.NumberColumn(
            "Tilstedeværelse (0-1)",
            help="Sannsynlighet for at personer er tilstede (0.0 - 1.0)",
            min_value=0.0,
            max_value=1.0,
            format="%.3f"
        ),
        # Hide internal columns
        "kategori": None 
    },
    use_container_width=True,
    hide_index=False,
    key="params_editor"
)

# ------------------------------------------------------------
# 6.3 SYNC CHANGES TO STATE
# ------------------------------------------------------------
if not edited_params.equals(st.session_state["qra_params_df"]):
    st.session_state["qra_params_df"] = edited_params
    
# ------------------------------------------------------------
# SITUATIONS
# ------------------------------------------------------------

col1, col2 = st.columns(2)

with col1:
    st.subheader("Situasjoner")
    d = {"Situation":["Dag","Kveld","Natt","Helg"], "Varighet":[0.1,0.2,0.3,0.4]}
    df_sit = pd.DataFrame(data=d)
    st.data_editor(df_sit)
with col2:
    st.header("testing")