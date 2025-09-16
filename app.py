# app.py
import streamlit as st
import pandas as pd
import re
from datetime import datetime
from comment_fetcher import get_all_comments
from google import genai

# -----------------------------
# 🔐 Load API keys from secrets
# -----------------------------
# เพิ่มใน .streamlit/secrets.toml:
# YOUTUBE_API_KEY = "YOUR_YOUTUBE_API_KEY"
# GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"
YOUTUBE_API_KEY = secrets["YOUTUBE_API_KEY"]
GEMINI_API_KEY = secrets["GEMINI_API_KEY"]

# -----------------------------
# 🤖 Gemini Client
# -----------------------------
client = genai.Client(api_key=GEMINI_API_KEY)

# -----------------------------
# 🧩 Helper Functions
# -----------------------------
VIDEO_ID_RE = re.compile(r'^[A-Za-z0-9_-]{11}$')

def extract_single_video_id(raw_text: str) -> str | None:
    """
    รองรับการกรอกทั้ง Video ID ตรง ๆ หรือ URL (watch?v=, youtu.be, shorts, embed)
    คืนค่า video_id (ยาว 11 ตัว) หรือ None ถ้าไม่พบ
    """
    if not raw_text:
        return None

    text = raw_text.strip()

    # ถ้าเป็น video id ตรงๆ
    if len(text) == 11 and VIDEO_ID_RE.fullmatch(text):
        return text

    # หาใน URL รูปแบบต่าง ๆ
    patterns = [
        r'(?:v=)([A-Za-z0-9_-]{11})',              # ...watch?v=VIDEOID
        r'youtu\.be/([A-Za-z0-9_-]{11})',          # youtu.be/VIDEOID
        r'youtube\.com/embed/([A-Za-z0-9_-]{11})', # .../embed/VIDEOID
        r'youtube\.com/shorts/([A-Za-z0-9_-]{11})' # .../shorts/VIDEOID
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return m.group(1)

    return None


def build_prompt(question: str, df: pd.DataFrame, max_chars: int = 30000) -> str:
    """
    สร้างพรอมพ์ให้ Gemini:
    - ใช้คอลัมน์ 'comment' เป็นหลัก
    - จำกัดความยาวเพื่อความเสถียร
    """
    if "comment" in df.columns:
        comments_series = df["comment"].astype(str)
    else:
        # fallback: ใช้คอลัมน์อื่น ๆ ที่ดูสื่อความหมายใกล้เคียง
        candidate_cols = [c for c in df.columns if c.lower() in ("text", "content", "message")]
        if candidate_cols:
            comments_series = df[candidate_cols[0]].astype(str)
        else:
            comments_series = df.astype(str).agg(" ".join, axis=1)

    comments_text = "\n".join(comments_series.tolist())
    truncated = False
    if len(comments_text) > max_chars:
        comments_text = comments_text[:max_chars]
        truncated = True

    prompt = f"""
คุณคือผู้ช่วยวิเคราะห์ความเห็นของผู้ชม YouTube ในเชิงคุณภาพและปริมาณอย่างกระชับและมีโครงสร้าง

[คำถามของผู้ใช้]
{question}

[ข้อมูลความคิดเห็นจากผู้ชม]
{comments_text}

[แนวทางการสรุป]
1) ตอบตรงคำถาม พร้อม bullet แบ่งหัวข้อชัดเจน
2) ยกตัวอย่างคอมเมนต์ที่สนับสนุนข้อสรุป (ย่อและนิรนาม)
3) ถ้าพบทั้งบวก/ลบ/กลาง ให้บอกร้อยละโดยประมาณ
4) ถ้ามีข้อเสนอแนะ actionable item ให้เรียงลำดับความสำคัญ (1-3)
    """.strip()

    if truncated:
        prompt += "\n\n[หมายเหตุ] เพื่อความเสถียร ได้ตัดข้อความความคิดเห็นให้พอดีกับขีดจำกัดของโมเดล"
    return prompt


def ask_gemini(question: str, df: pd.DataFrame) -> str:
    prompt = build_prompt(question, df)
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt
    )
    return response.text


# -----------------------------
# 🧭 Page Config & Header
# -----------------------------
st.set_page_config(
    page_title="YouTube Comment Analysis — Single Video (Gemini 2.0 Flash)",
    page_icon="🤖",
    layout="wide"
)
st.header("🕵️‍♂️ Analysis of YouTube Comments Using Gemini-2.0-Flash")

# -----------------------------
# 📚 Sidebar — Q&A History
# -----------------------------
with st.sidebar:
    st.subheader("📜 Conversations History")
    if st.session_state.get("qa_history"):
        for i, item in enumerate(reversed(st.session_state.qa_history[-5:]), 1):
            st.markdown(f"**{i}. คำถาม:** {item['question']}")
            st.markdown(f"✍️ คำตอบ: {item['answer'][:150]}...")
            st.markdown("---")
        if st.button("🗑️ Clear Conversations History"):
            st.session_state.qa_history = []
            st.info("Cleared.")
    else:
        st.info("No Conversations History")

