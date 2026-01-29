import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
from streamlit_folium import st_folium
from pyproj import Transformer
from blast_model import incident_pressure

# --- 1. SETUP & STATE CHECK ---
st.set_page_config(page_title="Seleksjon for QRA", page_icon=":material/checklist:", layout="wide")

if "GISanalysis_complete" not in st.session_state or not st.session_state["GISanalysis_complete"]:
    st.warning("Ingen data funnet. Vennligst kjør analysen på hovedsiden først.")
    st.page_link("streamlit_app.py", label="Gå til hovedside", icon=":material/home:") 
    st.stop()

# --- 2. STALE DATA CHECK ---
current_inputs = st.session_state.get("last_calc_inputs", {})
saved_inputs_for_qra = st.session_state.get("qra_inputs_snapshot", {})

if current_inputs != saved_inputs_for_qra:
    if "qra_editor_data" in st.session_state:
        del st.session_state["qra_editor_data"]
    if "map_center" in st.session_state:
        del st.session_state["map_center"]
    st.session_state["qra_inputs_snapshot"] = current_inputs

# --- 3. RETRIEVE DATA ---
gdf_anlegg = st.session_state["gdf_anlegg"]
inputs = current_inputs
NEI = inputs["nei"]
df_work = st.session_state["exp_buildings_gdf"].copy()

# --- 4. HELPER FUNCTIONS ---
def QD_func(NEI):
    QD_syk = max(round(44.4 * NEI ** (1/3)), 800)
    QD_bolig = max(round(22.2 * NEI ** (1/3)), 400)
    QD_vei = max(round(14.8 * NEI ** (1/3)), 180)
    return QD_syk, QD_bolig, QD_vei

QD_syk, QD_bolig, QD_vei = QD_func(NEI)
anlegg_point = gdf_anlegg.geometry.iloc[0] 

# Recalculate physics
df_work["avstand_meter"] = df_work.geometry.distance(anlegg_point)
df_work["trykk_kPa"] = df_work["avstand_meter"].apply(lambda d: incident_pressure(d, NEI))

# --- 5. LOGIC & DEFAULTS ---
def analyze_row(row):
    cat = row["kategori"]
    dist = row["avstand_meter"]
    if cat == "ingen beskyttelse": return "Ingen beskyttelse", False
    if cat == "skjermingsverdig":
        return ("⚠️ Skjermingsverdig", True) if dist < QD_syk else ("✅ Trygg", False)
    
    limit = QD_syk if cat == "sårbar" else (QD_bolig if cat == "bolig" else QD_vei)
    if dist < limit: return "⚠️ Innenfor QD", True
    return "✅ Trygg", False

status_results = df_work.apply(analyze_row, axis=1)
df_work["Status"] = [x[0] for x in status_results]
calculated_defaults = [x[1] for x in status_results]

# --- 6. INITIALIZE EDITOR STATE ---
if "qra_editor_data" not in st.session_state:
    df_work["Inkluder"] = calculated_defaults
    st.session_state["qra_editor_data"] = df_work
else:
    saved_df = st.session_state["qra_editor_data"]
    df_work["Inkluder"] = calculated_defaults
    common_indices = df_work.index.intersection(saved_df.index)
    df_work.loc[common_indices, "Inkluder"] = saved_df.loc[common_indices, "Inkluder"]

df_current = st.session_state["qra_editor_data"]

if not isinstance(df_current, gpd.GeoDataFrame):
    df_current = gpd.GeoDataFrame(df_current, geometry=df_work.geometry, crs=df_work.crs)

# --- 7. MAP STATE INITIALIZATION ---
transformer = Transformer.from_crs("EPSG:32633", "EPSG:4326", always_xy=True)
anlegg_lon, anlegg_lat = transformer.transform(anlegg_point.x, anlegg_point.y)

if "map_center" not in st.session_state:
    st.session_state["map_center"] = [anlegg_lat, anlegg_lon]

# Ensure dicts are converted to lists (Fix for TypeError)
if isinstance(st.session_state["map_center"], dict):
    c = st.session_state["map_center"]
    st.session_state["map_center"] = [c['lat'], c['lng']]

if "map_zoom" not in st.session_state:
    st.session_state["map_zoom"] = 14

if "last_processed_click" not in st.session_state:
    st.session_state["last_processed_click"] = None

# --- 8. LAYOUT & INTERACTION ---
st.title("Seleksjon av objekter til QRA")
st.write("Klikk på markører i kartet for å endre status.")

col_map, col_table = st.columns([1, 1])

