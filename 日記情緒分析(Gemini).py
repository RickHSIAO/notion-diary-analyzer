"""
日記情緒分析系統
讀取 Notion 日記（Toggle 格式），透過 Google Gemini API 分析情緒，給予分數與評語
"""

import os
import sys
import json
import re
from datetime import datetime, date
from dotenv import load_dotenv

# 確保 Windows 終端機正確輸出 UTF-8 與 emoji
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from google import genai
from google.genai import types
import requests

# 載入 .env 檔案
load_dotenv()


# ── 設定區 ──────────────────────────────────────────────
NOTION_API_KEY  = os.environ.get("NOTION_API_KEY", "")
NOTION_PAGE_ID  = os.environ.get("NOTION_DATABASE_ID", "")  # 日記主頁面 ID
GOOGLE_GEMINI_API_KEY = os.environ.get("GOOGLE_GEMINI_API_KEY", "")

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}



# ── 情緒等級對照 ────────────────────────────────────────
def get_level_message(score: float) -> str:
    if score >= 8:
        return "🌟 完美的一天 Perfect！今天真的很棒，繼續保持這份美好！"
    elif score >= 5:
        return "😊 今天還不錯，但還能更好！每一天都是進步的機會。"
    elif score >= 3:
        return "🌱 人生不是一帆風順，但要保持好心情！低潮只是暫時的。"
    else:
        return "💙 今天聽起來非常糟糕，要不要做其他事情來轉換心情？散步、聽音樂、或是找朋友聊聊都是好選擇。"


# ── Notion：從 Toggle 格式頁面讀取日記 ─────────────────
def extract_date_from_rich_text(rich_texts: list) -> date | None:
    """從 rich_text 陣列中提取日期 mention"""
    for rt in rich_texts:
        if rt.get("type") == "mention":
            mention = rt.get("mention", {})
            if mention.get("type") == "date":
                date_str = mention.get("date", {}).get("start", "")
                if date_str:
                    try:
                        return date.fromisoformat(date_str[:10])
                    except ValueError:
                        pass
    return None


def fetch_block_text(block_id: str) -> str:
    """遞迴讀取區塊及其子區塊的所有文字"""
    blocks_url = f"https://api.notion.com/v1/blocks/{block_id}/children"
    resp = requests.get(blocks_url, headers=NOTION_HEADERS, timeout=15)
    resp.raise_for_status()

    blocks = resp.json().get("results", [])
    texts = []

    for block in blocks:
        btype = block.get("type", "")
        rich = block.get(btype, {}).get("rich_text", [])
        for rt in rich:
            plain = rt.get("plain_text", "").strip()
            if plain:
                texts.append(plain)
        # 若有子區塊（如巢狀 toggle），也一並讀取
        if block.get("has_children"):
            child_text = fetch_block_text(block["id"])
            if child_text:
                texts.append(child_text)

    return "\n".join(texts)


def fetch_today_diary() -> tuple[str, str]:
    """
    從 Notion 日記主頁面讀取今天（或最新）的日記內容
    支援 heading_1 與 toggle 兩種格式，回傳 (日記文字, 日期標題)
    """
    if not NOTION_API_KEY or not NOTION_PAGE_ID:
        raise ValueError("請設定 NOTION_API_KEY 與 NOTION_DATABASE_ID 環境變數")

    # 讀取日記主頁面的所有區塊
    blocks_url = f"https://api.notion.com/v1/blocks/{NOTION_PAGE_ID}/children"
    resp = requests.get(blocks_url, headers=NOTION_HEADERS, timeout=15)
    resp.raise_for_status()
    blocks = resp.json().get("results", [])

    today = date.today()
    best_block = None
    best_date = None
    best_title = ""

    for block in blocks:
        btype = block.get("type")
        if btype not in ("toggle", "heading_1", "heading_2", "heading_3"):
            continue
        if not block.get("has_children"):
            continue

        rich_texts = block.get(btype, {}).get("rich_text", [])
        title = "".join(rt.get("plain_text", "") for rt in rich_texts).strip()

        # 先嘗試從 rich_text mention 取日期，再嘗試從標題開頭的 YYYY-MM-DD 取
        block_date = extract_date_from_rich_text(rich_texts)
        if not block_date and len(title) >= 10:
            try:
                block_date = date.fromisoformat(title[:10])
            except ValueError:
                pass

        if block_date:
            if block_date == today:
                return fetch_block_text(block["id"]), title
            elif best_date is None or block_date > best_date:
                best_date = block_date
                best_block = block
                best_title = title
        elif best_block is None:
            best_block = block
            best_title = title

    if best_block:
        return fetch_block_text(best_block["id"]), best_title

    return "", ""


