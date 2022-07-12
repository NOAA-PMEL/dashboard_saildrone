# -*- coding: utf-8 -*-
"""Saildrone Dashboard

The app reads a config file and shows  a map with the last reported location of selected drones.
Selecting a drone shows allows selections of variables for a trajectory ribbon plot and
any number of timeseris plots the selected platform.
Note: the flow is as follows:
    The map loads based on the initial callback on a method listening to Input('data-div', 'children').
    Select a drone is required, but doesn't have to be done first.
    Selecting a variable in the upper right plots the ribbon plot if one or more drones is selected.
    Selecting one of more variables in the bottom panel plots the timeseries of the selected variables.
"""
import random

import sys
import urllib

import datetime
import dateutil.parser
import dash
from dash import Dash, callback, html, dcc, dash_table, Input, Output, State, MATCH, ALL
import dash_bootstrap_components as dbc
import pandas
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
from plotly.subplots import make_subplots
import json
import matplotlib.colors as color
from erddapy import ERDDAP
import flask
import os
from itertools import cycle
from itertools import filterfalse

app = dash.Dash(__name__,
                suppress_callback_exceptions=True,
                external_stylesheets=[dbc.themes.BOOTSTRAP],
                # requests_pathname_prefix='/dashboard/saildrone/'
                )
app._favicon = 'favicon.ico'
server = app.server  # expose server variable for Procfile

application = app.server

version = 'v1.6'

with open('key.txt') as key:
    ESRI_API_KEY = key.readline()


# https://stackoverflow.com/questions/63787612/plotly-automatic-zooming-for-mapbox-maps
def zoom_center(lons: tuple = None, lats: tuple = None, lonlats: tuple = None,
                format: str = 'lonlat', projection: str = 'mercator',
                width_to_height: float = 2.0) -> (float, dict):
    """Finds optimal zoom and centering for a plotly mapbox.
    Must be passed (lons & lats) or lonlats.
    Temporary solution awaiting official implementation, see:
    https://github.com/plotly/plotly.js/issues/3434

    Parameters
    --------
    lons: tuple, optional, longitude component of each location
    lats: tuple, optional, latitude component of each location
    lonlats: tuple, optional, gps locations
    format: str, specifying the order of longitud and latitude dimensions,
        expected values: 'lonlat' or 'latlon', only used if passed lonlats
    projection: str, only accepting 'mercator' at the moment,
        raises `NotImplementedError` if other is passed
    width_to_height: float, expected ratio of final graph's with to height,
        used to select the constrained axis.

    Returns
    --------
    zoom: float, from 1 to 20 (I'm using .85 of the original value)
    center: dict, gps position with 'lon' and 'lat' keys

    >>> print(zoom_center((-109.031387, -103.385460),
    ...     (25.587101, 31.784620)))
    (5.75, {'lon': -106.208423, 'lat': 28.685861})
    """
    if lons is None and lats is None:
        if isinstance(lonlats, tuple):
            lons, lats = zip(*lonlats)
        else:
            raise ValueError(
                'Must pass lons & lats or lonlats'
            )

    maxlon, minlon = max(lons), min(lons)
    maxlat, minlat = max(lats), min(lats)
    center = {
        'lon': round((maxlon + minlon) / 2, 6),
        'lat': round((maxlat + minlat) / 2, 6)
    }

    # longitudinal range by zoom level (20 to 1)
    # in degrees, if centered at equator
    lon_zoom_range = np.array([
        0.0007, 0.0014, 0.003, 0.006, 0.012, 0.024, 0.048, 0.096,
        0.192, 0.3712, 0.768, 1.536, 3.072, 6.144, 11.8784, 23.7568,
        47.5136, 98.304, 190.0544, 360.0
    ])

    if projection == 'mercator':
        margin = 1.2
        height = (maxlat - minlat) * margin * width_to_height
        width = (maxlon - minlon) * margin
        lon_zoom = np.interp(width, lon_zoom_range, range(20, 0, -1))
        lat_zoom = np.interp(height, lon_zoom_range, range(20, 0, -1))
        zoom = round(min(lon_zoom, lat_zoom) * .85, 2)
    else:
        raise NotImplementedError(
            f'{projection} projection is not implemented'
        )

    return zoom, center


graph_config = {'displaylogo': False, 'modeBarButtonsToRemove': ['select2d', 'lasso2d'],
                'doubleClick': 'reset+autosize',
                'toImageButtonOptions': {'height': None, 'width': None, },
                }

line_rgb = 'rgba(.04,.04,.04,.05)'
plot_bg = 'rgba(1.0, 1.0, 1.0 ,1.0)'
blank_graph = go.Figure(go.Scatter(x=[0, 1], y=[0, 1], showlegend=False))
blank_graph.add_trace(go.Scatter(x=[0, 1], y=[0, 1], showlegend=False))
blank_graph.update_traces(visible=False)
blank_graph.update_layout(
    xaxis={"visible": False},
    yaxis={"visible": False},
    title='Make selections...',
    plot_bgcolor=plot_bg,
    annotations=[
        {
            "text": "Pick one or more drones<br>Pick a variable",
            "xref": "paper",
            "yref": "paper",
            "showarrow": False,
            "font": {
                "size": 14
            }
        },
    ]
)

blank_map = go.Figure(go.Scattergeo(lat=[0, 1], lon=[0, 1], showlegend=False, marker={'color': plot_bg}, ))
blank_map.add_trace(go.Scattergeo(lat=[0, 1], lon=[0, 1], showlegend=False, marker={'color': plot_bg}, ))
blank_map.update_geos(visible=False)
blank_map.update_layout(
    xaxis={"visible": False},
    yaxis={"visible": False},
    plot_bgcolor=plot_bg,
    annotations=[
        {
            "text": "Pick one or more drones<br>Pick a variable",
            "xref": "paper",
            "yref": "paper",
            "showarrow": False,
            "font": {
                "size": 14
            }
        }
    ]
)

no_data_graph = go.Figure()
no_data_graph = no_data_graph.update_layout(
    xaxis={"visible": False},
    yaxis={"visible": False},
    plot_bgcolor=plot_bg,
    annotations=[
        {
            "text": "No data found for selected platform...",
            "xref": "paper",
            "yref": "paper",
            "showarrow": False,
            "font": {
                "size": 28
            }
        }
    ]
)


def create_options(lns, remove):
    for n in remove:
        if n in lns:
            del lns[n]
    options = []
    for var in sorted(lns, key=lns.get):
        options.append({'label': lns[var], 'value': var})
    return options


height_of_row = 345
short_map_height = 450
tall_map_height = 800

invisible = {'display': 'none'}
visible = {'display': 'block'}

remove_plots = ['latitude', 'longitude', 'time', 'trajectory']
remove_trace = ['latitude', 'longitude', 'trajectory']

#  missions_file = os.getenv('MISSION_JSON')
missions_file = 'config/missions.json'
if missions_file is None:
    missions_file = os.getenv('MISSIONS_JSON')

missions_json = None
if missions_file is not None:
    with open(missions_file) as missions_config:
        missions_json = json.load(missions_config)
else:
    print('You must configure either a MISSION_JSON environment variable pointing to a config file.')
    sys.exit()

html_title = 'PMEL Data'
if 'html_title' in missions_json['config']['ui']:
    html_title = missions_json['config']['ui']['html_title']
dashboard_title = 'Data Dashboard'
if 'title' in missions_json['config']['ui']:
    dashboard_title = missions_json['config']['ui']['title']
dashboard_link = 'javascript:window.location.href=window.location.href'
if 'href' in missions_json['config']['ui']:
    dashboard_link = missions_json['config']['ui']['href']
logos = []
orgs = []
if 'logos' in missions_json['config']['ui']:
    logos = missions_json['config']['ui']['logos']
if 'orgs' in missions_json['config']['ui']:
    orgs = missions_json['config']['ui']['orgs']
