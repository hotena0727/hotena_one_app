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
from supabase import create_client
from streamlit_cookies_manager import EncryptedCookieManager

# ============================================================
# ✅ Page
# ============================================================
st.set_page_config(page_title="왕초보 탈출 마법의 단어장", layout="centered")

# ============================================================
# ✅ Secrets
# ============================================================
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = st.secrets.get("SUPABASE_ANON_KEY", "")
COOKIE_PASSWORD = st.secrets.get("COOKIE_PASSWORD", "change_me_please_32chars_min")
ADMIN_EMAILS_RAW = st.secrets.get("ADMIN_EMAILS", "")
ADMIN_EMAILS = {e.strip().lower() for e in re.split(r"[;,]", ADMIN_EMAILS_RAW) if e.strip()}

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    st.error("secrets.toml에 SUPABASE_URL / SUPABASE_ANON_KEY가 필요합니다.")
    st.stop()

supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# ============================================================
# ✅ Cookies (세션 유지)
# ============================================================
cookies = EncryptedCookieManager(prefix="magic_words_", password=COOKIE_PASSWORD)
if not cookies.ready():
    st.stop()

# ============================================================
# ✅ UI Style (CSS가 화면에 글자로 보이는 문제 방지: style 태그만 깔끔히)
# ============================================================
st.markdown(
    """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Kosugi+Maru&family=Noto+Sans+JP:wght@400;500;700;800&display=swap" rel="stylesheet">

<style>
:root{ --jp-rounded: "Noto Sans JP","Kosugi Maru","Hiragino Sans","Yu Gothic","Meiryo",sans-serif; }
.jp, .jp *{ font-family: var(--jp-rounded) !important; line-height:1.7; letter-spacing:.2px; }

/* buttons */
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

/* wrong note card */
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
.small-muted{ opacity:.75; font-size:12px; }

/* home card */
.home-card{
  border: 1px solid rgba(120,120,120,0.22);
  border-radius: 16px;
  padding: 14px 14px;
  background: rgba(255,255,255,0.03);
}
</style>
""",
    unsafe_allow_html=True,
)

# ============================================================
# ✅ CSV / Quiz constants
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "data" / "one.csv"  # ✅ 마킹된 CSV 권장
N = 10

# 왕초보: 레벨 선택 제거 → 기본 N5 고정
FIXED_LEVEL = "N5"

POS_CANON = {
    # i_adj 통일
    "adji_i": "i_adj", "adj_i": "i_adj", "i-adj": "i_adj", "adj-i": "i_adj", "i_adj": "i_adj",
    # na_adj 통일
    "adji_na": "na_adj", "adj_na": "na_adj", "na-adj": "na_adj", "adj-na": "na_adj", "na_adj": "na_adj",
}

POS_BUTTONS_CORE = [
    ("noun", "명사"),
    ("verb", "동사"),
    ("i_adj", "い형용사"),
    ("na_adj", "な형용사"),
    ("adv", "부사"),
]

POS_LABELS_USE = {"particle", "expr"}  # 조사/표현

QUIZ_TYPES_CORE = [
    ("reading", "발음"),   # ✅ “읽기” → “발음”
    ("meaning", "뜻"),
    ("kr2jp",   "한→일"),
]

DAILY_MIX_RATIO = {"use": 2, "adv": 2, "core": 6}

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
    return ""

def now_ts() -> int:
    return int(time.time())

def truthy(x: str) -> bool:
    return str(x or "").strip().lower() in {"1","true","yes","y","on"}

def display_jp_word(row: pd.Series) -> str:
    """
    화면에 보여줄 일본어 표기.
    - show_kanji가 true면 kanji_candidate(있으면) 우선
    - 없으면 jp_word
    """
    jp = str(row.get("jp_word", "")).strip()
    show = truthy(row.get("show_kanji", ""))
    kc = str(row.get("kanji_candidate", "")).strip()
    conf = str(row.get("kanji_confidence", "")).strip().lower()

    if show and kc:
        # low라도 보여줄지 여부는 여기서 결정
        # 왕초보라도 토글이 있다면 "후보"라도 노출 OK로 가는 게 자연스러움
        return kc
    return jp

