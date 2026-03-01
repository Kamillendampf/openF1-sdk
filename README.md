# openF1 Workspace

Die vollständige Dokumentation zur Facade und allen Resources findest du hier:

- [f1-sdk/README.md](E:/dev/Nexora/openF1/f1-sdk/README.md)

Kurzstart:

```python
import f1_sdk as f1

session = f1.session.latest()
print(session.meeting_key)

drivers = f1.driver.all(session_key=session.session_key)
```
