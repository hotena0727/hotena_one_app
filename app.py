# app.py
from __future__ import annotations

from pathlib import Path
import random
import re
import unicodedata
import json
import time

import pandas as pd
import streamlit as st

# ============================================================
# ✅ Page
# ============================================================
st.set_page_config(page_title="왕초보 탈출 마법의 단어장", layout="centered")

# ============================================================
# ✅ UI 기본 스타일
# ============================================================
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Kosugi+Maru&family=Noto+Sans+JP:wght@400;500;700;800&display=swap" rel="stylesheet">
<style>
:root{ --jp-rounded: "Noto Sans JP","Kosugi Maru","Hiragino Sans","Yu Gothic","Meiryo",sans-serif; }
.jp, .jp *{ font-family: var(--jp-rounded) !important; line-height:1.7; letter-spacing:.2px; }

div.stButton > button {
  padding: 8px 10px !important;
  font-size: 13px !important;
  font-weight: 800 !important;
  white-space: nowrap !important;
}

.qtypewrap div.stButton > button{
  height: 46px !important;
  border-radius: 14px !important;
  border: 1px solid rgba(120,120,120,0.22) !important;
  background: rgba(255,255,255,0.04) !important;
}

.qtype_hint{
  font-size: 14px;
  opacity: .72;
  margin-top: 4px;
  margin-bottom: 10px;
  line-height: 1.2;
}

.tight-divider hr{
  margin: 6px 0 10px 0 !important;
}

