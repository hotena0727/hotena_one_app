# ============================================================
# ✅ 왕초보 탈출 하테나일본어 (단어 앱) - 전체 복붙용 단일 파일
# - 품사 선택 + 유형 선택(발음/뜻/한→일)
# - 로그인/회원가입(Supabase Auth) + 쿠키 세션 복원
# - 홈/퀴즈/마이페이지/관리자 라우팅
# - 오답노트 + 오답만 다시풀기
# - 맞힌 단어 제외(정복) + 초기화
# - 사운드 토글 + 테스트 재생 + 제출 후 1회 SFX
#
# ✅ CSV (data/words_beginner.csv) 필수 컬럼(최종):
#   level, pos, jp_word, reading, meaning, example_jp, example_kr
#   - 문제는 jp_word(한자 포함 단어)에서 뽑음
#
# ✅ 이번 수정 반영:
#   1) 발음(読み) 문제에서 "보기 모양"으로 찍기 방지:
#      - verb: 가능한 한 '끝 2글자(히라가나 기준)' 동일 → 부족하면 '끝 1글자' 동일
#      - verb: する 동사는 보기 4개 모두 '～する'로 통일
#      - adj_i: 보기 전부 끝이 'い'로 통일(동일 pos 풀에서)
#      - adj_na: pos가 동일하므로 기본적으로 모양 찍기 난이도 상승(동사처럼 suffix 적용은 X)
#   2) 제출 후 SFX: perfect / (0.7 이상) correct / (그 외) wrong
#   3) ✅ 요청 반영: 부사/조사/접속사/감탄사(adv, particle, conj, interj) 에서는
#      - 유형을 "뜻, 한→일" 2개만 노출 (발음 숨김)
# ============================================================

from __future__ import annotations

from pathlib import Path
import random
import pandas as pd
import streamlit as st
import unicodedata
from supabase import create_client
from streamlit_cookies_manager import EncryptedCookieManager
import streamlit.components.v1 as components
from collections import Counter
import time
import traceback
import base64

# ============================================================
# ✅ Page Config + Paths
# ============================================================
st.set_page_config(page_title="왕초보 탈출 하테나일본어", layout="centered")

BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "data" / "words_beginner.csv"   # ✅ 왕초보 단어 CSV
APP_URL = "https://YOUR_STREAMLIT_APP_URL_HERE/"      # ✅ 이메일 인증 redirect용 (스트림릿 앱 주소로 교체)

# ============================================================
# ✅ App Settings
# ============================================================
SHOW_POST_SUBMIT_UI = "N"  # 제출 후 '내 최근 기록' 등을 퀴즈 페이지에 바로 보여줄지
SHOW_NAVER_TALK = "Y"
NAVER_TALK_URL = "https://talk.naver.com/W45141"

KST_TZ = "Asia/Seoul"
N = 10  # 한 번에 10문항

# ============================================================
# ✅ POS / QUIZ TYPES
# ============================================================
POS_OPTIONS = ["noun", "verb", "adj_i", "adj_na", "adv", "particle", "conj", "interj"]
POS_LABEL_MAP = {
    "noun": "명사",
    "verb": "동사",
    "adj_i": "い형용사",
    "adj_na": "な형용사",
    "adv": "부사",
    "particle": "조사",
    "conj": "접속사",
    "interj": "감탄사",
}

quiz_label_map = {
    "reading": "발음",
    "meaning": "뜻",
    "kr2jp": "한→일",
}
QUIZ_TYPES_USER = ["reading", "meaning", "kr2jp"]
QUIZ_TYPES_ADMIN = ["reading", "meaning", "kr2jp"]  # 필요시 관리자 전용 유형 추가 가능

# ✅ 요청 반영: 이 품사들은 발음(reading) 숨김
POS_ONLY_2TYPES = {"adv", "particle", "conj", "interj"}

# ============================================================
# ✅ Session Defaults
# ============================================================
if "quiz_type" not in st.session_state:
    st.session_state.quiz_type = "meaning"  # 왕초보는 뜻부터 추천
if "pos" not in st.session_state:
    st.session_state.pos = "noun"

if st.session_state.quiz_type not in QUIZ_TYPES_USER:
    st.session_state.quiz_type = "meaning"
if st.session_state.pos not in POS_OPTIONS:
    st.session_state.pos = "noun"

# ✅ (안전) 제한 품사인데 reading이 잡혀 있으면 meaning으로 강제
if str(st.session_state.get("pos", "noun")).lower().strip() in POS_ONLY_2TYPES and st.session_state.quiz_type == "reading":
    st.session_state.quiz_type = "meaning"

# ============================================================
# ✅ CSS (폰트/버튼/카드/간격)
# ============================================================
st.markdown(
    """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Kosugi+Maru&family=Noto+Sans+JP:wght@400;500;700;800&display=swap" rel="stylesheet">

<style>
:root{
  --jp-rounded: "Noto Sans JP","Kosugi Maru","Hiragino Sans","Yu Gothic","Meiryo",sans-serif;
}
.jp, .jp *{
  font-family: var(--jp-rounded) !important;
  line-height:1.7;
  letter-spacing:.2px;
}

/* 헤더 여백 */
div[data-testid="stMarkdownContainer"] h2,
div[data-testid="stMarkdownContainer"] h3,
div[data-testid="stMarkdownContainer"] h4{
  margin-top: 10px !important;
  margin-bottom: 8px !important;
}

/* 버튼 기본 */
div.stButton > button{
  padding: 6px 10px !important;
  font-size: 13px !important;
  line-height: 1.1 !important;
  white-space: nowrap !important;
}

/* 상단 환영바 */
.headbar{
  display:flex;
  align-items:flex-end;
  justify-content:space-between;
  gap:12px;
  margin: 10px 0 16px 0;
}
.headtitle{
  font-size:32px;
  font-weight:900;
  line-height:1.15;
  white-space: nowrap;
}
.headhello{
  font-size: 13px;
  font-weight:700;
  opacity:.88;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 52%;
}
.headhello .mail{
  font-weight:600;
  opacity:.75;
  margin-left:8px;
}

@media (max-width: 480px){
  div[data-baseweb="button-group"] button{
    padding: 9px 12px !important;
    font-size: 14px !important;
  }
  .headhello .mail{ display:none !important; }
  .headhello{ font-size:11px; }
  .headtitle{ font-size:22px; }
}

/* ====== 상단 선택 버튼 카드 스타일 ====== */
.qtypewrap div.stButton > button{
  height: 46px !important;
  border-radius: 14px !important;
  font-weight: 900 !important;
  font-size: 14px !important;
  border: 1px solid rgba(120,120,120,0.22) !important;
  background: rgba(255,255,255,0.04) !important;
  box-shadow: none !important;
  transition: transform .08s ease, box-shadow .08s ease, filter .08s ease;
}
.qtypewrap div.stButton > button:hover{
  transform: translateY(-1px);
  box-shadow: 0 12px 26px rgba(0,0,0,0.12) !important;
  filter: brightness(1.02);
}

/* 캡션 */
.qtype_hint{
  font-size: 15px;
  opacity: .70;
  margin-top: 2px;
  margin-bottom: 10px;
  line-height: 1.2;
}

/* divider 간격(래퍼로만) */
.tight-divider hr{
  margin: 6px 0 10px 0 !important;
}

/* Q번호 아래 간격 축소 */
div[data-testid="stMarkdownContainer"] h3{
  margin-bottom: 4px !important;
}
</style>
""",
    unsafe_allow_html=True,
)

# ============================================================
# ✅ Scroll Top Anchor + Helpers
# ============================================================
st.markdown('<div id="__TOP__"></div>', unsafe_allow_html=True)

def scroll_to_top(nonce: int = 0):
    components.html(
        f"""
        <script>
        (function () {{
          const doc = window.parent.document;
          const targets = [
            doc.querySelector('[data-testid="stAppViewContainer"]'),
            doc.querySelector('[data-testid="stMain"]'),
            doc.querySelector('section.main'),
            doc.documentElement,
            doc.body
          ].filter(Boolean);

          const go = () => {{
            try {{
              const top = doc.getElementById("__TOP__");
              if (top) top.scrollIntoView({{behavior: "auto", block: "start"}});
              targets.forEach(t => {{
                if (t && typeof t.scrollTo === "function") t.scrollTo({{top: 0, left: 0, behavior: "auto"}});
                if (t) t.scrollTop = 0;
              }});
              window.parent.scrollTo(0, 0);
              window.scrollTo(0, 0);
            }} catch(e) {{}}
          }};

          go();
          requestAnimationFrame(go);
          setTimeout(go, 50);
          setTimeout(go, 150);
          setTimeout(go, 350);
          setTimeout(go, 800);
        }})();
        </script>
        <!-- nonce:{nonce} -->
        """,
        height=1,
    )

