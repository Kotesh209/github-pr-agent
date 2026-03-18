# GitHub PR Agent

GitHub PR Agent is a web-based and API-backed tool that helps developers analyze pull requests, explore feature history, discover historically reviewed areas, and generate AI-assisted summaries from past review activity.

## Features

- **PR Analysis**
  - Analyze a PR number or feature description
  - Find similar historical PRs
  - Collect review feedback from similar PRs
  - Generate AI-powered reviewer expectation summaries

- **Feature History**
  - Search how a feature evolved across PRs
  - Filter by month and year
  - View version-to-version style feature history

- **Review Insights**
  - View most reviewed PRs
  - Detect frequently reviewed features using:
    - PR labels
    - PR title phrases
    - changed file/module paths

- **Export & Print**
  - Copy report
  - Export as Markdown
  - Export as JSON
  - Print report

## Tech Stack

- **Backend:** Python, Flask, Waitress
- **Frontend:** HTML, CSS, JavaScript
- **APIs:** GitHub REST API
- **AI Summarization:** QGenie SDK

## Project Structure

```text
github-pr-agent/
├── app.py
├── agent.py
├── github_client.py
├── similarity.py
├── summarizer.py
├── requirements.txt
├── .env.example
└── static/
    └── index.html
```

## Setup

### 1. Clone the repository
```bash
git clone https://github.com/YOUR_USERNAME/github-pr-agent.git
cd github-pr-agent
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Create environment file
Create a `.env` file in the project root.

Example:

```env
GITHUB_TOKEN=your_github_token
QGENIE_API_KEY=your_qgenie_api_key
GITHUB_REPO=microsoft/vscode
MODEL=anthropic::claude-sonnet-4-6
FLASK_DEBUG=false
```

## Running the Project

### Run web app
```bash
python app.py
```

Open in browser:

```text
http://localhost:5000
```

### Run CLI mode
Analyze a PR:

```bash
python agent.py --pr 123 --repo owner/repo
```

Analyze a feature description:

```bash
python agent.py --feature "dark mode settings panel" --repo owner/repo
```

## API Endpoints

### 1. Analyze PR / Feature
```http
GET /api/analyze
```

Query params:
- `mode=pr|feature`
- `value=<pr-number-or-feature-text>`
- `repo=owner/repo`
- `max=5`

### 2. Feature History
```http
GET /api/feature-history
```

Query params:
- `query=<feature-name>`
- `repo=owner/repo`
- `month=<1-12>` optional
- `year=<yyyy>` optional
- `max=20`

### 3. Review Insights
```http
GET /api/review-insights
```

Query params:
- `repo=owner/repo`
- `window=all|month`
- `limit=10`

## Example Use Cases

- “What changed for terminal-related features this year?”
- “Show feature history for authentication in January”


## Notes

- `.env` should **not** be committed.
- GitHub API search quality depends on repo data and query specificity.
- “Most visited PRs” is approximated using review/comment activity because GitHub does not expose direct PR view counts in the standard API.

## Suggested `.gitignore`

```gitignore
.env
.venv/
venv/
__pycache__/
*.pyc
*.pyo
*.pyd
dist/
build/
```

## Future Improvements

- Better semantic feature clustering
- Alias merging for similar feature names
- Smarter historical comparison across releases
- Richer report visualizations
- Better GitHub query fallbacks

