# -*- coding: utf-8 -*-
"""
Created on Tue Jan 20 13:32:09 2026

@author: KRHE
"""

import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
from pyproj import Transformer
from streamlit_folium import st_folium
from get_matrikkel_data import get_matrikkel_data

# --- IMPORT DICTIONARY ---
try:
    from bygningskoder import MATRIKKEL_BYGNINGSTYPE
except ImportError:
    st.error("Kunne ikke finne 'bygningskoder.py'. Sjekk filnavn og plassering.")
    MATRIKKEL_BYGNINGSTYPE = {} # Fallback to prevent crash


# --- 1. INITIALIZATION OF SESSION STATE ---
keys_to_init = [
    "exp_buildings_gdf", "gdf_anlegg", 
    "gdf_syk", "gdf_bolig", "gdf_vei", 
    "GISanalysis_complete", 
    "last_calc_inputs"
]

for key in keys_to_init:
    if key not in st.session_state:
        if key == "GISanalysis_complete":
            st.session_state[key] = False
        else:
            st.session_state[key] = None

# --- 2. HELPER FUNCTIONS ---
def epsg32633_to_latlon(x, y):
    transformer = Transformer.from_crs("EPSG:32633", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(x, y)
    return lat, lon

def QD_func(NEI):
    QD_syk = max(round(44.4 * NEI ** (1/3)), 800)
    QD_bolig = max(round(22.2 * NEI ** (1/3)), 400)
    QD_vei = max(round(14.8 * NEI ** (1/3)), 180)
    return QD_syk, QD_bolig, QD_vei

def classify_buildings(gdf):
    """
    Classifies buildings using the MATRIKKEL_BYGNINGSTYPE dictionary.
    Assigns colors: Purple (skjermingsverdig), Red (sårbar), etc.
    """
    # 1. Ensure the building code column is a string
    gdf["bygningstype"] = gdf["bygningstype"].astype(str)

    # 2. Convert the dictionary to a DataFrame for efficient merging
    # Expected Dict structure: "111": ("Enebolig", "bolig")
    ref_df = pd.DataFrame.from_dict(
        MATRIKKEL_BYGNINGSTYPE, 
        orient='index', 
        columns=['Beskrivelse', 'Kategori']
    )

    # 3. Merge the lookup data into the results
    gdf = gdf.merge(
        ref_df,
        left_on="bygningstype",
        right_index=True,
        how="left"
    )

    # 4. Define Logic to assign Category (with fallback)
    def assign_category(row):
        # If found in dictionary, use that
        if pd.notna(row["Kategori"]):
            return row["Kategori"]
        
        # Fallback if code is new/unknown: Guess type based on first digit
        code = str(row["bygningstype"])
        first_digit = code[0]
        
        if first_digit == "1": return "bolig"
        if first_digit in ["5", "6", "7", "8"]: return "sårbar"
        return "vei/industri" # Default fallback

    gdf["kategori"] = gdf.apply(assign_category, axis=1)

    # 5. Assign Colors
    color_map = {
        "sårbar": "red",
        "bolig": "orange",
        "vei/industri": "black",
        "skjermingsverdig": "purple",
        "ingen beskyttelse": "#79DAD6"
    }
    
    # Map the color, defaulting to 'black' if category is somehow unknown
    gdf["color"] = gdf["kategori"].map(color_map).fillna("black")

      
    return gdf

def create_qd_buffer(gdf, qd_value, pressure_label):
    out = gdf.copy().drop(columns=["nordUTM33", "oestUTM33"])
    out["QD"] = qd_value
    out["trykk"] = pressure_label
    out["geometry"] = out.geometry.buffer(qd_value)
    return out

def plot_matrikkel_on_map(gdf, m):
    if gdf is None or gdf.empty:
        return m
    categories = gdf["kategori"].unique()
    for cat in categories:
        subset = gdf[gdf["kategori"] == cat]
        color = subset["color"].iloc[0]
        subset = subset.drop(columns=["color", "kategori", "typekode"], errors="ignore")
        subset.explore(
            m=m,
            name=f"Bygg – {cat}",
            marker_type="circle",
            style_kwds=dict(color=color, fillColor=color, fillOpacity=1, radius=5),
        )
    return m

# --- 3. INPUT FORM ---
with st.form("my_form"):
    st.write("Input")

    nordUTM33 = st.number_input('Nord / Y', value=None, placeholder='UTM33N EPSG:32633')
    oestUTM33 = st.number_input('Øst / X', value=None, placeholder='UTM33N EPSG:32633')
    NEI = st.number_input('Totalvekt', step=1, min_value=1, max_value=100000)
   
    submitted = st.form_submit_button("Submit")
   
    if submitted:
        # Reset success flag temporarily
        st.session_state["GISanalysis_complete"] = False
        
        with st.spinner("Henter eksponerte objekter fra matrikkelen...", show_time=True):
            missing = []
            if nordUTM33 is None: missing.append("Nord / Y")
            if oestUTM33 is None: missing.append("Øst / X")
            if NEI is None: missing.append("Totalvekt (NEI)")
               
            if missing:
                st.error("Mangler følgende: " + ", ".join(missing))
                st.stop()
            
            # --- 1. SAVE THE INPUTS USED FOR THIS CALCULATION ---
            st.session_state["last_calc_inputs"] = {
                "nord": nordUTM33,
                "oest": oestUTM33,
                "nei": NEI
            }
            
            # 2. Process Data
            d = {'nordUTM33':[nordUTM33],'oestUTM33':[oestUTM33],'NEI':[NEI]}
            df = pd.DataFrame(data=d)
            gdf_anlegg = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.oestUTM33,df.nordUTM33),crs='EPSG:32633')
            
            # 3. Calculate Buffers
            QD_syk, QD_bolig, QD_vei = QD_func(NEI)
            gdf_syk   = create_qd_buffer(gdf_anlegg, QD_syk,   "2 kPa")
            gdf_bolig = create_qd_buffer(gdf_anlegg, QD_bolig, "5 kPa")
            gdf_vei   = create_qd_buffer(gdf_anlegg, QD_vei,   "9 kPa")
            
            # 4. API Call
            gdf_syk_bbox = pd.concat([gdf_syk, gdf_syk['geometry'].bounds], axis=1)
            row = gdf_syk_bbox.iloc[0]
            bbox_tuple = (row["minx"], row["miny"], row["maxx"], row["maxy"])
            
            exp_buildings_gdf = get_matrikkel_data(bbox_tuple) 
            
            # --- HANDLE NO RESULTS ---            
            if exp_buildings_gdf.empty:
                st.warning('Ingen bygninger eksponert :sunglasses:')
                # Build Map
                
                
                m = gdf_anlegg.explore(
                    marker_type=folium.Marker(icon=folium.Icon(color='blue', icon='bomb', prefix='fa')),
                    name='anlegg',
                    control=False
                )
                
                gdf_syk.explore(m=m, style_kwds=dict(fill=False, color='red'), name='QDsyk', control=False)
                gdf_bolig.explore(m=m, style_kwds=dict(fill=False, color='orange'), name='QDbolig', control=False)
                gdf_vei.explore(m=m, style_kwds=dict(fill=False, color='black'), name='QDvei', control=False)
                folium.LayerControl().add_to(m)
                st_folium(m, width="stretch", zoom=13, key="map_noobjects", returned_objects=[])
                st.stop()
                
            # --- APPLY CLASSIFICATION ---
            
            exp_buildings_gdf = exp_buildings_gdf[["bygningstype", "geometry"]]
            exp_buildings_gdf = classify_buildings(exp_buildings_gdf) # This adds 'kategori' and 'color' based on bygningskoder.py
            
            # 5. STORE PROCESSED DATA
            st.session_state["gdf_anlegg"] = gdf_anlegg
            st.session_state["gdf_syk"] = gdf_syk
            st.session_state["gdf_bolig"] = gdf_bolig
            st.session_state["gdf_vei"] = gdf_vei
            st.session_state["exp_buildings_gdf"] = exp_buildings_gdf
            
            # 6. Flag Analysis as Complete
            st.session_state["gdf_calculated"] = None
            st.session_state["GISanalysis_complete"] = True