def render_floating_scroll_top():
    components.html(
        """
<script>
(function(){
  const doc = window.parent.document;
  if (doc.getElementById("__FAB_TOP__")) return;

  const btn = doc.createElement("button");
  btn.id = "__FAB_TOP__";
  btn.textContent = "↑";

  btn.style.position = "fixed";
  btn.style.right = "14px";
  btn.style.zIndex = "2147483647";
  btn.style.width = "46px";
  btn.style.height = "46px";
  btn.style.borderRadius = "999px";
  btn.style.border = "1px solid rgba(120,120,120,0.25)";
  btn.style.background = "rgba(0,0,0,0.55)";
  btn.style.color = "#fff";
  btn.style.fontSize = "18px";
  btn.style.fontWeight = "900";
  btn.style.boxShadow = "0 10px 22px rgba(0,0,0,0.25)";
  btn.style.cursor = "pointer";
  btn.style.userSelect = "none";
  btn.style.display = "flex";
  btn.style.alignItems = "center";
  btn.style.justifyContent = "center";
  btn.style.opacity = "0";

  const applyDeviceVisibility = () => {
    try {
      const w = window.parent.innerWidth || window.innerWidth;
      if (w >= 801) btn.style.display = "none";
      else btn.style.display = "flex";
    } catch(e) {}
  };

  const goTop = () => {
    try {
      const top = doc.getElementById("__TOP__");
      if (top) top.scrollIntoView({behavior:"smooth", block:"start"});

      const targets = [
        doc.querySelector('[data-testid="stAppViewContainer"]'),
        doc.querySelector('[data-testid="stMain"]'),
        doc.querySelector('section.main'),
        doc.documentElement,
        doc.body
      ].filter(Boolean);

      targets.forEach(t => {
        if (t && typeof t.scrollTo === "function") t.scrollTo({top:0, left:0, behavior:"smooth"});
        if (t) t.scrollTop = 0;
      });

      window.parent.scrollTo(0,0);
      window.scrollTo(0,0);
    } catch(e) {}
  };

  btn.addEventListener("click", goTop);

  const mount = () => doc.querySelector('[data-testid="stAppViewContainer"]') || doc.body;

  const BASE = 18;
  const EXTRA = 34;

  const reposition = () => {
    try {
      const vv = window.parent.visualViewport || window.visualViewport;
      const innerH = window.parent.innerHeight || window.innerHeight;
      const hiddenBottom = vv ? Math.max(0, innerH - vv.height - (vv.offsetTop || 0)) : 0;
      btn.style.bottom = (BASE + EXTRA + hiddenBottom) + "px";
      btn.style.opacity = "1";
    } catch(e) {
      btn.style.bottom = "220px";
      btn.style.opacity = "1";
    }
    applyDeviceVisibility();
  };

  const tryAttach = (n=0) => {
    const root = mount();
    if (!root) {
      if (n < 30) return setTimeout(() => tryAttach(n+1), 50);
      return;
    }
    root.appendChild(btn);
    reposition();
    setTimeout(reposition, 50);
    setTimeout(reposition, 200);
    setTimeout(reposition, 600);
  };

  tryAttach();
  window.parent.addEventListener("resize", reposition, {passive:true});

  const vv = window.parent.visualViewport || window.visualViewport;
  if (vv) {
    vv.addEventListener("resize", reposition, {passive:true});
    vv.addEventListener("scroll", reposition, {passive:true});
  }
})();
</script>
        """,
        height=1,
    )

render_floating_scroll_top()

if st.session_state.get("_scroll_top_once"):
    st.session_state["_scroll_top_once"] = False
    st.session_state["_scroll_top_nonce"] = st.session_state.get("_scroll_top_nonce", 0) + 1
    scroll_to_top(nonce=st.session_state["_scroll_top_nonce"])

# ============================================================
# ✅ Cookies + Supabase
# ============================================================
cookies = EncryptedCookieManager(
    prefix="hatena_beginner_",
    password=st.secrets["COOKIE_PASSWORD"],
)
if not cookies.ready():
    st.info("잠깐만요! 곧 시작할게요🙂")
    st.stop()

if "SUPABASE_URL" not in st.secrets or "SUPABASE_ANON_KEY" not in st.secrets:
    st.error("Supabase Secrets가 설정되지 않았습니다. (SUPABASE_URL / SUPABASE_ANON_KEY)")
    st.stop()

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]
sb = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# ============================================================
# ✅ Utils: 위젯 잔상(q_...) 제거
# ============================================================
def clear_question_widget_keys():
    keys_to_del = [k for k in list(st.session_state.keys()) if isinstance(k, str) and k.startswith("q_")]
    for k in keys_to_del:
        st.session_state.pop(k, None)

# ============================================================
# ✅ Key helpers (정복/제외/배너)
# ============================================================
def mastery_key(qtype: str | None = None, pos: str | None = None) -> str:
    qt = qtype or st.session_state.get("quiz_type", "meaning")
    ps = (pos or st.session_state.get("pos", "noun")).lower().strip()
    return f"{ps}__{qt}"

def is_admin() -> bool:
    cached = st.session_state.get("is_admin_cached")
    if cached is not None:
        return bool(cached)

    u = st.session_state.get("user")
    if u is None:
        st.session_state["is_admin_cached"] = False
        return False

    sb_authed_local = get_authed_sb()
    if sb_authed_local is None:
        st.session_state["is_admin_cached"] = False
        return False

    val = fetch_is_admin_from_db(sb_authed_local, u.id)
    st.session_state["is_admin_cached"] = val
    return bool(val)

def ensure_mastered_words_shape():
    if "mastered_words" not in st.session_state or not isinstance(st.session_state.mastered_words, dict):
        st.session_state.mastered_words = {}
    types = QUIZ_TYPES_ADMIN if is_admin() else QUIZ_TYPES_USER
    for qt in types:
        st.session_state.mastered_words.setdefault(mastery_key(qt), set())

def ensure_excluded_wrong_words_shape():
    if "excluded_wrong_words" not in st.session_state or not isinstance(st.session_state.excluded_wrong_words, dict):
        st.session_state.excluded_wrong_words = {}
    types = QUIZ_TYPES_ADMIN if is_admin() else QUIZ_TYPES_USER
    for qt in types:
        st.session_state.excluded_wrong_words.setdefault(mastery_key(qt), set())

def ensure_mastery_banner_shape():
    if "mastery_banner_shown" not in st.session_state or not isinstance(st.session_state.mastery_banner_shown, dict):
        st.session_state.mastery_banner_shown = {}
    if "mastery_done" not in st.session_state or not isinstance(st.session_state.mastery_done, dict):
        st.session_state.mastery_done = {}

    types = QUIZ_TYPES_ADMIN if is_admin() else QUIZ_TYPES_USER
    for qt in types:
        k = mastery_key(qt)
        st.session_state.mastery_banner_shown.setdefault(k, False)
        st.session_state.mastery_done.setdefault(k, False)

# ============================================================
# ✅ Answers 동기화 + Progress save helper
# ============================================================
def sync_answers_from_widgets():
    qv = st.session_state.get("quiz_version", 0)
    quiz = st.session_state.get("quiz", [])
    if not isinstance(quiz, list):
        return

    answers = st.session_state.get("answers")
    if not isinstance(answers, list) or len(answers) != len(quiz):
        st.session_state.answers = [None] * len(quiz)

    for idx in range(len(quiz)):
        widget_key = f"q_{qv}_{idx}"
        if widget_key in st.session_state:
            st.session_state.answers[idx] = st.session_state[widget_key]

def start_quiz_state(quiz_list: list, qtype: str, clear_wrongs: bool = True):
    st.session_state.quiz_version = int(st.session_state.get("quiz_version", 0)) + 1
    st.session_state.quiz_type = qtype

    if not isinstance(quiz_list, list):
        quiz_list = []

    st.session_state.quiz = quiz_list
    st.session_state.answers = [None] * len(quiz_list)

    st.session_state.submitted = False
    st.session_state.saved_this_attempt = False
    st.session_state.stats_saved_this_attempt = False
    st.session_state.session_stats_applied_this_attempt = False

    if clear_wrongs:
        st.session_state.wrong_list = []

def mark_progress_dirty():
    st.session_state.progress_dirty = True
    st.session_state._progress_dirty_ts = time.time()

    sb_authed_local = get_authed_sb()
    u = st.session_state.get("user")
    if (sb_authed_local is None) or (u is None):
        return

    now = time.time()
    last = st.session_state.get("_last_progress_save_ts", 0.0)
    if now - last < 10.0:
        return

    try:
        save_progress_to_db(sb_authed_local, u.id)
        st.session_state._last_progress_save_ts = now
        st.session_state.progress_dirty = False
    except Exception:
        pass

# ============================================================
# ✅ Auth helpers (JWT refresh, sb authed)
# ============================================================
def is_jwt_expired_error(e: Exception) -> bool:
    msg = str(e).lower()
    return ("jwt expired" in msg) or ("pgrst303" in msg)

def clear_auth_everywhere():
    try:
        cookies["access_token"] = ""
        cookies["refresh_token"] = ""
        cookies.save()
    except Exception:
        pass

    for k in [
        "user", "access_token", "refresh_token",
        "login_email", "email_link_notice_shown",
        "auth_mode", "signup_done", "last_signup_ts",
        "page",
        "quiz", "answers", "submitted", "wrong_list",
        "quiz_version", "quiz_type",
        "saved_this_attempt", "stats_saved_this_attempt",
        "history", "wrong_counter", "total_counter",
        "attendance_checked", "streak_count", "did_attend_today",
        "is_admin_cached",
        "session_stats_applied_this_attempt",
        "mastered_words",
        "progress_restored", "pool_ready",
        "_sb_authed", "_sb_authed_token",
        "excluded_wrong_words",
        "mastery_banner_shown", "mastery_done",
        "pos",
    ]:
        st.session_state.pop(k, None)

def run_db(callable_fn):
    try:
        return callable_fn()
    except Exception as e:
        if is_jwt_expired_error(e):
            ok = refresh_session_from_cookie_if_needed(force=True)
            if ok:
                st.rerun()
            clear_auth_everywhere()
            st.warning("세션이 만료되었습니다. 다시 로그인해 주세요.")
            st.rerun()
        raise

def refresh_session_from_cookie_if_needed(force: bool = False) -> bool:
    if not force and st.session_state.get("user") and st.session_state.get("access_token"):
        return True

    rt = cookies.get("refresh_token")
    at = cookies.get("access_token")

    if rt:
        try:
            refreshed = sb.auth.refresh_session(rt)
            if refreshed and refreshed.session and refreshed.session.access_token:
                st.session_state.user = refreshed.user
                st.session_state.access_token = refreshed.session.access_token
                st.session_state.refresh_token = refreshed.session.refresh_token

                u_email = getattr(refreshed.user, "email", None)
                if u_email:
                    st.session_state["login_email"] = u_email.strip()

                cookies["access_token"] = refreshed.session.access_token
                cookies["refresh_token"] = refreshed.session.refresh_token
                cookies.save()
                return True
        except Exception:
            pass

    if at:
        try:
            u = sb.auth.get_user(at)
            user_obj = getattr(u, "user", None) or getattr(u, "data", None) or None
            if user_obj:
                st.session_state.user = user_obj
                st.session_state.access_token = at
                if rt:
                    st.session_state.refresh_token = rt
                u_email = getattr(user_obj, "email", None)
                if u_email:
                    st.session_state["login_email"] = u_email.strip()
                return True
        except Exception:
            pass

    return False

