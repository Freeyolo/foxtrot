import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
from streamlit_folium import st_folium
from pyproj import Transformer
# Import needed only for fallback

df_QRA = st.session_state["qra_selected_gdf"]

st.write(df_QRA["Beskrivelse"])
st.session_state