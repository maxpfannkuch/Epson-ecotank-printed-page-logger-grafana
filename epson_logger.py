#!/usr/bin/env python3
import os, sys, json, time, socket, re
import datetime as dt
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
import gspread
from google.oauth2.service_account import Credentials
from requests.exceptions import RequestException
from urllib3.exceptions import InsecureRequestWarning

# Unterdrücke SSL-Warnungen, wenn VERIFY_SSL=False
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

# ---------- Konfiguration ----------
def load_settings(path="settings.json"):
    if not os.path.exists(path):
        print(f"FEHLER: {path} nicht gefunden.", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    for r in ["USAGE_URL", "SPREADSHEET_ID", "GOOGLE_CREDS_JSON"]:
        if not cfg.get(r):
            print(f"FEHLER: '{r}' fehlt in {path}.", file=sys.stderr)
            sys.exit(1)
    cfg.setdefault("VERIFY_SSL", False)
    cfg.setdefault("WORKSHEET", "UsageLog")
    cfg.setdefault("LOCAL_BACKUP_FILE", "usage_log.ndjson")
    cfg.setdefault("PRINTER_IP", "")
    cfg.setdefault("TIMEZONE", "Europe/Berlin")
    return cfg

# ---------- HTTP ----------
def fetch_html(url, verify_ssl, timeout=12):
    s = requests.Session()
    s.verify = verify_ssl
    r = s.get(url, headers={"User-Agent": "printer-usage-logger"}, timeout=timeout)
    r.raise_for_status()
    return r.text

# ---------- Key-Normalisierung ----------
def norm_key(s: str) -> str:
    if s is None:
        return ""
    s = s.replace("\xa0", " ").replace("：", ":")
    s = re.sub(r"\s+", " ", s).strip()
    s = s.rstrip(" :")
    return s

# ---------- Parsing ----------
def parse_all_kv(soup: BeautifulSoup) -> dict:
    """Kombiniert dt/dd, 2-spaltige Tabellen und 1-Zellen-„Key: Value“."""
    data = {}

    # 1) dl/dt/dd
    for dl in soup.find_all("dl"):
        dts = dl.find_all("dt")
        dds = dl.find_all("dd")
        for dt_el, dd_el in zip(dts, dds):
            k = norm_key(dt_el.get_text(" ", strip=True))
            v = dd_el.get_text(" ", strip=True).strip()
            if k:
                data[k] = v

    # 2) Tabellen: 2-spaltig
    for tr in soup.find_all("tr"):
        tds = tr.find_all(["td", "th"])
        if len(tds) == 2:
            k = norm_key(tds[0].get_text(" ", strip=True))
            v = tds[1].get_text(" ", strip=True).strip()
            if k:
                data.setdefault(k, v)

    # 3) Tabellen: 1 Zelle "Key: Value"
    for tr in soup.find_all("tr"):
        tds = tr.find_all(["td", "th"])
        if len(tds) == 1:
            txt = tds[0].get_text(" ", strip=True).replace("：", ":")
            if ":" in txt:
                k, v = txt.split(":", 1)
                k = norm_key(k)
                if k:
                    data.setdefault(k, v.strip())

    return data

def extract_key_values(url: str, html: str, verify_ssl: bool) -> dict:
    """Parst Seite und folgt Frames/iframes; liefert das reichste Datenset."""
    soup = BeautifulSoup(html, "lxml")
    best = parse_all_kv(soup)
    best_count = len(best)

    for fr in soup.find_all(["frame", "iframe"]):
        src = fr.get("src") or ""
        if not src:
            continue
        abs_url = urljoin(url, src)
        try:
            inner_html = fetch_html(abs_url, verify_ssl=verify_ssl)
            inner_soup = BeautifulSoup(inner_html, "lxml")
            cand = parse_all_kv(inner_soup)
            if len(cand) > best_count:
                best, best_count = cand, len(cand)
        except Exception:
            continue

    if best_count < 5:
        try:
            with open("last_response.html", "w", encoding="utf-8") as f:
                f.write(html)
        except Exception:
            pass
    return best

# ---------- Google Sheets ----------
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def open_worksheet(spreadsheet_id, worksheet_name, creds_json_path):
    creds = Credentials.from_service_account_file(creds_json_path, scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(spreadsheet_id)
    try:
        ws = sh.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=worksheet_name, rows=200, cols=50)
    return ws

def ensure_header(ws, keys):
    header = ws.row_values(1)
    if not header:
        header = ["timestamp", "page_url", "printer_ip"] + sorted(keys)
        ws.update("A1", [header])
        return header
    missing = [k for k in sorted(keys) if k not in header]
    if missing:
        header += missing
        ws.update("A1", [header])
    return header

def append_row(ws, header, values_dict, usage_url, printer_ip):
    now = dt.datetime.now(dt.timezone.utc).astimezone().isoformat()
    row = []
    for col in header:
        if col == "timestamp":
            row.append(now)
        elif col == "page_url":
            row.append(usage_url)
        elif col == "printer_ip":
            row.append(printer_ip or "")
        else:
            row.append(values_dict.get(col, ""))
    ws.append_row(row, value_input_option="RAW")

# ---------- Lokaler Puffer ----------
def write_local_backup(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

def read_local_backups(path):
    items = []
    if not os.path.exists(path):
        return items
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and isinstance(obj.get("data"), dict):
                items.append(obj)
    return items

def rewrite_local_backups(path, entries):
    with open(path, "w", encoding="utf-8") as f:
        for obj in entries:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

# ---------- Netzwerk-Checks ----------
def host_reachable(host, port=80, timeout=2):
    if not host:
        return True
    try:
        socket.setdefaulttimeout(timeout)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((host, port))
        return True
    except Exception:
        return False

# ---------- Upload aller offenen Einträge ----------
def try_upload_all(cfg, first_record_keys=None):
    pending = read_local_backups(cfg["LOCAL_BACKUP_FILE"])
    if not pending:
        return True
    ws = open_worksheet(cfg["SPREADSHEET_ID"], cfg["WORKSHEET"], cfg["GOOGLE_CREDS_JSON"])
    if first_record_keys:
        ensure_header(ws, first_record_keys)
    left = []
    for entry in pending:
        try:
            keys = entry["data"].keys()
            header = ensure_header(ws, keys)
            append_row(ws, header, entry["data"], entry.get("page_url",""), entry.get("printer_ip",""))
        except Exception:
            left.append(entry)
    rewrite_local_backups(cfg["LOCAL_BACKUP_FILE"], left)
    return len(left) == 0

# ---------- Hauptschleife ----------
def main_loop():
    cfg = load_settings()
    usage_url  = cfg["USAGE_URL"]
    verify_ssl = bool(cfg["VERIFY_SSL"])
    printer_ip = cfg.get("PRINTER_IP", "")

    interval_main       = 1800  # 30 Minuten
    printer_tries       = 5    # max. Versuche pro Intervall
    printer_retry_delay = 60   # 60 Sekunden
    upload_retry_total  = 600  # bis zu 10 Min. Upload-Versuche
    upload_retry_step   = 30   # alle 30 Sek.

    print("Logger gestartet – läuft dauerhaft. Beenden mit Ctrl+C")

    while True:
        got_data = False
        last_keys = None

        # --- Drucker mehrfach versuchen ---
        for attempt in range(1, printer_tries + 1):
            try:
                if not host_reachable(printer_ip, 443, 2):
                    raise Exception("Drucker nicht erreichbar")
                html = fetch_html(usage_url, verify_ssl=verify_ssl, timeout=12)
                kv = extract_key_values(usage_url, html, verify_ssl)
                payload = {
                    "timestamp": dt.datetime.now().isoformat(),
                    "page_url": usage_url,
                    "printer_ip": printer_ip,
                    "data": kv
                }
                write_local_backup(cfg["LOCAL_BACKUP_FILE"], payload)
                print(f"[{dt.datetime.now()}] Druckerdaten gespeichert ({len(kv)} Werte)")
                got_data = True
                last_keys = kv.keys()
                break
            except Exception as e:
                print(f"[{dt.datetime.now()}] Drucker-Versuch {attempt}/{printer_tries} fehlgeschlagen: {e}")
                if attempt < printer_tries:
                    time.sleep(printer_retry_delay)

        if not got_data:
            # Offline-Marker
            write_local_backup(cfg["LOCAL_BACKUP_FILE"], {
                "timestamp": dt.datetime.now().isoformat(),
                "page_url": usage_url,
                "printer_ip": printer_ip,
                "data": {},
                "note": "printer_offline"
            })
            print(f"[{dt.datetime.now()}] Drucker offline – Offline-Eintrag gespeichert")

        # --- Uploadfenster: bis zu 10 Minuten wiederholt probieren ---
        deadline = time.time() + upload_retry_total
        uploaded_once = False
        while time.time() < deadline:
            try:
                if try_upload_all(cfg, first_record_keys=last_keys):
                    print(f"[{dt.datetime.now()}] Google-Upload erfolgreich – alle offenen Einträge übertragen")
                    uploaded_once = True
                    break
                else:
                    print(f"[{dt.datetime.now()}] Teilweise übertragen – erneut versuchen …")
            except Exception as e:
                print(f"[{dt.datetime.now()}] Google-Upload fehlgeschlagen: {e}")
            time.sleep(upload_retry_step)

        if not uploaded_once:
            print(f"[{dt.datetime.now()}] In diesem Intervall kein vollständiger Upload – später erneut")

        time.sleep(interval_main)

if __name__ == "__main__":
    main_loop()
