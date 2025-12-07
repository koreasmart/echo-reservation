import json
from pathlib import Path
from datetime import datetime, date
import calendar

import streamlit as st
from openai import OpenAI

# -------------------------------
# 0. OpenAI 설정
# -------------------------------
api_key = st.secrets["OPENAI_API_KEY"]
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
이 JSON 데이터만을 기준으로 대답해야 해. 대신 자연생태관 예약 혹은 자연생태관 프로그램과 관련있는 질문중 JSON 데이터에 없을 경우 대한민국에 있는 평균치의 자연생태관 기준으로 답해줘. 짧고 명확하고 친절하게 답해줘.
위의 제시한 관련된 데이터가 아닌 경우 엄격하게 모르는 정보는 "해당 정보는 제공되지 않습니다."라고 말해.


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
3. 사용자가 안내한 특정 프로그램과 시간을 선택하거나 혹은 직접 프로그램과 시간을 선택하면, "예약 정보를 폼에 자동으로 입력하시겠습니까?"라고 물어봐.
4. 사용자가 승인하면 다음 형식으로 정확히 답변해:
   [AUTO_FILL]
   DATE: YYYY-MM-DD
   PROGRAM: 프로그램명
   TIME: HH:MM-HH:MM
   [/AUTO_FILL]
5. 질문이 FAQ 내용과 관련 있으면, faq 항목을 참고해서 답해.
6. 자연생태관 예약 혹은 자연생태관 프로그램과 관련없는 질문을 할 경우, "저는 자연생태관 예약에 관한 질문에만 답변할 수 있습니다."라고 답해.
7. 프로그램에 관련된 설명이나 예약 절차를 설명할 때는, 사용자가 이해하기 쉽게 단계별로 차근차근 설명해.
8. 항상 한국어로, 친절하고 이해하기 쉽게 설명해.
"""
    return system_prompt

def call_llm(messages):
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
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

def parse_auto_fill(response: str):
    """챗봇 응답에서 [AUTO_FILL] 태그를 파싱"""
    if "[AUTO_FILL]" in response and "[/AUTO_FILL]" in response:
        start = response.find("[AUTO_FILL]") + len("[AUTO_FILL]")
        end = response.find("[/AUTO_FILL]")
        content = response[start:end].strip()
        
        data = {}
        for line in content.split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                data[key.strip()] = value.strip()
        return data
    return None

def find_slots_for_date(dt: date):
    """특정 날짜의 예약 가능한 프로그램 슬롯 찾기"""
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

# -------------------------------
# 3. Streamlit 화면 구성
# -------------------------------
st.set_page_config(
    page_title="단체 예약 예약 신청",
    page_icon="🌿",
    layout="wide",
)

# CSS 스타일
st.markdown("""
<style>
    .main-title {
        font-size: 24px;
        font-weight: bold;
        margin-bottom: 30px;
    }
    .section-title {
        font-size: 18px;
        font-weight: bold;
        margin-top: 30px;
        margin-bottom: 15px;
    }
    .calendar-container {
        background-color: #f8f9fa;
        padding: 20px;
        border-radius: 8px;
    }
    .chat-container {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 8px;
        border: 1px solid #e0e0e0;
        height: 600px;
        overflow-y: auto;
    }
    .stButton>button {
        background-color: #1e3a8a;
        color: white;
        width: 100%;
        padding: 10px;
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)

# Session state 초기화
if "chat_history" not in st.session_state:
    st.session_state.chat_history = [
        {
            "role": "assistant",
            "content": (
                "안녕하세요! 자연생태관 예약 상담 챗봇입니다. 🌿\n\n"
                "방문 날짜, 인원, 대상(초등학생/중학생/성인) 등을 말씀해 주시면\n"
                "적합한 프로그램을 안내해 드리겠습니다.\n\n"
                "예시: '9월 15일에 초등학생 30명이 방문하려고 합니다.'"
            ),
        }
    ]

if "auto_fill_data" not in st.session_state:
    st.session_state.auto_fill_data = None

if "current_year" not in st.session_state:
    st.session_state.current_year = 2025

if "current_month" not in st.session_state:
    st.session_state.current_month = 9

if "selected_date" not in st.session_state:
    st.session_state.selected_date = None

# 메인 타이틀
st.markdown('<div class="main-title">단체 예약 예약 신청</div>', unsafe_allow_html=True)

# 두 개의 컬럼으로 레이아웃 구성 (간격 추가)
col1, col2 = st.columns([1.5, 1], gap="large")

