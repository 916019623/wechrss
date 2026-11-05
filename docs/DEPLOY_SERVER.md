# 服务器部署与运维

面向 Linux 服务器（Docker），本文档只描述操作，不包含任何凭据。

## 目录约定

```
/appdata/wechrss-main            代码 + docker-compose.yml
/appdata/wechrss-main/data       数据卷：wechat_mp.db、credentials.json
/appdata/wechrss-main/captcha_work  验证码截图与日志（排查用）
/appdata/werss-backups           数据备份
```

## 首次部署

```bash
# 1. 拉代码（国内直连 GitHub 会超时，用镜像）
git clone https://gh-proxy.com/https://github.com/916019623/wechrss.git /appdata/wechrss-main
cd /appdata/wechrss-main

# 2. 启动
docker compose up -d --build

# 3. 健康检查
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/
```

服务默认只监听 `127.0.0.1:8080`，对外请用 Nginx 反代或 SSH 隧道。

## 日常更新

```bash
sh scripts/deploy.sh
```

脚本会：清理冲突文件 → `git pull`（镜像）→ `docker compose up -d --build` → 等健康检查。

## 状态巡检

```bash
sh scripts/status.sh
```

输出：文章总数、各源状态与下次同步时间、最近同步结果、Webhook 状态、容器资源。

## 验证码自检

```bash
sh scripts/captcha_test.sh 2      # 跑 2 轮
```

判读要点：

| 出票 | 含义 |
|---|---|
| `t03tserver...` | 真票，腾讯认可 |
| `terror_1007_...` | 被判定为机器，答案对也没用 |

出现 `terror` 时依次检查：

1. `DISPLAY` 是否设置、Xvfb 是否在跑（有头模式）
2. `CAPTCHA_HEADLESS` 是否为 0
3. 行为伪装是否生效（鼠标轨迹、UA、时区）
4. 容器进程数是否异常增长（泄漏会导致 `Cannot fork`）

## 容器内环境说明

镜像基于 `python:3.12-slim`，额外安装：

```
chromium            验证码用的浏览器
Xvfb :99            虚拟显示器，让 Chromium 以有头模式运行
fonts-noto-cjk      中文字体（缺字会渲染成方块）
```

环境变量（Dockerfile 内置）：

```
CHROME_PATH=/usr/bin/chromium
CAPTCHA_HEADLESS=0
CAPTCHA_WORK=/app/captcha_work
DISPLAY=:99
```

## 常见问题

**容器 unhealthy，日志出现 `can't start new fork/thread`**
浏览器进程泄漏。确认 `captcha/auto_unlock.py` 的 `solve()` 带 `try/finally` 清理；
临时处理：`docker restart wechrss-main-wechat-mp-fetcher-1`。

**验证码一直返回 `terror_1007`**
行为伪装被识别。检查 UA、时区、鼠标轨迹是否生效（见上方自检）。

**同步报 `-2041`**
风控。正常会自动走解锁流程；若持续失败，看 `captcha_work/auto_unlock.log`。

**GitHub 直连超时**
属预期，使用 `gh-proxy.com` 镜像作为 origin。
