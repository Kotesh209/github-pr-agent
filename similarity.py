from github_client import search_similar_prs

def extract_keywords(title):
    """Extract meaningful keywords from a PR title."""
    # Remove common words and keep meaningful ones
    stop_words = {
        "fix", "fixes", "fixed", "add", "adds", "added", "update", "updates",
        "updated", "remove", "removes", "removed", "the", "a", "an", "in",
        "on", "at", "to", "for", "of", "and", "or", "is", "are", "was",
        "were", "be", "been", "being", "have", "has", "had", "do", "does",
        "did", "will", "would", "could", "should", "may", "might", "shall",
        "not", "no", "nor", "so", "yet", "both", "either", "neither",
        "feat", "feature", "bug", "chore", "refactor", "test", "docs",
        "pr", "issue", "with", "from", "by", "this", "that", "it"
    }
    words = title.lower().replace(":", " ").replace("-", " ").replace("_", " ").split()
    keywords = [w for w in words if w not in stop_words and len(w) > 2]
    return keywords

def find_similar_prs(repo, pr_data=None, feature_description=None, max_results=5):
    """
    Find similar PRs based on either:
    - An existing PR (uses extracted keywords from title)
    - A feature description
    """
    similar_prs = []
    queries_to_try = []

    if pr_data:
        title = pr_data.get("title", "")
        labels = [l["name"] for l in pr_data.get("labels", [])]
        keywords = extract_keywords(title)

        print(f"  Extracted keywords: {keywords}")

        # Try multiple search strategies from most specific to least
        if len(keywords) >= 3:
            queries_to_try.append(" ".join(keywords[:4]))   # top 4 keywords
        if len(keywords) >= 2:
            queries_to_try.append(" ".join(keywords[:3]))   # top 3 keywords
        if len(keywords) >= 1:
            queries_to_try.append(" ".join(keywords[:2]))   # top 2 keywords
        if labels:
            queries_to_try.append(" ".join(labels))         # labels only

        current_pr_number = pr_data.get("number")

        for query in queries_to_try:
            print(f"  Trying search query: '{query}'")
            try:
                results = search_similar_prs(repo, query, max_results=max_results * 2)
                for item in results:
                    if item["number"] != current_pr_number:
                        # Avoid duplicates
                        if not any(p["number"] == item["number"] for p in similar_prs):
                            similar_prs.append({
                                "number": item["number"],
                                "title": item["title"],
                                "url": item["html_url"],
                                "state": item["state"],
                                "score": item.get("score", 0)
                            })
                if len(similar_prs) >= max_results:
                    break
            except Exception as e:
                print(f"  Warning: Search failed for query '{query}': {e}")
                continue

    elif feature_description:
        keywords = extract_keywords(feature_description)
        queries_to_try = [
            " ".join(keywords[:4]) if len(keywords) >= 4 else " ".join(keywords),
            " ".join(keywords[:2]) if len(keywords) >= 2 else keywords[0] if keywords else feature_description
        ]

        for query in queries_to_try:
            print(f"  Trying search query: '{query}'")
            try:
                results = search_similar_prs(repo, query, max_results=max_results)
                for item in results:
                    if not any(p["number"] == item["number"] for p in similar_prs):
                        similar_prs.append({
                            "number": item["number"],
                            "title": item["title"],
                            "url": item["html_url"],
                            "state": item["state"],
                            "score": item.get("score", 0)
                        })
                if len(similar_prs) >= max_results:
                    break
            except Exception as e:
                print(f"  Warning: Search failed for query '{query}': {e}")
                continue

    return similar_prs[:max_results]
