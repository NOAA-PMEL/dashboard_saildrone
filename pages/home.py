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
config = json.loads(constants.redis_instance.hget("saildrone", "config"))

def layout():

    df = db.get_locations()

    zoom, center = zc.zoom_center(df['longitude'], df['latitude'])

    df = df.sort_values('mission_id')

    overview_map = px.scatter_mapbox(
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
        legend_x=.21,
        height=1250,
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        mapbox_style="white-bg",
        mapbox_layers=[
            {
                "below": 'traces',
                "sourcetype": "raster",
                "sourceattribution": "Powered by Esri",
                "source": [
                    "https://ibasemaps-api.arcgis.com/arcgis/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}?token=" + constants.ESRI_API_KEY
                ]
            }
        ],
        mapbox_zoom=zoom,
        mapbox_center=center,
    )

    layout = ddk.Block(children=[
        ddk.Graph(id='overview-map', figure=overview_map)
    ])
    return layout