def get_authed_sb():
    if not st.session_state.get("access_token"):
        refresh_session_from_cookie_if_needed(force=True)

    token = st.session_state.get("access_token")
    if not token:
        return None

    cached = st.session_state.get("_sb_authed")
    cached_token = st.session_state.get("_sb_authed_token")

    if cached is not None and cached_token == token:
        return cached

    sb2 = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    sb2.postgrest.auth(token)

    st.session_state["_sb_authed"] = sb2
    st.session_state["_sb_authed_token"] = token
    return sb2

def to_kst_naive(x):
    ts = pd.to_datetime(x, utc=True, errors="coerce")
    if isinstance(ts, pd.Series):
        return ts.dt.tz_convert(KST_TZ).dt.tz_localize(None)
    if pd.isna(ts):
        return ts
    return ts.tz_convert(KST_TZ).tz_localize(None)

# ============================================================
# ✅ DB functions (기존 테이블 구조 그대로 활용)
# ============================================================
def delete_all_learning_records(sb_authed, user_id):
    sb_authed.table("quiz_attempts").delete().eq("user_id", user_id).execute()
    clear_progress_in_db(sb_authed, user_id)

def ensure_profile(sb_authed, user):
    try:
        sb_authed.table("profiles").upsert(
            {"id": user.id, "email": getattr(user, "email", None)},
            on_conflict="id",
        ).execute()
    except Exception:
        pass

def mark_attendance_once(sb_authed):
    if st.session_state.get("attendance_checked"):
        return None
    try:
        res = sb_authed.rpc("mark_attendance_kst", {}).execute()
        st.session_state.attendance_checked = True
        return res.data[0] if res.data else None
    except Exception:
        st.session_state.attendance_checked = True
        return None

def save_attempt_to_db(sb_authed, user_id, user_email, pos, quiz_type, quiz_len, score, wrong_list):
    payload = {
        "user_id": user_id,
        "user_email": user_email,
        "level": str(pos),          # ✅ level 컬럼에 pos 저장
        "pos_mode": str(quiz_type), # ✅ pos_mode 컬럼에 유형 저장
        "quiz_len": int(quiz_len),
        "score": int(score),
        "wrong_count": int(len(wrong_list)),
        "wrong_list": wrong_list,
    }
    sb_authed.table("quiz_attempts").insert(payload).execute()

def fetch_recent_attempts(sb_authed, user_id, limit=10):
    return (
        sb_authed.table("quiz_attempts")
        .select("created_at, level, pos_mode, quiz_len, score, wrong_count, wrong_list")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )

def fetch_all_attempts_admin(sb_authed, limit=500):
    return (
        sb_authed.table("quiz_attempts")
        .select("created_at, user_email, level, pos_mode, quiz_len, score, wrong_count")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )

def fetch_is_admin_from_db(sb_authed, user_id):
    try:
        res = sb_authed.table("profiles").select("is_admin").eq("id", user_id).single().execute()
        if res and res.data and "is_admin" in res.data:
            return bool(res.data["is_admin"])
    except Exception:
        pass
    return False

def build_word_results_bulk_payload(quiz: list[dict], answers: list, quiz_type: str, pos: str) -> list[dict]:
    items = []
    for idx, q in enumerate(quiz):
        word_key = (str(q.get("jp_word", "")).strip() or str(q.get("reading", "")).strip())
        if not word_key:
            continue
        picked = answers[idx] if idx < len(answers) else None
        is_correct = (picked == q.get("correct_text"))

        items.append(
            {
                "word_key": word_key,
                "level": "BEGINNER",
                "pos": str(pos),
                "quiz_type": str(quiz_type),
                "is_correct": bool(is_correct),
            }
        )
    return items

# ============================================================
# ✅ Progress (DB 저장/복원)
# ============================================================
def save_progress_to_db(sb_authed, user_id: str):
    if "quiz" not in st.session_state or "answers" not in st.session_state:
        return

    payload = {
        "pos": st.session_state.get("pos"),
        "quiz_type": st.session_state.get("quiz_type"),
        "quiz_version": int(st.session_state.get("quiz_version", 0) or 0),
        "quiz": st.session_state.get("quiz"),
        "answers": st.session_state.get("answers"),
        "submitted": bool(st.session_state.get("submitted", False)),
    }

    sb_authed.table("profiles").upsert(
        {"id": user_id, "progress": payload},
        on_conflict="id",
    ).execute()

def clear_progress_in_db(sb_authed, user_id: str):
    sb_authed.table("profiles").upsert(
        {"id": user_id, "progress": None},
        on_conflict="id",
    ).execute()

def restore_progress_from_db(sb_authed, user_id: str):
    try:
        res = (
            sb_authed.table("profiles")
            .select("progress")
            .eq("id", user_id)
            .single()
            .execute()
        )
    except Exception:
        return

    if not res or not res.data:
        return

    progress = res.data.get("progress")
    if not progress:
        return

    st.session_state.pos = progress.get("pos", st.session_state.get("pos", "noun"))
    st.session_state.quiz_type = progress.get("quiz_type", st.session_state.get("quiz_type", "meaning"))
    st.session_state.quiz_version = int(progress.get("quiz_version", st.session_state.get("quiz_version", 0) or 0))
    st.session_state.quiz = progress.get("quiz", st.session_state.get("quiz"))
    st.session_state.answers = progress.get("answers", st.session_state.get("answers"))
    st.session_state.submitted = bool(progress.get("submitted", st.session_state.get("submitted", False)))

    if st.session_state.pos not in POS_OPTIONS:
        st.session_state.pos = "noun"
    if st.session_state.quiz_type not in QUIZ_TYPES_USER:
        st.session_state.quiz_type = "meaning"

    # ✅ 제한 품사면 reading 복원되더라도 meaning으로 강제
    if str(st.session_state.get("pos", "noun")).lower().strip() in POS_ONLY_2TYPES and st.session_state.quiz_type == "reading":
        st.session_state.quiz_type = "meaning"

    if isinstance(st.session_state.quiz, list):
        qlen = len(st.session_state.quiz)
        if not isinstance(st.session_state.answers, list) or len(st.session_state.answers) != qlen:
            st.session_state.answers = [None] * qlen

# ============================================================
# ✅ Admin
# ============================================================
def get_available_quiz_types() -> list[str]:
    return QUIZ_TYPES_ADMIN if is_admin() else QUIZ_TYPES_USER

# ✅ (신규) pos에 따라 가능한 유형 필터
def get_available_quiz_types_for_pos(pos: str) -> list[str]:
    pos = str(pos).strip().lower()
    base = get_available_quiz_types()
    if pos in POS_ONLY_2TYPES:
        return [t for t in base if t in ("meaning", "kr2jp")]
    return base

# ============================================================
# ✅ SOUND
# ============================================================
def _audio_autoplay_data_uri(mime: str, b: bytes):
    b64 = base64.b64encode(b).decode("utf-8")
    st.markdown(
        f"""
        <audio autoplay>
          <source src="data:{mime};base64,{b64}">
        </audio>
        """,
        unsafe_allow_html=True
    )

def play_sound_file(path: str):
    try:
        p = (BASE_DIR / path).resolve() if not str(path).startswith("/") else Path(path)
        if not p.exists():
            if is_admin():
                st.warning(f"[SOUND] 파일 없음: {p}")
            return
        data = p.read_bytes()
        mime = "audio/mpeg" if str(p).lower().endswith(".mp3") else "audio/wav"
        _audio_autoplay_data_uri(mime, data)
    except Exception as e:
        if is_admin():
            st.error("[SOUND] 재생 실패")
            st.exception(e)

def render_sound_toggle():
    if "sound_enabled" not in st.session_state:
        st.session_state.sound_enabled = False

    c1, c2, c3 = st.columns([1.4, 4.6, 4.0], vertical_alignment="center")
    with c1:
        st.session_state.sound_enabled = st.toggle("🔊", value=st.session_state.sound_enabled, label_visibility="collapsed")
    with c2:
        st.caption("소리 " + ("ON ✅" if st.session_state.sound_enabled else "OFF"))
    with c3:
        if st.session_state.sound_enabled:
            if st.button("🔈 테스트", use_container_width=True, key="btn_sound_test"):
                play_sound_file("assets/correct.mp3")

def sfx(event: str):
    if not st.session_state.get("sound_enabled", False):
        return
    mp = {
        "correct": "assets/correct.mp3",
        "wrong":   "assets/wrong.mp3",
        "perfect": "assets/perfect.mp3",
    }
    path = mp.get(event)
    if path:
        play_sound_file(path)

