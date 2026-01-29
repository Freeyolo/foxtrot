import streamlit as st
import geopandas as gpd
import pandas as pd
import numpy as np
from blast_model import incident_pressure

# --- 1. SETUP & STATE CHECK ---
st.set_page_config(page_title="Analyse av objekter", page_icon=":material/analytics:")

if "GISanalysis_complete" not in st.session_state or not st.session_state["GISanalysis_complete"]:
    st.warning("Ingen data funnet. Vennligst gå tilbake til hovedsiden og kjør analysen først.")
    st.page_link("streamlit_app.py", label="Gå til hovedside", icon=":material/home:") 
    st.stop()

# --- 2. RETRIEVE INPUTS ---
gdf_anlegg = st.session_state["gdf_anlegg"]
inputs = st.session_state["last_calc_inputs"]
NEI = inputs["nei"]

# --- 3. HELPER FUNCTION (QD Limits) ---
def QD_func(NEI):
    """Calculates regulatory safety distances."""
    QD_syk = max(round(44.4 * NEI ** (1/3)), 800)
    QD_bolig = max(round(22.2 * NEI ** (1/3)), 400)
    QD_vei = max(round(14.8 * NEI ** (1/3)), 180)
    return QD_syk, QD_bolig, QD_vei

QD_syk, QD_bolig, QD_vei = QD_func(NEI)

# --- 4. CALCULATIONS (PERFORM ONCE & PERSIST) ---
# We check if 'gdf_calculated' exists. If not, we perform the heavy math and save it.
if "gdf_calculated" not in st.session_state or st.session_state["gdf_calculated"] is None:
    
    # Load RAW data from Page 1
    df_calc = st.session_state["exp_buildings_gdf"].copy()
    
    # A. Calculate Distance (Geometry)
    anlegg_point = gdf_anlegg.geometry.iloc[0]
    df_calc["avstand_meter"] = df_calc.geometry.distance(anlegg_point)
    
    # B. Calculate Blast Overpressure (Physics Model)
    # This is the "expensive" operation we want to do only once
    df_calc["trykk_kPa"] = df_calc["avstand_meter"].apply(lambda d: incident_pressure(d, NEI))
    
    # C. Sort by distance
    df_calc = df_calc.sort_values(by="avstand_meter")
    
    # SAVE to Session State
    st.session_state["gdf_calculated"] = df_calc

# --- 5. LOAD CALCULATED DATA ---
# Now we simply refer to the stored, calculated DataFrame
exp_buildings_gdf = st.session_state["gdf_calculated"]

# --- 6. DETERMINE VIOLATIONS & METRICS ---

# Helper to find closest object
def get_min_distance(df, category):
    subset = df[df["kategori"] == category]
    if subset.empty:
        return None
    return subset["avstand_meter"].min()

min_dist_syk = get_min_distance(exp_buildings_gdf, "sårbar")
min_dist_bolig = get_min_distance(exp_buildings_gdf, "bolig")
min_dist_industri = get_min_distance(exp_buildings_gdf, "vei/industri")

# Filter Violations
df_syk_inside = exp_buildings_gdf[
    (exp_buildings_gdf["kategori"] == "sårbar") & 
    (exp_buildings_gdf["avstand_meter"] < QD_syk)
]

df_bolig_inside = exp_buildings_gdf[
    (exp_buildings_gdf["kategori"] == "bolig") & 
    (exp_buildings_gdf["avstand_meter"] < QD_bolig)
]

df_industri_inside = exp_buildings_gdf[
    (exp_buildings_gdf["kategori"] == "vei/industri") & 
    (exp_buildings_gdf["avstand_meter"] < QD_vei)
]

df_skjerming_inside = exp_buildings_gdf[
    (exp_buildings_gdf["kategori"] == "skjermingsverdig") & 
    (exp_buildings_gdf["avstand_meter"] < QD_syk)
]

total_violation_count = len(df_syk_inside) + len(df_bolig_inside) + len(df_industri_inside)

# --- 7. RENDER PAGE ---
st.title("Detaljert Analyse")
st.write(f"Analyse basert på et netto eksplosivinnhold (NEI) på **{NEI} kg**.")

