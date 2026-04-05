# import os
# import httpx
# import re

# # ── Intent Router (Groq API) ────────────────────────────────────────────────

# async def classify_intent_with_groq(query: str) -> str:
#     api_key = os.getenv("GROQ_API_KEY")
#     if not api_key:
#         q = query.lower()
#         if any(w in q for w in ["issue", "problem", "error", "bug", "fail", "challenge"]):
#             return "issue_search"
#         if any(w in q for w in ["article", "post", "blog", "pulse"]):
#             return "content_search"
#         return "profile_search"

#     async with httpx.AsyncClient() as client:
#         try:
#             resp = await client.post(
#                 "https://api.groq.com/openai/v1/chat/completions",
#                 headers={"Authorization": f"Bearer {api_key}"},
#                 json={
#                     "model": "llama-3.3-70b-versatile",
#                     "messages": [
#                         {
#                             "role": "user",
#                             "content": (
#                                 "Classify the following query into exactly one of: "
#                                 "profile_search, issue_search, content_search.\n\n"
#                                 f'Query: "{query}"\n\n'
#                                 "Respond with only the label (e.g., profile_search)."
#                             ),
#                         }
#                     ],
#                     "temperature": 0.0,
#                 },
#                 timeout=10,
#             )
#             resp.raise_for_status()
#             return resp.json()["choices"][0]["message"]["content"].strip().lower()
#         except Exception:
#             return "profile_search"

# def _build_linkedin_query(intent: str, query: str) -> str:
#     clean = query.strip().strip('"').strip("'")
    
#     # site:linkedin.com/in is the best for profile discovery
#     if intent == "profile_search":
#         return f'site:linkedin.com/in "{clean}"'

#     # RECTIFIED: Simplified expansion. 
#     # Using "problems" instead of a giant OR list reduces DDG throttling.
#     elif intent == "issue_search":
#         return f"site:linkedin.com {clean} problems"

#     elif intent == "content_search":
#         return f"site:linkedin.com/pulse {clean}"

#     return f"site:linkedin.com {clean}"

# async def normalize_query_for_platform(platform: str, query: str) -> str:
#     intent = await classify_intent_with_groq(query)
#     print(f"    [intent] platform={platform} intent={intent} query={query!r}")

#     clean = query.strip().strip('"').strip("'")

#     if platform == "linkedin":
#         return _build_linkedin_query(intent, clean)

#     elif platform == "reddit":
#         # RECTIFIED: If your discovery.py uses the JSON API, do NOT use 'site:'
#         # If it uses Bing/DDG, keep 'site:'. 
#         # Assuming discovery.py uses the JSON API first:
#         return clean 

#     elif platform in ["twitter", "x"]:
#         return f"site:twitter.com {clean} OR site:x.com {clean}"

#     elif platform == "github":
#         # RECTIFIED: The GitHub API crashes if it sees 'site:github.com'.
#         # We only pass keywords and API-specific qualifiers.
#         if intent == "profile_search":
#             return f"{clean} type:user"
#         elif intent == "issue_search":
#             return f"{clean} is:issue state:open"
#         return clean 

#     elif platform == "stackoverflow":
#         return f"site:stackoverflow.com {clean}"

#     return clean








import os
import re
import httpx

async def classify_intent_with_groq(query: str) -> str:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
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
    clean = query.strip().strip('"').strip("'")

    if intent == "profile_search":
        words = clean.split()
        if len(words) <= 4:
            return f'site:linkedin.com/in "{clean}"'
        return f"site:linkedin.com/in {clean}"

    elif intent == "issue_search":
        # Search BOTH posts and pulse articles for problem discussions
        # Two separate queries joined — caller will run both
        return f"site:linkedin.com {clean} challenges OR issues OR problems"

    elif intent == "content_search":
        return f"site:linkedin.com/pulse {clean}"

    return f"site:linkedin.com {clean}"


def _build_linkedin_posts_query(query: str) -> str:
    """
    Dedicated query targeting LinkedIn /posts/ URLs specifically.
    These are status updates, shared posts, and comment threads —
    highest intent signals because they show real-time pain points.
    """
    clean = query.strip().strip('"').strip("'")
    return f"site:linkedin.com/posts {clean}"


async def normalize_query_for_platform(platform: str, query: str) -> str:
    intent = await classify_intent_with_groq(query)
    print(f"    [intent] platform={platform} intent={intent} query={query!r}")

    clean = query.strip().strip('"').strip("'")

    if platform == "linkedin":
        return _build_linkedin_query(intent, clean)

    elif platform == "reddit":
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


async def get_linkedin_queries(query: str) -> list[str]:
    """
    Returns MULTIPLE queries for LinkedIn so we search:
      1. General linkedin.com (profiles + pulse + posts)
      2. Specifically /posts/ URLs for status updates and comments
      3. /pulse/ for long-form articles
    All three together give maximum intent surface area.
    """
    intent = await classify_intent_with_groq(query)
    clean  = query.strip().strip('"').strip("'")

    queries = []

    # Always include the primary intent-based query
    queries.append(_build_linkedin_query(intent, clean))

    # Always add a dedicated posts search — this finds real-time status updates
    queries.append(_build_linkedin_posts_query(clean))

    # For issue/content intents, also search pulse articles separately
    if intent in ("issue_search", "content_search"):
        queries.append(f"site:linkedin.com/pulse {clean}")

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique.append(q)

    return unique