# -----------------------------
# 🎯 Single Video Input
# -----------------------------
st.subheader("🧩 Input a YouTube Video ID or URL (Single)")
video_input = st.text_input(
    "ระบุ YouTube Video ID หรือ URL (1 รายการ)",
    placeholder="เช่น https://youtu.be/OMV9F9zB4KU หรือ OMV9F9zB4KU"
)

video_id = extract_single_video_id(video_input) if video_input else None

# แสดงตัวอย่างวิดีโอ
if video_id:
    st.subheader("▶️ Video Reference")
    st.video(f"https://www.youtube.com/watch?v={video_id}")
    st.caption(f"Video — `{video_id}`")

# -----------------------------
# 📥 Fetch Comments (Always fresh)
# -----------------------------
fetch_btn = st.button("🔄 Retrieve the Latest YouTube Comments", type="primary")

if fetch_btn:
    if not video_id:
        st.warning("กรุณาใส่ Video ID/URL ให้ถูกต้องก่อนดึงความคิดเห็น")
        st.stop()

    with st.spinner("⏳ กำลังดึงความคิดเห็นทั้งหมดจาก YouTube..."):
        try:
            # ดึงเฉพาะ top-level comments เรียงจาก "ล่าสุด"
            df = get_all_comments(
                video_id,
                YOUTUBE_API_KEY,
                include_replies=False,  # ปรับเป็น True ได้ถ้าต้องการ replies ด้วย
                order="time",           # "time" = ล่าสุดก่อน, "relevance" = ความเกี่ยวข้อง
                save_to_csv=False
            )

            if df is None or df.empty:
                st.error("ไม่พบความคิดเห็น หรือวิดีโอนี้อาจปิดการแสดงความคิดเห็น")
                st.stop()

            # เก็บใน session สำหรับใช้ถาม AI ต่อ
            st.session_state.latest_df = df
            st.session_state.latest_video_id = video_id

            st.success(f"✅ ดึงข้อมูลสำเร็จ: {len(df)} ความคิดเห็น จากวิดีโอ {video_id}")

            # สรุปข้อมูลเบื้องต้น / ตัวอย่างข้อมูล
            with st.expander("🔎 ตัวอย่างข้อมูล"):
                st.dataframe(df.head, use_container_width=True)

            # ปุ่มดาวน์โหลด CSV
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "⬇️ Download CSV",
                data=csv_bytes,
                file_name=f"youtube_comments_{video_id}_{ts}.csv",
                mime="text/csv"
            )

        except Exception as e:
            st.error(f"❌ เกิดข้อผิดพลาดในการดึงความคิดเห็น: {e}")
            st.stop()

# -----------------------------
# 🤖 Ask AI (Gemini)
# -----------------------------
df = st.session_state.get("latest_df")
if df is not None and not df.empty:
    st.subheader("🤖 Ask AI")

    # Suggested Questions
    st.markdown("💡 **Suggested Questions**")
    suggestions = {
        "📈 ผู้ชมรู้สึกอย่างไร? (Sentiment)": "วิเคราะห์ว่าโดยรวมผู้ชมรู้สึกอย่างไรกับวิดีโอนี้ (positive / negative / neutral) พร้อมยกตัวอย่างข้อความสนับสนุน",
        "💬 คนพูดถึงอะไรบ่อยที่สุด?": "จากความคิดเห็นทั้งหมด ผู้ชมพูดถึงประเด็นใดบ่อยที่สุดในเชิงบวกหรือลบ",
        "🎯 ข้อเสนอแนะ / คำวิจารณ์": "สรุปข้อเสนอแนะหรือคำวิจารณ์จากผู้ชมเกี่ยวกับวิดีโอนี้",
    }

    if "selected_prompt" not in st.session_state:
        st.session_state.selected_prompt = ""

    cols = st.columns(len(suggestions))
    for i, (label, prompt_text) in enumerate(suggestions.items()):
        if cols[i].button(label):
            st.session_state.selected_prompt = prompt_text

    question = st.text_area(
        "💬 Your Question",
        value=st.session_state.selected_prompt,
        placeholder="Example: What are people saying about BYD ?"
    )

    if st.button("🚀 วิเคราะห์ด้วย Gemini AI"):
        if not question.strip():
            st.warning("กรุณาพิมพ์คำถามก่อน")
            st.stop()

        with st.spinner("🔍 AI กำลังวิเคราะห์..."):
            try:
                answer = ask_gemini(question.strip(), df)
                st.success("✅ วิเคราะห์สำเร็จ")
                st.subheader("📊 คำตอบจาก Gemini:")
                st.write(answer)

                # Save history
                if "qa_history" not in st.session_state:
                    st.session_state.qa_history = []
                st.session_state.qa_history.append({
                    "question": question.strip(),
                    "answer": answer
                })

                # Clear selected suggestion
                st.session_state.selected_prompt = ""

            except Exception as e:
                st.error(f"❌ เกิดข้อผิดพลาดจาก Gemini: {e}")
