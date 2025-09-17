
# YouTube Comment Analysis by Gemini

This project leverages AI (Gemini) to analyze YouTube comments. Users can interactively explore sentiment, trends, and insights from large sets of YouTube comment data using a user-friendly Streamlit web application.

---
# Streamlit App
https://youtubecommentanalysisbygemini-snz9izdcrkujhqv3lbskds.streamlit.app/


## Topic

**YouTube Comment Analysis**  
The main objective of this project is to analyze YouTube comments to extract valuable insights such as sentiment, common topics, and user engagement patterns. This helps content creators, marketers, and researchers better understand their audience and improve content strategies.

---
- Input YouTube URL or ID.
- Select question or ask your question.
- Wait a moment for answer from Gemeni.

**How to Run the App Locally:**
```bash
pip install -r requirements.txt
streamlit run app.py
```

---

## Project Structure
```
├── app.py                  # Main Streamlit app entry point
├── comment_fetcher.py      # Import dataset from comment on youtube
└── .streamlit/
    └── secrets.toml
```

---

## Dataset

The primary dataset used in this project contains real YouTube comments and basic metadata.

---

## Features

- **Sentiment Analysis:** Classifies comments as Positive, Neutral, or Negative.
- **Keyword Extraction:** Identifies trending words and topics using word clouds.
- **Engagement Statistics:** Visualizes likes, replies, and other engagement metrics.
- **Filtering & Search:** Filter comments by sentiment, date, or keywords.
- **Interactive Visualizations:** Real-time charts (bar, pie, line, word cloud) for deeper insights.

---

Feel free to contribute or customize the project for your own analysis needs!
