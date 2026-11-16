FROM python:3.12-slim
# EPICENTRE: stateless FastAPI app. No secrets in this image: credentials come from the EC2 instance role
# (IMDSv2) or from the environment at `docker run` time; the password is EPICENTRE_PASSWORD and the origin secret is
# EPICENTRE_ORIGIN_SECRET, environment only (docs/deploy.md).
# Licensed data (data/starter, data/etf_holdings.csv) is never baked in: mount it read-only (docs/deploy.md).
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN useradd --create-home --uid 10001 epicentre && chown -R epicentre /app/data
USER epicentre
EXPOSE 8000
# /api/health is exempt from the password, so the probe sends no credentials.
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"
# 0.0.0.0 is the container's own interface; the host publishes the port (docs/deploy.md).
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
