import yfinance as yf
import requests
import pandas as pd
import os
from datetime import datetime

# --- 配置區 ---
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK')

def get_twse_hot_stocks():
    """自動抓取證交所成交量前 20 名，並篩選 20 元以下標的"""
    hot_targets = {}
    try:
        # 證交所成交量前20名 API (不需 Key)
        url = "https://www.twse.com.tw/exchangeReport/MI_INDEX20?response=json"
        res = requests.get(url)
        data = res.json()
        
        # 取得股票清單數據
        # 欄位：[排名, 證券代號, 證券名稱, 成交股數, 成交筆數, 開盤價, ...]
        items = data.get('data', [])
        
        for item in items:
            code = item[1] # 股票代碼
            name = item[2] # 股票名稱
            try:
                # 取得開盤價並轉換為數字
                open_p = float(item[5].replace(',', ''))
                
                # 核心篩選條件：20 元以下
                if 0 < open_p <= 20.0:
                    hot_targets[f"{code}.TW"] = name
            except ValueError:
                continue
                
            if len(hot_targets) >= 5: break # 取前 5 名
            
    except Exception as e:
        print(f"抓取證交所熱門股失敗: {e}")
        # 若 API 失敗，退回備用清單
        return {"2409.TW": "友達", "3494.TW": "誠研", "8105.TW": "凌巨", "2014.TW": "中鴻", "1314.TW": "中石化"}
    
    return hot_targets

def monitor_stocks():
    # 自動獲取標的，不再需要手動輸入陣列
    stock_map = get_twse_hot_stocks()
    if not stock_map:
        print("未發現符合 20 元以下之熱門標的")
        return

    print(f"今日自動篩選標的: {list(stock_map.values())}")
    
    for stock_id, stock_name in stock_map.items():
        try:
            ticker = yf.Ticker(stock_id)
            # 獲取今日 1 分鐘 K 線
            df = ticker.history(period="1d", interval="1m")
            if df.empty: continue

            open_p = round(df['Open'].iloc[0], 2)
            current_p = round(df['Close'].iloc[-1], 2)
            cheap_p = round(open_p * 0.985, 2)  # 1.5% 便宜價
            exit_p = round(current_p * 1.025, 2) # 2.5% 停利點

            if current_p <= cheap_p:
                table = (
                    f"```\n"
                    f"項目       | 數值\n"
                    f"-----------|-----------\n"
                    f"股票名稱   | {stock_name}\n"
                    f"今日開盤   | {open_p}\n"
                    f"觸發買入   | {current_p}\n"
                    f"建議停利   | {exit_p}\n"
                    f"```"
                )
                
                payload = {
                    "embeds": [{
                        "title": f"🎯 自動監測信號：{stock_name}",
                        "description": table,
                        "color": 15158332,
                        "footer": {"text": f"執行時間: {datetime.now().strftime('%H:%M:%S')}"}
                    }]
                }
                requests.post(DISCORD_WEBHOOK_URL, json=payload)
                
        except Exception as e:
            print(f"錯誤 {stock_id}: {e}")

if __name__ == "__main__":
    monitor_stocks()
