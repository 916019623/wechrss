FROM python:3.12-slim
LABEL org.opencontainers.image.title="WeRSS" \
      org.opencontainers.image.description="Self-hosted WeChat public account to RSS service" \
      org.opencontainers.image.licenses="MIT"
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN sed -i s@http://deb.debian.org@https://mirrors.tuna.tsinghua.edu.cn@g /etc/apt/sources.list.d/debian.sources
COPY requirements.txt ./
RUN pip install --no-cache-dir --index-url https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt \
    && PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright python -m playwright install --with-deps chromium
COPY . .
RUN mkdir -p /app/data
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=8s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=5)" || exit 1
CMD ["python", "web_app.py", "--host", "0.0.0.0", "--port", "8080"]
