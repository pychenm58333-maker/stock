import yfinance as yf
import requests
import os
from datetime import datetime

# --- 配置區 ---
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK')
IS_MANUAL = os.getenv('GITHUB_EVENT_NAME') == 'workflow_dispatch'

# 備用補位名單 (F/T/C 模型精選)
BACKUP_POOL = {
    "2409.TW": "友達",
    "2014.TW": "中鴻",
    "8105.TW": "凌巨",
    "6116.TW": "彩晶",
    "1314.TW": "中石化",
    "2323.TW": "中環",
    "3494.TW": "誠研"
}

def get_adr_status():
    """抓取昨晚美股友達 ADR (AUOTY) 漲跌幅"""
    try:
        adr = yf.Ticker("AUOTY")
        # 抓取近 5 天以確保有資料 (避開美股休市)
        hist = adr.history(period="5d")
        if len(hist) >= 2:
            prev_close = hist['Close'].iloc[-2]
            last_close = hist['Close'].iloc[-1]
            pct = round(((last_close - prev_close) / prev_close) * 100, 2)
            return f"{pct:+.2f}%" # 顯示正負號
    except:
        pass
    return "N/A"

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
            if len(code) > 4: continue # 排除 ETF
            
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
    except Exception as e:
        print(f"API 異常，啟用全備用模式: {e}")

    # 2. 備用名單補位 (補滿 5 支)
    if len(final_targets) < 5:
        for b_code, b_name in BACKUP_POOL.items():
            if len(final_targets) >= 5: break
            if b_code not in final_targets:
                final_targets[b_code] = b_name
    
    return final_targets

def send_discord_msg(index, title, stock_name, stock_id, open_p, current_p, cheap_p, exit_p, change_pct, status_msg, adr_info):
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
    
    # 將 ADR 資訊放入 Footer
    footer_text = f"監測時間: {datetime.now().strftime('%H:%M:%S')} | 🇺🇸 友達ADR: {adr_info}"

    payload = {
        "embeds": [{
            "title": f"{status_icon} [{index}/5] {title}：{stock_name}",
            "description": table,
            "color": color,
            "footer": {"text": footer_text}
        }]
    }
    requests.post(DISCORD_WEBHOOK_URL, json=payload)

def monitor_stocks():
    stock_map = get_mixed_stock_list()
    stock_list = list(stock_map.items())
    print(f"監控清單: {stock_list}")
    
    # 獲取 ADR 狀態 (只抓一次，共用)
    adr_status = get_adr_status()
    
    for i, (stock_id, stock_name) in enumerate(stock_list, 1):
        try:
            ticker = yf.Ticker(stock_id)
            df = ticker.history(period="2d", interval="1m")
            if df.empty: continue

            latest = df.iloc[-1]
            today_data = df[df.index.date == datetime.now().date()]
            if not today_data.empty:
                open_p = round(today_data['Open'].iloc[0], 2)
            else:
                open_p = round(latest['Open'], 2)

            current_p = round(latest['Close'], 2)
            cheap_p = round(open_p * 0.985, 2)
            exit_p = round(current_p * 1.025, 2)
            change_pct = round(((current_p - open_p) / open_p) * 100, 2)

            if current_p <= cheap_p:
                send_discord_msg(i, "買入訊號", stock_name, stock_id, open_p, current_p, cheap_p, exit_p, change_pct, "建議佈局", adr_status)
            elif IS_MANUAL:
                send_discord_msg(i, "手動回報", stock_name, stock_id, open_p, current_p, cheap_p, exit_p, change_pct, "觀望中", adr_status)
                
        except Exception as e:
            print(f"錯誤 {stock_id}: {e}")

if __name__ == "__main__":
    monitor_stocks()
