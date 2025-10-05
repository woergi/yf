import yfinance as yf
import json
import os
from datetime import datetime

# --- Konfiguration ---
TICKER = "AAPL"
OUTPUT_FILE = "data/financial_data.json"
DATA_FIELD = "Current Assets" # Der Bilanzposten, den wir wollen

# Stellen Sie sicher, dass der Zielordner existiert
os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

try:
    # 1. Daten abrufen
    ticker = yf.Ticker(TICKER)
    
    # Ruft die Bilanz (Balance Sheet) als Pandas DataFrame ab
    balance_sheet = ticker.balance_sheet
    
    # 2. Daten verarbeiten
    # Wählt den gewünschten Posten aus und nimmt den aktuellsten Wert (erste Spalte)
    if DATA_FIELD in balance_sheet.index:
        current_assets_value = balance_sheet.loc[DATA_FIELD].iloc[0]
    else:
        # Fallback oder Fehler bei fehlendem Feld (z.B. bei Quartalsdaten)
        current_assets_value = "N/A"
        
    # 3. JSON-Struktur erstellen
    data_output = {
        "ticker": TICKER,
        "date_fetched": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "current_assets": int(current_assets_value) if isinstance(current_assets_value, (int, float)) else current_assets_value,
        "source": "Yahoo Finance via yfinance"
    }

    # 4. Daten speichern
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(data_output, f, indent=4)
        
    print(f"Daten für {TICKER} erfolgreich in {OUTPUT_FILE} gespeichert.")

except Exception as e:
    print(f"Fehler beim Abrufen der Daten: {e}")
    # Beenden Sie das Skript mit einem Fehlercode, wenn der Abruf fehlschlägt
    exit(1)

