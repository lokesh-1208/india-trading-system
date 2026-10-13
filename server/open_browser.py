"""Open Kasauti in the browser as soon as the server answers (used by start_kasauti.bat).

Waits up to three minutes: the first start installs libraries and reads all the data.
"""

import time
import urllib.request
import webbrowser

ADDRESS = "http://127.0.0.1:8765"

for _ in range(180):
    try:
        with urllib.request.urlopen(ADDRESS + "/api/jobs", timeout=2):
            break
    except Exception:
        time.sleep(1)
webbrowser.open(ADDRESS)
