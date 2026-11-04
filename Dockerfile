FROM python:3.12-slim
LABEL org.opencontainers.image.title="WeRSS" \
      org.opencontainers.image.description="Self-hosted WeChat public account to RSS service" \
      org.opencontainers.image.licenses="MIT"
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV CHROME_PATH=/usr/bin/chromium \
    CAPTCHA_HEADLESS=0 \
    CAPTCHA_WORK=/app/captcha_work \
    DISPLAY=:99
RUN sed -i s@http://deb.debian.org@https://mirrors.tuna.tsinghua.edu.cn@g /etc/apt/sources.list.d/debian.sources
# chromium + 中文字体 + Xvfb（验证码需要有头浏览器）
RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb x11-utils fonts-noto-cjk chromium \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir --index-url https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
COPY . .
RUN mkdir -p /app/data /app/captcha_work
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=8s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=5)" || exit 1
# Xvfb 提供虚拟显示，让 Chromium 以「有头」方式运行（验证码难度更低）
CMD ["sh", "-c", "Xvfb :99 -screen 0 1280x1400x24 >/tmp/xvfb.log 2>&1 & sleep 2; exec python web_app.py --host 0.0.0.0 --port 8080"]
