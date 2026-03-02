import os
import csv
import json
import requests
from datetime import datetime

CSV_URL = "https://amplifyetfs.com/wp-content/uploads/feeds/AmplifyWeb.40XL.XL_SWAP_Holdings.csv"
STATE_FILE = "state.json"
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

TARGET_TICKERS = {
    "MAPS": "WM Technology Inc",
    "GRWG": "GrowGeneration Corp"
}

def fetch_csv():
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/csv"
    }
    response = requests.get(CSV_URL, headers=headers)
    response.raise_for_status()
    return response.text.splitlines()

def parse_csv(lines):
    header_index = -1
    header = []
    
    # Find header
    for i, line in enumerate(lines[:10]):
        cols = [c.strip() for c in next(csv.reader([line]))]
        col_upper = [c.upper() for c in cols]
        
        has_ticker = any(h in ["TICKER", "STOCKTICKER"] for h in col_upper)
        has_shares = "SHARES" in col_upper
        
        if has_ticker and has_shares:
            header_index = i
            header = col_upper
            break
            
    if header_index == -1:
        raise ValueError("Could not find header row in CSV")
        
    date_col = next((i for i, h in enumerate(header) if h == "DATE"), -1)
    ticker_col = next((i for i, h in enumerate(header) if h in ["TICKER", "STOCKTICKER"]), -1)
    shares_col = header.index("SHARES")
    weight_col = next((i for i, h in enumerate(header) if h in ["WEIGHTINGS", "WEIGHTING"]), -1)
    
    holdings = {}
    
    for line in lines[header_index + 1:]:
        if not line.strip():
            continue
            
        cols = [c.strip() for c in next(csv.reader([line]))]
        if ticker_col >= len(cols):
            continue
            
        ticker = cols[ticker_col].upper()
        
        if ticker in TARGET_TICKERS:
            date_str = cols[date_col] if date_col != -1 and cols[date_col] else datetime.now().strftime("%Y-%m-%d")
            # Try parsing date to standard YYYY-MM-DD if possible
            try:
                date_obj = datetime.strptime(date_str, "%m/%d/%Y")
                date_str = date_obj.strftime("%Y-%m-%d")
            except ValueError:
                pass # Keep as is if we can't parse it
                
            shares = int(float(cols[shares_col].replace(',', '')))
            
            weighting = 0.0
            if weight_col != -1 and weight_col < len(cols) and cols[weight_col]:
                weight_str = cols[weight_col].replace('%', '').strip()
                try:
                    # Convert to decimal (e.g. 1.5% -> 0.015) to match previous Apps Script logic
                    weighting = float(weight_str) / 100.0
                except ValueError:
                    pass
                    
            holdings[ticker] = {
                "date": date_str,
                "shares": shares,
                "weighting": weighting
            }
            
    return holdings

def load_state():
    if not os.path.exists(STATE_FILE):
        return {"fields": ["date", "shares", "weighting"], "data": {}}
    with open(STATE_FILE, "r") as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def send_discord_alert(ticker, company, current_data, previous_data):
    if not WEBHOOK_URL:
        print(f"Warning: No DISCORD_WEBHOOK_URL set. Would have sent alert for {ticker}")
        return
        
    current_shares = current_data["shares"]
    prev_shares = previous_data["shares"] if previous_data else 0
    delta = current_shares - prev_shares
    
    if delta == 0:
        return
        
    percent_change = (delta / prev_shares) if prev_shares != 0 else 0
    
    direction = "increased" if delta > 0 else "decreased"
    emoji = "📈" if delta > 0 else "📉"
    
    current_weighting = current_data["weighting"] * 100
    prev_weighting = (previous_data["weighting"] * 100) if previous_data else 0
    
    prev_weighting_str = f"{prev_weighting:.2f}%" if previous_data else "N/A"
    
    description = f"""
**Company:** {company} ({ticker})
**Date:** {current_data['date']}

**Current Shares:** {current_shares:,}
**Previous Shares:** {prev_shares:,}
**Change:** {delta:,} shares ({percent_change:.2%})

**Current Weighting:** {current_weighting:.2f}%
**Previous Weighting:** {prev_weighting_str}

The ETF has {direction} its position by {abs(delta):,} shares.
"""

    payload = {
        "content": f"{emoji} **CNBS ETF Holding Change Alert**",
        "embeds": [{
            "description": description.strip(),
            "color": 0x155724 if delta > 0 else 0x721c24
        }]
    }

    response = requests.post(WEBHOOK_URL, json=payload)
    if response.status_code not in [200, 204]:
        print(f"Failed to send webhook: {response.status_code} {response.text}")

def main():
    print("Fetching CSV...")
    lines = fetch_csv()
    
    print("Parsing CSV...")
    current_holdings = parse_csv(lines)
    
    print("Loading state...")
    state = load_state()
    data = state.setdefault("data", {})
    
    fields = state.get("fields", ["date", "shares", "weighting"])
    shares_idx = fields.index("shares")
    weight_idx = fields.index("weighting")
    
    for ticker, company in TARGET_TICKERS.items():
        if ticker not in current_holdings:
            print(f"Could not find {ticker} in live holdings.")
            continue
            
        current = current_holdings[ticker]
        history = data.get(ticker, [])
        
        # Determine previous state
        previous_data = None
        if history:
            last_entry = history[-1]
            previous_data = {
                "date": last_entry[fields.index("date")] if "date" in fields else "",
                "shares": last_entry[shares_idx],
                "weighting": last_entry[weight_idx]
            }
        
        current_shares = current["shares"]
        
        # Compare and Alert
        if previous_data and current_shares != previous_data["shares"]:
            print(f"Detected change for {ticker}: {previous_data['shares']} -> {current_shares}")
            send_discord_alert(ticker, company, current, previous_data)
        elif not previous_data:
            print(f"First time tracking {ticker}, initializing state without alert.")
            
        # Update state if changed
        if not previous_data or current_shares != previous_data["shares"] or current["weighting"] != previous_data["weighting"]:
            # Append new record
            record = []
            for field in fields:
                record.append(current.get(field, None))
            history.append(record)
            data[ticker] = history
            
    # Save back
    save_state(state)
    print("Done")

if __name__ == "__main__":
    main()
