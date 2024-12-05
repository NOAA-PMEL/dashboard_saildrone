import dash
from dash import html, dcc, callback, exceptions, Input, Output, State, no_update, callback_context
import dash_design_kit as ddk
import plotly.graph_objects as go
import plotly.express as px
import json
import constants
import db
import urllib
from itertools import filterfalse
import pandas as pd
from plotly.subplots import make_subplots
import datetime
import numpy as np
import sdig.util.zc as zc
from sdig.erddap.info import Info
import time
import dash_bootstrap_components as dbc


height_of_row = 345
short_map_height = 450
tall_map_height = 800

line_rgb = 'rgba(.04,.04,.04,.05)'
plot_bg = 'rgba(1.0, 1.0, 1.0 ,1.0)'

d_format = "%Y-%m-%d"
mission_start_seconds = None
mission_end_seconds = None

def get_blank(message):
    blank_graph = go.Figure(go.Scatter(x=[0, 1], y=[0, 1], showlegend=False))
    blank_graph.add_trace(go.Scatter(x=[0, 1], y=[0, 1], showlegend=False))
    blank_graph.update_traces(visible=False)
    blank_graph.update_layout(
        xaxis={"visible": False},
        yaxis={"visible": False},
        annotations=[
            {
                "text": message,
                "xref": "paper",
                "yref": "paper",
                "showarrow": False,
                "font": {
                    "size": 14
                }
            },
        ]
    )
    return blank_graph
blank_graph = get_blank('Pick one or more drones<br>Pick a variable')

dash.register_page(__name__, path="/mission", path_template='/mission/<mission_id>')

