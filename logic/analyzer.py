import os
from groq import AsyncGroq

class AnalysisEngine:
    def __init__(self):
        self.client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

    async def get_intent_and_response(self, text):
        """Analyzes post content for recruitment intent."""
        prompt = f"""
        Role: Technical Headhunter AI.
        Input Data: "{text[:3000]}"
        
        Task:
        1. Determine the 'Intent' (e.g., Hiring Software Engineer, Seeking Internship, Networking).
        2. Draft a personalized, professional reach-out message.
        
        Output Format (Strict):
        Intent: <intent>
        Reach-out: <message>
        """
        
        response = await self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4
        )
        return response.choices[0].message.content