.wrong-card{
  border: 1px solid rgba(120,120,120,0.25);
  border-radius: 16px;
  padding: 14px 14px;
  margin-bottom: 10px;
  background: rgba(255,255,255,0.02);
}
.wrong-top{
  display:flex;
  align-items:flex-start;
  justify-content:space-between;
  gap:12px;
  margin-bottom: 8px;
}
.wrong-title{ font-weight: 900; font-size: 15px; margin-bottom: 4px; }
.wrong-sub{ opacity: 0.8; font-size: 12px; }
.tag{
  display:inline-flex;
  align-items:center;
  gap:6px;
  padding: 5px 9px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 800;
  border: 1px solid rgba(120,120,120,0.25);
  background: rgba(255,255,255,0.03);
  white-space: nowrap;
}
.ans-row{
  display:grid;
  grid-template-columns: 72px 1fr;
  gap:10px;
  margin-top:6px;
  font-size: 13px;
}
.ans-k{ opacity: 0.7; font-weight: 800; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# ✅ 상수 / CSV
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "data" / "words_magic_marked.csv"  # ✅ 마킹된 CSV 권장

N = 10
LEVELS = ["N5", "N4", "N3", "N2", "N1"]

# ✅ pos 라벨 통일(선우님 방식)
# - i형용사: i_adj
# - な형용사: na_adj
POS_CANON = {
    "adji_i": "i_adj", "adj_i": "i_adj", "i-adj": "i_adj", "adj-i": "i_adj", "i_adj": "i_adj",
    "adji_na": "na_adj", "adj_na": "na_adj", "na-adj": "na_adj", "adj-na": "na_adj", "na_adj": "na_adj",
}

# ✅ 앱에서 선택할 코어 품사(너무 잘게 쪼개지 말고 체감 중심)
POS_BUTTONS_CORE = [
    ("noun", "명사"),
    ("verb", "동사"),
    ("i_adj", "い형용사"),
    ("na_adj", "な형용사"),
    ("adv", "부사"),
]

# ✅ use 전용(조사/표현은 엔진 분리)
POS_LABELS_USE = {"particle", "expr"}

QUIZ_TYPES_CORE = [
    ("reading", "발음"),      # ✅ “읽기” → “발음”
    ("meaning", "뜻"),
    ("kr2jp",   "한→일"),
]

# daily_mix 고정 비율(체감 좋게)
DAILY_MIX_RATIO = {
    "use": 2,      # 조사/표현(use_final)
    "adv": 2,      # 부사
    "core": 6,     # 명사/동사/형용사 등
}

# ============================================================
# ✅ Utils
# ============================================================
def _nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", str(s or "")).strip()

def norm_level(x: str) -> str:
    x = _nfkc(x).upper().replace(" ", "")
    m = re.search(r"(N[1-5])", x)
    if m:
        return m.group(1)
    if x in {"1","2","3","4","5"}:
        return {"1":"N1","2":"N2","3":"N3","4":"N4","5":"N5"}[x]
    return x if x in LEVELS else ""

def safe_str(x) -> str:
    return "" if x is None else str(x)

# ============================================================
# ✅ CSV Load
# ============================================================
READ_KW = dict(
    dtype=str,
    keep_default_na=False,
    na_values=["nan", "NaN", "NULL", "null", "None", "none"],
)

@st.cache_data(show_spinner=False)
def load_pool(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, **READ_KW)

    required = {"level","pos","jp_word","reading","meaning_kr","example_jp","example_kr","show_kanji"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV 필수 컬럼 누락: {sorted(list(missing))}")

    # normalize
    df["level"] = df["level"].apply(norm_level)
    df["pos"] = df["pos"].astype(str).str.strip().str.lower().map(lambda x: POS_CANON.get(x, x))

    for c in ["jp_word","reading","meaning_kr","example_jp","example_kr","show_kanji"]:
        df[c] = df[c].astype(str).str.strip()

    # optional cols
    for c in ["kanji_candidate","kanji_confidence"]:
        if c not in df.columns:
            df[c] = ""

    # remove empties
    df = df[(df["level"] != "") & (df["jp_word"] != "") & (df["reading"] != "") & (df["meaning_kr"] != "")]
    return df.reset_index(drop=True)

def ensure_pool():
    if "pool" in st.session_state and isinstance(st.session_state.pool, pd.DataFrame):
        return
    if not CSV_PATH.exists():
        st.error(f"CSV 파일이 없습니다: {CSV_PATH}")
        st.stop()
    st.session_state.pool = load_pool(str(CSV_PATH))

# ============================================================
# ✅ use_final: example_jp에서 빈칸 자동 생성
# ============================================================
def build_blank_prompt_from_example(example_jp: str, target: str) -> tuple[str, bool]:
    ex = (example_jp or "").strip()
    t = (target or "").strip()
    if not ex or not t:
        return "{blank}", False

    marked = f"【{t}】"
    if marked in ex:
        return ex.replace(marked, "____", 1), True

    if f" {t} " in f" {ex} ":
        # 안전: 공백 토큰
        padded = f" {ex} "
        padded = padded.replace(f" {t} ", " ____ ", 1)
        return padded.strip(), True

    # 마지막 fallback(정확도 낮음) — 표현(2글자 이상)에만 추천
    if len(t) >= 2 and t in ex:
        return ex.replace(t, "____", 1), True

    return "{blank}", False

def make_use_final_question(row: pd.Series, pool: pd.DataFrame) -> dict:
    jp = str(row.get("jp_word", "")).strip()
    rd = str(row.get("reading", "")).strip()
    mn = str(row.get("meaning_kr", "")).strip()
    lvl = str(row.get("level", "")).strip()
    pos = str(row.get("pos", "")).strip()

    ex_jp = str(row.get("example_jp", "")).strip()
    prompt_tpl, used_example = build_blank_prompt_from_example(ex_jp, jp)

    if not used_example or prompt_tpl.strip() in ("{blank}", "____"):
        # 최후 안전장치
        prompt_tpl = "____（빈칸에 알맞은 표현을 고르세요）"

    # 보기 후보: use(pos 동일) 우선
    pool_pos = pool[pool["pos"] == pos].copy()
    candidates = pool_pos.loc[pool_pos["jp_word"] != jp, "jp_word"].drop_duplicates().tolist()
    candidates = [c for c in candidates if str(c).strip()]

    if len(candidates) < 3:
        pool_use = pool[pool["pos"].isin(POS_LABELS_USE)]
        candidates = pool_use.loc[pool_use["jp_word"] != jp, "jp_word"].drop_duplicates().tolist()
        candidates = [c for c in candidates if str(c).strip()]

    if len(candidates) < 3:
        candidates = pool.loc[pool["jp_word"] != jp, "jp_word"].drop_duplicates().tolist()
        candidates = [c for c in candidates if str(c).strip()]

    wrongs = random.sample(candidates, 3)
    choices = wrongs + [jp]
    random.shuffle(choices)

    return {
        "mode": "use_final",
        "prompt_tpl": prompt_tpl,
        "choices": choices,
        "correct_text": jp,

        "level": lvl,
        "pos": pos,
        "jp_word": jp,
        "reading": rd,
        "meaning_kr": mn,
        "example_jp": ex_jp,
        "example_kr": str(row.get("example_kr", "")).strip(),

        "kanji_candidate": str(row.get("kanji_candidate", "")).strip(),
        "kanji_confidence": str(row.get("kanji_confidence", "")).strip(),

        "used_example": bool(used_example),
    }

# ============================================================
# ✅ core question (reading/meaning/kr2jp) - 같은 pos에서 보기 구성
# ============================================================
def make_core_question(row: pd.Series, qtype: str, pool: pd.DataFrame) -> dict:
    jp = str(row.get("jp_word", "")).strip()
    rd = str(row.get("reading", "")).strip()
    mn = str(row.get("meaning_kr", "")).strip()
    lvl = str(row.get("level", "")).strip()
    pos = str(row.get("pos", "")).strip()

    pool_pos = pool[pool["pos"] == pos].copy()

    if qtype == "reading":
        prompt = f"{jp}의 발음은?"
        correct = rd
        candidates = pool_pos.loc[pool_pos["reading"] != correct, "reading"].drop_duplicates().tolist()
        candidates = [c for c in candidates if str(c).strip()]
        if len(candidates) < 3:
            candidates = pool.loc[pool["reading"] != correct, "reading"].drop_duplicates().tolist()
            candidates = [c for c in candidates if str(c).strip()]
        wrongs = random.sample(candidates, 3)

    elif qtype == "meaning":
        prompt = f"{jp}의 뜻은?"
        correct = mn
        candidates = pool_pos.loc[pool_pos["meaning_kr"] != correct, "meaning_kr"].drop_duplicates().tolist()
        candidates = [c for c in candidates if str(c).strip()]
        if len(candidates) < 3:
            candidates = pool.loc[pool["meaning_kr"] != correct, "meaning_kr"].drop_duplicates().tolist()
            candidates = [c for c in candidates if str(c).strip()]
        wrongs = random.sample(candidates, 3)

    elif qtype == "kr2jp":
        prompt = f"'{mn}'의 일본어는?"
        correct = jp
        candidates = pool_pos.loc[pool_pos["jp_word"] != correct, "jp_word"].drop_duplicates().tolist()
        candidates = [c for c in candidates if str(c).strip()]
        if len(candidates) < 3:
            candidates = pool.loc[pool["jp_word"] != correct, "jp_word"].drop_duplicates().tolist()
            candidates = [c for c in candidates if str(c).strip()]
        wrongs = random.sample(candidates, 3)

    else:
        raise ValueError("unknown qtype")

    choices = wrongs + [correct]
    random.shuffle(choices)

    return {
        "mode": "core",
        "qtype": qtype,
        "prompt": prompt,
        "choices": choices,
        "correct_text": correct,

        "level": lvl,
        "pos": pos,
        "jp_word": jp,
        "reading": rd,
        "meaning_kr": mn,
        "example_jp": str(row.get("example_jp", "")).strip(),
        "example_kr": str(row.get("example_kr", "")).strip(),

        "kanji_candidate": str(row.get("kanji_candidate", "")).strip(),
        "kanji_confidence": str(row.get("kanji_confidence", "")).strip(),
    }

# ============================================================
# ✅ daily_mix build
# ============================================================
def pick_level_mix(level: str) -> dict[str, str]:
    """
    N5: 기본은 N5, 일부를 N4에서 섞어 부드러운 승급
    N4 이상: 기본 레벨 + 상위 1단계에서 소량 섞기(원하면 확장)
    """
    level = level.upper().strip()
    if level == "N5":
        return {"base":"N5", "soft_up":"N4"}  # ✅ 부드러운 승급
    if level == "N4":
        return {"base":"N4", "soft_up":"N3"}
    if level == "N3":
        return {"base":"N3", "soft_up":"N2"}
    if level == "N2":
        return {"base":"N2", "soft_up":"N1"}
    return {"base":"N1", "soft_up":"N1"}

def build_daily_mix(level: str, pool: pd.DataFrame) -> list[dict]:
    mix = pick_level_mix(level)
    base_lv = mix["base"]
    soft_lv = mix["soft_up"]

    # use 풀
    use_base = pool[(pool["level"] == base_lv) & (pool["pos"].isin(POS_LABELS_USE))].copy()
    use_soft = pool[(pool["level"] == soft_lv) & (pool["pos"].isin(POS_LABELS_USE))].copy()

    # adv 풀
    adv_base = pool[(pool["level"] == base_lv) & (pool["pos"] == "adv")].copy()
    adv_soft = pool[(pool["level"] == soft_lv) & (pool["pos"] == "adv")].copy()

    # core 풀(명사/동사/형용사)
    core_pos = {"noun","verb","i_adj","na_adj"}
    core_base = pool[(pool["level"] == base_lv) & (pool["pos"].isin(core_pos))].copy()
    core_soft = pool[(pool["level"] == soft_lv) & (pool["pos"].isin(core_pos))].copy()

    # fallback: 부족하면 레벨 무시 확장
    if len(core_base) < 30:
        core_base = pool[pool["pos"].isin(core_pos)].copy()
    if len(adv_base) < 10:
        adv_base = pool[pool["pos"] == "adv"].copy()
    if len(use_base) < 10:
        use_base = pool[pool["pos"].isin(POS_LABELS_USE)].copy()

    def sample_df(df1, df2, k, soft_k=0):
        out = []
        if k <= 0:
            return out
        soft_k = max(0, min(soft_k, k))
        base_k = k - soft_k

        if len(df1) >= base_k:
            out += df1.sample(n=base_k, replace=False).to_dict("records")
        else:
            out += df1.sample(n=min(base_k, len(df1)), replace=False).to_dict("records")

        if soft_k > 0:
            if len(df2) >= soft_k:
                out += df2.sample(n=soft_k, replace=False).to_dict("records")
            else:
                out += df2.sample(n=min(soft_k, len(df2)), replace=False).to_dict("records")
        return out

    # ✅ 비율 유지 + “부드러운 승급” 소량 포함
    use_rows  = sample_df(use_base,  use_soft,  DAILY_MIX_RATIO["use"],  soft_k=1 if base_lv != "N1" else 0)
    adv_rows  = sample_df(adv_base,  adv_soft,  DAILY_MIX_RATIO["adv"],  soft_k=1 if base_lv != "N1" else 0)
    core_rows = sample_df(core_base, core_soft, DAILY_MIX_RATIO["core"], soft_k=2 if base_lv in {"N5","N4"} else 1)

    # ✅ core는 “품사별로 고정된 문항 유형” 추천(체감 안정)
    # - noun/verb/adj: meaning 위주 + 일부 reading/kr2jp
    def core_qtype_for_pos(p: str) -> str:
        if p in {"verb","i_adj","na_adj"}:
            return random.choices(["meaning","reading","kr2jp"], weights=[6,3,1])[0]
        if p == "noun":
            return random.choices(["meaning","kr2jp","reading"], weights=[6,3,1])[0]
        return "meaning"

    quiz: list[dict] = []

    # use_final
    for r in use_rows:
        quiz.append(make_use_final_question(pd.Series(r), pool))

    # adv는 core 엔진으로(meaning 중심)
    for r in adv_rows:
        row = pd.Series(r)
        qt = random.choices(["meaning","reading","kr2jp"], weights=[7,2,1])[0]
        quiz.append(make_core_question(row, qt, pool))

    # core
    for r in core_rows:
        row = pd.Series(r)
        qt = core_qtype_for_pos(str(row.get("pos","")))
        quiz.append(make_core_question(row, qt, pool))

    random.shuffle(quiz)
    return quiz[:N]

# ============================================================
# ✅ 오답이면 복습 가중치(간단 버전)
# ============================================================
def apply_wrong_weight_pool(pool: pd.DataFrame, wrong_keys: list[str]) -> pd.DataFrame:
    """
    wrong_keys에 포함된 jp_word를 샘플링 확률 높이기 위한 간단한 복제 방식.
    (무겁지 않게, 로딩 부담 적게)
    """
    if not wrong_keys:
        return pool
    keys = set([k.strip() for k in wrong_keys if k and str(k).strip()])
    if not keys:
        return pool
    wrong_df = pool[pool["jp_word"].isin(keys)].copy()
    if len(wrong_df) == 0:
        return pool
    # 2배 정도만 가중(과하지 않게)
    return pd.concat([pool, wrong_df], ignore_index=True)

# ============================================================
# ✅ 상태 초기화
# ============================================================
def clear_q_keys():
    qv = st.session_state.get("quiz_version", 0)
    keys = [k for k in list(st.session_state.keys()) if isinstance(k,str) and k.startswith(f"q_{qv}_")]
    for k in keys:
        st.session_state.pop(k, None)

def start_quiz(quiz: list[dict]):
    st.session_state.quiz_version = int(st.session_state.get("quiz_version", 0)) + 1
    st.session_state.quiz = quiz
    st.session_state.answers = [None] * len(quiz)
    st.session_state.submitted = False
    st.session_state.wrong_list = []

def sync_answers():
    qv = st.session_state.get("quiz_version", 0)
    quiz = st.session_state.get("quiz", [])
    if not isinstance(quiz, list):
        return
    ans = st.session_state.get("answers")
    if not isinstance(ans, list) or len(ans) != len(quiz):
        st.session_state.answers = [None] * len(quiz)

    for i in range(len(quiz)):
        wk = f"q_{qv}_{i}"
        if wk in st.session_state:
            st.session_state.answers[i] = st.session_state[wk]

# ============================================================
# ✅ 상단 UI
# ============================================================
st.markdown("<div class='jp' style='font-size:26px; font-weight:900; margin:2px 0 8px 0;'>✨ 왕초보 탈출 마법의 단어장</div>", unsafe_allow_html=True)
st.caption("오늘은 ‘틀려도 괜찮은 날’로 잡아요. 10문항만 끝내면 루틴 성공입니다 🙂")

ensure_pool()
pool: pd.DataFrame = st.session_state.pool

if "level" not in st.session_state:
    st.session_state.level = "N5"
if "pos_pick" not in st.session_state:
    st.session_state.pos_pick = "daily_mix"
if "quiz_type" not in st.session_state:
    st.session_state.quiz_type = "meaning"

# 버튼 래퍼
st.markdown("<div class='qtypewrap'>", unsafe_allow_html=True)

# 레벨
lv_cols = st.columns(len(LEVELS), gap="small")
for i, lv in enumerate(LEVELS):
    sel = (st.session_state.level == lv)
    with lv_cols[i]:
        if st.button(("✅ " if sel else "") + lv, type=("primary" if sel else "secondary"), use_container_width=True, key=f"btn_lv_{lv}"):
            st.session_state.level = lv
            clear_q_keys()
            st.session_state.quiz = []
            st.session_state.submitted = False

st.markdown("<div class='qtype_hint jp'>✨ 레벨을 선택하세요</div>", unsafe_allow_html=True)

# 품사 선택(코어 + daily_mix + use 전용)
pos_options = [("daily_mix","오늘의 추천(daily_mix)")] + POS_BUTTONS_CORE + [("use","조사·표현(사용)")]
pos_cols = st.columns(3, gap="small")
for idx, (pval, plabel) in enumerate(pos_options):
    sel = (st.session_state.pos_pick == pval)
    with pos_cols[idx % 3]:
        if st.button(("✅ " if sel else "") + plabel, type=("primary" if sel else "secondary"), use_container_width=True, key=f"btn_pos_{pval}"):
            st.session_state.pos_pick = pval
            clear_q_keys()
            st.session_state.quiz = []
            st.session_state.submitted = False

st.markdown("<div class='qtype_hint jp'>✨ 품사를 선택하세요</div>", unsafe_allow_html=True)

# 유형(코어 전용)
type_cols = st.columns(len(QUIZ_TYPES_CORE), gap="small")
for i, (qt, label) in enumerate(QUIZ_TYPES_CORE):
    sel = (st.session_state.quiz_type == qt)
    with type_cols[i]:
        if st.button(("✅ " if sel else "") + label, type=("primary" if sel else "secondary"), use_container_width=True, key=f"btn_qt_{qt}"):
            st.session_state.quiz_type = qt
            clear_q_keys()
            st.session_state.quiz = []
            st.session_state.submitted = False

st.markdown("<div class='qtype_hint jp'>✨ 유형을 선택하세요</div>", unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div class='tight-divider'>", unsafe_allow_html=True)
st.divider()
st.markdown("</div>", unsafe_allow_html=True)

# ============================================================
# ✅ 훅: 제출 후 daily_mix 자동 배치(원하면 여기서만 제어)
# ============================================================
def maybe_auto_queue_daily_mix_after_submit():
    """
    제출 후:
      - 다음 10문항 버튼을 누르지 않아도,
        화면 맨 아래에 '다음은 오늘의 추천'을 자연스럽게 제공
    """
    if not st.session_state.get("submitted"):
        return
    st.info("다음 세트는 ‘오늘의 추천’으로 자연스럽게 이어가도 좋아요 🙂")
    if st.button("▶ 오늘의 추천(daily_mix) 바로 시작", type="primary", use_container_width=True, key="btn_auto_daily_mix"):
        clear_q_keys()
        quiz = build_daily_mix(st.session_state.level, pool)
        start_quiz(quiz)
        st.rerun()

# ============================================================
# ✅ 새 문제 생성
# ============================================================
def build_quiz_now() -> list[dict]:
    level = st.session_state.level
    pos_pick = st.session_state.pos_pick
    qtype = st.session_state.quiz_type

    # 복습 가중치(오답 키) 적용
    wrong_keys = [w.get("jp_word","") for w in (st.session_state.get("wrong_list", []) or []) if isinstance(w, dict)]
    pool2 = apply_wrong_weight_pool(pool, wrong_keys)

    if pos_pick == "daily_mix":
        return build_daily_mix(level, pool2)

    if pos_pick == "use":
        use_df = pool2[(pool2["level"] == level) & (pool2["pos"].isin(POS_LABELS_USE))].copy()
        if len(use_df) < N:
            # 부드러운 승급 포함
            soft = pick_level_mix(level)["soft_up"]
            use_df = pd.concat([use_df, pool2[(pool2["level"] == soft) & (pool2["pos"].isin(POS_LABELS_USE))]], ignore_index=True)
        if len(use_df) < N:
            use_df = pool2[pool2["pos"].isin(POS_LABELS_USE)].copy()
        rows = use_df.sample(n=min(N, len(use_df)), replace=False).to_dict("records")
        return [make_use_final_question(pd.Series(r), pool2) for r in rows]

    # 코어 품사
    core_df = pool2[(pool2["level"] == level) & (pool2["pos"] == pos_pick)].copy()
    if len(core_df) < N:
        soft = pick_level_mix(level)["soft_up"]
        core_df = pd.concat([core_df, pool2[(pool2["level"] == soft) & (pool2["pos"] == pos_pick)]], ignore_index=True)
    if len(core_df) < N:
        core_df = pool2[pool2["pos"] == pos_pick].copy()

    rows = core_df.sample(n=min(N, len(core_df)), replace=False).to_dict("records")
    return [make_core_question(pd.Series(r), qtype, pool2) for r in rows]

# 버튼
c1, c2 = st.columns(2)
with c1:
    if st.button("🔄 새 문제(랜덤 10문항)", use_container_width=True, key="btn_new"):
        clear_q_keys()
        quiz = build_quiz_now()
        start_quiz(quiz)
        st.rerun()
with c2:
    if st.button("🧹 오답 초기화", use_container_width=True, key="btn_clear_wrongs"):
        st.session_state.wrong_list = []
        st.success("오답을 비웠습니다.")
        st.rerun()

# 최초 1회 자동 생성
if "quiz" not in st.session_state or not isinstance(st.session_state.quiz, list):
    st.session_state.quiz = []
if len(st.session_state.quiz) == 0:
    quiz = build_quiz_now()
    start_quiz(quiz)

quiz = st.session_state.quiz
answers = st.session_state.answers

# ============================================================
# ✅ 문제 표시
# ============================================================
for idx, q in enumerate(quiz):
    st.subheader(f"Q{idx+1}")

    qv = st.session_state.quiz_version
    widget_key = f"q_{qv}_{idx}"

    if q.get("mode") == "use_final":
        prompt = q.get("prompt_tpl", "____")
        st.markdown(f"<div class='jp' style='margin-top:-6px; margin-bottom:6px; font-size:18px; font-weight:500; line-height:1.35;'>{prompt}</div>", unsafe_allow_html=True)
        if q.get("meaning_kr"):
            st.caption(f"뜻 힌트: {q['meaning_kr']}")
    else:
        st.markdown(f"<div class='jp' style='margin-top:-6px; margin-bottom:6px; font-size:18px; font-weight:500; line-height:1.35;'>{q.get('prompt','')}</div>", unsafe_allow_html=True)

    prev = answers[idx]
    default_index = q["choices"].index(prev) if (prev is not None and prev in q["choices"]) else None

    picked = st.radio(
        label="보기",
        options=q["choices"],
        index=default_index,
        key=widget_key,
        label_visibility="collapsed",
    )
    answers[idx] = picked

sync_answers()

# ============================================================
# ✅ 제출/채점
# ============================================================
quiz_len = len(quiz)
all_answered = (quiz_len > 0) and all(a is not None for a in answers)

if st.button("✅ 제출하고 채점하기", disabled=not all_answered, type="primary", use_container_width=True, key="btn_submit"):
    st.session_state.submitted = True

if not all_answered:
    st.info("모든 문제에 답을 선택하면 제출 버튼이 활성화됩니다.")

# ============================================================
# ✅ 오답노트 JSON 저장 규격(스펙)
# ============================================================
def build_wrong_item(idx: int, q: dict, picked: str) -> dict:
    """
    ✅ 오답노트 JSON 스펙(고정):
      {
        "v": 1,
        "ts": <unix>,
        "no": 1..N,
        "set": {"level": "...", "pos_pick": "...", "mode": "...", "qtype": "..."},
        "q": {
          "prompt": "...", "choices": [...], "correct": "...", "picked": "..."
        },
        "word": {
          "jp_word": "...", "reading": "...", "meaning_kr": "...",
          "example_jp": "...", "example_kr": "...",
          "pos": "...", "level": "..."
        },
        "kanji": {"candidate": "...", "confidence": "..."}
      }
    """
    mode = q.get("mode", "")
    qtype = q.get("qtype", "") if mode == "core" else "use_final"

    if mode == "use_final":
        prompt = q.get("prompt_tpl", "")
    else:
        prompt = q.get("prompt", "")

    return {
        "v": 1,
        "ts": int(time.time()),
        "no": int(idx + 1),
        "set": {
            "level": st.session_state.level,
            "pos_pick": st.session_state.pos_pick,
            "mode": mode,
            "qtype": qtype,
        },
        "q": {
            "prompt": prompt,
            "choices": list(q.get("choices", [])),
            "correct": str(q.get("correct_text", "")),
            "picked": "" if picked is None else str(picked),
        },
        "word": {
            "jp_word": str(q.get("jp_word", "")),
            "reading": str(q.get("reading", "")),
            "meaning_kr": str(q.get("meaning_kr", "")),
            "example_jp": str(q.get("example_jp", "")),
            "example_kr": str(q.get("example_kr", "")),
            "pos": str(q.get("pos", "")),
            "level": str(q.get("level", "")),
        },
        "kanji": {
            "candidate": str(q.get("kanji_candidate", "")),
            "confidence": str(q.get("kanji_confidence", "")),
        }
    }

# ============================================================
# ✅ 제출 후 화면
# ============================================================
if st.session_state.get("submitted"):
    score = 0
    wrong_list = []

    for idx, q in enumerate(quiz):
        picked = answers[idx]
        correct = q.get("correct_text")
        if picked == correct:
            score += 1
        else:
            wrong_list.append(build_wrong_item(idx, q, picked))

    st.success(f"점수: {score} / {quiz_len}")

    if score == quiz_len:
        st.balloons()
        st.success("🎉 완벽! 오늘 루틴 성공입니다.")
    elif score >= int(quiz_len * 0.7):
        st.info("👍 흐름 좋습니다. 오답만 한 번 더 보면 ‘진짜 내 것’ 돼요.")
    else:
        st.warning("💪 괜찮아요. 오답은 ‘학습이 일어난 증거’입니다.")

    st.session_state.wrong_list = wrong_list

    # 오답노트 표시
    if wrong_list:
        st.subheader("❌ 오답 노트")
        for w in wrong_list:
            no = w["no"]
            jp = w["word"]["jp_word"]
            prompt = w["q"]["prompt"]
            picked = w["q"]["picked"]
            correct = w["q"]["correct"]
            reading = w["word"]["reading"]
            meaning = w["word"]["meaning_kr"]
            mode = w["set"]["mode"]

            st.markdown(f"""
<div class="jp">
  <div class="wrong-card">
    <div class="wrong-top">
      <div>
        <div class="wrong-title">Q{no}. {jp}</div>
        <div class="wrong-sub">{prompt} · mode: {mode}</div>
      </div>
      <div class="tag">오답</div>
    </div>

    <div class="ans-row"><div class="ans-k">내 답</div><div>{picked}</div></div>
    <div class="ans-row"><div class="ans-k">정답</div><div><b>{correct}</b></div></div>
    <div class="ans-row"><div class="ans-k">발음</div><div>{reading}</div></div>
    <div class="ans-row"><div class="ans-k">뜻</div><div>{meaning}</div></div>
  </div>
</div>
""", unsafe_allow_html=True)

        # ✅ 오답 JSON 다운로드
        st.download_button(
            "⬇️ 오답노트 JSON 내려받기",
            data=json.dumps(wrong_list, ensure_ascii=False, indent=2).encode("utf-8"),
            file_name="wrong_note.json",
            mime="application/json",
            use_container_width=True,
            key="btn_dl_wrong_json",
        )

        # 오답만 다시 풀기
        if st.button("❌ 오답만 다시 풀기", type="primary", use_container_width=True, key="btn_retry_wrongs"):
            clear_q_keys()
            # 오답 jp_word만 모아서 우선 출제
            keys = [x["word"]["jp_word"] for x in wrong_list]
            retry_df = pool[pool["jp_word"].isin(keys)].copy()
            retry_df = retry_df.sample(frac=1).reset_index(drop=True)

            retry_quiz: list[dict] = []
            for _, r in retry_df.iterrows():
                if r["pos"] in POS_LABELS_USE:
                    retry_quiz.append(make_use_final_question(r, pool))
                else:
                    qt = st.session_state.quiz_type
                    retry_quiz.append(make_core_question(r, qt, pool))

            start_quiz(retry_quiz[:max(5, len(retry_quiz))])
            st.rerun()

    # ✅ daily_mix 자동 배치 훅
    maybe_auto_queue_daily_mix_after_submit()
