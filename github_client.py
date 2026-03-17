import os
import re
from collections import Counter
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
BASE_URL = "https://api.github.com"

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28"
}

def _get(url, params=None):
    res = requests.get(url, headers=HEADERS, params=params, verify=False)
    res.raise_for_status()
    return res.json()


def _paginate(url, params=None, limit_pages=5):
    items = []
    current_page = 1
    params = dict(params or {})

    while current_page <= limit_pages:
        page_params = {**params, "page": current_page}
        data = _get(url, params=page_params)
        batch = data.get("items", data if isinstance(data, list) else [])
        if not batch:
            break
        items.extend(batch)
        if len(batch) < page_params.get("per_page", 30):
            break
        current_page += 1

    return items


def get_pr(repo, pr_number):
    """Fetch a single PR by number."""
    url = f"{BASE_URL}/repos/{repo}/pulls/{pr_number}"
    return _get(url)


def search_similar_prs(repo, query, max_results=10, sort="relevance", order="desc"):
    """Search for similar PRs using GitHub search API."""
    url = f"{BASE_URL}/search/issues"
    params = {
        "q": f"{query} repo:{repo} is:pr is:merged",
        "sort": sort,
        "order": order,
        "per_page": max_results
    }
    return _get(url, params=params).get("items", [])


def search_feature_history(repo, query, month=None, year=None, max_results=20):
    """Search merged PRs for a feature query, optionally constrained to a month/year."""
    qualifiers = [f"repo:{repo}", "is:pr", "is:merged"]
    if year and month:
        start = datetime(year, month, 1)
        end = datetime(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)
        qualifiers.append(f"merged:{start.date()}..{end.date()}")

    base_qualifiers = ' '.join(qualifiers)
    normalized = _normalize_feature_name(query)
    query_parts = [p for p in re.split(r"\s+", normalized) if p]
    search_queries = []

    if query.strip():
        search_queries.append(f'"{query.strip()}" {base_qualifiers}')
    if normalized and normalized != query.strip().lower():
        search_queries.append(f'"{normalized}" {base_qualifiers}')
    if query_parts:
        search_queries.append(f"{' '.join(query_parts[:4])} {base_qualifiers}")
    if len(query_parts) >= 2:
        search_queries.append(f"{' '.join(query_parts[:2])} {base_qualifiers}")

    url = f"{BASE_URL}/search/issues"
    seen = set()
    collected = []

    for search_query in search_queries:
        params = {
            "q": search_query,
            "sort": "updated",
            "order": "desc",
            "per_page": min(max_results, 100)
        }
        items = _get(url, params=params).get("items", [])
        for item in items:
            if item["number"] in seen:
                continue
            seen.add(item["number"])
            collected.append({
                "number": item["number"],
                "title": item["title"],
                "url": item["html_url"],
                "state": item["state"],
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
                "closed_at": item.get("closed_at")
            })
            if len(collected) >= max_results:
                return collected[:max_results]

    return collected[:max_results]


def get_most_reviewed_prs(repo, limit=10, window="all"):
    """Return PRs with the highest combined feedback counts in the selected time window."""
    qualifiers = [f"repo:{repo}", "is:pr", "is:closed"]
    if window == "month":
        qualifiers.append("merged:>=2026-01-01")

    url = f"{BASE_URL}/search/issues"
    params = {
        "q": ' '.join(qualifiers),
        "sort": "updated",
        "order": "desc",
        "per_page": 25
    }

    candidates = _paginate(url, params=params, limit_pages=2)
    ranked = []
    for item in candidates[:20]:
        pr_number = item["number"]
        feedback = collect_all_feedback(repo, pr_number)
        files = get_pr_files(repo, pr_number)
        total_reviews = (
            len(feedback["reviews"])
            + len(feedback["review_comments"])
            + len(feedback["issue_comments"])
            + len(feedback["commit_comments"])
        )
        ranked.append({
            "number": pr_number,
            "title": item["title"],
            "url": item["html_url"],
            "review_count": total_reviews,
            "changed_files": len(files),
            "updated_at": item.get("updated_at")
        })

    ranked.sort(key=lambda pr: (pr["review_count"], pr["changed_files"]), reverse=True)
    return ranked[:limit]


def _normalize_feature_name(name):
    name = re.sub(r"[^a-zA-Z0-9/ ._-]+", " ", (name or "").strip().lower())
    name = re.sub(r"\s+", " ", name).strip(" -_./")
    return name


def _extract_title_phrases(title):
    stop_words = {
        "fix", "fixes", "fixed", "add", "adds", "added", "update", "updates",
        "updated", "remove", "removes", "removed", "the", "a", "an", "in",
        "on", "at", "to", "for", "of", "and", "or", "is", "are", "was",
        "were", "be", "been", "being", "have", "has", "had", "do", "does",
        "did", "will", "would", "could", "should", "may", "might", "shall",
        "not", "no", "nor", "so", "yet", "both", "either", "neither",
        "feat", "feature", "bug", "chore", "refactor", "test", "docs", "support",
        "enable", "improve", "cleanup", "handle", "use", "with", "from", "this", "that", "into"
    }
    words = [w for w in re.split(r"[^a-zA-Z0-9]+", (title or "").lower()) if w]
    filtered = [w for w in words if w not in stop_words and len(w) > 2]
    phrases = []
    if filtered:
        phrases.append(" ".join(filtered[:2]))
    if len(filtered) >= 3:
        phrases.append(" ".join(filtered[:3]))
    return [_normalize_feature_name(p) for p in phrases if p]


