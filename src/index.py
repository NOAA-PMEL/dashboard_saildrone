# -*- coding: utf-8 -*-
"""Simple page to show links to all the available dashboards.
"""

import dash
from dash import Dash, callback, html, dcc, dash_table, Input, Output, State, MATCH, ALL
import dash_bootstrap_components as dbc

app = dash.Dash(__name__,
                suppress_callback_exceptions=True,
                external_stylesheets=[dbc.themes.BOOTSTRAP],
                # requests_pathname_prefix='/dashboard/wsm/'
                )
app._favicon = 'favicon.ico'

server = app.server  # expose server variable for Procfile

application = app.server

app.layout = html.Div(style={'paddingLeft': '15px', 'paddingRight': '25px'}, children=[
    dbc.Navbar(
        [
            dbc.Row(style={'width': '100%'},
                    align="center",
                    # no_gutters=True,
                    children=[
                        dbc.Col(width=8, children=[
                            dbc.Row(id='header-items', children=[
                                dbc.Col(width=4, children=[
                                    html.Img(src='https://www.pmel.noaa.gov/sites/default/files/pmel_logo_full.png',
                                             style={'height': '79px', 'width': '407px'})]),
                                dbc.Col(width=8, style={'display': 'flex', 'alignItems': 'center'}, children=[
                                    html.A(
                                        dbc.NavbarBrand('PMEL Data Dashboards', className="ml-2",
                                                        style={'paddingTop': '160px',
                                                               'fontSize': '2.5em',
                                                               'fontWeight': 'bold'}),
                                        href='https://www.pmel.noaa.gov/', style={'textDecoration': 'none'}
                                    )
                                ]
                                        )
                            ]),
                        ])
                    ])
        ]),
    dbc.Row(children=[
        dbc.Col(width=4, style={'margin': '10px'}, children=[
            html.A(style={'display': 'inline', 'textDecoration': 'none'}, children=[
                html.Img(height=300, width=450, src='assets/saildrone.png')
            ], href='dashboard/saildrone/')
        ]),
        dbc.Col(width=4, style={'display': 'flex', 'align-items': 'center'},
                children=[
                    html.A(style={'display': 'inline', 'textDecoration': 'none'},
                           children=[
                               html.H3(children=['All current saildrone missions']),
                           ], href='dashboard/saildrone/')
                ])
    ]),
    dbc.Row(children=[
        dbc.Col(width=4, style={'margin': '10px'}, children=[
            html.A(style={'display': 'inline', 'textDecoration': 'none'}, children=[
                html.Img(height=300, width=450, src='assets/wsm.png')
            ], href='dashboard/wsm/')
        ]),
        dbc.Col(width=4, style={'display': 'flex', 'align-items': 'center'},
                children=[
                    html.A(style={'display': 'inline', 'textDecoration': 'none'},
                           children=[
                               html.H3(children=['2021 Hurricane Mission']),
                           ], href='dashboard/wsm/')
                ])
    ]),
    dbc.Row(children=[
        dbc.Col(width=4, style={'margin': '10px'}, children=[
            html.A(style={'display': 'inline', 'textDecoration': 'none'}, children=[
                html.Img(height=300, width=450, src='assets/osites.png')
            ], href='dashboard/oceansites/')
        ]),
        dbc.Col(width=4, style={'display': 'flex', 'align-items': 'center'},
                children=[
                    html.A(style={'display': 'inline', 'textDecoration': 'none'},
                           children=[
                               html.H3(children=['OceanSITES Flux Data']),
                           ], href='dashboard/oceansites/')
                ])
    ]),
    dbc.Row(style={'marginBottom': '10px'}, children=[
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
                        html.Div(style={'fontSize': '1.0em', 'position': 'absolute', 'bottom': '0'},
                                 children=['1.0'])
                    ])
                ])
            ])
        ]),
        html.Div(id='data-div', style={'display': 'none'})
    ])
])

if __name__ == '__main__':
    app.run_server(debug=True)
