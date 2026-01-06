import json
from dataclasses import dataclass
from datetime import datetime, date as _date, time as _time
from typing import Any, Dict, List, Tuple

import pytz
import streamlit as st
from lunar_python import Solar


# =========================
# 1) 四柱计算
# =========================
@dataclass(frozen=True)
class Pillars:
    year_gz: str
    month_gz: str
    day_gz: str
    hour_gz: str
    day_master: str  # 日干


def get_pillars(dt_local: datetime) -> Pillars:
    solar = Solar.fromYmdHms(
        dt_local.year, dt_local.month, dt_local.day,
        dt_local.hour, dt_local.minute, dt_local.second
    )
    lunar = solar.getLunar()
    year_gz = lunar.getYearInGanZhi()
    month_gz = lunar.getMonthInGanZhi()
    day_gz = lunar.getDayInGanZhi()
    hour_gz = lunar.getTimeInGanZhi()
    return Pillars(year_gz, month_gz, day_gz, hour_gz, day_gz[0])


# =========================
# 2) 特征提取（五行/十神/藏干）
# =========================
GAN_WUXING = {
    "甲": "木", "乙": "木",
    "丙": "火", "丁": "火",
    "戊": "土", "己": "土",
    "庚": "金", "辛": "金",
    "壬": "水", "癸": "水",
}
YIN_YANG = {
    "甲": "阳", "乙": "阴",
    "丙": "阳", "丁": "阴",
    "戊": "阳", "己": "阴",
    "庚": "阳", "辛": "阴",
    "壬": "阳", "癸": "阴",
}
SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
KE    = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}

ZHI_CANGGAN = {
    "子": ["癸"], "丑": ["己", "癸", "辛"], "寅": ["甲", "丙", "戊"], "卯": ["乙"],
    "辰": ["戊", "乙", "癸"], "巳": ["丙", "戊", "庚"], "午": ["丁", "己"],
    "未": ["己", "丁", "乙"], "申": ["庚", "壬", "戊"], "酉": ["辛"],
    "戌": ["戊", "辛", "丁"], "亥": ["壬", "甲"],
}


def ten_god(day_master: str, other_gan: str) -> str:
    dm_wx = GAN_WUXING[day_master]
    ot_wx = GAN_WUXING[other_gan]
    same_polar = (YIN_YANG[day_master] == YIN_YANG[other_gan])

    if ot_wx == dm_wx:
        return "比肩" if same_polar else "劫财"
    if SHENG[dm_wx] == ot_wx:
        return "食神" if same_polar else "伤官"
    if KE[dm_wx] == ot_wx:
        return "偏财" if same_polar else "正财"
    if KE[ot_wx] == dm_wx:
        return "七杀" if same_polar else "正官"
    if SHENG[ot_wx] == dm_wx:
        return "偏印" if same_polar else "正印"
    return "未知"


def extract_features(p: Pillars) -> Dict[str, Any]:
    gans = [p.year_gz[0], p.month_gz[0], p.day_gz[0], p.hour_gz[0]]
    zhis = [p.year_gz[1], p.month_gz[1], p.day_gz[1], p.hour_gz[1]]

    wuxing_counts = {k: 0 for k in ["木", "火", "土", "金", "水"]}
    for g in gans:
        wuxing_counts[GAN_WUXING[g]] += 1

    canggan_ten_gods: List[Tuple[str, str, str]] = []
    for z in zhis:
        for cg in ZHI_CANGGAN[z]:
            wuxing_counts[GAN_WUXING[cg]] += 1
            canggan_ten_gods.append((z, cg, ten_god(p.day_master, cg)))

    labels = ["年干", "月干", "日干", "时干"]
    ten_gods_gan = {}
    for lbl, g in zip(labels, gans):
        ten_gods_gan[lbl] = "日主" if g == p.day_master else ten_god(p.day_master, g)

    return {
        "wuxing_counts": wuxing_counts,
        "ten_gods_gan": ten_gods_gan,
        "canggan_ten_gods": canggan_ten_gods
    }


# =========================
# 3) 区间规则（banded rules）
# =========================
def _band_wuxing(count: int) -> str:
    if count <= 2:
        return "low"
    elif count <= 4:
        return "medium"
    else:
        return "high"