def layout(mission_id=None, **params):
    if mission_id is None:
        return html.Div('')
    mission  = json.loads(constants.redis_instance.hget("mission", mission_id))
    df = db.get_mission_locations(mission_id, mission['dsg_id'])
    
    mode = 'lines'
    if 'mode' in params:
        mode = params['mode']

    q_plots_per = 'all'
    if 'plots_per' in params:
        q_plots_per = params['plots_per']

    if q_plots_per == 'one':
        check_plots_per = ['one']
    else:
        check_plots_per = []

    req_drones = []
    if 'drone' in params:
        req_drones = params['drone']

    trace_decimation = 24
    if 'trace_decimation' in params:
        trace_decimation_params = params['trace_decimation']
        trace_decimation = trace_decimation_params

    plots_decimation = 24
    if 'plots_decimation' in params:
        plots_decimation_params = params['plots_decimation']
        plots_decimation = plots_decimation_params

    trace_variable = None
    if 'trace_variable' in params:
        trace_variable_params = params['trace_variable']
        trace_variable = trace_variable_params

    plot_variables = []
    if 'timeseries' in params:
        plot_variables = params['timeseries']
        if isinstance(plot_variables, str):
            plot_variables = [plot_variables]

    if 'start_date' in params:
        set_start_date = params['start_date']
    else:
        set_start_date = df.time.min()
        
    # Make sure you cover the rest of the last day.

    if 'end_date' in params:
        set_end_date = params['end_date']
    else:
        set_end_date = df.time.max()
        sed = datetime.datetime.strptime(set_end_date, '%Y-%m-%dT%H:%M:%SZ')
        sed = sed + datetime.timedelta(hours=36)
        set_end_date = sed.strftime(d_format)
        
    mission_start_date = df.time.min()
    sd = datetime.datetime.strptime(mission_start_date, '%Y-%m-%dT%H:%M:%SZ')
    mission_start_seconds = sd.timestamp()
    mission_start_date = sd.strftime(d_format)
    mission_end_date = df.time.max()
    ed = datetime.datetime.strptime(mission_end_date, '%Y-%m-%dT%H:%M:%SZ')
    ed = ed + datetime.timedelta(hours=36)
    mission_end_seconds = ed.timestamp()
    mission_end_date = ed.strftime(d_format)


    time_marks = Info.get_time_marks(mission_start_seconds, mission_end_seconds)

    if 'columns' in params:
        set_max_columns = params['columns']
    else:
        if 'max_columns' in mission['ui']:
            set_max_columns = str(mission['ui']['max_columns'])
        else:
            set_max_columns = 4

    # Sort dict by value
    variable_options = []
    trace_variable_options = [{'label':'Daily Location', 'value':'location'}]
    trace_variable = 'location'
    m_long_names = mission['long_names']
    for var in m_long_names:
        variable_options.append({'label':m_long_names[var], 'value': var})
        trace_variable_options.append({'label':m_long_names[var], 'value': var})
    
    drones_selected = []
    drone_options = []
    for drone in mission['drones']:
        drone_options.append({'label': mission['drones'][drone]['label'], 'value': drone})
        drones_selected.append(drone)

    if len(req_drones) == 0:
        req_drones = drones_selected

    logo_card = []
    logos = []
    downloads = {'display': 'none'}
    if 'downloads' in mission:
        if mission['downloads'] == 'true':
            downloads = {'display': ''}
    if 'logo' in mission['ui']:
        logo_img = mission['ui']['logo']
        if not logo_img.startswith("http"):
            logo_img = constants.assets + logo_img
        style = {'max-width':'100%'}
        if 'logo_bgcolor' in mission['ui']:
            style['background-color'] = mission['ui']['logo_bgcolor']
        logo = html.A(
                html.Img(style=style,
                    src=logo_img
                )
            )
        if 'href' in mission['ui']:
            logo.href = mission['ui']['href']
            logo.target='_blank'
        logos.append(logo)
    if 'link_text' in mission['ui'] and 'href' in mission['ui']:
        text = html.A(mission['ui']['link_text'], href = mission['ui']['href'], target='_blank')
        logos.append(text)
    if len(logos) > 0:
        logo_card = ddk.Card(children=logos,)
    df.sort_values(['trajectory', 'time'], inplace=True)
    mission_title = mission['ui']['title']

    if mission_id is None:
        raise exceptions.PageError
    else:
        layout = ddk.Block([
            ddk.Row([
                ddk.Card(width=1.0, children=[
                        html.Div(mission_title, style={'fontSize': '1.5em'}),
                ]),
            ]),
            ddk.Row([
                ddk.Block(width=.1, children=[
                    ddk.ControlCard(children=[
                        ddk.CardHeader(title='Date Range and Drone Selection for all Plots'),
                        ddk.ControlItem(label='Date Range:', children=[
                            ddk.Block(width=.5, children=[
                                dcc.Input(id='start-date', debounce=True, value=mission_start_date),
                            ]),
                            ddk.Block(width=.5, children=[
                                dcc.Input(id='end-date', debounce=True, value=mission_end_date),
                            ]),
                        ]),
                        ddk.ControlItem(children=[
                            html.Div(style={
                                'padding-right': '10px', 
                                'padding-left': '10px', 
                                'padding-top': '20px', 
                                'padding-bottom': '0px'}, 
                            children=[
                                    dcc.RangeSlider(id='time-range-slider',
                                                    value=[mission_start_seconds, mission_end_seconds],
                                                    min=mission_start_seconds,
                                                    max=mission_end_seconds,
                                                    step=constants.day_step,
                                                    marks=time_marks,
                                                    updatemode='mouseup',
                                                    allowCross=False)
                            ])
                        ]),
                        ddk.ControlItem(label='Drones: ', children=[
                            dcc.Dropdown(
                                id='drone', 
                                multi=True, 
                                clearable=True, 
                                options=drone_options, 
                                placeholder='Select one or more drones to plot.',
                                value=req_drones
                            ),
                        ]),
                    ]),
                    ddk.ControlCard(children=[
                        ddk.CardHeader(title='Data Download'),
                        ddk.ControlItem(label="Full resolution of variables shown in timeseries plot:", children=[
                             html.Button("Download", id='download', disabled=True)
                        ])
                    ])
                ]),
                ddk.Block(width=.4,children=[
                    ddk.Card(children=[
                        ddk.ControlCard(orientation='horizontal', children=[
                            ddk.ControlItem(width=70, children=[
                                dcc.Dropdown(id='trace-variable', 
                                    multi=False, 
                                    clearable=False, 
                                    options=trace_variable_options, 
                                    placeholder='Variable for trajectory plot',
                                    value=trace_variable,
                                )],
                            ),
                            ddk.ControlItem(width=30, children=[
                                dcc.Dropdown(id='trace-decimation',
                                    style=constants.HIDDEN,
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
                                    value=str(trace_decimation)
                                )],
                            )
                        ]),
                        dcc.Loading(ddk.Graph(id='trajectory-map'))
                    ])   
                ])
            ]),

            ddk.Row([
                ddk.Card(children=[
                    ddk.ControlCard(orientation='horizontal', children=[
                            ddk.ControlItem(width=30, children=[
                                dcc.Dropdown(
                                    id='plot-variables', 
                                    multi=True, 
                                    clearable=True, 
                                    options=variable_options, 
                                    placeholder='Select variables for timeseries plots.',
                                    value=plot_variables
                                ),
                            ]),
                            ddk.ControlItem(width=20, children=[
                                dcc.Checklist(id='plots-per', options=[{'label': 'One plot per drone', 'value': 'one'}], value=check_plots_per) 
                            ]),
                            ddk.ControlItem(width=20, children=[
                                dcc.Dropdown(
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
                                    value=str(plots_decimation)
                                ),
                            ]),
                            ddk.ControlItem(width=10, children=[
                                dcc.Dropdown(
                                    id='plots-mode',
                                    options=[
                                        {'label': 'Markers', 'value': 'markers'},
                                        {'label': 'Lines', 'value': 'lines'},
                                        {'label': 'Both', 'value': 'both'},
                                    ],
                                    multi=False,
                                    clearable=False,
                                    placeholder='Line mode',
                                    value=mode
                                ),
                            ]),
                            ddk.ControlItem(width=15, children=[
                                dcc.Dropdown(
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
                                    value=set_max_columns
                                ),
                            ])
                        
                    ]),
                    html.Progress(id="progress-bar", value="0", style={'visibility':'hidden', 'width':'100%'}),
                    dcc.Loading(ddk.Graph(id='timeseries-plots', figure=blank_graph))
                ])
            ]),
            dbc.Modal(id='download-dialog', children=[
                dbc.ModalHeader(children=['Download links for the drones show in the timeseries plot:']),
                dbc.ModalBody(id='download-links', children="some links"),
                dbc.ModalFooter(dbc.Button("Close", id="close", className="ml-auto")),
            ])
        ])
        return layout



