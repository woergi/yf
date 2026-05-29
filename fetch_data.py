import argparse
import yfinance as yf
import json
import os
import time
import pandas as pd
from datetime import datetime, timedelta

OUTPUT_FILE = "data/financial_data.json"
MAX_RUNTIME_SECONDS = 55 * 60  # 55 Minuten – Puffer vor GitHub's 60-Min-Limit
STALENESS_DAYS = 14
DELAY_BETWEEN_REQUESTS = 3  # Sekunden zwischen API-Calls

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


def get_sp500_tickers():
    """Lädt die S&P 500 Ticker-Liste von Wikipedia."""
    import io
    import requests as req

    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; sp500-fetcher/1.0)"}

    try:
        response = req.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        tables = pd.read_html(io.StringIO(response.text))
        df = tables[0]
        tickers = df["Symbol"].tolist()
        # Wikipedia nutzt Punkte statt Bindestriche (z.B. BRK.B → BRK-B)
        tickers = [t.replace(".", "-") for t in tickers]
        print(f"S&P 500: {len(tickers)} Ticker von Wikipedia geladen.")
        return sorted(tickers)
    except Exception as e:
        print(f"Wikipedia-Abruf fehlgeschlagen ({e}). Kein Fallback verfügbar.")
        return []


def load_existing_data():
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r") as f:
            return json.load(f)
    return {"metadata": {}, "companies": {}}


def save_data(data):
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(data, f, indent=4)


def is_fresh(company_data):
    """Gibt True zurück wenn der Eintrag jünger als STALENESS_DAYS ist."""
    ts = company_data.get("last_updated")
    if not ts:
        return False
    try:
        last_updated = datetime.fromisoformat(ts)
        return datetime.now() - last_updated < timedelta(days=STALENESS_DAYS)
    except ValueError:
        return False


def extract_latest_values(dataframe, fields_list):
    data = {}
    if dataframe is None or dataframe.empty:
        return {field: "N/A - Datenquelle leer" for field in fields_list}
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
    historical_data = {}
    if dataframe is None or dataframe.empty:
        return {}
    for date_col in dataframe.columns:
        year = str(date_col.year)
        historical_data[year] = {}
        for field in fields_list:
            value = dataframe.loc[field, date_col] if field in dataframe.index else None
            if value is None or pd.isna(value):
                historical_data[year][field] = "N/A"
            elif isinstance(value, (int, float)):
                historical_data[year][field] = int(value)
            else:
                historical_data[year][field] = value
    return historical_data


