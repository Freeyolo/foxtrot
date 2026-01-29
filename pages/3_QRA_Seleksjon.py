import streamlit as st
import geopandas as gpd
import pandas as pd
from blast_model import incident_pressure

# --- 1. SETUP & STATE CHECK ---
st.set_page_config(page_title="Seleksjon for QRA", page_icon=":material/checklist:")

if "GISanalysis_complete" not in st.session_state or not st.session_state["GISanalysis_complete"]:
    st.warning("Ingen data funnet. Vennligst kjør analysen på hovedsiden først.")
    st.page_link("streamlit_app.py", label="Gå til hovedside", icon=":material/home:") 
    st.stop()

# --- 2. STALE DATA CHECK (CRITICAL FIX) ---
# We check if the inputs (NEI/Coords) have changed since the last time we visited this page.
# If they have changed, we MUST clear the saved table state to ensure new defaults are applied.
current_inputs = st.session_state.get("last_calc_inputs", {})
saved_inputs_for_qra = st.session_state.get("qra_inputs_snapshot", {})

if current_inputs != saved_inputs_for_qra:
    # Data has changed! Wipe the old editor state to force a recalculation of defaults
    if "qra_editor_data" in st.session_state:
        del st.session_state["qra_editor_data"]
    # Update the snapshot
    st.session_state["qra_inputs_snapshot"] = current_inputs

# --- 3. RETRIEVE DATA & RE-CALCULATE METRICS ---
gdf_anlegg = st.session_state["gdf_anlegg"]
inputs = current_inputs
NEI = inputs["nei"]

# Retrieve the full dataset
df_work = st.session_state["exp_buildings_gdf"].copy()

# --- 4. HELPER FUNCTIONS (QD & STATUS) ---
def QD_func(NEI):
    QD_syk = max(round(44.4 * NEI ** (1/3)), 800)
    QD_bolig = max(round(22.2 * NEI ** (1/3)), 400)
    QD_vei = max(round(14.8 * NEI ** (1/3)), 180)
    return QD_syk, QD_bolig, QD_vei

# Recalculate limits and physics
QD_syk, QD_bolig, QD_vei = QD_func(NEI)
anlegg_point = gdf_anlegg.geometry.iloc[0]

# Recalculate distance/pressure
df_work["avstand_meter"] = df_work.geometry.distance(anlegg_point)
df_work["trykk_kPa"] = df_work["avstand_meter"].apply(lambda d: incident_pressure(d, NEI))

# --- 5. DEFINE STATUS AND DEFAULT SELECTION LOGIC ---
def analyze_row(row):
    """
    Returns (Status_String, Include_Boolean)
    Include_Boolean is TRUE only if the object is inside the hazard zone.
    """
    cat = row["kategori"]
    dist = row["avstand_meter"]
    
    # A. Check "Ingen beskyttelse" -> Always False
    if cat == "ingen beskyttelse":
        return "Ingen beskyttelse", False
    
    # B. Check "Skjermingsverdig" (Special case: check against QD_syk)
    if cat == "skjermingsverdig":
        if dist < QD_syk:
            return "⚠️ Skjermingsverdig", True
        else:
            return "✅ Trygg", False

    # C. Check Standard Categories
    limit = 0
    if cat == "sårbar":
        limit = QD_syk
    elif cat == "bolig":
        limit = QD_bolig
    elif cat in ["industri", "vei/industri"]:
        limit = QD_vei
    else:
        return "❓ Ukjent", False

    # D. Determine Violation
    if dist < limit:
        return "⚠️ Innenfor QD", True
    else:
        return "✅ Trygg", False

# Apply logic
# We zip the result to separate columns efficiently
status_results = df_work.apply(analyze_row, axis=1)
df_work["Status"] = [x[0] for x in status_results]
calculated_defaults = [x[1] for x in status_results]

# --- 6. INITIALIZE EDITOR STATE ---
if "qra_editor_data" not in st.session_state:
    # FIRST LOAD (or after reset): Use our calculated defaults
    df_work["Inkluder"] = calculated_defaults
    st.session_state["qra_editor_data"] = df_work