def _band_0_1_2_3plus(count: int) -> str:
    if count == 0:
        return "none"
    elif count == 1:
        return "low"
    elif count == 2:
        return "medium"
    else:
        return "high"


def _band_0_1_2plus(count: int) -> str:
    if count == 0:
        return "none"
    elif count == 1:
        return "low"
    else:
        return "high"


def eval_rules(features: Dict[str, Any]) -> List[Dict[str, Any]]:
    hits: List[Dict[str, Any]] = []

    wux = features["wuxing_counts"]
    ten_gans = features["ten_gods_gan"]
    canggan = features["canggan_ten_gods"]

    # 天干十神计数（不含日主）
    tg_gan_counter: Dict[str, int] = {}
    for pos, tg in ten_gans.items():
        if tg == "日主":
            continue
        tg_gan_counter[tg] = tg_gan_counter.get(tg, 0) + 1

    # 藏干十神计数
    tg_cg_counter: Dict[str, int] = {}
    for z, cg, tg in canggan:
        tg_cg_counter[tg] = tg_cg_counter.get(tg, 0) + 1

    # 五行 band（五条必输出）
    for e in ["木", "火", "土", "金", "水"]:
        cnt = int(wux.get(e, 0))
        band = _band_wuxing(cnt)
        hits.append({
            "rule_id": f"WUXING-{e}",
            "title": f"{e}元素水平",
            "message": band,
            "evidence": {"element": e, "count": cnt, "band": band}
        })

    # 天干十神 band 表
    all_tg = ["比肩", "劫财", "食神", "伤官", "偏财", "正财", "七杀", "正官", "偏印", "正印"]
    band_table = {}
    for tg in all_tg:
        c = tg_gan_counter.get(tg, 0)
        band_table[tg] = {"count": c, "band": _band_0_1_2_3plus(c)}
    hits.append({
        "rule_id": "TEN-GOD-GANS",
        "title": "天干十神强度（区间）",
        "message": "none/low/medium/high",
        "evidence": {"ten_god_gans": band_table}
    })

    # 藏干十神 Top5
    sorted_items = sorted(tg_cg_counter.items(), key=lambda x: x[1], reverse=True)
    top_items = sorted_items[:5]
    out = []
    for tg, c in top_items:
        out.append({"ten_god": tg, "count": c, "band": _band_0_1_2plus(c)})

    hits.append({
        "rule_id": "CANGGAN-TOP5",
        "title": "藏干十神强度（Top5）",
        "message": "none/low/high",
        "evidence": {"top": out}
    })

    return hits


