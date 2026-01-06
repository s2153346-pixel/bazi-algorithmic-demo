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

    return Pillars(
        lunar.getYearInGanZhi(),
        lunar.getMonthInGanZhi(),
        lunar.getDayInGanZhi(),
        lunar.getTimeInGanZhi(),
        lunar.getDayInGanZhi()[0]
    )


# =========================
# 2) 特征提取（五行 / 十神 / 藏干）
# =========================
GAN_WUXING = {
    "甲":"木","乙":"木","丙":"火","丁":"火",
    "戊":"土","己":"土","庚":"金","辛":"金",
    "壬":"水","癸":"水"
}
YIN_YANG = {
    "甲":"阳","乙":"阴","丙":"阳","丁":"阴",
    "戊":"阳","己":"阴","庚":"阳","辛":"阴",
    "壬":"阳","癸":"阴"
}
SHENG = {"木":"火","火":"土","土":"金","金":"水","水":"木"}
KE    = {"木":"土","土":"水","水":"火","火":"金","金":"木"}

ZHI_CANGGAN = {
    "子":["癸"], "丑":["己","癸","辛"], "寅":["甲","丙","戊"], "卯":["乙"],
    "辰":["戊","乙","癸"], "巳":["丙","戊","庚"], "午":["丁","己"],
    "未":["己","丁","乙"], "申":["庚","壬","戊"], "酉":["辛"],
    "戌":["戊","辛","丁"], "亥":["壬","甲"],
}

def ten_god(day_master: str, other_gan: str) -> str:
    dm = GAN_WUXING[day_master]
    ot = GAN_WUXING[other_gan]
    same = YIN_YANG[day_master] == YIN_YANG[other_gan]

    if ot == dm:
        return "比肩" if same else "劫财"
    if SHENG[dm] == ot:
        return "食神" if same else "伤官"
    if KE[dm] == ot:
        return "偏财" if same else "正财"
    if KE[ot] == dm:
        return "七杀" if same else "正官"
    if SHENG[ot] == dm:
        return "偏印" if same else "正印"
    return "未知"


def extract_features(p: Pillars) -> Dict[str, Any]:
    gans = [p.year_gz[0], p.month_gz[0], p.day_gz[0], p.hour_gz[0]]
    zhis = [p.year_gz[1], p.month_gz[1], p.day_gz[1], p.hour_gz[1]]

    wuxing = {k: 0 for k in ["木","火","土","金","水"]}
    for g in gans:
        wuxing[GAN_WUXING[g]] += 1

    canggan = []
    for z in zhis:
        for cg in ZHI_CANGGAN[z]:
            wuxing[GAN_WUXING[cg]] += 1
            canggan.append((z, cg, ten_god(p.day_master, cg)))

    labels = ["年干","月干","日干","时干"]
    ten_gans = {
        lbl: ("日主" if g == p.day_master else ten_god(p.day_master, g))
        for lbl, g in zip(labels, gans)
    }

    return {
        "wuxing_counts": wuxing,
        "ten_gods_gan": ten_gans,
        "canggan_ten_gods": canggan
    }


# =========================
# 3) 区间规则（方案 A）
# =========================
def band_wuxing(c):
    return "low" if c <= 2 else "medium" if c <= 4 else "high"


def band_012(c):
    return "none" if c == 0 else "low" if c == 1 else "high"


def eval_rules(features: Dict[str, Any]) -> List[Dict[str, Any]]:
    hits = []

    for e, c in features["wuxing_counts"].items():
        band = band_wuxing(c)
        hits.append({
            "rule": f"WUXING-{e}",
            "message": f"{e} 元素水平：{band}",
            "evidence": {"count": c}
        })

    return hits


# =========================
# 4) Streamlit UI（关键修正点在这里）
# =========================
st.set_page_config(page_title="Bazi Algorithmic Demo", layout="wide")
st.title("Bazi Algorithmic Religious Knowledge System — Demo")

col1, col2 = st.columns(2)

with col1:
    tz_name = st.selectbox("Time zone", ["Asia/Kuala_Lumpur", "Asia/Shanghai", "UTC"])

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
    st.markdown(
        """
        **Pipeline**
        Input datetime → Four Pillars → Feature extraction → Rule-based interpretation  
        This demo treats Bazi as an *algorithmic religious knowledge system*,
        not a predictive oracle.
        """
    )

if run:
    tz = pytz.timezone(tz_name)
    dt_local = tz.localize(datetime.combine(birth_date, birth_time))

    pillars = get_pillars(dt_local)
    features = extract_features(pillars)
    rules = eval_rules(features)

    result = {
        "input": dt_local.isoformat(),
        "pillars": pillars.__dict__,
        "features": features,
        "rules": rules
    }

    st.subheader("Four Pillars")
    st.json(result["pillars"])

    st.subheader("Features")
    st.json(result["features"])

    st.subheader("Rule-based interpretation")
    st.json(rules)

    st.download_button(
        "Download result.json",
        json.dumps(result, ensure_ascii=False, indent=2),
        file_name="bazi_result.json",
        mime="application/json"
    )
