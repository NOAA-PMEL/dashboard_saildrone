from dash import Dash, dcc, html, page_container, Input, Output, CeleryManager, DiskcacheManager

import dash_design_kit as ddk
import plotly.express as px
import json
import os
import redis
import dateutil
import constants
import dash_bootstrap_components as dbc
from sdig.erddap.info import Info
import tasks

import diskcache

import celery
from celery import Celery
from celery.schedules import crontab
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


celery_app = Celery(broker=os.environ.get("REDIS_URL", "redis://127.0.0.1:6379"), backend=os.environ.get("REDIS_URL", "redis://127.0.0.1:6379"))
if os.environ.get("DASH_ENTERPRISE_ENV") == "WORKSPACE":
    # For testing...
    # import diskcache
    cache = diskcache.Cache("./cache")
    background_callback_manager = DiskcacheManager(cache)
else:
    # For production...
    background_callback_manager = CeleryManager(celery_app)


@celery_app.task
def run_update():
    tasks.load_missions()

#
# !!!!!!!!!!
# Changing to on_after_finalize from on_after_config was the trick to getting
# the update task scheduled. It was being registered, but never scheduled.
@celery_app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    # Update all missions once an hour at 32 minutes past
    sender.add_periodic_task(
         crontab(minute='32', hour='*'),
         run_update.s(),
         name='Update missions'
    )

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
for collection in sorted(collections, reverse=True):
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

app = Dash(__name__, use_pages=True, suppress_callback_exceptions=True, background_callback_manager=background_callback_manager, external_stylesheets=[dbc.themes.BOOTSTRAP]) 
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
                    src=app.get_asset_url("pmel-emblem-rgb-2022.png")
                ), href='https://www.pmel.noaa.gov/'
            ),
            dcc.Link(
                ddk.Title('Saildrone Missions'),
                href=constants.base
            ),
            ddk.Menu(children=menu),
        ]
    ),            
    ddk.SidebarCompanion(style={'margin-left': '-25px'}, children=[
        # ddk.PageHeader(children=[
        #     html.Div('Parts of the US government are closed. This site will not be updated; however, NOAA websites and social media channels necessary to protect lives and property will be maintained. See ', style={'display':'inline-block'}), 
        #     html.Div('.', style={'display':'inline-block', 'visibility': 'hidden'}),
        #     html.A('www.weather.gov', href='https://www.weather.gov', style={'display':'inline-block'}), 
        #     html.Div('.', style={'display':'inline-block', 'visibility': 'hidden'}),
        #     html.Div(' for critical weather information. To learn more, see ', style={'display': 'inline-block'}), 
        #     html.Div('.', style={'display':'inline-block', 'visibility': 'hidden'}),
        #     html.A('www.commerce.gov', href='https://www.commerce.gov', style={'display':'inline-block'}), 
        #     html.Div('.', style={'display':'inline-block', 'visibility': 'hidden'}),
        #     html.Div('.', style={'display':'inline-block'})], style={'display':'inline-block'}),
        page_container,
        ddk.PageFooter(children=[                    
            html.Hr(),
            ddk.Block(children=[
                ddk.Block(width=.3, children=[
                    html.Div(children=[
                        dcc.Link('National Oceanic and Atmospheric Administration',
                                href='https://www.noaa.gov/', style={'font-size': '.8em'}),
                    ]),
                    html.Div(children=[
                        dcc.Link('Pacific Marine Environmental Laboratory',
                                href='https://www.pmel.noaa.gov/',style={'font-size': '.8em'}),
                    ]),
                    html.Div(children=[
                        dcc.Link('oar.pmel.webmaster@noaa.gov', href='mailto:oar.pmel.webmaster@noaa.gov', style={'font-size': '.8em'})
                    ]),
                    dcc.Link('DOC |', href='https://www.commerce.gov/', style={'font-size': '.8em'}),
                    dcc.Link(' NOAA |', href='https://www.noaa.gov/', style={'font-size': '.8em'}),
                    dcc.Link(' OAR |', href='https://www.research.noaa.gov/', style={'font-size': '.8em'}),
                    dcc.Link(' PMEL |', href='https://www.pmel.noaa.gov/', style={'font-size': '.8em'}),
                    dcc.Link(' Privacy Policy |', href='https://www.noaa.gov/disclaimer', style={'font-size': '.8em'}),
                    dcc.Link(' Disclaimer |', href='https://www.noaa.gov/disclaimer',style={'font-size': '.8em'}),
                    dcc.Link(' Accessibility', href='https://www.pmel.noaa.gov/accessibility',style={'font-size': '.8em'})
                ]),
                ddk.Block(width=.7,children=[html.Img(src=app.get_asset_url('pmel-lockup-rgb-2022.png'), style={'height': '90px'})])
            ])
        ])
    ]),

])


if __name__ == '__main__':
    app.run_server(debug=True)
