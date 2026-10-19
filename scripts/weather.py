#!/usr/bin/env python3
"""下一交易日 A 股盘前晴雨。只使用标准库。

满足率是已打分条件的得分占比，不是上涨概率。
盘中才有的成交额、北向、龙头不进这张表。
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

CN = timezone(timedelta(hours=8))
UA = "Mozilla/5.0"
SINA = "https://hq.sinajs.cn/list="
WSCN = "https://api-one-wscn.awtmt.com/apiv1/finance/macrodatas"
SZSE = "https://www.szse.cn/api/report/exchange/onepersistenthour/monthList"


def fetch(url: str, referer: str | None = None, timeout: int = 20) -> bytes:
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def num(value) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace("%", "").replace(",", "")
    if text in ("", "--", "None"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def light_equity(pct: float | None):
    """涨为绿，跌幅小于 1 个点为黄，否则红。pct 单位是百分点。"""
    if pct is None:
        return None, None
    if pct >= 0:
        return "绿", 1.0
    if pct > -1:
        return "黄", 0.5
    return "红", 0.0


def weather_name(rate: float | None) -> str:
    if rate is None:
        return "无数据"
    if rate >= 0.75:
        return "晴"
    if rate >= 0.55:
        return "多云"
    if rate >= 0.40:
        return "阴"
    return "雨"


def sina_map(codes: list[str]) -> dict[str, list[str]]:
    url = SINA + ",".join(codes)
    text = fetch(url, referer="https://finance.sina.com.cn/").decode("gbk", "replace")
    out = {}
    for line in text.split(";"):
        line = line.strip()
        if "hq_str_" not in line or '"' not in line:
            continue
        key = line.split("hq_str_", 1)[1].split("=", 1)[0]
        body = line.split('"', 2)[1]
        out[key] = body.split(",") if body else []
    return out


def pct_change(last, prev) -> float | None:
    last_n, prev_n = num(last), num(prev)
    if last_n is None or prev_n in (None, 0):
        return None
    return (last_n - prev_n) / prev_n * 100


def trading_days(year: int, month: int) -> list[str]:
    raw = fetch(f"{SZSE}?month={year}-{month:02d}").decode("utf-8")
    data = json.loads(raw).get("data") or []
    days = []
    for row in data:
        if str(row.get("jybz")) == "1" and row.get("jyrq"):
            days.append(str(row["jyrq"])[:10])
    return sorted(days)


def month_days(year: int, month: int) -> list[str]:
    if month == 0:
        year, month = year - 1, 12
    if month == 13:
        year, month = year + 1, 1
    try:
        return trading_days(year, month)
    except Exception:
        return []


def next_session(today: datetime) -> tuple[str, str]:
    """今天仍是交易日且未收盘，目标就是今天；否则取下一个开市日。"""
    y, m = today.year, today.month
    opens = set(month_days(y, m) + month_days(y, m + 1) + month_days(y, m - 1))
    day = today.date().isoformat()
    if day in opens and (today.hour, today.minute) < (9, 30):
        return day, "今天尚未开盘"
    if day in opens and (today.hour, today.minute) < (15, 0):
        return day, "今天已开盘，外面的市场按各自是否在交易取值"
    cursor = today.date() + timedelta(days=1)
    for _ in range(16):
        if cursor.isoformat() in opens:
            return cursor.isoformat(), "下一开市日的盘前"
        cursor += timedelta(days=1)
    raise RuntimeError("深交所日历里找不到下一个开市日")


def us_session_date(stamp: str) -> str | None:
    """新浪美股时间是北京时间。21:30 后是当晚那一盘；凌晨印出的收盘属于前一个美股交易日。"""
    try:
        quoted = datetime.strptime(stamp.strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    if quoted.hour >= 21:
        return quoted.date().isoformat()
    return (quoted.date() - timedelta(days=1)).isoformat()


def in_session(now: datetime, tz_name: str, windows: list[tuple[int, int, int, int]]) -> bool:
    """windows 是交易所当地时间的 [开, 收) 分钟窗口。周末视为已收盘。"""
    local = now.astimezone(ZoneInfo(tz_name))
    if local.weekday() >= 5:
        return False
    minute = local.hour * 60 + local.minute
    return any(start_h * 60 + start_m <= minute < end_h * 60 + end_m for start_h, start_m, end_h, end_m in windows)


US_SESSION = [(9, 30, 16, 0)]
JP_SESSION = [(9, 0, 11, 30), (12, 30, 15, 0)]
KR_SESSION = [(9, 0, 15, 30)]


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "无"
    return f"{value:+.2f}%"


def third_friday(year: int, month: int) -> str:
    first = datetime(year, month, 1)
    offset = (4 - first.weekday()) % 7
    day = 1 + offset + 14
    return datetime(year, month, day).date().isoformat()


def macro_between(start, end) -> list[dict]:
    items = []
    cursor = start
    while cursor <= end:
        stop = min(cursor + timedelta(days=6), end)
        begin = int(datetime(cursor.year, cursor.month, cursor.day, tzinfo=CN).timestamp())
        finish = int(datetime(stop.year, stop.month, stop.day, 23, 59, 59, tzinfo=CN).timestamp())
        payload = json.loads(fetch(f"{WSCN}?start={begin}&end={finish}").decode("utf-8"))
        if payload.get("code") != 20000:
            raise RuntimeError(f"宏观日历返回 {payload.get('code')}")
        batch = (payload.get("data") or {}).get("items") or []
        for item in batch:
            stamp = item.get("public_date")
            when = datetime.fromtimestamp(stamp, CN) if isinstance(stamp, (int, float)) else None
            if when is None or not (cursor <= when.date() <= stop):
                continue
            items.append({
                "time": when.strftime("%Y-%m-%d"),
                "country": item.get("country") or "",
                "title": item.get("title") or "",
                "actual": num(item.get("actual")),
                "forecast": num(item.get("forecast")),
                "previous": num(item.get("previous")),
                "importance": item.get("importance") or 0,
            })
        cursor = stop + timedelta(days=1)
    return items


def latest(items: list[dict], country: str, needle: str) -> dict | None:
    found = [it for it in items if it["country"] == country and needle in it["title"]]
    return max(found, key=lambda it: it["time"]) if found else None


def row(name: str, detail: str, color: str | None, score: float | None, group: str) -> dict:
    return {"name": name, "detail": detail, "light": color or "灰", "score": score, "group": group}


def score_us_macro(items: list[dict], today) -> dict:
    """越高越好：非农、实际 GDP。越低越好：CPI/PPI 同比。只看有公布值和预期的条目。"""
    cutoff = (today.date() - timedelta(days=21)).isoformat()
    higher = ("非农", "实际GDP")
    lower_needles = ("CPI同比", "PPI同比")
    judged = []
    for it in items:
        if it["country"] != "美国" or it["time"] < cutoff:
            continue
        if it["actual"] is None or it["forecast"] is None or it["importance"] < 2:
            continue
        title = it["title"]
        if any(k in title for k in higher):
            good = it["actual"] >= it["forecast"]
        elif any(k in title for k in lower_needles):
            good = it["actual"] <= it["forecast"]
        else:
            continue
        judged.append((good, it))
    if not judged:
        return row("美国数据", "近 21 天没有可对照预期的条目", None, None, "宏观")
    beats = sum(1 for good, _ in judged if good)
    misses = len(judged) - beats
    bits = []
    for good, it in sorted(judged, key=lambda pair: pair[1]["time"])[-4:]:
        mark = "好于或持平预期" if good else "差于预期"
        bits.append(f"{it['title']} {it['actual']:g}（预期 {it['forecast']:g}，{mark}）")
    detail = "；".join(bits)
    if misses > beats:
        return row("美国数据", detail, "红", 0.0, "宏观")
    if beats > misses:
        return row("美国数据", detail, "绿", 1.0, "宏观")
    return row("美国数据", detail, "黄", 0.5, "宏观")


def score_china(items: list[dict]):
    pmi = latest(items, "中国", "官方制造业PMI")
    m1 = latest(items, "中国", "M1货币供应同比")
    m2 = latest(items, "中国", "M2货币供应同比")
    cpi = latest(items, "中国", "CPI同比")
    ppi = latest(items, "中国", "PPI同比")

    if pmi is None or pmi["actual"] is None:
        pmi_row = row("PMI", "没有官方制造业 PMI 公布值", None, None, "宏观")
        china = row("中国数据", "没有官方制造业 PMI", None, None, "宏观")
    else:
        prev = f"，前值 {pmi['previous']:g}" if pmi["previous"] is not None else ""
        detail = f"{pmi['time']} {pmi['title']} {pmi['actual']:g}{prev}"
        color, score = ("绿", 1.0) if pmi["actual"] >= 50 else ("红", 0.0)
        pmi_row = row("PMI", detail, color, score, "宏观")
        if m1 and m1["actual"] is not None and m1["previous"] is not None and m1["actual"] < m1["previous"] and color == "绿":
            china = row(
                "中国数据",
                detail + f"；M1 {m1['actual']:g} 低于前值 {m1['previous']:g}",
                "黄",
                0.5,
                "宏观",
            )
        else:
            china = row("中国数据", detail, color, score, "宏观")

    if not m1 or m1["actual"] is None or m1["previous"] is None or not m2 or m2["actual"] is None:
        money = row("M1 / M2", "货币供应公布值不齐", None, None, "宏观")
    else:
        m2_prev = f"{m2['previous']:g}" if m2["previous"] is not None else "—"
        detail = f"M2 {m2['actual']:g}（前值 {m2_prev}），M1 {m1['actual']:g}（前值 {m1['previous']:g}）"
        if m1["actual"] < m1["previous"]:
            money = row("M1 / M2", detail + "，M1 没有改善", "红", 0.0, "宏观")
        elif m2["actual"] > 0:
            money = row("M1 / M2", detail, "绿", 1.0, "宏观")
        else:
            money = row("M1 / M2", detail + "，M2 同比不为正", "红", 0.0, "宏观")

    if not cpi or cpi["actual"] is None or not ppi or ppi["actual"] is None:
        prices = row("CPI / PPI", "公布值为空，不进分", None, None, "宏观")
    else:
        ok = 0 <= cpi["actual"] <= 3 and ppi["actual"] > -2
        detail = f"CPI {cpi['actual']:g}%，PPI {ppi['actual']:g}%"
        prices = row("CPI / PPI", detail, "绿" if ok else "红", 1.0 if ok else 0.0, "宏观")
    return china, pmi_row, money, prices


def build(target: str | None = None) -> dict:
    now = datetime.now(CN)
    notes = []
    if target:
        session, when_note = target, "指定交易日的盘前"
    else:
        session, when_note = next_session(now)
    y, m, _d = (int(x) for x in session.split("-"))
    opens = month_days(y, m)
    if opens and session not in opens:
        notes.append(f"{session} 不在深交所开市日里")

    quotes = sina_map([
        "gb_inx", "gb_ixic", "gb_dji", "b_NKY", "b_KOSPI",
        "fx_susdcny", "fx_susdjpy", "fx_seurusd",
        "hf_CL", "nf_AU0", "hf_BTC", "gb_vixy",
    ])

    def parts(code: str) -> list[str]:
        return quotes.get(code) or []

    def us_close(code: str):
        p = parts(code)
        pct = num(p[2] if len(p) > 2 else None)
        stamp = p[3] if len(p) > 3 else ""
        return pct, us_session_date(stamp), stamp

    spx_pct, spx_day, _spx_stamp = us_close("gb_inx")
    ndx_pct, ndx_day, _ndx_stamp = us_close("gb_ixic")
    known = [x for x in (spx_pct, ndx_pct) if x is not None]
    if not known:
        us = row("美股", "标普和纳指都没有涨跌幅", None, None, "隔夜")
    else:
        worse = min(known)
        color, score = light_equity(worse)
        us_today = now.astimezone(ZoneInfo("America/New_York")).date().isoformat()
        if in_session(now, "America/New_York", US_SESSION) and us_today in (spx_day, ndx_day):
            state = "盘中"
        else:
            state = f"{spx_day or ndx_day or '最近'} 收盘"
        us = row(
            "美股",
            f"{state} 标普 {fmt_pct(spx_pct)}，纳指 {fmt_pct(ndx_pct)}（取更差的 {worse:+.2f}%）",
            color,
            score,
            "隔夜",
        )

    def asia(code: str, label: str, tz_name: str, windows: list[tuple[int, int, int, int]]) -> dict:
        """开盘用正在交易的涨跌幅，收盘用行情上最近一个交易日的收盘。"""
        p = parts(code)
        pct = num(p[3] if len(p) > 3 else None)
        day = (p[6] if len(p) > 6 else "").strip()
        if pct is None or not day or "没有交易" in day:
            return row(label, "没有涨跌幅", None, None, "当天")
        name = p[0] if p else label
        local_day = now.astimezone(ZoneInfo(tz_name)).date().isoformat()
        if in_session(now, tz_name, windows) and day == local_day:
            state = f"{name} 盘中 {pct:+.2f}% {day}"
        else:
            state = f"{name} {day} 收盘 {pct:+.2f}%"
        color, score = light_equity(pct)
        return row(label, state, color, score, "当天")

    jp = asia("b_NKY", "日股", "Asia/Tokyo", JP_SESSION)
    kr = asia("b_KOSPI", "韩股", "Asia/Seoul", KR_SESSION)

    def fx_pct(code: str) -> float | None:
        p = parts(code)
        if len(p) <= 8:
            return None
        return pct_change(p[3], p[8])

    cny, jpy, eur = fx_pct("fx_susdcny"), fx_pct("fx_susdjpy"), fx_pct("fx_seurusd")
    if None in (cny, jpy, eur):
        fx = row("汇率", "美元人民币、美元日元或欧元美元缺字段", None, None, "隔夜")
    else:
        detail = f"人民币 {cny:+.2f}%，美元日元 {jpy:+.2f}%，欧元美元 {eur:+.2f}%"
        if abs(jpy) > 1 or abs(eur) > 1:
            fx = row("汇率", detail + "，日元或欧元日波幅超过 1%", "红", 0.0, "隔夜")
        elif abs(cny) < 0.3:
            fx = row("汇率", detail, "绿", 1.0, "隔夜")
        elif abs(cny) < 0.8:
            fx = row("汇率", detail, "黄", 0.5, "隔夜")
        else:
            fx = row("汇率", detail + "，人民币日波幅达到 0.8%", "红", 0.0, "隔夜")

    oil_p = parts("hf_CL")
    oil_pct = pct_change(oil_p[0] if oil_p else None, oil_p[7] if len(oil_p) > 7 else None)
    if oil_pct is None:
        oil = row("原油", "纽约原油缺价格", None, None, "隔夜")
    else:
        detail = f"纽约原油 {num(oil_p[0]):.2f}，较前收 {oil_pct:+.2f}%"
        if len(oil_p) > 12:
            detail += f"，日期 {oil_p[12]}"
        if oil_pct > 2:
            oil = row("原油", detail, "红", 0.0, "隔夜")
        elif oil_pct > 1:
            oil = row("原油", detail, "黄", 0.5, "隔夜")
        else:
            oil = row("原油", detail, "绿", 1.0, "隔夜")

    gold_p = parts("nf_AU0")
    gold_pct = pct_change(gold_p[8] if len(gold_p) > 10 else None, gold_p[10] if len(gold_p) > 10 else None)
    if gold_pct is None:
        gold = row("黄金", "沪金主力缺结算价", None, None, "隔夜")
    else:
        detail = f"沪金主力 {num(gold_p[8]):.2f}，较昨结算 {gold_pct:+.2f}%"
        if gold_pct > 2:
            gold = row("黄金", detail, "红", 0.0, "隔夜")
        elif gold_pct > 1:
            gold = row("黄金", detail, "黄", 0.5, "隔夜")
        else:
            gold = row("黄金", detail, "绿", 1.0, "隔夜")

    btc_p = parts("hf_BTC")
    btc_pct = pct_change(btc_p[0] if btc_p else None, btc_p[7] if len(btc_p) > 7 else None)
    if btc_pct is None:
        btc = row("比特币", "比特币期货缺价格", None, None, "隔夜")
    else:
        detail = f"比特币期货 {num(btc_p[0]):.0f}，较前收 {btc_pct:+.2f}%"
        if btc_pct <= -5:
            btc = row("比特币", detail, "红", 0.0, "隔夜")
        elif btc_pct <= -3:
            btc = row("比特币", detail, "黄", 0.5, "隔夜")
        else:
            btc = row("比特币", detail, "绿", 1.0, "隔夜")

    vix_p = parts("gb_vixy")
    vix_pct = num(vix_p[2] if len(vix_p) > 2 else None)
    vix_day = us_session_date(vix_p[3]) if len(vix_p) > 3 else None
    if vix_pct is None:
        vix = row("VIXY", "没有涨跌幅", None, None, "隔夜")
    else:
        price = num(vix_p[1])
        price_bit = f"{price:.2f}，" if price is not None else ""
        us_today = now.astimezone(ZoneInfo("America/New_York")).date().isoformat()
        if in_session(now, "America/New_York", US_SESSION) and vix_day == us_today:
            state = "盘中"
        else:
            state = f"{vix_day or '最近'} 收盘"
        detail = f"{state} ProShares 短期期货恐慌 ETF {price_bit}{vix_pct:+.2f}%"
        if vix_pct >= 5:
            vix = row("VIXY", detail, "红", 0.0, "隔夜")
        elif vix_pct >= 3:
            vix = row("VIXY", detail, "黄", 0.5, "隔夜")
        else:
            vix = row("VIXY", detail, "绿", 1.0, "隔夜")

    friday = third_friday(y, m)
    month_end = set(opens[-2:]) if len(opens) >= 2 else set()
    hit_16 = session == friday or session in month_end
    why = []
    if session == friday:
        why.append("股指交割日（当月第三个周五）")
    if session in month_end:
        why.append("月末最后两个交易日")
    cal16 = row(
        "交割日 / 月底",
        "、".join(why) if why else f"不是交割日（{friday}），也不是月末",
        "红" if hit_16 else "绿",
        0.0 if hit_16 else 1.0,
        "日历",
    )

    quarter = m in (3, 6, 9, 12)
    q_end = set(opens[-5:]) if quarter and len(opens) >= 5 else set()
    hit_17 = session in q_end
    cal17 = row(
        "季末 / 年末",
        "落在 3/6/9/12 月最后五个交易日" if hit_17 else "不是季末或年末窗口",
        "红" if hit_17 else "绿",
        0.0 if hit_17 else 1.0,
        "日历",
    )

    end = now.date()
    start = end - timedelta(days=24)
    try:
        items = macro_between(start, end)
    except Exception as exc:
        items = []
        notes.append(f"宏观日历没有取到：{exc}")
    if items:
        china, pmi_row, money, prices = score_china(items)
        us_macro = score_us_macro(items, now)
    else:
        blank = "宏观日历为空"
        china = row("中国数据", blank, None, None, "宏观")
        pmi_row = row("PMI", blank, None, None, "宏观")
        money = row("M1 / M2", blank, None, None, "宏观")
        prices = row("CPI / PPI", blank, None, None, "宏观")
        us_macro = row("美国数据", blank, None, None, "宏观")

    rows = [us, kr, jp, fx, oil, gold, btc, vix, cal16, cal17, us_macro, china, pmi_row, money, prices]
    scored = [r for r in rows if r["score"] is not None]
    overnight = [r for r in scored if r["group"] in ("隔夜", "当天", "日历")]
    total = sum(r["score"] for r in scored)
    night = sum(r["score"] for r in overnight)
    rate = total / len(scored) if scored else None
    night_rate = night / len(overnight) if overnight else None
    return {
        "as_of": now.strftime("%Y-%m-%d %H:%M"),
        "session": session,
        "when": when_note,
        "weather": weather_name(rate),
        "score": round(total, 1),
        "counted": len(scored),
        "rate": None if rate is None else round(rate, 4),
        "overnight_weather": weather_name(night_rate),
        "overnight_score": round(night, 1),
        "overnight_counted": len(overnight),
        "overnight_rate": None if night_rate is None else round(night_rate, 4),
        "rows": rows,
        "notes": notes,
    }


def render(report: dict) -> str:
    rate = report["rate"]
    night = report["overnight_rate"]
    lines = [
        f"目标交易日：{report['session']}（{report['when']}）",
        f"取数时间：{report['as_of']}",
    ]
    if rate is None:
        lines.append("盘前天气：无数据")
    else:
        lines.append(
            f"盘前天气：{report['weather']}    满足率 {rate * 100:.0f}%"
            f"（{report['score']:g} / {report['counted']}）"
        )
    if night is not None:
        lines.append(
            f"不含宏观：{report['overnight_weather']}    {night * 100:.0f}%"
            f"（{report['overnight_score']:g} / {report['overnight_counted']}）"
        )
    lines.append("")
    lines.append("打分")
    for item in report["rows"]:
        if item["score"] is None:
            continue
        lines.append(f"- {item['light']}  {item['name']}：{item['detail']}")
    gray = [item for item in report["rows"] if item["score"] is None]
    if gray:
        lines.append("")
        lines.append("未计入")
        for item in gray:
            lines.append(f"- 灰  {item['name']}：{item['detail']}")
    lines.append("")
    lines.append("这是条件满足率，不是上涨概率。VIXY 是短期 VIX 期货 ETF，日涨 ≥5% 记红、≥3% 记黄；现货 VIX 行情停更，不用。")
    lines.extend(report["notes"])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="A股下一交易日盘前晴雨")
    parser.add_argument("--date", help="指定目标交易日 YYYY-MM-DD，默认自动选下一开市日")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()
    try:
        report = build(args.date)
    except Exception as exc:
        print(f"取数失败：{exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
