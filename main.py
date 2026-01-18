import yfinance as yf
import requests
import os
from datetime import datetime, timezone, timedelta

# --- 配置區 ---
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK')
# 判斷是否為手動執行
IS_MANUAL = os.getenv('GITHUB_EVENT_NAME') == 'workflow_dispatch'

# 備用補位名單
BACKUP_POOL = {
    "2409.TW": "友達", "2014.TW": "中鴻", "8105.TW": "凌巨",
    "6116.TW": "彩晶", "1314.TW": "中石化", "2323.TW": "中環", "3494.TW": "誠研"
}

def get_current_tw_time():
    """取得台灣目前的時與分"""
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
    """混合策略：API 熱門股 + 備用名單補位 + 去重"""
    final_targets = {}
    
    # 1. 嘗試抓取證交所熱門股
    try:
        url = "https://www.twse.com.tw/exchangeReport/MI_INDEX20?response=json"
        res = requests.get(url, timeout=5)
        data = res.json()
        items = data.get('data', [])
        
        for item in items:
            code = item[1].strip()
            name = item[2].strip()
            if len(code) > 4: continue 
            
            try:
                raw_open = item[5].replace(',', '').strip()
                if raw_open == '--' or not raw_open: continue
                open_p = float(raw_open)
                if 0 < open_p <= 20.0:
                    stock_id = f"{code}.TW"
                    if stock_id not in final_targets:
                        final_targets[stock_id] = name
            except:
                continue
            if len(final_targets) >= 5: break
    except:
        pass

    # 2. 備用名單補位
    if len(final_targets) < 5:
        for b_code, b_name in BACKUP_POOL.items():
            if len(final_targets) >= 5: break
            if b_code not in final_targets:
                final_targets[b_code] = b_name
    
    return final_targets

def send_discord_pre_market(stock_list, adr_pct):
    """發送 08:00 盤前戰報 (包含夜盤建議)"""
    # 根據 ADR 判斷建議
    if adr_pct >= 1.0:
        advice = "🇺🇸 ADR大漲，個股易開高！\n⛔ 嚴禁追價，建議將買點下移至平盤下 1%。"
        color = 15158332 # 紅色警示
    elif adr_pct <= -1.0:
        advice = "🇺🇸 ADR走弱，今日有低點可期。\n✅ 維持 1.5% 便宜價策略，大膽佈局。"
        color = 3066993  # 綠色機會
    else:
        advice = "⚖️ 盤勢震盪，個股表現為主。\n👀 依照原定 1.5% 紀律執行。"
        color = 3447003  # 藍色中性

    # 製作今日觀察名單表格
    list_str = ""
    for i, (sid, name) in enumerate(stock_list, 1):
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
            "title": "☀️ 08:00 盤前夜盤戰報",
            "description": table,
            "color": color,
            "footer": {"text": f"發報時間: {datetime.now().strftime('%H:%M:%S')}"}
        }]
    }
    requests.post(DISCORD_WEBHOOK_URL, json=payload)

def send_discord_monitor(index, stock_name, stock_id, open_p, current_p, cheap_p, exit_p, change_pct, status_msg):
    """發送 09:10 盤中監測訊號"""
    is_triggered = current_p <= cheap_p
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
            "title": f"{status_icon} [{index}/5] 監測：{stock_name}",
            "description": table,
            "color": color,
            "footer": {"text": f"監測時間: {datetime.now().strftime('%H:%M:%S')}"}
        }]
    }
    requests.post(DISCORD_WEBHOOK_URL, json=payload)

def monitor_stocks():
    # 取得現在台灣時間
    tw_time = get_current_tw_time()
    current_hour = tw_time.hour
    
    # 抓取名單與 ADR
    stock_map = get_mixed_stock_list()
    stock_list = list(stock_map.items())
    adr_pct = get_adr_status()

    # --- 情境 A: 早上 08:00 ~ 08:59 -> 執行盤前戰報 ---
    # 手動執行時(IS_MANUAL)若想看戰報，可暫時不限縮時間，但為了區隔，這裡設定為：
    # 若手動執行且時間 < 09:00，也發戰報
    if current_hour == 8 or (IS_MANUAL and current_hour < 9):
        print("執行 08:00 盤前戰報模式...")
        send_discord_pre_market(stock_list, adr_pct)
        return

    # --- 情境 B: 早上 09:00 後 -> 執行盤中監測 ---
    print("執行 09:10 盤中監測模式...")
    for i, (stock_id, stock_name) in enumerate(stock_list, 1):
        try:
            ticker = yf.Ticker(stock_id)
            df = ticker.history(period="2d", interval="1m")
            if df.empty: continue

            latest = df.iloc[-1]
            # 嘗試抓今日開盤，若無(可能剛開盤)則抓昨天收盤當參考
            today_data = df[df.index.date == tw_time.date()]
            if not today_data.empty:
                open_p = round(today_data['Open'].iloc[0], 2)
            else:
                open_p = round(latest['Open'], 2) # 暫用昨收代替

            current_p = round(latest['Close'], 2)
            cheap_p = round(open_p * 0.985, 2)
            exit_p = round(current_p * 1.025, 2)
            change_pct = round(((current_p - open_p) / open_p) * 100, 2)

            # 只有 "跌破便宜價" 或 "手動執行" 才發訊
            if current_p <= cheap_p:
                send_discord_monitor(i, stock_name, stock_id, open_p, current_p, cheap_p, exit_p, change_pct, "建議佈局")
            elif IS_MANUAL:
                send_discord_monitor(i, stock_name, stock_id, open_p, current_p, cheap_p, exit_p, change_pct, "觀望中")
                
        except Exception as e:
            print(f"監控錯誤 {stock_id}: {e}")

if __name__ == "__main__":
    monitor_stocks()
