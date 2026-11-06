FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir uv==0.9.26 && useradd --system --create-home boyun
WORKDIR /src
COPY engine/ /src/engine/
RUN uv sync --locked --project /src/engine --extra pdf --no-dev
ENV PATH="/src/engine/.venv/bin:${PATH}"
RUN mkdir -p /var/lib/boyun && chown boyun:boyun /var/lib/boyun
USER boyun
WORKDIR /var/lib/boyun
EXPOSE 8769
ENTRYPOINT ["decision-lab"]
CMD ["serve", "--port", "8769", "--output-dir", "/var/lib/boyun", "--container-bind"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8769/api/bootstrap', timeout=4).read(64)"]
