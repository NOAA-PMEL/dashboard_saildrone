import dash
from dash import html, callback, Output, Input, State

dash.register_page(__name__, path="/test")

def layout(test_id=None, **params):
    return html.Div(id='content', children='test_id='+str(test_id))

@callback (
    [
        Output('content', 'children')
    ],
    [
        Input('content', 'nClicks')
    ],
    [
        State('content', 'children')
    ]
)
def calling_baton_rouge(clicky, whats_there):
    return [whats_there+'  callback ran']