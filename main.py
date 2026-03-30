import os
import asyncio
import dash_bootstrap_components as dbc
from dash import Dash, html, dcc, Input, Output, State
from dotenv import load_dotenv

# Internal Engines
# RECTIFIED: Importing the correct function name
from engines.discovery import find_platform_leads_from_search 
from engines.extraction import ExtractionEngine
from logic.analyzer import AnalysisEngine
import storage

load_dotenv()
storage.init_storage()

app = Dash(__name__, external_stylesheets=[dbc.themes.CYBORG])

app.layout = dbc.Container([
    dbc.Row([
        dbc.Col([
            html.H1('LAT.AI | RECRUITMENT SWARM', className='text-center mt-5 text-info'),
            html.P('Stealth Hybrid Discovery (Snippets + Deep Crawl)', className='text-center text-muted mb-4'),
            
            dbc.Input(id='search-input', placeholder='e.g. CUDA specialist or React developer...', className='mb-3'),
            
            html.Label('Target Platforms:', className='text-info small mb-2'),
            dbc.Checklist(
                id='platform-selector',
                options=[
                    {'label': 'LinkedIn', 'value': 'linkedin'},
                    {'label': 'Reddit', 'value': 'reddit'},
                    {'label': 'GitHub', 'value': 'github'},
                    {'label': 'StackOverflow', 'value': 'stackoverflow'},
                    {'label': 'X', 'value': 'X'},
                ],
                value=['stackoverflow'],
                inline=True,
                className='mb-4 text-light',
                switch=True
            ),
            
            dbc.Button('EXECUTE SWARM', id='search-btn', color='info', className='w-100 mb-5 shadow-lg'),
            dcc.Loading(id='loading-output', children=html.Div(id='feed-container'), type='graph', color='#00cfbd')
        ], width=10)
    ], justify='center')
], fluid=True)

@app.callback(
    Output('feed-container', 'children'),
    Input('search-btn', 'n_clicks'),
    State('search-input', 'value'),
    State('platform-selector', 'value'),
    prevent_initial_call=True
)
def update_dashboard(n, keyword, platforms):
    if not keyword or not platforms:
        return dbc.Alert('Missing keyword or platform selection.', color='warning')

    async def run_swarm():
        extractor = ExtractionEngine()
        analyzer = AnalysisEngine()
        all_leads = []

        for platform in platforms:
            # 1. Discovery Phase (Gets snippets and URLs)
            leads_data = await find_platform_leads_from_search(platform, keyword)
            
            for item in leads_data:
                url = item['url']
                
                # 2. Hybrid Extraction Logic
                if platform in ['linkedin', 'reddit']:
                    # Use the Snippet text from Google results (Bypasses Login Walls)
                    print(f"   [📄] Using Snippet context for {platform}...")
                    context_text = f"Title: {item['title']}\nSnippet: {item['snippet']}"
                else:
                    # Use Crawl4AI for full technical content (StackOverflow/GitHub)
                    print(f"   [🕷️] Deep Crawling {platform}...")
                    context_text = await extractor.to_markdown(url)
                
                if not context_text: continue

                # 3. AI Analysis Phase
                analysis_text = await analyzer.get_intent_and_response(context_text)
                
                # 4. Storage & Results
                result = {
                    'query': keyword, 
                    'platform': platform, 
                    'url': url,
                    'intent': item.get('title', 'Technical Lead')[:60], # Clean snippet title
                    'response': analysis_text
                }
                
                storage.save_to_all(result)
                all_leads.append(result)
        
        return all_leads

    # Running the swarm logic
    leads = asyncio.run(run_swarm())

    if not leads:
        return dbc.Alert('No leads found. Check terminal logs for blocks.', color='danger')

    return [dbc.Card([
        dbc.CardHeader([
            html.Span(lead['platform'].upper(), className='badge bg-info me-2'),
            html.A(lead['url'], href=lead['url'], target="_blank", className='text-info small text-decoration-none')
        ]),
        dbc.CardBody([
            html.H6(lead['intent'], className="text-info mb-2 small"),
            html.P(lead['response'], className='small text-light')
        ])
    ], className='mb-3 border-info bg-dark shadow') for lead in leads]

if __name__ == '__main__':
    app.run(debug=True, port=8052)