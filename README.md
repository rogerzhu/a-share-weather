# 仅供娱乐

# A 股晴雨表

什么时候跑都行。外面的市场还在交易，就用正在走的涨跌幅；已经收盘，就用最近一个交易日的收盘。灯多的那边叫晴，灯少的那边叫雨。它数的是清单，不是 K 线里的未来。

满足率不是上涨概率，更不能换成满仓或清仓。拿它下单，娱乐精神就用超了。

只需要 Python 3.9+ 标准库，没有第三方包，也不用 API Key。

## 直接跑

在本目录执行：

```bash
python3 scripts/weather.py
python3 scripts/weather.py --date 2026-10-20
python3 scripts/weather.py --json
```

交易日当天 15:00（北京时间）之前，目标日就是今天。过了 15:00，或者今天休市，才跳到下一个深交所开市日。

不在本目录时，相对路径会找不到脚本，换成它的绝对路径。

## 装进编程助手

跟哪家助手无关。认技能的工具，都是扫一个目录，找里面的 `SKILL.md`。把本目录整份放进去，名字用 `a-share-weather`，`scripts/weather.py` 留在 `SKILL.md` 旁边。只拷说明文件，助手会找不到脚本。

```bash
mkdir -p <技能目录>
cp -R . <技能目录>/a-share-weather
```

`<技能目录>` 换成这个工具自己的技能文件夹。两个常见例子：

```bash
# Cursor
mkdir -p ~/.cursor/skills
cp -R . ~/.cursor/skills/a-share-weather

# Claude Code
mkdir -p ~/.claude/skills
cp -R . ~/.claude/skills/a-share-weather
```

工具把技能放在项目里时，同样整份拷进那个项目的技能目录。它不自动扫目录、只吃一段说明时，把这个文件夹加进上下文，让它按 `SKILL.md` 运行旁边的 `scripts/weather.py`。

没有助手也可以，上面「直接跑」就够了。脚本不调用 Cursor 或 Claude 的接口，本机有 Python 3.9+ 并且能上网即可。

## 输出长什么样

文本里有：目标交易日、取数时间、天气和满足率、不含宏观的那一行、打了分的条目、记灰的条目。`--json` 是同一份内容。

| 灯 | 得分 |
|----|------|
| 绿 | 1 |
| 黄 | 0.5 |
| 红 | 0 |
| 灰 | 不进分母，当场离席 |

| 满足率 | 天气 |
|--------|------|
| ≥ 75% | 晴 |
| ≥ 55% | 多云 |
| ≥ 40% | 阴 |
| < 40% | 雨 |

## 打分规则

| 条目 | 数据 | 规则 |
|------|------|------|
| 美股 | 新浪 `gb_inx`、`gb_ixic` | 美东 9:30–16:00 用盘中涨跌幅，其余时间用最近收盘。标普和纳指取更差的那个：≥0 绿，跌幅不到 1 个点黄，否则红 |
| 日股 / 韩股 | `b_NKY`、`b_KOSPI` | 东京 9:00–11:30、12:30–15:00，首尔 9:00–15:30，开盘用盘中，收盘用最近一个交易日收盘。涨跌规则同美股 |
| VIXY | `gb_vixy` | 跟美股同一时段。日涨 ≥5% 红，≥3% 黄 |
| 汇率 | `fx_susdcny`、`fx_susdjpy`、`fx_seurusd` | 人民币涨跌幅不到 0.3% 绿、不到 0.8% 黄；日元或欧元涨跌幅超过 1% 红 |
| 原油 | `hf_CL` | 较前收上涨超过 2% 红，超过 1% 黄 |
| 黄金 | `nf_AU0` | 较昨结算上涨超过 2% 红，超过 1% 黄 |
| 比特币 | `hf_BTC` | 较前收下跌达到 5% 红，达到 3% 黄 |
| 交割日 / 月底 | 深交所日历 | 当月第三个周五，或当月最后两个交易日，红 |
| 季末 / 年末 | 深交所日历 | 3、6、9、12 月最后五个交易日，红 |
| 美国数据 | 华尔街见闻宏观日历 | 近 21 天里，非农和实际 GDP 不低于预期算好，CPI、PPI 同比不高于预期算好。差的比好的多则红，反过来绿，打平黄 |
| 中国数据 | 同上 | 官方制造业 PMI ≥50 为绿；若同时 M1 低于前值，这一行改黄 |
| PMI | 同上 | 官方制造业 PMI ≥50 为绿。和「中国数据」各算一次 |
| M1 / M2 | 同上 | M1 低于前值为红。和「中国数据」里的 M1 各算一次 |

成交额、北向、龙头、涨停不在这张表里。它们要开盘以后才有，硬算就是提前剧透。

## 常见误会

**开盘和收盘用的不是同一根数？**  
美股、VIXY、日经、韩股：这个市场正在交易，就用正在走的涨跌幅；已经收盘，就用行情上最近一个交易日的收盘。没有涨跌幅才记灰。周末算收盘。

**VIXY 怎么有时整行是灰的？**  
新浪没给涨跌幅。有数字就按日涨打灯：≥5% 红，≥3% 黄。文件是 `scripts/weather.py`，没有 `SKILL.py`。

**晴了是不是明天会涨？**  
不会。75% 只说明清单里绿灯比较多。天气和指数之间没有签约。

**能换数据源吗？**  
脚本已经在用新浪和华尔街见闻。助手按 `SKILL.md` 运行这份脚本就行，不必另写一套。

**关键词能改吗？**  
改 `SKILL.md` 开头的 `description`。助手靠这段文字决定要不要动手。

**断网能跑吗？**  
不能。标准库只省了安装，没省网线。

## 目录

```text
a-share-weather-skills/
├── SKILL.md
├── README.md
├── LICENSE
├── .gitignore
├── docs/
│   └── v2.0-changes.md
└── scripts/
    └── weather.py
```

`weather.py` 里没有把美股、日经、韩股合成一行。三条各过各的日子。

## 发到 GitHub

在本目录单独建库，不要推进 `a-stock-data`。

```bash
git init
git add .
git commit -m "Publish the A-share weather skill."
git branch -M main
git remote add origin git@github.com:rogerzhu/a-share-weather.git
git push -u origin HEAD
```

仓库地址：[github.com/rogerzhu/a-share-weather](https://github.com/rogerzhu/a-share-weather)。

## 许可

[Apache License 2.0](./LICENSE)。
