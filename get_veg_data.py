# -*- coding: utf-8 -*-
"""
Created on Tue Aug 12 09:52:32 2025

@author: KRHE
"""

import requests
import pandas as pd
import geopandas as gpd
from shapely import wkt

def get_veg_data(row):
    """Denne funksjonen bruker SVV NVDB API til å finne alle veier, ÅDT og hastighet innenfor en bounding box
    https://nvdb-docs.atlas.vegvesen.no/"""
    nvdburl = 'https://nvdbapiles.atlas.vegvesen.no/vegobjekter/540'  # 540 er ÅDT
    fartsurl = 'https://nvdbapiles.atlas.vegvesen.no/vegobjekter/105'  # 105 = Fartsgrense

    minx, miny, maxx, maxy = row['minx'], row['miny'], row['maxx'], row['maxy']

    headers = {
        'accept': 'application/json',
        'X-Client': 'Utdrag ÅDT',
        'X-Client-Session': '402b9aee-16f9-e38d-2ce7-cd6bc20eb3e3'
    }
    params = {
        'srid': '5973',
        'inkluder': 'alle',
        'segmentering': 'true',
        'kartutsnitt': f'{minx},{miny},{maxx},{maxy}',
    }

    try:
        response = requests.get(nvdburl, params=params, headers=headers)
        response.raise_for_status()
        jsonResponse = response.json()
        if 'objekter' not in jsonResponse:
            return gpd.GeoDataFrame()
    except (requests.exceptions.RequestException, ValueError) as err:
        print("Error:", err)
        return gpd.GeoDataFrame()

    vegdata_list = []
    for vegobjekt in jsonResponse['objekter']:
        vegdata_dict = {'Vegobj_id': vegobjekt['id']}
        if 'geometri' in vegobjekt and 'wkt' in vegobjekt['geometri']:
            vegdata_dict['geometry'] = vegobjekt['geometri']['wkt']
        for egenskap in vegobjekt['egenskaper']:
            if egenskap['id'] == 4621:
                vegdata_dict['ÅDT_år'] = egenskap['verdi']
            if egenskap['id'] == 4623:
                vegdata_dict['ÅDT_total'] = egenskap['verdi']
            if egenskap['id'] == 4625:
                vegdata_dict['ÅDT_grunnlag'] = egenskap['verdi']
        vegdata_list.append(vegdata_dict)

    vegdata = pd.DataFrame(vegdata_list)
    if vegdata.empty:
        return gpd.GeoDataFrame()

    if 'geometry' in vegdata:
        vegdata['geometry'] = vegdata['geometry'].apply(wkt.loads)
    geo_veg_data = gpd.GeoDataFrame(vegdata, geometry='geometry', crs="EPSG:5973")

    try:
        fart_response = requests.get(fartsurl, params=params, headers=headers)
        fart_response.raise_for_status()
        fart_json = fart_response.json()
        if 'objekter' not in fart_json:
            geo_veg_data['Fartsgrense'] = None
            return geo_veg_data
    except Exception as err:
        print("Error fetching speed limits:", err)
        geo_veg_data['Fartsgrense'] = None
        return geo_veg_data

    fart_list = []
    for obj in fart_json['objekter']:
        fart_dict = {}
        if 'geometri' in obj and 'wkt' in obj['geometri']:
            fart_dict['geometry'] = obj['geometri']['wkt']
        for egenskap in obj['egenskaper']:
            if egenskap['id'] == 2021:
                fart_dict['Fartsgrense'] = egenskap['verdi']
        if 'geometry' in fart_dict and 'Fartsgrense' in fart_dict:
            fart_list.append(fart_dict)

    fart_df = pd.DataFrame(fart_list)
    if fart_df.empty:
        geo_veg_data['Fartsgrense'] = None
        return geo_veg_data

    fart_df['geometry'] = fart_df['geometry'].apply(wkt.loads)
    geo_fart = gpd.GeoDataFrame(fart_df, geometry='geometry', crs="EPSG:5973")

    geo_veg_data = gpd.overlay(
        geo_veg_data,
        geo_fart[['geometry', 'Fartsgrense']],
        how='intersection'
    )
    return geo_veg_data