with col_map:
    st.subheader("Kart")
    
    map_gdf = df_current.to_crs(epsg=4326)
    
    m = folium.Map(
        location=st.session_state["map_center"], 
        zoom_start=st.session_state["map_zoom"],
        tiles="OpenStreetMap"
    )
    
    folium.Marker(
        [anlegg_lat, anlegg_lon],
        icon=folium.Icon(color='blue', icon='bomb', prefix='fa'),
        tooltip="Anlegg"
    ).add_to(m)

    fg = folium.FeatureGroup(name="Objekter")
    
    for idx, row in map_gdf.iterrows():
        is_included = row["Inkluder"]
        color = "#28a745" if is_included else "#6c757d"
        fill_opacity = 0.9 if is_included else 0.5
        radius = 8 if is_included else 6
        
        folium.CircleMarker(
            location=[row.geometry.y, row.geometry.x],
            radius=radius,
            color="white",
            weight=1,
            fill=True,
            fill_color=color,
            fill_opacity=fill_opacity,
            tooltip=f"{row['Beskrivelse']}",
        ).add_to(fg)

    # RENDER MAP
    # We include 'center' and 'zoom' so we know where the user is looking
    map_output = st_folium(
        m,
        center=st.session_state["map_center"],
        zoom=st.session_state["map_zoom"],
        feature_group_to_add=fg,       
        key="selector_map",
        height=600,
        width=700,
        returned_objects=["last_object_clicked", "center", "zoom"] 
    )

    # --- HANDLING INTERACTIONS ---
    
    # 1. Update View State (Crucial for stability)
    # If the user panned or zoomed, save that new position immediately.
    # We use the 'center' returned by st_folium (the current view), NOT the click location.
    if map_output["center"]:
        c = map_output["center"]
        st.session_state["map_center"] = [c["lat"], c["lng"]]
        st.session_state["map_zoom"] = map_output["zoom"]

    # 2. Process Click
    if map_output["last_object_clicked"]:
        
        clicked_lat = map_output["last_object_clicked"]["lat"]
        clicked_lng = map_output["last_object_clicked"]["lng"]
        current_click_id = f"{clicked_lat}_{clicked_lng}"
        
        # Prevent infinite loop by checking ID
        if current_click_id != st.session_state["last_processed_click"]:
            
            # Find the building
            match = map_gdf[
                (map_gdf.geometry.y.between(clicked_lat - 0.00001, clicked_lat + 0.00001)) &
                (map_gdf.geometry.x.between(clicked_lng - 0.00001, clicked_lng + 0.00001))
            ]
            
            if not match.empty:
                target_idx = match.index[0]
                # Toggle
                current_val = st.session_state["qra_editor_data"].loc[target_idx, "Inkluder"]
                st.session_state["qra_editor_data"].loc[target_idx, "Inkluder"] = not current_val
                
                # Mark as processed
                st.session_state["last_processed_click"] = current_click_id
                
                # Rerun to update color. 
                # Because we updated st.session_state["map_center"] in step 1 above using the 
                # current map view, the map will reload EXACTLY where it is now.
                st.rerun()

with col_table:
    st.subheader("Tabell")
    
    display_df = st.session_state["qra_editor_data"].sort_values(
        by=["Inkluder", "avstand_meter"], ascending=[False, True]
    )
    
    cols_to_show = ["Inkluder", "Status", "Beskrivelse", "kategori", "avstand_meter", "trykk_kPa", "bygningstype"]
    cols_to_show = [c for c in cols_to_show if c in display_df.columns]

    edited_df = st.data_editor(
        display_df[cols_to_show],
        column_config={
            "Inkluder": st.column_config.CheckboxColumn("Inkluder?", default=False),
            "avstand_meter": st.column_config.NumberColumn("Avstand", format="%.1f m"),
            "trykk_kPa": st.column_config.NumberColumn("Trykk", format="%.2f kPa"),
            "Status": st.column_config.TextColumn("Status", width="medium"),
            "Beskrivelse": st.column_config.TextColumn("Beskrivelse", width="large"),
        },
        hide_index=True,
        use_container_width=True,
        height=600,
        key="qra_editor_key" 
    )
    
    st.session_state["qra_editor_data"].update(edited_df["Inkluder"])

# --- 9. SAVE SELECTION BUTTON ---
st.divider()
col_info, col_btn = st.columns([3, 1])

with col_info:
    num_selected = st.session_state["qra_editor_data"]["Inkluder"].sum()
    st.info(f"**Valgt:** {num_selected} av {len(st.session_state['qra_editor_data'])} objekter.")

with col_btn:
    if st.button("Bekreft utvalg og gå videre", type="primary", use_container_width=True):
        final_df = st.session_state["qra_editor_data"]
        selected_indices = final_df[final_df["Inkluder"]].index
        
        original_gdf = st.session_state["exp_buildings_gdf"]
        final_qra_gdf = original_gdf.loc[selected_indices].copy()
        
        final_qra_gdf["avstand_meter"] = final_df.loc[selected_indices, "avstand_meter"]
        final_qra_gdf["trykk_kPa"] = final_df.loc[selected_indices, "trykk_kPa"]
        final_qra_gdf["Status"] = final_df.loc[selected_indices, "Status"]
        
        st.session_state["qra_selected_gdf"] = final_qra_gdf
        st.success("Utvalg lagret!")