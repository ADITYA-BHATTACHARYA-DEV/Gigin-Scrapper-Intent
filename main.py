import os
import json
import asyncio
import dash
import dash_bootstrap_components as dbc
from dash import Dash, html, dcc, Input, Output, State, callback_context, ALL
from dotenv import load_dotenv

from engines.discovery import find_platform_leads_from_search, _playwright_stackoverflow
from engines.extraction import ExtractionEngine
from logic.analyzer import AnalysisEngine
import storage



# Add these along with your other imports
from bulk_worker.ui import bulk_layout
from bulk_worker.manager import BulkSwarmManager
from bulk_worker.persistence import init_bulk_db, save_bulk_checkpoint, get_pending_list

import base64
import io
import pandas as pd


load_dotenv()
storage.init_storage()

SCORE_THRESHOLD = int(os.getenv("SCORE_THRESHOLD", "4"))

app = Dash(__name__, external_stylesheets=[dbc.themes.CYBORG],
           suppress_callback_exceptions=True)

app.layout = dbc.Container([
    html.H1('LAT.AI | RECRUITMENT SWARM', className='text-center mt-4 text-info'),
    html.P('Intent-Led Lead Discovery', className='text-center text-muted mb-3'),

    dbc.Tabs([

        # ── Tab 1: Search ────────────────────────────────────────────────
        dbc.Tab(label='Search', tab_id='tab-search', children=[
            dbc.Row(dbc.Col([
                dbc.Input(
                    id='search-input',
                    placeholder='e.g. hiring issues in recruitment...',
                    className='mt-3 mb-2'
                ),
                html.Label('Min intent score (1–10):', className='text-muted small'),
                dcc.Slider(
                    id='score-threshold',
                    min=1, max=10, step=1, value=SCORE_THRESHOLD,
                    marks={i: str(i) for i in range(1, 11)},
                    className='mb-3'
                ),
                html.Label('Target Platforms:', className='text-info small mb-1'),
                dbc.Checklist(
                    id='platform-selector',
                    options=[
                        {'label': 'LinkedIn',      'value': 'linkedin'},
                        {'label': 'Reddit',        'value': 'reddit'},
                        {'label': 'GitHub',        'value': 'github'},
                        {'label': 'StackOverflow', 'value': 'stackoverflow'},
                        {'label': 'X',             'value': 'x'},
                    ],
                    value=['linkedin', 'reddit'],
                    inline=True,
                    className='mb-3 text-light',
                    switch=True
                ),
                dbc.Button(
                    'EXECUTE SWARM', id='search-btn',
                    color='info', className='w-100 mb-2'
                ),
                dbc.Button(
                    'Clear All Leads', id='clear-btn',
                    color='danger', outline=True,
                    className='w-100 mb-4'
                ),
                html.Div(id='clear-output'),
                dcc.Loading(
                    id='loading-output',
                    children=html.Div(id='feed-container'),
                    type='graph',
                    color='#00cfbd'
                )
            ], width=10), justify='center')
        ]),

        # ── Tab 2: Review Queue ──────────────────────────────────────────
        dbc.Tab(label='Review Queue', tab_id='tab-review', children=[
            dbc.Row(dbc.Col([
                dbc.Button(
                    'Refresh Queue', id='refresh-queue-btn',
                    color='secondary', className='mt-3 mb-3'
                ),
                html.Div(id='review-container')
            ], width=10), justify='center')
        ]),

        # ── Tab 3: KPIs ──────────────────────────────────────────────────
        dbc.Tab(label='KPIs', tab_id='tab-kpis', children=[
            dbc.Row(dbc.Col([
                dbc.Button(
                    'Refresh KPIs', id='refresh-kpi-btn',
                    color='secondary', className='mt-3 mb-3'
                ),
                html.Div(id='kpi-container')
            ], width=10), justify='center')
        ]),

        # ── Tab 4: Bulk Discovery ──────────────────────────────────────────
        dbc.Tab(
            label='Bulk Discovery', 
            tab_id='tab-bulk', 
            children=bulk_layout() # <--- This calls the UI from your bulk_worker folder
        ),

    ], id='main-tabs', active_tab='tab-search'),
], fluid=True)


