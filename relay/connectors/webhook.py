"""HTTP/webhook connector — lets a task notify some external endpoint (Slack incoming
webhook, a CI trigger, your own API, etc.) when a run finishes or a step completes."""

import requests


def send_webhook(url: str, payload: dict, timeout: int = 15) -> dict:
    resp = requests.post(url, json=payload, timeout=timeout)
    return {"status_code": resp.status_code, "body": resp.text[:2000]}
