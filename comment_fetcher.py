# comment_fetcher.py
import requests
import pandas as pd
import time
from typing import Optional, Callable, List, Dict, Union

API_BASE = "https://www.googleapis.com/youtube/v3"

def get_video_title(
    video_id: str,
    api_key: str,
    session: Optional[requests.Session] = None,
    timeout: int = 15
) -> str:
    """ดึงชื่อวิดีโอแบบปลอดภัย"""
    sess = session or requests.Session()
    params = {"part": "snippet", "id": video_id, "key": api_key}
    try:
        r = sess.get(f"{API_BASE}/videos", params=params, timeout=timeout)
        r.raise_for_status()
        items = r.json().get("items", [])
        return items[0]["snippet"]["title"] if items else "Unknown Title"
    except Exception:
        return "Unknown Title"


def _fetch_top_level_comments(
    video_id: str,
    api_key: str,
    session: Optional[requests.Session] = None,
    timeout: int = 15,
    order: str = "relevance",   # "time" เพื่อเรียงล่าสุดก่อน
    progress_cb: Optional[Callable[[int], None]] = None,
    max_pages: Optional[int] = None
) -> List[Dict]:
    """ดึง top-level comments ทั้งหมด (แบ่งหน้า)"""
    sess = session or requests.Session()
    url = f"{API_BASE}/commentThreads"
    params = {
        "part": "snippet",
        "videoId": video_id,
        "key": api_key,
        "maxResults": 100,
        "textFormat": "plainText",
        "order": order
    }

    results: List[Dict] = []
    page = 0
    next_token: Optional[str] = None

    while True:
        if max_pages is not None and page >= max_pages:
            break
        if next_token:
            params["pageToken"] = next_token
        else:
            params.pop("pageToken", None)

        try:
            resp = sess.get(url, params=params, timeout=timeout)
            # จัดการ quota / rate limit แบบง่าย ๆ
            if resp.status_code in (403, 429, 503):
                # รอและลองใหม่แบบ backoff ขั้นพื้นฐาน
                time.sleep(2)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            # หยุดลูปเมื่อเกิด error ร้ายแรง
            break

        items = data.get("items", [])
        if not items:
            # ถ้าไม่มี items และไม่มี nextToken ก็จบ
            next_token = data.get("nextPageToken")
            if not next_token:
                break

        for item in items:
            tlc = item["snippet"]["topLevelComment"]
            s = tlc["snippet"]
            results.append({
                "video_id": video_id,
                "comment_id": tlc.get("id"),
                "parent_id": None,
                "is_reply": False,
                "video_title": "",  # จะเติมทีหลัง
                "author": s.get("authorDisplayName"),
                "author_channel_id": (s.get("authorChannelId") or {}).get("value"),
                "comment": s.get("textDisplay") or s.get("textOriginal"),
                "like_count": s.get("likeCount"),
                "published_at": s.get("publishedAt"),
                "updated_at": s.get("updatedAt"),
                "total_reply_count": item["snippet"].get("totalReplyCount", 0)
            })

        page += 1
        if progress_cb:
            progress_cb(len(results))

        next_token = data.get("nextPageToken")
        if not next_token:
            break

    return results


def _fetch_replies_for_parents(
    parent_ids: List[str],
    api_key: str,
    session: Optional[requests.Session] = None,
    timeout: int = 15
) -> List[Dict]:
    """ดึง replies ให้ครบทุก parent id"""
    if not parent_ids:
        return []

    sess = session or requests.Session()
    url = f"{API_BASE}/comments"
    params = {
        "part": "snippet",
        "textFormat": "plainText",
        "maxResults": 100,
        "key": api_key,
    }

    all_replies: List[Dict] = []
    for pid in parent_ids:
        params["parentId"] = pid
        next_token: Optional[str] = None

        while True:
            if next_token:
                params["pageToken"] = next_token
            else:
                params.pop("pageToken", None)

            resp = sess.get(url, params=params, timeout=timeout)
            if resp.status_code in (403, 429, 503):
                time.sleep(2)
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("items", []):
                s = item["snippet"]
                all_replies.append({
                    "video_id": s.get("videoId"),
                    "comment_id": item.get("id"),
                    "parent_id": pid,
                    "is_reply": True,
                    "video_title": "",  # จะเติมทีหลัง
                    "author": s.get("authorDisplayName"),
                    "author_channel_id": (s.get("authorChannelId") or {}).get("value"),
                    "comment": s.get("textDisplay") or s.get("textOriginal"),
                    "like_count": s.get("likeCount"),
                    "published_at": s.get("publishedAt"),
                    "updated_at": s.get("updatedAt"),
                    "total_reply_count": None
                })

            next_token = data.get("nextPageToken")
            if not next_token:
                break

    return all_replies


def get_all_comments(
    video_ids: Union[str, List[str]],
    api_key: str,
    *,
    include_replies: bool = False,
    order: str = "relevance",        # ใช้ "time" ถ้าต้องการเรียงใหม่ล่าสุด
    save_to_csv: bool = False,
    csv_path: str = "youtube_comments.csv",
    timeout: int = 15,
    progress_cb: Optional[Callable[[int], None]] = None,
    max_pages: Optional[int] = None
) -> pd.DataFrame:
    """
    ดึงคอมเมนต์จาก YouTube:
    - รองรับ video_id เดี่ยว (str) หรือหลายตัว (list[str])
    - include_replies=True เพื่อดึง replies ทั้งหมด
    - order="time" เพื่อเรียงคอมเมนต์ใหม่ล่าสุดก่อน
    - save_to_csv=True เพื่อบันทึกไฟล์ CSV (ค่าเริ่มต้น False)
    """
    # รองรับทั้ง str และ list
    if isinstance(video_ids, str):
        video_ids = [video_ids]

    # กรอง id ที่ไม่น่าจะถูกต้อง (11 ตัวอักษร)
    video_ids = [vid.strip() for vid in video_ids if vid and len(vid.strip()) == 11]

    session = requests.Session()
    all_rows: List[Dict] = []

    for vid in video_ids:
        title = get_video_title(vid, api_key, session=session, timeout=timeout)

        top = _fetch_top_level_comments(
            vid, api_key,
            session=session,
            timeout=timeout,
            order=order,
            progress_cb=progress_cb,
            max_pages=max_pages
        )

        # ใส่ title ให้ทุกรายการ
        for r in top:
            r["video_title"] = title

        rows = top

        if include_replies:
            parent_ids = [r["comment_id"] for r in top if r.get("comment_id")]
            reps = _fetch_replies_for_parents(parent_ids, api_key, session=session, timeout=timeout)
            for r in reps:
                r["video_title"] = title
            rows.extend(reps)

        all_rows.extend(rows)

    df = pd.DataFrame(all_rows)

    if save_to_csv:
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    return df