# ── Helpers ──────────────────────────────────────────────────────────────────
def _lead_card(lead):
    level_color = {
        'Buying Intent':  'success',
        'Problem Intent': 'warning',
        'Topic Intent':   'info',
        'Not Relevant':   'secondary',
    }.get(lead.get('intent_level', ''), 'secondary')

    # Badge color per result type
    type_color = {
        'post':    'primary',
        'article': 'info',
        'profile': 'secondary',
        'company': 'dark',
    }.get(lead.get('result_type', 'other'), 'secondary')

    result_type_label = lead.get('result_type', 'other').upper()

    return dbc.Card([
        dbc.CardHeader([
            html.Span(lead['platform'].upper(), className='badge bg-info me-2'),
            html.Span(result_type_label, className=f'badge bg-{type_color} me-2'),
            html.Span(lead.get('intent_level', ''), className=f'badge bg-{level_color} me-2'),
            html.Span(f"Score: {lead.get('score', 0)}/10", className='badge bg-dark me-2'),
            html.A(lead['url'], href=lead['url'], target='_blank', className='text-info small'),
        ]),
        dbc.CardBody([
            html.H6(lead['intent'], className='text-info mb-1 small'),
            html.P(lead.get('reach_out', ''), className='small text-light mb-0'),
        ])
    ], className='mb-3 border-info bg-dark shadow')

def _review_card(row):
    # Added 'result_type' to the unpack sequence (Position 9)
    # The order must match your database columns exactly.
    rid, ts, query, platform, url, intent, intent_level, score, \
        result_type, llm_resp, reach_out, status, outcome = row # <--- Added result_type here

    level_color = {
        'Buying Intent':  'success',
        'Problem Intent': 'warning',
        'Topic Intent':   'info',
        'Not Relevant':   'secondary',
    }.get(intent_level or '', 'secondary')

    # Now you can use the result_type in your Review Queue cards too!
    type_color = {
        'post':    'primary',
        'article': 'info',
        'profile': 'secondary',
        'company': 'dark',
    }.get(result_type or 'other', 'secondary')

    return dbc.Card([
        dbc.CardHeader([
            html.Span(platform.upper(), className='badge bg-info me-2'),
            html.Span((result_type or 'OTHER').upper(), className=f'badge bg-{type_color} me-2'),
            html.Span(intent_level or '', className=f'badge bg-{level_color} me-2'),
            html.Span(f"Score: {score}/10", className='badge bg-dark me-2'),
            html.A(url, href=url, target='_blank', className='text-info small'),
        ]),
        dbc.CardBody([
            html.H6(intent or '', className='text-info mb-1 small'),
            html.P(reach_out or llm_resp or '', className='small text-light mb-2'),
            dbc.ButtonGroup([
                dbc.Button(
                    'Approve',
                    id={'type': 'approve-btn', 'index': url},
                    color='success', size='sm', className='me-1'
                ),
                dbc.Button(
                    'Reject',
                    id={'type': 'reject-btn', 'index': url},
                    color='danger', size='sm'
                ),
            ])
        ])
    ], className='mb-3 border-warning bg-dark')
# ── Callback: Run swarm ──────────────────────────────────────────────────────