with col1:
    # 캘린더 섹션
    st.markdown("### 날짜 선택")
    
    # 월 네비게이션을 캘린더 위에 배치
    col_month_nav = st.columns([0.3, 2.4, 0.3])
    
    with col_month_nav[0]:
        if st.button("◀", key="prev_month", use_container_width=True):
            if st.session_state.current_month == 1:
                st.session_state.current_month = 12
                st.session_state.current_year -= 1
            else:
                st.session_state.current_month -= 1
            st.rerun()
    
    with col_month_nav[1]:
        st.markdown(f"<h3 style='text-align: center; margin: 0;'>{st.session_state.current_year}. {st.session_state.current_month:02d}</h3>", unsafe_allow_html=True)
    
    with col_month_nav[2]:
        if st.button("▶", key="next_month", use_container_width=True):
            if st.session_state.current_month == 12:
                st.session_state.current_month = 1
                st.session_state.current_year += 1
            else:
                st.session_state.current_month += 1
            st.rerun()
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # 간단한 캘린더 표시
    year = st.session_state.current_year
    month = st.session_state.current_month
    cal = calendar.monthcalendar(year, month)
    
    # 요일 헤더
    days = ['일', '월', '화', '수', '목', '금', '토']
    cols_header = st.columns(7)
    for i, day in enumerate(days):
        with cols_header[i]:
            st.markdown(f"<div style='text-align: center; color: {'red' if i==0 else 'black'};'>{day}</div>", unsafe_allow_html=True)
    
    # 캘린더 날짜
    available_dates = []
    for p in eco_data.get("programs", []):
        for slot in p.get("availableSlots", []):
            slot_date = datetime.strptime(slot["date"], "%Y-%m-%d")
            if slot_date.month == month and slot_date.year == year:
                available_dates.append(slot_date.day)
    
    available_dates = list(set(available_dates))
    
    for week in cal:
        cols = st.columns(7)
        for i, day in enumerate(week):
            with cols[i]:
                if day == 0:
                    st.write("")
                else:
                    # 선택된 날짜 확인
                    is_selected = (st.session_state.selected_date and 
                                   st.session_state.selected_date.year == year and 
                                   st.session_state.selected_date.month == month and 
                                   st.session_state.selected_date.day == day)
                    
                    if day in available_dates:
                        # 예약 가능한 날짜만 버튼으로 표시
                        if is_selected:
                            # 선택된 날짜
                            if st.button(f"🟡&ensp;&ensp;{day}", key=f"date_{year}_{month}_{day}", 
                                       use_container_width=True,
                                       type="primary"):
                                st.session_state.selected_date = date(year, month, day)
                                st.rerun()
                        else:
                            # 선택되지 않은 예약 가능 날짜
                            if st.button(f"🟡&ensp;&ensp;{day}", key=f"date_{year}_{month}_{day}", 
                                       use_container_width=True):
                                st.session_state.selected_date = date(year, month, day)
                                st.rerun()
                    else:
                        # 예약 불가능한 날짜는 텍스트로만 표시
                        st.markdown(f"<div style='text-align: center; padding: 8px; color: #ccc;'>{day}</div>", unsafe_allow_html=True)
    
    st.markdown("---")
    
    # 선택된 날짜 표시
    if st.session_state.selected_date:
        st.success(f"📅 선택된 날짜: {st.session_state.selected_date.strftime('%Y년 %m월 %d일')}")
    
    st.markdown("---")
    
    # 예약 폼 (날짜 선택 여부와 관계없이 항상 표시)
    with st.form("reservation_form"):
        st.markdown('<div class="section-title">신청자 정보</div>', unsafe_allow_html=True)
        
        # 자동 입력된 데이터 또는 선택된 날짜 사용
        form_date = st.session_state.selected_date
        
        if st.session_state.auto_fill_data:
            date_str = st.session_state.auto_fill_data.get("DATE")
            if date_str:
                form_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                st.session_state.selected_date = form_date
        
        if form_date:
            st.markdown(f"**선택된 방문일**: {form_date.strftime('%Y년 %m월 %d일')}")
        
        col_name, col_contact = st.columns(2)
        with col_name:
            org_name = st.text_input("단체명", placeholder="예) ○○초등학교 3학년")
        with col_contact:
            contact = st.text_input("연락처", placeholder="010-0000-0000")
        
        col_org, col_position = st.columns(2)
        with col_org:
            representative = st.text_input("담당자 이름", placeholder="담당자 성명")
        with col_position:
            email = st.text_input("이메일", placeholder="example@example.com")
        
        # 프로그램 선택
        st.markdown("**프로그램 선택**")
        
        # 선택된 날짜가 있을 때만 프로그램 로드
        if form_date:
            slots = find_slots_for_date(form_date)
        else:
            slots = []
        
        if slots:
            options = []
            labels = []
            selected_index = 0
            
            for idx, s in enumerate(slots):
                key = f"{s['programName']}|{s['time']}"
                label = f"[{s['programName']}] {s['time']} (잔여: {s['remain']}명)"
                options.append(key)
                labels.append(label)
                
                # 자동 입력 데이터와 일치하는지 확인
                if st.session_state.auto_fill_data:
                    auto_program = st.session_state.auto_fill_data.get("PROGRAM")
                    auto_time = st.session_state.auto_fill_data.get("TIME")
                    if auto_program and auto_time:
                        if s['programName'] == auto_program and s['time'] == auto_time:
                            selected_index = idx
            
            selected_program = st.selectbox(
                "프로그램 및 시간",
                options=options,
                format_func=lambda x: labels[options.index(x)],
                index=selected_index
            )
        else:
            if form_date:
                st.info("선택한 날짜에 예약 가능한 프로그램이 없습니다.")
            else:
                st.info("날짜를 선택하면 예약 가능한 프로그램이 표시됩니다.")
            selected_program = None
        
        # 인원 선택
        st.markdown("**참가 인원**")
        people = st.number_input("인원 (명)", min_value=1, value=10, step=1)
        
        st.markdown("---")
        
        # 약관 동의
        st.markdown('<div class="section-title">약관 동의</div>', unsafe_allow_html=True)
        
        with st.expander("이용약관 안내"):
            st.markdown(
                "**개인정보 수집 및 이용 안내**\n\n"
                "- 개인정보는 예약 확인 및 안내 목적으로만 사용됩니다.\n"
                "- 수집항목: 단체명, 연락처, 담당자명, 이메일\n"
                "- 보유기간: 예약 종료 후 6개월\n\n"
                "**예약 변경 및 취소 규정**\n\n"
                "- 방문일 기준 1일 전까지 취소 가능합니다.\n"
                "- 당일 취소는 불가능하며, 노쇼 시 향후 예약이 제한될 수 있습니다."
            )
        
        agree_terms = st.checkbox("위 내용을 모두 확인하였으며, 이용약관 및 개인정보 수집·이용에 동의합니다.")
        
        submitted = st.form_submit_button("신청하기", use_container_width=True)
        
        if submitted:
            if not form_date:
                st.error("캘린더에서 날짜를 먼저 선택해 주세요.")
            elif not selected_program:
                st.error("프로그램을 선택해 주세요.")
            elif not org_name or not contact or not representative:
                st.error("필수 신청자 정보를 모두 입력해 주세요.")
            elif not agree_terms:
                st.error("약관에 동의해야 신청이 가능합니다.")
            else:
                st.success(
                    f"✅ 예약 신청이 완료되었습니다!\n\n"
                    f"**예약 정보**\n"
                    f"- 방문일: {form_date.strftime('%Y년 %m월 %d일')}\n"
                    f"- 프로그램: {selected_program}\n"
                    f"- 단체명: {org_name}\n"
                    f"- 인원: {people}명\n"
                    f"- 담당자: {representative}\n\n"
                    f"※ 예약 확정은 담당자 검토 후 연락드리겠습니다."
                )
                # 자동 입력 데이터 및 선택된 날짜 초기화
                st.session_state.auto_fill_data = None
                st.session_state.selected_date = None

