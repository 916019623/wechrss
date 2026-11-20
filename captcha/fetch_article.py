# -*- coding: utf-8 -*-
"""用现有的有头浏览器（验证码那个）打开文章页，看能不能拿到正文。

服务端 IP 直接 requests 抓 mp 链接会被拦成「环境异常」，
但有头 Chrome 带完整指纹，通常能正常渲染。
"""
import base64
import importlib.util
import os
import sys
import time

CAP = "/app/captcha" if os.path.isdir("/app/captcha") else os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "captcha")


def load(n):
    sp = importlib.util.spec_from_file_location(n, os.path.join(CAP, n + ".py"))
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


cp = load("captcha_pc")
URL = sys.argv[1] if len(sys.argv) > 1 else (
    "https://mp.weixin.qq.com/s?__biz=MzA4MDQyMTkwMA==&mid=2651937060&idx=1&sn=ca2b64adfec07f83")

cp.kill_browser()
cp.open_page()
time.sleep(2)
c = cp.CDP()
c.send("Page.navigate", url=URL)
time.sleep(8)

info = c.eval("""(() => {
  const el = document.querySelector('#js_content') || document.querySelector('.rich_media_content');
  const t = document.body ? document.body.innerText : '';
  return JSON.stringify({hasContent: !!el, len: t.length, head: t.slice(0, 120)});
})()""")
print("页面信息:", info)

if info:
    import json
    d = json.loads(info)
    print("有正文容器:", d["hasContent"], "文本长度:", d["len"])
    print("开头:", d["head"].replace("\n", " ")[:100])

    if d["hasContent"]:
        text = c.eval("""(() => {
          const el = document.querySelector('#js_content') || document.querySelector('.rich_media_content');
          return el ? el.innerText : '';
        })()""")
        print("正文长度:", len(text or ""))
        print("正文前 200:", (text or "")[:200].replace("\n", " "))
        open("/app/captcha_work/article_text.txt", "w", encoding="utf-8").write(text or "")
        print("已保存到 /app/captcha_work/article_text.txt")

cp.kill_browser()
