# ── Base image ────────────────────────────────────────────────
FROM python:3.12-slim

# ── Set working directory ──────────────────────────────────────
WORKDIR /app

# ── Install dependencies first (layer cache) ──────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Copy source code ───────────────────────────────────────────
COPY . .

# ── Expose port ────────────────────────────────────────────────
EXPOSE 5000

# ── Run with Waitress (pure Python, works on all platforms) ───
# --threads 8   → handle multiple users at the same time
CMD ["waitress-serve", "--host=0.0.0.0", "--port=5000", "--threads=8", "app:app"]