# ── Gemini：情緒分析 ────────────────────────────────────
def analyze_emotion(diary_text: str) -> dict:
    """呼叫 Google Gemini API 分析日記情緒，回傳 score 與 comment"""
    if not GOOGLE_GEMINI_API_KEY:
        raise ValueError("請設定 GOOGLE_GEMINI_API_KEY 環境變數")

    client = genai.Client(api_key=GOOGLE_GEMINI_API_KEY)

    system_prompt = """你是一位溫暖、有同理心的情緒分析師，專門分析日記的情緒狀態。

你的任務：
1. 仔細閱讀日記內容
2. 分析整體情緒狀態（正向/負向的事件、用詞、語氣）
3. 給予 0～10 分的情緒分數（0 = 極度負面，10 = 極度正面）
4. 寫一段 2～4 句的中文評語，溫暖且具體地回應日記內容

請務必以 JSON 格式回應，格式如下：
{
  "score": <數字，0-10，可以有小數點如 7.5>,
  "comment": "<評語文字>"
}

評分標準：
- 8~10：充滿正能量、開心、有成就感、感恩
- 5~8 ：普通至不錯，有小確幸但也有小煩惱
- 3~5 ：有壓力、疲憊、挫折，但還能撐過去
- 0~3 ：非常低落、悲傷、憤怒、或發生很糟糕的事
"""

    # 依序嘗試，若配額耗盡則自動換下一個模型（優先用最新、品質最佳的模型）
    models_to_try = [
        "gemini-2.5-flash",       # 最佳品質，5 RPM / 250K TPM / 20 RPD
        "gemini-3.1-flash-lite",  # 最高 RPM，15 RPM / 250K TPM / 500 RPD
        "gemini-3.0-flash",       # 5 RPM / 250K TPM / 20 RPD
        "gemini-2.5-flash-lite",  # 10 RPM / 250K TPM / 20 RPD
        "gemini-2.0-flash",       # 上一代，0 RPM（付費帳戶用）
        "gemini-2.0-flash-lite",  # 上一代輕量版
    ]
    last_error = None

    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=f"\n請分析以下日記內容：\n\n{diary_text}",
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                ),
            )
            response_text = response.text
            break
        except Exception as e:
            err_str = str(e)
            if any(k in err_str for k in ("429", "RESOURCE_EXHAUSTED", "quota", "503", "UNAVAILABLE")):
                reason = "配額已用盡" if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str else "暫時無法使用（伺服器繁忙）"
                print(f"⚠️  {model_name} {reason}，嘗試下一個模型...")
                last_error = e
                continue
            raise
    else:
        print("\n❌ 所有可用模型皆暫時無法使用：")
        print("   • 免費配額可能已於今日用盡（每日重置）")
        print("   • 或 Google 伺服器目前繁忙")
        print("   建議：稍後再試，或前往 https://ai.dev/rate-limit 確認用量。")
        raise RuntimeError("所有 Gemini 模型配額皆已用盡或暫時不可用") from last_error

    # 解析 JSON（允許 markdown code block 包覆）
    json_match = re.search(r"\{.*?\}", response_text, re.DOTALL)
    if not json_match:
        raise ValueError(f"Gemini 回應格式錯誤：{response_text}")

    result = json.loads(json_match.group())
    return {
        "score": float(result["score"]),
        "comment": result["comment"],
    }


# ── 主流程 ──────────────────────────────────────────────
def run_analysis(diary_text: str | None = None):
    """
    執行情緒分析流程

    使用方式：
      run_analysis()               # 自動讀取今天（或最新）的 Notion 日記
      run_analysis(diary_text="...") # 直接傳入文字（測試用）
    """
    print("=" * 50)
    print(f"  日記情緒分析  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    if diary_text:
        text = diary_text
        entry_title = "手動輸入"
        print("📖 使用手動輸入的日記內容\n")
    else:
        print("📖 讀取 Notion 日記中...")
        text, entry_title = fetch_today_diary()
        if entry_title:
            print(f"找到日記：{entry_title}\n")

    if not text.strip():
        print("⚠️  找不到日記內容，請確認 Notion 設定或直接傳入文字。")
        return

    print(f"日記內容（前 200 字）：\n{text[:200]}{'...' if len(text) > 200 else ''}\n")
    print("🤔 分析中...")

    try:
        result = analyze_emotion(text)
    except RuntimeError:
        return None

    score     = result["score"]
    comment   = result["comment"]
    level_msg = get_level_message(score)

    print("\n" + "─" * 50)
    print(f"  情緒分數：{score:.1f} / 10")
    print(f"  {level_msg}")
    print("─" * 50)
    print(f"\n💬 Gemini 的評語：\n{comment}\n")

    return {"score": score, "comment": comment, "level_message": level_msg}


# ── 執行 ────────────────────────────────────────────────
if __name__ == "__main__":
    # 方式二：直接貼入文字測試（不需要 Notion 設定）— 先測試這個
    sample_diary = """
    今天工作上遇到一個很難解決的 bug，花了整整三個小時才找到原因，
    結果只是一個漏掉的分號。雖然有點挫折，但解決之後還是很有成就感。
    下午和朋友去吃了火鍋，聊了很多，心情好多了。
    晚上回家看了一集喜歡的動漫，今天整體來說還算不錯的一天。
    """
    #run_analysis(diary_text=sample_diary)

    # 方式一：從 Notion 自動讀取最新日記（確認 sample 有效後再開啟）
    run_analysis()

   