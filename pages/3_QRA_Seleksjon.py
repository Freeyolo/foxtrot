import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
from streamlit_folium import st_folium
from pyproj import Transformer
# Import needed only for fallback
from blast_model import incident_pressure

# ------------------------------------------------------------
# 1. PAGE SETUP
# ------------------------------------------------------------
st.set_page_config(
    page_title="Seleksjon for QRA",
    page_icon=":material/checklist:"
)

# ------------------------------------------------------------
# 2. REQUIRED STATE CHECK
# ------------------------------------------------------------
if not st.session_state.get("GISanalysis_complete", False):
    st.warning("Ingen data funnet. Vennligst kjør analysen på hovedsiden først.")
    st.page_link("streamlit_app.py", label="Gå til hovedside", icon=":material/home:", width="stretch")
    st.stop()

# ------------------------------------------------------------
# 3. INPUT STALENESS CHECK
# ------------------------------------------------------------
current_inputs = st.session_state.get("last_calc_inputs", {})
snapshot_inputs = st.session_state.get("qra_input", {})

if current_inputs != snapshot_inputs:
    # Inputs changed (e.g. NEI or location), so previous selection/map is invalid
    keys_to_clear = [
        "qra_editor_data",
        "processed_map_gdf",
        "map_center",
        "map_zoom",
        "last_processed_click",
        "gdf_calculated" # Clear physics cache too if inputs changed
    ]
    for k in keys_to_clear:
        if k in st.session_state:
            del st.session_state[k]

    st.session_state["qra_input"] = current_inputs

# ------------------------------------------------------------
# 4. DATA RETRIEVAL (OPTIMIZED)
# ------------------------------------------------------------
gdf_anlegg = st.session_state["gdf_anlegg"]
NEI = current_inputs["nei"]

# OPTIMIZATION: Check if physics is already calculated in Session State
if "gdf_calculated" in st.session_state and st.session_state["gdf_calculated"] is not None:
    # FAST PATH: Load from memory (Computed on Page 2)
    df_work = st.session_state["gdf_calculated"].copy()
else:
    # SLOW PATH: Fallback calculation (Only runs if Page 2 was skipped)
    df_work = st.session_state["exp_buildings_gdf"].copy()
    anlegg_point = gdf_anlegg.geometry.iloc[0]
    
    # Physics Calculation
    df_work["avstand_meter"] = df_work.geometry.distance(anlegg_point)
    df_work["trykk_kPa"] = df_work["avstand_meter"].apply(lambda d: incident_pressure(d, NEI))
    df_work = df_work.sort_values("avstand_meter")
    
    # Store result so we don't calculate again
    st.session_state["gdf_calculated"] = df_work

# ------------------------------------------------------------
# 5. LOGIC & DEFAULTS (Determine Inclusion)
# ------------------------------------------------------------
def QD_limits(NEI):
    return (
        max(round(44.4 * NEI ** (1 / 3)), 800),
        max(round(22.2 * NEI ** (1 / 3)), 400),
        max(round(14.8 * NEI ** (1 / 3)), 180),
    )

QD_syk, QD_bolig, QD_vei = QD_limits(NEI)

def analyze_row(row):
    cat = row["kategori"]
    dist = row["avstand_meter"]
    
    # Exclusion logic
    if cat == "ingen beskyttelse": 
        return "Ingen beskyttelse", False
    
    # Skjermingsverdig logic
    if cat == "skjermingsverdig":
        return ("🚫 Skjermingsverdig", True) if dist < QD_syk else ("✅ Trygg", False)
    
    # Standard logic
    limit = QD_syk if cat == "sårbar" else (QD_bolig if cat == "bolig" else QD_vei)
    return ("⚠️ Innenfor QD", True) if dist < limit else ("✅ Trygg", False)

# Initialize the Editor DataFrame if not present
if "qra_editor_data" not in st.session_state:
    # Apply logic to determine default status/include
    results = df_work.apply(analyze_row, axis=1)
    df_work["Status"] = [r[0] for r in results]
    df_work["Inkluder"] = [r[1] for r in results]
    
    st.session_state["qra_editor_data"] = df_work.copy()