cones_url = None  # this will get caught in an exception later on and everything will be fine
if 'cones_url' in missions_json['config']['ui']:
    cones_url = missions_json['config']['ui']['cones_url']
missions = []
if 'missions' in missions_json['config']:
    missions = missions_json['config']['missions']

max_columns = 3
if 'max_columns' in missions_json['config']['ui']:
    max_columns = int(missions_json['config']['ui']['max_columns'])

for mission in missions:
    drones = mission['drones']
    mission['category_orders'] = {'trajectory': sorted(drones.keys())}
    start_dates = []
    end_dates = []
    all_info_dt = []
    for d in drones:
        info_drone = drones[d]['url']
        info_id = info_drone[info_drone.rindex("/") + 1:]
        info_server = info_drone[0: info_drone.index('/erddap') + 7]
        erpy = ERDDAP(server=info_server, protocol='tabledap')
        drone_info_url = erpy.get_info_url(info_id, response='csv')
        info_for_drone = pd.read_csv(drone_info_url)
        all_info_dt.append(info_for_drone)
        drone_vars = list(
            info_for_drone.loc[(info_for_drone['Row Type'] == 'attribute') &
                               (info_for_drone['Variable Name'] != 'NC_GLOBAL')]['Variable Name'].unique())
        drones[d]['variables'] = drone_vars
        chk_start_date = info_for_drone.loc[(info_for_drone['Row Type'] == 'attribute') & (
                info_for_drone['Attribute Name'] == 'time_coverage_start') & (
                                                    info_for_drone['Variable Name'] == 'NC_GLOBAL')][
            'Value'].to_list()[0]
        chk_end_date = info_for_drone.loc[(info_for_drone['Row Type'] == 'attribute') & (
                info_for_drone['Attribute Name'] == 'time_coverage_end') & (
                                                  info_for_drone['Variable Name'] == 'NC_GLOBAL')][
            'Value'].to_list()[0]
        start_dates.append(chk_start_date)
        end_dates.append(chk_end_date)

    sorted_start = sorted(start_dates)
    start_date = sorted_start[0]

    sorted_end = sorted(end_dates)
    end_date = sorted_end[-1]

    start_date_datetime = dateutil.parser.isoparse(start_date)
    end_date_datetime = dateutil.parser.isoparse(end_date)

    start_date = start_date_datetime.date().strftime('%Y-%m-%d')
    end_date = end_date_datetime.date().strftime('%Y-%m-%d')
    mission['start_date'] = start_date
    mission['end_date'] = end_date
    info = pd.concat(all_info_dt)

    long_df_all = info.loc[(info['Row Type'] == 'attribute') & (info['Attribute Name'] == 'long_name')]
    long_df = long_df_all.drop_duplicates(subset=['Variable Name'])
    long_names = dict(zip(long_df['Variable Name'], long_df['Value'].str.capitalize()))

    unit_df = info.loc[(info['Row Type'] == 'attribute') & (info['Attribute Name'] == 'units')]
    units = dict(zip(unit_df['Variable Name'], unit_df['Value']))
    mission['long_names'] = long_names
    mission['units'] = units

# print(json.dumps(missions_json, indent=4, sort_keys=True))

# if 'latitude' in units:
#     del units['latitude']
# if 'longitude' in units:
#     del units['longitude']
# if 'time' in units:
#     del units['time']
# # Cheating, since I know what this is. Could find it in info dataframe
# if 'trajectory' in units:
#     del units['trajectory']

header_items = []

palette = cycle(px.colors.qualitative.Bold)

app.title = html_title

if len(logos) > 0:
    logo = logos[0]['logo']
    header_items.append(dbc.Col(width=3, style={'min-width': '320px'}, children=[html.Img(src=logo, style={'width': 'auto', 'height': 'auto'})]))

if len(orgs) > 0:
    org_col = dbc.Col(width=4)
    org_kids = []
    for org in orgs:
        org_row = dbc.Row(
            html.A(children=[org['org']], href=org['url'],
                   style={'text-decoration': 'none', 'font-size': '1.1rem', 'font-weight': 'bold'})
        )
        org_kids.append(org_row)
    org_col.children=org_kids
    header_items.append(org_col)

title_width = 6
if len(orgs) > 0:
    title_width = 5

header_items.append(
    dbc.Col(width=title_width, style={'display': 'flex', 'align-items': 'center'}, children=[
        html.A(
            dbc.NavbarBrand(dashboard_title, className="ml-2", style={'font-size': '1.1rem', 'font-weight': 'bold'}),
            href=dashboard_link, style={'text-decoration': 'none'}
        )
    ])
)

if len(logos) > 1:
    logo = logos[1]['logo']
    header_items.append(dbc.Col(width=3, children=[html.Img(src=logo, style={'width': 'auto', 'height': 'auto'})]))

mission_menu = []
mission_options = []
num_missions = 0
mission_id_initial_value = ''
if missions_json and 'missions' in missions_json['config']:
    all_missions = missions_json['config']['missions']
    num_missions = len(all_missions)
    if num_missions == 1:
        mission_id_initial_value = all_missions[0]['mission_id']
    for mission in all_missions:
        mission_options.append({'label': mission['ui']['title'], 'value': mission['mission_id']})

# To find a mission (if it exists) by misison_id to this:
#  mission = next((item for item in missions if item['mission_id'] == 'id_desired'), None)

