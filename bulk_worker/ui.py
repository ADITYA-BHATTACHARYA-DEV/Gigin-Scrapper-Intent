import dash_bootstrap_components as dbc
from dash import html, dcc

def bulk_layout():
    return dbc.Container([
        dbc.Row([
            dbc.Col([
                html.H4("Bulk Company Discovery Swarm", className="text-info mt-3"),
                html.P("Upload 1,000+ companies to scour LinkedIn for decision makers.", className="text-muted small"),
                
                dcc.Upload(
                    id='bulk-upload',
                    children=html.Div(['Drag and Drop or ', html.A('Select Excel File')]),
                    style={'width': '100%', 'height': '60px', 'lineHeight': '60px', 'borderWidth': '1px', 
                           'borderStyle': 'dashed', 'borderRadius': '5px', 'textAlign': 'center', 'margin': '10px 0'}
                ),
                html.Div(id='bulk-file-info', className="text-info mb-3 small"),

                dbc.Card([
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                html.Label("Concurrency", className="small text-muted"),
                                dbc.Select(id="bulk-concurrency", value="3", options=[
                                    {"label": "1 (Stealth)", "value": "1"},
                                    {"label": "3 (Normal)", "value": "3"},
                                    {"label": "5 (Fast)", "value": "5"}
                                ])
                            ]),
                            dbc.Col([
                                html.Label("Delay (s)", className="small text-muted"),
                                dbc.Input(id="bulk-delay", type="number", value=15)
                            ])
                        ])
                    ])
                ], className="bg-dark border-secondary mb-3"),

                dbc.Button("START BULK EXECUTION", id="bulk-run-btn", color="success", className="w-100 mb-3"),
                
                html.Div(id="bulk-log-console", style={
                    'height': '300px', 'overflowY': 'scroll', 'backgroundColor': '#000',
                    'color': '#00ff41', 'padding': '15px', 'fontFamily': 'monospace', 'fontSize': '12px',
                    'border': '1px solid #333'
                }, children="Ready for instructions...")
            ], width=12)
        ])
    ])