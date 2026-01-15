import yfinance as yf
import requests
import os
from datetime import datetime

# --- 配置區 ---
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK')
# 取得 GitHub 執行環境變數，判斷是否為手動執行 (workflow_dispatch)
IS_MANUAL = os.getenv('GITHUB_EVENT_NAME') == 'workflow_dispatch'

def get_twse_hot_stocks():
    hot_targets = {}
    try:
        url = "https://www.twse.com.tw/exchangeReport/MI_INDEX20?response=json"
        res = requests.get(url)
        data = res.json()
        items = data.get('data', [])
        
        for item in items:
            code = item[1]
            name = item[2]
            try:
                # 排除 ETF (代碼長度超過 4 碼或含有英文字母的通常是 ETF 或特別股)
                if len(code) > 4: continue 
                
                open_p = float(item[5].replace(',', ''))
                # 核心篩選：20 元以下標的
                if 0 < open_p <= 20.0:
                    hot_targets[f"{code}.TW"] = name
            except:
                continue
            if len(hot_targets) >= 5: break
    except:
        return {"2409.TW": "友達", "8105.TW": "凌巨", "2014.TW": "中鴻", "3494.TW": "誠研", "1314.TW": "中石化"}
    return hot_targets

def send_discord_msg(title, stock_name, stock_id, open_p, current_p, cheap_p, exit_p, status_msg):
    # 根據是否觸發買入更換顏色 (紅色: 15158332, 藍色: 3447003)
    color = 15158332 if current_p <= cheap_p else 3447003
    
    table = (
        f"```\n"
        f"項目       | 數值\n"
        f"-----------|-----------\n"
        f"股票名稱   | {stock_name}\n"
        f"今日開盤   | {open_p}\n"
        f"當前現價   | {current_p}\n"
        f"便宜買點   | {cheap_p}\n"
        f"建議停利   | {exit_p}\n"
        f"狀態       | {status_msg}\n"
        f"```"
    )
    
    payload = {
        "embeds": [{
            "title": f"{title}：{stock_name}",
            "description": table,
            "color": color,
            "footer": {"text": f"報告時間: {datetime.now().strftime('%H:%M:%S')}"}
        }]
    }
    requests.post(DISCORD_WEBHOOK_URL, json=payload)

def monitor_stocks():
    stock_map = get_twse_hot_stocks()
    print(f"今日監控標銘: {list(stock_map.values())}")
    
    for stock_id, stock_name in stock_map.items():
        try:
            ticker = yf.Ticker(stock_id)
            df = ticker.history(period="1d", interval="1m")
            if df.empty: continue

            open_p = round(df['Open'].iloc[0], 2)
            current_p = round(df['Close'].iloc[-1], 2)
            cheap_p = round(open_p * 0.985, 2)
            exit_p = round(current_p * 1.025, 2)

            # 判斷邏輯：
            # 1. 如果現價 <= 便宜價 -> 觸發「訊號」
            # 2. 如果是手動執行 -> 觸發「回報」
            if current_p <= cheap_p:
                send_discord_msg("🎯 買入訊號觸發", stock_name, stock_id, open_p, current_p, cheap_p, exit_p, "低於便宜價，建議佈局")
            elif IS_MANUAL:
                send_discord_msg("📝 手動狀態回報", stock_name, stock_id, open_p, current_p, cheap_p, exit_p, "未達買點，持續觀察")
                
        except Exception as e:
            print(f"錯誤 {stock_id}: {e}")

if __name__ == "__main__":
    monitor_stocks()