with col2:
    st.markdown('<div class="section-title">AI 예약 상담 챗봇 🤖</div>', unsafe_allow_html=True)
    
    # 챗봇 컨테이너
    chat_container = st.container()
    
    with chat_container:
        # 기존 대화 출력
        for msg in st.session_state.chat_history:
            with st.chat_message("assistant" if msg["role"] == "assistant" else "user"):
                st.markdown(msg["content"])
    
    # 입력창
    prompt = st.chat_input("예약이나 프로그램에 대해 궁금한 점을 입력해 주세요.")
    
    if prompt:
        # 사용자 메시지 추가
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        
        with st.spinner("답변을 생성하고 있습니다..."):
            reply = chat_with_eco_center(st.session_state.chat_history, prompt)
        
        # 자동 입력 데이터 파싱
        auto_fill = parse_auto_fill(reply)
        if auto_fill:
            st.session_state.auto_fill_data = auto_fill
            # [AUTO_FILL] 태그 제거한 깨끗한 메시지
            clean_reply = reply.split("[AUTO_FILL]")[0].strip()
            st.session_state.chat_history.append({"role": "assistant", "content": clean_reply + "\n\n✅ 예약 정보가 왼쪽 폼에 자동으로 입력되었습니다!"})
        else:
            st.session_state.chat_history.append({"role": "assistant", "content": reply})
        
        st.rerun()
    
    # 대화 초기화 버튼
    if st.button("대화 초기화", use_container_width=True):
        st.session_state.chat_history = [
            {
                "role": "assistant",
                "content": (
                    "안녕하세요! 자연생태관 예약 상담 챗봇입니다. 🌿\n\n"
                    "방문 날짜, 인원, 대상(초등학생/중학생/성인) 등을 말씀해 주시면\n"
                    "적합한 프로그램을 안내해 드리겠습니다.\n\n"
                    "예시: '9월 15일에 초등학생 30명이 방문하려고 합니다.'"
                ),
            }
        ]
        st.session_state.auto_fill_data = None
        st.rerun()

# 하단 안내 문구
st.markdown("---")
st.info("💡 AI 챗봇을 통해 프로그램을 추천받고, 자동으로 예약 정보를 입력받을 수 있습니다.")
st.caption("문의: 자연생태관 고객센터 02-1234-5678")