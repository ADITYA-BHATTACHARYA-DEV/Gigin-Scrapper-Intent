import os
import re
from groq import AsyncGroq

class AnalysisEngine:
    def __init__(self):
        self.client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

    async def get_intent_and_response(self, text: str) -> dict:
        prompt = f"""
You are an Intent Marketing AI for a B2B SaaS recruitment tool.

Analyze this social post/profile:
"{text[:3000]}"

Return EXACTLY this format, nothing else:

Intent-Level: <Buying Intent | Problem Intent | Topic Intent | Not Relevant>
Score: <integer 1-10 where 10 = actively buying>
Intent-Label: <one sentence describing what this person needs>
Reach-out: <a helpful, non-salesy reply using Empathy → Insight → Soft suggestion format>
"""
        response = await self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4
        )
        raw = response.choices[0].message.content

        # Parse structured fields out of the LLM response
        def extract(label):
            m = re.search(rf"{label}:\s*(.+)", raw)
            return m.group(1).strip() if m else ""

        score_str = extract("Score")
        try:
            score = int(score_str)
        except ValueError:
            score = 0

        return {
            "intent_level": extract("Intent-Level"),
            "score": score,
            "intent_label": extract("Intent-Label"),
            "reach_out": extract("Reach-out"),
            "raw": raw,
        }