@app.callback(
    Output('feed-container', 'children'),
    Input('search-btn', 'n_clicks'),
    State('search-input', 'value'),
    State('platform-selector', 'value'),
    State('score-threshold', 'value'),
    prevent_initial_call=True
)
def run_swarm(n, keyword, platforms, min_score):
    if not keyword or not platforms:
        return dbc.Alert('Missing keyword or platform selection.', color='warning')

    async def _run():
        extractor = ExtractionEngine()
        analyzer  = AnalysisEngine()
        all_leads = []

        for platform in platforms:
            leads_data = await find_platform_leads_from_search(platform, keyword)

            for item in leads_data:
                url = item['url']

                # Skip duplicate URL+query combos
                if storage.is_duplicate(url, keyword):
                    print(f"   [skip] Duplicate: {url}")
                    continue

                # Extraction
                if platform in ['linkedin', 'reddit', 'x']:
                    context_text = f"Title: {item['title']}\nSnippet: {item['snippet']}"
                else:
                    try:
                        context_text = await extractor.to_markdown(url)
                    except Exception:
                        if platform == 'stackoverflow':
                            try:
                                context_text = await _playwright_stackoverflow(url)
                            except Exception:
                                context_text = f"Title: {item['title']}\nSnippet: {item['snippet']}"
                        else:
                            context_text = f"Title: {item['title']}\nSnippet: {item['snippet']}"

                if not context_text:
                    continue

                # Analysis
                analysis = await analyzer.get_intent_and_response(context_text)

                # Score filter
                if analysis['score'] < min_score:
                    print(f"   [skip] Score {analysis['score']} < {min_score}: {url}")
                    continue

                result = {
                    'query':        keyword,
                    'platform':     platform,
                    'url':          url,
                    'intent':       analysis['intent_label'][:60],
                    'intent_level': analysis['intent_level'],
                    'score':        analysis['score'],
                    'response':     analysis['raw'],
                    'reach_out':    analysis['reach_out'],
                        'result_type':  item.get('result_type', 'other'),
                }

                storage.save_to_all(result)
                all_leads.append(result)

        return all_leads

    leads = asyncio.run(_run())

    if not leads:
        return dbc.Alert(
            'No leads above score threshold. Lower the slider or check terminal logs.',
            color='danger'
        )

    return [_lead_card(lead) for lead in leads]


# ── Callback: Clear all leads ────────────────────────────────────────────────

@app.callback(
    Output('clear-output', 'children'),
    Input('clear-btn', 'n_clicks'),
    prevent_initial_call=True
)
def clear_leads(n):
    storage.clear_all()
    return dbc.Alert('All leads cleared. Ready for fresh run.', color='warning', duration=3000)


# ── Callback: Load review queue ──────────────────────────────────────────────

@app.callback(
    Output('review-container', 'children'),
    Input('refresh-queue-btn', 'n_clicks'),
    prevent_initial_call=True
)
def load_review_queue(n):
    rows = storage.fetch_by_status('pending_review')
    if not rows:
        return dbc.Alert('No leads pending review.', color='info')
    return [_review_card(row) for row in rows]


# ── Callback: Approve / Reject ───────────────────────────────────────────────

@app.callback(
    Output({'type': 'approve-btn', 'index': ALL}, 'disabled'),
    Output({'type': 'reject-btn',  'index': ALL}, 'disabled'),
    Input({'type': 'approve-btn',  'index': ALL}, 'n_clicks'),
    Input({'type': 'reject-btn',   'index': ALL}, 'n_clicks'),
    prevent_initial_call=True
)
def handle_review(approve_clicks, reject_clicks):
    ctx = callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate

    triggered_prop = ctx.triggered[0]['prop_id']
    raw_id   = triggered_prop.rsplit('.', 1)[0]
    btn_info = json.loads(raw_id)

    url    = btn_info['index']
    action = btn_info['type']

    if action == 'approve-btn':
        storage.update_status(url, 'approved', 'approved via UI')
        print(f"   [✓] Approved: {url}")
    else:
        storage.update_status(url, 'rejected', 'rejected via UI')
        print(f"   [✗] Rejected: {url}")

    n = len(approve_clicks)
    return [False] * n, [False] * n


# ── Callback: KPIs ───────────────────────────────────────────────────────────

@app.callback(
    Output('kpi-container', 'children'),
    Input('refresh-kpi-btn', 'n_clicks'),
    prevent_initial_call=True
)
def load_kpis(n):
    kpis = storage.fetch_kpis()
    platform_rows = [
        html.Tr([
            html.Td(p, className='text-info'),
            html.Td(str(c), className='text-light')
        ])
        for p, c in kpis['by_platform'].items()
    ]
    return [
        dbc.Row([
            dbc.Col(dbc.Card(dbc.CardBody([
                html.H4(str(kpis['total_detected']), className='text-info mb-0'),
                html.Small('Total detected', className='text-muted')
            ]), className='bg-dark border-info'), width=4),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.H4(str(kpis['high_intent']), className='text-success mb-0'),
                html.Small('Score ≥ 7 (high intent)', className='text-muted')
            ]), className='bg-dark border-success'), width=4),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.H4(str(kpis['approved']), className='text-warning mb-0'),
                html.Small('Approved for outreach', className='text-muted')
            ]), className='bg-dark border-warning'), width=4),
        ], className='mb-4 mt-3'),
        html.H6('Leads by platform', className='text-muted mt-2 mb-2'),
        dbc.Table(
            [html.Tbody(platform_rows)],
            bordered=True,
            size='sm',
            className='w-50 table-dark'
        )
    ]




