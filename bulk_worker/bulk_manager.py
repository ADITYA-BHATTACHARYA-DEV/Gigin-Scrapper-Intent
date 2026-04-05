import asyncio
import random
import pandas as pd
import io
import base64
from engines.discovery import find_platform_leads_from_search
from logic.analyzer import AnalysisEngine
import storage

class BulkSwarmManager:
    def __init__(self, concurrency=3, delay=15):
        self.semaphore = asyncio.Semaphore(concurrency)
        self.delay = delay
        self.analyzer = AnalysisEngine()
        self.target_roles = "(CEO OR 'HR Manager' OR 'Talent Acquisition' OR 'Head of Recruitment')"

    async def run(self, companies, min_score, progress_callback=None):
        # 1. Initialize checkpoint table
        storage.init_bulk_storage()
        
        # 2. Register all companies as pending if they don't exist
        for c in companies:
            try:
                storage.update_bulk_status(c, 'pending')
            except: pass

        # 3. Filter for only pending/failed tasks
        todo = storage.get_pending_companies()
        total = len(todo)
        
        tasks = [self.process_company(c, min_score, i, total, progress_callback) for i, c in enumerate(todo)]
        return await asyncio.gather(*tasks)

    async def process_company(self, company, min_score, index, total, callback):
        async with self.semaphore:
            # Random jitter to prevent IP ban
            await asyncio.sleep(random.uniform(5, 12))
            
            if callback: 
                callback(f"[*] Processing {index+1}/{total}: {company}")

            query = f"site:linkedin.com/in {company} {self.target_roles}"
            
            try:
                storage.update_bulk_status(company, 'processing')
                leads = await find_platform_leads_from_search('linkedin', query)
                
                for lead in leads:
                    if storage.is_duplicate(lead['url'], company): continue
                    
                    context = f"Company: {company}\nLead: {lead['title']}\nSnippet: {lead['snippet']}"
                    analysis = await self.analyzer.get_intent_and_response(context)
                    
                    if analysis['score'] >= min_score:
                        result = {
                            'query': company, 'platform': 'linkedin', 'url': lead['url'],
                            'intent': f"Decision Maker @ {company}",
                            'intent_level': analysis['intent_level'], 'score': analysis['score'],
                            'response': analysis['raw'], 'reach_out': analysis['reach_out'],
                            'result_type': 'profile'
                        }
                        storage.save_to_all(result)
                
                storage.update_bulk_status(company, 'completed')
                # Wait for defined cooling period
                await asyncio.sleep(self.delay)
                return f"✅ {company} completed."
            
            except Exception as e:
                storage.update_bulk_status(company, 'failed')
                return f"❌ {company} failed: {str(e)}"