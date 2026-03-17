import os
import sys
import json
import urllib3
from flask import Flask, request, jsonify, Response, send_from_directory
from dotenv import load_dotenv

# Disable SSL warnings for corporate network
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

# Force UTF-8
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

app = Flask(__name__, static_folder="static")

# ─────────────────────────────────────────────
# Serve the frontend
# ─────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory("static", "index.html")


# ─────────────────────────────────────────────
# SSE helper
# ─────────────────────────────────────────────
def sse_event(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data)}\n\n"


# ─────────────────────────────────────────────
# Main streaming analysis endpoint
# ─────────────────────────────────────────────
@app.route("/api/analyze")
def analyze():
    """
    Query params:
      - mode   : "pr" | "feature"
      - value  : PR number (int) or feature description (str)
      - repo   : owner/repo  (default from .env or microsoft/vscode)
      - max    : max similar PRs (default 5)

    Returns a text/event-stream of SSE events.
    Each event is a JSON object:
      { type: "step" | "log" | "result" | "error" | "done", ... }
    """
    mode  = request.args.get("mode", "").strip()
    value = request.args.get("value", "").strip()
    repo  = request.args.get("repo", os.getenv("GITHUB_REPO", "microsoft/vscode")).strip()
    max_results = int(request.args.get("max", 5))

    if not mode or not value:
        return jsonify({"error": "mode and value are required"}), 400
    if mode not in ("pr", "feature"):
        return jsonify({"error": "mode must be 'pr' or 'feature'"}), 400

    def stream():
        from github_client import get_pr, collect_all_feedback
        from similarity import find_similar_prs
        from summarizer import summarize

        # ── Step 1: Fetch PR / set context ──────────────────────────
        yield sse_event({"type": "step", "step": 1, "message": "Fetching PR details..." if mode == "pr" else "Setting up feature context..."})

        pr_data = None
        context_description = ""

        if mode == "pr":
            try:
                pr_number = int(value)
                pr_data = get_pr(repo, pr_number)
                context_description = f"PR #{pr_number}: {pr_data['title']}"
                yield sse_event({"type": "log", "level": "success", "message": f"Found: {pr_data['title']}"})
                yield sse_event({"type": "log", "level": "success", "message": f"State: {pr_data['state']}"})
                yield sse_event({"type": "log", "level": "success", "message": f"Author: {pr_data['user']['login']}"})
                yield sse_event({"type": "pr_meta", "title": pr_data["title"], "state": pr_data["state"], "author": pr_data["user"]["login"], "number": pr_number})
            except Exception as e:
                yield sse_event({"type": "error", "message": f"Could not fetch PR #{value}: {e}"})
                return
        else:
            context_description = value
            yield sse_event({"type": "log", "level": "info", "message": f"Feature: {value}"})

        # ── Step 2: Find similar PRs ─────────────────────────────────
        yield sse_event({"type": "step", "step": 2, "message": "Finding similar past PRs..."})
        try:
            similar_prs = find_similar_prs(
                repo,
                pr_data=pr_data,
                feature_description=value if mode == "feature" else None,
                max_results=max_results
            )
            if not similar_prs:
                yield sse_event({"type": "error", "message": "No similar PRs found."})
                return
            yield sse_event({"type": "log", "level": "success", "message": f"Found {len(similar_prs)} similar PRs"})
            for pr in similar_prs:
                yield sse_event({"type": "log", "level": "info", "message": f"  PR #{pr['number']}: {pr['title'][:70]}"})
            yield sse_event({"type": "similar_prs", "prs": similar_prs})
        except Exception as e:
            yield sse_event({"type": "error", "message": f"Error finding similar PRs: {e}"})
            return

        # ── Step 3: Collect feedback ─────────────────────────────────
        yield sse_event({"type": "step", "step": 3, "message": "Collecting all feedback from similar PRs..."})
        similar_prs_feedback = []
        for pr in similar_prs:
            pr_num = pr["number"]
            yield sse_event({"type": "log", "level": "info", "message": f"Fetching feedback for PR #{pr_num}: {pr['title'][:50]}..."})
            try:
                feedback = collect_all_feedback(repo, pr_num)
                total = (
                    len(feedback["reviews"]) +
                    len(feedback["review_comments"]) +
                    len(feedback["issue_comments"]) +
                    len(feedback["commit_comments"])
                )
                yield sse_event({"type": "log", "level": "success", "message": f"  {total} feedback items collected"})
                if total > 0:
                    similar_prs_feedback.append({
                        "pr_number": pr_num,
                        "pr_title": pr["title"],
                        "pr_url": pr["url"],
                        "feedback": feedback
                    })
            except Exception as e:
                yield sse_event({"type": "log", "level": "warning", "message": f"  Could not fetch feedback for PR #{pr_num}: {e}"})

        if not similar_prs_feedback:
            yield sse_event({"type": "error", "message": "No feedback found in any similar PRs."})
            return

        # ── Step 4: AI Summarization ─────────────────────────────────
        model_name = os.getenv("MODEL", "anthropic::claude-sonnet-4-6")
        yield sse_event({"type": "step", "step": 4, "message": f"Summarizing with AI ({model_name})..."})
        try:
            summary = summarize(context_description, similar_prs_feedback)
        except Exception as e:
            yield sse_event({"type": "error", "message": f"AI summarization failed: {e}"})
            return

        # ── Step 5: Send final result ────────────────────────────────
        yield sse_event({"type": "step", "step": 5, "message": "Generating report..."})
        yield sse_event({
            "type": "result",
            "context": context_description,
            "summary": summary,
            "analyzed_prs": [
                {
                    "pr_number": item["pr_number"],
                    "pr_title": item["pr_title"],
                    "pr_url":   item["pr_url"]
                }
                for item in similar_prs_feedback
            ]
        })
        yield sse_event({"type": "done"})

    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/feature-history")
