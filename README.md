# openF1 Workspace

The complete documentation for the OpenF1 API itself, including all available API resources and endpoints, can be found here:

https://openf1.org/

## Installation

Requirements:

- Python 3.9 or newer
- optionally Node.js, if the Angular frontend should be rebuilt locally

Install and start the backend:

```bash
pip install -r requirements.txt
python main.py
```

### OAuth and Live Data

If OAuth is required for accessing live data, the configuration must be provided in:

```text
config/openf1.auth.ini
```

An OpenF1 account and the appropriate API access may be required to use live sessions.

You can register for the OpenF1 API and subscribe to the available paid API plans here:

https://openf1.org/

The availability of live data, subscription plans, pricing, and API access conditions are defined and managed exclusively by OpenF1 and may change at any time.

This project is not affiliated with OpenF1's pricing decisions and assumes **no responsibility or liability for OpenF1 pricing, subscription fees, pricing changes, subscription conditions, or the availability of OpenF1 services**.

If the Angular frontend should be rebuilt on the target system:

```bash
cd angular-frontend
npm install
```

## Quick Start

```python
import f1_sdk as f1

session = f1.session.latest()
print(session.meeting_key)

drivers = f1.driver.all(session_key=session.session_key)
```