# ============================================================
# ✅ Supabase Auth helpers
# ============================================================
def set_auth_cookie(session: dict):
    cookies["sb_session"] = json.dumps(session, ensure_ascii=False)
    cookies.save()

def get_auth_cookie() -> dict | None:
    raw = cookies.get("sb_session")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None

def clear_auth_cookie():
    try:
        cookies["sb_session"] = ""
        cookies.save()
    except Exception:
        pass

def refresh_session_if_needed() -> dict | None:
    """
    쿠키에 저장된 access/refresh로 세션 복원.
    만료면 refresh로 재발급 시도.
    """
    sess = get_auth_cookie()
    if not sess:
        return None
    access = sess.get("access_token")
    refresh = sess.get("refresh_token")
    if not access or not refresh:
        return None

    try:
        new_sess = supabase.auth.set_session(access, refresh)
        if new_sess and getattr(new_sess, "session", None):
            s = new_sess.session
            pack = {
                "access_token": s.access_token,
                "refresh_token": s.refresh_token,
                "user": {"id": s.user.id, "email": s.user.email},
            }
            set_auth_cookie(pack)
            return pack
    except Exception:
        return None

    return sess

def get_user() -> dict | None:
    sess = st.session_state.get("auth_session")
    if not sess:
        return None
    return sess.get("user")

def db_get_profile(user_id: str) -> dict | None:
    try:
        res = supabase.table("user_profiles").select("*").eq("user_id", user_id).limit(1).execute()
        data = res.data or []
        return data[0] if data else None
    except Exception:
        return None

def db_upsert_profile(user_id: str, email: str):
    try:
        supabase.table("user_profiles").upsert({"user_id": user_id, "email": email}).execute()
    except Exception:
        pass

def ensure_role_bootstrap(user: dict):
    if not user:
        return
    email = (user.get("email") or "").lower().strip()
    if not email or email not in ADMIN_EMAILS:
        return
    prof = db_get_profile(user["id"])
    if not prof:
        db_upsert_profile(user["id"], email)
        prof = db_get_profile(user["id"])
    if prof and prof.get("role") != "admin":
        try:
            supabase.table("user_profiles").update({"role": "admin"}).eq("user_id", user["id"]).execute()
        except Exception:
            pass

# ============================================================
# ✅ CSV Load
# ============================================================
READ_KW = dict(dtype=str, keep_default_na=False, na_values=["nan","NaN","NULL","null","None","none"])

