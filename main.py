import yfinance as yf
import requests
import os
from datetime import datetime

# --- 配置區 ---
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK')
IS_MANUAL = os.getenv('GITHUB_EVENT_NAME') == 'workflow_dispatch'

# --- 備用補位名單 (F/T/C 模型精選) ---
# 當 API 熱門股抓取不足 5 支時，將依序從此清單遞補
# 選股標準：20 元以下 + 基本面轉機 + 技術面支撐 + 籌碼流動性
BACKUP_POOL = {
    "2409.TW": "友達",   # 面板轉機/法人回補
    "2014.TW": "中鴻",   # 鋼價上揚/多頭排列
    "8105.TW": "凌巨",   # 車用面板/股性活潑
    "6116.TW": "彩晶",   # 低價面板/W底型態
    "1314.TW": "中石化", # 資產題材/底部鐵板
    "2323.TW": "中環",   # 業外收益/隔日沖熱點
    "3494.TW": "誠研"    # 轉機題材/主力控盤
}

def get_mixed_stock_list():
    """
    混合策略：
    1. 先從證交所 API 抓取熱門成交股 (優先)
    2. 若不足 5 支，從 BACKUP_POOL 補足
    3. 嚴格執行去重 (Deduplication)
    """
    final_targets = {}
    
    # --- 階段一：嘗試抓取證交所熱門股 ---
    try:
        url = "https://www.twse.com.tw/exchangeReport/MI_INDEX20?response=json"
        res = requests.get(url, timeout=5)
        data = res.json()
        items = data.get('data', [])
        
        for item in items:
            code = item[1].strip()
            name = item[2].strip()
            
            # 排除 ETF/基金 (代碼 > 4)
            if len(code) > 4: continue
            
            try:
                # 檢查開盤價
                raw_open = item[5].replace(',', '').strip()
                if raw_open == '--' or not raw_open: continue
                open_p = float(raw_open)
                
                # 篩選 20 元以下
                if 0 < open_p <= 20.0:
                    stock_id = f"{code}.TW"
                    if stock_id not in final_targets:
                        final_targets[stock_id] = name
            except:
                continue
            
            if len(final_targets) >= 5: break
            
    except Exception as e:
        print(f"API 抓取部分失敗，將使用備用名單補齊: {e}")

    # --- 階段二：數量檢查與補齊 (Fill the Gap) ---
    # 如果不足 5 支，從備用清單中補，直到滿 5 支為止
    if len(final_targets) < 5:
        print(f"目前只有 {len(final_targets)} 支，啟動補位機制...")
        for b_code, b_name in BACKUP_POOL.items():
            if len(final_targets) >= 5:
                break
            # 關鍵去重：只有當代碼不存在時才加入
            if b_code not in final_targets:
                final_targets[b_code] = b_name
    
    return final_targets

def send_discord_msg(index, title, stock_name, stock_id, open_p, current_p, cheap_p, exit_p, change_pct, status_msg):
    is_triggered = current_p <= cheap_p
    # 顏色邏輯：觸發(紅) vs 觀察(藍)
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
            # 在標題加入序號 (例如 #1/5)，方便您確認是否重複
            "title": f"{status_icon} [{index}/5] {title}：{stock_name}",
            "description": table,
            "color": color,
            "footer": {"text": f"監測時間: {datetime.now().strftime('%H:%M:%S')}"}
        }]
    }
    requests.post(DISCORD_WEBHOOK_URL, json=payload)

def monitor_stocks():
    stock_map = get_mixed_stock_list()
    # 將字典轉為 list 以便排序和編號
    stock_list = list(stock_map.items())
    print(f"最終執行名單 ({len(stock_list)}支): {stock_list}")
    
    # 使用 enumerate 加入序號 (index)
    for i, (stock_id, stock_name) in enumerate(stock_list, 1):
        try:
            ticker = yf.Ticker(stock_id)
            df = ticker.history(period="2d", interval="1m")
            if df.empty: continue

            latest = df.iloc[-1]
            # 抓取今日開盤，若無則用最新一筆 Open
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
                send_discord_msg(i, "買入訊號", stock_name, stock_id, open_p, current_p, cheap_p, exit_p, change_pct, "建議佈局")
            elif IS_MANUAL:
                send_discord_msg(i, "手動回報", stock_name, stock_id, open_p, current_p, cheap_p, exit_p, change_pct, "觀望中")
                
        except Exception as e:
            print(f"監控錯誤 {stock_id}: {e}")

if __name__ == "__main__":
    monitor_stocks()
