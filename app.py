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
RULES: List[Dict[str, Any]] = [
    {
        "id": "R002",
        "title": "伤官出现（时干）",
        "if": {"type": "ten_god_eq", "position": "时干", "value": "伤官"},
        "then": {"message": "时干见伤官，常被解读为表达与创造的驱动力较强，但也可能带来与规范/权威的张力。"}
    },
    {
        "id": "R003",
        "title": "七杀较多（藏干）",
        "if": {"type": "canggan_tg_ge", "value": "七杀", "count": 2},
        "then": {"message": "藏干中七杀出现次数较多，解释上可讨论压力/竞争情境中的行动策略，以及风险与纪律的平衡。"}
    },
]

def eval_rules(features: Dict[str, Any]) -> List[Dict[str, Any]]:
    hits = []

    tg_counter: Dict[str,int] = {}
    for z, cg, tg in features["canggan_ten_gods"]:
        tg_counter[tg] = tg_counter.get(tg, 0) + 1

    for r in RULES:
        cond = r["if"]
        ok = False
        evidence = {}

        if cond["type"] == "ten_god_eq":
            pos = cond["position"]
            expected = cond["value"]
            actual = features["ten_gods_gan"].get(pos)
            ok = (actual == expected)
            evidence = {"position": pos, "actual": actual, "expected": expected}

        elif cond["type"] == "canggan_tg_ge":
            tg = cond["value"]
            threshold = cond["count"]
            actual = tg_counter.get(tg, 0)
            ok = actual >= threshold
            evidence = {"ten_god": tg, "count": actual, "threshold": threshold}

        if ok:
            hits.append({
                "rule_id": r["id"],
                "title": r["title"],
                "message": r["then"]["message"],
                "evidence": evidence
            })

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


