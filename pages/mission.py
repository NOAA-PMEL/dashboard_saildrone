import dash
from dash import dcc, html, callback, Output, Input, State, no_update, ctx
import plotly.graph_objects as go
import plotly.express as px
import dash_design_kit as ddk
from plotly.subplots import make_subplots

import pandas as pd
import json

import db
import constants
from sdig.util import zc

from tsdownsample import MinMaxLTTBDownsampler
import numpy as np

row_height = 450
line_rgb = 'rgba(.04,.04,.04,.2)'
plot_bg = 'rgba(1.0, 1.0, 1.0 ,1.0)'

dash.register_page(__name__, path="/mission")

def layout(mission_id=None, **params):
    layout = ''
    if mission_id is not None:
        constants.redis_instance.hset('mission', 'current_mission', mission_id)
        mission_drones = []
        mission_variables = []
        variables = []
        mission_config = json.loads(constants.redis_instance.hget("mission", mission_id))
        for drone in mission_config['drones']:
            drone_cf = mission_config['drones'][drone]
            mission_drones.append({'label': drone_cf['label'], 'value': drone})
            variables = variables + mission_config['drones'][drone]['variables']
        variables = list(set(variables))
        variables.sort()
        logo_img = mission_config['ui']['logo']
        start_date = mission_config['start_date']
        end_date = mission_config['end_date']
        long_names = mission_config['long_names']
        if not logo_img.startswith("http"):
            logo_img = constants.assets + logo_img
        for var in variables:
            mission_variables.append({'label': long_names[var], 'value': var})
        mission_variables = sorted(mission_variables, key=lambda d: d['label'])
        mission_variables_value = variables[0]
        layout = [
            ddk.Card(width=1, children=[
                ddk.CardHeader(title=mission_config['ui']['title'], children=[
                    html.Img(src=logo_img, style={'height': '65px', 'padding-bottom': '10px'}),
                ]),
                ddk.Block(width=.3, children=[
                    ddk.ControlCard(width=1, children=[
                        ddk.ControlItem(label='Drones:', children=[
                            dcc.Dropdown(id='drones', options=mission_drones, multi=True)
                        ]),
                        ddk.ControlItem(label="Time Range:", children=[
                            dcc.DatePickerRange(
                                id='date-range',
                                min_date_allowed=start_date,
                                max_date_allowed=end_date,
                                start_date=start_date,
                                end_date=end_date
                            )
                        ])
                    ]),
                    ddk.ControlCard(width=1, children=[
                        ddk.ControlItem(label='Add a trace of this variable to the map:', children=[
                        dcc.Dropdown(id='trace-variable', options=mission_variables, value=mission_variables_value, multi=False)
                        ]),
                    ]),
                ]),
                ddk.Card(width=.7, children=[
                    dcc.Loading(dcc.Graph(id='trajectory-map'))
                ]),
                ddk.ControlCard(width=1, orientation='horizontal', children=[
                    ddk.ControlItem(width=.3, label='Timeseries Variables:', children=[
                        dcc.Dropdown(id='timeseries-variables', options=mission_variables, multi=True)
                    ]),
                    ddk.ControlItem(width=.6, children=[
                            dcc.Loading([html.Div(id='message', children='Resampling...', style={'visibility':'hidden', 'width':'100%'}), html.Div(id='loader', style={'display':'none'})]),
                        ]
                    ),
                    ddk.ControlItem(width=.1, children=[
                            html.Button(id="reset", children="Reset", style={'float':'right'}),
                        ]
                    )
                ]),
                ddk.Card(width=1., children=[
                    html.Progress(id="progress-bar", value="0", style={'visibility':'hidden', 'width':'100%'}),
                    ddk.Graph(id='timeseries-plots', figure=constants.get_blank('Choose what to plot with controls above'))
                ])
            ])
        ]
    else:
        layout = html.Div('No mission id was included on the page URL.')
    return layout


@callback(
    [
        Output('drones', 'value')
    ],
    [
        Input('trajectory-map', 'clickData')
    ],
    [
        State('drones', 'value')
    ]
)
def drone_click(click_data, state_drones):
    if click_data is not None:
        top_click = click_data['points'][0]
        drone = top_click['customdata']
        if state_drones is None:
            state_drones = []
        if drone not in state_drones:
            state_drones.append(drone)
        return [state_drones]
    return no_update


