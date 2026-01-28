# -*- coding: utf-8 -*-
"""
Created on Tue Aug 12 10:40:10 2025

@author: KRHE
"""
import numpy as np

def incident_pressure(D,NEI):
    """
    Incident overpressure (kPa) from simplified Kingery–Bulmash (Swisdak, 1994).
    Args:
      D   : distance (m)
      NEI : net explosive content (kg TNT eq)
    Returns:
      pressure in kPa (float). np.nan if inputs invalid.
    """
    if NEI is None or NEI <= 0 or D is None or D <= 0:
        return np.nan

    Z = D/NEI**(1/3) #scaled distance

    if Z <= 2.9:
        Az = 7.2106
        Bz = -2.1069
        Cz = -0.3229
        Dz = 0.1117
        Ez = 0.0685
    elif Z <= 23.8:
        Az = 7.5938
        Bz = -3.0523
        Cz = 0.40977
        Dz = 0.0261
        Ez = -0.01267
    elif Z > 23.8:
        Az = 6.0536
        Bz = -1.4066
        Cz = 0
        Dz = 0
        Ez = 0
    return (np.exp(Az+Bz*np.log(Z) + Cz * (np.log(Z))**2+ Dz * (np.log(Z))**3+ Ez * (np.log(Z))**4))