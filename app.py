import json
from pathlib import Path
from datetime import datetime, date

import streamlit as st
from openai import OpenAI

# -------------------------------
# 0. OpenAI 설정
# -------------------------------
# 환경변수 OPENAI_API_KEY를 사용합니다.
# (bash/zsh)  export OPENAI_API_KEY="sk-xxxx"
# (PowerShell) $env:OPENAI_API_KEY="sk-xxxx"
client = OpenAI()


# -------------------------------
# 1. JSON 데이터 로딩
# -------------------------------
@st.cache_data
def load_eco_data():
    json_path = Path(__file__).parent / "eco_programs.json"
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


eco_data = load_eco_data()


# -------------------------------
# 2. LLM 관련 함수
# -------------------------------
def build_system_prompt(eco_data: dict) -> str:
    center_name = eco_data.get("centerName", "자연생태관")
    rules = eco_data.get("visitRules", {})
    max_people = rules.get("maxPeoplePerTeam")
    min_people = rules.get("minPeoplePerTeam")
    deadline_hours = rules.get("reservationDeadlineHours")
    json_str = json.dumps(eco_data, ensure_ascii=False)

    system_prompt = f"""
너는 {center_name} 온라인 방문 예약을 도와주는 AI 챗봇이야.

아래 JSON 데이터는 자연생태관의 프로그램, 시간표, 방문 규정을 담고 있어.
이 JSON 데이터만을 기준으로 대답해야 해. 모르는 정보는 "해당 정보는 제공되지 않습니다."라고 말해.

방문 규칙:
- 1팀 최소 인원: {min_people}명
- 1팀 최대 인원: {max_people}명
- 예약 마감: 방문 예정일 {deadline_hours}시간 전까지

JSON 데이터:
{json_str}

답변 시 지켜야 할 원칙:
1. 사용자가 날짜, 인원, 대상(초등학생/중학생 등)을 말하면,
   JSON의 programs와 availableSlots를 보고 가능한 프로그램과 시간을 안내해.
2. 정원(capacity)와 reserved를 보고, 남은 자리가 없으면 "정원 마감"이라고 알려줘.
3. 현재 버전에서는 실제 예약 저장/정원 차감은 하지 않고,
   "예약이 완료되었다고 가정하고" 안내만 해도 괜찮아.
4. 질문이 FAQ 내용과 관련 있으면, faq 항목을 참고해서 답해.
5. 항상 한국어로, 친절하고 이해하기 쉽게 설명해.
"""
    return system_prompt


def call_llm(messages):
    completion = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        temperature=0.2,
    )
    return completion.choices[0].message.content


def chat_with_eco_center(history, user_message: str) -> str:
    system_prompt = build_system_prompt(eco_data)
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})
    return call_llm(messages)


# -------------------------------
# 3. Streamlit 화면 구성
# -------------------------------
st.set_page_config(
    page_title="단체·해설 예약 신청",
    page_icon="🌿",
    layout="wide",
)

st.title("단체·해설 예약 신청")

# 화면을 좌/우로 나눔: 왼쪽 = 예약화면, 오른쪽 = 챗봇
left, right = st.columns([2.0, 1.0])