def feature_history():
    query = request.args.get("query", "").strip()
    repo = request.args.get("repo", os.getenv("GITHUB_REPO", "microsoft/vscode")).strip()
    month = request.args.get("month", type=int)
    year = request.args.get("year", type=int)
    max_results = request.args.get("max", default=10, type=int)

    if not query:
        return jsonify({"error": "query is required"}), 400

    from github_client import search_feature_history
    from summarizer import summarize_feature_history

    items = search_feature_history(repo, query, month=month, year=year, max_results=max_results)
    summary = summarize_feature_history(query, items, month=month, year=year)
    return jsonify({
        "query": query,
        "repo": repo,
        "month": month,
        "year": year,
        "summary": summary,
        "items": items
    })


@app.route("/api/review-insights")
def review_insights():
    repo = request.args.get("repo", os.getenv("GITHUB_REPO", "microsoft/vscode")).strip()
    limit = request.args.get("limit", default=10, type=int)
    window = request.args.get("window", default="all", type=str)

    from github_client import get_most_reviewed_prs, get_frequently_reviewed_features
    from summarizer import summarize_review_insights

    try:
        most_reviewed = get_most_reviewed_prs(repo, limit=limit, window=window)
        frequent_features = get_frequently_reviewed_features(repo, limit=limit)
        summary = summarize_review_insights(most_reviewed, frequent_features)
    except Exception as e:
        return jsonify({"error": f"Could not load review insights: {e}"}), 500

    return jsonify({
        "repo": repo,
        "window": window,
        "summary": summary,
        "most_reviewed_prs": most_reviewed,
        "frequent_features": frequent_features
    })


# ─────────────────────────────────────────────
if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    if debug_mode:
        # Local development: use Flask built-in server with auto-reload
        app.run(debug=True, port=5000, threaded=True)
    else:
        # Production: use Waitress — pure Python, works on Windows/ARM64
        from waitress import serve
        print("Starting Waitress server on http://0.0.0.0:5000")
        serve(app, host="0.0.0.0", port=5000, threads=8)