date_col = ['time']
app.layout = html.Div(style={'padding-left': '15px', 'padding-right': '25px'}, children=[
    dcc.Location(id='location', refresh=False),
    dcc.Store(id='layout-complete'),
    dcc.Store(id='mission-selected'),
    dcc.Store(id='trace-config'),
    dcc.Store(id='plots-config'),
    dcc.Store(id='current-mission-id'),
    dbc.Navbar(
        [
            # Use row and col to control vertical alignment of logo / brand
            dbc.Row(style={'width': '100%'},
                    align="center",
                    # no_gutters=True,
                    children=[
                        dbc.Col(width=8, children=dbc.Row(id='header-items',
                                                          children=header_items
                                                          )),
                        dbc.Col(id='menu-col', width=4, children=[

                            dcc.Dropdown(style=dict(width='100%'),
                                         id='mission-menu-dd',
                                         options=mission_options,
                                         multi=False,
                                         clearable=True,
                                         placeholder='Pick a mission...',
                                         disabled=bool(num_missions == 1),
                                         value=mission_id_initial_value,
                                         )
                        ])
                    ]
                    ),
        ]),
    html.Div(id='page-layout', children=[
        dbc.Row([
            dbc.Col(id='location-map-column', width=12, children=[
                dbc.Card(children=[
                    dbc.CardHeader(id="map-title", children=[
                        dbc.Row(align="center", children=[
                            dbc.Col(width=4, children=[
                                html.H5(id='map-card-title', children=["Current Location of the Mission Saildrones"],
                                        className="card-title", style={"float": "left"})
                            ]),
                            dbc.Col(width=8, children=[
                                html.Div(id='drone-menu-display', style={'display': 'none'},
                                         children=[
                                             dcc.Dropdown(style=dict(width='100%'),
                                                          id='drone',
                                                          options=[],  # drones in the mission
                                                          placeholder='Select one or more drones',
                                                          multi=True,
                                                          clearable=True,
                                                          ),
                                         ])  # drones to be set (from the request)
                            ]),
                        ])
                    ]),
                    dcc.Loading(id='map-loader', children=[dcc.Graph(id='location-map', config=graph_config), ]),
                ]),
            ]),
            dbc.Col(id='date-range-column', style={'display': 'none'}, width=1, children=[
                dbc.Card(children=[
                    dbc.CardHeader(children=[
                        html.H5(children=['Date Range'],
                                className="card-title", style={"float": "left"})
                    ]),
                    dcc.DatePickerRange(id='date-range',
                                        # minimum_nights=0, allows same date to be selected, but borks the timeseries graphs
                                        )
                ]),
            ]),
            dbc.Col(id='trajectory-map-column', style={'display': 'none'}, width=5, children=[
                dbc.Card(children=[
                    dbc.CardHeader(children=[
                        dbc.Row(align="center", children=[
                            dbc.Col(width=2, children=[
                                html.H5(id='trace-title', children=['Trajectory'],
                                        className="card-title", style={"float": "left"})
                            ]),
                            dbc.Col(width=6, children=[
                                dcc.Dropdown(style=dict(width='100%'),
                                             id='trace-variable',
                                             # options=create_options(long_names.copy(), remove_trace),
                                             multi=False,
                                             clearable=False,
                                             placeholder='Pick a variable to trace...',
                                             # value=trace_variable
                                             ),
                            ]),
                            dbc.Col(width=4, children=[
                                dcc.Dropdown(style=dict(width='100%'),
                                             id='trace-decimation',
                                             options=[
                                                 {'label': '1 sample/24 hours', 'value': '24'},
                                                 {'label': '1 sample/18 hours', 'value': '18'},
                                                 {'label': '1 sample/15 hours', 'value': '15'},
                                                 {'label': '1 sample/12 hours', 'value': '12'},
                                                 {'label': '1 sample/9 hours', 'value': '9'},
                                                 {'label': '1 sample/6 hours', 'value': '6'},
                                                 {'label': '1 sample/3 hours', 'value': '3'},
                                                 {'label': 'No sub-sampling', 'value': '0'},
                                             ],
                                             multi=False,
                                             clearable=False,
                                             # value=trace_decimation
                                             ),
                            ])
                        ]),
                    ]),
                    dcc.Loading(id='trace-loader',
                                children=[dcc.Graph(id='trajectory-plot', config=graph_config, )])
                ], ),
            ])
        ]),
        dbc.Row([
            dbc.Col(id='timeseries-plots-column', style={'display': 'none'}, width=12, children=[
                dbc.Card(children=[
                    dbc.CardHeader(children=[
                        dbc.Row(align="center", children=[
                            dbc.Col(width=3, children=[
                                html.H5(id='plots-title', children=['Plots...'],
                                        className="card-title", style={"float": "left"})
                            ]),
                            dbc.Col(width=3, children=[
                                dcc.Dropdown(style=dict(width='100%'),
                                             id='plot-variables',
                                             # options=create_options(long_names.copy(), remove_plots),
                                             multi=True,
                                             clearable=False,
                                             placeholder='Pick variables for timeseries plots...',
                                             # value=plot_variables
                                             ),
                            ]),
                            dbc.Col(width=2, children=[
                                dbc.Checklist(id='plots-per', options=[
                                    {"label": "One plot per platform", "value": 'one'}
                                ], inline=True, switch=True
                                              )
                            ]),
                            dbc.Col(width=2, children=[
                                dcc.Dropdown(style=dict(width='100%'),
                                             id='plots-decimation',
                                             options=[
                                                 {'label': '1 sample/24 hours', 'value': '24'},
                                                 {'label': '1 sample/18 hours', 'value': '18'},
                                                 {'label': '1 sample/15 hours', 'value': '15'},
                                                 {'label': '1 sample/12 hours', 'value': '12'},
                                                 {'label': '1 sample/9 hours', 'value': '9'},
                                                 {'label': '1 sample/6 hours', 'value': '6'},
                                                 {'label': '1 sample/3 hours', 'value': '3'},
                                                 {'label': 'No sub-sampling', 'value': '0'},
                                             ],
                                             multi=False,
                                             clearable=False,
                                             # value=plots_decimation
                                             ),
                            ]),
                            dbc.Col(width=1, children=[
                                dcc.Dropdown(style=dict(width='100%'),
                                             id='plots-mode',
                                             options=[
                                                 {'label': 'Markers', 'value': 'markers'},
                                                 {'label': 'Lines', 'value': 'lines'},
                                                 {'label': 'Both', 'value': 'both'},
                                             ],
                                             multi=False,
                                             clearable=False,
                                             placeholder='Line mode',
                                             value='both'
                                             ),
                            ]),
                            dbc.Col(width=1, children=[
                                dcc.Dropdown(style=dict(width='100%'),
                                             id='plots-columns',
                                             options=[
                                                 {'label': '1 column', 'value': '1'},
                                                 {'label': '2 columns', 'value': '2'},
                                                 {'label': '3 columns', 'value': '3'},
                                                 {'label': '4 columns', 'value': '4'},
                                             ],
                                             multi=False,
                                             clearable=False,
                                             placeholder='Maximum columns',
                                             ),
                            ]),
                        ]),
                    ]),
                    dcc.Loading(id='plot-loader',
                                children=[dcc.Graph(id='plots', config=graph_config, )]),
                ]),
            ])
        ]),
        dbc.Row(style={'margin-bottom': '10px'}, children=[
            dbc.Col(width=12, children=[
                dbc.Card(children=[
                    dbc.Row(children=[
                        dbc.Col(width=1, children=[
                            html.Img(src='https://www.pmel.noaa.gov/sites/default/files/PMEL-meatball-logo-sm.png',
                                     height=100,
                                     width=100),
                        ]),
                        dbc.Col(width=10, children=[
                            html.Div(children=[
                                dcc.Link('National Oceanic and Atmospheric Administration',
                                         href='https://www.noaa.gov/'),
                            ]),
                            html.Div(children=[
                                dcc.Link('Pacific Marine Environmental Laboratory', href='https://www.pmel.noaa.gov/'),
                            ]),
                            html.Div(children=[
                                dcc.Link('oar.pmel.webmaster@noaa.gov', href='mailto:oar.pmel.webmaster@noaa.gov')
                            ]),
                            html.Div(children=[
                                dcc.Link('DOC |', href='https://www.commerce.gov/'),
                                dcc.Link(' NOAA |', href='https://www.noaa.gov/'),
                                dcc.Link(' OAR |', href='https://www.research.noaa.gov/'),
                                dcc.Link(' PMEL |', href='https://www.pmel.noaa.gov/'),
                                dcc.Link(' Privacy Policy |', href='https://www.noaa.gov/disclaimer'),
                                dcc.Link(' Disclaimer |', href='https://www.noaa.gov/disclaimer'),
                                dcc.Link(' Accessibility', href='https://www.pmel.noaa.gov/accessibility')
                            ])
                        ]),
                        dbc.Col(width=1, children=[
                            html.Div(style={'font-size': '1.1rem', 'position': 'absolute', 'bottom': '0'},
                                     children=[version])
                        ])
                    ])
                ])
            ])
        ])
    ]),
    html.Div(id='data-div', style={'display': 'none'})
])


def get_cones_df(cone_data_url):
    cones_df = None
    try:
        cones_df = pd.read_csv(cone_data_url, skiprows=[1])
    except:
        print('load_platforms: No cones found.')
    return cones_df


def get_location_df(drones_in, days_ago):
    all_dfs = []
    for sd in drones_in:
        # You have to specify the drone since some data sets are actually collections of drones
        lurl = drones_in[sd]['url'] + '.csv?trajectory,time,latitude,longitude&orderByClosest(%22time/24hours%22)&trajectory="' + str(sd) + '"'
        # This is a hack because time/24hours & max(time)-7days doesn't work for a data set with one day of data
        if days_ago > 0 and 'sea_trial' not in lurl:
            lurl = lurl + '&time>=max(time)-' + str(days_ago) + 'days'
        print(lurl)
        sdf = pd.read_csv(
            lurl,
            dtype={'trajectory': 'str', 'time': 'str', 'latitude': np.float64, 'longitude': np.float64},
            skiprows=[1])
        all_dfs.append(sdf)
    df = pd.concat(all_dfs, ignore_index=True)
    return df


@app.callback(
    [
        Output('mission-menu-dd', 'value')
    ],
    [
        Input('data-div', 'children'),
        Input('location-map', 'clickData'),
    ]
)
def set_mission_menu_from_url(click, selection):
    url = flask.request.referrer
    parts = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parts.query)
    set_mission_id = None
    if 'mission_id' in params:
        set_mission_id = params['mission_id'][0]
    if selection is not None:
        fst_point = selection['points'][0]
        selection_code = fst_point['customdata'][0]
        clicked_mission = next(
            (item for item in missions_json['config']['missions'] if item['mission_id'] == selection_code), None)
        if clicked_mission is not None:
            set_mission_id = selection_code

    return [set_mission_id]