@st.cache_data(show_spinner=False)
def load_pool(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, **READ_KW)

    required = {"level","pos","jp_word","reading","meaning_kr","example_jp","example_kr","show_kanji"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV 필수 컬럼 누락: {sorted(list(missing))}")

    # optional cols
    if "kanji_candidate" not in df.columns:
        df["kanji_candidate"] = ""
    if "kanji_confidence" not in df.columns:
        df["kanji_confidence"] = ""

    df["level"] = df["level"].apply(norm_level)
    df["pos"] = df["pos"].astype(str).str.strip().str.lower().map(lambda x: POS_CANON.get(x, x))

    for c in ["jp_word","reading","meaning_kr","example_jp","example_kr","show_kanji","kanji_candidate","kanji_confidence"]:
        df[c] = df[c].astype(str).str.strip()

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
# ✅ use_final (빈칸 생성)
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
        padded = f" {ex} "
        padded = padded.replace(f" {t} ", " ____ ", 1)
        return padded.strip(), True

    if len(t) >= 2 and t in ex:
        return ex.replace(t, "____", 1), True

    return "{blank}", False

def make_use_final_question(row: pd.Series, pool: pd.DataFrame) -> dict:
    jp = str(row.get("jp_word", "")).strip()
    ex_jp = str(row.get("example_jp", "")).strip()
    prompt_tpl, used_example = build_blank_prompt_from_example(ex_jp, jp)
    if not used_example or prompt_tpl.strip() in ("{blank}", "____"):
        prompt_tpl = "____（빈칸에 알맞은 표현을 고르세요）"

    pos = str(row.get("pos","")).strip()
    candidates = pool[(pool["pos"] == pos) & (pool["jp_word"] != jp)]["jp_word"].drop_duplicates().tolist()
    candidates = [c for c in candidates if str(c).strip()]
    if len(candidates) < 3:
        candidates = pool[pool["pos"].isin(POS_LABELS_USE) & (pool["jp_word"] != jp)]["jp_word"].drop_duplicates().tolist()
        candidates = [c for c in candidates if str(c).strip()]
    if len(candidates) < 3:
        candidates = pool[pool["jp_word"] != jp]["jp_word"].drop_duplicates().tolist()
        candidates = [c for c in candidates if str(c).strip()]

    wrongs = random.sample(candidates, 3)
    choices = wrongs + [jp]
    random.shuffle(choices)

    return {
        "mode": "use_final",
        "prompt_tpl": prompt_tpl,
        "choices": choices,
        "correct_text": jp,
        "level": str(row.get("level","")).strip(),
        "pos": pos,
        "jp_word": jp,
        "reading": str(row.get("reading","")).strip(),
        "meaning_kr": str(row.get("meaning_kr","")).strip(),
        "example_jp": ex_jp,
        "example_kr": str(row.get("example_kr","")).strip(),
        "show_kanji": str(row.get("show_kanji","")).strip(),
        "kanji_candidate": str(row.get("kanji_candidate","")).strip(),
        "kanji_confidence": str(row.get("kanji_confidence","")).strip(),
        "used_example": bool(used_example),
    }

def make_core_question(row: pd.Series, qtype: str, pool: pd.DataFrame) -> dict:
    jp = str(row.get("jp_word", "")).strip()
    rd = str(row.get("reading", "")).strip()
    mn = str(row.get("meaning_kr", "")).strip()
    lvl = str(row.get("level", "")).strip()
    pos = str(row.get("pos", "")).strip()

    # ✅ (보너스) 가나 단어는 발음 문제가 무의미할 수 있으니 자동 완화
    if qtype == "reading" and jp == rd:
        qtype = "meaning"

    pool_pos = pool[pool["pos"] == pos].copy()

    if qtype == "reading":
        shown = display_jp_word(row)  # ✅ 핵심: 문제 표기는 jp_word/한자 후보
        prompt = f"{shown}의 발음은?"
        correct = rd
        candidates = pool_pos.loc[pool_pos["reading"] != correct, "reading"].drop_duplicates().tolist()
    elif qtype == "meaning":
        shown = display_jp_word(row)
        prompt = f"{shown}의 뜻은?"
        correct = mn
        candidates = pool_pos.loc[pool_pos["meaning_kr"] != correct, "meaning_kr"].drop_duplicates().tolist()
    elif qtype == "kr2jp":
        prompt = f"'{mn}'의 일본어는?"
        correct = jp
        candidates = pool_pos.loc[pool_pos["jp_word"] != correct, "jp_word"].drop_duplicates().tolist()
    else:
        raise ValueError("unknown qtype")

    candidates = [c for c in candidates if str(c).strip()]
    if len(candidates) < 3:
        col = "reading" if qtype == "reading" else ("meaning_kr" if qtype == "meaning" else "jp_word")
        candidates = pool.loc[pool[col] != correct, col].drop_duplicates().tolist()
        candidates = [c for c in candidates if str(c).strip()]

    wrongs = random.sample(candidates, 3)
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
        "show_kanji": str(row.get("show_kanji","")).strip(),
        "kanji_candidate": str(row.get("kanji_candidate","")).strip(),
        "kanji_confidence": str(row.get("kanji_confidence","")).strip(),
    }

def pick_level_mix(level: str) -> dict[str, str]:
    level = level.upper().strip()
    if level == "N5": return {"base":"N5", "soft_up":"N4"}
    if level == "N4": return {"base":"N4", "soft_up":"N3"}
    if level == "N3": return {"base":"N3", "soft_up":"N2"}
    if level == "N2": return {"base":"N2", "soft_up":"N1"}
    return {"base":"N1", "soft_up":"N1"}

