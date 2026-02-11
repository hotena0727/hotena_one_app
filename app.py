# app.py  (복붙용 단일 파일)
from __future__ import annotations

from pathlib import Path
import random
import time
import traceback
import unicodedata
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# ----------------------------
# Page
# ----------------------------
st.set_page_config(page_title="왕초보 탈출 마법의 단어장", layout="centered")

# ----------------------------
# Constants
# ----------------------------
BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "data" / "왕초보_탈출_마법의_단어장_완성본_300_대표한자후보_confidence.csv"  # 선우님 파일명에 맞게 수정 가능
N = 10

LEVELS = ["N5", "N4", "N3", "N2", "N1"]

# pos 라벨: 선우님 기준으로 통일
# - i_adj / na_adj (권장)
# - verb / noun / adv / particle / expr 등
POS_LABELS_MAIN = ["noun", "verb", "i_adj", "na_adj", "adv"]
POS_LABELS_USE  = ["particle", "expr"]  # use 엔진 전용

QUIZ_TYPES = ["reading", "meaning", "kr2jp", "daily_mix", "use_final"]

QUIZ_LABEL = {
    "reading": "발음",          # ✅ (읽기 → 발음)
    "meaning": "뜻",
    "kr2jp": "한→일(단어)",
    "daily_mix": "오늘의 추천",
    "use_final": "USE(조사·표현)",
}

READ_KW = dict(
    dtype=str,
    keep_default_na=False,
    na_values=["nan", "NaN", "NULL", "null", "None", "none"],
)

# ----------------------------
# Minimal UI CSS
# ----------------------------
st.markdown(
    """
<style>
:root{ --jp: -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans JP","Hiragino Sans","Yu Gothic","Meiryo",sans-serif; }
.jp, .jp *{ font-family: var(--jp) !important; line-height:1.65; letter-spacing:.2px; }
.smallcap{ opacity:.72; font-size:13px; }
.card{
  border:1px solid rgba(120,120,120,0.25);
  border-radius:18px;
  padding:14px 14px;
  background: rgba(255,255,255,0.03);
}
.pill{
  display:inline-flex; align-items:center; gap:6px;
  padding:6px 10px; border-radius:999px;
  border:1px solid rgba(120,120,120,0.25);
  background: rgba(255,255,255,0.03);
  font-size:12px; font-weight:800;
}
.wrong-card{
  border: 1px solid rgba(120,120,120,0.25);
  border-radius: 16px;
  padding: 14px 14px;
  margin-bottom: 10px;
  background: rgba(255,255,255,0.02);
}
.wrong-title{ font-weight: 900; font-size: 15px; margin-bottom: 4px; }
.wrong-sub{ opacity: 0.8; font-size: 12px; }
.ans-row{ display:grid; grid-template-columns: 72px 1fr; gap:10px; margin-top:6px; font-size: 13px; }
.ans-k{ opacity: 0.7; font-weight: 800; }
</style>
""",
    unsafe_allow_html=True
)

# ----------------------------
# Helpers
# ----------------------------
def _nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", str(s or "")).strip()

def _to_hira(s: str) -> str:
    s = _nfkc(s)
    out = []
    for ch in s:
        code = ord(ch)
        if 0x30A1 <= code <= 0x30F6:
            out.append(chr(code - 0x60))
        else:
            out.append(ch)
    return "".join(out)

def mastery_key(level: str, qtype: str) -> str:
    return f"{level}__{qtype}"

# ----------------------------
# Wrongnote (통일 규격)
# ----------------------------
def ensure_wrongnote_shape():
    if "wrongnote" not in st.session_state or not isinstance(st.session_state["wrongnote"], list):
        st.session_state["wrongnote"] = []

def wrongnote_append(item: dict):
    ensure_wrongnote_shape()
    st.session_state["wrongnote"].append(item)

def wrongnote_record_core(idx: int, q: dict, picked: str | None):
    """core(발음/뜻/한→일) 오답 기록 통일 규격"""
    correct = str(q.get("correct_text", ""))
    if (picked is not None) and (str(picked) == correct):
        return

    item = {
        "No": idx + 1,
        "문제": str(q.get("prompt", "")),
        "내 답": "" if picked is None else str(picked),
        "정답": correct,
        "단어": str(q.get("jp_word", "")).strip(),
        "발음": str(q.get("reading", "")).strip(),      # ✅ 발음
        "뜻": str(q.get("meaning_kr", "")).strip(),     # ✅ meaning_kr
        "레벨": str(q.get("level", "")).strip(),
        "품사": str(q.get("pos", "")).strip(),
        "유형": str(q.get("qtype", "")),
        "선택지": q.get("choices", []),
    }
    wrongnote_append(item)