@app.callback(
    [
        Output('current-mission-id', 'data'),
        Output('header-items', 'children'),
        Output('drone-menu-display', 'style'),
        Output('drone', 'options'),
        Output('date-range', 'min_date_allowed'),
        Output('date-range', 'max_date_allowed'),
        Output('date-range', 'initial_visible_month'),
        Output('date-range', 'start_date'),
        Output('date-range', 'end_date'),
        Output('trace-variable', 'options'),
        Output('trace-variable', 'value'),
        Output('plot-variables', 'options'),
        Output('plot-variables', 'value'),
        Output('trace-decimation', 'value'),
        Output('plots-decimation', 'value'),
        Output('plots-columns', 'value'),
        Output('plots-mode', 'value'),
        Output('plots-per', 'value'),
        Output('mission-menu-dd', 'style'),
        Output('layout-complete', 'data'),
    ],
    [
        Input('data-div', 'children'),
        Input('mission-menu-dd', 'value')
    ],
    [
        State('current-mission-id', 'data'),
    ]
)
def page_layout(click, mission_id_from_menu, state_mission_id):
    # This will run every time.
    # To decide on the layout, this function will consider 3 things:
    #
    # 1. If there are enough query parameters to determine the state of the UI as set up to display one
    #    particular mission (mission_id=blah) and then fill in all of the other state set for that mission
    #    display.
    # 2. With no mission ID, look at the total number of missions in the config.
    #       -> If there is only one, configure the UI for that mission nd display the mission layout.
    #       -> If there is more than one, configure the UI for the overview page

    update_mission_metadata()

    url = flask.request.referrer
    parts = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parts.query)

    # If the state mission id is not set, then it's the initial load
    print('mission id from state is ' + str(state_mission_id))
    if 'mission_id' in params and (state_mission_id is None or len(state_mission_id) == 0):
        mission_id = params['mission_id'][0]
        print('mission_id from url is ' + str(mission_id))
        mission_layout = True
    # override with the menu value if it's set
    else:
        print('mmission id from menu is ' + str(mission_id_from_menu))
        mission_id = mission_id_from_menu
        mission_layout = True

    if mission_id is None:
        if len(missions_json['config']['missions']) == 1:
            mission_id = missions_json['config']['missions'][0]['mission_id']
            mission_layout = True
        else:
            mission_layout = False

    if state_mission_id is not None:
        if mission_id == state_mission_id:
            raise dash.exceptions.PreventUpdate

    # set to None for overview layout
    set_start_date = None
    set_end_date = None
    drone_options = []
    variable_options = []
    trace_variable = None
    plot_variables = []
    set_max_columns = max_columns
    trace_decimation = 24
    plots_decimation = 24
    mode = 'both'
    q_plots_per = []
    mission_start_date = None
    mission_end_date = None
    print('mission_layout is ' + str(mission_layout))
    if mission_layout:
        m_header_items = []
        m_logos = []
        m_orgs = []
        m_title_width = 6
        cur_mission = next(
            (item for item in missions_json['config']['missions'] if item['mission_id'] == mission_id), None)
        if 'logos' in cur_mission['ui']:
            m_logos = cur_mission['ui']['logos']
        if len(m_logos) > 0:
            a_logo = logos[0]['logo']
            m_header_items.append(dbc.Col(width=3, children=[html.Img(src=a_logo, style={'height':'auto', 'width':'auto'})]))

        if 'orgs' in cur_mission['ui']:
            m_orgs = cur_mission['ui']['orgs']
            if len(m_orgs) > 0:
                m_title_width = 5 
                m_org_col = dbc.Col(width=4)
                m_org_kids = []
                for m_org in m_orgs:
                    m_org_row = dbc.Row(
                        html.A(children=[m_org['org']], href=m_org['url'], style={'text-decoration': 'none', 'font-size': '1.1rem', 'font-weight': 'bold'})
                    )
                    m_org_kids.append(m_org_row)
                m_org_col.children = m_org_kids
                m_header_items.append(m_org_col)
        if 'title' in cur_mission['ui']:
            mission_title = cur_mission['ui']['title']
        else:
            mission_title = dashboard_title

        if 'href' in cur_mission['ui']:
            mission_href = cur_mission['ui']['href']
        else:
            mission_href = dashboard_link

        m_header_items.append(
            dbc.Col(width=m_title_width, style={'display': 'flex', 'align-items': 'center'}, children=[
            html.A(
                dbc.NavbarBrand(mission_title, className="ml-2", style={'font-size': '1.1rem', 'font-weight': 'bold'}),
                href=mission_href, style={'text-decoration': 'none'}
            )
            ])
        )

        if len(m_logos) > 1:
            a_logo = m_logos[1]['logo']
            m_header_items.append(dbc.Col(width=3, children=[
                                          html.Img(src=a_logo, style={'height':'auto', 'width':'auto'})
                                  ]))

        cur_drones = cur_mission['drones']
        for drone_key in sorted(cur_drones.keys()):
            drone_options.append({'label': cur_drones[drone_key]['label'], 'value': drone_key})
        cur_long_names = cur_mission['long_names']
        for key, value in sorted(cur_long_names.items(), key=lambda x: x[1]):
            variable_options.append({'label': value, 'value': key})

        if 'mode' in params:
            mode = params['mode'][0]

        if 'plots_per' in params:
            q_plots_per = params['plots_per'][0]
            if q_plots_per == 'all':
                q_plots_per = []
            else:
                q_plots_per = ['one']
        if 'drone' in params:
            req_drones = params['drone']
            # If we changed drones remove any old drones that aren't in the new mission
            if len(req_drones) > 0:
                req_drones[:] = filterfalse(lambda tdx: tdx not in drones, req_drones)
        if 'trace_decimation' in params:
            trace_decimation_params = params['trace_decimation']
            trace_decimation = trace_decimation_params[0]
        if 'plots_decimation' in params:
            plots_decimation_params = params['plots_decimation']
            plots_decimation = plots_decimation_params[0]
        trace_variable = None
        if 'trace_variable' in params:
            trace_variable_params = params['trace_variable']
            trace_variable = trace_variable_params[0]

        if 'timeseries' in params:
            plot_variables = params['timeseries']

        if 'start_date' in params:
            set_start_date = params['start_date'][0]
        else:
            set_start_date = cur_mission['start_date']
        mission_start_date = cur_mission['start_date']

        if 'end_date' in params:
            set_end_date = params['end_date'][0]
        else:
            set_end_date = cur_mission['end_date']
        mission_end_date = cur_mission['end_date']

        if 'columns' in params and state_mission_id is None:
            set_max_columns = params['columns'][0]
        else:
            if 'max_columns' in cur_mission['ui']:
                set_max_columns = str(cur_mission['ui']['max_columns'])
            else:
                set_max_columns = max_columns
        style = {'display': 'block'}

    else:
        m_header_items = header_items.copy()
        style = {'display': 'none'}
    missions_style = {'display': 'block', 'width': '100%'}
    if len(missions_json['config']['missions']) == 1:
        missions_style = {'display': 'none', 'width': '100%'}

    return [
        mission_id,
        m_header_items,
        style,
        drone_options,
        mission_start_date,
        mission_end_date,
        set_start_date,
        set_start_date,
        set_end_date,
        variable_options,
        trace_variable,
        variable_options,
        plot_variables,
        trace_decimation,
        plots_decimation,
        set_max_columns,
        mode,
        q_plots_per,
        missions_style,
        datetime.datetime.now().isoformat()
    ]