# ============================================================
# ✅ Login UI
# ============================================================
def auth_box():
    st.markdown("<div style='max-width:520px; margin:0 auto;'>", unsafe_allow_html=True)

    st.markdown(
        '<div class="jp" style="font-weight:900; font-size:16px; margin:6px 0 6px 0;">로그인</div>',
        unsafe_allow_html=True
    )

    qp = st.query_params
    came_from_email_link = any(k in qp for k in ["code", "token", "type", "access_token", "refresh_token"])
    if came_from_email_link and not st.session_state.get("email_link_notice_shown"):
        st.session_state.email_link_notice_shown = True
        st.session_state.auth_mode = "login"
        st.success("이메일 인증(또는 링크 확인)이 완료되었습니다. 이제 로그인해 주세요.")

    if "auth_mode" not in st.session_state:
        st.session_state.auth_mode = "login"

    mode = st.radio(
        label="",
        options=["login", "signup"],
        format_func=lambda x: "로그인" if x == "login" else "회원가입",
        horizontal=True,
        key="auth_mode_radio",
        index=0 if st.session_state.auth_mode == "login" else 1,
    )
    st.session_state.auth_mode = mode

    if st.session_state.get("signup_done"):
        st.success("회원가입 요청 완료! 이메일 인증이 필요할 수 있어요. 메일함을 확인한 뒤 로그인해 주세요.")
        st.session_state.signup_done = False

    if mode == "login":
        email = st.text_input("이메일", key="login_email_input")
        pw = st.text_input("비밀번호", type="password", key="login_pw_input")

        st.caption("비밀번호는 **회원가입 때 8자리 이상**으로 설정했을 가능성이 큽니다.")
        if pw and len(pw) < 8:
            st.warning(f"입력하신 비밀번호가 {len(pw)}자리입니다. 회원가입 때 8자리 이상으로 설정하셨다면 더 길게 입력해 주세요.")

        if st.button("로그인", use_container_width=True, key="btn_login"):
            if not email or not pw:
                st.warning("이메일과 비밀번호를 입력해주세요.")
                st.stop()

            try:
                res = sb.auth.sign_in_with_password({"email": email, "password": pw})
                st.session_state.user = res.user
                st.session_state["login_email"] = email.strip()

                if res.session and res.session.access_token:
                    st.session_state.access_token = res.session.access_token
                    st.session_state.refresh_token = res.session.refresh_token
                    cookies["access_token"] = res.session.access_token
                    cookies["refresh_token"] = res.session.refresh_token
                    cookies.save()
                else:
                    st.warning("로그인은 되었지만 세션 토큰이 없습니다. 이메일 인증 상태를 확인해주세요.")
                    st.session_state.access_token = None
                    st.session_state.refresh_token = None

                st.session_state.pop("is_admin_cached", None)
                st.success("로그인 완료!")
                st.rerun()

            except Exception:
                st.error("로그인 실패: 이메일/비밀번호 또는 이메일 인증 상태를 확인해주세요.")
                st.stop()

    else:
        email = st.text_input("이메일", key="signup_email")
        pw = st.text_input("비밀번호", type="password", key="signup_pw")

        pw_len = len(pw) if pw else 0
        pw_ok = pw_len >= 8
        email_ok = bool(email and email.strip())

        st.caption("비밀번호는 **8자리 이상**으로 설정해 주세요.")
        if pw and not pw_ok:
            st.warning(f"비밀번호가 너무 짧습니다. (현재 {pw_len}자) 8자리 이상으로 입력해 주세요.")

        if st.button("회원가입", use_container_width=True, disabled=not (email_ok and pw_ok), key="btn_signup"):
            try:
                last = st.session_state.get("last_signup_ts", 0.0)
                now = time.time()
                if now - last < 8:
                    st.warning("요청이 너무 빠릅니다. 잠시 후 다시 시도해주세요.")
                    st.stop()
                st.session_state.last_signup_ts = now

                sb.auth.sign_up(
                    {
                        "email": email,
                        "password": pw,
                        "options": {"email_redirect_to": APP_URL},
                    }
                )

                st.session_state.signup_done = True
                st.session_state.auth_mode = "login"
                st.session_state["login_email"] = email.strip()
                st.rerun()

            except Exception as e:
                msg = str(e).lower()
                if "rate limit" in msg and "email" in msg:
                    st.session_state.auth_mode = "login"
                    st.session_state["login_email"] = email.strip()
                    st.session_state.signup_done = False
                    st.warning("이메일 발송 제한에 걸렸습니다. 잠시 후 다시 시도해주세요.")
                    st.rerun()

                st.error("회원가입 실패(에러 확인):")
                st.exception(e)
                st.stop()

    st.markdown("</div>", unsafe_allow_html=True)