def refresh_sp500_list(output):
    """Aktualisiert die S&P 500 Liste wenn sie älter als STALENESS_DAYS ist."""
    last_fetched = output.get("metadata", {}).get("sp500_last_fetched")
    if last_fetched:
        try:
            age = datetime.now() - datetime.fromisoformat(last_fetched)
            if age < timedelta(days=STALENESS_DAYS):
                print(f"S&P 500 Liste aktuell (Stand: {last_fetched}).\n")
                return
        except ValueError:
            pass

    tickers = get_sp500_tickers()
    if not tickers:
        print("S&P 500 Liste konnte nicht aktualisiert werden – nutze bestehende Einträge.\n")
        return

    added = sum(1 for t in tickers if t not in output["companies"])
    for ticker in tickers:
        if ticker not in output["companies"]:
            output["companies"][ticker] = {}

    output["metadata"]["sp500_last_fetched"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    output["metadata"]["sp500_total"] = len(tickers)
    print(f"S&P 500 Liste aktualisiert: {len(tickers)} Ticker ({added} neu hinzugefügt).\n")


def fetch_ticker(ticker_symbol):
    """Ruft alle Finanzdaten für ein einzelnes Ticker-Symbol ab."""
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        company_name = info.get("longName", "Name nicht gefunden")

        balance_sheet = ticker.balance_sheet
        income_statement = ticker.financials
        cash_flow_statement = ticker.cashflow

        latest_data = {
            "BalanceSheet": extract_latest_values(balance_sheet, FIELDS_TO_EXTRACT["BalanceSheet"]),
            "IncomeStatement": extract_latest_values(income_statement, FIELDS_TO_EXTRACT["IncomeStatement"]),
            "CashFlowStatement": extract_latest_values(cash_flow_statement, FIELDS_TO_EXTRACT["CashFlowStatement"]),
            "Valuation": {
                "Price Earnings Ratio": info.get("trailingPE") or info.get("forwardPE") or "N/A",
                "Price to Book Ratio": info.get("priceToBook") or "N/A",
                "Dividend Yield": info.get("dividendYield") or "N/A"
            }
        }

        historical_output = {
            "BalanceSheet": extract_historical_data(balance_sheet, FIELDS_TO_EXTRACT["BalanceSheet"]),
            "IncomeStatement": extract_historical_data(income_statement, FIELDS_TO_EXTRACT["IncomeStatement"]),
            "CashFlowStatement": extract_historical_data(cash_flow_statement, FIELDS_TO_EXTRACT["CashFlowStatement"]),
        }

        historical_valuation = {}
        for year in historical_output["IncomeStatement"].keys():
            historical_valuation[year] = {
                "Price Earnings Ratio": "N/A (Historische Berechnung nötig)",
                "Price to Book Ratio": "N/A (Historische Berechnung nötig)"
            }
        historical_output["Valuation"] = historical_valuation
        
        print(f"  Erfolgreich: {ticker_symbol}")

        return {
            "company_name": company_name,
            "last_updated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "latest_data": latest_data,
            "historical_data": historical_output
        }

    except Exception as e:
        print(f"  FEHLER bei {ticker_symbol}: {e}")
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="S&P 500 Finanzdaten-Abruf")
    parser.add_argument("-n", "--num-tickers", type=int, default=None,
                        metavar="N", help="Nur N Ticker abrufen (zum Testen)")
    args = parser.parse_args()

    run_start = time.time()
    run_start_dt = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    print("=== S&P 500 Finanzdaten-Abruf gestartet ===")
    print(f"Start: {run_start_dt}")
    if args.num_tickers:
        print(f"TEST-MODUS: Maximal {args.num_tickers} Ticker")
    else:
        print(f"Maximale Laufzeit: {MAX_RUNTIME_SECONDS // 60} Minuten")
    print(f"Daten älter als {STALENESS_DAYS} Tage werden aktualisiert\n")

    # Bestehende Daten laden (für Resume-Funktion)
    output = load_existing_data()
    if "companies" not in output:
        output["companies"] = {}
    if "metadata" not in output:
        output["metadata"] = {}

    # S&P 500 Liste prüfen und ggf. aktualisieren (max. alle 14 Tage)
    refresh_sp500_list(output)
    save_data(output)

    if not output["companies"]:
        print("ABBRUCH: Keine Ticker vorhanden.")
        exit(1)

    all_tickers = sorted(output["companies"])

    # Zähler für diese Runde
    updated = 0
    skipped_fresh = 0
    failed = []

    for ticker_symbol in all_tickers:
        if args.num_tickers and updated >= args.num_tickers:
            print(f"\nTest-Limit von {args.num_tickers} Ticker(n) erreicht.")
            break

        elapsed = time.time() - run_start

        if elapsed >= MAX_RUNTIME_SECONDS:
            print(f"\nZeitlimit erreicht ({MAX_RUNTIME_SECONDS // 60} Min.). Nächster Start setzt fort.")
            break

        existing = output["companies"].get(ticker_symbol, {})

        if is_fresh(existing):
            skipped_fresh += 1
            continue

        data = fetch_ticker(ticker_symbol)

        if data:
            output["companies"][ticker_symbol] = data
            updated += 1
            # Nach jedem Ticker speichern – kein Datenverlust bei Abbruch
            save_data(output)
        else:
            failed.append(ticker_symbol)

        time.sleep(DELAY_BETWEEN_REQUESTS)

    # Metadaten aktualisieren (sp500_last_fetched und sp500_total bleiben erhalten)
    elapsed_total = time.time() - run_start
    output["metadata"].update({
        "last_run": run_start_dt,
        "last_run_duration_seconds": int(elapsed_total),
        "total_stored": len(output["companies"]),
        "last_run_updated": updated,
        "last_run_skipped_fresh": skipped_fresh,
        "last_run_failed": failed
    })
    save_data(output)

    sp500_total = output["metadata"].get("sp500_total", "?")
    print("\n=== Zusammenfassung ===")
    print(f"Laufzeit:           {int(elapsed_total // 60)}m {int(elapsed_total % 60)}s")
    print(f"Aktualisiert:       {updated}")
    print(f"Übersprungen:       {skipped_fresh} (aktuell)")
    print(f"Fehlgeschlagen:     {len(failed)}")
    print(f"Gesamt gespeichert: {len(output['companies'])} / {sp500_total} S&P 500")
    if failed:
        print(f"Fehler bei: {', '.join(failed)}")