# Right now the only reason this runs is because of the initial callback
# when the app starts. It could be tied to a refresh button...
@app.callback(
    [
        Output('location-map', 'figure'),
        Output('location-map-column', 'width'),
        Output('date-range-column', 'style'),
        Output('trajectory-map-column', 'style'),
        Output('timeseries-plots-column', 'style')
    ],
    [
        Input('layout-complete', 'data'),
    ],
    [
        State('current-mission-id', 'data')
    ]
)
def load_platforms(layout_complete, cur_mission_id):
    ctx = dash.callback_context
    if layout_complete is None:
        raise dash.exceptions.PreventUpdate

    if cur_mission_id is not None and len(cur_mission_id) > 0:
        the_mission = next(
            (item for item in missions_json['config']['missions'] if item['mission_id'] == cur_mission_id), None)
        cur_cones_url = None
        if 'cones_url' in the_mission['ui']:
            cur_cones_url = the_mission['ui']['cones_url']
        get_drones = the_mission['drones']
        days_ago = -1
        if 'days_ago' in the_mission['ui']:
            days_ago = int(the_mission['ui']['days_ago'])
        df = get_location_df(get_drones, days_ago)
        category_orders = the_mission['category_orders']
        marker_color = 'trajectory'
        hover_data = ['time', 'latitude', 'longitude', 'trajectory']
        labels = {'trajectory': 'Saildrone ID'}
        custom_data = ['trajectory']
        width = 6
        style = {'display': 'block'}
        height_of_map = short_map_height
        color_seq = px.colors.qualitative.Dark24
    else:
        all_drone_locations = []
        titles = []
        cur_cones_url = None
        if 'cones_url' in missions_json['config']['ui']:
            cur_cones_url = missions_json['config']['ui']['cones_url']
        days_ago = -1
        if 'days_ago' in missions_json['config']['ui']:
            days_ago = int(missions_json['config']['ui']['days_ago'])
        for plot_mission in missions_json['config']['missions']:
            get_drones = plot_mission['drones']
            gdf = get_location_df(get_drones, days_ago)
            titles.append(plot_mission['ui']['title'])
            gdf['title'] = plot_mission['ui']['title']
            gdf['mission_id'] = plot_mission['mission_id']
            all_drone_locations.append(gdf)
        df = pd.concat(all_drone_locations)
        category_orders = {'title': titles}
        marker_color = 'title'
        hover_data = ['time', 'latitude', 'longitude', 'title']
        labels = {'title': 'Mission'}
        custom_data = ['mission_id']
        width = 12
        style = {'display': 'none'}
        height_of_map = tall_map_height
        color_seq = px.colors.qualitative.Alphabet

    cones_df = get_cones_df(cur_cones_url)
    zoom, center = zoom_center(lons=df['longitude'], lats=df['latitude'])
    location_map = px.scatter_mapbox(df, lat='latitude', lon='longitude',
                                     color=marker_color,
                                     hover_data=hover_data,
                                     custom_data=custom_data,
                                     labels=labels,
                                     category_orders=category_orders,
                                     color_discrete_sequence=color_seq
                                     )
    location_map.update_layout(
        mapbox_style="white-bg",
        mapbox_layers=[
            {
                "below": 'traces',
                "sourcetype": "raster",
                "sourceattribution": "Powered by Esri",
                "source": [
                    "https://ibasemaps-api.arcgis.com/arcgis/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}?token=" + ESRI_API_KEY
                ]
            }
        ],
        mapbox_zoom=zoom,
        mapbox_center=center,
        height=height_of_map,
        legend=dict(
            orientation="h",
            yanchor="top",
            y=1.1,
        ), clickmode='event+select', modebar_orientation='v')
    location_map.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0})
    location_map.update_geos(
        fitbounds='locations',
        showcoastlines=True, coastlinecolor="RebeccaPurple",
        showland=True, landcolor="LightGreen",
        showocean=True, oceancolor="Azure",
        showlakes=True, lakecolor="Blue",
    )
    location_map.update_traces(marker_size=10, unselected=dict(marker=dict(opacity=1.0)), )

    cone_colors = px.colors.qualitative.Light24

    if cones_df is not None and cones_df.shape[0] > 1:
        cones = cones_df['name'].unique()
        for inx, cone in enumerate(cones):
            colors = color.to_rgba(cone_colors[inx])
            fill_color = 'rgba(' + str(colors[0]) + ',' + str(colors[1]) + ',' + str(colors[2]) + ', 0.5)'
            line_color = cone_colors[inx]
            x = cones_df.loc[cones_df['name'] == cone, 'longitude']
            y = cones_df.loc[cones_df['name'] == cone, 'latitude']
            cone_map = go.Scattermapbox(lon=x,
                                        lat=y,
                                        mode='lines',
                                        name=cone,
                                        fill='toself',
                                        hoverinfo='name',
                                        hoverlabel={'namelength': -1},
                                        fillcolor=fill_color,
                                        line=dict(color=line_color))
            location_map.add_trace(cone_map)

    return [location_map, width, style, style, style]


@app.callback([
    Output('plots-title', 'children')
], [
    Input('location', 'search'),
])
def ts_plot_title(search):
    if search is None:
        raise dash.exceptions.PreventUpdate
    elif len(search) == 0:
        raise dash.exceptions.PreventUpdate

    title = ''
    if search is not None and len(search) > 0:
        params = urllib.parse.parse_qs(search[1:])
        if 'drone' in params:
            tdrones = params['drone']
            for i, d in enumerate(tdrones):
                if i == 0:
                    title = title + d
                else:
                    title = title + ', ' + d
    else:
        raise dash.exceptions.PreventUpdate

    plots_title = 'Plots for saildrone ' + str(title)
    return [plots_title]


@app.callback([
    Output('drone', 'value'),
], [
    Input('location-map', 'clickData'),
    Input('data-div', 'children'),
    Input('layout-complete', 'data')
], [
    State('location', 'search')
]
)
def set_drone_from_map(selection, click, layout_complete, search):
    if layout_complete is None:
        raise dash.exceptions.PreventUpdate
    # get from the URL as well as a map click
    url = flask.request.referrer
    parts = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parts.query)
    qdrones = []
    if 'drone' in params:
        qdrones = params['drone']

    if search is not None:
        current_selections = urllib.parse.parse_qs(search[1:])
        if 'drone' in current_selections:
            qdrones = current_selections['drone']
    if selection is not None:
        fst_point = selection['points'][0]
        selection_code = fst_point['customdata'][0]
        if selection_code in qdrones:
            qdrones.remove(selection_code)
        else:
            qdrones.append(selection_code)
    return [qdrones]


@app.callback([
    Output('trace-config', 'data'),
], [
    Input('drone', 'value'),
    Input('trace-decimation', 'value'),
    Input('trace-variable', 'value'),
    Input('date-range', 'start_date'),
    Input('date-range', 'end_date')
], [
    State('current-mission-id', 'data')
]
)
def set_trace_data(drone, trace_decimation, trace_variable, selected_start_date, selected_end_date, cur_id):
    trace_config = {'config': {}}
    drones_selected = []
    check_mission_drones = []

    if drone is not None:
        print(drone)
        if cur_id is not None:
            cur_mission = next(
                (item for item in missions_json['config']['missions'] if item['mission_id'] == cur_id), [])
            check_mission_drones = cur_mission['drones']
        if isinstance(drone, list):
            if len(check_mission_drones) > 0:
                print('before not in list')
                print(drone)
                drone[:] = filterfalse(lambda x: x not in check_mission_drones, drone)
                print('after not in list')
                print(drone)
            drones_selected = drone
        elif isinstance(drone, str):
            if len(check_mission_drones) > 0:
                if drone in check_mission_drones:
                    drones_selected = [drone]
                    print('single drone')
                    print(drones_selected)
        if len(drones_selected) > 0:
            print('adding drones to donfig')
            trace_config['config']['drones'] = drones_selected

    if trace_decimation is None:
        trace_decimation = "24"
    trace_config['config']['trace_decimation'] = trace_decimation

    if trace_variable is not None:
        if len(trace_variable) > 0:
            if isinstance(trace_variable, list):
                trace_config['config']['trace_variable'] = trace_variable
            else:
                trace_config['config']['trace_variable'] = [trace_variable]
    if selected_start_date is not None:
        if len(selected_start_date) > 0:
            if isinstance(selected_start_date, list):
                trace_config['config']['start_date'] = selected_start_date[0]
            else:
                trace_config['config']['start_date'] = selected_start_date

    if selected_end_date is not None:
        if len(selected_end_date) > 0:
            if isinstance(selected_end_date, list):
                trace_config['config']['end_date'] = selected_end_date[0]
            else:
                trace_config['config']['end_date'] = selected_end_date
    return [json.dumps(trace_config)]


