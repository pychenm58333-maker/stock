import yfinance as yf
import requests
import os
from datetime import datetime, timezone, timedelta

# --- 配置區 ---
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK')
# 取得 GitHub 執行事件名稱
EVENT_NAME = os.getenv('GITHUB_EVENT_NAME')
IS_MANUAL = (EVENT_NAME == 'workflow_dispatch')

# 備用補位名單 (F/T/C 模型精選)
BACKUP_POOL = {
    "2409.TW": "友達", "2014.TW": "中鴻", "8105.TW": "凌巨",
    "6116.TW": "彩晶", "1314.TW": "中石化", "2323.TW": "中環", "3494.TW": "誠研"
}

def get_current_tw_time():
    """精準取得台灣目前的時、分、秒"""
    utc_now = datetime.now(timezone.utc)
    tw_now = utc_now + timedelta(hours=8)
    return tw_now

def get_adr_status():
    """抓取昨晚美股友達 ADR (AUOTY) 漲跌幅"""
    try:
        adr = yf.Ticker("AUOTY")
        hist = adr.history(period="5d")
        if len(hist) >= 2:
            prev_close = hist['Close'].iloc[-2]
            last_close = hist['Close'].iloc[-1]
            pct = round(((last_close - prev_close) / prev_close) * 100, 2)
            return pct
    except:
        return 0.0

def get_mixed_stock_list():
    """自動篩選：證交所熱門股 + 備用名單補位 (確保 5 支個股不重複)"""
    final_targets = {}
    try:
        url = "https://www.twse.com.tw/exchangeReport/MI_INDEX20?response=json"
        res = requests.get(url, timeout=10)
        data = res.json()
        items = data.get('data', [])
        
        for item in items:
            code = item[1].strip()
            name = item[2].strip()
            if len(code) > 4: continue # 排除 ETF
            
            try:
                raw_open = item[5].replace(',', '').strip()
                if raw_open == '--' or not raw_open: continue
                open_p = float(raw_open)
                # 篩選 20 元以下
                if 0 < open_p <= 20.0:
                    stock_id = f"{code}.TW"
                    if stock_id not in final_targets:
                        final_targets[stock_id] = name
            except: continue
            if len(final_targets) >= 5: break
    except: pass

    # 若不足 5 支，由備用池補齊
    if len(final_targets) < 5:
        for b_code, b_name in BACKUP_POOL.items():
            if len(final_targets) >= 5: break
            if b_code not in final_targets:
                final_targets[b_code] = b_name
    return final_targets

def send_discord_pre_market(stock_list, adr_pct):
    """【08:00 模式】發送盤前戰報與夜盤建議"""
    if adr_pct >= 1.0:
        advice = "🇺🇸 ADR大漲，開盤易衝高！\n⛔ 嚴禁追價，建議等 09:30 回測再考慮。"
        color = 15158332 # 紅色警示
    elif adr_pct <= -1.0:
        advice = "🇺🇸 ADR走弱，早盤恐有殺盤。\n✅ 策略不變，跌破 1.5% 便宜價再進場。"
        color = 3066993  # 綠色機會
    else:
        advice = "⚖️ 夜盤平穩，個股各自發揮。\n👀 維持 1.5% 紀律執行。"
        color = 3447003  # 藍色

    list_str = ""
    for i, (sid, name) in enumerate(stock_list.items(), 1):
        list_str += f"{i}. {name} ({sid})\n"

    table = (
        f"```\n"
        f"【今日重點觀察清單】\n"
        f"{list_str}\n"
        f"-----------------------\n"
        f"友達ADR昨收: {adr_pct:+.2f}%\n"
        f"```\n"
        f"**💡 操盤建議：**\n{advice}"
    )

    payload = {
        "embeds": [{
            "title": "☀️ 盤前夜盤戰報",
            "description": table,
            "color": color,
            "footer": {"text": f"發報時間: {datetime.now().strftime('%H:%M:%S')}"}
        }]
    }
    requests.post(DISCORD_WEBHOOK_URL, json=payload)

def send_discord_monitor(index, stock_name, stock_id, open_p, current_p, cheap_p, exit_p, change_pct, status_msg):
    """【09:10 模式】發送盤中監測詳情"""
    is_triggered = (current_p <= cheap_p)
    color = 15158332 if is_triggered else 3447003
    status_icon = "🔥" if is_triggered else "📝"

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
            "title": f"{status_icon} [{index}/5] {stock_name}",
            "description": table,
            "color": color,
            "footer": {"text": f"監測時間: {datetime.now().strftime('%H:%M:%S')}"}
        }]
    }
    requests.post(DISCORD_WEBHOOK_URL, json=payload)

def monitor_stocks():
    tw_time = get_current_tw_time()
    hour = tw_time.hour
    
    stock_map = get_mixed_stock_list()
    adr_pct = get_adr_status()

    # --- 邏輯 A：盤前戰報 (09:00 以前執行) ---
    if hour < 9:
        print(f"目前時間 {tw_time.strftime('%H:%M')}, 啟動盤前模式...")
        send_discord_pre_market(stock_map, adr_pct)
        return

    # --- 邏輯 B：盤中監測 (09:00 以後執行) ---
    print(f"目前時間 {tw_time.strftime('%H:%M')}, 啟動盤中模式...")
    for i, (stock_id, stock_name) in enumerate(stock_map.items(), 1):
        try:
            ticker = yf.Ticker(stock_id)
            df = ticker.history(period="1d", interval="1m")
            if df.empty: continue

            latest = df.iloc[-1]
            open_p = round(df['Open'].iloc[0], 2)
            current_p = round(latest['Close'], 2)
            cheap_p = round(open_p * 0.985, 2)
            exit_p = round(current_p * 1.025, 2)
            change_pct = round(((current_p - open_p) / open_p) * 100, 2)

            # 觸發買入點或是手動執行
            if current_p <= cheap_p:
                send_discord_monitor(i, stock_name, stock_id, open_p, current_p, cheap_p, exit_p, change_pct, "達標，建議買入")
            elif IS_MANUAL:
                send_discord_monitor(i, stock_name, stock_id, open_p, current_p, cheap_p, exit_p, change_pct, "手動抽查回報")
                
        except Exception as e:
            print(f"監控錯誤 {stock_id}: {e}")

if __name__ == "__main__":
    monitor_stocks()