def require_login():
    if st.session_state.get("user") is None:
        st.markdown(
            """
<div class="jp" style="margin: 8px 0 14px 0;">
  <div style="
    border:1px solid rgba(120,120,120,0.18);
    border-radius:18px;
    padding:16px 16px;
    background: rgba(255,255,255,0.03);
  ">
    <div style="font-weight:900; font-size:22px; line-height:1.15;">
      ✨ 왕초보 탈출 단어 퀴즈
    </div>
    <div style="margin-top:6px; opacity:.85; font-size:13px; line-height:1.55;">
      하루 10문항으로 가볍게 루틴을 만들어요.<br/>
      정답은 저장되고, 오답은 다시 풀 수 있어요.
    </div>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )
        auth_box()
        st.stop()

# ============================================================
# ✅ 네이버톡 배너 (제출 후만)
# ============================================================
def render_naver_talk():
    st.divider()
    st.markdown(
        f"""
<style>
@keyframes floaty {{
  0% {{ transform: translateY(0); }}
  50% {{ transform: translateY(-6px); }}
  100% {{ transform: translateY(0); }}
}}
@keyframes ping {{
  0% {{ transform: scale(1); opacity: 0.9; }}
  70% {{ transform: scale(2.2); opacity: 0; }}
  100% {{ transform: scale(2.2); opacity: 0; }}
}}
.floating-naver-talk,
.floating-naver-talk:visited,
.floating-naver-talk:hover,
.floating-naver-talk:active {{
  position: fixed;
  right: 18px;
  bottom: 90px;
  z-index: 99999;
  text-decoration: none !important;
  color: inherit !important;
}}
.floating-wrap {{
  position: relative;
  animation: floaty 2.2s ease-in-out infinite;
}}
.talk-btn {{
  background: #03C75A;
  color: #fff;
  border: 0;
  border-radius: 999px;
  padding: 14px 18px;
  font-size: 15px;
  font-weight: 700;
  box-shadow: 0 12px 28px rgba(0,0,0,0.22);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 10px;
  line-height: 1.1;
  text-decoration: none !important;
}}
.talk-btn:hover {{ filter: brightness(0.95); }}
.talk-text small {{
  display: block;
  font-size: 12px;
  font-weight: 600;
  opacity: 0.95;
  margin-top: 2px;
}}
.badge {{
  position: absolute;
  top: -6px;
  right: -6px;
  width: 12px;
  height: 12px;
  background: #ff3b30;
  border-radius: 999px;
  box-shadow: 0 6px 14px rgba(0,0,0,0.25);
}}
.badge::after {{
  content: "";
  position: absolute;
  left: 50%;
  top: 50%;
  width: 12px;
  height: 12px;
  transform: translate(-50%, -50%);
  border-radius: 999px;
  background: rgba(255,59,48,0.55);
  animation: ping 1.2s ease-out infinite;
}}
@media (max-width: 600px) {{
  .floating-naver-talk {{ bottom: 110px; right: 14px; }}
  .talk-btn {{ padding: 13px 16px; font-size: 14px; }}
  .talk-text small {{ font-size: 11px; }}
}}
</style>

<a class="floating-naver-talk" href="{NAVER_TALK_URL}" target="_blank" rel="noopener noreferrer">
  <div class="floating-wrap">
    <span class="badge"></span>
    <button class="talk-btn" type="button">
      <span>💬</span>
      <span class="talk-text">
        1:1 하테나쌤 상담
        <small>수강신청 문의하기</small>
      </span>
    </button>
  </div>
</a>
""",
        unsafe_allow_html=True,
    )

# ============================================================
# ✅ Top Card (마이페이지/관리자/로그아웃)
# ============================================================
def nav_to(page: str, scroll_top: bool = True):
    st.session_state.page = page
    if scroll_top:
        st.session_state["_scroll_top_once"] = True

def nav_logout():
    clear_auth_everywhere()

def render_topcard():
    u = st.session_state.get("user")
    if not u:
        return

    st.markdown('<div class="topcard">', unsafe_allow_html=True)
    left, r_admin, r_my, r_logout = st.columns([6.0, 1.2, 2.4, 2.4], vertical_alignment="center")

    with left:
        st.markdown("<div style='height:40px;'></div>", unsafe_allow_html=True)

    with r_admin:
        if is_admin():
            st.button("📊", use_container_width=True, help="관리자 대시보드",
                      key="topcard_btn_nav_admin", on_click=nav_to, args=("admin",))
        else:
            st.markdown("<div style='height:40px;'></div>", unsafe_allow_html=True)

    with r_my:
        st.button("📌 마이페이지", use_container_width=True, help="내 학습 기록/오답 TOP10 보기",
                  key="topcard_btn_nav_my", on_click=nav_to, args=("my",))

    with r_logout:
        st.button("🚪 로그아웃", use_container_width=True, help="로그아웃",
                  key="topcard_btn_logout", on_click=nav_logout)

    st.markdown("</div>", unsafe_allow_html=True)

# ============================================================
# ✅ CSV Load Pool  (✅ CSV 최종 스펙 반영)
# ============================================================
READ_KW = dict(
    dtype=str,
    keep_default_na=False,
    na_values=["nan", "NaN", "NULL", "null", "None", "none"],
)

@st.cache_data(show_spinner=False)
def load_pool(csv_path_str: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path_str, **READ_KW)

    # ✅ CSV 최종 필수 컬럼
    required_cols = {"level", "pos", "jp_word", "reading", "meaning", "example_jp", "example_kr"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"CSV 필수 컬럼 누락: {sorted(list(missing))}")

    def _nfkc(s):
        return unicodedata.normalize("NFKC", str(s or "")).strip()

    df["level"] = df["level"].apply(_nfkc).str.upper().str.strip()
    df["pos"] = df["pos"].apply(_nfkc).str.lower().str.strip()
    df["jp_word"] = df["jp_word"].apply(_nfkc).str.strip()
    df["reading"] = df["reading"].apply(_nfkc).str.strip()
    df["meaning"] = df["meaning"].apply(_nfkc).str.strip()
    df["example_jp"] = df["example_jp"].apply(_nfkc).str.strip()
    df["example_kr"] = df["example_kr"].apply(_nfkc).str.strip()

    # 빈 줄 제거
    df = df[
        (df["pos"] != "") &
        (df["jp_word"] != "") &
        (df["reading"] != "") &
        (df["meaning"] != "")
    ].copy()

    return df.reset_index(drop=True)

def ensure_pool_ready():
    if st.session_state.get("pool_ready") and isinstance(st.session_state.get("_pool"), pd.DataFrame):
        return
    try:
        pool = load_pool(str(CSV_PATH))
    except Exception as e:
        st.error(f"단어 데이터 로드 실패: {e}")
        st.stop()

    if len(pool) < N:
        st.error(f"단어가 부족합니다: pool={len(pool)} (N={N})")
        st.stop()

    st.session_state["_pool"] = pool
    st.session_state["pool_ready"] = True

    if is_admin():
        with st.expander("🔎 디버그: 품사별 단어 수", expanded=False):
            st.write(pool["pos"].value_counts(dropna=False))
            st.write("CSV_PATH =", str(CSV_PATH))

# ============================================================
# ✅ Quiz Logic
# ============================================================
def _nfkc_str(x) -> str:
    return unicodedata.normalize("NFKC", str(x or "")).strip()

def _to_hira(s: str) -> str:
    s = _nfkc_str(s)
    out = []
    for ch in s:
        code = ord(ch)
        if 0x30A1 <= code <= 0x30F6:
            out.append(chr(code - 0x60))
        else:
            out.append(ch)
    return "".join(out)

def _uniq(xs):
    out, seen = [], set()
    for x in xs:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out

def _suffix_kana(x: str, n: int) -> str:
    s = _to_hira(_nfkc_str(x))
    return s[-n:] if len(s) >= n else s

def _is_suru_verb(reading: str) -> bool:
    r = _to_hira(_nfkc_str(reading))
    return r.endswith("する")

def _jp_okurigana_suffix(jp_word: str) -> str:
    """
    jp_word 끝에서 '오쿠리가나(히라/가타카나 연속 꼬리)'를 뽑아 히라가나로 반환.
    예) 直す -> す
        立てる -> てる
        掃除する -> する
        おもう(한자 없음) -> おもう (하지만 이 경우는 크게 의미 없으니 뒤에서 보정)
    """
    s = _nfkc_str(jp_word)
    if not s:
        return ""
    i = len(s)
    # 뒤에서부터 kana(히라/가타) 연속 부분을 수집
    while i > 0:
        ch = s[i-1]
        code = ord(ch)
        is_hira = (0x3040 <= code <= 0x309F)
        is_kata = (0x30A0 <= code <= 0x30FF)
        if is_hira or is_kata:
            i -= 1
        else:
            break
    tail = s[i:]
    tail = _to_hira(tail)
    return tail

def _safe_suffix_hira(x: str, n: int) -> str:
    xh = _to_hira(_nfkc_str(x))
    return xh[-n:] if len(xh) >= n else xh

def _pick_reading_wrongs(candidates: list[str], correct: str, pos: str, jp_word: str = "", k: int = 3) -> list[str]:
    """
    ✅ 새 규칙
    1) 끝 모양을 최대한 맞춘다.
    2) jp_word의 오쿠리가나가 2글자면, 보기 reading 끝도 2글자 동일을 최우선.
       (가능한 만큼 채우고, 부족하면 1글자 동일로 보강)
    3) 그래도 부족하면 "가장 비슷한 끝" 후보로 채우되, 완전 엉뚱한 끝은 최대한 늦게.
    """
    correct_nf = _nfkc_str(correct)
    cands = _uniq([_nfkc_str(c) for c in candidates if _nfkc_str(c) and _nfkc_str(c) != correct_nf])
    if len(cands) < k:
        return []

    # 정답/후보는 히라가나 기준으로 비교
    correct_h = _to_hira(correct_nf)

    # 오쿠리가나(꼬리) 추출
    okuri = _jp_okurigana_suffix(jp_word)
    okuri = _to_hira(okuri)

    # (중요) 한자 없는 단어는 okuri가 전체가 되어버릴 수 있음 → "끝 비교용"으로만 쓰자
    ok2 = okuri[-2:] if len(okuri) >= 2 else ""
    ok1 = okuri[-1:] if len(okuri) >= 1 else ""

    # 정답의 끝도 참고
    cor2 = _safe_suffix_hira(correct_h, 2)
    cor1 = _safe_suffix_hira(correct_h, 1)

    # “2글자 모양” 타겟: (오쿠리 2글자 존재하면 그걸 우선) 없으면 정답 끝2글자
    target2 = ok2 if ok2 else cor2
    target1 = ok1 if ok1 else cor1

    # 0) する(특수): "する" 꼬리면 우선적으로 する로 맞추기
    want_suru = (target2 == "する") or correct_h.endswith("する")

    def score(c: str) -> int:
        ch = _to_hira(c)
        sc = 0
        if want_suru:
            if ch.endswith("する"):
                sc += 100
            else:
                sc -= 50
        if target2 and _safe_suffix_hira(ch, 2) == target2:
            sc += 60
        if target1 and _safe_suffix_hira(ch, 1) == target1:
            sc += 25
        if ch == correct_h:
            sc -= 999
        return sc

    ranked = sorted(cands, key=lambda x: score(x), reverse=True)

    same2 = [c for c in ranked if target2 and _safe_suffix_hira(c, 2) == target2]
    same1 = [c for c in ranked if target1 and _safe_suffix_hira(c, 1) == target1]

    out = []
    for c in same2:
        if c not in out:
            out.append(c)
        if len(out) == k:
            return out
    for c in same1:
        if c not in out:
            out.append(c)
        if len(out) == k:
            return out
    for c in ranked:
        if c not in out:
            out.append(c)
        if len(out) == k:
            return out

    return out[:k]

def make_question(row: pd.Series, qtype: str, pool: pd.DataFrame) -> dict:
    jp = str(row.get("jp_word", "")).strip()
    rd = str(row.get("reading", "")).strip()
    mn = str(row.get("meaning", "")).strip()
    pos = str(row.get("pos", "")).strip().lower()
    ex_jp = str(row.get("example_jp", "")).strip()
    ex_kr = str(row.get("example_kr", "")).strip()

    pool_pos = pool[pool["pos"].astype(str).str.strip().str.lower() == pos].copy()

    if qtype == "reading":
        prompt = f"{jp}의 발음은?"
        correct = rd
        candidates = (
            pool_pos.loc[pool_pos["reading"] != correct, "reading"]
            .dropna().drop_duplicates().tolist()
        )
        wrongs = _pick_reading_wrongs(candidates, correct, pos=pos, jp_word=jp, k=3)
        if len(wrongs) < 3:
            c2 = _uniq([str(x).strip() for x in candidates if str(x).strip()])
            if len(c2) < 3:
                st.error(f"오답 후보 부족(발음): pos={pos}, 후보={len(c2)}개")
                st.stop()
            wrongs = random.sample(c2, 3)

    elif qtype == "meaning":
        prompt = f"{jp}의 뜻은?"
        correct = mn
        candidates = (
            pool_pos.loc[pool_pos["meaning"] != correct, "meaning"]
            .dropna().drop_duplicates().tolist()
        )
        if len(candidates) < 3:
            st.error(f"오답 후보 부족(뜻): pos={pos}, 후보={len(candidates)}개")
            st.stop()
        wrongs = random.sample(candidates, 3)

    elif qtype == "kr2jp":
        prompt = f"'{mn}'의 일본어는?"
        correct = jp
        candidates = (
            pool_pos.loc[pool_pos["jp_word"] != correct, "jp_word"]
            .dropna().astype(str).str.strip().tolist()
        )
        candidates = [x for x in dict.fromkeys(candidates) if x]
        if len(candidates) < 3:
            st.error(f"오답 후보 부족(한→일): pos={pos}, 후보={len(candidates)}개")
            st.stop()
        wrongs = random.sample(candidates, 3)

    else:
        raise ValueError(f"Unknown qtype: {qtype}")

    choices = wrongs + [correct]
    random.shuffle(choices)

    return {
        "prompt": prompt,
        "choices": choices,
        "correct_text": correct,
        "jp_word": jp,
        "reading": rd,
        "meaning": mn,
        "pos": pos,
        "qtype": qtype,
        "example_jp": ex_jp,
        "example_kr": ex_kr,
    }

def build_quiz(qtype: str, pos: str) -> list[dict]:
    # ✅ 안전장치: 제한 품사에서는 reading 강제 금지
    pos = str(pos).strip().lower()
    qtype = str(qtype).strip()
    if pos in POS_ONLY_2TYPES and qtype == "reading":
        qtype = "meaning"

    ensure_pool_ready()
    ensure_mastered_words_shape()
    ensure_excluded_wrong_words_shape()
    ensure_mastery_banner_shape()

    pool = st.session_state["_pool"]

    base_pos = pool[pool["pos"].astype(str).str.strip().str.lower() == pos].copy()

    if len(base_pos) < N:
        st.warning(f"{POS_LABEL_MAP.get(pos,pos)} 단어가 부족합니다. (현재 {len(base_pos)}개 / 필요 {N}개)")
        return []

    k = mastery_key(qtype=qtype, pos=pos)
    mastered = st.session_state.get("mastered_words", {}).get(k, set())
    excluded = st.session_state.get("excluded_wrong_words", {}).get(k, set())

    blocked = set()
    if mastered:
        blocked |= set(mastered)
    if excluded:
        blocked |= set(excluded)

    def _filter_blocked(df: pd.DataFrame) -> pd.DataFrame:
        if not blocked:
            return df
        keys = df["jp_word"].astype(str).str.strip()
        return df[~keys.isin(blocked)].copy()

    base = _filter_blocked(base_pos)

    if len(base) < N:
        st.session_state.setdefault("mastery_done", {})
        st.session_state.mastery_done[k] = True
        return []

    sampled = base.sample(n=N, replace=False).reset_index(drop=True)
    return [make_question(sampled.iloc[i], qtype, pool) for i in range(N)]

def build_quiz_from_wrongs(wrong_list: list, qtype: str, pos: str) -> list:
    # ✅ 안전장치
    pos = str(pos).strip().lower()
    qtype = str(qtype).strip()
    if pos in POS_ONLY_2TYPES and qtype == "reading":
        qtype = "meaning"

    ensure_pool_ready()
    pool = st.session_state["_pool"]

    wrong_words = []
    for w in (wrong_list or []):
        key = str(w.get("단어", "")).strip()
        if key:
            wrong_words.append(key)
    wrong_words = list(dict.fromkeys(wrong_words))

    if not wrong_words:
        st.warning("현재 오답 노트가 비어 있어요. 🙂")
        return []

    retry_df = pool[
        (pool["pos"].astype(str).str.strip().str.lower() == str(pos).lower().strip())
        & (pool["jp_word"].isin(wrong_words))
    ].copy()
    if len(retry_df) == 0:
        st.error("오답 단어를 풀에서 찾지 못했습니다. (jp_word 매칭 확인)")
        st.stop()

    retry_df = retry_df.sample(frac=1).reset_index(drop=True)
    return [make_question(retry_df.iloc[i], qtype, pool) for i in range(len(retry_df))]

# ============================================================
# ✅ Admin/My pages
# ============================================================
def render_admin_dashboard():
    st.subheader("📊 관리자 대시보드")

    if not is_admin():
        st.error("접근 권한이 없습니다.")
        st.session_state.page = "quiz"
        st.stop()

    if st.button("← 돌아가기", use_container_width=True, key="btn_admin_back"):
        st.session_state.page = "quiz"
        st.rerun()

    sb_authed_local = get_authed_sb()
    if sb_authed_local is None:
        st.warning("세션 토큰이 없습니다. 다시 로그인해 주세요.")
        return

    st.caption("※ 확장 가능: 전체 기록 조회 등")
    if st.button("최근 전체 기록 100개 보기", use_container_width=True, key="btn_admin_fetch100"):
        try:
            res = run_db(lambda: fetch_all_attempts_admin(sb_authed_local, limit=100))
            if not res.data:
                st.info("기록이 없습니다.")
            else:
                df = pd.DataFrame(res.data)
                df["created_at"] = to_kst_naive(df["created_at"])
                df["품사"] = df["level"].map(lambda x: POS_LABEL_MAP.get(str(x), str(x)))
                df["유형"] = df["pos_mode"].map(lambda x: quiz_label_map.get(str(x), str(x)))
                st.dataframe(df, use_container_width=True, hide_index=True)
        except Exception as e:
            st.error("조회 실패")
            st.write(str(e))

def render_my_dashboard():
    st.subheader("📌 내 대시보드")

    if st.button("← 돌아가기", use_container_width=True, key="btn_my_back"):
        st.session_state.page = "quiz"
        st.rerun()

    u = st.session_state.get("user")
    if not u:
        st.warning("로그인 정보가 없습니다. 다시 로그인해 주세요.")
        st.session_state.page = "quiz"
        st.stop()

    user_id_local = getattr(u, "id", None)
    if not user_id_local:
        st.warning("유저 ID를 찾지 못했습니다. 다시 로그인해 주세요.")
        st.session_state.page = "quiz"
        st.stop()

    sb_authed_local = get_authed_sb()
    if sb_authed_local is None:
        st.warning("세션 토큰이 없습니다. 다시 로그인해 주세요.")
        return

    with st.expander("🗑️ 전체 학습 기록 완전 초기화", expanded=False):
        st.warning("이 작업은 되돌릴 수 없습니다.\n(최근 기록 / 오답 TOP10 / 진행중 복원까지 모두 초기화됩니다.)")
        agree = st.checkbox("초기화에 동의합니다.", key="chk_reset_all_agree")
        if st.button("🗑️ 지금 완전 초기화", type="primary", use_container_width=True, key="btn_reset_all_records"):
            if not agree:
                st.error("초기화에 동의해 주세요.")
                st.stop()

            try:
                run_db(lambda: delete_all_learning_records(sb_authed_local, user_id_local))

                clear_question_widget_keys()
                for k in [
                    "history", "wrong_counter", "total_counter",
                    "wrong_list", "quiz", "answers", "submitted",
                    "saved_this_attempt", "stats_saved_this_attempt",
                    "session_stats_applied_this_attempt",
                    "quiz_version",
                    "mastered_words", "mastery_banner_shown", "mastery_done",
                    "progress_restored", "pool_ready",
                    "excluded_wrong_words",
                ]:
                    st.session_state.pop(k, None)

                st.success("✅ 전체 학습 기록이 완전 초기화되었습니다.")
                st.session_state.page = "quiz"
                st.rerun()

            except Exception as e:
                st.error("초기화 실패: RLS 정책(삭제 권한) 또는 테이블/컬럼 확인이 필요합니다.")
                st.exception(e)

    try:
        res = run_db(lambda: fetch_recent_attempts(sb_authed_local, user_id_local, limit=50))
    except Exception as e:
        st.info("기록을 불러오지 못했습니다.")
        st.write(str(e))
        return

    if not res.data:
        st.info("아직 저장된 기록이 없습니다. 문제를 풀고 제출하면 기록이 쌓여요.")
        return

    hist = pd.DataFrame(res.data).copy()
    hist["created_at"] = to_kst_naive(hist["created_at"])
    hist["품사"] = hist["level"].map(lambda x: POS_LABEL_MAP.get(str(x), str(x)))
    hist["유형"] = hist["pos_mode"].map(lambda x: quiz_label_map.get(str(x), str(x)))
    hist["정답률"] = (hist["score"] / hist["quiz_len"]).fillna(0.0)

    avg_rate = float(hist["정답률"].mean() * 100)
    best = int(hist["score"].max())
    last_score = int(hist.iloc[0]["score"])
    last_total = int(hist.iloc[0]["quiz_len"])

    dashboard_html = f"""
    <style>
    .stat-grid{{
      display:grid;
      grid-template-columns: repeat(3, 1fr);
      gap:12px;
      margin: 6px 0 6px 0;
    }}
    .stat-card{{
      border:1px solid rgba(120,120,120,0.25);
      border-radius:18px;
      padding:14px 14px;
      background: rgba(255,255,255,0.02);
    }}
    .stat-label{{
      font-size:12px;
      font-weight:800;
      opacity:.72;
      line-height:1.2;
    }}
    .stat-value{{
      margin-top:6px;
      font-size:22px;
      font-weight:900;
      line-height:1.1;
    }}
    .stat-sub{{
      margin-top:6px;
      font-size:12px;
      opacity:.70;
      line-height:1.2;
    }}
    @media (max-width: 520px){{
      .stat-grid{{ grid-template-columns: 1fr; }}
      .stat-value{{ font-size:24px; }}
    }}
    </style>

    <div class="jp">
      <div class="stat-grid">
        <div class="stat-card">
          <div class="stat-label">최근 평균(최대 50회)</div>
          <div class="stat-value">{avg_rate:.0f}%</div>
          <div class="stat-sub">정답률 기준</div>
        </div>

        <div class="stat-card">
          <div class="stat-label">최고 점수</div>
          <div class="stat-value">{best} / {last_total}</div>
          <div class="stat-sub">최근 기록 중 최고</div>
        </div>

        <div class="stat-card">
          <div class="stat-label">최근 점수</div>
          <div class="stat-value">{last_score} / {last_total}</div>
          <div class="stat-sub">가장 최근 1회</div>
        </div>
      </div>
    </div>
    """
    components.html(dashboard_html, height=330)

    st.markdown("### ❌ 자주 틀린 단어 TOP10 (최근 50회)")

    counter = Counter()
    for row in (res.data or []):
        wl = row.get("wrong_list") or []
        if isinstance(wl, list):
            for w in wl:
                word = str(w.get("단어", "")).strip()
                if word:
                    counter[word] += 1

    if not counter:
        st.caption("아직 오답 데이터가 충분하지 않습니다. 몇 번 더 풀면 TOP10이 생겨요 🙂")
        return

    st.markdown(
        """