def build_daily_mix(level: str, pool: pd.DataFrame) -> list[dict]:
    mix = pick_level_mix(level)
    base_lv, soft_lv = mix["base"], mix["soft_up"]

    use_base = pool[(pool["level"] == base_lv) & (pool["pos"].isin(POS_LABELS_USE))]
    use_soft = pool[(pool["level"] == soft_lv) & (pool["pos"].isin(POS_LABELS_USE))]
    adv_base = pool[(pool["level"] == base_lv) & (pool["pos"] == "adv")]
    adv_soft = pool[(pool["level"] == soft_lv) & (pool["pos"] == "adv")]

    core_pos = {"noun","verb","i_adj","na_adj"}
    core_base = pool[(pool["level"] == base_lv) & (pool["pos"].isin(core_pos))]
    core_soft = pool[(pool["level"] == soft_lv) & (pool["pos"].isin(core_pos))]

    if len(core_base) < 30: core_base = pool[pool["pos"].isin(core_pos)]
    if len(adv_base) < 10: adv_base = pool[pool["pos"] == "adv"]
    if len(use_base) < 10: use_base = pool[pool["pos"].isin(POS_LABELS_USE)]

    def sample_df(df1, df2, k, soft_k=0):
        out = []
        soft_k = max(0, min(soft_k, k))
        base_k = k - soft_k
        if base_k > 0 and len(df1) > 0:
            out += df1.sample(n=min(base_k, len(df1)), replace=False).to_dict("records")
        if soft_k > 0 and len(df2) > 0:
            out += df2.sample(n=min(soft_k, len(df2)), replace=False).to_dict("records")
        return out

    use_rows  = sample_df(use_base,  use_soft,  DAILY_MIX_RATIO["use"],  soft_k=1 if base_lv != "N1" else 0)
    adv_rows  = sample_df(adv_base,  adv_soft,  DAILY_MIX_RATIO["adv"],  soft_k=1 if base_lv != "N1" else 0)
    core_rows = sample_df(core_base, core_soft, DAILY_MIX_RATIO["core"], soft_k=2 if base_lv in {"N5","N4"} else 1)

    def core_qtype_for_pos(p: str) -> str:
        if p in {"verb","i_adj","na_adj"}:
            return random.choices(["meaning","reading","kr2jp"], weights=[6,3,1])[0]
        if p == "noun":
            return random.choices(["meaning","kr2jp","reading"], weights=[6,3,1])[0]
        return "meaning"

    quiz = []
    for r in use_rows:
        quiz.append(make_use_final_question(pd.Series(r), pool))
    for r in adv_rows:
        qt = random.choices(["meaning","reading","kr2jp"], weights=[7,2,1])[0]
        quiz.append(make_core_question(pd.Series(r), qt, pool))
    for r in core_rows:
        row = pd.Series(r)
        qt = core_qtype_for_pos(str(row.get("pos","")))
        quiz.append(make_core_question(row, qt, pool))

    random.shuffle(quiz)
    return quiz[:N]

# ============================================================
# ✅ 오답이면 복습 가중치(가볍게)
# ============================================================
def apply_wrong_weight_pool(pool: pd.DataFrame, wrong_keys: list[str]) -> pd.DataFrame:
    keys = {k.strip() for k in wrong_keys if k and str(k).strip()}
    if not keys:
        return pool
    wrong_df = pool[pool["jp_word"].isin(keys)]
    if len(wrong_df) == 0:
        return pool
    return pd.concat([pool, wrong_df], ignore_index=True)

# ============================================================
# ✅ Quiz state
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
# ✅ DB save helpers
# ============================================================
def build_wrong_item(idx: int, q: dict, picked: str) -> dict:
    mode = q.get("mode", "")
    qtype = q.get("qtype", "") if mode == "core" else "use_final"
    prompt = q.get("prompt_tpl", "") if mode == "use_final" else q.get("prompt", "")

    return {
        "v": 1,
        "ts": now_ts(),
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
            "show_kanji": str(q.get("show_kanji", "")),
        },
        "kanji": {
            "candidate": str(q.get("kanji_candidate", "")),
            "confidence": str(q.get("kanji_confidence", "")),
        }
    }