import base64, io, pandas as pd, asyncio
from bulk_worker.ui import bulk_layout
from bulk_worker.manager import BulkSwarmManager
from bulk_worker.persistence import init_bulk_db, save_bulk_checkpoint, get_pending_list

init_bulk_db()

# Add this to your Tab list in app.layout
# dbc.Tab(label='Bulk Discovery', tab_id='tab-bulk', children=bulk_layout())

@app.callback(
    Output('bulk-log-console', 'children'),
    Output('bulk-file-info', 'children'),
    Input('bulk-run-btn', 'n_clicks'),
    State('bulk-upload', 'contents'),
    State('bulk-upload', 'filename'),
    State('bulk-concurrency', 'value'),
    State('bulk-delay', 'value'),
    State('score-threshold', 'value'),
    prevent_initial_call=True
)
def trigger_bulk(n, contents, filename, concurrency, delay, min_score):
    if not contents: return "Upload a file first.", ""

    # Parse Excel
    _, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    df = pd.read_excel(io.BytesIO(decoded))
    companies = df.iloc[:, 0].dropna().astype(str).tolist()

    # Pre-register tasks in DB
    for c in companies:
        save_bulk_checkpoint(c, 'pending')

    # Run Manager
    manager = BulkSwarmManager(concurrency=int(concurrency), delay=int(delay))
    
    # Executing logic
    async def _run():
        todo = get_pending_list()
        tasks = [manager.process_company(c, min_score) for c in todo]
        return await asyncio.gather(*tasks)

    results = asyncio.run(_run())
    
    return [html.Div(r) for r in results], f"Processed {len(companies)} companies."



#######################
@app.callback(
    Output('bulk-file-info', 'children', allow_duplicate=True),
    Input('bulk-upload', 'contents'),
    Input('bulk-run-btn', 'n_clicks'),
    State('bulk-upload', 'filename'),
    prevent_initial_call=True
)
def update_bulk_status(contents, n_clicks, filename):
    ctx = callback_context
    if not ctx.triggered:
        return ""
    
    # Get the ID of the component that triggered this
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if trigger_id == 'bulk-upload':
        return f"📂 File '{filename}' loaded and ready for swarm."
    
    elif trigger_id == 'bulk-run-btn':
        return "🚀 Swarm active. Check console below or terminal for real-time progress..."
    
    return ""


@app.callback(
    Output('bulk-log-console', 'children',allow_duplicate=True),
    # Note: 'bulk-file-info' has been removed from here!
    Input('bulk-run-btn', 'n_clicks'),
    State('bulk-upload', 'contents'),
    State('bulk-upload', 'filename'),
    State('bulk-concurrency', 'value'),
    State('bulk-delay', 'value'),
    State('score-threshold', 'value'),
    prevent_initial_call=True
)
def trigger_bulk(n, contents, filename, concurrency, delay, min_score):
    if not contents: return "Please upload an Excel file first."

    try:
        _, content_string = contents.split(',')
        decoded = base64.b64decode(content_string)
        df = pd.read_excel(io.BytesIO(decoded))
        companies = df.iloc[:, 0].dropna().astype(str).tolist()

        for c in companies:
            save_bulk_checkpoint(c, 'pending')

        manager = BulkSwarmManager(concurrency=int(concurrency), delay=int(delay))
        
        async def _run_batch():
            todo = get_pending_list()
            tasks = [manager.process_company(c, min_score) for c in todo]
            return await asyncio.gather(*tasks)

        results = asyncio.run(_run_batch())
        return [html.Div(r) for r in results]

    except Exception as e:
        return f"Error: {str(e)}"

if __name__ == '__main__':
    app.run(debug=True, port=8052)