@callback(
    [
        Output('download-dialog', 'is_open'),
        Output('download-links', 'children')
    ],
    [
        Input('download', 'n_clicks'),
        Input('close', 'n_clicks')
    ]
)
def open_download_dialog(open_click, close_click):
    if callback_context.triggered_id is None:
        return [False, dash.no_update]
    if "close" in callback_context.triggered_id:
        return [False, dash.no_update]
    download_s = constants.redis_instance.hget("downloads", "urls")
    thead = html.Thead(html.Tr([html.Th("Saildrone"), html.Th("CSV"), html.Th("HTML"), html.Th("netCDF")]))
    body_rows = []
    if download_s is not None and len(download_s) > 0 and 'download' in callback_context.triggered_id:
        download_dict = json.loads(download_s)
        for drone_down in download_dict:
            csv_url = download_dict[drone_down]
            html_url = csv_url.replace('.csv', '.htmlTable')
            netcdf_url = csv_url.replace('.csv', '.ncCF')
            row = html.Tr(
                    [
                        html.Td(drone_down, style={"width":"25%"}), 
                        html.Td(dcc.Link('.csv', href=csv_url, target='_blank'), style={"width":"25%"}), 
                        html.Td(dcc.Link('.html', href=html_url, target='_blank'), style={"width":"25%"}), 
                        html.Td(dcc.Link('.ncCF', href=netcdf_url, target='_blank'), style={"width":"25%"})
                    ]
                )
            body_rows.append(row)
        table = html.Table(children=[thead, html.Tbody(children=body_rows)], style={"width":"100%"})
        return [True, table]
    else:
        return [False, dash.no_update]


