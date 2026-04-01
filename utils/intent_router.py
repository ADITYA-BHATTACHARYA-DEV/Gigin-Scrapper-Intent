import os
import httpx

# ── Intent Router (Groq API) ────────────────────────────────────────────────

async def classify_intent_with_groq(query: str) -> str:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        # Fallback: simple keyword heuristic so the pipeline still works
        q = query.lower()
        if any(w in q for w in ["issue", "problem", "error", "bug", "fail", "challenge", "trouble", "difficult"]):
            return "issue_search"
        if any(w in q for w in ["article", "post", "blog", "pulse", "wrote", "published"]):
            return "content_search"
        return "profile_search"

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Classify the following query into exactly one of: "
                            "profile_search, issue_search, content_search.\n\n"
                            f'Query: "{query}"\n\n'
                            "Respond with only the label, nothing else."
                        ),
                    }
                ],
                "temperature": 0.0,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip().lower()


def _build_linkedin_query(intent: str, query: str) -> str:
    """
    Build a DDG-friendly site: query for LinkedIn.
    Rules:
      - Never wrap the entire user query in double quotes — DDG treats that as
        an exact-phrase match and returns 0 results for anything longer than ~3 words.
      - Use OR-expanded keyword sets for issue/content intents so DDG has
        multiple retrieval paths.
      - Always keep site: unquoted and at the front.
    """
    # Strip any quotes the caller may have already added
    clean = query.strip().strip('"').strip("'")

    if intent == "profile_search":
        # For names / short identifiers, exact phrase is fine
        words = clean.split()
        if len(words) <= 4:
            return f'site:linkedin.com/in "{clean}"'
        # Longer queries → keyword search without quotes
        return f"site:linkedin.com/in {clean}"

    elif intent == "issue_search":
        # Content search across all of linkedin.com, keyword style
        # Add high-signal synonyms so DDG has more surface area to match
        keywords = clean
        return f"site:linkedin.com {keywords} challenges OR issues OR problems"

    elif intent == "content_search":
        # Pulse articles
        keywords = clean
        return f"site:linkedin.com/pulse {keywords}"

    # Default fallback
    return f"site:linkedin.com {clean}"


async def normalize_query_for_platform(platform: str, query: str) -> str:
    intent = await classify_intent_with_groq(query)
    print(f"    [intent] platform={platform} intent={intent} query={query!r}")

    clean = query.strip().strip('"').strip("'")

    if platform == "linkedin":
        return _build_linkedin_query(intent, clean)

    elif platform == "reddit":
        # Don't quote long queries — same DDG exact-match trap
        words = clean.split()
        if len(words) <= 4:
            return f'site:reddit.com "{clean}"'
        return f"site:reddit.com {clean}"

    elif platform in ["twitter", "x"]:
        words = clean.split()
        if len(words) <= 4:
            return f'site:twitter.com "{clean}" OR site:x.com "{clean}"'
        return f"site:twitter.com {clean} OR site:x.com {clean}"

    elif platform == "github":
        if intent == "profile_search":
            return f'site:github.com "{clean}"'
        elif intent == "issue_search":
            return f"site:github.com/issues {clean}"
        return f"site:github.com {clean}"

    elif platform == "stackoverflow":
        return f"site:stackoverflow.com {clean}"

    return clean