<style>
.wt10-card{
  border:1px solid rgba(120,120,120,0.25);
  border-radius:18px;
  padding:14px 16px;
  margin:12px 0;
  background: rgba(255,255,255,0.02);
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:14px;
}
.wt10-left{
  display:flex;
  flex-direction:column;
  gap:6px;
  min-width: 0;
}
.wt10-title{
  font-size:18px;
  font-weight:900;
  line-height:1.15;
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
}
.wt10-sub{
  font-size:13px;
  opacity:.75;
}
.wt10-badge{
  border:1px solid rgba(120,120,120,0.25);
  background: rgba(255,255,255,0.03);
  border-radius:999px;
  padding:7px 12px;
  font-size:13px;
  font-weight:900;
  white-space:nowrap;
}
</style>
""",
        unsafe_allow_html=True,
    )

    def render_wrong_top10_card(rank: int, word: str, cnt: int):
        st.markdown(
            f"""
<div class="jp">
  <div class="wt10-card">
    <div class="wt10-left">
      <div class="wt10-title">#{rank} {word}</div>
      <div class="wt10-sub">최근 50회 기준</div>
    </div>
    <div class="wt10-badge">오답 {cnt}회</div>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )

    top10 = counter.most_common(10)
    for i, (w, cnt) in enumerate(top10, start=1):
        render_wrong_top10_card(i, str(w), int(cnt))

# ============================================================
# ✅ Home
# ============================================================
def reset_quiz_state_only():
    clear_question_widget_keys()
    for k in ["quiz", "answers", "submitted", "wrong_list",
              "saved_this_attempt", "stats_saved_this_attempt",
              "session_stats_applied_this_attempt"]:
        st.session_state.pop(k, None)

def go_quiz_from_home():
    reset_quiz_state_only()
    st.session_state.page = "quiz"
    st.session_state["_scroll_top_once"] = True

