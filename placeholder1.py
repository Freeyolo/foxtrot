# -*- coding: utf-8 -*-
"""
Created on Tue Jan 27 12:06:46 2026

@author: KRHE
"""

import streamlit as st
from streamlit_folium import st_folium
import folium
from pyproj import Transformer

st.set_page_config(page_title="Folium Click Map", layout="wide")

st.title("Interactive Folium Map")
st.write("Click anywhere on the map to drop a marker at the clicked location.")


def latlon_to_epsg32633(lat, lon):
    """
    Convert latitude/longitude (EPSG:4326) to UTM Zone 33N (EPSG:32633).

    Parameters:
        lat (float): Latitude in decimal degrees
        lon (float): Longitude in decimal degrees

    Returns:
        (x, y): Coordinates in meters in EPSG:32633
    """
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:32633", always_xy=True)
    x, y = transformer.transform(lon, lat)
    return round(x,2), round(y,2)


def epsg32633_to_latlon(x, y):
    """
    Convert UTM Zone 33N (EPSG:32633) coordinates to latitude/longitude (EPSG:4326).

    Parameters:
        x (float): Easting in meters
        y (float): Northing in meters

    Returns:
        (lat, lon): Latitude and longitude in decimal degrees
    """
    transformer = Transformer.from_crs("EPSG:32633", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(x, y)
    return lat, lon

# Initial map center
if not st.session_state["input_coordinates"]:
    start_coords = [59.2638, 10.4044]  # Example: Tønsberg area
    start_coordsUTM33N = latlon_to_epsg32633(start_coords[0], start_coords[1])
else: 
    start_coordsUTM33N = [st.session_state["input_coordinates"]["oestUTM33"], st.session_state["input_coordinates"]["nordUTM33"]]
    start_coords = epsg32633_to_latlon(st.session_state["input_coordinates"]["oestUTM33"], st.session_state["input_coordinates"]["nordUTM33"])
        
m = folium.Map(location=start_coords, zoom_start=12)

# Add a marker
folium.Marker(
    location=start_coords,
    icon=folium.Icon(color='blue', icon='bomb', prefix='fa'),
    popup=f'{start_coordsUTM33N}',
    tooltip="eksplosivanlegg"
).add_to(m)


# Add click popup functionality
m.add_child(folium.LatLngPopup())

# Display folium map and capture interactions
returned = st_folium(m, width=700, height=500)

# Check if a click event is captured
if returned and "last_clicked" in returned and returned["last_clicked"] is not None:
    lat = returned["last_clicked"]['lat']
    lon = returned["last_clicked"]['lng']

    latutm, lonutm =  latlon_to_epsg32633(lat, lon)
    
    st.success(f"Clicked location: {lonutm:.2f}, {latutm:.2f}")

    # Show a map with a marker at the clicked position
else:
    st.info("Click on the map to see coordinates and drop a marker.")