def db_save_study_session(user_id: str, score: int, total: int):
    try:
        supabase.table("study_sessions").insert({
            "user_id": user_id,
            "level": st.session_state.level,
            "pos_pick": st.session_state.pos_pick,
            "quiz_type": st.session_state.quiz_type,
            "mode": st.session_state.pos_pick,
            "total": int(total),
            "score": int(score),
            "meta": {"app": "words_magic_v1"},
        }).execute()
    except Exception:
        pass

def db_save_wrong_notes(user_id: str, wrong_list: list[dict]):
    if not wrong_list:
        return
    rows = []
    for w in wrong_list:
        wd = w.get("word", {})
        qq = w.get("q", {})
        rows.append({
            "user_id": user_id,
            "level": wd.get("level",""),
            "pos": wd.get("pos",""),
            "jp_word": wd.get("jp_word",""),
            "reading": wd.get("reading",""),
            "meaning_kr": wd.get("meaning_kr",""),
            "prompt": qq.get("prompt",""),
            "choices": qq.get("choices", []),
            "correct": qq.get("correct",""),
            "picked": qq.get("picked",""),
            "payload": w,
        })
    try:
        supabase.table("wrong_notes").insert(rows).execute()
    except Exception:
        pass

# ============================================================
# ✅ Auth UI
# ============================================================
def render_login_box():
    st.subheader("🔐 로그인")
    with st.form("login_form", clear_on_submit=False):
        email = st.text_input("이메일", value="", placeholder="example@email.com")
        pw = st.text_input("비밀번호", value="", type="password", placeholder="비밀번호")
        c1, c2 = st.columns(2)
        with c1:
            login = st.form_submit_button("로그인", use_container_width=True)
        with c2:
            signup = st.form_submit_button("회원가입", use_container_width=True)

    if login:
        try:
            res = supabase.auth.sign_in_with_password({"email": email, "password": pw})
            s = res.session
            pack = {"access_token": s.access_token, "refresh_token": s.refresh_token, "user": {"id": s.user.id, "email": s.user.email}}
            set_auth_cookie(pack)
            st.session_state.auth_session = pack
            st.success("로그인 완료!")
            st.rerun()
        except Exception:
            st.error("로그인 실패: 이메일/비밀번호를 확인해주세요.")

    if signup:
        try:
            supabase.auth.sign_up({"email": email, "password": pw})
            st.success("회원가입 요청 완료! 이메일 인증이 필요할 수 있어요.")
        except Exception:
            st.error("회원가입 실패: 이미 가입된 이메일이거나 비밀번호 정책을 확인해주세요.")

def render_header_userbar(profile: dict | None):
    user = get_user()
    if not user:
        return

    email = user.get("email","")
    role = (profile or {}).get("role","user")
    banned = bool((profile or {}).get("is_banned", False))

    cols = st.columns([1,1,1])
    with cols[0]:
        st.markdown(f"<div class='small-muted'>로그인: <b>{email}</b></div>", unsafe_allow_html=True)
    with cols[1]:
        st.markdown(f"<div class='small-muted'>권한: <b>{role}</b></div>", unsafe_allow_html=True)
    with cols[2]:
        if st.button("로그아웃", use_container_width=True, key="btn_logout"):
            try:
                supabase.auth.sign_out()
            except Exception:
                pass
            clear_auth_cookie()
            st.session_state.auth_session = None
            st.rerun()

    if banned:
        reason = (profile or {}).get("banned_reason") or "관리자에 의해 접근이 제한되었습니다."
        st.error(f"접근 제한: {reason}")
        st.stop()