@app.callback([
    Output('plots-config', 'data'),
], [
    Input('drone', 'value'),
    Input('plots-decimation', 'value'),
    Input('plot-variables', 'value'),
    Input('date-range', 'start_date'),
    Input('date-range', 'end_date'),
    Input('plots-columns', 'value'),
    Input('plots-mode', 'value'),
    Input('plots-per', 'value'),
], [
    State('current-mission-id', 'data')
]
)
def set_plots_data(drone, plots_decimation, plot_variables, selected_start_date, selected_end_date, columns, mode,
                   plots_per, cur_id):
    plots_config = {'config': {}}
    if mode is None:
        mode = 'both'
    plots_config['config']['mode'] = mode
    if columns is None:
        columns = max_columns
    plots_config['config']['columns'] = columns
    drones_selected = []
    check_mission_drones = []
    if drone is not None:
        if cur_id is not None:
            cur_mission = next(
                (item for item in missions_json['config']['missions'] if item['mission_id'] == cur_id), [])
            check_mission_drones = cur_mission['drones']
        if isinstance(drone, list):
            if len(check_mission_drones) > 0:
                drone[:] = filterfalse(lambda x: x not in check_mission_drones, drone)
            drones_selected = drone
        elif isinstance(drone, str):
            if len(check_mission_drones) > 0:
                if drone in check_mission_drones:
                    drones_selected = [drone]
        if len(drones_selected) > 0:
            plots_config['config']['drones'] = drones_selected

    if plots_decimation is None:
        plots_decimation = "24"
    plots_config['config']['plots_decimation'] = plots_decimation

    pp_value = 'all'
    if plots_per is not None:
        if isinstance(plots_per, list):
            if len(plots_per) > 0:
                pp_value = plots_per[0]
        else:
            pp_value = plots_per
    plots_config['config']['plots_per'] = pp_value

    if plot_variables is not None:
        if isinstance(plot_variables, list):
            if len(plot_variables) > 0:
                plots_config['config']['timeseries'] = plot_variables
        else:
            if len(plot_variables) > 0:
                plots_config['config']['timeseries'] = [plot_variables]
    if selected_start_date is not None:
        if len(selected_start_date) > 0:
            plots_config['config']['start_date'] = selected_start_date
    if selected_end_date is not None:
        if len(selected_end_date) > 0:
            plots_config['config']['end_date'] = selected_end_date
    return [json.dumps(plots_config)]


@app.callback([
    Output('location', 'search'),
], [
    Input('drone', 'value'),
    Input('trace-decimation', 'value'),
    Input('trace-variable', 'value'),
    Input('plots-decimation', 'value'),
    Input('plot-variables', 'value'),
    Input('date-range', 'start_date'),
    Input('date-range', 'end_date'),
    Input('plots-columns', 'value'),
    Input('plots-mode', 'value'),
    Input('plots-per', 'value'),
    Input('mission-menu-dd', 'value')
], [
    State('current-mission-id', 'data')
]
)
def set_search(drone,
               trace_decimation,
               trace_variable,
               plots_decimation,
               plot_variables,
               selected_start_date,
               selected_end_date,
               num_plot_cols,
               plot_mode,
               plots_per,
               mission_dropdown_value,
               current_mission_id):
    s = '?'
    if mission_dropdown_value is not None and len(mission_dropdown_value) > 0:
        s = s + 'mission_id=' + str(mission_dropdown_value)
    check_mission_drones = []
    if current_mission_id is not None and len(current_mission_id) > 0:
        the_cur_mission = next(
            (item for item in missions_json['config']['missions'] if item['mission_id'] == current_mission_id), None)
        check_mission_drones = the_cur_mission['drones']

    if drone is not None:
        if isinstance(drone, list):
            # squish out any drones that aren't from the current mission
            drone[:] = filterfalse(lambda x: x not in check_mission_drones, drone)
            for d in drone:
                if len(s) == 1:
                    s = s + 'drone=' + d
                else:
                    s = s + '&drone=' + d
        elif isinstance(drone, str):
            # if drone in check_mission_drones:
            s = s + 'drone=' + drone
    if trace_decimation is not None:
        if len(s) == 1:
            s = s + 'trace_decimation=' + str(trace_decimation)
        else:
            s = s + '&trace_decimation=' + str(trace_decimation)
    if trace_variable is not None:
        if len(s) == 1:
            s = s + 'trace_variable=' + trace_variable
        else:
            s = s + '&trace_variable=' + trace_variable
    if plots_decimation is not None:
        if len(s) == 1:
            s = s + 'plots_decimation=' + str(plots_decimation)
        else:
            s = s + '&plots_decimation=' + str(plots_decimation)
    if plot_variables is not None:
        if isinstance(plot_variables, list):
            for ts in plot_variables:
                if len(s) == 1:
                    s = s + 'timeseries=' + ts
                else:
                    s = s + '&timeseries=' + ts
        elif isinstance(plot_variables, str):
            s = s + '&timeseries=' + plot_variables

    if selected_start_date is not None:
        if len(selected_start_date) > 0:
            s = s + '&start_date=' + selected_start_date

    if selected_end_date is not None:
        if len(selected_end_date) > 0:
            s = s + '&end_date=' + selected_end_date

    if num_plot_cols is not None:
        s = s + '&columns=' + str(num_plot_cols)

    if plot_mode is not None:
        s = s + '&mode=' + plot_mode

    pp_value = 'all'
    if plots_per is not None:
        if isinstance(plots_per, list):
            if len(plots_per) > 0:
                pp_value = plots_per[0]
        if len(s) == 1:
            s = s + 'plots_per=' + str(pp_value)
        else:
            s = s + '&plots_per=' + str(pp_value)

    if len(s) == 1:
        return ['']
    else:
        return [s]


