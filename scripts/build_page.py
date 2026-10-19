#!/usr/bin/env python3
"""把 weather.py --json 的结果写成一页静态晴雨表。只使用标准库。"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

SKY = {
    "晴": ("#f6e7b8", "#8a5a12"),
    "多云": ("#e4ebf2", "#3d5166"),
    "阴": ("#e6e2d8", "#4e4a43"),
    "雨": ("#d5e0ea", "#1d3d57"),
    "无数据": ("#efeae2", "#4e4a43"),
}
LIGHT = {
    "绿": "#2f7d4a",
    "黄": "#b8860b",
    "红": "#b64032",
    "灰": "#8a847a",
}
GROUPS = ("隔夜", "当天", "日历", "宏观")


def pct(rate) -> str:
    if rate is None:
        return "—"
    return f"{rate * 100:.0f}%"


def points(score, counted) -> str:
    if score is None or not counted:
        return "没有可打分的条目"
    return f"{score:g} / {counted}"


def table_body(rows: list[dict]) -> str:
    body = []
    for row in rows:
        light = row.get("light") or "灰"
        color = LIGHT.get(light, LIGHT["灰"])
        body.append(
            "<tr>"
            f'<td class="light"><span class="dot" style="background:{color}"></span>{html.escape(light)}</td>'
            f"<td>{html.escape(row.get('name') or '')}</td>"
            f"<td>{html.escape(row.get('detail') or '')}</td>"
            "</tr>"
        )
    return "".join(body)


def rows_html(rows: list[dict]) -> str:
    picked = [row for row in rows if row["score"] is not None]
    if not picked:
        return ""
    seen = []
    for row in picked:
        group = row.get("group") or "其他"
        if group not in seen:
            seen.append(group)
    ordered = [name for name in GROUPS if name in seen] + [name for name in seen if name not in GROUPS]
    chunks = []
    for group in ordered:
        items = [row for row in picked if (row.get("group") or "其他") == group]
        chunks.append(
            f"<h2>{html.escape(group)}</h2><table><tbody>{table_body(items)}</tbody></table>"
        )
    return "\n".join(chunks)


def render(report: dict) -> str:
    weather = report.get("weather") or "无数据"
    wash, ink = SKY.get(weather, SKY["无数据"])
    notes = "".join(f"<p>{html.escape(str(note))}</p>" for note in report.get("notes") or [])
    all_rows = report.get("rows") or []
    scored = rows_html(all_rows)
    gray = [row for row in all_rows if row["score"] is None]
    gray_block = (
        f"<h2>未计入</h2><table><tbody>{table_body(gray)}</tbody></table>" if gray else ""
    )
    night = report.get("overnight_rate")
    night_line = ""
    if night is not None:
        night_line = (
            f"<p class='sub'>不含宏观：{html.escape(report.get('overnight_weather') or '')}"
            f" {pct(night)}（{points(report.get('overnight_score'), report.get('overnight_counted'))}）</p>"
        )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>A 股开盘晴雨表 · 仅供娱乐</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: #f3efe6;
    color: #1c1915;
    font-family: "PingFang SC", "Noto Sans SC", "Source Han Sans SC", sans-serif;
    line-height: 1.55;
  }}
  main {{
    max-width: 760px;
    margin: 0 auto;
    padding: 28px 20px 64px;
  }}
  .seal {{
    display: inline-block;
    margin: 0;
    padding: 4px 10px;
    border: 2px solid #b64032;
    color: #b64032;
    font-weight: 700;
    letter-spacing: 0.2em;
  }}
  h1 {{
    margin: 18px 0 6px;
    font-family: "Songti SC", "Noto Serif SC", "Source Han Serif SC", serif;
    font-size: 2rem;
    font-weight: 700;
    letter-spacing: 0.04em;
  }}
  .warn {{ margin: 0 0 22px; color: #5c5348; }}
  .board {{
    background: {wash};
    border: 1px solid #d9d1c3;
    padding: 22px 22px 16px;
  }}
  .weather {{
    margin: 0;
    font-family: "Songti SC", "Noto Serif SC", serif;
    font-size: 5.5rem;
    line-height: 1;
    color: {ink};
  }}
  .rate {{
    margin: 8px 0 0;
    font-size: 1.8rem;
    font-variant-numeric: tabular-nums;
  }}
  .meta, .sub {{ margin: 6px 0 0; color: #3f3a33; }}
  h2 {{
    margin: 28px 0 8px;
    font-size: 0.95rem;
    letter-spacing: 0.12em;
    color: #6b6258;
  }}
  table {{ width: 100%; border-collapse: collapse; }}
  td {{
    padding: 10px 8px 10px 0;
    border-bottom: 1px solid #e4ddd1;
    vertical-align: top;
  }}
  td.light {{ width: 4.2em; white-space: nowrap; font-weight: 650; }}
  .dot {{
    display: inline-block;
    width: 0.7em;
    height: 0.7em;
    margin-right: 0.4em;
    border-radius: 50%;
    vertical-align: -0.05em;
  }}
  footer {{
    margin-top: 28px;
    color: #6b6258;
    font-size: 0.92rem;
  }}
  footer p {{ margin: 0 0 8px; }}
</style>
</head>
<body>
<main>
  <p class="seal">仅供娱乐</p>
  <h1>A 股开盘晴雨表</h1>
  <p class="warn">满足率是清单里打了分的条件占了多少，不是上涨概率，也不能换成满仓或清仓。</p>
  <section class="board">
    <p class="weather">{html.escape(weather)}</p>
    <p class="rate">{pct(report.get("rate"))}　{html.escape(points(report.get("score"), report.get("counted")))}</p>
    <p class="meta">目标交易日 {html.escape(str(report.get("session") or ""))}（{html.escape(str(report.get("when") or ""))}）</p>
    <p class="meta">取数时间 {html.escape(str(report.get("as_of") or ""))}（北京时间）</p>
    {night_line}
  </section>
  <section>
    {scored}
  </section>
  {gray_block}
  <footer>
    <p>这是条件满足率，不是上涨概率。VIXY 是短期 VIX 期货 ETF，日涨 ≥5% 记红、≥3% 记黄。</p>
    {notes}
    <p>页面在北京时间每天 9:00 左右更新。GitHub 的定时器按 UTC 排队，晚到一会儿也正常。</p>
  </footer>
</main>
</body>
</html>
"""


def main() -> int:
    if len(sys.argv) != 3:
        print("用法：python3 scripts/build_page.py weather.json 输出目录", file=sys.stderr)
        return 2
    report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(render(report), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