# ---- 왼쪽: 예약 화면 ----
with left:
    st.subheader("1. 방문일 / 프로그램 선택")

    # (1) 달력 영역
    today = date.today()
    selected_date = st.date_input("방문일을 선택해 주세요.", value=today)

    # JSON에서 해당 날짜에 가능한 프로그램/시간 찾기
    def find_slots_for_date(dt: date):
        target_str = dt.strftime("%Y-%m-%d")
        results = []
        for p in eco_data.get("programs", []):
            for slot in p.get("availableSlots", []):
                if slot["date"] == target_str:
                    remain = slot["capacity"] - slot["reserved"]
                    results.append({
                        "programId": p["programId"],
                        "programName": p["name"],
                        "target": p["target"],
                        "time": slot["time"],
                        "capacity": slot["capacity"],
                        "reserved": slot["reserved"],
                        "remain": remain,
                    })
        return results

    slots = find_slots_for_date(selected_date)

    if not slots:
        st.info("선택한 날짜에는 예약 가능한 프로그램이 없습니다.")
        selected_slot_key = None
    else:
        st.markdown("**해당 날짜의 예약 가능 프로그램/시간**")
        # 라디오 버튼으로 선택 (프로그램명 + 시간 + 잔여인원)
        options = []
        labels = []
        for idx, s in enumerate(slots):
            key = f"{s['programId']}|{s['time']}"
            label = (
                f"[{s['programName']}] {s['time']} / 대상: {s['target']} "
                f"/ 정원: {s['capacity']}명 / 잔여: {s['remain']}명"
            )
            options.append(key)
            labels.append(label)

        selected_slot_key = st.radio(
            "프로그램과 시간을 선택해 주세요.",
            options=options,
            format_func=lambda x: labels[options.index(x)],
            index=0,
        )

    st.markdown("---")
    st.subheader("2. 신청자 정보")

    # 신청자 정보 + 약관동의는 form 으로 감쌈
    with st.form("reservation_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            org_name = st.text_input("단체명", placeholder="예) ○○초등학교 3학년")
        with col2:
            contact = st.text_input("연락처", placeholder="010-0000-0000")
        with col3:
            people = st.number_input("참가 인원(명)", min_value=1, value=10, step=1)

        col4, col5 = st.columns(2)
        with col4:
            representative = st.text_input("담당자 이름")
        with col5:
            email = st.text_input("이메일 (선택)", placeholder="example@example.com")

        st.markdown("**유의사항 안내**")
        st.markdown(
            "- 신청 전, 프로그램 대상 및 소요시간을 반드시 확인해 주세요.\n"
            "- 예약 확정은 담당자 검토 후 별도 연락으로 안내드립니다.\n"
            "- 방문일 기준 1일 전까지 취소 가능합니다."
        )

        st.markdown("---")
        st.subheader("3. 약관 동의")

        with st.expander("이용약관 안내"):
            st.markdown(
                "여기에 자연생태관 이용약관, 개인정보 처리방침 등의 내용을 넣습니다.\n\n"
                "- 개인정보는 예약 확인 및 안내 목적으로만 사용됩니다.\n"
                "- 예약 변경/취소 규정 등..."
            )

        agree_terms = st.checkbox("위 내용을 모두 확인하였으며, 이용약관 및 개인정보 수집·이용에 동의합니다.")

        submitted = st.form_submit_button("신청하기")

        if submitted:
            if not selected_slot_key:
                st.error("방문일 및 프로그램/시간을 먼저 선택해 주세요.")
            elif not org_name or not contact or not representative:
                st.error("필수 신청자 정보를 모두 입력해 주세요.")
            elif not agree_terms:
                st.error("약관에 동의해야 신청이 가능합니다.")
            else:
                st.success(
                    f"임시 신청 완료!\n\n"
                    f"- 방문일: {selected_date.strftime('%Y-%m-%d')}\n"
                    f"- 선택 프로그램/시간: {selected_slot_key}\n"
                    f"- 단체명: {org_name}\n"
                    f"- 인원: {people}명\n\n"
                    f"※ 현재 버전은 데모로, 실제 DB 저장 및 확정은 이루어지지 않습니다."
                )


# ---- 오른쪽: AI 챗봇 ----
with right:
    st.subheader("AI 예약 상담 챗봇")

    # 대화 history 초기화
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [
            {
                "role": "assistant",
                "content": (
                    "안녕하세요, 자연생태관 AI 예약 상담 챗봇입니다.\n"
                    "방문 날짜, 인원, 대상(초등학생/중학생/성인) 등을 말씀해 주시면\n"
                    "어떤 프로그램이 적합한지 안내해 드릴게요. 😊"
                ),
            }
        ]

    # 기존 대화 출력
    for msg in st.session_state.chat_history:
        with st.chat_message("assistant" if msg["role"] == "assistant" else "user"):
            st.markdown(msg["content"])

    # 입력창
    prompt = st.chat_input("예약이나 프로그램에 대해 궁금한 점을 입력해 주세요.")

    if prompt:
        # 사용자 메시지 추가/보여주기
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.spinner("프로그램 정보를 확인하고 있습니다..."):
            reply = chat_with_eco_center(st.session_state.chat_history, prompt)

        st.session_state.chat_history.append({"role": "assistant", "content": reply})
        with st.chat_message("assistant"):
            st.markdown(reply)
