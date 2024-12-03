import dash
from dash import html, dcc, callback, Input, Output, exceptions
import dash_design_kit as ddk
import plotly.express as px
import plotly.graph_objects as go
import os
import json
import redis
import pandas as pd
import db
import sdig.util.zc as zc
import constants

dash.register_page(__name__, path='/', )

def layout():

    df = db.get_locations()

    zoom, center = zc.zoom_center(df['longitude'], df['latitude'])

    df = df.sort_values('mission_id')

    overview_map = px.scatter_map(
        df, 
        lat='latitude', 
        lon='longitude', 
        color='title', 
        hover_data=['title', 'time'], 
        custom_data=['mission_id'],
        color_discrete_sequence=px.colors.qualitative.Dark24
    )
    overview_map.update_traces(hovertemplate='<b>%{customdata[1]}</b><br><br>Latitude: %{lat}<br>Longitude: %{lon}<br>Time: %{customdata[2]}<extra></extra>')

    overview_map.update_layout(
        legend_title='Mission',
        legend_orientation="v",
        legend_x=1.,
        height=1250,
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        map_style="white-bg",
        map_layers=[
            {
                "below": 'traces',
                "sourcetype": "raster",
                "sourceattribution": "General Bathymetric Chart of the Oceans (GEBCO); NOAA National Centers for Environmental Information (NCEI)",
                "source": [
                    'https://tiles.arcgis.com/tiles/C8EMgrsFcRFL6LrL/arcgis/rest/services/GEBCO_basemap_NCEI/MapServer/tile/{z}/{y}/{x}'
                ]
            }
        ],
        map_zoom=zoom,
        map_center=center,
    )

    layout = ddk.Block(width=1., children=[
        ddk.Graph(id='overview-map', figure=overview_map)
    ])
    return layout