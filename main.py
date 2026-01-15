import yfinance as yf
import requests
import os
from datetime import datetime

# --- 配置區 ---
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK')
IS_MANUAL = os.getenv('GITHUB_EVENT_NAME') == 'workflow_dispatch'

def get_twse_hot_stocks():
    """從證交所排行中過濾並補滿 5 支 20 元以下純個股"""
    hot_targets = {}
    try:
        url = "https://www.twse.com.tw/exchangeReport/MI_INDEX20?response=json"
        res = requests.get(url)
        data = res.json()
        items = data.get('data', [])
        
        for item in items:
            code = item[1]
            name = item[2]
            # 排除 ETF 與權證 (代碼長度 > 4)
            if len(code) > 4: continue 
            
            try:
                # 取得今日開盤價
                open_p = float(item[5].replace(',', ''))
                # 核心篩選：20 元以下
                if 0 < open_p <= 20.0:
                    hot_targets[f"{code}.TW"] = name
            except:
                continue
            
            if len(hot_targets) >= 5: break
            
    except:
        return {"2409.TW": "友達", "8105.TW": "凌巨", "2014.TW": "中鴻", "3494.TW": "誠研", "1314.TW": "中石化"}
    return hot_targets

def send_discord_msg(title, stock_name, stock_id, open_p, current_p, cheap_p, exit_p, change_pct, status_msg):
    is_triggered = current_p <= cheap_p
    color = 15158332 if is_triggered else 3447003
    status_icon = "🔥" if is_triggered else "📝"

    # 使用 Markdown 表格並加入漲跌幅顯示
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
    print(f"今日自動篩選個股: {list(stock_map.values())}")
    
    for stock_id, stock_name in stock_map.items():
        try:
            ticker = yf.Ticker(stock_id)
            df = ticker.history(period="1d", interval="1m")
            if df.empty: continue

            open_p = round(df['Open'].iloc[0], 2)
            current_p = round(df['Close'].iloc[-1], 2)
            cheap_p = round(open_p * 0.985, 2)
            exit_p = round(current_p * 1.025, 2)
            
            # 計算今日漲跌幅 %
            change_pct = round(((current_p - open_p) / open_p) * 100, 2)

            # 邏輯判斷：買入訊號或手動執行
            if current_p <= cheap_p:
                send_discord_msg("買入訊號觸發", stock_name, stock_id, open_p, current_p, cheap_p, exit_p, change_pct, "達標，建議買入")
            elif IS_MANUAL:
                send_discord_msg("手動狀態回報", stock_name, stock_id, open_p, current_p, cheap_p, exit_p, change_pct, "未達買點，觀望中")
                
        except Exception as e:
            print(f"抓取錯誤 {stock_id}: {e}")

if __name__ == "__main__":
    monitor_stocks()
