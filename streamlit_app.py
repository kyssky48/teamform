# 생성: 2026-10-21 22:33 (KST)
"""팀 편성 앱 화면. 화면 요소의 key는 공고 2.7절 표와 같아야 한다(자동 채점)."""
import os

import streamlit as st

from teamform import auth, config, service
from teamform.ai import AIError, openrouter_caller
from teamform.model import Account, Student
from teamform.store import MemoryStore

REFRESH_SECONDS = 3  # 다른 사람의 변경 보기: 5초 이하 (공고 2.7절)

st.set_page_config(page_title="팀 편성", page_icon="👥")


# ---- 저장소와 AI ----


@st.cache_resource(show_spinner=False)
def get_store():
    """연결은 한 번만 만들고 모든 화면이 다시 씀(공고 4.2절). 실패하면 캐시하지 않고 다음에 다시 시도."""
    if os.environ.get("TEAMFORM_STORE") == "memory":  # 화면 시험용
        store = MemoryStore()
    else:
        from teamform.pg_store import PgStore

        url = config.get_secret("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL 없음")
        store = PgStore(url)
        store.apply_schema()
    admin_pw = config.get_secret("ADMIN_PASSWORD")
    if not admin_pw:
        raise RuntimeError("ADMIN_PASSWORD 없음")
    auth.ensure_admin(store, admin_pw)
    return store


def get_caller():
    if os.environ.get("TEAMFORM_FAKE_AI") == "fail":  # 화면 시험용: 모든 모델이 실패하는 경우

        def fail(model, prompt):
            raise AIError("시험용 가짜 실패")

        return fail
    return openrouter_caller(config.get_secret("OPENROUTER_API_KEY") or "")


try:
    store = get_store()
except Exception as e:  # 예외 글에 DB 주소가 섞일 수 있으므로 종류만 보여 줌
    st.error(f"DB에 연결하지 못함 ({type(e).__name__}). 잠시 뒤 다시 열어 주세요.")
    st.stop()


# ---- 공통 ----


def me() -> Account | None:
    return st.session_state.get("account")


def set_result(text: str) -> None:
    st.session_state["result"] = text


def show_result() -> None:
    with st.container(key="result"):
        text = st.session_state.get("result", "")
        if text:
            (st.success if text.startswith("승인") else st.info if text.startswith("대기") else st.warning)(text)


def describe(s: Student) -> str:
    subs = ", ".join(s.sub_roles) if s.sub_roles else "없음"
    return f"{s.name} — 주 역할: {s.main_role} / 보조 역할: {subs}"


def logout() -> None:
    for k in ("account", "result", "assign_log"):
        st.session_state.pop(k, None)


def still_valid(account: Account) -> bool:
    """명단을 다시 올려 학생이 사라졌으면 로그인 화면으로."""
    found = store.get_login(account.student_no)
    return found is not None and found[0].is_admin == account.is_admin


# ---- 로그인 ----


def login_page() -> None:
    st.title("팀 편성")
    with st.form("login_form"):
        st.text_input("학번", key="login_student_no")
        st.text_input("비밀번호", type="password", key="login_password")
        submitted = st.form_submit_button("로그인", key="login_submit")
    if submitted:
        account = auth.login(store, st.session_state.login_student_no, st.session_state.login_password)
        if account is None:
            set_result("막힘: 학번이나 비밀번호가 틀림")
        else:
            st.session_state["account"] = account
            set_result(f"승인: {account.name}(으)로 로그인함")
            st.rerun()
    show_result()


def header(account: Account) -> None:
    col1, col2 = st.columns([4, 1])
    with col1:
        with st.container(key="whoami"):
            st.markdown(f"**{account.name}** ({account.student_no}) 로그인 중")
    with col2:
        st.button("로그아웃", key="logout", on_click=logout)


# ---- 학생 화면 ----


def on_apply(team_id: int) -> None:
    set_result(service.apply(store, me(), team_id))


def on_vote(applicant_no: str, yes: bool) -> None:
    set_result(service.vote(store, me(), applicant_no, yes))