# --- 4. RENDER OUTPUT ---
if st.session_state["GISanalysis_complete"]:
    
    st.divider()
    st.subheader("Resultat")
    
    # --- DISPLAY SAVED VALUES ---
    inputs = st.session_state["last_calc_inputs"]
    if inputs:
        st.info(f"**Valgte verdier:** Nord: {inputs['nord']}, Øst: {inputs['oest']}, Totalvekt: {inputs['nei']} kg")
        
    with st.spinner("Tegner kart...", show_time=True):
        # --- RE-GENERATE MAP FROM SAVED DATA ---
        gdf_anlegg = st.session_state["gdf_anlegg"]
        gdf_syk = st.session_state["gdf_syk"]
        gdf_bolig = st.session_state["gdf_bolig"]
        gdf_vei = st.session_state["gdf_vei"]
        exp_buildings = st.session_state["exp_buildings_gdf"]
    
        # Build Map
        m = gdf_anlegg.explore(
            marker_type=folium.Marker(icon=folium.Icon(color='blue', icon='bomb', prefix='fa')),
            name='anlegg',
            control=False
        )
        
        gdf_syk.explore(m=m, style_kwds=dict(fill=False, color='red'), name='QDsyk', control=False)
        gdf_bolig.explore(m=m, style_kwds=dict(fill=False, color='orange'), name='QDbolig', control=False)
        gdf_vei.explore(m=m, style_kwds=dict(fill=False, color='black'), name='QDvei', control=False)
        
        m = plot_matrikkel_on_map(exp_buildings, m)
        folium.LayerControl().add_to(m)
    
        # Render Map
        st_folium(
            m, 
            width="stretch", 
            zoom=13, 
            key="map_1",
            returned_objects=[]
        )
        
        st.page_link(
            "pages/2_QD_analyse.py", 
            label="Analyser lokasjon", 
            icon=":material/calculate:", 
            width="stretch"
        )
