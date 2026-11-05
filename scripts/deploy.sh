#!/bin/sh
# 服务器更新与重建：拉取最新代码 → 重建镜像 → 健康检查
#
# 用法（在服务器上执行）:
#   sh scripts/deploy.sh
#
# 说明：服务器在国内直连 GitHub 会超时，远程 origin 使用镜像地址。
#       若镜像变更，改 REMOTE 即可。
set -e

REMOTE="${REMOTE:-https://gh-proxy.com/https://github.com/916019623/wechrss.git}"
DIR="${DIR:-/appdata/wechrss-main}"
CONTAINER="${CONTAINER:-wechrss-main-wechat-mp-fetcher-1}"

cd "$DIR"

echo "=== 1. 记录当前版本 ==="
git log --oneline -1

echo "=== 2. 清理会与远端冲突的本地文件 ==="
git checkout -- . 2>/dev/null || true
rm -f captcha/one_round_inspect.py captcha/diag_page.py captcha/submit_only.py \
      captcha/click_test.py captcha/refresh_test.py captcha/capture_only.py \
      captcha/flow_once.py 2>/dev/null || true

echo "=== 3. 拉取代码 ==="
git remote set-url origin "$REMOTE" 2>/dev/null || true
GIT_TERMINAL_PROMPT=0 git pull --ff-only 2>&1 | tail -5
git log --oneline -1

echo "=== 4. 重建并启动 ==="
docker compose up -d --build 2>&1 | tail -3

echo "=== 5. 健康检查（最多等 60 秒）==="
i=0
while [ $i -lt 12 ]; do
  sleep 5
  i=$((i+1))
  status=$(docker inspect -f '{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null || echo unknown)
  [ "$status" = "healthy" ] && break
done
echo "容器状态: $status"
docker stats --no-stream --format 'pids={{.PIDs}} mem={{.MemUsage}}' "$CONTAINER"
curl -s -o /dev/null -w "http=%{http_code}\n" http://127.0.0.1:8080/ || true
