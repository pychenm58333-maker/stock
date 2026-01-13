import yfinance as yf
import requests
import json
import os
from datetime import datetime

# 從系統環境變數讀取 Webhook (為了安全)
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK')
# 這裡的標的我會每天 14:00 提供清單給您，您可以手動更新此陣列
# 根據 2026/01/13 最新收盤數據更新
TARGET_STOCKS = ["2409.TW", "8105.TW", "2014.TW", "3494.TW", "1314.TW"]
ENTRY_RATIO = 0.985  # 便宜價定義

def send_to_discord(title, fields):
    payload = {
        "embeds": [{
            "title": title,
            "color": 3066993,
            "fields": fields,
            "footer": {"text": f"監測時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
        }]
    }
    requests.post(DISCORD_WEBHOOK_URL, data=json.dumps(payload), headers={"Content-Type":"application/json"})

def run_monitor():
    print("啟動雲端監控...")
    for stock in TARGET_STOCKS:
        ticker = yf.Ticker(stock)
        df = ticker.history(period="1d", interval="1m")
        if df.empty: continue
        
        open_p = df['Open'].iloc[0]
        current_p = df['Close'].iloc[-1]
        cheap_p = round(open_p * ENTRY_RATIO, 2)
        
        if current_p <= cheap_p:
            fields = [
                {"name": "標的", "value": stock, "inline": True},
                {"name": "開盤價", "value": str(open_p), "inline": True},
                {"name": "當前便宜價", "value": f"**{current_p}**", "inline": True},
                {"name": "建議賣出價", "value": f"**{round(current_p * 1.02, 2)}**", "inline": False}
            ]
            send_to_discord("🎯 雲端當沖信號觸發", fields)

if __name__ == "__main__":
    run_monitor()
