# Epson-ecotank-printed-page-logger-grafana
# Epson Printer Usage Logger

Der Epson Usage Logger liest periodisch Nutzungsdaten eines Epson-Druckers aus dem lokalen Netzwerk aus und speichert sie in einem Google Sheet. Das System ist für den Dauerbetrieb ausgelegt, läuft auf einem Raspberry Pi und ist widerstandsfähig gegenüber Netzwerk- und Geräteausfällen. Optional können die Daten in Grafana visualisiert werden.

Dieses Projekt eignet sich zur Langzeitüberwachung von Druckvolumen, Farbverbrauch, Seitenzählern und anderen Nutzungsmetriken.

---

## Funktionen

- Regelmäßiges Auslesen der Druckerstatus-Webseite.
- Unterstützung typischer Epson-Informationsseiten wie Nutzungsstatistiken, Zählerstände und Druckeigenschaften.
- Fallback-Mechanismen bei Drucker- oder Internet-Ausfall.
- Speicherung aller ausgelesenen Werte in einer lokalen NDJSON-Datei (Queue).
- Automatischer Upload aller ausstehenden Datensätze zu Google Sheets.
- Automatische Erweiterung der Tabellenzeilen um neue Schlüssel.
- Vollständig automatisierbar über systemd, kein Cron erforderlich.
- Optional: Einbindung der Daten in Grafana zur Visualisierung.

---

## Grafana-Integration

Die gesammelten Daten können in Grafana dargestellt werden. Die Integration erfolgt entweder direkt über ein Google Sheets Plugin oder über eine weitere Datenbank wie InfluxDB, Prometheus oder SQLite, in die die Daten regelmäßig exportiert werden können.

Typische Visualisierungen:

- Entwicklung der gedruckten Seitenzahlen über Zeit.
- Vergleich einseitiger und zweiseitiger Ausdrucke.
- Farbverbrauch und Füllstände.
- Druckvolumen nach Tagen, Wochen oder Monaten.
- Status des Druckers (online/offline).

---

## Unterstützte Geräte

Dieses Projekt wurde mit einem Epson ET-2860 getestet, sollte aber mit allen Epson-Druckern funktionieren, die eine HTML-basierte Nutzungsseite bereitstellen.

---

## Voraussetzungen

- Raspberry Pi (oder vergleichbares Linux-System)
- Python 3.9 oder höher
- Epson-Drucker im lokalen Netzwerk
- Google Cloud Service Account mit Zugriff auf Sheets API
- Ein Google Sheet zur Datenspeicherung
- Optional: Grafana Server zur Visualisierung

---

## Installation

### 1. Repository klonen
```
git clone https://github.com/DEIN_USERNAME/epson-logger.git
cd epson-logger
```

### 2. Virtuelle Umgebung erstellen
```
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Abhängigkeiten installieren
```
pip install -r requirements.txt
```

---

## Konfiguration

### 1. Beispiel-Settings kopieren
```
cp settings.example.json settings.json
```

### 2. `settings.json` bearbeiten
```
nano settings.json
```

Die Datei enthält unter anderem die URL der Druckerseite, die Spreadsheet-ID und den Pfad zur Service-Account-Datei.

---

## Google-Credentials

Eine Datei namens `credentials.json` muss im Projektverzeichnis abgelegt werden. Diese Datei enthält die privaten Service-Account-Schlüssel für den Zugriff auf Google Sheets.

Diese Datei darf niemals veröffentlicht oder in einem Repository versioniert werden.

---

## Starten des Loggers

### Manuell
```
source .venv/bin/activate
python epson_logger.py
```

Der Logger startet und läuft dauerhaft, bis er per Tastaturunterbrechung beendet wird.

---

## Einrichtung als systemd-Service

Eine systemd-Service-Datei ermöglicht den automatischen Start beim Booten.

### 1. Service-Datei erstellen
```
sudo nano /etc/systemd/system/epson-logger.service
```

### 2. Inhalt einfügen
```
[Unit]
Description=Epson Usage Logger
After=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/epson-logger
ExecStart=/home/pi/epson-logger/.venv/bin/python /home/pi/epson-logger/epson_logger.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 3. Aktivieren und starten
```
sudo systemctl daemon-reload
sudo systemctl enable epson-logger.service
sudo systemctl start epson-logger.service
```

### 4. Status prüfen
```
sudo systemctl status epson-logger.service
```

---

## Dateistruktur

```
epson-logger/
├── epson_logger.py
├── settings.example.json
├── credentials.example.json
└── README.md
```

---

## Sicherheitshinweise

Folgende Dateien dürfen niemals in ein öffentliches Repository gelangen:

- settings.json
- credentials.json
- usage_log.ndjson
- last_response.html

Sie enthalten private Schlüssel, interne IP-Adressen und möglicherweise sensible Druckerlivedaten.  
Diese Dateien werden standardmäßig in `.gitignore` ausgeschlossen.

---

## Beiträge

Fehlerberichte, Verbesserungsvorschläge und Pull Requests sind willkommen.

---

## Lizenz

MIT License