def record_use_attempt_to_wrongnote(q: dict, idx: int, picked: str | None, is_correct: bool):
    """use_final 오답 기록 통일 규격"""
    if is_correct:
        return
    item = {
        "No": idx + 1,
        "문제": str(q.get("prompt_tpl", "")).replace("{blank}", "____"),
        "내 답": "" if picked is None else str(picked),
        "정답": str(q.get("correct_text", "")),
        "단어": str(q.get("jp_word", "")).strip(),
        "발음": str(q.get("reading", "")).strip(),
        "뜻": str(q.get("meaning_kr", "")).strip(),
        "레벨": str(q.get("level", "")).strip(),
        "품사": str(q.get("pos", "")).strip(),
        "유형": "use_final",
        "선택지": q.get("choices", []),
    }
    wrongnote_append(item)

# ----------------------------
# Load Pool
# CSV 설계:
# level	pos	jp_word	reading	meaning_kr	example_jp	example_kr	show_kanji	kanji_candidate	kanji_confidence
# ----------------------------
@st.cache_data(show_spinner=False)
def load_pool(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, **READ_KW)

    required = {"level", "pos", "jp_word", "reading", "meaning_kr"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV 필수 컬럼 누락: {sorted(list(missing))}")

    def norm_level(x: str) -> str:
        x = _nfkc(x).upper().replace(" ", "")
        m = pd.Series([x]).str.extract(r"(N[1-5])", expand=False).iloc[0]
        if isinstance(m, str) and m in LEVELS:
            return m
        digit_map = {"1":"N1","2":"N2","3":"N3","4":"N4","5":"N5"}
        if x in digit_map:
            return digit_map[x]
        return ""

    df["level"] = df["level"].apply(norm_level)
    df["pos"] = df["pos"].astype(str).str.strip().str.lower()

    # 필드 정리
    for col in ["jp_word", "reading", "meaning_kr", "example_jp", "example_kr"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    # empty 제거
    df = df[(df["level"] != "") & (df["jp_word"] != "") & (df["reading"] != "") & (df["meaning_kr"] != "")].copy()

    # 한자 후보/신뢰도 컬럼이 없을 수도 있으니 안전 처리
    if "kanji_candidate" not in df.columns:
        df["kanji_candidate"] = ""
    if "kanji_confidence" not in df.columns:
        df["kanji_confidence"] = ""

    # show_kanji 기본값
    if "show_kanji" not in df.columns:
        df["show_kanji"] = "Y"

    return df.reset_index(drop=True)

def ensure_pool():
    if st.session_state.get("_pool_ready") and isinstance(st.session_state.get("_pool"), pd.DataFrame):
        return
    try:
        pool = load_pool(str(CSV_PATH))
    except Exception as e:
        st.error(f"단어 데이터 로드 실패: {e}")
        st.stop()

    st.session_state["_pool"] = pool
    st.session_state["_pool_ready"] = True

# ----------------------------
# Selection Strategy (daily_mix)
# ----------------------------
def choose_level_for_daily_mix(base_level: str, allow_soft_promo: bool = True) -> str:
    """
    ✅ N5에서도 일부 N4를 섞는 부드러운 승급
    - N5: 80% N5, 20% N4 (allow_soft_promo=True)
    - N4+: 그대로 (또는 필요하면 확장 가능)
    """
    base_level = base_level.upper().strip()
    if base_level == "N5" and allow_soft_promo:
        return "N4" if random.random() < 0.20 else "N5"
    return base_level

def sample_by_level_pos(level: str, pos_list: list[str], k: int) -> pd.DataFrame:
    ensure_pool()
    pool = st.session_state["_pool"]
    df = pool[(pool["level"] == level) & (pool["pos"].isin(pos_list))].copy()
    if len(df) == 0:
        return df
    if len(df) <= k:
        return df.sample(frac=1).reset_index(drop=True)
    return df.sample(n=k, replace=False).reset_index(drop=True)

def pick_from_wrongs_first(level: str, k: int) -> pd.DataFrame:
    """
    ✅ 오답이면 복습 가중치:
    wrongnote에 쌓인 단어(jp_word)를 우선으로 뽑아서 daily_mix에 섞는다.
    - 단, 레벨이 맞는 것만
    """
    ensure_wrongnote_shape()
    ensure_pool()
    pool = st.session_state["_pool"]

    wrong_words = []
    for it in st.session_state["wrongnote"]:
        w = str(it.get("단어", "")).strip()
        if w:
            wrong_words.append(w)
    wrong_words = list(dict.fromkeys(wrong_words))  # uniq preserve

    if not wrong_words:
        return pool.iloc[0:0].copy()

    df = pool[(pool["level"] == level) & (pool["jp_word"].isin(wrong_words))].copy()
    if len(df) == 0:
        return pool.iloc[0:0].copy()

    df = df.sample(frac=1).reset_index(drop=True)
    return df.head(k).copy()

# ----------------------------
# Question Builders (core)
# ----------------------------
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
    elif qtype == "meaning":
        prompt = f"{jp}의 뜻은?"
        correct = mn
        candidates = pool_pos.loc[pool_pos["meaning_kr"] != correct, "meaning_kr"].drop_duplicates().tolist()
    elif qtype == "kr2jp":
        prompt = f"'{mn}'의 일본어는?"
        correct = jp
        candidates = pool_pos.loc[pool_pos["jp_word"] != correct, "jp_word"].drop_duplicates().tolist()
    else:
        raise ValueError("unknown core qtype")

    candidates = [c for c in candidates if str(c).strip()]

    if len(candidates) < 3:
        # 왕초보 데이터에서는 소수 품사에서 발생 가능 → 안전하게 전체 pos로 완화
        candidates2 = pool.loc[
            (pool["pos"] == pos) &
            ((pool["reading"] if qtype=="reading" else pool["meaning_kr"] if qtype=="meaning" else pool["jp_word"]) != correct),
        ]
        candidates = candidates2[
            "reading" if qtype=="reading" else "meaning_kr" if qtype=="meaning" else "jp_word"
        ].drop_duplicates().tolist()
        candidates = [c for c in candidates if str(c).strip()]

    if len(candidates) < 3:
        # 마지막 안전장치: 전체 풀에서 채우기
        col = "reading" if qtype=="reading" else "meaning_kr" if qtype=="meaning" else "jp_word"
        candidates = pool.loc[pool[col] != correct, col].drop_duplicates().tolist()
        candidates = [c for c in candidates if str(c).strip()]

    wrongs = random.sample(candidates, 3)
    choices = wrongs + [correct]
    random.shuffle(choices)

    return {
        "qtype": qtype,
        "prompt": prompt,
        "choices": choices,
        "correct_text": correct,

        "level": lvl,
        "pos": pos,
        "jp_word": jp,
        "reading": rd,
        "meaning_kr": mn,

        # 한자 후보 (옵션)
        "kanji_candidate": str(row.get("kanji_candidate", "")).strip(),
        "kanji_confidence": str(row.get("kanji_confidence", "")).strip(),
    }

# ----------------------------
# use_final engine (조사·표현)
# ----------------------------
def make_use_final_question(row: pd.Series, pool: pd.DataFrame) -> dict:
    """
    ✅ use_final:
    - prompt_tpl: "{blank} は 〜です" 형태 템플릿
    - 정답: row의 jp_word (조사/표현)
    - 보기: 같은 pos에서 3개
    """
    jp = str(row.get("jp_word", "")).strip()
    rd = str(row.get("reading", "")).strip()
    mn = str(row.get("meaning_kr", "")).strip()
    lvl = str(row.get("level", "")).strip()
    pos = str(row.get("pos", "")).strip()

    # 템플릿: expr/particle에 따라 가볍게 분기
    if pos == "particle":
        prompt_tpl = "{blank} いきます / {blank} たべます"
    else:
        prompt_tpl = "{blank}！(상황에 맞게 사용)"

    pool_pos = pool[pool["pos"] == pos].copy()
    candidates = pool_pos.loc[pool_pos["jp_word"] != jp, "jp_word"].drop_duplicates().tolist()
    candidates = [c for c in candidates if str(c).strip()]

    if len(candidates) < 3:
        # 전체 use pos로 완화
        candidates = pool.loc[(pool["pos"].isin(POS_LABELS_USE)) & (pool["jp_word"] != jp), "jp_word"].drop_duplicates().tolist()
        candidates = [c for c in candidates if str(c).strip()]

    wrongs = random.sample(candidates, 3)
    choices = wrongs + [jp]
    random.shuffle(choices)

    return {
        "qtype": "use_final",
        "prompt_tpl": prompt_tpl,
        "choices": choices,
        "correct_text": jp,

        "level": lvl,
        "pos": pos,
        "jp_word": jp,
        "reading": rd,
        "meaning_kr": mn,

        "kanji_candidate": str(row.get("kanji_candidate", "")).strip(),
        "kanji_confidence": str(row.get("kanji_confidence", "")).strip(),
    }

def render_use_final_question(q: dict, idx: int):
    st.subheader(f"Q{idx+1}")

    prompt = str(q.get("prompt_tpl", "")).replace("{blank}", "____")
    st.markdown(f"<div class='jp' style='margin-top:-6px; font-size:18px; font-weight:600;'>{prompt}</div>", unsafe_allow_html=True)
    st.caption("심리 안정 문구: 괜찮아요. 감으로 찍어도 학습이 됩니다 🙂")

    widget_key = f"use_{st.session_state.quiz_version}_{idx}"
    picked = st.radio("보기", q["choices"], key=widget_key, label_visibility="collapsed")

    # 즉시 채점(=use_final은 가볍게 체감)
    is_correct = (picked == q["correct_text"])
    if st.button("✅ 확인", use_container_width=True, key=f"btn_use_check_{st.session_state.quiz_version}_{idx}"):
        if is_correct:
            st.success("정답 ✅ (이런 식으로 ‘자주 쓰는 자리’를 익히면 빨라요.)")
        else:
            st.warning(f"오답 ❌ 정답: {q['correct_text']}")
        record_use_attempt_to_wrongnote(q, idx, picked, is_correct)

# ----------------------------
# Build Quiz (core / daily_mix / use_final)
# ----------------------------
def build_core_quiz(level: str, qtype: str) -> list[dict]:
    ensure_pool()
    pool = st.session_state["_pool"]

    level = level.upper().strip()
    base = pool[pool["level"] == level].copy()
    if len(base) < N:
        st.warning(f"{level} 데이터가 부족합니다. (현재 {len(base)}개 / 필요 {N}개)")
        return []

    sampled = base.sample(n=N, replace=False).reset_index(drop=True)
    return [make_core_question(sampled.iloc[i], qtype, pool) for i in range(N)]

def build_use_final_set(level: str, k: int = 4) -> list[dict]:
    """
    오늘의 추천에서 뒤쪽에 자동 배치하는 use_final 묶음
    """
    ensure_pool()
    pool = st.session_state["_pool"]

    level = level.upper().strip()
    base = pool[(pool["level"] == level) & (pool["pos"].isin(POS_LABELS_USE))].copy()
    if len(base) == 0:
        return []

    if len(base) < k:
        base = base.sample(frac=1).reset_index(drop=True)
    else:
        base = base.sample(n=k, replace=False).reset_index(drop=True)

    return [make_use_final_question(base.iloc[i], pool) for i in range(len(base))]

def build_daily_mix(level: str) -> list[dict]:
    """
    ✅ 오늘의 추천:
    - 앞부분: core(명/동/형) + 부사 (4지선다)
    - 뒷부분: use_final(조사/표현) 자동 배치
    - N5 / N4+ 분기 + N5 soft promo + 오답 복습 가중치
    """
    ensure_pool()
    pool = st.session_state["_pool"]

    base_level = level.upper().strip()
    lv_for_core = choose_level_for_daily_mix(base_level, allow_soft_promo=True)

    # (A) 오답 복습 우선 3문항
    review_df = pick_from_wrongs_first(lv_for_core, k=3)

    # (B) 신규: 코어(명/동/형) 4문항 + 부사 3문항 = 총 7문항
    core_df = sample_by_level_pos(lv_for_core, ["noun", "verb", "i_adj", "na_adj"], k=4)
    adv_df  = sample_by_level_pos(lv_for_core, ["adv"], k=3)

    merged = pd.concat([review_df, core_df, adv_df], ignore_index=True)
    merged = merged.drop_duplicates(subset=["jp_word"]).reset_index(drop=True)

    # 부족하면 전체 main pos에서 보충
    if len(merged) < 7:
        need = 7 - len(merged)
        filler = sample_by_level_pos(lv_for_core, POS_LABELS_MAIN, k=need)
        merged = pd.concat([merged, filler], ignore_index=True).drop_duplicates(subset=["jp_word"]).reset_index(drop=True)

    # core 문항 유형 고정 규칙(추천):
    # - noun: meaning
    # - verb: reading
    # - i_adj/na_adj: meaning
    # - adv: meaning
    def fixed_qtype_by_pos(pos: str) -> str:
        pos = (pos or "").lower().strip()
        if pos == "verb":
            return "reading"    # 동사는 발음 중심이 체감이 좋음
        return "meaning"

    core_questions = []
    for i in range(min(7, len(merged))):
        r = merged.iloc[i]
        qt = fixed_qtype_by_pos(str(r.get("pos", "")))
        core_questions.append(make_core_question(r, qt, pool))

    # (C) use_final: 레벨 분기
    # - N5: particle 2 + expr 2 (가능하면)
    # - N4+: particle 1 + expr 3 (표현 비중 업)
    use_k = 4
    use_lv = base_level  # use는 기본레벨 기준(체감 안정)
    use_set = build_use_final_set(use_lv, k=use_k)

    # 최종 10문항: core 6 + use 4 (or core7 + use3 등 조정 가능)
    # 지금은 체감 좋게 core 6 + use 4
    core_take = 6 if len(core_questions) >= 6 else len(core_questions)
    quiz = core_questions[:core_take] + use_set[:(N - core_take)]

    # 부족하면 core로 채우기
    while len(quiz) < N:
        extra = build_core_quiz(lv_for_core, "meaning")
        if not extra:
            break
        quiz.append(extra[0])

    return quiz[:N]

# ----------------------------
# State
# ----------------------------
def clear_question_keys():
    keys = [k for k in list(st.session_state.keys()) if isinstance(k, str) and (k.startswith("q_") or k.startswith("use_"))]
    for k in keys:
        st.session_state.pop(k, None)

def start_quiz_state(quiz: list[dict], qtype: str):
    st.session_state.quiz_version = int(st.session_state.get("quiz_version", 0)) + 1
    st.session_state.quiz_type = qtype
    st.session_state.quiz = quiz if isinstance(quiz, list) else []
    st.session_state.answers = [None] * len(st.session_state.quiz)
    st.session_state.submitted = False

# defaults
if "level" not in st.session_state:
    st.session_state.level = "N5"
if "quiz_type" not in st.session_state:
    st.session_state.quiz_type = "daily_mix"
if "quiz_version" not in st.session_state:
    st.session_state.quiz_version = 0
if "quiz" not in st.session_state:
    st.session_state.quiz = []
if "answers" not in st.session_state:
    st.session_state.answers = []
if "submitted" not in st.session_state:
    st.session_state.submitted = False

ensure_wrongnote_shape()
ensure_pool()

# ----------------------------
# Header
# ----------------------------
st.markdown(
    """
<div class="jp">
  <div style="font-size:30px; font-weight:900; line-height:1.1;">🪄 왕초보 탈출 마법의 단어장</div>
  <div class="smallcap">오늘은 “안전하게 할 수 있는 것”만. 어려우면 안 내보냅니다 🙂</div>
</div>
""",
    unsafe_allow_html=True
)
st.divider()

# ----------------------------
# Top Controls
# ----------------------------
c1, c2 = st.columns([5, 5])
with c1:
    st.session_state.level = st.selectbox("레벨", LEVELS, index=LEVELS.index(st.session_state.level))
with c2:
    qt = st.selectbox("유형", QUIZ_TYPES, index=QUIZ_TYPES.index(st.session_state.quiz_type),
                      format_func=lambda x: QUIZ_LABEL.get(x, x))
    st.session_state.quiz_type = qt

st.markdown(
    """
<div class="jp card">
  <div style="font-weight:900; font-size:16px;">✨ 오늘의 추천</div>
  <div class="smallcap">지금은 “틀려도 괜찮은 모드”예요. 정답보다 ‘노출’이 더 중요합니다.</div>
</div>
""",
    unsafe_allow_html=True
)

btn1, btn2 = st.columns(2)
with btn1:
    if st.button("🔄 새 문제(10문항)", use_container_width=True):
        clear_question_keys()
        lv = st.session_state.level
        qtype = st.session_state.quiz_type

        if qtype == "daily_mix":
            quiz = build_daily_mix(lv)
        elif qtype == "use_final":
            quiz = build_use_final_set(lv, k=N)
        else:
            quiz = build_core_quiz(lv, qtype)

        start_quiz_state(quiz, qtype)
        st.rerun()

with btn2:
    if st.button("🧹 오답노트 비우기", use_container_width=True):
        st.session_state["wrongnote"] = []
        st.success("오답노트를 비웠습니다.")
        st.rerun()

st.divider()

# 최초 1회 자동 생성
if not st.session_state.quiz:
    qtype = st.session_state.quiz_type
    lv = st.session_state.level

    if qtype == "daily_mix":
        quiz = build_daily_mix(lv)
    elif qtype == "use_final":
        quiz = build_use_final_set(lv, k=N)
    else:
        quiz = build_core_quiz(lv, qtype)

    start_quiz_state(quiz, qtype)

# ----------------------------
# Render Questions
# ----------------------------
quiz = st.session_state.quiz
if not quiz:
    st.info("출제할 데이터가 없습니다. CSV 레벨/품사를 확인해 주세요.")
    st.stop()

# daily_mix에서는 use_final 문항이 섞일 수 있음 → 렌더 분기
for idx, q in enumerate(quiz):
    if q.get("qtype") == "use_final":
        render_use_final_question(q, idx)
        st.divider()
        continue

    # core 문항
    st.subheader(f"Q{idx+1}")
    st.markdown(
        f"<div class='jp' style='margin-top:-6px; font-size:18px; font-weight:600;'>{q['prompt']}</div>",
        unsafe_allow_html=True
    )
    st.caption("심리 안정 문구: 지금은 속도가 먼저예요. ‘정확함’은 나중에 따라옵니다 🙂")

    widget_key = f"q_{st.session_state.quiz_version}_{idx}"
    picked = st.radio("보기", q["choices"], key=widget_key, label_visibility="collapsed")
    st.session_state.answers[idx] = picked

st.divider()

# ----------------------------
# Submit & Score (core만 채점, use_final은 즉시확인형)
# ----------------------------
# core 문항만 제출 채점: use_final은 위에서 이미 처리
core_indices = [i for i, q in enumerate(quiz) if q.get("qtype") != "use_final"]
all_core_answered = all(st.session_state.answers[i] is not None for i in core_indices) if core_indices else True

if st.button("✅ 제출하고 채점하기(코어)", type="primary", use_container_width=True, disabled=not all_core_answered):
    st.session_state.submitted = True

if st.session_state.submitted:
    score = 0
    total = len(core_indices)
    for i in core_indices:
        q = quiz[i]
        picked = st.session_state.answers[i]
        if str(picked) == str(q["correct_text"]):
            score += 1
        else:
            wrongnote_record_core(i, q, picked)

    if total > 0:
        st.success(f"코어 점수: {score} / {total}")
    else:
        st.info("이번 세트는 use(조사·표현) 중심이라 코어 채점이 없습니다.")

# ----------------------------
# Wrongnote Render (통합)
# ----------------------------
if st.session_state.get("wrongnote"):
    st.subheader("❌ 오답노트(통합 저장)")

    def _s(v): return "" if v is None else str(v)

    for it in st.session_state["wrongnote"][-30:][::-1]:  # 최근 30개만
        no = _s(it.get("No"))
        word = _s(it.get("단어"))
        qtext = _s(it.get("문제"))
        picked = _s(it.get("내 답"))
        correct = _s(it.get("정답"))
        pron = _s(it.get("발음"))
        meaning = _s(it.get("뜻"))
        qtype = QUIZ_LABEL.get(_s(it.get("유형")), _s(it.get("유형")))
        pos = _s(it.get("품사"))
        lv = _s(it.get("레벨"))

        st.markdown(
            f"""
<div class="jp">
  <div class="wrong-card">
    <div class="wrong-title">Q{no}. {word}</div>
    <div class="wrong-sub">{qtext} · 유형: {qtype} · {lv}/{pos}</div>

    <div class="ans-row"><div class="ans-k">내 답</div><div>{picked}</div></div>
    <div class="ans-row"><div class="ans-k">정답</div><div><b>{correct}</b></div></div>
    <div class="ans-row"><div class="ans-k">발음</div><div>{pron}</div></div>
    <div class="ans-row"><div class="ans-k">뜻</div><div>{meaning}</div></div>
  </div>
</div>
""",
            unsafe_allow_html=True
        )

# Debug
with st.expander("🔎 디버그(원하면 닫아두세요)", expanded=False):
    st.write("CSV_PATH =", str(CSV_PATH))
    pool = st.session_state.get("_pool")
    if isinstance(pool, pd.DataFrame):
        st.write("레벨별:", pool["level"].value_counts().to_dict())
        st.write("품사별:", pool["pos"].value_counts().to_dict())
    st.write("wrongnote len =", len(st.session_state.get("wrongnote", [])))
