from dash import Dash, dcc, html, page_container, Input, Output
import dash_design_kit as ddk
import plotly.express as px
import json
import os
import redis
import dateutil
import constants
from sdig.erddap.info import Info

version = 'v2.1'

config_json = None
with open('config/missions.json') as missions_config:
    config_json = json.load(missions_config)

if config_json is None:
    print('Missions config file not found.')
    sys.exit()    

collections = config_json['collections']

menu = []
coloridx = 0
for collection in collections:
    member_children = []
    member = collections[collection]
    item = ddk.CollapsibleMenu(title=member['title'])
    missions = member['missions']
    for idx, m in enumerate(sorted(missions)):
        mission = missions[m]
        link = constants.base + 'mission?mission_id=' + m
        icolor = px.colors.qualitative.Dark24[coloridx]
        coloridx = coloridx + 1
        menu_item = dcc.Link(children=[ddk.Icon(icon_name='database', icon_color=icolor), mission['ui']['title']], href=link)
        member_children.append(menu_item)
    item.children=member_children
    menu.append(item)



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
            ddk.Card(children=[
                html.Div(children=[
                    dcc.Link('National Oceanic and Atmospheric Administration',
                            href='https://www.noaa.gov/', style={'font-size': '.8em'}),
                ]),
                html.Div(children=[
                    html.Hr(),
                    dcc.Link('Pacific Marine Environmental Laboratory',
                            href='https://www.pmel.noaa.gov/',style={'font-size': '.8em'}),
                ]),
                html.Div(children=[
                    html.Hr(),
                    dcc.Link('oar.pmel.webmaster@noaa.gov', href='mailto:oar.pmel.webmaster@noaa.gov', style={'font-size': '.8em'})
                ]),
                html.Div(children=[
                    html.Hr(),
                    dcc.Link('DOC |', href='https://www.commerce.gov/', style={'font-size': '.8em'}),
                    dcc.Link(' NOAA |', href='https://www.noaa.gov/', style={'font-size': '.8em'}),
                    dcc.Link(' OAR |', href='https://www.research.noaa.gov/', style={'font-size': '.8em'}),
                    dcc.Link(' PMEL |', href='https://www.pmel.noaa.gov/', style={'font-size': '.8em'}),
                    dcc.Link(' Privacy Policy |', href='https://www.noaa.gov/disclaimer', style={'font-size': '.8em'}),
                    dcc.Link(' Disclaimer |', href='https://www.noaa.gov/disclaimer',style={'font-size': '.8em'}),
                    dcc.Link(' Accessibility', href='https://www.pmel.noaa.gov/accessibility',style={'font-size': '.8em'})
                ])
            ])
        ]
    ),            
    ddk.SidebarCompanion(style={'margin-left': '-25px'}, children=[
        page_container
    ])
])

if __name__ == '__main__':
    app.run_server(debug=True)