def render_home():
    u = st.session_state.get("user")
    email = (getattr(u, "email", None) if u else None) or st.session_state.get("login_email", "")

    st.markdown(
        f"""
<div class="jp headbar">
  <div class="headtitle">✨ 왕초보 탈출</div>
  <div class="headhello">환영합니다 🙂 <span class="mail">{email}</span></div>
</div>
""",
        unsafe_allow_html=True,
    )

    quotes = [
        "오늘 10문항이면 충분해요.",
        "루틴은 작게, 지속은 길게.",
        "정답보다 중요한 건 ‘계속’입니다.",
        "단어가 쌓이면 문장이 열립니다.",
        "오늘의 한 번이 내일의 자신감이에요.",
    ]
    q = random.choice(quotes)

    st.markdown(
        f"""
<div class="jp" style="
  margin-top:1px;
  border:1px solid rgba(120,120,120,0.18);
  border-radius:18px; padding:16px; background:rgba(255,255,255,0.03);">
  <div style="font-weight:900; font-size:14px; opacity:.75;">오늘의 말</div>
  <div style="margin-top:6px; font-weight:900; font-size:20px; line-height:1.3;">{q}</div>
  <div style="margin-top:10px; opacity:.80; font-size:13px; line-height:1.55;">
    품사 하나씩만 잡아도, 말이 빨라집니다.
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    st.divider()

    c1, c2, c3 = st.columns([5, 3, 3])
    with c1:
        st.button("▶ 오늘의 퀴즈 시작", type="primary", use_container_width=True,
                  key="btn_home_start", on_click=go_quiz_from_home)
    with c2:
        st.button("📌 마이페이지", use_container_width=True,
                  key="btn_home_my", on_click=nav_to, args=("my",))
    with c3:
        st.button("🚪 로그아웃", use_container_width=True,
                  key="btn_home_logout", on_click=nav_logout)

# ============================================================
# ✅ App Start: refresh → login → routing
# ============================================================
ok = refresh_session_from_cookie_if_needed(force=False)
if not ok and (cookies.get("refresh_token") or cookies.get("access_token")):
    clear_auth_everywhere()
    st.caption("세션 복원에 실패해서 로그인을 다시 요청합니다.")

require_login()

ALLOWED_PAGES = {"home", "quiz", "my", "admin"}
if "page" not in st.session_state:
    st.session_state.page = "home"
if st.session_state.get("page") not in ALLOWED_PAGES:
    st.session_state.page = "home"

user = st.session_state.user
user_id = user.id
user_email = getattr(user, "email", None) or st.session_state.get("login_email")
sb_authed = get_authed_sb()

# ✅ pos 기반 available_types 적용
try:
    if sb_authed is not None:
        available_types = get_available_quiz_types_for_pos(st.session_state.get("pos", "noun"))
    else:
        base_types = QUIZ_TYPES_USER
        pos_now = str(st.session_state.get("pos", "noun")).lower().strip()
        available_types = [t for t in base_types if t in ("meaning", "kr2jp")] if pos_now in POS_ONLY_2TYPES else base_types
except Exception:
    pos_now = str(st.session_state.get("pos", "noun")).lower().strip()
    available_types = ["meaning", "kr2jp"] if pos_now in POS_ONLY_2TYPES else QUIZ_TYPES_USER

# ✅ 현재 선택된 유형이 pos에서 허용되지 않으면 meaning으로 강제
if st.session_state.get("quiz_type") not in available_types:
    st.session_state.quiz_type = "meaning"

if sb_authed is not None and not st.session_state.get("progress_restored"):
    try:
        restore_progress_from_db(sb_authed, user_id)
    except Exception:
        pass
    st.session_state.progress_restored = True

# ✅ 복원 후에도 pos/available_types 재동기화
try:
    available_types = get_available_quiz_types_for_pos(st.session_state.get("pos", "noun")) if sb_authed is not None else available_types
except Exception:
    pass
if st.session_state.get("quiz_type") not in available_types:
    st.session_state.quiz_type = "meaning"

if st.session_state.get("page") != "home":
    u = st.session_state.get("user")
    email = (getattr(u, "email", None) if u else None) or st.session_state.get("login_email", "")
    st.markdown(
        f"""
<div class="jp headbar">
  <div class="headtitle">✨ 단어 퀴즈</div>
  <div class="headhello">환영합니다 🙂 <span class="mail">{email}</span></div>
</div>
""",
        unsafe_allow_html=True,
    )

if sb_authed is not None:
    ensure_profile(sb_authed, user)
    att = mark_attendance_once(sb_authed)
    if att:
        st.session_state["streak_count"] = int(att.get("streak_count", 0) or 0)
        st.session_state["did_attend_today"] = bool(att.get("did_attend", False))

# ============================================================
# ✅ Routing
# ============================================================
if st.session_state.page == "home":
    render_home()
    st.stop()

if st.session_state.page == "admin":
    if not is_admin():
        st.session_state.page = "quiz"
        st.warning("관리자 권한이 없습니다.")
        st.rerun()
    render_admin_dashboard()
    st.stop()

if st.session_state.page == "my":
    try:
        render_my_dashboard()
    except Exception:
        st.error("마이페이지에서 예외가 발생했습니다. 아래 Traceback을 확인해 주세요.")
        st.code(traceback.format_exc())
    st.stop()

# ============================================================
# ✅ Quiz Page
# ============================================================
render_topcard()
render_sound_toggle()

streak = st.session_state.get("streak_count")
did_today = st.session_state.get("did_attend_today")
if streak is not None:
    if did_today:
        st.success(f"✅ 오늘 출석 완료!  (연속 {streak}일)")
    else:
        st.caption(f"연속 출석 {streak}일")
    if streak >= 30:
        st.info("🔥 30일 연속 달성!")
    elif streak >= 7:
        st.info("🏅 7일 연속 달성!")

if "today_goal" not in st.session_state:
    st.session_state.today_goal = "오늘은 10문항 1회 완주"
if "today_goal_done" not in st.session_state:
    st.session_state.today_goal_done = False

with st.container():
    st.markdown("### 🎯 오늘의 목표(루틴)")
    c1, c2 = st.columns([7, 3])
    with c1:
        st.session_state.today_goal = st.text_input(
            "목표 문장",
            value=st.session_state.today_goal,
            label_visibility="collapsed",
            placeholder="예) 오늘은 명사 1회 + 동사 1회",
        )
    with c2:
        st.session_state.today_goal_done = st.checkbox("달성", value=bool(st.session_state.today_goal_done))
    if st.session_state.today_goal_done:
        st.success("좋아요. 오늘 루틴 완료 ✅")
    else:
        st.caption("가볍게라도 체크하면 루틴이 끊기지 않습니다.")

st.divider()

if "quiz_version" not in st.session_state:
    st.session_state.quiz_version = 0
if "submitted" not in st.session_state:
    st.session_state.submitted = False
if "wrong_list" not in st.session_state:
    st.session_state.wrong_list = []
if "saved_this_attempt" not in st.session_state:
    st.session_state.saved_this_attempt = False
if "stats_saved_this_attempt" not in st.session_state:
    st.session_state.stats_saved_this_attempt = False
if "session_stats_applied_this_attempt" not in st.session_state:
    st.session_state.session_stats_applied_this_attempt = False
if "history" not in st.session_state:
    st.session_state.history = []
if "progress_dirty" not in st.session_state:
    st.session_state.progress_dirty = False
if "wrong_counter" not in st.session_state:
    st.session_state.wrong_counter = {}
if "total_counter" not in st.session_state:
    st.session_state.total_counter = {}

ensure_mastered_words_shape()
ensure_excluded_wrong_words_shape()
ensure_mastery_banner_shape()

# ============================================================
# ✅ 상단 UI: 품사 버튼 → 유형 버튼 → 캡션 → divider
# ============================================================
def on_pick_pos(ps: str):
    ps = str(ps).strip().lower()
    if ps == st.session_state.pos:
        return
    st.session_state.pos = ps

    # ✅ pos 제한이면 reading 선택 상태를 자동 해제
    if ps in POS_ONLY_2TYPES and st.session_state.quiz_type == "reading":
        st.session_state.quiz_type = "meaning"

    # ✅ pos 변경에 따라 available_types 재계산(전역 변수 업데이트 목적)
    # (Streamlit rerun 환경이라 아래에서 다시 그려질 때 반영됨)
    clear_question_widget_keys()
    new_quiz = build_quiz(st.session_state.quiz_type, st.session_state.pos)
    start_quiz_state(new_quiz, st.session_state.quiz_type, clear_wrongs=True)
    st.session_state["_scroll_top_once"] = True

def on_pick_qtype(qt: str):
    qt = str(qt).strip()
    if qt == st.session_state.quiz_type:
        return
    st.session_state.quiz_type = qt

    clear_question_widget_keys()
    new_quiz = build_quiz(st.session_state.quiz_type, st.session_state.pos)
    start_quiz_state(new_quiz, st.session_state.quiz_type, clear_wrongs=True)
    st.session_state["_scroll_top_once"] = True

# ✅ 현재 pos 기준으로 유형 리스트 재계산(표시 직전에!)
try:
    if sb_authed is not None:
        available_types = get_available_quiz_types_for_pos(st.session_state.get("pos", "noun"))
    else:
        pos_now = str(st.session_state.get("pos", "noun")).lower().strip()
        available_types = ["meaning", "kr2jp"] if pos_now in POS_ONLY_2TYPES else QUIZ_TYPES_USER
except Exception:
    pos_now = str(st.session_state.get("pos", "noun")).lower().strip()
    available_types = ["meaning", "kr2jp"] if pos_now in POS_ONLY_2TYPES else QUIZ_TYPES_USER

# ✅ 선택된 유형이 현재 pos에서 허용되지 않으면 meaning으로 강제
if st.session_state.get("quiz_type") not in available_types:
    st.session_state.quiz_type = "meaning"

st.markdown('<div class="qtypewrap">', unsafe_allow_html=True)

pos_cols = st.columns(4, gap="small")
for i, ps in enumerate(POS_OPTIONS):
    with pos_cols[i % 4]:
        is_sel = (ps == st.session_state.pos)
        st.button(
            ("✅ " if is_sel else "") + POS_LABEL_MAP.get(ps, ps),
            use_container_width=True,
            type=("primary" if is_sel else "secondary"),
            key=f"btn_pos_{ps}",
            on_click=on_pick_pos,
            args=(ps,),
        )

st.markdown('<div class="qtype_hint jp">✨품사를 선택하세요</div>', unsafe_allow_html=True)

type_cols = st.columns(len(available_types), gap="small")
for i, qt in enumerate(available_types):
    with type_cols[i]:
        is_sel = (qt == st.session_state.quiz_type)
        st.button(
            ("✅ " if is_sel else "") + quiz_label_map.get(qt, qt),
            use_container_width=True,
            type=("primary" if is_sel else "secondary"),
            key=f"btn_qtype_{qt}",
            on_click=on_pick_qtype,
            args=(qt,),
        )

st.markdown('<div class="qtype_hint jp">✨유형을 선택하세요</div>', unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)

st.markdown('<div class="tight-divider">', unsafe_allow_html=True)
st.divider()
st.markdown("</div>", unsafe_allow_html=True)

# ============================================================
# ✅ 버튼: 새 문제 / 맞힌 단어 제외 초기화
# ============================================================
cbtn1, cbtn2 = st.columns(2)

with cbtn1:
    if st.button("🔄 새 문제(랜덤 10문항)", use_container_width=True, key="btn_new_random_10"):
        k_now = mastery_key()
        if st.session_state.get("mastery_done", {}).get(k_now, False):
            st.session_state["_scroll_top_once"] = True
            st.rerun()

        clear_question_widget_keys()
        new_quiz = build_quiz(st.session_state.quiz_type, st.session_state.pos)
        start_quiz_state(new_quiz, st.session_state.quiz_type, clear_wrongs=True)
        st.session_state["_scroll_top_once"] = True
        st.rerun()

with cbtn2:
    if st.button("✅ 맞힌 단어 제외 초기화", use_container_width=True, key="btn_reset_mastered_current_type"):
        ensure_mastered_words_shape()
        k_now = mastery_key()
        st.session_state.mastered_words[k_now] = set()
        st.session_state.mastery_banner_shown[k_now] = False
        st.session_state.mastery_done[k_now] = False

        # ✅ 제한 품사면 quiz_type 방어
        if str(st.session_state.get("pos","noun")).lower().strip() in POS_ONLY_2TYPES and st.session_state.quiz_type == "reading":
            st.session_state.quiz_type = "meaning"

        clear_question_widget_keys()
        new_quiz = build_quiz(st.session_state.quiz_type, st.session_state.pos)
        start_quiz_state(new_quiz, st.session_state.quiz_type, clear_wrongs=True)

        st.success(f"초기화 완료 (품사: {POS_LABEL_MAP.get(st.session_state.pos, st.session_state.pos)} / 유형: {quiz_label_map[st.session_state.quiz_type]})")
        st.session_state["_scroll_top_once"] = True
        st.rerun()

k_now = mastery_key()
if st.session_state.get("mastery_done", {}).get(k_now, False):
    st.success("🏆 이 품사/유형을 완전히 정복했어요!")
    st.caption("👉 다른 품사·유형을 선택하거나, '맞힌 단어 제외 초기화'로 다시 시작할 수 있어요.")

# ============================================================
# ✅ 퀴즈 생성(없으면 1회 자동 생성)
# ============================================================
if "quiz" not in st.session_state or not isinstance(st.session_state.quiz, list):
    st.session_state.quiz = []

is_mastered_done = bool(st.session_state.get("mastery_done", {}).get(k_now, False))
if (not is_mastered_done) and len(st.session_state.quiz) == 0:
    clear_question_widget_keys()
    st.session_state.quiz = build_quiz(st.session_state.quiz_type, st.session_state.pos) or []
    st.session_state.submitted = False

if len(st.session_state.quiz) == 0:
    st.info("이 품사에 출제할 단어가 없어요. CSV의 pos 값을 확인해 주세요.")
    st.stop()

quiz_len = len(st.session_state.quiz)
if "answers" not in st.session_state or not isinstance(st.session_state.answers, list) or len(st.session_state.answers) != quiz_len:
    st.session_state.answers = [None] * quiz_len

if bool(st.session_state.get("mastery_done", {}).get(k_now, False)):
    st.stop()

# ============================================================
# ✅ 문제 표시
# ============================================================
for idx, q in enumerate(st.session_state.quiz):
    st.subheader(f"Q{idx+1}")
    st.markdown(
        f'<div class="jp" style="margin-top:-6px; margin-bottom:6px; font-size:18px; font-weight:500; line-height:1.35;">{q["prompt"]}</div>',
        unsafe_allow_html=True
    )

    widget_key = f"q_{st.session_state.quiz_version}_{idx}"
    prev = st.session_state.answers[idx]
    default_index = None
    if prev is not None and prev in q["choices"]:
        default_index = q["choices"].index(prev)

    choice = st.radio(
        label="보기",
        options=q["choices"],
        index=default_index,
        key=widget_key,
        label_visibility="collapsed",
        on_change=mark_progress_dirty,
    )
    st.session_state.answers[idx] = choice

sync_answers_from_widgets()

# ============================================================
# ✅ 제출/채점
# ============================================================
quiz_len = len(st.session_state.quiz)
all_answered = (quiz_len > 0) and all(a is not None for a in st.session_state.answers)

if st.button("✅ 제출하고 채점하기", disabled=not all_answered, type="primary", use_container_width=True, key="btn_submit"):
    st.session_state.submitted = True
    st.session_state.session_stats_applied_this_attempt = False

if not all_answered:
    st.info("모든 문제에 답을 선택하면 제출 버튼이 활성화됩니다.")

# ============================================================
# ✅ 제출 후 화면
# ============================================================
if st.session_state.submitted:
    show_post_ui = (SHOW_POST_SUBMIT_UI == "Y") or is_admin()

    ensure_mastered_words_shape()
    ensure_excluded_wrong_words_shape()

    current_type = st.session_state.quiz_type
    current_pos = st.session_state.pos
    k_now = mastery_key()

    score = 0
    wrong_list = []

    for idx, q in enumerate(st.session_state.quiz):
        picked = st.session_state.answers[idx]
        correct = q["correct_text"]
        word_key = str(q.get("jp_word", "")).strip()

        if picked == correct:
            score += 1
            if word_key:
                st.session_state.mastered_words.setdefault(k_now, set()).add(word_key)
        else:
            wrong_list.append({
                "No": idx + 1,
                "문제": str(q.get("prompt", "")),
                "내 답": "" if picked is None else str(picked),
                "정답": str(correct),
                "단어": str(q.get("jp_word", "")).strip(),
                "읽기": str(q.get("reading", "")).strip(),
                "뜻": str(q.get("meaning", "")).strip(),
                "품사": current_pos,
                "유형": current_type,
            })

    st.session_state.wrong_list = wrong_list

    st.success(f"점수: {score} / {quiz_len}")
    ratio = score / quiz_len if quiz_len else 0

    if ratio == 1:
        sfx("perfect")
    elif ratio >= 0.7:
        sfx("correct")
    else:
        sfx("wrong")

    if ratio == 1:
        st.balloons()
        st.success("🎉 완벽해요! 전부 정답입니다.")
    elif ratio >= 0.7:
        st.info("👍 잘하고 있어요! 조금만 더 다듬으면 완벽해질 거예요.")
    else:
        st.warning("💪 괜찮아요! 틀린 문제는 성장의 재료예요. 다시 한 번 도전해봐요.")

    sb_authed_local = get_authed_sb()
    if sb_authed_local is None:
        if show_post_ui:
            st.warning("DB 저장/조회용 토큰이 없습니다. 다시 로그인해 주세요.")
    else:
        if not st.session_state.saved_this_attempt:
            try:
                run_db(lambda: save_attempt_to_db(
                    sb_authed=sb_authed_local,
                    user_id=user_id,
                    user_email=user_email,
                    pos=current_pos,
                    quiz_type=current_type,
                    quiz_len=quiz_len,
                    score=score,
                    wrong_list=wrong_list,
                ))
                st.session_state.saved_this_attempt = True
            except Exception as e:
                if show_post_ui:
                    st.warning("DB 저장에 실패했습니다. (테이블/컬럼/권한/RLS 정책 확인 필요)")
                    st.write(str(e))

        if not st.session_state.stats_saved_this_attempt:
            try:
                sync_answers_from_widgets()
                items = build_word_results_bulk_payload(
                    quiz=st.session_state.quiz,
                    answers=st.session_state.answers,
                    quiz_type=current_type,
                    pos=current_pos,
                )
                if items:
                    run_db(lambda: sb_authed_local.rpc("record_word_results_bulk", {"p_items": items}).execute())
                st.session_state.stats_saved_this_attempt = True
            except Exception as e:
                if show_post_ui and is_admin():
                    st.error("❌ 단어 통계(bulk) 저장 실패 (RPC/정책 확인)")
                    st.exception(e)

        try:
            save_progress_to_db(sb_authed_local, user_id)
        except Exception:
            pass

    # ============================================================
    # ✅ 오답노트
    # ============================================================
    if st.session_state.wrong_list:
        st.subheader("❌ 오답 노트")

        st.markdown(
            """
<style>
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
  font-weight: 700;
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
.ans-k{ opacity: 0.7; font-weight: 700; }
</style>
""",
            unsafe_allow_html=True,
        )

        def _s(v):
            return "" if v is None else str(v)

        for w in st.session_state.wrong_list:
            no = _s(w.get("No"))
            qtext = _s(w.get("문제"))
            picked = _s(w.get("내 답"))
            correct = _s(w.get("정답"))
            word = _s(w.get("단어"))
            reading = _s(w.get("읽기"))
            meaning = _s(w.get("뜻"))
            mode = quiz_label_map.get(w.get("유형"), w.get("유형", ""))
            pos_label = POS_LABEL_MAP.get(w.get("품사"), w.get("품사", ""))

            st.markdown(
                f"""
<div class="jp">
  <div class="wrong-card">
    <div class="wrong-top">
      <div>
        <div class="wrong-title">Q{no}. {word}</div>
        <div class="wrong-sub">{qtext} · 품사: {pos_label} · 유형: {mode}</div>
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

        if st.button("❌ 틀린 문제만 다시 풀기", type="primary", use_container_width=True, key="btn_retry_wrongs_bottom"):
            clear_question_widget_keys()
            retry_quiz = build_quiz_from_wrongs(st.session_state.wrong_list, st.session_state.quiz_type, st.session_state.pos)
            start_quiz_state(retry_quiz, st.session_state.quiz_type, clear_wrongs=True)
            st.session_state["_scroll_top_once"] = True
            st.rerun()

    if st.button("✅ 다음 10문항 시작하기", type="primary", use_container_width=True, key="btn_next_10"):
        clear_question_widget_keys()
        new_quiz = build_quiz(st.session_state.quiz_type, st.session_state.pos)
        start_quiz_state(new_quiz, st.session_state.quiz_type, clear_wrongs=True)
        st.session_state["_scroll_top_once"] = True
        st.rerun()

    show_naver_talk = (SHOW_NAVER_TALK == "Y") or is_admin()
    if show_naver_talk:
        render_naver_talk()
