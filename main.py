import yfinance as yf
import requests
import os
from datetime import datetime

# --- 配置區 ---
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK')
IS_MANUAL = os.getenv('GITHUB_EVENT_NAME') == 'workflow_dispatch'

def get_twse_hot_stocks():
    """從證交所排行 API 穩定過濾並補滿 5 支 20 元以下個股"""
    hot_targets = {}
    try:
        url = "https://www.twse.com.tw/exchangeReport/MI_INDEX20?response=json"
        res = requests.get(url, timeout=10)
        data = res.json()
        items = data.get('data', [])
        
        for item in items:
            code = item[1].strip()
            name = item[2].strip()
            
            # 1. 排除 ETF (代碼超過 4 碼) 與權證
            if len(code) > 4: continue 
            
            try:
                # 2. 處理開盤價字串轉數字，若為 '--' 則跳過
                raw_open = item[5].replace(',', '').strip()
                if raw_open == '--' or not raw_open: continue
                
                open_p = float(raw_open)
                # 3. 核心篩選：20 元以下
                if 0 < open_p <= 20.0:
                    hot_targets[f"{code}.TW"] = name
            except:
                continue
            
            # 4. 補滿 5 支個股即停止
            if len(hot_targets) >= 5: break
            
    except Exception as e:
        print(f"API 抓取異常: {e}")
        # 備援名單
        return {"2409.TW": "友達", "8105.TW": "凌巨", "2014.TW": "中鴻", "3494.TW": "誠研", "1314.TW": "中石化"}
    
    return hot_targets

def send_discord_msg(title, stock_name, stock_id, open_p, current_p, cheap_p, exit_p, change_pct, status_msg):
    is_triggered = current_p <= cheap_p
    color = 15158332 if is_triggered else 3447003
    status_icon = "🔥" if is_triggered else "📝"

    # 確保數值對齊與漲跌幅顯示
    table = (
        f"```\n"
        f"項目       | 數值\n"
        f"-----------|-----------\n"
        f"名稱代碼   | {stock_name} ({stock_id})\n"
        f"今日開盤   | {open_p:<10}\n"
        f"當前現價   | {current_p:<10} ({change_pct}%)\n"
        f"便宜買點   | {cheap_p:<10}\n"
        f"建議停利   | {exit_p:<10}\n"
        f"狀態       | {status_msg}\n"
        f"```"
    )
    
    payload = {
        "embeds": [{
            "title": f"{status_icon} {title}：{stock_name}",
            "description": table,
            "color": color,
            "footer": {"text": f"監測時間: {datetime.now().strftime('%H:%M:%S')}"}
        }]
    }
    requests.post(DISCORD_WEBHOOK_URL, json=payload)

def monitor_stocks():
    stock_map = get_twse_hot_stocks()
    print(f"目前掃描結果: {list(stock_map.values())}")
    
    for stock_id, stock_name in stock_map.items():
        try:
            ticker = yf.Ticker(stock_id)
            # 增加數據獲取時間跨度確保非空
            df = ticker.history(period="2d", interval="1m")
            if df.empty: continue

            # 取最後一筆即時數據
            latest = df.iloc[-1]
            # 抓取今日該標的首筆開盤價
            today_open = df[df.index.date == datetime.now().date()]
            open_p = round(today_open['Open'].iloc[0], 2) if not today_open.empty else round(latest['Open'], 2)
            
            current_p = round(latest['Close'], 2)
            cheap_p = round(open_p * 0.985, 2)
            exit_p = round(current_p * 1.025, 2)
            change_pct = round(((current_p - open_p) / open_p) * 100, 2)

            if current_p <= cheap_p:
                send_discord_msg("買入訊號觸發", stock_name, stock_id, open_p, current_p, cheap_p, exit_p, change_pct, "建議佈局")
            elif IS_MANUAL:
                send_discord_msg("手動狀態回報", stock_name, stock_id, open_p, current_p, cheap_p, exit_p, change_pct, "觀望中")
                
        except Exception as e:
            print(f"標的監控錯誤 {stock_id}: {e}")

if __name__ == "__main__":
    monitor_stocks()
