import yfinance as yf
import requests
import os
from datetime import datetime, timezone, timedelta

# --- 配置區 ---
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK')
EVENT_NAME = os.getenv('GITHUB_EVENT_NAME')
IS_MANUAL = (EVENT_NAME == 'workflow_dispatch')

# 精選備用池 (基本面/技術面/籌碼面優質標的)
BACKUP_POOL = {
    "2409.TW": "友達", "2014.TW": "中鴻", "8105.TW": "凌巨",
    "6116.TW": "彩晶", "1314.TW": "中石化", "2323.TW": "中環", "3494.TW": "誠研"
}

def get_current_tw_time():
    utc_now = datetime.now(timezone.utc)
    return utc_now + timedelta(hours=8)

def get_adr_status():
    try:
        adr = yf.Ticker("AUOTY")
        hist = adr.history(period="5d")
        if len(hist) >= 2:
            prev = hist['Close'].iloc[-2]
            last = hist['Close'].iloc[-1]
            return round(((last - prev) / prev) * 100, 2)
    except: pass
    return 0.0

def get_mixed_stock_list():
    final_targets = {}
    try:
        url = "https://www.twse.com.tw/exchangeReport/MI_INDEX20?response=json"
        res = requests.get(url, timeout=10)
        data = res.json()
        items = data.get('data', [])
        for item in items:
            code = item[1].strip()
            name = item[2].strip()
            if len(code) > 4: continue
            try:
                raw_open = item[5].replace(',', '').strip()
                if raw_open == '--': continue
                if 0 < float(raw_open) <= 20.0:
                    final_targets[f"{code}.TW"] = name
            except: continue
            if len(final_targets) >= 5: break
    except: pass

    if len(final_targets) < 5:
        for b_code, b_name in BACKUP_POOL.items():
            if len(final_targets) >= 5: break
            if b_code not in final_targets: final_targets[b_code] = b_name
    return final_targets

# --- 新增：14:00 收盤評估發送函式 ---
def send_discord_after_market(stock_map):
    content = "📈 **明日高勝率標的評估 (20元以下精選)**\n\n"
    for i, (sid, name) in enumerate(stock_map.items(), 1):
        try:
            t = yf.Ticker(sid)
            close_p = round(t.history(period="1d")['Close'].iloc[-1], 2)
            # 預算明日：便宜價(今日收盤價*0.985), 建議賣出(今日收盤價*1.025)
            cheap = round(close_p * 0.985, 2)
            target = round(close_p * 1.025, 2)
            content += f"**{i}. {name} ({sid})**\n今日收盤: {close_p} | 預估買入: {cheap} | 建議賣出: {target}\n"
        except:
            content += f"**{i}. {name} ({sid})** - 資料獲取失敗\n"

    payload = {
        "embeds": [{
            "title": "📝 收盤總結：隔日開盤戰略評估",
            "description": content,
            "color": 3447003,
            "footer": {"text": f"評估時間: {datetime.now().strftime('%H:%M:%S')}"}
        }]
    }
    requests.post(DISCORD_WEBHOOK_URL, json=payload)

def send_discord_pre_market(stock_list, adr_pct):
    advice = "⚖️ 維持紀律"
    if adr_pct >= 1.0: advice = "⛔ ADR大漲，嚴禁追價！建議買點下移。"
    elif adr_pct <= -1.0: advice = "✅ ADR走弱，早盤恐有低點，分批佈局。"
    
    list_str = "\n".join([f"{i}. {n} ({s})" for i, (s, n) in enumerate(stock_list.items(), 1)])
    table = f"```\n【今日觀察清單】\n{list_str}\n-----------------------\n友達ADR: {adr_pct:+.2f}%\n```\n**💡 建議：** {advice}"
    payload = {"embeds": [{"title": "☀️ 08:00 盤前夜盤戰報", "description": table, "color": 15158332}]}
    requests.post(DISCORD_WEBHOOK_URL, json=payload)

def send_discord_monitor(index, name, sid, open_p, current_p, cheap_p, exit_p, change_pct, msg):
    is_t = (current_p <= cheap_p)
    table = f"```\n名稱代碼 | {name} ({sid})\n今日開盤 | {open_p}\n當前現價 | {current_p} ({change_pct}%)\n便宜買點 | {cheap_p}\n建議停利 | {exit_p}\n```"
    payload = {"embeds": [{"title": f"{'🔥' if is_t else '📝'} [{index}/5] {name}", "description": table, "color": 15158332 if is_t else 3447003}]}
    requests.post(DISCORD_WEBHOOK_URL, json=payload)

def monitor_stocks():
    tw_time = get_current_tw_time()
    hour = tw_time.hour
    stock_map = get_mixed_stock_list()

    # A: 14:00 收盤模式
    if hour == 14:
        send_discord_after_market(stock_map)
        return
    # B: 09:00 前 盤前模式
    if hour < 9:
        send_discord_pre_market(stock_map, get_adr_status())
        return
    # C: 盤中監測
    for i, (sid, name) in enumerate(stock_map.items(), 1):
        try:
            df = yf.Ticker(sid).history(period="1d", interval="1m")
            if df.empty: continue
            open_p = round(df['Open'].iloc[0], 2)
            curr_p = round(df['Close'].iloc[-1], 2)
            cheap = round(open_p * 0.985, 2)
            target = round(curr_p * 1.025, 2)
            chg = round(((curr_p - open_p) / open_p) * 100, 2)
            if curr_p <= cheap or IS_MANUAL:
                send_discord_monitor(i, name, sid, open_p, curr_p, cheap, target, chg, "訊號觸發")
        except: pass

if __name__ == "__main__":
    monitor_stocks()
