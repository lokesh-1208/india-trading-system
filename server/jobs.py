"""Long downloads run in the background while the page shows their progress.

Only one job runs at a time. The page asks for the status every second or so.
"""

import threading
import time
import traceback

from trading import update

from server.store import STORE

KINDS = {
    "daily": ("Update data", lambda report: update.run_update(report=report)),
    "premarket": ("Refresh before open", lambda report: update.run_premarket(report)),
    "full_prices": ("Download full price history",
                    lambda report: update.run_update(report=report, full_prices=True,
                                                     include_company_data=False)),
    "company": ("Refresh all company results",
                lambda report: update.refresh_company_data(report, everything=True,
                                                           include_shareholding=True)),
}


class Jobs:
    def __init__(self):
        self._lock = threading.Lock()
        self.state = {"running": False, "kind": None, "label": None, "step": None, "done": 0,
                      "total": 0, "started": None, "finished": None, "message": None,
                      "error": None}

    def snapshot(self):
        with self._lock:
            state = dict(self.state)
        if state["running"] and state["started"]:
            state["seconds"] = round(time.time() - state["started"])
        return state

    def start(self, kind):
        if kind not in KINDS:
            raise ValueError(f"Unknown job: {kind}")
        with self._lock:
            if self.state["running"]:
                return False
            label, work = KINDS[kind]
            self.state.update(running=True, kind=kind, label=label, step="Starting", done=0,
                              total=0, started=time.time(), finished=None, message=None,
                              error=None)
        threading.Thread(target=self._run, args=(work,), daemon=True).start()
        return True

    def _report(self, step, done, total):
        with self._lock:
            self.state.update(step=step, done=done, total=total)

    def _run(self, work):
        try:
            summary = work(self._report)
            message = _describe(summary)
            error = None
        except Exception as exc:          # shown on the page, kept for the log
            message, error = None, f"{exc}"
            traceback.print_exc()
        STORE.clear()
        with self._lock:
            self.state.update(running=False, finished=time.time(), message=message, error=error)


def _describe(summary):
    parts = []
    seconds = summary.get("seconds")
    if seconds is not None:
        parts.append(f"Done in {seconds // 60} min {seconds % 60} s." if seconds >= 60
                     else f"Done in {seconds} s.")
    if summary.get("prices"):
        parts.append(update.describe_prices(summary["prices"]))
    if summary.get("failed_markets"):
        parts.append("No data for: " + ", ".join(summary["failed_markets"]) + ".")
    if summary.get("news_added") is not None and not summary.get("news_problem"):
        parts.append(f"{summary['news_added']} new announcements.")
    if summary.get("news_problem") or summary.get("flows_problem"):
        parts.append("Some NSE downloads did not work; they are retried next time.")
    if summary.get("filings_companies"):
        parts.append(f"Result filings checked for {summary['filings_companies']} companies.")
    if summary.get("preopen"):
        parts.append("NSE pre-open prices saved.")
    elif "preopen" in summary:
        parts.append("NSE pre-open prices come after 9:08 am.")
    if summary.get("results_problem") or summary.get("shareholding_problem"):
        parts.append("Company data did not finish; it continues on the next update.")
    return " ".join(parts) or "Done."


JOBS = Jobs()