def render_admin_panel():
    st.subheader("🛠 관리자")
    st.caption("※ 프로필 role/is_banned 조회/업데이트(초기 운영용)")

    q = st.text_input("사용자 이메일 검색", value="", placeholder="email로 검색")
    if st.button("검색", key="btn_admin_search"):
        try:
            res = supabase.table("user_profiles").select("*").ilike("email", f"%{q}%").limit(20).execute()
            rows = res.data or []
            if rows:
                st.dataframe(pd.DataFrame(rows))
            else:
                st.info("검색 결과 없음")
        except Exception:
            st.error("검색 실패")

    st.markdown("### 빠른 차단/해제(수동 입력)")
    st.caption("user_id(UUID)로 업데이트합니다. (실수 방지용)")

    user_id = st.text_input("user_id", value="", placeholder="UUID")
    ban_reason = st.text_input("사유(선택)", value="", placeholder="예: 악의적 사용")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("차단", use_container_width=True, key="btn_ban"):
            try:
                supabase.table("user_profiles").update({"is_banned": True, "banned_reason": ban_reason}).eq("user_id", user_id).execute()
                st.success("차단 처리 완료")
            except Exception:
                st.error("실패(권한/RLS/ID 확인)")
    with c2:
        if st.button("해제", use_container_width=True, key="btn_unban"):
            try:
                supabase.table("user_profiles").update({"is_banned": False, "banned_reason": ""}).eq("user_id", user_id).execute()
                st.success("차단 해제 완료")
            except Exception:
                st.error("실패(권한/RLS/ID 확인)")
    with c3:
        if st.button("관리자 지정", use_container_width=True, key="btn_make_admin"):
            try:
                supabase.table("user_profiles").update({"role": "admin"}).eq("user_id", user_id).execute()
                st.success("관리자 지정 완료")
            except Exception:
                st.error("실패(권한/RLS/ID 확인)")

# ============================================================
# ✅ 로그인 복원
# ============================================================
if "auth_session" not in st.session_state:
    st.session_state.auth_session = None

if st.session_state.auth_session is None:
    st.session_state.auth_session = refresh_session_if_needed()

user = get_user()
if not user:
    st.markdown("<div class='jp' style='font-size:26px; font-weight:900; margin:2px 0 8px 0;'>✨ 왕초보 탈출 마법의 단어장</div>", unsafe_allow_html=True)
    st.caption("오늘은 10문항만 해도 충분합니다. 로그인하고 이어가요 🙂")
    render_login_box()
    st.stop()

# 프로필 확인/부트스트랩
ensure_role_bootstrap(user)
profile = db_get_profile(user["id"])
if not profile:
    db_upsert_profile(user["id"], user.get("email",""))
    profile = db_get_profile(user["id"]) or {}

render_header_userbar(profile)

# ============================================================
# ✅ 상단 타이틀
# ============================================================
st.markdown("<div class='jp' style='font-size:26px; font-weight:900; margin:2px 0 8px 0;'>✨ 왕초보 탈출 마법의 단어장</div>", unsafe_allow_html=True)
st.caption("‘틀려도 괜찮은 날’로 잡아요. 10문항만 끝내면 루틴 성공입니다 🙂")

# ============================================================
# ✅ 탭 구성 (홈 복구!)
# ============================================================
tabs = st.tabs(["홈", "학습", "마이페이지", "관리자"])

with tabs[3]:
    if (profile.get("role") == "admin") or ((user.get("email","").lower().strip()) in ADMIN_EMAILS):
        render_admin_panel()
    else:
        st.info("관리자 권한이 없습니다.")

# ============================================================
# ✅ 데이터 로드 + 기본 상태
# ============================================================
ensure_pool()
pool: pd.DataFrame = st.session_state.pool

# 왕초보 고정 레벨
st.session_state.level = FIXED_LEVEL

if "pos_pick" not in st.session_state:
    st.session_state.pos_pick = "daily_mix"
if "quiz_type" not in st.session_state:
    st.session_state.quiz_type = "meaning"
if "quiz" not in st.session_state or not isinstance(st.session_state.quiz, list):
    st.session_state.quiz = []
if "answers" not in st.session_state or not isinstance(st.session_state.answers, list):
    st.session_state.answers = []
if "submitted" not in st.session_state:
    st.session_state.submitted = False
if "wrong_list" not in st.session_state:
    st.session_state.wrong_list = []

def maybe_auto_queue_daily_mix_after_submit():
    if not st.session_state.get("submitted"):
        return
    st.info("다음 세트는 ‘오늘의 추천’으로 자연스럽게 이어가도 좋아요 🙂")
    if st.button("▶ 오늘의 추천(daily_mix) 바로 시작", type="primary", use_container_width=True, key="btn_auto_daily_mix"):
        clear_q_keys()
        quiz = build_daily_mix(st.session_state.level, pool)
        start_quiz(quiz)
        st.rerun()

