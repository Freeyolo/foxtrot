# -*- coding: utf-8 -*-
"""
Created on Tue Aug 12 09:59:03 2025

@author: KRHE
"""
import requests
import geopandas as gpd
from io import BytesIO

def get_matrikkel_data(bbox_tuple):
    """Denne funksjonen bruker Kartverkets API til å finne alle bygninger innenfor en bounding box."""
    wfs_url = "https://wfs.geonorge.no/skwms1/wfs.matrikkelen-bygningspunkt?"

    minx, miny, maxx, maxy = bbox_tuple
    bbox_str = f'{minx},{miny},{maxx},{maxy},EPSG:32633'

    params = {
        'service': 'WFS',
        'version': '2.0.0',
        'request': 'GetFeature',
        'typename': 'app:Bygning',
        'srsname': 'EPSG:32633',
        'outputformat': 'application/gml+xml; version=3.2',
        'bbox': bbox_str,
    }

    try:
        response = requests.get(wfs_url, params=params)
        response.raise_for_status()
    except requests.exceptions.HTTPError as errh:
        print("HTTP Error:", errh)
        return gpd.GeoDataFrame()
    except requests.exceptions.ConnectionError as errc:
        print("Error Connecting:", errc)
        return gpd.GeoDataFrame()
    except requests.exceptions.Timeout as errt:
        print("Timeout Error:", errt)
        return gpd.GeoDataFrame()
    except requests.exceptions.RequestException as err:
        print("Error:", err)
        return gpd.GeoDataFrame()

    try:
        matrikkel_data = gpd.read_file(BytesIO(response.content))
        return matrikkel_data
    except ValueError as ve:
        print(f"ValueError: {ve}")
        return gpd.GeoDataFrame()
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return gpd.GeoDataFrame()
