# 생성: 2026-10-21 22:15 (KST)
# 버리는 시범 코드: st.fragment 안의 단추와 result 컨테이너 갱신 확인
import streamlit as st

@st.cache_resource
def shared():
    return {"apps": []}

S = shared()
st.text_input("학번", key="login_student_no")
me = st.query_params.get("me", "A")
with st.container(key="whoami"):
    st.write(me)

@st.fragment(run_every=3)
def board():
    with st.container(key="team_1"):
        st.write("지원자:", ", ".join(S["apps"]) or "없음")
    if st.button("지원", key="apply_1"):
        S["apps"].append(me)
        st.session_state["result"] = f"대기: {me} 지원"
    for a in S["apps"]:
        if a != me and st.button("찬성", key=f"vote_yes_{a}"):
            st.session_state["result"] = f"승인: {a}"
    with st.container(key="result"):
        st.write(st.session_state.get("result", ""))

board()
