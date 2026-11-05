#!/bin/sh
# 查看采集与推送状态
#
# 用法: sh scripts/status.sh
set -e

DB="${DB:-/appdata/wechrss-main/data/wechat_mp.db}"
CONTAINER="${CONTAINER:-wechrss-main-wechat-mp-fetcher-1}"

python3 - "$DB" <<'PY'
import sqlite3, sys, time

c = sqlite3.connect(sys.argv[1])
c.row_factory = sqlite3.Row

print("=== 文章总数 ===")
print(" ", c.execute("select count(*) from articles").fetchone()[0])

print("=== 源状态 ===")
for r in c.execute("select id,name,last_status,last_sync_at,next_sync_at from sources order by id"):
    last = time.strftime("%m-%d %H:%M", time.localtime(r["last_sync_at"])) if r["last_sync_at"] else "-"
    nxt = time.strftime("%H:%M", time.localtime(r["next_sync_at"])) if r["next_sync_at"] else "-"
    print(f"  {r['id']} {r['name']:10s} {r['last_status']:12s} last={last} next={nxt}")

print("=== 最近同步 ===")
for r in c.execute("select id,source_id,status,received,new_count,message from sync_runs order by id desc limit 6"):
    print(f"  #{r['id']} 源{r['source_id']} {r['status']} 收{r['received']} 新{r['new_count']} {(r['message'] or '')[:50]}")

print("=== 推送 ===")
for r in c.execute("select id,event_type,enabled,last_status,last_error,last_triggered_at from webhooks"):
    t = time.strftime("%m-%d %H:%M", time.localtime(r["last_triggered_at"])) if r["last_triggered_at"] else "-"
    print(f"  #{r['id']} {r['event_type']} enabled={r['enabled']} {r['last_status']} at {t} {(r['last_error'] or '')[:40]}")
PY

echo "=== 容器资源 ==="
docker stats --no-stream --format 'pids={{.PIDs}} mem={{.MemUsage}} cpu={{.CPUPerc}}' "$CONTAINER"