# ------------------------------------------------------------
# 6. MASTER DATA POINTERS
# ------------------------------------------------------------
# df_current is the Single Source of Truth for this page
df_current = st.session_state["qra_editor_data"]

# Ensure geometry is preserved (in case session state stored it as plain pandas)
if not isinstance(df_current, gpd.GeoDataFrame):
    df_current = gpd.GeoDataFrame(df_current, geometry=df_work.geometry, crs=df_work.crs)

# Create/Update CRS-converted version for Map (Lat/Lon)
if "processed_map_gdf" not in st.session_state:
    st.session_state["processed_map_gdf"] = df_current.to_crs(epsg=4326)

map_gdf = st.session_state["processed_map_gdf"]
# Important: Sync the 'Inkluder' column from editor to the map gdf for coloring
map_gdf["Inkluder"] = df_current["Inkluder"]

# ------------------------------------------------------------
# 7. MAP VIEW STATE
# ------------------------------------------------------------

if "map_center" not in st.session_state:
    anlegg = st.session_state["gdf_anlegg"].geometry.iloc[0]
    transformer = Transformer.from_crs("EPSG:32633", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(anlegg.x, anlegg.y)
    st.session_state["map_center"] = [lat, lon]

# Safety check
if isinstance(st.session_state["map_center"], dict):
    c = st.session_state["map_center"]
    st.session_state["map_center"] = [c.get('lat'), c.get('lng')]

if "last_processed_click" not in st.session_state:
    st.session_state["last_processed_click"] = None

# ------------------------------------------------------------
# 8. UI RENDER
# ------------------------------------------------------------

st.title("Seleksjon av objekter til QRA")
st.write("Klikk på objekter i kartet eller tabellen for å inkludere / ekskludere objektene i kvantitativ risikoanalyse.")
st.info(
    "**Standardvalg:** Kun objekter som ligger **innenfor** sikkerhetsavstandene er valgt automatisk. "
)
col_map, col_table = st.columns(2)

# --- MAP SECTION ---

st.subheader("Kart")

# 1. Base Map (Centered on Anlegg)
m = folium.Map(
    location=st.session_state["map_center"], 
    zoom_start=14,
    tiles="OpenStreetMap"
)

# 2. CALCULATE BOUNDS FOR GDF_SYK (Largest Radius)
# This ensures the map always zooms to fit the safety circle
try:
    gdf_syk = st.session_state["gdf_syk"]
    min_x, min_y, max_x, max_y = gdf_syk.total_bounds
    
    # Transform bounds from UTM33 to Lat/Lon
    transformer = Transformer.from_crs("EPSG:32633", "EPSG:4326", always_xy=True)
    sw_lon, sw_lat = transformer.transform(min_x, min_y)
    ne_lon, ne_lat = transformer.transform(max_x, max_y)
    
    # Apply fit_bounds to the map
    m.fit_bounds([[sw_lat, sw_lon], [ne_lat, ne_lon]])
except Exception as e:

    pass

# 3. Add Anlegg Marker
anlegg_ll = st.session_state["gdf_anlegg"].to_crs(epsg=4326).geometry.iloc[0]
folium.Marker(
    [anlegg_ll.y, anlegg_ll.x],
    icon=folium.Icon(color="blue", icon="bomb", prefix="fa"),
    tooltip="Anlegg",
).add_to(m)

# 4. ADD QD rings 
gdf_bolig = st.session_state["gdf_bolig"]
gdf_vei = st.session_state["gdf_vei"]

gdf_syk.explore(m=m, style_kwds=dict(fill=False, color='red'), name='QDsyk', control=False)
gdf_bolig.explore(m=m, style_kwds=dict(fill=False, color='orange'), name='QDbolig', control=False)
gdf_vei.explore(m=m, style_kwds=dict(fill=False, color='black'), name='QDvei', control=False)
folium.LayerControl().add_to(m)

# 5. Dynamic Feature Group (Selectable Objects)
fg = folium.FeatureGroup(name="Objekter")

for idx, row in map_gdf.iterrows():
    included = row["Inkluder"]
    folium.CircleMarker(
        [row.geometry.y, row.geometry.x],
        radius=8 if included else 6,
        color="white",
        weight=1,
        fill=True,
        fill_color="#28a745" if included else "#6c757d",
        fill_opacity=0.9 if included else 0.5,
        tooltip=str(row["beskrivelse"]),
    ).add_to(fg)

# 6. Render Map
map_output = st_folium(
    m,
    feature_group_to_add=fg,
    returned_objects=["last_object_clicked"], 
    height=600,
    width="stretch",
    key="selector_map",
)

# 7. Handle Click (Toggle Selection)
if map_output.get("last_object_clicked"):
    lat = map_output["last_object_clicked"]["lat"]
    lng = map_output["last_object_clicked"]["lng"]
    click_id = f"{lat:.6f}_{lng:.6f}"

    if click_id != st.session_state["last_processed_click"]:
        # Find clicked object
        tol = 1e-4
        hit = map_gdf[
            (abs(map_gdf.geometry.y - lat) < tol) & 
            (abs(map_gdf.geometry.x - lng) < tol)
        ]

        if not hit.empty:
            idx = hit.index[0]
            # Toggle Boolean
            current_val = df_current.loc[idx, "Inkluder"]
            df_current.loc[idx, "Inkluder"] = not current_val
            
            # Mark processed and Rerun
            st.session_state["last_processed_click"] = click_id
            st.rerun()

# --- TABLE SECTION ---

st.subheader("Tabell")
st.info("Velg objekter som skal inkluderes i QRA. Objektenes beskrivelse kan redigeres")
display_df = df_current.sort_values(
    ["Inkluder", "avstand_meter"], ascending=[False, True]
)

# Define columns to show
cols = ["Inkluder", "Status", "beskrivelse", "kategori", "avstand_meter", "trykk_kPa"]
cols = [c for c in cols if c in display_df.columns]

edited = st.data_editor(
    display_df[cols],
    column_config={
        "Inkluder": st.column_config.CheckboxColumn("Inkluder", width=40),
        "beskrivelse": st.column_config.TextColumn("Beskrivelse"),
        "Status": st.column_config.TextColumn("Status", disabled=True, width=75),
        "kategori": st.column_config.TextColumn("Kategori", disabled=True),
        "avstand_meter": st.column_config.NumberColumn("Avstand (m)", format="%.1f", disabled=True, width=40),
        "trykk_kPa": st.column_config.NumberColumn("Trykk (kPa)", format="%.2f", disabled=True, width=40),
    },
    hide_index=True,
    height=600,
    key="table_editor"
)

# 6. SYNC TABLE -> MAP (Fixed Logic)
# We check if *either* Inkluder or Beskrivelse has changed.
editable_cols = ["Inkluder", "beskrivelse"]

# Align the original data to the sorted edited data using the index
current_subset = df_current.loc[edited.index, editable_cols]
edited_subset = edited[editable_cols]

# If there is a discrepancy (user edited text or checkbox)
if not current_subset.equals(edited_subset):
    # Update the Master DataFrame in Session State
    # Note: .update() matches on index, so the sorting of 'edited' doesn't break data alignment
    df_current.update(edited_subset)
    
    # Also update the Map DataFrame so tooltips/colors update correctly
    if "processed_map_gdf" in st.session_state:
        st.session_state["processed_map_gdf"].update(edited_subset)
    
    # Rerun to refresh the map and save state
    st.rerun()


# ------------------------------------------------------------
# 9. SAVE SELECTION
# ------------------------------------------------------------
st.divider()
num_selected = int(df_current["Inkluder"].sum())
st.info(f"**Valgt:** {num_selected} av {len(df_current)} objekter")

with st.popover("Bekreft utvalg", type="primary", width="stretch"):
    final = df_current[df_current["Inkluder"]].copy()
    
    # Ensure Status column is preserved in the final output
    if "Status" in df_current.columns:
        final["Status"] = df_current.loc[final.index, "Status"]
        
    st.session_state["qra_selected_gdf"] = final

    if st.button("Gå til side for QRA parametere", width="stretch", type="secondary"):
        st.switch_page("pages/4_QRA_Parametere.py")