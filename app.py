import json
from dataclasses import dataclass
from datetime import datetime
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
SHENG = {"木":"火","火":"土","土":"金","金":"水","水":"木"}
KE    = {"木":"土","土":"水","水":"火","火":"金","金":"木"}

ZHI_CANGGAN = {
    "子": ["癸"],
    "丑": ["己", "癸", "辛"],
    "寅": ["甲", "丙", "戊"],
    "卯": ["乙"],
    "辰": ["戊", "乙", "癸"],
    "巳": ["丙", "戊", "庚"],
    "午": ["丁", "己"],
    "未": ["己", "丁", "乙"],
    "申": ["庚", "壬", "戊"],
    "酉": ["辛"],
    "戌": ["戊", "辛", "丁"],
    "亥": ["壬", "甲"],
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

    wuxing_counts = {k: 0 for k in ["木","火","土","金","水"]}
    for g in gans:
        wuxing_counts[GAN_WUXING[g]] += 1

    canggan_ten_gods: List[Tuple[str,str,str]] = []
    for z in zhis:
        for cg in ZHI_CANGGAN[z]:
            wuxing_counts[GAN_WUXING[cg]] += 1
            canggan_ten_gods.append((z, cg, ten_god(p.day_master, cg)))

    labels = ["年干","月干","日干","时干"]
    ten_gods_gan = {}
    for lbl, g in zip(labels, gans):
        ten_gods_gan[lbl] = "日主" if g == p.day_master else ten_god(p.day_master, g)

    return {
        "wuxing_counts": wuxing_counts,
        "ten_gods_gan": ten_gods_gan,
        "canggan_ten_gods": canggan_ten_gods
    }


# =========================
# 3) 规则引擎（IF → THEN + evidence）
# =========================
RULES = [
    # --- 五行：区间标签（低/中/高）---
    {"id":"W01", "title":"木元素水平", "if":{"type":"wuxing_band","element":"木"}, "then":{}},
    {"id":"W02", "title":"火元素水平", "if":{"type":"wuxing_band","element":"火"}, "then":{}},
    {"id":"W03", "title":"土元素水平", "if":{"type":"wuxing_band","element":"土"}, "then":{}},
    {"id":"W04", "title":"金元素水平", "if":{"type":"wuxing_band","element":"金"}, "then":{}},
    {"id":"W05", "title":"水元素水平", "if":{"type":"wuxing_band","element":"水"}, "then":{}},

    # --- 十神：在四柱天干中的出现强度（0/1/2/3/4 -> 低/中/高）---
    {"id":"T01", "title":"十神分布强度（天干）", "if":{"type":"ten_god_band_all_gans"}, "then":{}},

    # --- 藏干十神：出现强度（0/1/2+ -> 无/低/高）---
    {"id":"C01", "title":"藏干十神强度（Top）", "if":{"type":"canggan_top_band","topk":5}, "then":{}},
]

def _band_wuxing(count: int) -> str:
    # 这里的阈值是“示范版”，你后面可以根据样例分布再校准
    # 天干4 + 藏干(最多~8) → 总量常在 10~14 附近波动
    if count <= 2:
        return "low"
    elif count <= 4:
        return "medium"
    else:
        return "high"

def _band_count_0_1_2plus(count: int) -> str:
    if count == 0:
        return "none"
    elif count == 1:
        return "low"
    else:
        return "high"

def _band_count_0_1_2_3plus(count: int) -> str:
    if count == 0:
        return "none"
    elif count == 1:
        return "low"
    elif count == 2:
        return "medium"
    else:
        return "high"

def eval_rules(features: Dict[str, Any]) -> List[Dict[str, Any]]:
    hits: List[Dict[str, Any]] = []

    wux = features["wuxing_counts"]
    ten_gans = features["ten_gods_gan"]
    canggan = features["canggan_ten_gods"]

    # 统计：天干十神（不含“日主”）
    tg_gan_counter: Dict[str, int] = {}
    for pos, tg in ten_gans.items():
        if tg == "日主":
            continue
        tg_gan_counter[tg] = tg_gan_counter.get(tg, 0) + 1

    # 统计：藏干十神
    tg_cg_counter: Dict[str, int] = {}
    for z, cg, tg in canggan:
        tg_cg_counter[tg] = tg_cg_counter.get(tg, 0) + 1

    for r in RULES:
        cond = r["if"]

        # --- 五行区间 ---
        if cond["type"] == "wuxing_band":
            e = cond["element"]
            cnt = int(wux.get(e, 0))
            band = _band_wuxing(cnt)

            msg_map = {
                "low":    f"{e}元素偏低（low）。在形式化系统中，这被标记为结构性弱项，需要依赖其他结构（如十神/组合）补足语义。",
                "medium": f"{e}元素处于中等水平（medium）。说明该维度未呈现强烈偏向，解释更依赖语境参数与组合规则。",
                "high":   f"{e}元素偏高（high）。在规则系统中可作为显著偏向维度，用于触发更强约束的解释路径。"
            }

            hits.append({
                "rule_id": r["id"],
                "title": r["title"],
                "message": msg_map[band],
                "evidence": {"element": e, "count": cnt, "band": band}
            })
            continue

        # --- 天干十神：全部输出强度表（永远有输出）---
        if cond["type"] == "ten_god_band_all_gans":
            # 对常见十神集合做一个完整表，保证“没出现”也会显示 none
            all_tg = ["比肩","劫财","食神","伤官","偏财","正财","七杀","正官","偏印","正印"]
            band_table = {}
            for tg in all_tg:
                c = tg_gan_counter.get(tg, 0)
                band_table[tg] = {"count": c, "band": _band_count_0_1_2_3plus(c)}

            hits.append({
                "rule_id": r["id"],
                "title": r["title"],
                "message": "天干十神分布以区间标签表示（none/low/medium/high），用于展示哪些解释维度在结构层面更突出。",
                "evidence": {"ten_god_gans": band_table}
            })
            continue

        # --- 藏干十神：TopK 输出（永远有输出）---
        if cond["type"] == "canggan_top_band":
            topk = int(cond.get("topk", 5))
            sorted_items = sorted(tg_cg_counter.items(), key=lambda x: x[1], reverse=True)
            top_items = sorted_items[:topk]

            out = []
            for tg, c in top_items:
                out.append({"ten_god": tg, "count": c, "band": _band_count_0_1_2plus(c)})

            hits.append({
                "rule_id": r["id"],
                "title": r["title"],
                "message": f"藏干十神按出现频次排序，输出 Top {topk} 并给出区间标签（none/low/high）。",
                "evidence": {"top": out}
            })
            continue

    return hits



# =========================
# 4) Streamlit UI
# =========================
st.set_page_config(page_title="Bazi Algorithmic Model Demo", layout="wide")
st.title("Bazi Algorithmic Religious Knowledge System — Demo")

col1, col2 = st.columns(2)

with col1:
    tz_name = st.selectbox("Time zone", ["Asia/Kuala_Lumpur", "Asia/Shanghai", "UTC"], index=0)
    date = st.date_input("Birth date (Gregorian)")
    time = st.time_input("Birth time (local)")
    run = st.button("Run model")

with col2:
    st.markdown("### What this demo does")
    st.write(
        "Input a birth datetime → compute Four Pillars → extract interpretable features "
        "(wuxing / ten gods / hidden stems) → apply rule-based explanations with evidence."
    )

if run:
    tz = pytz.timezone(tz_name)
    dt_local = tz.localize(datetime.combine(date, time))

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

    st.subheader("Four Pillars")
    st.json(result["pillars"])

    st.subheader("Features")
    st.json(result["features"])

    st.subheader("Rule hits (with evidence)")
    if not rule_hits:
        st.info("No rules hit. Add more rules in RULES.")
    else:
        for h in rule_hits:
            st.markdown(f"**{h['rule_id']} | {h['title']}**")
            st.write(h["message"])
            st.caption(f"Evidence: {h['evidence']}")

    st.subheader("Download JSON output")
    st.download_button(
        label="Download result.json",
        data=json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"),
        file_name="result.json",
        mime="application/json"
    )


