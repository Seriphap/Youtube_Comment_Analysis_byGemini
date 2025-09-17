# app.py
import streamlit as st
import pandas as pd
import re
from datetime import datetime
from comment_fetcher import get_all_comments
from google import genai

# -----------------------------
# 🤖 Gemini Client
# -----------------------------

YOUTUBE_API_KEY = st.secrets["YOUTUBE_API_KEY"]
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
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


[ภาษาเอาต์พุต]
- ตอบเป็นภาษาเดียวกับคำถามของผู้ใช้
- ถ้าคำถามเป็นภาษาอังกฤษ ให้ตอบเป็นภาษาอังกฤษ
- ถ้าคำถามเป็นภาษาไทย ให้ตอบเป็นภาษาไทย
- ห้ามผสมภาษาในคำอธิบาย (ยกเว้นตัวอย่างคอมเมนต์ซึ่งให้คงภาษาต้นฉบับได้)

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
st.subheader("Input a YouTube Video ID or URL")
video_input = st.text_input(
    "Input YouTube Video ID or URL (Single Video)",
    placeholder="Example: https://youtu.be/OMV9F9zB4KU or OMV9F9zB4KU"
)

video_id = extract_single_video_id(video_input) if video_input else None

# แสดงตัวอย่างวิดีโอ
if video_id:
    st.subheader("▶️ Video Reference")
    Col1, Col2 = st.columns(2)
    with Col1:
        st.video(f"https://www.youtube.com/watch?v={video_id}")
    st.caption(f"Video — `{video_id}`")

# -----------------------------
# 📥 Fetch Comments (Always fresh)
# -----------------------------
fetch_btn = st.button("🔄 Retrieve the Latest YouTube Comments")

if fetch_btn:
    if not video_id:
        st.warning("please correct Video ID/URL before retrieve the youtube comments")
        st.stop()

    with st.spinner("⏳ loading all comments from YouTube..."):
        try:
            df = get_all_comments(
                video_id,
                YOUTUBE_API_KEY,
                include_replies=False,
                order="time",
                save_to_csv=False
            )

            if df is None or df.empty:
                st.error("No comment or The video is not allowed to comments")
                st.stop()

            # เก็บใน session
            st.session_state.latest_df = df
            st.session_state.latest_video_id = video_id

            # เก็บ timestamp ไว้เพื่อให้ชื่อไฟล์คงที่ข้ามการ rerun
            st.session_state.latest_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

            st.success(f"✅ Data successfully retrieved: {len(df)} comments from video {video_id}")

        except Exception as e:
            st.error(f"❌ An error occurred while retrieving the comments.: {e}")
            st.stop()

# -----------------------------
# แสดงตัวอย่าง + ปุ่มดาวน์โหลด (อยู่นอก fetch_btn)
# -----------------------------
df = st.session_state.get("latest_df")
if df is not None and not df.empty:

    # สรุปข้อมูลเบื้องต้น / ตัวอย่างข้อมูล
    with st.expander("🔎 All Comments"):
        st.dataframe(df, use_container_width=True)

    # ปุ่มดาวน์โหลด CSV (อยู่ตรงนี้เพื่อไม่หายเวลา rerun)
    csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
    ts = st.session_state.get("latest_ts") or datetime.now().strftime("%Y%m%d_%H%M%S")
    vid = st.session_state.get("latest_video_id", "unknown")
    st.download_button(
        "⬇️ Download CSV",
        data=csv_bytes,
        file_name=f"youtube_comments_{vid}_{ts}.csv",
        mime="text/csv",
        key="download_csv"  # ให้ key คงที่ ป้องกันชนกับปุ่มอื่น ๆ
    )

    # -----------------------------
    # 🤖 Ask AI (Gemini)
    # -----------------------------
    st.subheader("🕵️‍♂️ Ask AI")

    st.markdown("💡 **Suggested Questions**")
    suggestions = {
        "📈 ผู้ชมรู้สึกอย่างไร? (Sentiment)": "วิเคราะห์ว่าโดยรวมผู้ชมรู้สึกอย่างไรกับวิดีโอนี้ (positive / negative / neutral) พร้อมยกตัวอย่างข้อความสนับสนุน",
        "💬 คนพูดถึงอะไรบ่อยที่สุด?": "จากความคิดเห็นทั้งหมด ผู้ชมพูดถึงประเด็นใดบ่อยที่สุดในเชิงบวกหรือลบ",
        "🎯 ข้อเสนอแนะ / คำวิจารณ์": "สรุปข้อเสนอแนะหรือคำวิจารณ์จากผู้ชมเกี่ยวกับวิดีโอนี้",
        "📈 How do viewers feel? (Sentiment)": "Analyze the overall sentiment of the viewers toward the video (positive / negative / neutral), and provide example comments to support the conclusion.",
        "💬 What do people talk about the most?": "From all the comments, identify the most frequently mentioned topic—whether in a positive or negative light.",
        "🎯 Suggestions / Criticisms": "Summarize viewer suggestions or criticisms regarding the video.",
        "🤔💭 Your other questions": "",
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
        placeholder="Example: What are people saying about?"
    )

    if st.button("🚀 Analysis by Gemini AI"):
        if not question.strip():
            st.warning("please select or input your question")
            st.stop()

        with st.spinner("🔍 AI Analyzing..."):
            try:
                answer = ask_gemini(question.strip(), df)
                st.success("✅ Analysis completed successfullyใ")
                st.subheader("📊 Answer from Gemini:")
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
                st.error(f"❌ An error occurred from Gemini: {e}")
