#!/bin/sh
# 验证码自检：连跑 N 轮，统计真票（t03）与被拒（terror）
#
# 用法: sh scripts/captcha_test.sh [轮数]
#
# 判读：t03 开头才是真票；terror_1007 表示腾讯判定为机器，需要检查伪装是否生效。
set -e

N="${1:-2}"
CONTAINER="${CONTAINER:-wechrss-main-wechat-mp-fetcher-1}"
TMP=$(mktemp)

echo "=== 环境自检 ==="
docker exec "$CONTAINER" /usr/local/bin/python /app/captcha/captcha_pc.py check 2>&1 | tail -8

i=1
while [ "$i" -le "$N" ]; do
  echo "---- 第 $i 轮 ----"
  docker exec "$CONTAINER" /usr/local/bin/python /app/captcha/auto_unlock.py --wait 150 2>&1 \
    | grep -E "拿到 ticket|未拿到 ticket" | tee -a "$TMP"
  i=$((i + 1))
done

echo "=== 统计 ==="
echo "真票(t03)   : $(grep -c 'ticket: t0' "$TMP" || true)"
echo "被拒(terror): $(grep -c 'ticket: terror' "$TMP" || true)"
rm -f "$TMP"

echo "=== 进程数（应保持在两位数）==="
docker stats --no-stream --format 'pids={{.PIDs}} mem={{.MemUsage}}' "$CONTAINER"
