from dash import Dash, dcc, html, page_container, Input, Output
import dash_design_kit as ddk
import plotly.express as px
import json
import os
import redis
import dateutil
import constants
from sdig.erddap.info import Info

version = 'v2.0'

config_json = None
with open('config/missions.json') as missions_config:
    config_json = json.load(missions_config)

if config_json is None:
    print('Missions config file not found.')
    sys.exit()    

missions = config_json['config']['missions']

for m in missions:
    mission = missions[m]
    drones = mission['drones']
    mission['category_orders'] = {'trajectory': sorted(drones.keys())}
    start_dates = []
    end_dates = []
    all_infos = []
    long_names = {}
    units = {}
    dsg_ids = []
    for d in drones:
        url = drones[d]['url']
        drone_info = Info(url)
        all_infos.append(drone_info)

        drone_info.get_variables()
        drone_vars, d_long_names, d_units, standard_names = drone_info.get_variables()
        drones[d]['variables'] = drone_vars
        depth_name, dsg_id = drone_info.get_dsg_info()
        dsg_ids.append(dsg_id['trajectory'])
        long_names = {**long_names, **d_long_names}
        units = {**units, **d_units}

    uids = list(set(dsg_ids))
    if len(uids) == 1:
        mission['dsg_id'] = uids[0]
    else:
        print('Mission has non-unique DSG ID names.')
    mission['long_names'] = long_names
    mission['units'] = units

menu = []
for idx, m in enumerate(sorted(missions)):
    link = constants.base + 'mission?mission_id=' + m
    icolor = px.colors.qualitative.Dark24[idx]
    menu_item = dcc.Link(children=[ddk.Icon(icon_name='database', icon_color=icolor), missions[m]['ui']['title']], href=link)
    menu.append(menu_item)

constants.redis_instance.hset("saildrone", "config", json.dumps(config_json))      

app = Dash(__name__, use_pages=True, suppress_callback_exceptions=True)
server = app.server  # expose server variable for Procfile

app.layout = ddk.App([
    dcc.Location(id='url', refresh=False),
    dcc.Store(id='plots-trigger'),
    dcc.Store(id='trace-trigger'),
    ddk.Sidebar(
        foldable=True,
        children=[
            html.A(
                ddk.Logo(
                    src=app.get_asset_url("PMEL_50th_Logo_vFINAL_emblem.png")
                ), href='https://www.pmel.noaa.gov/'
            ),
            dcc.Link(
                ddk.Title('Saildone Missions'),
                href=constants.base
            ),
            ddk.Menu(children=menu),
        ]
    ),            
    ddk.SidebarCompanion(style={'margin-left': '-25px'}, children=[
        page_container
    ])
])

if __name__ == '__main__':
    app.run_server(debug=True)
