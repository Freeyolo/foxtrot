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

# --- 1. SAFE INITIALIZATION ---
if "input_coordinates" not in st.session_state:
    st.session_state["input_coordinates"] = {}
if "latlon_coordinates" not in st.session_state:
    st.session_state["latlon_coordinates"] = {}
if "exp_buildings_gdf" not in st.session_state:
    st.session_state["exp_buildings_gdf"] = {}
if "folium_map" not in st.session_state:
    st.session_state["folium_map"] = None
if "GISanalysis_complete" not in st.session_state:
    st.session_state["GISanalysis_complete"] = False

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
    gdf["bygningstype"] = gdf["bygningstype"].astype(str)
    gdf["typekode"] = gdf["bygningstype"].str[0]
    gdf["kategori"] = gdf["typekode"].map({
        "1": "bolig", "5": "sårbar", "6": "sårbar", 
        "7": "sårbar", "8": "sårbar", "2": "industri", 
        "3": "industri", "4": "industri", "9": "industri"
    }).fillna("industri")
    gdf["color"] = gdf["kategori"].map({
        "bolig": "orange", "industri": "black", "sårbar": "red"
    })
    return gdf

def create_qd_buffer(gdf, qd_value, pressure_label):
    out = gdf.copy().drop(columns=["nordUTM33", "oestUTM33"])
    out["QD"] = qd_value
    out["trykk"] = pressure_label
    out["geometry"] = out.geometry.buffer(qd_value)
    return out

def plot_matrikkel_on_map(gdf, m):
    categories = gdf["kategori"].unique()
    for cat in categories:
        subset = gdf[gdf["kategori"] == cat]
        color = subset["color"].iloc[0]
        subset = subset.drop(columns=["color", "kategori", "typekode"], errors="ignore")
        subset.explore(
            m=m,
            name=f"Bygg – {cat}",
            marker_type="circle",
            style_kwds=dict(color=color, fillColor=color, fillOpacity=1),
        )
    return m

# --- 3. INPUT FORM ---
with st.form("my_form"):
    st.write("Input")
    nordUTM33 = st.number_input('Nord / Y', value=None, step=1, placeholder='EPSG:32633 - WGS 84 / UTM zone 33N')
    oestUTM33 = st.number_input('Øst / X', value=None, step=1, placeholder='EPSG:32633 - WGS 84 / UTM zone 33N')
    NEI = st.number_input('Totalvekt', value=None, step=1, min_value=1, max_value=100000, placeholder='Netto eksplosivinnhold (NEI) i kg')
   
    submitted = st.form_submit_button("Submit")
   
    if submitted:
        # Reset analysis state immediately on new submit
        st.session_state["GISanalysis_complete"] = False
        st.session_state["folium_map"] = None
        
        with st.spinner("Henter eksponerte bygninger fra Matrikkelen…", show_time=True):
            # Validation
            missing = []
            if nordUTM33 is None: missing.append("Nord / Y")
            if oestUTM33 is None: missing.append("Øst / X")
            if NEI is None: missing.append("Totalvekt (NEI)")
               
            if missing:
                st.error("Mangler følgende: " + ", ".join(missing))
                st.stop()

            # Save inputs
            st.session_state["input_coordinates"] = {"oestUTM33": oestUTM33, "nordUTM33": nordUTM33, "NEI": NEI} 
            lat, lon = epsg32633_to_latlon(oestUTM33, nordUTM33)
            st.session_state["latlon_coordinates"] = {"lat": lat, "lon": lon}
            
            # Create Geometry
            d = {'nordUTM33':[nordUTM33],'oestUTM33':[oestUTM33],'NEI':[NEI]}
            df = pd.DataFrame(data=d)
            gdf_anlegg = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.oestUTM33,df.nordUTM33),crs='EPSG:32633')
            
            # Calculate Buffers
            QD_syk, QD_bolig, QD_vei = QD_func(NEI)
            gdf_syk   = create_qd_buffer(gdf_anlegg, QD_syk,   "2 kPa")
            gdf_bolig = create_qd_buffer(gdf_anlegg, QD_bolig, "5 kPa")
            gdf_vei   = create_qd_buffer(gdf_anlegg, QD_vei,   "9 kPa")
            
            # Init Map
            m = gdf_anlegg.explore(
                marker_type=folium.Marker(icon=folium.Icon(color='blue', icon='bomb', prefix='fa')),
                name='anlegg',
                control=False
            )
            
            # API Call Logic
            gdf_syk_bbox = pd.concat([gdf_syk, gdf_syk['geometry'].bounds], axis=1)
            row = gdf_syk_bbox.iloc[0]
            bbox_tuple = (row["minx"], row["miny"], row["maxx"], row["maxy"])
                        
            exp_buildings_gdf = get_matrikkel_data(bbox_tuple) 
            
            if exp_buildings_gdf.empty:
                st.warning('Ingen bygninger eksponert :sunglasses:')
                st.stop()
                
            exp_buildings_gdf = exp_buildings_gdf[["bygningstype", "geometry"]]
      
            # Add layers
            gdf_syk.explore(m=m, style_kwds=dict(fill=False, color='red'), name='QDsyk', control=False)
            gdf_bolig.explore(m=m, style_kwds=dict(fill=False, color='orange'), name='QDbolig', control=False)
            gdf_vei.explore(m=m, style_kwds=dict(fill=False, color='black'), name='QDvei', control=False)
            
            # Classify and plot
            exp_buildings_gdf = classify_buildings(exp_buildings_gdf)
            st.session_state["exp_buildings_gdf"] = exp_buildings_gdf
            m = plot_matrikkel_on_map(st.session_state["exp_buildings_gdf"], m)
            folium.LayerControl().add_to(m)
            
            # --- SAVE SUCCESS STATE ---
            st.session_state['folium_map'] = m
            st.session_state['GISanalysis_complete'] = True

# --- 4. RENDER OUTPUT ---
# This block runs on every script cycle, ensuring the map stays visible
if st.session_state.get("GISanalysis_complete"):
    st.divider()
    st.subheader("Resultat")
    
    if st.session_state['folium_map'] is not None:
        # returned_objects=[] prevents the map from triggering a re-run when loaded
        # This stops the flicker loop.
        st_folium(
            st.session_state['folium_map'], 
            use_container_width=True, 
            zoom=13, 
            key="map_1",
            returned_objects=[] 
        )
    
    # We check the analysis flag for the link, NOT the form submit button
    st.page_link(
        "pages/2_QD_analysis.py", 
        label="Analyser lokasjon", 
        icon=":material/calculate:", 
        use_container_width=True
    )