@callback(
    [
        Output('trajectory-map', 'figure')
    ],
    [
        Input('trace-variable', 'value'),
        Input('drones', 'value'),
        Input('date-range', 'start_date'),
        Input('date-range', 'end-date'),
    ],
)
def plot_locations_and_trajectory(in_variable, in_drones, in_start_date, in_end_date):
    mission_id = constants.redis_instance.hget('mission', 'current_mission').decode("utf-8")
    mission_config = json.loads(constants.redis_instance.hget("mission", mission_id))
    df = db.get_mission_locations(mission_id, mission_config['dsg_id'])
    df['location_text'] = '<b>' + df['trajectory'].astype(str) + '</b>' +\
                          '<br>lat=' + df['latitude'].apply(lambda x: '{:,.2f}'.format(x)) +\
                          '<br>lon=' + df['longitude'].apply(lambda x: '{:,.2f}'.format(x)) +\
                          '<br>time=' + df['time'].astype(str)   

    figure = go.Figure()
    drones = df['trajectory'].unique()
    drones.sort()
    for idx, drone in enumerate(drones):
        ddf = df.loc[df['trajectory']==drone]
        location_trace = go.Scattermap(lat=ddf['latitude'], 
                                          lon=ddf['longitude'],
                                          marker=dict(color=mission_config['drones'][drone]['color']), 
                                          name=str(drone),
                                          hoverinfo='text',
                                          hovertext=ddf['location_text'],
                                          customdata=ddf['trajectory'],
                                          uid=str(drone)
                                          )
        figure.add_trace(location_trace)
    
    time_con = ''
    if in_start_date is not None and len(in_start_date) > 0:
        time_con = '&time>=' + in_start_date
    if in_end_date is not None and len(in_end_date) > 0:
        time_con = '&time<=' + in_end_date


    if in_variable is not None and len(in_variable) > 0 and in_drones is not None and len(in_drones) > 0:
        # Create a trace to add to the figure            
        n = int(50000/(len(in_drones)))
        drone_dfs = []
        for idx, drone in enumerate(in_drones):
            url = mission_config['drones'][drone]['url'] + '.csv?time,latitude,longitude,trajectory,' + in_variable + time_con
            tdf = pd.read_csv(url, skiprows=[1])
            tdf = tdf.loc[tdf['time'].notna()]
            tdf = tdf.loc[tdf[in_variable].notna()]
            tdf.reset_index(inplace=True)
            tdf['millis'] = pd.to_datetime(tdf['time']).astype('int64')
            x = tdf['millis'].to_numpy()
            y = tdf[in_variable].to_numpy()
            # Downsample to n_out points using the (possible irregularly spaced) x-data
            s_ds = MinMaxLTTBDownsampler().downsample(x, y, n_out=n)
            tdf = tdf.iloc[s_ds]
            drone_dfs.append(tdf)
        pdf = pd.concat(drone_dfs)
        pdf['trace_text'] = '<b>' + pdf['trajectory'].astype(str) + '</b><br>' +\
                                in_variable + '=' + pdf[in_variable].apply(lambda x: '{:,.2f}'.format(x)) + '<br>' \
                            'lat=' + pdf['latitude'].apply(lambda x: '{:,.2f}'.format(x)) + '<br>' + \
                            'lon=' + pdf['longitude'].apply(lambda x: '{:,.2f}'.format(x)) + '<br>' + \
                            'time=' + pdf['time'].astype(str) 
        trace = go.Scattermap(lat=pdf["latitude"], lon=pdf["longitude"],
                                    marker=dict(showscale=True, color=pdf[in_variable],
                                                colorscale='Viridis', size=8,
                                                colorbar=dict(
                                                    title_side='right',
                                                    title_font_size=16,
                                                    tickfont_size=16,
                                                    title_text=in_variable,
                                                    len=.9
                                                )
                                            ),
                                    name=in_variable,
                                    hoverinfo='text',
                                    hovertext=pdf['trace_text'],
                                    
                            )
        figure.add_trace(trace)
    zoom, center = zc.zoom_center(df['longitude'], df['latitude'])
    figure.update_layout(
        legend_title='Drone:',
        legend_orientation="v",
        legend_x=0.,
        map_zoom=zoom,
        map_center=center,
        margin={'r':0, 'l':0, 't':0, 'b':0},
        uirevision='location_map'
    )
    figure.update_legends(uirevision='no_update')
    return [figure]