@callback(
[
    Output('url', 'search'),
    Output('url', 'refresh')
],[
    Input('drone', 'value'),
    Input('trace-decimation', 'value'),
    Input('trace-variable', 'value'),
    Input('plots-decimation', 'value'),
    Input('plot-variables', 'value'),
    Input('start-date', 'value'),
    Input('end-date', 'value'),
    Input('plots-columns', 'value'),
    Input('plots-mode', 'value'),
    Input('plots-per', 'value'),
],[
    State('url', 'search')
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
               state_search
            ):
    
    if state_search is not None:
        state_params = urllib.parse.parse_qs(state_search[1:])
    
    if 'mission_id' in state_params:
        # I don't know how we would get here without this being set
        mission_id = state_params['mission_id']
        s = '?mission_id=' + mission_id[0]


    if drone is not None:
        if isinstance(drone, list):
            for d in drone:
                s = s + '&drone=' + d
        elif isinstance(drone, str):
            # if drone in check_mission_drones:
            s = s + '&drone=' + drone
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
        return [s, False]


@callback([
    Output('trace-trigger', 'data'),
    Output('trace-decimation', 'style')
], [
    Input('drone', 'value'),
    Input('trace-decimation', 'value'),
    Input('trace-variable', 'value'),
    Input('start-date', 'value'),
    Input('end-date', 'value')
], [
    State('url', 'search')
]
)
def set_trace_data(drone, trace_decimation, trace_variable, selected_start_date, selected_end_date, state_search):

    # Bail immediately if you don't have drones or you don't have a variable to plot
    if drone is None:
        raise exceptions.PreventUpdate
    if trace_variable is None:
        raise exceptions.PreventUpdate

    if len(drone) == 0:
        raise exceptions.PreventUpdate
    
    if len(trace_variable) == 0:
        raise exceptions.PreventUpdate

    if state_search is not None:
        state_params = urllib.parse.parse_qs(state_search[1:])
        
    if 'mission_id' in state_params:
        # I don't know how we would get here without this being set
        cur_id = state_params['mission_id'][0]

    trace_config = {'config': {}}
    drones_selected = []
    check_mission_drones = []

    if cur_id is not None:
        cur_mission = json.loads(constants.redis_instance.hget("mission", cur_id))
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
        trace_config['config']['drones'] = drones_selected

    if trace_decimation is None:
        trace_decimation = "24"
    trace_config['config']['trace_decimation'] = trace_decimation

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
    constants.redis_instance.hset("saildrone", "trace_config", json.dumps(trace_config))

    if trace_variable == 'location':
        visibility = constants.HIDDEN
    else:
        visibility = constants.VISIBLE
    return ['go', visibility]


@callback([
    Output('trajectory-map', 'figure'),
], [
    Input('trace-trigger', 'data'),
], [
    State('url', 'search')
], prevent_initial_call=True, background=True)
def make_trajectory_trace(trace_config, state_search):
    if trace_config is None:
        raise dash.exceptions.PreventUpdate
    elif len(trace_config) == 0:
        raise dash.exceptions.PreventUpdate

    if state_search is not None:
        state_params = urllib.parse.parse_qs(state_search[1:])
        
    if 'mission_id' in state_params:
        # I don't know how we would get here without this being set
        cur_mission_id = state_params['mission_id'][0]


    if cur_mission_id is None:
        raise dash.exceptions.PreventUpdate
    elif len(cur_mission_id) == 0:
        raise dash.exceptions.PreventUpdate

    the_cur_mission = json.loads(constants.redis_instance.hget("mission", cur_mission_id))

    trace_decimation = 24
    trace_start_date = None
    trace_end_date = None

    trace_json = json.loads(constants.redis_instance.hget("saildrone", "trace_config"))
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

    if 'location' in trace_variable:
        df = db.get_mission_locations(cur_mission_id, the_cur_mission['dsg_id'])
        # Trim the locations by time and selected drones
        df = df.loc[df['time']>=trace_start_date]
        df = df.loc[df['time']<=trace_end_date]
        df = df.loc[df[the_cur_mission['dsg_id']].isin(pdrones)]
        # this is a special plot of only the locations of the drones
        drone_map = px.scatter_geo(
            df, 
            lat='latitude', 
            lon='longitude', 
            color='trajectory', 
            fitbounds='locations', 
            hover_data=['time'], 
            color_discrete_sequence=px.colors.qualitative.Dark24,
            title='Daily locations of each mission drone.'
        )
        drone_map.update_geos(
            resolution=50,
            showcoastlines=True, coastlinecolor="Black",
            showland=True, landcolor="Tan",
            showocean=True, oceancolor="LightBlue",
        )
        drone_map.update_layout(
            margin={"r":0,"t":60,"l":0,"b":0}, 
            legend_title_text='Drone',
            legend_orientation='v',
            legend_x=constants.legend_location,
        )
        return [drone_map]


    if 'time' not in trace_variable:
        trace_variable.append('time')

    
    cur_drones = the_cur_mission['drones']
    cur_long_names = the_cur_mission['long_names']
    cur_units = the_cur_mission['units']

    if 'latitude' not in trace_variable:
        trace_variable.append('latitude')
    if 'longitude' not in trace_variable:
        trace_variable.append('longitude')
    if 'trajectory' not in trace_variable:
        trace_variable.append('trajectory')
    req_var = ",".join(trace_variable)

    order_by = '&orderBy("time")'
    if trace_decimation > 0:
        order_by = '&orderByClosest("time/' + str(trace_decimation) + 'hours")'
    if trace_start_date is not None:
        order_by = order_by + '&time>=' + trace_start_date
    #if trace_end_date is not None and 'seatrial' not in cur_mission_id:
    if trace_end_date is not None:
        if '00:00:00' in trace_end_date:
            trace_end_date = trace_end_date.replace('00:00:00', "23:59:59")
        order_by = order_by + '&time<=' + trace_end_date
    data_tables = []
    for drone_id in pdrones:
        base_url = cur_drones[drone_id]['url'] + '.csv?'
        traj_query = '&trajectory="' + drone_id + '"' + order_by
        encoded_query = urllib.parse.quote(traj_query, safe='&()=:/')
        tr_drone_url = base_url + req_var + encoded_query
        try:
            d_df = pd.read_csv(tr_drone_url, skiprows=[1])
            data_tables.append(d_df)
        except Exception as ex:
            print('Trajectory plot: exception getting data from url: ' + tr_drone_url)
            print('e=' + str(ex))
            continue

    if len(data_tables) == 0:
        return [get_blank('No data for this combination of selections.')]

    df = pd.concat(data_tables)

    if df.shape[0] < 3:
        return [get_blank('No data available for this combination of selections.')]

    df = df[df[trace_variable[0]].notna()]
    df.loc[:, 'text_time'] = df['time'].astype(str)
    df.loc[:, 'millis'] = pd.to_datetime(df['time']).view(np.int64)
    df.loc[:, 'text'] = df['text_time'] + "<br>" + df['trajectory'].astype(str) + "<br>" + trace_variable[0] + '=' + df[
        trace_variable[0]].astype(str)
    plot_var = trace_variable[0]
    name_var = trace_variable[0]
    color_scale = 'inferno'
    cb_title = cur_long_names[name_var]
    if name_var in cur_units:
        cb_title = cb_title + ' (' + cur_units[name_var] + ')'
    color_bar_opts = dict(x=-.15, title=cb_title, title_side='right')
    if plot_var == 'time':
        plot_var = 'millis'
        name_var = 'Date/Time'
        color_scale = 'cividis_r'
        color_bar_opts = dict(x=-.15, title=name_var, ticktext=[df['text_time'].iloc[0], df['text_time'].iloc[-1]],
                              tickvals=[df['millis'].iloc[0], df['millis'].iloc[-1]])
    zoom, center = zc.zoom_center(lons=df['longitude'], lats=df['latitude'])
    annotation = None
    if df.shape[0] > 25000:
        df = df.sample(n=25000).sort_values(by=['time', 'trajectory'], ascending=True)
        annotation = 'Sub-sampled to 25,000 points.'
    location_trace = go.Figure(go.Scattermap(lat=df["latitude"], lon=df["longitude"],
                                      text=df['text'],
                                      marker=dict(showscale=True, color=df[plot_var],
                                                  colorscale=color_scale, size=8,
                                                  colorbar=color_bar_opts, 
                                                )
                                ))
    if annotation is not None:
        location_trace.add_annotation(text=annotation,
                  xref="paper", yref="paper",
                  x=0.01, y=0.01, showarrow=False)                           
    location_trace.update_layout(
        height=short_map_height, margin={"r": 0, "t": 0, "l": 0, "b": 0},
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
    
    location_trace.update_geos(fitbounds='locations',
                               showcoastlines=True, coastlinecolor="RebeccaPurple",
                               showland=True, landcolor="LightGreen",
                               showocean=True, oceancolor="Azure",
                               showlakes=True, lakecolor="Blue", projection=dict(type="mercator"),
                               )
    ct = datetime.datetime.now()
    
    print('At ' + str(ct) + ' plotting trajectory of ' + str(trace_variable[0]) + ' for ' + str(pdrones) + ' from ' + the_cur_mission['ui']['title'])
    return [location_trace]


@callback([
    Output('plots-trigger', 'data'),
], [
    Input('drone', 'value'),
    Input('plots-decimation', 'value'),
    Input('plot-variables', 'value'),
    Input('start-date', 'value'),
    Input('end-date', 'value'),
    Input('plots-columns', 'value'),
    Input('plots-mode', 'value'),
    Input('plots-per', 'value'),
], [
    State('url', 'search')
]
)
def set_plots_data(drone, plots_decimation, plot_variables, selected_start_date, selected_end_date, columns, mode, plots_per, state_search):

    if drone is None:
        raise exceptions.PreventUpdate
    if plot_variables is None:
        raise exceptions.PreventUpdate

    if len(drone) == 0:
        raise exceptions.PreventUpdate
    
    if len(plot_variables) == 0:
        raise exceptions.PreventUpdate

    if state_search is not None:
        state_params = urllib.parse.parse_qs(state_search[1:])
        
    if 'mission_id' in state_params:
        # I don't know how we would get here without this being set
        cur_id = state_params['mission_id'][0]

    plots_config = {'config': {}}

    if mode is None:
        mode = 'lines'
    plots_config['config']['mode'] = mode
    if columns is None:
        columns = max_columns
    plots_config['config']['columns'] = columns
    drones_selected = []
    check_mission_drones = []

    if cur_id is not None:
        cur_mission = json.loads(constants.redis_instance.hget("mission", cur_id))
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
    else:
        raise exceptions.PreventUpdate

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
    
    if isinstance(plot_variables, list):
        if len(plot_variables) > 0:
            plots_config['config']['timeseries'] = plot_variables
        else:
            raise exceptions.PreventUpdate
    else:
        if len(plot_variables) > 0:
            plots_config['config']['timeseries'] = [plot_variables]
        else:
            raise exceptions.PreventUpdate

    if selected_start_date is not None:
        if len(selected_start_date) > 0:
            plots_config['config']['start_date'] = selected_start_date
    if selected_end_date is not None:
        if len(selected_end_date) > 0:
            plots_config['config']['end_date'] = selected_end_date

    constants.redis_instance.hset("saildrone", "plots_config", json.dumps(plots_config))
    return ['go']


@callback(
    Output('timeseries-plots', 'figure'),
    Output('download', 'disabled'),
    Input('plots-trigger', 'data'),
    State('url', 'search'),
    background=True,
    running=[
        (
            Output("progress-bar", "style"),
            {"visibility": "visible", "width":"100%"},
            {"visibility": "hidden", "widht": "100%"},
        ),
    ],
    progress=[Output("progress-bar", "value"), Output("progress-bar", "max")],
    prevent_initial_call=True,    
)
def make_plots(set_progress, trigger, state_search):
    # TIMING
    # start = time.perf_counter()
    set_progress(("0","0"))
    if state_search is not None:
        state_params = urllib.parse.parse_qs(state_search[1:])
    
    if 'mission_id' in state_params:
        # I don't know how we would get here without this being set
        cur_mission_id = state_params['mission_id'][0]

    plots = get_blank('Trouble downloading data. Try again, maybe with fewer data points.')
    # DEBUG print('Set blank plot')
    num_columns = 3;
    plots_decimation = 24
    plots_start_date = None
    plots_end_date = None

    plots_config = json.loads(constants.redis_instance.hget("saildrone", "plots_config"))
    # DEBUG print('plots config loaded')
    # must have a drone, and a variable
    if 'drones' in plots_config['config']:
        tsdrones = plots_config['config']['drones']
    else:
        return [blank_graph, True]

    if 'timeseries' in plots_config['config']:
        plot_variables = plots_config['config']['timeseries']
        original_order = plot_variables.copy()
        if len(plot_variables) == 0:
            return [blank_graph, True]
    else:
        return [blank_graph, True]
    max_progress = (len(tsdrones)*len(plot_variables)) + 2
    progress = 1
    set_progress((str(progress), str(max_progress)))

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

    the_mission_config = json.loads(constants.redis_instance.hget("mission", cur_mission_id))
    # DEBUG print('mission config loaded')
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
        order_by = '&orderByClosest("time/' + str(plots_decimation) + 'hours")'
    # hack for now because there's only one day
    download_time_con_start = ''
    if plots_start_date is not None:
        order_by = order_by + '&time>=' + plots_start_date
        download_time_con_start = '&time>=' + plots_start_date
    #if plot_end_date is not None and 'seatrial' not in cur_mission_id:
    download_time_con_end = ''
    if plots_end_date is not None:
        if '00:00:00' in plots_end_date:
            plots_end_date = plots_end_date.replace('00:00:00', '23:59:59')
        order_by = order_by + '&time<=' + plots_end_date
        download_time_con_end = '&time<=' + plots_end_date
    # TIMING
    # setup_over = time.perf_counter()
    # setup_time = setup_over - start
    download_urls = {}
    plot_data_tables = []
    for d_ts in tsdrones:
        drone_plot_variables = plot_variables.copy()
        for plot_var in plot_variables:
            if plot_var not in cur_drones[d_ts]['variables']:
                drone_plot_variables.remove(plot_var)
                
        req_var = ",".join(drone_plot_variables)
        url_base = cur_drones[d_ts]['url'] + '.csv?'
        query = '&trajectory="' + d_ts + '"' + order_by
        q = urllib.parse.quote(query, safe='&()=:/')
        full_query = '&trajectory="' + d_ts + '"'
        fq = urllib.parse.quote(full_query, safe='&()=:/')
        drone_url = url_base + req_var + q
        download_urls[d_ts] = url_base + req_var + fq + download_time_con_start + download_time_con_end
        try:
            # DEBUG print('reading drone data from ' + drone_url)
            ts_df = pd.read_csv(drone_url, skiprows=[1], parse_dates=['time'])
            plot_data_tables.append(ts_df)
            progress = progress + 1
            set_progress((str(progress), str(max_progress)))
        except Exception as e:
            print('Timeseries plots: exception getting data from ' + drone_url)
            print('e=', str(e))
            continue
    constants.redis_instance.hset("downloads", "urls", json.dumps(download_urls))
    if len(plot_data_tables) == 0:
        return [get_blank('No data for this combination of selections.'), True]
    df = pd.concat(plot_data_tables)
    if df.shape[0] < 3:
        return [get_blank('No data for this combination of selections.'), True]
    df['trajectory'] = df['trajectory'].astype(str)
    colnames = list(df.columns)
    df.loc[:, 'text_time'] = df['time'].astype(str)
    annotation = None
    sub_title = ''
    if df.shape[0] > 25000:
        annotation = 'All timeseries plots sub-sampled to 25,000 total points each.'
        df = df.sample(n=25000).sort_values(by=['time', 'trajectory'], ascending=True)
    subplots = {}
    titles = {}
    # DEBUG print('finished subsample')
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
    # TIMING
    # data_read_over = time.perf_counter()
    # data_read_time = data_read_over - setup_over
    colnames.remove('latitude')
    colnames.remove('longitude')
    colnames.remove('time')
    colnames.remove('trajectory')
    mode = 'lines'
    if 'mode' in plots_config['config']:
        mode = plots_config['config']['mode']
    if mode == 'both':
        mode = 'lines+markers'
    legend_count = 0
    for var in original_order:
        if var in df.columns.to_list():
            dfvar = df[['time', 'text_time', 'trajectory', var]].copy()
            # dfvar.loc[:, 'text_time'] = dfvar['time'].astype(str)
            dfvar.loc[:, 'time'] = pd.to_datetime(dfvar['time'])
            dfvar.dropna(subset=[var], how='all', inplace=True)
            if dfvar.shape[0] > 2:
                subtraces = []
                for drn in tsdrones:
                    index = sorted(list(cur_drones.keys())).index(drn)
                    n_color = px.colors.qualitative.Dark24[index % 24]
                    dfvar_drone = dfvar.loc[(dfvar['trajectory'] == drn)]
                    if plots_decimation > 0 and dfvar_drone.shape[0] > 3:
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
                    dfvar_drone = dfvar_drone.sort_values(by=['time', 'trajectory'], ascending=True)
                    show_legend=True
                    if legend_count > 0:
                        show_legend=False
                    varplot = go.Scattergl(x=dfvar_drone['time'], y=dfvar_drone[var], name=drn,
                                        marker={'color': n_color},
                                        mode=mode, hoverinfo='x+y+name', showlegend=show_legend, legendgroup=drn)
                    progress = progress + 1
                    set_progress((str(progress), str(max_progress)))
                    subtraces.append(varplot)
                    # DEBUG print('plotting ' + str(drn))
                legend_count = legend_count+1
                subplots[var] = subtraces
                title = var + sub_title
                if var in cur_long_names:
                    title = cur_long_names[var] + sub_title

                if var in cur_units:
                    title = title + ' (' + cur_units[var] + ')'
                titles[var] = title

    if plots_per == 'all':
        num_plots = len(subplots)
    else:
        num_plots = len(subplots) * len(tsdrones)
    if num_plots == 0:
        return [get_blank('No data for this combination of selections.'), True]
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
            legend_count = legend_count + 1
            if plots_per == 'all':
                plot_index = plot_index + 1
                if plot_index > 1:
                    if col == num_columns:
                        row = row + 1
                col = plot_index % num_columns
                if col == 0:
                    col = num_columns
            # DEBUG print('adding subplot')
            plots.update_xaxes({'showticklabels': True, 'gridcolor': line_rgb})
            plots.update_yaxes({'gridcolor': line_rgb})
            # Position the one and only legend that controls all the plots
            plots.layout['legend']={'yref': 'paper', 'y': 1.3, 'xref': 'paper', 'x': .1, 'orientation': 'h'}

    plots['layout'].update(height=graph_height, margin=dict(l=80, r=80, b=80, t=80, ))
    if annotation is not None:
        plots.add_annotation(text=annotation,
                    xref="paper", yref="paper",
                    x=0.01, y=1.3, showarrow=False)  

    progress = progress + 1
    set_progress((str(progress), str(max_progress)))
    ct = datetime.datetime.now()

    # TIMING 
    # end = time.perf_counter()
    # plotting_time = end - data_read_over
    # total_time = end-start
    # try:
    #     with open("/workspace/timing.csv", "a") as time_file:
    #         timings = str(len(original_order))+','+str(len(tsdrones))+','+str(setup_time)+','+str(data_read_time)+','+str(plotting_time)+','+str(total_time)+'\n'
    #         time_file.write(timings)
    # except Exception as e:
    #     print(str(e))

    print('At ' + str(ct) + ' plotting timeseries of ' + str(colnames) + ' for ' + str(tsdrones) + ' from ' + the_mission_config['ui']['title'])
    set_progress(("0", "0"))
    return [plots, False]



@callback(
    [
        Output('time-range-slider', 'value', allow_duplicate=True),
        Output('start-date', 'value'),
        Output('end-date', 'value')
    ],
    [
        Input('time-range-slider', 'value'),
        Input('start-date', 'value'),
        Input('end-date', 'value'),
    ], prevent_initial_call=True
)
def set_date_range_from_slider(slide_values, in_start_date, in_end_date,):
    if slide_values is None:
        raise exceptions.PreventUpdate

    range_min = mission_start_seconds
    range_max = mission_end_seconds

    ctx = callback_context
    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]

    start_seconds = slide_values[0]
    end_seconds = slide_values[1]

    start_output = in_start_date
    end_output = in_end_date

    if trigger_id == 'start-date':
        try:
            in_start_date_obj = datetime.datetime.strptime(in_start_date, d_format)
        except:
            in_start_date_obj = datetime.datetime.fromtimestamp(start_seconds)
        start_output = in_start_date_obj.date().strftime(d_format)
        start_seconds = in_start_date_obj.timestamp()
        if start_seconds < range_min:
            start_seconds = range_min
            in_start_date_obj = datetime.datetime.fromtimestamp(start_seconds)
            start_output = in_start_date_obj.date().strftime(d_format)
        elif start_seconds > range_max:
            start_seconds = range_max
            in_start_date_obj = datetime.datetime.fromtimestamp(start_seconds)
            start_output = in_start_date_obj.date().strftime(d_format)
        elif start_seconds > end_seconds:
            start_seconds = end_seconds
            in_start_date_obj = datetime.datetime.fromtimestamp(start_seconds)
            start_output = in_start_date_obj.date().strftime(d_format)
    elif trigger_id == 'end-date':
        try:
            in_end_date_obj = datetime.datetime.strptime(in_end_date, d_format)
        except:
            in_end_date_obj = datetime.datetime.fromtimestamp((end_seconds))
        end_output = in_end_date_obj.date().strftime(d_format)
        end_seconds = in_end_date_obj.timestamp()
        if end_seconds < range_min:
            end_seconds = range_min
            in_end_date_obj = datetime.datetime.fromtimestamp(end_seconds)
            end_output = in_end_date_obj.date().strftime(d_format)
        elif end_seconds > range_max:
            end_seconds = range_max
            in_end_date_obj = datetime.datetime.fromtimestamp(end_seconds)
            end_output = in_end_date_obj.date().strftime(d_format)
        elif end_seconds < start_seconds:
            end_seconds = start_seconds
            in_end_date_obj = datetime.datetime.fromtimestamp(end_seconds)
            end_output = in_end_date_obj.date().strftime(d_format)
    elif trigger_id == 'time-range-slider':
        in_start_date_obj = datetime.datetime.fromtimestamp(slide_values[0])
        start_output = in_start_date_obj.strftime(d_format)
        in_end_date_obj = datetime.datetime.fromtimestamp(slide_values[1])
        end_output = in_end_date_obj.strftime(d_format)

    return [[start_seconds, end_seconds],
            start_output,
            end_output
            ]