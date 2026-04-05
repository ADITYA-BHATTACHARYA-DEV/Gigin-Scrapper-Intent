import asyncio
import random
from engines.discovery import _search_linkedin, find_platform_leads_from_search
from logic.analyzer import AnalysisEngine
from .persistence import save_bulk_checkpoint
import storage

class BulkSwarmManager:
    def __init__(self, concurrency=3, delay=15):
        self.semaphore = asyncio.Semaphore(concurrency)
        self.delay = delay
        self.analyzer = AnalysisEngine()
        # High-signal roles for recruitment
        self.target_roles = "(CEO OR 'Talent Acquisition' OR 'Head of Engineering' OR Founder)"

    async def process_company(self, company, min_score):
        async with self.semaphore:
            # Jitter to avoid bot detection
            await asyncio.sleep(random.uniform(5, 10))
            save_bulk_checkpoint(company, 'active')
            
            try:
                # Use the existing discovery logic
                query = f"{company} {self.target_roles}"
                leads = await _search_linkedin('linkedin', query, None) # None for proxies if not env-set
                
                count = 0
                for lead in leads:
                    if storage.is_duplicate(lead['url'], company): continue
                    
                    # AI Analysis
                    context = f"Company: {company}\nLead: {lead['title']}\nSnippet: {lead['snippet']}"
                    intel = await self.analyzer.get_intent_and_response(context)
                    
                    if intel['score'] >= min_score:
                        result = {
                            'query': f"BULK: {company}", 'platform': 'linkedin', 'url': lead['url'],
                            'intent': f"Decision Maker @ {company}", 'intent_level': intel['intent_level'],
                            'score': intel['score'], 'response': intel['raw'], 
                            'reach_out': intel['reach_out'], 'result_type': lead.get('result_type', 'profile')
                        }
                        storage.save_to_all(result)
                        count += 1
                
                save_bulk_checkpoint(company, 'completed', count=count)
                await asyncio.sleep(self.delay)
                return f"✅ {company}: Found {count} leads."
            
            except Exception as e:
                save_bulk_checkpoint(company, 'failed', error=str(e))
                return f"❌ {company} failed: {str(e)}"