@callback (
    [
        Output('timeseries-plots', 'figure', allow_duplicate=True),
        Output('loader', 'children', allow_duplicate=True),
    ],
    [
        Input('timeseries-variables', 'value'),
        Input('drones', 'value'),
        Input('date-range', 'start_date'),
        Input('date-range', 'end-date'),
    ], 
    background=True,
    running=[
        (
            Output("progress-bar", "style"),
            {"visibility": "visible", "width":"100%"},
            {"visibility": "hidden", "widht": "100%"},
        )
    ],
    prevent_initial_call=True, 
    progress=[Output("progress-bar", "value"), Output("progress-bar", "max")],
)
def timeseries_plots(set_progress, in_variables, in_drones, in_start_date, in_end_date):
    set_progress(["0","0"])
    if in_variables is not None and len(in_variables) > 0 and in_drones is not None:
        mission_id = constants.redis_instance.hget('mission', 'current_mission').decode("utf-8")
        mission_config = json.loads(constants.redis_instance.hget("mission", mission_id))
        time_con = ''
        if in_start_date is not None and len(in_start_date) > 0:
            time_con = '&time>=' + in_start_date
        if in_end_date is not None and len(in_end_date) > 0:
            time_con = '&time<=' + in_end_date
        figure = create_subplot(mission_config, in_variables)
        uirevision = '_'.join(in_drones)+"_"+"_".join(in_variables)
        sub_sample_ratio = 1.
        progress_max = len(in_drones) + len(in_variables) + 2
        progress = 1
        set_progress([str(progress), str(progress_max)])
        for dix, drone in enumerate(in_drones):
            get_vars = ','.join(in_variables)
            url = mission_config['drones'][drone]['url'] + '.csv?time,trajectory,' + get_vars + time_con
            tdf = pd.read_csv(url, skiprows=[1])
            tdf = tdf.loc[tdf['time'].notna()]
            tdf.reset_index(inplace=True)
            tdf['millis'] = pd.to_datetime(tdf['time']).astype('int64')
            progress = progress + 1
            set_progress([str(progress), str(progress_max)])
            for vix, var in enumerate(in_variables):
                plot_df = tdf[['time','millis','trajectory',var]]
                plot_df.reset_index(inplace=True)
                constants.redis_instance.hset("cache", mission_id+"_"+drone+"_"+var, json.dumps(plot_df.to_json()))
                sub_sample_ratio, trace = make_trace(plot_df, drone, var, mission_config['drones'][drone]['color'], vix)
                figure.add_trace(trace, row=vix+1, col=1)
                progress = progress + 1
                set_progress([str(progress), str(progress_max)])
        figure = annotate_figure(figure, in_variables, sub_sample_ratio, mission_config)
        set_progress([str(progress_max), str(progress_max)])
        set_progress(["0","0"])
        return [figure, '']
    else:
        return no_update, no_update

@callback(
    [
        Output('timeseries-plots', 'figure', allow_duplicate=True),
        Output('loader', 'children', allow_duplicate=True),
    ],
    [
        Input('timeseries-plots', 'relayoutData'),
        Input('reset', 'n_clicks')
    ],
    [
        State('drones', 'value'),
        State('timeseries-variables', 'value')
    ], 
    background=True,
    running=[
        (
            Output("progress-bar", "style"),
            {"visibility": "visible", "width":"100%"},
            {"visibility": "hidden", "widht": "100%"},
        ),
        (
            Output("message", "style"),
            {"visibility": "visible", "width":"100%"},
            {"visibility": "hidden", "widht": "100%"},
        )
    ],
    prevent_initial_call=True, 
    progress=[Output("progress-bar", "value"), Output("progress-bar", "max")],
)
def zoom_plot(set_progress, layout_data, click, in_drones, in_variables):
    reset = False
    if ctx.triggered_id == 'reset':
        reset = True
    mission_id = constants.redis_instance.hget('mission', 'current_mission').decode("utf-8")
    mission_config = json.loads(constants.redis_instance.hget("mission", mission_id))
    if layout_data is not None and 'xaxis.range[0]' in layout_data and 'xaxis.range[1]' in layout_data:
        xstart = layout_data['xaxis.range[0]']
        xend = layout_data['xaxis.range[1]']
    else:
        return no_update
    set_progress(("0", "0"))
    figure = create_subplot(mission_config, in_variables)
    sub_sample_ratio = 1.
    max_progress = len(in_variables) + len(in_drones) 
    progress = 1
    set_progress((str(progress), str(max_progress)))
    for dix, drone in enumerate(in_drones):
        progress = progress + 1
        set_progress((str(progress), str(max_progress)))
        for vix, var in enumerate(in_variables):
            cache_id = mission_id+"_"+drone+"_"+var
            plot_df = pd.read_json(json.loads(constants.redis_instance.hget("cache", cache_id)))
            # Cut down the dataframe to the timerange in the layout
            # Unless the reset button was pushed
            if not reset:
                plot_df = plot_df.loc[plot_df['time']>=xstart]
                plot_df = plot_df.loc[plot_df['time']<=xend]
                plot_df.reset_index(inplace=True)
            sub_sample_ratio, trace = make_trace(plot_df, drone, var, mission_config['drones'][drone]['color'], vix)
            figure.add_trace(trace, row=vix+1, col=1)
            progress = progress + 1
            set_progress((str(progress), str(max_progress)))
    set_progress(("0", "0"))
    figure = annotate_figure(figure, in_variables, sub_sample_ratio, mission_config)
    return [figure, '']


