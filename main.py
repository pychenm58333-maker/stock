import yfinance as yf
import requests
import json
import os
import time
from datetime import datetime

# --- 配置區 ---
# 透過 GitHub Secrets 讀取 Discord Webhook
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK')

# 根據 1/8 最新收盤截圖動態更新監控標的
TARGET_STOCKS = ["3494.TW", "2409.TW", "8105.TW", "2014.TW", "1314.TW"]

# 交易參數
ENTRY_RATIO = 0.985        # 便宜價：開盤價回測 1.5%
TRAILING_STOP_PCT = 0.015  # 移動停利：高點回落 1.5%

def send_discord_notification(title, content_list, color=3066993):
    """發送 Discord Embed 訊息"""
    fields = [{"name": c[0], "value": str(c[1]), "inline": True} for c in content_list]
    payload = {
        "embeds": [{
            "title": title,
            "color": color,
            "fields": fields,
            "footer": {"text": f"報告時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
        }]
    }
    requests.post(DISCORD_WEBHOOK_URL, data=json.dumps(payload), headers={"Content-Type": "application/json"})

def monitor_stocks():
    print(f"[{datetime.now()}] 啟動 2026 雲端監測系統...")
    
    for stock_id in TARGET_STOCKS:
        try:
            ticker = yf.Ticker(stock_id)
            # 獲取今日 1 分鐘 K 線數據，確保數據採自證交所即時行情
            df = ticker.history(period="1d", interval="1m")
            
            if df.empty or len(df) < 1:
                continue

            open_price = df['Open'].iloc[0]
            current_price = df['Close'].iloc[-1]
            
            # 判斷是否符合 20 元以下策略
            if open_price > 20.0:
                print(f"{stock_id} 開盤價 {open_price} 超過 20 元，略過。")
                continue

            # 計算便宜價
            # $EntryPrice = Open \times 0.985$
            cheap_price = round(open_price * ENTRY_RATIO, 2)
            
            print(f"{stock_id} | 開盤: {open_price} | 現價: {current_price} | 目標便宜價: {cheap_price}")

            # 買入觸發邏輯
            if current_price <= cheap_price:
                suggested_exit = round(current_price * 1.025, 2)
                
                info = [
                    ("標的代號", stock_id),
                    ("今日開盤", open_price),
                    ("觸發買入點", f"**{current_price}**"),
                    ("建議停利點", suggested_exit),
                    ("狀態", "🔥 已達便宜價")
                ]
                send_discord_notification("🎯 當沖買入信號觸發", info, color=15158332)
                
        except Exception as e:
            print(f"監控 {stock_id} 時發生錯誤: {e}")

if __name__ == "__main__":
    monitor_stocks()