else:
    # RELOAD: The user is coming back to this page.
    # We want to keep their manual checkmarks, BUT we must be careful if the row count changed.
    saved_df = st.session_state["qra_editor_data"]
    
    # Safe Merge: Use the calculated default as a base, overwrite with saved if index exists
    df_work["Inkluder"] = calculated_defaults # Start with strict defaults
    
    # If indices match, restore user's previous choices
    common_indices = df_work.index.intersection(saved_df.index)
    df_work.loc[common_indices, "Inkluder"] = saved_df.loc[common_indices, "Inkluder"]

# Sort: Included first, then by distance
df_work = df_work.sort_values(by=["Inkluder", "avstand_meter"], ascending=[False, True])

# Filter Columns
cols_to_show = ["Inkluder", "Status", "Beskrivelse", "kategori", "avstand_meter", "trykk_kPa"]
cols_to_show = [c for c in cols_to_show if c in df_work.columns]
df_work = df_work[cols_to_show]

# --- 7. RENDER PAGE ---
st.title("Seleksjon av objekter til QRA")
st.write("Velg hvilke objekter som skal tas med videre.")
st.info(
    "**Standardvalg:** Kun objekter som ligger **innenfor** sikkerhetsavstandene er valgt automatisk. "
    "Objekter som er 'Trygge' eller har 'Ingen beskyttelse' er synlige i tabellen, men ikke valgt."
)

# Reset Button (In case user wants to restore strict defaults manually)
if st.button("Tilbakestill til standardvalg"):
    if "qra_editor_data" in st.session_state:
        del st.session_state["qra_editor_data"]
    st.rerun()

# --- 8. DATA EDITOR ---
# We use a dynamic key based on inputs to ensure the widget resets if inputs change
editor_key = f"qra_editor_{inputs.get('nei', 0)}_{inputs.get('nord', 0)}"

edited_df = st.data_editor(
    df_work,
    column_config={
        "Inkluder": st.column_config.CheckboxColumn(
            "Inkluder?",
            help="Huk av for å ta med i videre beregninger",
            default=False, 
        ),
        "Status": st.column_config.TextColumn(
            "Status", width="medium", disabled=True
        ),
        "avstand_meter": st.column_config.NumberColumn(
            "Avstand", format="%.1f m", disabled=True
        ),
        "trykk_kPa": st.column_config.NumberColumn(
            "Trykk", format="%.2f kPa", disabled=True
        ),
        "Beskrivelse": st.column_config.TextColumn(
            "Beskrivelse", width="large", disabled=True
        ),
        "kategori": st.column_config.TextColumn(
            "Kategori", disabled=True
        ),
    },
    hide_index=True,
    width="stretch",
    key=editor_key
)

# --- 9. SAVE SELECTION ---
num_selected = edited_df["Inkluder"].sum()
num_total = len(edited_df)

st.write(f"**Valgt:** {num_selected} av {num_total} objekter.")

if st.button("Bekreft utvalg og gå videre", type="primary"):
    # 1. Save state
    st.session_state["qra_editor_data"] = edited_df
    
    # 2. Extract
    original_gdf = st.session_state["exp_buildings_gdf"].copy()
    selected_indices = edited_df[edited_df["Inkluder"]].index
    
    final_qra_gdf = original_gdf.loc[selected_indices].copy()
    final_qra_gdf["avstand_meter"] = edited_df.loc[selected_indices, "avstand_meter"]
    final_qra_gdf["trykk_kPa"] = edited_df.loc[selected_indices, "trykk_kPa"]
    final_qra_gdf["Status"] = edited_df.loc[selected_indices, "Status"]
    
    # 3. Store
    st.session_state["qra_selected_gdf"] = final_qra_gdf
    
    st.success(f"Lagret {len(final_qra_gdf)} objekter! Du kan nå gå videre til neste steg.")