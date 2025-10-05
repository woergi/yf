import yfinance as yf
import json
import os
from datetime import datetime
import pandas as pd

# --- Konfiguration ---
# Fügen Sie alle gewünschten Ticker-Symbole in diese Liste ein
TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN"] 
OUTPUT_FILE = "data/financial_data.json"
FAILED_TICKERS = [] # Liste zum Speichern fehlgeschlagener Ticker

# Die Listen der zu extrahierenden Felder bleiben unverändert
FIELDS_TO_EXTRACT = {
    "BalanceSheet": [
        "Cash, Cash Equivalents And Short Term Investments", 
        "Receivables", 
        "Current Assets", 
        "Total Non Current Assets", 
        "Total Assets", 
        "Payables", 
        "Current Debt", 
        "Current Liabilities", 
        "Total Non Current Liabilities Net Minority Interest", 
        "Total Liabilities Net Minority Interest", 
        "Stockholders Equity"
    ],
    "IncomeStatement": [
        "Total Revenue", 
        "Gross Profit", 
        "Operating Income", 
        "Pretax Income", 
        "Net Income Continuous Operations", 
        "Net Income Common Stockholders", 
        "Normalized Income", 
        "EBIT", 
        "EBITDA"
    ],
    "CashFlowStatement": [
        "Cash Dividends Paid"
    ]
}

# Stellen Sie sicher, dass der Zielordner existiert
os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

# Hilfsfunktionen (unverändert)

def extract_latest_values(dataframe, fields_list):
    """Extrahiert die neuesten Werte (erste Spalte) für die gegebenen Felder aus dem DataFrame."""
    data = {}
    if dataframe is None or dataframe.empty:
        for field in fields_list:
            data[field] = "N/A - Datenquelle leer"
        return data

    for field in fields_list:
        if field in dataframe.index:
            raw_value = dataframe.loc[field].iloc[0]
            
            if pd.isna(raw_value):
                data[field] = "N/A - Wert fehlt"
            elif isinstance(raw_value, (int, float)):
                data[field] = int(raw_value)
            else:
                data[field] = raw_value
        else:
            data[field] = "N/A - Feld nicht gefunden"
            
    return data

def extract_historical_data(dataframe, fields_list):
    """Extrahiert alle verfügbaren Jahre für die gegebenen Felder."""
    
    historical_data = {}
    if dataframe is None or dataframe.empty:
        return {}

    for date_col in dataframe.columns:
        year = str(date_col.year)
        historical_data[year] = {}
        
        for field in fields_list:
            value = dataframe.loc[field, date_col] if field in dataframe.index else None
            
            if pd.isna(value) or value is None:
                historical_data[year][field] = "N/A"
            elif isinstance(value, (int, float)):
                historical_data[year][field] = int(value)
            else:
                historical_data[year][field] = value
                
    return historical_data

# --- Hauptlogik für einen einzelnen Ticker ---

def fetch_financial_data_for_ticker(ticker_symbol):
    """Ruft alle aktuellen und historischen Daten für ein Ticker-Symbol ab."""
    print(f"Starte Abruf für {ticker_symbol}...")
    
    try:
        # 1. Ticker-Objekt initialisieren
        ticker = yf.Ticker(ticker_symbol)
        
        # 2. Allgemeine Infos abrufen
        info = ticker.info 
        company_name = info.get('longName', 'Name nicht gefunden')

        # 3. Finanzberichte abrufen
        balance_sheet = ticker.balance_sheet
        income_statement = ticker.financials
        cash_flow_statement = ticker.cashflow
        
        # 4. Daten extrahieren und strukturieren
        
        latest_data = {
            "BalanceSheet": extract_latest_values(balance_sheet, FIELDS_TO_EXTRACT["BalanceSheet"]),
            "IncomeStatement": extract_latest_values(income_statement, FIELDS_TO_EXTRACT["IncomeStatement"]),
            "CashFlowStatement": extract_latest_values(cash_flow_statement, FIELDS_TO_EXTRACT["CashFlowStatement"]),
        }

        historical_output = {
            "BalanceSheet": extract_historical_data(balance_sheet, FIELDS_TO_EXTRACT["BalanceSheet"]),
            "IncomeStatement": extract_historical_data(income_statement, FIELDS_TO_EXTRACT["IncomeStatement"]),
            "CashFlowStatement": extract_historical_data(cash_flow_statement, FIELDS_TO_EXTRACT["CashFlowStatement"]),
        }

        return {
            "company_name": company_name,
            "latest_data": latest_data,
            "historical_data": historical_output
        }
        
    except Exception as e:
        print(f"FEHLER beim Abrufen der Daten für {ticker_symbol}: {e}")
        FAILED_TICKERS.append(ticker_symbol)
        return None

# --- Hauptprogramm ---

if __name__ == "__main__":
    final_output = {
        "metadata": {
            "date_fetched": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "tickers_requested": len(TICKERS)
        },
        "companies": {} # Hier werden die Daten pro Ticker gespeichert
    }
    
    # Durchläuft jeden Ticker in der Liste
    for ticker_symbol in TICKERS:
        data = fetch_financial_data_for_ticker(ticker_symbol)
        if data:
            final_output["companies"][ticker_symbol] = data
    
    # Aktualisiert die Metadaten mit dem Ergebnis
    final_output["metadata"]["tickers_succeeded"] = len(final_output["companies"])
    final_output["metadata"]["tickers_failed"] = FAILED_TICKERS
    
    # Daten speichern
    try:
        with open(OUTPUT_FILE, 'w') as f:
            json.dump(final_output, f, indent=4)
            
        print("\n=============================================")
        print(f"✅ FINALE AUSGABE: {len(final_output['companies'])} Ticker erfolgreich gespeichert.")
        if FAILED_TICKERS:
            print(f"❌ Folgende Ticker sind fehlgeschlagen: {', '.join(FAILED_TICKERS)}")
        print("=============================================")
            
    except Exception as e:
        print(f"KRITISCHER FEHLER beim Speichern der finalen JSON-Datei: {e}")
        exit(1)