@st.fragment(run_every=REFRESH_SECONDS)
def student_board() -> None:
    account = me()
    if account is None or not still_valid(account):
        logout()
        st.rerun(scope="app")
    b = service.board(store, account)
    if b.closed:
        st.info("모집이 마감되었습니다.")
    if b.my_team:
        st.write(f"내 팀: 팀{b.my_team}")
    elif b.my_pending:
        st.write(f"아직 팀이 없음 — 팀{b.my_pending.team_id}에 낸 지원의 결과를 기다리는 중")
    else:
        st.write("아직 팀이 없음")

    for team in b.teams:
        with st.container(key=f"team_{team.team_id}", border=True):
            mark = " (내 팀)" if team.team_id == b.my_team else ""
            st.markdown(f"**팀{team.team_id}**{mark} · {len(team.members)}/4명")
            for m in team.members:
                st.write("- " + describe(m))
            if not team.members:
                st.caption("팀원 없음")
            st.button("이 팀에 지원", key=f"apply_{team.team_id}", disabled=not b.can_apply,
                      on_click=on_apply, args=(team.team_id,))
            if team.team_id == b.my_team and team.pending:
                st.markdown("기다리는 지원")
                for pv in team.pending:
                    vote_row(pv)
    show_result()


def vote_row(pv: service.PendingView) -> None:
    no = pv.applicant.student_no
    st.write(describe(pv.applicant))
    c1, c2, c3 = st.columns([1, 1, 2])
    c1.button("찬성", key=f"vote_yes_{no}", disabled=not pv.can_vote, on_click=on_vote, args=(no, True))
    c2.button("거부", key=f"vote_no_{no}", disabled=not pv.can_vote, on_click=on_vote, args=(no, False))
    if pv.my_vote:
        c3.write(f"내 투표: {pv.my_vote}")


# ---- 관리자 화면 ----


def on_start() -> None:
    f = st.session_state.get("admin_roster_file")
    count = int(st.session_state.get("admin_team_count") or 0)
    set_result(service.start(store, me(), f.getvalue() if f else None, count))
    st.session_state.pop("assign_log", None)


def on_close() -> None:
    set_result(service.close(store, me()))


def on_confirm() -> None:
    set_result(service.confirm(store, me()))
    st.session_state.pop("assign_log", None)


def admin_controls() -> None:
    st.subheader("명단 올리기")
    st.file_uploader("명단 CSV (UTF-8)", type=["csv"], key="admin_roster_file")
    st.number_input("팀 수", min_value=1, max_value=20, value=3, step=1, key="admin_team_count")
    st.button("명단으로 처음 상태 만들기", key="admin_start", on_click=on_start)

    st.subheader("마감과 배정")
    st.button("모집 마감", key="admin_close", on_click=on_close)
    clicked = st.button("AI 배정", key="admin_assign")
    status_box = st.container(key="assign_status")
    with status_box:
        for line in st.session_state.get("assign_log", []):
            st.write(line)
    if clicked:
        st.session_state["assign_log"] = []

        def on_status(text: str) -> None:
            st.session_state["assign_log"].append(text)
            status_box.write(text)

        with status_box:
            with st.spinner("AI가 배정안을 만드는 중"):
                outcome = service.assign(store, me(), get_caller(), config.MODELS, on_status)
        # 다시 실행(st.rerun)하지 않음: 아래의 배정안 표, 확정 단추, 현황이 이 실행에서 바로 새 상태로 그려짐
        set_result(outcome)
    plan_table()
    st.button("배정안 확정", key="admin_confirm", on_click=on_confirm)


def plan_table() -> None:
    loaded = service.load_plan(store)
    if not loaded:
        return
    plan, source = loaded
    st.markdown(f"**확정 전 배정안** (만든 곳: {source})")
    rows = []
    for no, team in sorted(plan.items(), key=lambda kv: (kv[1], kv[0])):
        s = store.get_student(no)
        if s:
            rows.append({"팀": f"팀{team}", "이름": s.name, "주 역할": s.main_role,
                         "보조 역할": ", ".join(s.sub_roles) or "없음"})
    st.dataframe(rows, hide_index=True, width="stretch")


@st.fragment(run_every=REFRESH_SECONDS)
def admin_board() -> None:
    account = me()
    if account is None or not still_valid(account):
        logout()
        st.rerun(scope="app")
    b = service.board(store, account)
    st.subheader("현황")
    st.write("모집 마감됨" if b.closed else "모집 중")
    with st.container(key="unassigned", border=True):
        st.markdown("**팀이 없는 학생**")
        st.write(", ".join(s.name for s in b.unassigned) if b.unassigned else "없음")
    for team in b.teams:
        with st.container(key=f"team_{team.team_id}", border=True):
            st.markdown(f"**팀{team.team_id}** · {len(team.members)}/4명")
            for m in team.members:
                st.write("- " + describe(m))
            for pv in team.pending:
                st.caption(f"대기 중인 지원: {pv.applicant.name}")
    show_result()


# ---- 화면 고르기 ----

account = me()
if account is not None and not still_valid(account):
    logout()
    account = None

if account is None:
    login_page()
else:
    header(account)
    if account.is_admin:
        admin_controls()
        admin_board()
    else:
        student_board()
