"""Request driver — runs INSIDE the sandbox network (harness image, Python 3 standard library only).

    python driver.py wait <url> <seconds>
    python driver.py http <base url> <requests.jsonl> <responses.jsonl>

One response line per request, in order, with sorted keys, so two runs of the same system on the
same inputs produce comparable files. Only the status, the content type and the body are kept:
transport headers (Date, Server) are not the system's behaviour.
"""
import json
import sys
import time
import urllib.error
import urllib.request


def _body(raw, content_type):
    text = raw.decode("utf-8", errors="replace")
    if "json" in (content_type or ""):
        try:
            return json.loads(text)
        except ValueError:
            pass
    return {"_text": text}


def send(base, req):
    data = req.get("body")
    headers = dict(req.get("headers") or {})
    if isinstance(data, (dict, list)):
        data = json.dumps(data).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    elif isinstance(data, str):
        data = data.encode("utf-8")
    request = urllib.request.Request(base + req["path"], data=data, method=req["method"].upper(), headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as r:
            status, ctype, raw = r.status, r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as e:
        status, ctype, raw = e.code, e.headers.get("Content-Type", ""), e.read()
    except Exception as e:  # noqa: BLE001 — recorded as behaviour: the system did not answer
        return {"request": {"method": req["method"].upper(), "path": req["path"]}, "error": type(e).__name__}
    return {"request": {"method": req["method"].upper(), "path": req["path"]}, "status": status,
            "contentType": (ctype or "").split(";")[0].strip(), "body": _body(raw, ctype)}


def main(argv):
    if argv[1] == "wait":
        deadline = time.time() + float(argv[3])
        while time.time() < deadline:
            try:
                urllib.request.urlopen(argv[2], timeout=2).read()
                return 0
            except urllib.error.HTTPError:
                return 0  # it answered
            except Exception:  # noqa: BLE001
                time.sleep(0.5)
        return 1
    if argv[1] == "http":
        with open(argv[3], encoding="utf-8") as f, open(argv[4], "w", encoding="utf-8") as out:
            for line in f:
                if line.strip():
                    out.write(json.dumps(send(argv[2], json.loads(line)), sort_keys=True) + "\n")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