def build_quiz_now() -> list[dict]:
    level = st.session_state.level
    pos_pick = st.session_state.pos_pick
    qtype = st.session_state.quiz_type

    wrong_keys = [w.get("jp_word","") for w in (st.session_state.get("wrong_list", []) or []) if isinstance(w, dict)]
    pool2 = apply_wrong_weight_pool(pool, wrong_keys)

    if pos_pick == "daily_mix":
        return build_daily_mix(level, pool2)

    if pos_pick == "use":
        use_df = pool2[(pool2["level"] == level) & (pool2["pos"].isin(POS_LABELS_USE))]
        if len(use_df) < N:
            soft = pick_level_mix(level)["soft_up"]
            use_df = pd.concat([use_df, pool2[(pool2["level"] == soft) & (pool2["pos"].isin(POS_LABELS_USE))]], ignore_index=True)
        if len(use_df) < N:
            use_df = pool2[pool2["pos"].isin(POS_LABELS_USE)]
        rows = use_df.sample(n=min(N, len(use_df)), replace=False).to_dict("records")
        return [make_use_final_question(pd.Series(r), pool2) for r in rows]

    core_df = pool2[(pool2["level"] == level) & (pool2["pos"] == pos_pick)]
    if len(core_df) < N:
        soft = pick_level_mix(level)["soft_up"]
        core_df = pd.concat([core_df, pool2[(pool2["level"] == soft) & (pool2["pos"] == pos_pick)]], ignore_index=True)
    if len(core_df) < N:
        core_df = pool2[pool2["pos"] == pos_pick]

    rows = core_df.sample(n=min(N, len(core_df)), replace=False).to_dict("records")
    return [make_core_question(pd.Series(r), qtype, pool2) for r in rows]