# =========================
# 4) 将结构结果翻译为“段落解释”（主输出）
# =========================
def generate_interpretation_text(pillars: Pillars, features: Dict[str, Any], rule_hits: List[Dict[str, Any]]) -> str:
    wx = features["wuxing_counts"]
    tg_gan = features["ten_gods_gan"]

    # 五行 band 读取（来自 rule_hits）
    band_map = {}
    for h in rule_hits:
        if h.get("rule_id", "").startswith("WUXING-"):
            e = h["evidence"]["element"]
            band_map[e] = h["evidence"]["band"]

    def _wx_desc(e: str) -> str:
        band = band_map.get(e, "medium")
        if band == "high":
            return f"{e}偏旺"
        if band == "low":
            return f"{e}偏弱"
        return f"{e}中等"

    # 段落 1：结构概览
    p1 = (
        "从结构配置来看，该命式的五行分布呈现出相对均衡的格局。"
        f"木、火、土整体处于{_wx_desc('木')}、{_wx_desc('火')}与{_wx_desc('土')}的范围，"
        f"而金、水相对{_wx_desc('金')}与{_wx_desc('水')}。"
        "在算法模型中，这类分布通常被归类为“稳定—中性结构”，"
        "即解释重点更多来自关系结构与十神配置，而非单一五行极端偏盛。"
    )

    # 段落 2：日主与动力/制约
    p2 = (
        f"日主为{pillars.day_master}。就生成—制约关系而言，"
        "生成链条未出现明显断裂，意味着系统内部动能较为连贯；"
        "同时，制约性要素并不突出，外在压制压力相对有限。"
        "因此，算法更倾向将该命式理解为“内在一致性较强、依赖自我调节”的配置，"
        "其风险多来自内部张力的管理方式，而非外部冲击。"
    )

    # 段落 3：天干十神（规范/资源）
    norm_bits = []
    if "正官" in tg_gan.values() or "七杀" in tg_gan.values():
        norm_bits.append("权威/规范维度（官杀）")
    if "正印" in tg_gan.values() or "偏印" in tg_gan.values():
        norm_bits.append("知识/正当性维度（印星）")
    if norm_bits:
        p3 = (
            "天干层面显示出明显的制度化取向："
            + "与".join(norm_bits) +
            "在关键位置出现。"
            "在算法解释框架中，这通常意味着行动与决策更容易被“规则性、可辩护的理由、知识资本”所组织，"
            "表现为对秩序、资格、名分或可被承认的路径更敏感。"
        )
    else:
        p3 = (
            "天干层面未呈现强烈的制度化指向（如官杀或印星的显著集中），"
            "算法将其视为较为开放的结构：解释更依赖藏干层与组合关系带来的差异。"
        )

    # 段落 4：潜在张力（藏干）
    p4 = (
        "藏干层面通常承载“隐性机制”。就本模型输出而言，"
        "多重藏干的重复出现意味着解释并不由单一要素决定，而是由若干潜在维度共同约束。"
        "算法把这种结构理解为“可讨论张力”：并非必然指向失衡，而是提示在规范与行动、稳定与竞争之间存在可调空间。"
    )

    # 段落 5：吉凶总结（非决定论）
    p5 = (
        "综合五行区间、十神结构与隐性张力，该模型给出的总体评估为："
        "偏向“中上格局、吉性较稳，凶性风险可控”。"
        "需要强调的是，这里的“吉/凶”并非预测式结论，而是结构条件判断："
        "当制度化资源与内部一致性能够被良好调度时，系统更容易呈现正向结果；"
        "反之，若隐性张力在关键情境下被放大，则风险上升。"
    )

    return "\n\n".join([p1, p2, p3, p4, p5])


# =========================
# 5) Streamlit UI（主输出：段落解释）
# =========================
st.set_page_config(page_title="Bazi Algorithmic Model Demo", layout="wide")
st.title("Bazi Algorithmic Religious Knowledge System — Demo")

col1, col2 = st.columns([1, 1])

with col1:
    tz_name = st.selectbox("Time zone", ["Asia/Kuala_Lumpur", "Asia/Shanghai", "UTC"], index=0)

    birth_date = st.date_input(
        "Birth date (Gregorian)",
        value=_date(1995, 1, 1),
        min_value=_date(1800, 1, 1),
        max_value=_date.today()
    )

    birth_time = st.time_input(
        "Birth time (local)",
        value=_time(9, 30)
    )

    run = st.button("Run model")

with col2:
    st.markdown("### What this demo does")
    st.write(
        "Input a birth datetime → compute Four Pillars → extract interpretable features "
        "(wuxing / ten gods / hidden stems) → generate an evidence-aware interpretation narrative."
    )
    st.caption(
        "Note: The 'auspicious/inauspicious' statement is presented as a structural evaluation, "
        "not a deterministic prediction."
    )

if run:
    tz = pytz.timezone(tz_name)
    dt_local = tz.localize(datetime.combine(birth_date, birth_time))

    pillars = get_pillars(dt_local)
    features = extract_features(pillars)
    rule_hits = eval_rules(features)

    result = {
        "input": {"datetime_local": dt_local.isoformat(), "timezone": tz_name},
        "pillars": {
            "year": pillars.year_gz,
            "month": pillars.month_gz,
            "day": pillars.day_gz,
            "hour": pillars.hour_gz,
            "day_master": pillars.day_master
        },
        "features": features,
        "rule_hits": rule_hits
    }

    st.subheader("Interpretation (paragraph narrative)")
    interpretation_text = generate_interpretation_text(pillars, features, rule_hits)
    st.markdown(interpretation_text)

    with st.expander("Show computational details (Four Pillars / Features / Rules)"):
        st.json(result)

    st.subheader("Download JSON output")
    st.download_button(
        label="Download result.json",
        data=json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"),
        file_name="result.json",
        mime="application/json"
    )
