import yfinance as yf
import requests
import json
import os
from datetime import datetime

# --- 配置區 ---
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK')

# 預設監控的熱門候選池 (涵蓋面板、鋼鐵、塑化等低價族群)
CANDIDATE_POOL = [
    "2409.TW", "3494.TW", "8105.TW", "2014.TW", "1314.TW", 
    "2610.TW", "2883.TW", "6116.TW", "3481.TW", "2323.TW"
]

def get_dynamic_targets():
    """自動從候選池中篩選出符合 20 元以下的標的"""
    targets = {}
    print("正在掃描市場標的...")
    for sid in CANDIDATE_POOL:
        try:
            t = yf.Ticker(sid)
            # 抓取最新收盤價進行過濾
            fast_info = t.basic_metadata
            current_price = fast_info.get('last_price') or t.history(period="1d")['Close'].iloc[-1]
            
            # 核心邏輯：只取 20 元以下
            if current_price and current_price <= 20.0:
                # 獲取中文名稱 (若無則顯示代碼)
                name = t.info.get('shortName', sid)
                targets[sid] = name
            
            if len(targets) >= 5: break # 取前 5 名最符合條件的標的
        except:
            continue
    return targets

def monitor_stocks():
    stock_map = get_dynamic_targets()
    if not stock_map:
        print("未發現符合 20 元以下之標的")
        return

    print(f"今日監控標的: {list(stock_map.values())}")
    
    for stock_id, stock_name in stock_map.items():
        try:
            ticker = yf.Ticker(stock_id)
            df = ticker.history(period="1d", interval="1m")
            if df.empty: continue

            # 數據精確化處理
            open_p = round(df['Open'].iloc[0], 2)
            current_p = round(df['Close'].iloc[-1], 2)
            cheap_p = round(open_p * 0.985, 2)  # 1.5% 便宜價
            exit_p = round(current_p * 1.025, 2) # 2.5% 停利點

            # 觸發條件檢查
            if current_p <= cheap_p:
                # Discord 表格美化格式
                table = (
                    f"```\n"
                    f"項目       | 數值\n"
                    f"-----------|-----------\n"
                    f"股票名稱   | {stock_name}\n"
                    f"標的代碼   | {stock_id}\n"
                    f"今日開盤   | {open_p}\n"
                    f"觸發買入   | {current_p}\n"
                    f"建議停利   | {exit_p}\n"
                    f"```"
                )
                
                payload = {
                    "embeds": [{
                        "title": "🎯 雲端當沖信號觸發",
                        "description": table,
                        "color": 15158332, # 紅色提醒
                        "footer": {"text": f"監測時間: {datetime.now().strftime('%H:%M:%S')}"}
                    }]
                }
                requests.post(DISCORD_WEBHOOK_URL, json=payload)
                
        except Exception as e:
            print(f"監控錯誤 {stock_id}: {e}")

if __name__ == "__main__":
    monitor_stocks()