# ============================================================
# ✅ 홈 탭 (예전 느낌: 바로 문제 안 나오고 '시작' 유도)
# ============================================================
with tabs[0]:
    st.markdown(
        """
<div class="home-card jp">
  <div style="font-size:18px; font-weight:900; margin-bottom:6px;">오늘은 10문항만 해도 충분합니다 🙂</div>
  <div style="opacity:.85; font-size:13px; line-height:1.35;">
    · 왕초보 기본 루틴은 <b>N5 고정</b>이에요.<br>
    · ‘오늘의 추천’은 조사/표현/부사/코어를 섞어서 딱 10문항으로 맞춰드려요.<br>
    · 틀려도 괜찮습니다. 오답은 “학습이 일어난 증거”예요.
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("▶ 오늘의 추천 시작", type="primary", use_container_width=True, key="btn_home_start_daily"):
            st.session_state.pos_pick = "daily_mix"
            clear_q_keys()
            start_quiz(build_quiz_now())
            st.rerun()
    with c2:
        if st.button("▶ 조사·표현(사용)만", use_container_width=True, key="btn_home_start_use"):
            st.session_state.pos_pick = "use"
            clear_q_keys()
            start_quiz(build_quiz_now())
            st.rerun()

    st.caption("원하시면 학습 탭에서 품사/유형을 바꿔서 진행할 수도 있어요.")

# ============================================================
# ✅ 학습 탭
# ============================================================
with tabs[1]:
    st.markdown("<div class='qtypewrap'>", unsafe_allow_html=True)

    # ✅ 레벨 선택 제거(고정 N5)
    st.markdown("<div class='qtype_hint jp'>✨ 레벨: <b>N5(고정)</b></div>", unsafe_allow_html=True)

    # 품사 버튼
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

    # 유형 버튼(코어용)
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

    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔄 새 문제(랜덤 10문항)", use_container_width=True, key="btn_new"):
            clear_q_keys()
            start_quiz(build_quiz_now())
            st.rerun()
    with c2:
        if st.button("🧹 오답 초기화", use_container_width=True, key="btn_clear_wrongs"):
            st.session_state.wrong_list = []
            st.success("오답을 비웠습니다.")
            st.rerun()

    # ✅ 예전처럼: 접속 즉시 문제 생성 X
    if not st.session_state.quiz:
        st.info("홈에서 시작하거나, 위의 ‘새 문제’ 버튼을 눌러 시작하세요 🙂")
        st.stop()

    quiz = st.session_state.quiz
    answers = st.session_state.answers

    for idx, q in enumerate(quiz):
        st.subheader(f"Q{idx+1}")
        qv = st.session_state.quiz_version
        widget_key = f"q_{qv}_{idx}"

        if q.get("mode") == "use_final":
            prompt = q.get("prompt_tpl", "____")
            st.markdown(
                f"<div class='jp' style='margin-top:-6px; margin-bottom:6px; font-size:18px; font-weight:500; line-height:1.35;'>{prompt}</div>",
                unsafe_allow_html=True,
            )
            if q.get("meaning_kr"):
                st.caption(f"뜻 힌트: {q['meaning_kr']}")
        else:
            st.markdown(
                f"<div class='jp' style='margin-top:-6px; margin-bottom:6px; font-size:18px; font-weight:500; line-height:1.35;'>{q.get('prompt','')}</div>",
                unsafe_allow_html=True,
            )

        prev = answers[idx] if idx < len(answers) else None
        default_index = q["choices"].index(prev) if (prev is not None and prev in q["choices"]) else None
        picked = st.radio("보기", q["choices"], index=default_index, key=widget_key, label_visibility="collapsed")

        if idx >= len(answers):
            answers.append(picked)
        else:
            answers[idx] = picked

    sync_answers()

    quiz_len = len(quiz)
    all_answered = (quiz_len > 0) and all(a is not None for a in answers[:quiz_len])

    if st.button("✅ 제출하고 채점하기", disabled=not all_answered, type="primary", use_container_width=True, key="btn_submit"):
        st.session_state.submitted = True

    if not all_answered:
        st.info("모든 문제에 답을 선택하면 제출 버튼이 활성화됩니다.")

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

        db_save_study_session(user["id"], score=score, total=quiz_len)
        db_save_wrong_notes(user["id"], wrong_list)

        st.session_state.wrong_list = wrong_list

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

                st.markdown(
                    f"""
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
""",
                    unsafe_allow_html=True,
                )

            st.download_button(
                "⬇️ 오답노트 JSON 내려받기",
                data=json.dumps(wrong_list, ensure_ascii=False, indent=2).encode("utf-8"),
                file_name="wrong_note.json",
                mime="application/json",
                use_container_width=True,
                key="btn_dl_wrong_json",
            )

            if st.button("❌ 오답만 다시 풀기", type="primary", use_container_width=True, key="btn_retry_wrongs"):
                clear_q_keys()
                keys = [x["word"]["jp_word"] for x in wrong_list]
                retry_df = pool[pool["jp_word"].isin(keys)].sample(frac=1).reset_index(drop=True)

                retry_quiz = []
                for _, r in retry_df.iterrows():
                    if r["pos"] in POS_LABELS_USE:
                        retry_quiz.append(make_use_final_question(r, pool))
                    else:
                        retry_quiz.append(make_core_question(r, st.session_state.quiz_type, pool))

                start_quiz(retry_quiz[:max(5, len(retry_quiz))])
                st.rerun()

        maybe_auto_queue_daily_mix_after_submit()

# ============================================================
# ✅ 마이페이지
# ============================================================
with tabs[2]:
    st.subheader("📌 내 학습 기록")

    try:
        sres = supabase.table("study_sessions").select("*").eq("user_id", user["id"]).order("created_at", desc=True).limit(20).execute()
        rows = sres.data or []
        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df[["created_at","level","pos_pick","quiz_type","total","score"]])
        else:
            st.info("아직 저장된 기록이 없습니다.")
    except Exception:
        st.warning("기록을 불러오지 못했습니다(권한/RLS 확인).")

    st.subheader("❌ 최근 오답")
    try:
        wres = supabase.table("wrong_notes").select("*").eq("user_id", user["id"]).order("created_at", desc=True).limit(30).execute()
        wrows = wres.data or []
        if wrows:
            wdf = pd.DataFrame(wrows)
            st.dataframe(wdf[["created_at","level","pos","jp_word","reading","meaning_kr","picked","correct"]])
        else:
            st.info("최근 오답이 없습니다.")
    except Exception:
        st.warning("오답을 불러오지 못했습니다(권한/RLS 확인).")