@app.callback([
    Output('trajectory-plot', 'figure'),
], [
    Input('trace-config', 'data'),
    Input('current-mission-id', 'data'),
], prevent_initial_call=True)
def make_trajectory_trace(trace_config, cur_mission_id):
    if trace_config is None:
        raise dash.exceptions.PreventUpdate
    elif len(trace_config) == 0:
        raise dash.exceptions.PreventUpdate

    if cur_mission_id is None:
        raise dash.exceptions.PreventUpdate
    elif len(cur_mission_id) == 0:
        raise dash.exceptions.PreventUpdate

    trace_decimation = 24
    trace_start_date = None
    trace_end_date = None

    if trace_config is not None and len(trace_config) > 0:
        # must hae a drone, and a variable
        trace_json = json.loads(trace_config)
        if 'drones' in trace_json['config']:
            pdrones = trace_json['config']['drones']
        else:
            return [blank_map]

        if 'trace_variable' in trace_json['config']:
            trace_variable = trace_json['config']['trace_variable']
        else:
            return [blank_map]

        # don't have to have a decimation value, but it's gonna be there anyway
        if 'trace_decimation' in trace_json['config']:
            trace_decimation_params = trace_json['config']['trace_decimation']
            trace_decimation = int(trace_decimation_params)

        if 'start_date' in trace_json['config']:
            trace_start_date = trace_json['config']['start_date']
        if 'end_date' in trace_json['config']:
            trace_end_date = trace_json['config']['end_date']
    else:
        raise dash.exceptions.PreventUpdate

    if 'time' not in trace_variable:
        trace_variable.append('time')

    the_cur_mission = next(
        (item for item in missions_json['config']['missions'] if item['mission_id'] == cur_mission_id), None)
    cur_drones = the_cur_mission['drones']
    cur_long_names = the_cur_mission['long_names']

    if 'latitude' not in trace_variable:
        trace_variable.append('latitude')
    if 'longitude' not in trace_variable:
        trace_variable.append('longitude')
    if 'trajectory' not in trace_variable:
        trace_variable.append('trajectory')
    req_var = ",".join(trace_variable)

    order_by = '&orderBy("time")'
    if trace_decimation > 0:
        order_by = '&orderByClosest(%22time/' + str(trace_decimation) + 'hours%22)'
    if trace_start_date is not None:
        order_by = order_by + '&time>=' + trace_start_date
    #if trace_end_date is not None and 'seatrial' not in cur_mission_id:
    if trace_end_date is not None:
        trace_end_date = trace_end_date + "T23:59:59"
        order_by = order_by + '&time<=' + trace_end_date
    data_tables = []
    for drone_id in pdrones:
        drone_url = cur_drones[drone_id]['url'] + '.csv?' + req_var + order_by + '&trajectory="' + drone_id + '"'
        try:
            d_df = pd.read_csv(drone_url, skiprows=[1], parse_dates=date_col)
            data_tables.append(d_df)
        except:
            print('exception getting data from ' + drone_url)
            continue

    if len(data_tables) == 0:
        return [no_data_graph]

    df = pandas.concat(data_tables)

    if df.shape[0] < 3:
        return [no_data_graph]

    df = df[df[trace_variable[0]].notna()]
    df.loc[:, 'text_time'] = df['time'].astype(str)
    df.loc[:, 'millis'] = pd.to_datetime(df['time']).view(np.int64)
    df.loc[:, 'text'] = df['text_time'] + "<br>" + df['trajectory'].astype(str) + "<br>" + trace_variable[0] + '=' + df[
        trace_variable[0]].astype(str)
    plot_var = trace_variable[0]
    name_var = trace_variable[0]
    color_scale = 'inferno'
    color_bar_opts = dict(x=-.15, title=cur_long_names[name_var])
    if plot_var == 'time':
        plot_var = 'millis'
        name_var = 'Date/Time'
        color_scale = 'cividis_r'
        color_bar_opts = dict(x=-.15, title=name_var, ticktext=[df['text_time'].iloc[0], df['text_time'].iloc[-1]],
                              tickvals=[df['millis'].iloc[0], df['millis'].iloc[-1]])
    zoom, center = zoom_center(lons=df['longitude'], lats=df['latitude'])
    location_trace = go.Figure(data=go.Scattermapbox(lat=df["latitude"], lon=df["longitude"],
                                                     text=df['text'],
                                                     marker=dict(showscale=True, color=df[plot_var],
                                                                 colorscale=color_scale, size=8,
                                                                 colorbar=color_bar_opts, )
                                                     )
                               )
    location_trace.update_layout(
        height=short_map_height, margin={"r": 0, "t": 0, "l": 0, "b": 0},
        mapbox_style="white-bg",
        mapbox_layers=[
            {
                "below": 'traces',
                "sourcetype": "raster",
                "sourceattribution": "Powered by Esri",
                "source": [
                    "https://ibasemaps-api.arcgis.com/arcgis/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}?token=" + ESRI_API_KEY
                ]
            }
        ],
        mapbox_zoom=zoom,
        mapbox_center=center,
    )

    location_trace.update_geos(fitbounds='locations',
                               showcoastlines=True, coastlinecolor="RebeccaPurple",
                               showland=True, landcolor="LightGreen",
                               showocean=True, oceancolor="Azure",
                               showlakes=True, lakecolor="Blue", projection=dict(type="mercator"),
                               )
    ct = datetime.datetime.now()
    print('At ' + str(ct) + ' plotting trajectory of ' + str(trace_variable[0]) + ' for ' + str(pdrones))
    return [location_trace]