st.divider()

# --- A. SUMMARY METRICS ---
st.subheader("Oppsummering av eksponerte objekt")

col1, col2, col3 = st.columns(3)

def fmt_dist(val):
    return f"{val:.1f} m" if val is not None else "Ingen funnet"

# 1. SÅRBAR
with col1:
    st.markdown("#### Sårbar")
    st.metric(
        label="Antall brudd", 
        value=len(df_syk_inside),
        delta_color="inverse" if len(df_syk_inside) > 0 else "off"
    )
    st.caption(f"📏 **Krav (QD):** {QD_syk} m")
    st.caption(f"🏥 **Nærmeste:** {fmt_dist(min_dist_syk)}")

# 2. BOLIG
with col2:
    st.markdown("#### Bolig")
    st.metric(
        label="Antall brudd", 
        value=len(df_bolig_inside),
        delta_color="inverse" if len(df_bolig_inside) > 0 else "off"
    )
    st.caption(f"📏 **Krav (QD):** {QD_bolig} m")
    st.caption(f"🏠 **Nærmeste:** {fmt_dist(min_dist_bolig)}")

# 3. INDUSTRI
with col3:
    st.markdown("#### Industri / Vei")
    st.metric(
        label="Antall brudd", 
        value=len(df_industri_inside),
        delta_color="inverse" if len(df_industri_inside) > 0 else "off"
    )
    st.caption(f"📏 **Krav (QD):** {QD_vei} m")
    st.caption(f"🏭 **Nærmeste:** {fmt_dist(min_dist_industri)}")

st.divider()

# --- WARNINGS ---
if not df_skjerming_inside.empty:
    st.warning(
        f"⚠️ **OBS:** Det er identifisert **{len(df_skjerming_inside)}** skjermingsverdige objekter "
        f"innenfor sikkerhetsavstanden for sårbare objekter ({QD_syk} m). "
        "Disse bør vurderes særskilt."
    )

if total_violation_count == 0:
    st.success("Ingen bygninger innenfor sin respektive sikkerhetsavstand! :shield:")
else:
    st.error(f"Totalt **{total_violation_count}** objekter innenfor sikkerhetsavstandene.")

st.divider()

# --- B. DETAILED TABLE ---
st.subheader("Tabell over alle bygninger")

# Prepare display DataFrame
display_df = exp_buildings_gdf[["Beskrivelse", "kategori", "avstand_meter", "trykk_kPa"]].copy()

# Add Status Column
def get_status(row):
    cat = row["kategori"]
    dist = row["avstand_meter"]
    
    # Check violations
    if cat == "sårbar" and dist < QD_syk:
        return "⚠️ Innenfor QD  (sårbar)"
    elif cat == "bolig" and dist < QD_bolig:
        return "⚠️ Innenfor QD (bolig)"
    elif cat == "vei/industri" and dist < QD_vei:
        return "⚠️ Innenfor QD (vei/ind.)"
    elif cat == "ingen beskyttelse":
        return None
    else:
        return "✅ Trygg"

display_df["Status"] = display_df.apply(get_status, axis=1)

# Rename columns
display_df.columns = ["Beskrivelse", "Kategori", "Avstand (m)", "Trykk (kPa)", "Status"]

# Display Table with Formatting
st.dataframe(
    display_df, 
    width="stretch",
    hide_index=True,
    column_config={
        "Avstand (m)": st.column_config.NumberColumn(format="%.1f m"),
        "Trykk (kPa)": st.column_config.NumberColumn(format="%.2f kPa"),
        "Status": st.column_config.TextColumn(width="medium"),
    }
)

# Navigation and Download
st.page_link(
    "pages/3_QRA_seleksjon.py", 
    label="Gå til side for seleksjon av objekter til QRA", 
    icon=":material/calculate:", 
    width="stretch",
)

csv = display_df.to_csv(index=False).encode('utf-8')
st.download_button(
    label="Last ned tabell som CSV",
    data=csv,
    file_name='bygningsanalyse_resultat.csv',
    mime='text/csv',
)