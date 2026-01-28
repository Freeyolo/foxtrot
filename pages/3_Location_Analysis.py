import streamlit as st
import geopandas as gpd
import pandas as pd
import numpy as np
import os
from blast_model import incident_pressure

# --- 1. SETUP & CONFIG ---
st.set_page_config(page_title="Analyse av bygninger", page_icon=":material/analytics:")

# Function to load and cache the CSV lookup table
@st.cache_data
def load_building_codes():
    # 1. Get the directory where 'page3.py' is located (.../ExploGIS/pages)
    current_dir = os.path.dirname(__file__)
    
    # 2. Construct the path to the CSV in the parent directory (.../ExploGIS/bygningstype.csv)
    file_path = os.path.join(current_dir, "..", "bygningstype.csv")
    
    # 3. Read the file
    try:
        df = pd.read_csv(file_path, sep=";", encoding="utf-8", dtype={'Kodeverdi': str})
        return df[['Kodeverdi', 'Navn']]
    except FileNotFoundError:
        st.error(f"Could not find file at: {file_path}")
        return pd.DataFrame()

# Check if analysis is ready
if "GISanalysis_complete" not in st.session_state or not st.session_state["GISanalysis_complete"]:
    st.warning("Ingen data funnet. Vennligst gå tilbake til hovedsiden og kjør analysen først.")
    st.page_link("streamlit_app.py", label="Gå til hovedside", icon=":material/home:") 
    st.stop()

# --- 2. RETRIEVE DATA ---
gdf_anlegg = st.session_state["gdf_anlegg"]
exp_buildings_gdf = st.session_state["exp_buildings_gdf"].copy()
inputs = st.session_state["last_calc_inputs"]
NEI = inputs["nei"]

# Load the building codes (Adjust filename if yours is different)
df_codes = load_building_codes()

# --- 3. HELPER FUNCTION ---
def QD_func(NEI):
    QD_syk = max(round(44.4 * NEI ** (1/3)), 800)
    QD_bolig = max(round(22.2 * NEI ** (1/3)), 400)
    QD_vei = max(round(14.8 * NEI ** (1/3)), 180)
    return QD_syk, QD_bolig, QD_vei

# --- 4. CALCULATIONS ---
QD_syk, QD_bolig, QD_vei = QD_func(NEI)

# Distance Calculation
anlegg_point = gdf_anlegg.geometry.iloc[0]
exp_buildings_gdf["avstand_meter"] = exp_buildings_gdf.geometry.distance(anlegg_point)

# Pressure Calculation
exp_buildings_gdf["trykk_kPa"] = exp_buildings_gdf["avstand_meter"].apply(
    lambda d: incident_pressure(d, NEI)
)

# --- MERGE DESCRIPTIONS ---
# Ensure 'bygningstype' is string to match 'Kodeverdi'
exp_buildings_gdf["bygningstype"] = exp_buildings_gdf["bygningstype"].astype(str)

# Left join to add the description
exp_buildings_gdf = exp_buildings_gdf.merge(
    df_codes, 
    left_on="bygningstype", 
    right_on="Kodeverdi", 
    how="left"
)

# If a code isn't found in the CSV, fill 'Navn' with the original numeric code
exp_buildings_gdf["Navn"] = exp_buildings_gdf["Navn"].fillna(exp_buildings_gdf["bygningstype"])

# Sort by distance
exp_buildings_gdf = exp_buildings_gdf.sort_values(by="avstand_meter")

# --- 5. DETERMINE VIOLATIONS ---
df_syk_inside = exp_buildings_gdf[(exp_buildings_gdf["kategori"] == "sårbar") & (exp_buildings_gdf["avstand_meter"] < QD_syk)]
df_bolig_inside = exp_buildings_gdf[(exp_buildings_gdf["kategori"] == "bolig") & (exp_buildings_gdf["avstand_meter"] < QD_bolig)]
df_industri_inside = exp_buildings_gdf[(exp_buildings_gdf["kategori"] == "industri") & (exp_buildings_gdf["avstand_meter"] < QD_vei)]

total_violation_count = len(df_syk_inside) + len(df_bolig_inside) + len(df_industri_inside)

# --- 6. RENDER PAGE ---
st.title("Detaljert Analyse")
st.write(f"Analyse basert på et netto eksplosivinnhold (NEI) på **{NEI} kg**.")

st.divider()

# --- A. SUMMARY ---
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Sårbare objekt", len(df_syk_inside), help=f"Grense: {QD_syk} m")
with col2:
    st.metric("Boliger", len(df_bolig_inside), help=f"Grense: {QD_bolig} m")
with col3:
    st.metric("Industri / Næring", len(df_industri_inside), help=f"Grense: {QD_vei} m")

if total_violation_count > 0:
    st.error(f"Totalt {total_violation_count} bygninger ligger for nærme anlegget.")
else:
    st.success("Ingen bygninger bryter med sikkerhetsavstandene! :shield:")

st.divider()

# --- B. DETAILED TABLE ---
st.subheader("Tabell over alle bygninger")

# Define status logic
def get_status(row):
    cat = row["kategori"]
    dist = row["avstand_meter"]
    if cat == "sårbar" and dist < QD_syk: return "⚠️ Innenfor sone"
    elif cat == "bolig" and dist < QD_bolig: return "⚠️ Innenfor sone"
    elif cat == "industri" and dist < QD_vei: return "⚠️ Innenfor sone"
    else: return "✅ Trygg"

# Create display DataFrame with the new 'Navn' column
# We use 'Navn' instead of 'bygningstype' (the number)
display_df = exp_buildings_gdf[["Navn", "kategori", "avstand_meter", "trykk_kPa"]].copy()

display_df["Status"] = exp_buildings_gdf.apply(get_status, axis=1)

# Rename columns for final display
display_df.columns = ["Beskrivelse", "Kategori", "Avstand (m)", "Trykk (kPa)", "Status"]

st.dataframe(
    display_df, 
    use_container_width=True,
    hide_index=True,
    column_config={
        "Avstand (m)": st.column_config.NumberColumn(format="%.1f m"),
        "Trykk (kPa)": st.column_config.NumberColumn(format="%.2f kPa"),
        "Beskrivelse": st.column_config.TextColumn(width="large"),
    }
)

csv = display_df.to_csv(index=False).encode('utf-8')
st.download_button("Last ned tabell som CSV", csv, 'bygningsanalyse_resultat.csv', 'text/csv')