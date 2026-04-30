"""
日記情緒分析系統
讀取 Notion 日記（Toggle 格式），透過本地 Ollama LLM 分析情緒，給予分數與評語
"""

import os
import json
import re
from datetime import datetime, date
from dotenv import load_dotenv
import requests


# 載入 .env 檔案
env_path = r"F:\RickHSIAO\Python\My Project\日記情緒分析\.env"
load_dotenv(env_path, override=True)

# ── 設定區 ──────────────────────────────────────────────
NOTION_API_KEY  = os.environ.get("NOTION_API_KEY", "")
NOTION_PAGE_ID  = os.environ.get("NOTION_DATABASE_ID", "")  # 日記主頁面 ID
OLLAMA_API_URL = "http://localhost:11434/api/generate"  # Ollama 本地 API

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
    支援 heading_1 格式：標題為 "YYYY-MM-DD — 標題"，以 divider 分隔
    回傳 (日記文字, 日期標題)
    """
    if not NOTION_API_KEY or not NOTION_PAGE_ID:
        raise ValueError("請設定 NOTION_API_KEY 與 NOTION_DATABASE_ID 環境變數")

    # 逐頁讀取，找到目標後立即停止
    blocks_url = f"https://api.notion.com/v1/blocks/{NOTION_PAGE_ID}/children"
    print(f"📡 連接 Notion API: {blocks_url}")
    today = date.today()
    best_entry = None  # (entry_date, title, block_id)
    best_date = None
    total_blocks = 0    
    url = blocks_url

    while url:
        try:
            resp = requests.get(url, headers=NOTION_HEADERS, timeout=15)
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            print(f"❌ HTTP 錯誤 {e.response.status_code}: {e.response.text}")
            raise
        data = resp.json()
        blocks = data.get("results", [])
        total_blocks += len(blocks)

        for block in blocks:
            # 1. 不是大標題？跳過！
            if block.get("type") != "heading_1":
                continue
            # 2. 標題裡面沒有包著內容（子區塊）？跳過！
            if not block.get("has_children"):
                continue

            rich_texts = block.get("heading_1", {}).get("rich_text", [])
            title = "".join(rt.get("plain_text", "") for rt in rich_texts).strip()
            m = re.match(r"(\d{4}-\d{2}-\d{2})", title)
            if not m:
                continue
            try:
                entry_date = date.fromisoformat(m.group(1))
            except ValueError:
                continue

            if entry_date == today:
                print(f"✅ 找到今天的日記！（掃描 {total_blocks} 個區塊）")
                content = fetch_block_text(block["id"])
                return _clean_content(content), title

            if best_date is None or entry_date > best_date:
                best_date = entry_date
                best_entry = (entry_date, title, block["id"])

        next_cursor = data.get("next_cursor")
        url = f"{blocks_url}?start_cursor={next_cursor}" if next_cursor else None

    if best_entry:
        entry_date, title, block_id = best_entry
        print(f"✅ 找到最新的日記（日期：{entry_date}，掃描 {total_blocks} 個區塊）")
        content = fetch_block_text(block_id)
        return _clean_content(content), title

    print("⚠️  找不到任何日記")
    return "", ""


def _clean_content(text: str) -> str:
    """過濾佔位文字與空行"""
    placeholder = "Add your notes here"
    lines = [l for l in text.splitlines() if l.strip() and placeholder not in l]
    return "\n".join(lines)


# ── Ollama：情緒分析 ────────────────────────────────────
def analyze_emotion(diary_text: str) -> dict:
    """呼叫本地 Ollama LLM 分析日記情緒，回傳 score 與 comment"""

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

    prompt = f"{system_prompt}\n\n請分析以下日記內容：\n\n{diary_text}"

    try:
        response = requests.post(
            OLLAMA_API_URL,
            json={"model": "qwen2.5:14b", "prompt": prompt, "stream": False},
            timeout=60
        )
        response.raise_for_status()
        response_text = response.json().get("response", "")
    except requests.exceptions.ConnectionError:
        raise ValueError("❌ 無法連接 Ollama 服務\n請確認:\n1. Ollama 已安裝\n2. qwen2.5:14b 模型已下載\n3. Ollama 正在執行（ollama serve）")
    except Exception as e:
        raise ValueError(f"Ollama 錯誤：{str(e)}")

    # 解析 JSON（允許 markdown code block 包覆）
    json_match = re.search(r"\{.*?\}", response_text, re.DOTALL)
    if not json_match:
        raise ValueError(f"Ollama 回應格式錯誤：{response_text}")

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

    result = analyze_emotion(text)
    score     = result["score"]
    comment   = result["comment"]
    level_msg = get_level_message(score)

    print("\n" + "─" * 50)
    print(f"  情緒分數：{score:.1f} / 10")
    print(f"  {level_msg}")
    print("─" * 50)
    print(f"\n💬 Ollama 的評語：\n{comment}\n")

    return {"score": score, "comment": comment, "level_message": level_msg}


# ── 執行 ────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        run_analysis()
    except Exception as e:
        print(f"❌ 讀取 Notion 失敗：{e}\n")
        print("🔄 改用範例文字進行測試...\n")
        sample_diary = """
        今天工作上遇到一個很難解決的 bug，花了整整三個小時才找到原因，
        結果只是一個漏掉的分號。雖然有點挫折，但解決之後還是很有成就感。
        下午和朋友去吃了火鍋，聊了很多，心情好多了。
        晚上回家看了一集喜歡的動漫，今天整體來說還算不錯的一天。
        """
        run_analysis(diary_text=sample_diary)

    #   執行前 先完全關閉Ollama的程式，再下 "ollama serve" command 執行程式
    #   再打開Ollama的程式
   