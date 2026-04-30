# 📖 Notion 日記情緒分析系統 (Notion Diary Emotion Analyzer)

> 一個結合 Notion API 與大型語言模型 (LLM)，全自動化追蹤與分析每日心理狀態的工具。


<img width="1662" height="1305" alt="Ollama完成圖" src="https://github.com/user-attachments/assets/dca86077-ebf1-47d3-bbb4-7965fae0ec78" />
<img width="2039" height="1299" alt="Gemini成功圖" src="https://github.com/user-attachments/assets/6730c3a6-a5e4-40ca-9578-d45293851fec" />
<img width="2004" height="1252" alt="Gemini失敗圖" src="https://github.com/user-attachments/assets/2380cb5a-6423-4a48-b598-5cafc4b56c1d" />



## 💡 專案簡介
在快節奏的生活中，我們常常忽略了自我情緒的梳理。本專案旨在打造一個「無感介入」的情緒追蹤系統。使用者只需維持平常在 Notion 寫日記的習慣，系統便會自動抓取最新內容，透過 AI 進行語意與情緒分析，並給予量化的分數與溫暖的回饋。

這個專案不僅是我從硬體維護跨足軟體開發的實戰作品，也展現了我對 API 串接、資料清理、以及 AI 系統穩定性（Error Handling）的掌握能力。

## 🛠️ 技術亮點與實作細節

為了確保系統的強健性與實用性，我在開發過程中解決了以下技術挑戰：

1. **複雜的 Notion 資料結構解析 (Recursion)**：
   * 捨棄低效的全域掃描，精準抓取前 100 個區塊。
   * 運用**遞迴 (Recursive) 函數**，成功解析 Notion 中常見的巢狀結構（如 Toggle 摺疊列表）與多層次標題。
   * 實作時間探知邏輯，支援 `@Today` Mention 標籤與 `YYYY-MM-DD` 標題解析。
2. **LLM 的提示詞工程與格式控制**：
   * 嚴格定義 System Prompt，規範 AI 扮演具同理心的分析師角色。
   * 透過 **Regex (正則表達式)** 手動實作 JSON 萃取器，防止 LLM 回傳多餘廢話導致系統崩潰。
3. **高可用性的多模型備援機制 (Fallback Design)**：
   * 在 Gemini 版本中，為了避免 API `429 Too Many Requests` 或額度耗盡的問題，實作了自動降級備援機制（Gemini-2.5-flash -> 2.0-flash -> 2.0-flash-lite）。
   * 確保系統在各種網路或配額限制下，依然能保持最高成功率。
4. **雙版本對照 (Ollama vs. Gemini)**：
   * 同時提供地端模型 (Ollama) 與雲端 API (Gemini) 雙版本，展現對不同 LLM 部署架構的理解與實作能力。

## 🚀 系統架構與流程

1. **觸發**：執行 Python 腳本。
2. **提取 (Notion API)**：透過 API 讀取特定 Database ID 的內容，尋找符合今日日期的日記區塊。
3. **清洗**：過濾空白內容，將零散的 Rich Text 碎片黏合成純文字。
4. **分析 (Gemini API / Ollama)**：將純文字送入 LLM 進行情緒鑑定。
5. **輸出**：回傳 0~10 分的情緒分數與具體評語，並透過系統底層編碼設定 (`sys.stdout`) 確保終端機完美輸出 UTF-8 與 Emoji。

## 📦 快速開始 (Quick Start)

### 1. 安裝依賴套件
```bash
pip install requests google-genai python-dotenv

2. 環境變數設定
請在專案根目錄建立一個 .env 檔案，並填入以下資訊（請參考 .env.example）：

3. 執行程式
# 執行雲端高可用版本 (推薦)
python 日記情緒分析(Gemini).py

# 或執行地端開源模型版本 (需確保 Ollama 背景執行中)
python 日記情緒分析(Ollama).py


關於作者
從Gogoro電動機車保養維護、醫工設備的妥善率管理，一路走到了軟體開發的世界。我習慣用系統化的思維來拆解問題，現在，我正把這份對「系統穩定度」的堅持，轉化為一行行的程式碼。


聯絡方式
scott5566123@gmail.com
www.linkedin.com/in/rick-hsiao-7a5901344
