# openF1 Workspace

Die vollstaendige Dokumentation zur Facade und allen Resources findest du hier:


## Installation

Voraussetzungen:

- Python 3.9 oder neuer
- optional Node.js, falls das Angular-Frontend lokal neu gebaut werden soll

Backend installieren und starten:

```bash
pip install -r requirements.txt
python main.py
```

Falls OAuth fuer Live-Daten genutzt werden soll, muss die Konfiguration in `config/openf1.auth.ini` gesetzt werden.

Falls das Angular-Frontend auf dem Zielsystem neu gebaut werden soll:

```bash
cd angular-frontend
npm install
```

## Kurzstart

```python
import f1_sdk as f1

session = f1.session.latest()
print(session.meeting_key)

drivers = f1.driver.all(session_key=session.session_key)
```