@app.callback([
    Output('plots', 'figure'),
], [
    Input('plots-config', 'data'),
    Input('current-mission-id', 'data')
], prevent_initial_call=True)
def make_plots(plots_json, cur_mission_id):
    if cur_mission_id is None:
        raise dash.exceptions.PreventUpdate

    num_columns = 3;
    plots_decimation = 24
    plots_start_date = None
    plots_end_date = None
    if plots_json is None:
        raise dash.exceptions.PreventUpdate
    elif len(plots_json) == 0:
        raise dash.exceptions.PreventUpdate

    if plots_json is not None and len(plots_json) > 0:
        plots_config = json.loads(plots_json)
        # must have a drone, and a variable
        if 'drones' in plots_config['config']:
            tsdrones = plots_config['config']['drones']
        else:
            return [blank_graph]

        if 'timeseries' in plots_config['config']:
            plot_variables = plots_config['config']['timeseries']
            original_order = plot_variables.copy()
            if len(plot_variables) == 0:
                return [blank_graph]
        else:
            return [blank_graph]
        # don't have to have a decimation value, but it's gonna be there anyway
        if 'plots_decimation' in plots_config['config']:
            plots_decimation = int(plots_config['config']['plots_decimation'])
        if 'start_date' in plots_config['config']:
            plots_start_date = plots_config['config']['start_date']
        if 'end_date' in plots_config['config']:
            plots_end_date = plots_config['config']['end_date']
        if 'columns' in plots_config['config']:
            num_columns = int(plots_config['config']['columns'])

        plots_per = 'all'
        if 'plots_per' in plots_config['config']:
            plots_per = plots_config['config']['plots_per']
    else:
        raise dash.exceptions.PreventUpdate

    the_mission_config = next(
        (item for item in missions_json['config']['missions'] if item['mission_id'] == cur_mission_id), None)
    cur_drones = the_mission_config['drones']
    # the next thing
    cur_long_names = the_mission_config['long_names']
    cur_units = the_mission_config['units']
    if 'time' not in plot_variables:
        plot_variables.append('time')
    if 'latitude' not in plot_variables:
        plot_variables.append('latitude')
    if 'longitude' not in plot_variables:
        plot_variables.append('longitude')
    if 'trajectory' not in plot_variables:
        plot_variables.append('trajectory')

    order_by = '&orderBy("time")'
    if plots_decimation > 0:
        order_by = '&orderByClosest(%22time/' + str(plots_decimation) + 'hours%22)'
    # hack for now because there's only one day
    if plots_start_date is not None:
        order_by = order_by + '&time>=' + plots_start_date
    #if plot_end_date is not None and 'seatrial' not in cur_mission_id:
    if plots_end_date is not None:
        plots_end_date = plots_end_date + 'T23:59:59'
        order_by = order_by + '&time<=' + plots_end_date

    plot_data_tables = []
    for d_ts in tsdrones:
        drone_plot_variables = plot_variables.copy()
        for plot_var in plot_variables:
            if plot_var not in cur_drones[d_ts]['variables']:
                drone_plot_variables.remove(plot_var)
        req_var = ",".join(drone_plot_variables)
        drone_url = cur_drones[d_ts]['url'] + '.csv?' + req_var + order_by + '&trajectory="' + d_ts + '"'
        try:
            print(drone_url)
            ts_df = pd.read_csv(drone_url, skiprows=[1], parse_dates=date_col)
            plot_data_tables.append(ts_df)
        except:
            print('exception getting data from ' + drone_url)
            continue
    if len(plot_data_tables) == 0:
        return [no_data_graph]
    df = pandas.concat(plot_data_tables)
    if df.shape[0] < 3:
        return [no_data_graph]
    df['trajectory'] = df['trajectory'].astype(str)
    colnames = list(df.columns)
    df.loc[:, 'text_time'] = df['time'].astype(str)

    sub_title = ''
    if df.shape[0] > 25000:
        sub_title = ' (>25K timeseries sub-sampled to 25,000 points) '
        df = df.sample(n=25000).sort_values(by=['time', 'trajectory'], ascending=True)
    subplots = {}
    titles = {}

    if '24' in str(plots_decimation):
        fre = '24H'
    elif '18' in str(plots_decimation):
        fre = '18H'
    elif '15' in str(plots_decimation):
        fre = '15H'
    elif '12' in str(plots_decimation):
        fre = '12H'
    elif '9' in str(plots_decimation):
        fre = '9H'
    elif '6' in str(plots_decimation):
        fre = '6H'
    elif '3' in str(plots_decimation):
        fre = '3H'
    else:
        fre = '1H'

    colnames.remove('latitude')
    colnames.remove('longitude')
    colnames.remove('time')
    colnames.remove('trajectory')
    mode = 'both'
    if 'mode' in plots_config['config']:
        mode = plots_config['config']['mode']
    if mode == 'both':
        mode = 'lines+markers'
    for var in original_order:
        dfvar = df[['time', 'trajectory', var]].copy()
        dfvar.loc[:, 'text_time'] = dfvar['time'].astype(str)
        dfvar.loc[:, 'time'] = pd.to_datetime(dfvar['time'])
        dfvar.dropna(subset=[var], how='all', inplace=True)
        if dfvar.shape[0] > 2:
            subtraces = []
            for drn in tsdrones:
                index = sorted(list(cur_drones.keys())).index(drn)
                n_color = px.colors.qualitative.Dark24[index % 24]
                dfvar_drone = dfvar.loc[(dfvar['trajectory'] == drn)]
                if plots_decimation > 0:
                    df2 = dfvar_drone.set_index('time')
                    # make a index at the expected delta
                    fill_dates = pd.date_range(dfvar_drone['time'].iloc[0], dfvar_drone['time'].iloc[-1], freq=fre)
                    all_dates = fill_dates.append(df2.index)
                    fill_sort = sorted(all_dates)
                    pdf3 = df2.reindex(fill_sort)
                    mask1 = ~pdf3['trajectory'].notna() & ~pdf3['trajectory'].shift().notna()
                    mask2 = pdf3['trajectory'].notna()
                    pdf4 = pdf3[mask1 | mask2]
                    dfvar_drone = pdf4.reset_index()
                render_test = dfvar_drone.shape[0]/(len(tsdrones)*len(original_order))
                dfvar_drone = dfvar_drone.sort_values(by=['time', 'trajectory'], ascending=True)
                if render_test > 1000 / (len(tsdrones) * len(original_order)):
                    varplot = go.Scattergl(x=dfvar_drone['time'], y=dfvar_drone[var], name=drn,
                                           marker={'color': n_color},
                                           mode=mode, hoverinfo='x+y+name')
                else:
                    varplot = go.Scatter(x=dfvar_drone['time'], y=dfvar_drone[var], name=drn,
                                         marker={'color': n_color},
                                         mode=mode, hoverinfo='x+y+name')
                subtraces.append(varplot)
            subplots[var] = subtraces
            title = var + sub_title
            if var in cur_long_names:
                title = cur_long_names[var] + sub_title
            print('checking ' + var + ' in units of')
            for u in cur_units:
                print(u)
            if var in cur_units:
                title = title + ' (' + cur_units[var] + ')'
            titles[var] = title

    if plots_per == 'all':
        num_plots = len(subplots)
    else:
        num_plots = len(subplots) * len(tsdrones)

    if num_plots == 0:
        return [no_data_graph]
    num_rows = int(num_plots / num_columns)
    if num_rows == 0:
        num_rows = num_rows + 1
    if num_plots > num_columns and num_plots % num_columns > 0:
        num_rows = num_rows + 1
    row_h = []
    for i in range(0, num_rows):
        row_h.append(1 / num_rows)
    graph_height = height_of_row * num_rows
    num_cols = min(num_plots, num_columns)

    titles_list = []
    if plots_per == 'one':
        for plot in original_order:
            next_title = titles[plot]
            if plot in subplots:
                c_plots = subplots[plot]
                for sp in c_plots:
                    sp_title = next_title + ' at ' + sp['name']
                    titles_list.append(sp_title)
    else:
        for plot in original_order:
            if plot in subplots:
                next_title = titles[plot]
                titles_list.append(next_title)

    plots = make_subplots(rows=num_rows, cols=num_cols, shared_xaxes='all', subplot_titles=titles_list,
                          shared_yaxes=False,
                          row_heights=row_h)
    plot_index = 1
    col = 1
    row = 1
    for plot in original_order:
        if plot in subplots:
            current_plots = subplots[plot]
            for i, cp in enumerate(current_plots):
                plots.add_trace(cp, row=row, col=col)
                if plots_per == 'one':
                    plot_index = plot_index + 1
                    if plot_index > 1:
                        if col == num_columns:
                            row = row + 1
                    col = plot_index % num_columns
                    if col == 0:
                        col = num_columns
            if plots_per == 'all':
                plot_index = plot_index + 1
                if plot_index > 1:
                    if col == num_columns:
                        row = row + 1
                col = plot_index % num_columns
                if col == 0:
                    col = num_columns

            plots.update_xaxes({'showticklabels': True, 'gridcolor': line_rgb})
            # plots.update_yaxes({'gridcolor': line_rgb, 'fixedrange': True})
            plots.update_yaxes({'gridcolor': line_rgb})

    plots['layout'].update(height=graph_height, margin=dict(l=80, r=80, b=80, t=80, ))
    plots.update_layout(plot_bgcolor=plot_bg)
    plots.update_traces(showlegend=False)
    ct = datetime.datetime.now()
    print('At ' + str(ct) + ' plotting timeseries of ' + str(colnames) + ' for ' + str(tsdrones))
    return [plots]


def update_mission_metadata():
    for updt_mission in missions:
        updt_drones = updt_mission['drones']
        updt_start_dates = []
        updt_end_dates = []
        updt_all_info_dt = []
        for updt_drone in updt_drones:
            updt_info_url = updt_drones[updt_drone]['url']
            updt_info_id = updt_info_url[updt_info_url.rindex("/") + 1:]
            updt_info_server = updt_info_url[0: updt_info_url.index('/erddap') + 7]
            updt_erdapy = ERDDAP(server=updt_info_server, protocol='tabledap')
            updt_drone_info_url = updt_erdapy.get_info_url(updt_info_id, response='csv')
            drone_info_df = pd.read_csv(updt_drone_info_url)
            updt_all_info_dt.append(drone_info_df)

            updt_start_date = drone_info_df.loc[(drone_info_df['Row Type'] == 'attribute') & (
                    drone_info_df['Attribute Name'] == 'time_coverage_start') & (
                    drone_info_df['Variable Name'] == 'NC_GLOBAL')]['Value'].to_list()[0]
            updt_end_date = drone_info_df.loc[(drone_info_df['Row Type'] == 'attribute') & (
                    drone_info_df['Attribute Name'] == 'time_coverage_end') & (
                    drone_info_df['Variable Name'] == 'NC_GLOBAL')]['Value'].to_list()[0]
            updt_start_dates.append(updt_start_date)
            updt_end_dates.append(updt_end_date)

        updt_sorted_start = sorted(updt_start_dates)
        updt_start_date = updt_sorted_start[0]

        updt_sorted_end = sorted(updt_end_dates)
        updt_end_date = updt_sorted_end[-1]

        updt_start_date_datetime = dateutil.parser.isoparse(updt_start_date)
        updt_end_date_datetime = dateutil.parser.isoparse(updt_end_date)

        updt_start_date = updt_start_date_datetime.date().strftime('%Y-%m-%d')
        updt_end_date = updt_end_date_datetime.date().strftime('%Y-%m-%d')
        updt_mission['start_date'] = updt_start_date
        updt_mission['end_date'] = updt_end_date

    rtnow = datetime.datetime.now()
    nwst = datetime.datetime.isoformat(rtnow)
    print('Updated mission end times at ', nwst)
    return nwst


if __name__ == '__main__':
    app.run_server(debug=True)