def create_subplot(mission_config, in_variables):
    titles = []
    row_hts = []
    for var in in_variables:
        title = var
        if var in mission_config['long_names']:
            title = mission_config['long_names'][var]
        if var in mission_config['units']:
            title = title + ' (' + mission_config['units'][var] + ')'
        titles.append(title)
        row_hts.append(row_height)
    row_count = len(in_variables)
    vert = .16
    if row_count > 1:
        vert = vert/(row_count-1)
    figure = make_subplots(rows=row_count, 
                           cols=1, 
                           shared_xaxes='all', 
                           subplot_titles=titles,
                           shared_yaxes=False,
                           row_heights=row_hts,
                           vertical_spacing=vert
                           )
    return figure

def make_trace(plot_df, drone, var, color, vix):
    legend = 'legend'
    if vix > 0:
        legend = legend + str(vix+1)
    sub_sample_ratio = 1.0
    if plot_df.shape[0] > 5000:
        sub_sample_ratio = 5000/plot_df.shape[0]
        x = plot_df['millis'].to_numpy()
        y = plot_df[var].to_numpy()
        # Downsample to n_out points using the (possible irregularly spaced) x-data
        s_ds = MinMaxLTTBDownsampler().downsample(x, y, n_out=5000)
        plot_df = plot_df.iloc[s_ds]
    plot_df.loc[:,'text'] = '<b>drone=' + str(drone) + '<b><br>time=' + plot_df['time'].astype(str) + '<br>' + var + '=' + plot_df[var].apply(lambda x: '{:,.2f}'.format(x))
    trace = go.Scattergl(x=plot_df['time'], y=plot_df[var], hoverinfo='text', hovertext=plot_df['text'], marker={'color': color}, showlegend=True, name=str(drone), legendgroup=str(drone), legend=legend)
    return sub_sample_ratio, trace


def annotate_figure(figure, in_variables, sub_sample_ratio, mission_config):
    figure.update_layout(height=len(in_variables)*row_height, margin={'t':20, 'l':0, 'r':0, 'b': 0} , legend={
            'orientation': 'h',
            "y": 1.1,
            "xref": "container",
            "yref": "container",
    })
    legmap = {}
    for l, var in enumerate(in_variables):
        legdef = 'legend'
        if l > 0:
            legdef = legdef + str(l+1)
        legmap[legdef] = {'orientation': 'h', "y": 1.1, "xref": "container", "yref": "container", }
    figure.update_layout(legmap)
    if sub_sample_ratio < 1.0:
        figure.add_annotation(x=0.05,
                                y=1.055,
                                xref="paper", 
                                yref="y domain",
                                showarrow=False,
                                text='Sub-sampling ratio: ' + '{:,.2f}'.format(sub_sample_ratio))
    for vix, var in enumerate(in_variables):
        short_label = var + '(' + mission_config['units'][var] + ')'
        figure.update_yaxes({
            'title': short_label,
            'titlefont': {'size': 16},
            'gridcolor': line_rgb,
            'zeroline': True,
            'zerolinecolor': line_rgb,
            'showline': True,
            'linewidth': 1,
            'linecolor': line_rgb,
            'mirror': True,
            'tickfont': {'size': 16}
        }, row=vix+1, col=1)
        figure.update_xaxes({
            'ticklabelmode': 'period',
            'showticklabels': True,
            'gridcolor': line_rgb,
            'zeroline': True,
            'zerolinecolor': line_rgb,
            'showline': True,
            'linewidth': 1,
            'linecolor': line_rgb,
            'mirror': True,
            'tickfont': {'size': 16},
            'tickformatstops' : [
                dict(dtickrange=[1000, 60000], value="%H:%M:%S\n%d%b%Y"),
                dict(dtickrange=[60000, 3600000], value="%H:%M\n%d%b%Y"),
                dict(dtickrange=[3600000, 86400000], value="%H:%M\n%d%b%Y"),
                dict(dtickrange=[86400000, 604800000], value="%e\n%b %Y"),
                dict(dtickrange=[604800000, "M1"], value="%b\n%Y"),
                dict(dtickrange=["M1", "M12"], value="%b\n%Y"),
                dict(dtickrange=["M12", None], value="%Y")
            ]
        }, row=vix+1, col=1)
    return figure