def _extract_file_features(changed_files):
    feature_names = []
    ignored_roots = {"test", "tests", "docs", "build", ".github", "scripts"}
    for changed_file in changed_files:
        path = changed_file.get("filename", "")
        if not path:
            continue
        parts = [p for p in path.split("/") if p]
        if not parts:
            continue
        root = parts[0].lower()
        if root in ignored_roots and len(parts) > 1:
            root = parts[1].lower()
        feature_names.append(_normalize_feature_name(root))
        if len(parts) > 1 and parts[0].lower() not in ignored_roots:
            feature_names.append(_normalize_feature_name(f"{parts[0]}/{parts[1]}"))
    return [name for name in feature_names if name]


def get_frequently_reviewed_features(repo, limit=10):
    """Infer feature names from labels, PR titles, and changed file modules."""
    url = f"{BASE_URL}/search/issues"
    params = {
        "q": f"repo:{repo} is:pr is:closed",
        "sort": "updated",
        "order": "desc",
        "per_page": 20
    }

    prs = _paginate(url, params=params, limit_pages=2)[:20]
    feature_counter = Counter()
    feature_examples = {}

    for item in prs:
        pr_number = item["number"]
        feature_candidates = set()

        labels = item.get("labels", []) or []
        for label in labels:
            label_name = _normalize_feature_name(label.get("name", ""))
            if label_name and len(label_name) > 2:
                feature_candidates.add(label_name)

        for phrase in _extract_title_phrases(item.get("title", "")):
            feature_candidates.add(phrase)

        try:
            changed_files = get_pr_files(repo, pr_number)
            for file_feature in _extract_file_features(changed_files):
                feature_candidates.add(file_feature)
        except Exception:
            changed_files = []

        for feature_name in feature_candidates:
            if len(feature_name) < 3:
                continue
            feature_counter[feature_name] += 1
            feature_examples.setdefault(feature_name, []).append({
                "number": pr_number,
                "title": item["title"],
                "url": item["html_url"]
            })

    results = []
    for feature_name, count in feature_counter.most_common(limit):
        results.append({
            "feature": feature_name,
            "review_frequency": count,
            "examples": feature_examples.get(feature_name, [])[:3]
        })
    return results

def get_pr_reviews(repo, pr_number):
    """Fetch all reviews for a PR."""
    url = f"{BASE_URL}/repos/{repo}/pulls/{pr_number}/reviews"
    return _get(url)

def get_pr_review_comments(repo, pr_number):
    """Fetch all line-level review comments for a PR."""
    url = f"{BASE_URL}/repos/{repo}/pulls/{pr_number}/comments"
    return _get(url)

def get_pr_issue_comments(repo, pr_number):
    """Fetch all issue/thread comments for a PR."""
    url = f"{BASE_URL}/repos/{repo}/issues/{pr_number}/comments"
    return _get(url)

def get_pr_commits(repo, pr_number):
    """Fetch all commits for a PR."""
    url = f"{BASE_URL}/repos/{repo}/pulls/{pr_number}/commits"
    return _get(url)

def get_commit_comments(repo, commit_sha):
    """Fetch all comments on a specific commit."""
    url = f"{BASE_URL}/repos/{repo}/commits/{commit_sha}/comments"
    return _get(url)

def get_pr_files(repo, pr_number):
    """Fetch all files changed in a PR."""
    url = f"{BASE_URL}/repos/{repo}/pulls/{pr_number}/files"
    return _get(url)

def collect_all_feedback(repo, pr_number):
    """Collect ALL feedback for a PR - reviews, comments, commit comments."""
    feedback = {
        "reviews": [],
        "review_comments": [],
        "issue_comments": [],
        "commit_comments": []
    }

    # Reviews
    try:
        reviews = get_pr_reviews(repo, pr_number)
        for r in reviews:
            if r.get("body", "").strip():
                feedback["reviews"].append({
                    "author": r["user"]["login"],
                    "state": r["state"],
                    "body": r["body"]
                })
    except Exception as e:
        print(f"  Warning: Could not fetch reviews: {e}")

    # Line-level review comments
    try:
        review_comments = get_pr_review_comments(repo, pr_number)
        for c in review_comments:
            if c.get("body", "").strip():
                feedback["review_comments"].append({
                    "author": c["user"]["login"],
                    "file": c.get("path", ""),
                    "line": c.get("line", ""),
                    "body": c["body"]
                })
    except Exception as e:
        print(f"  Warning: Could not fetch review comments: {e}")

    # Issue/thread comments
    try:
        issue_comments = get_pr_issue_comments(repo, pr_number)
        for c in issue_comments:
            if c.get("body", "").strip():
                feedback["issue_comments"].append({
                    "author": c["user"]["login"],
                    "body": c["body"]
                })
    except Exception as e:
        print(f"  Warning: Could not fetch issue comments: {e}")

    # Commit comments
    try:
        commits = get_pr_commits(repo, pr_number)
        for commit in commits[:5]:  # limit to 5 commits
            sha = commit["sha"]
            comments = get_commit_comments(repo, sha)
            for c in comments:
                if c.get("body", "").strip():
                    feedback["commit_comments"].append({
                        "author": c["user"]["login"],
                        "sha": sha[:7],
                        "body": c["body"]
                    })
    except Exception as e:
        print(f"  Warning: Could not fetch commit comments: {e}")

    return feedback
