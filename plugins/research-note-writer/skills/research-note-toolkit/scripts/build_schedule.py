# -*- coding: utf-8 -*-
"""Build a research-note writing schedule from a config.json roster.

Generates one entry per participating researcher per month, spread across the
month so that only 1-2 people write in any given calendar week. Record dates are
weekdays only (national holidays excluded). Confirmation dates fall a configurable
number of workdays after the record date.

Usage:
    python build_schedule.py config.json [out_dir]

Outputs (in out_dir, default "."):
    schedule.json          - full chronological list with a 1-based "page" index
    schedule.csv           - human-readable table
    entries_by_writer.json - same entries grouped by writer name
"""
import sys, os, json, csv, math
import datetime as dt

try:
    import holidays
except ImportError:
    sys.exit("Install the 'holidays' package:  pip install holidays")


def ym(s):
    y, m = s.split("-")
    return int(y) * 12 + int(m) - 1  # month index


def month_range(start, end):
    a, b = ym(start), ym(end)
    for k in range(a, b + 1):
        yield k // 12, k % 12 + 1


def load_holidays(country, years):
    try:
        return holidays.country_holidays(country, years=years)
    except Exception:
        return holidays.HolidayBase()  # empty -> weekends only


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cfg = json.load(open(sys.argv[1], encoding="utf-8"))
    out = sys.argv[2] if len(sys.argv) > 2 else "."
    os.makedirs(out, exist_ok=True)

    period = cfg["period"]
    years = list(range(int(period["start"][:4]), int(period["end"][:4]) + 1))
    KR = load_holidays(period.get("holidays_country", "KR"), years)

    def is_workday(d):
        return d.weekday() < 5 and d not in KR

    def workdays(y, m):
        d = dt.date(y, m, 1); res = []
        while d.month == m:
            if is_workday(d):
                res.append(d)
            d += dt.timedelta(days=1)
        return res

    gap_lo, gap_hi = cfg.get("schedule", {}).get("confirm_gap_days", [5, 10])

    def confirm_date(rec):
        for off in range(gap_lo, gap_hi + 1):
            c = rec + dt.timedelta(days=off)
            if is_workday(c):
                return c
        c = rec + dt.timedelta(days=gap_hi + 1)          # fall back past the window
        while not is_workday(c):
            c += dt.timedelta(days=1)
        return c

    roster = cfg["roster"]

    def active(y, m):
        idx = y * 12 + m - 1
        return [r for r in roster if ym(r["start"]) <= idx <= ym(r["end"])]

    def confirmer(y, m):
        idx = y * 12 + m - 1
        for c in cfg["confirmers"]:
            if ym(c["start"]) <= idx <= ym(c["end"]):
                return c["name"]
        return ""

    rows = []
    for y, m in month_range(period["start"], period["end"]):
        writers = active(y, m)                 # roster order controls week placement
        wd = workdays(y, m); n = len(writers)
        for i, r in enumerate(writers):
            pos = min(int((i + 0.5) / n * len(wd)), len(wd) - 1)  # even spread
            rec = wd[pos]; conf = confirm_date(rec)
            rows.append({"rec": rec, "conf": conf, "writer": r["name"],
                         "confirmer": confirmer(y, m), "source": r.get("source", ""),
                         "year": y, "month": m})
    rows.sort(key=lambda r: r["rec"])

    seq = {}
    full = []
    for pg, r in enumerate(rows, 1):
        seq[r["writer"]] = seq.get(r["writer"], 0) + 1
        full.append({"page": pg, "seq": seq[r["writer"]],
                     "rec": r["rec"].strftime("%Y. %m. %d."),
                     "conf": r["conf"].strftime("%Y. %m. %d."),
                     "writer": r["writer"], "confirmer": r["confirmer"],
                     "source": r["source"], "year": r["year"], "month": r["month"]})

    json.dump(full, open(os.path.join(out, "schedule.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    by = {}
    for e in full:
        by.setdefault(e["writer"], []).append(e)
    json.dump(by, open(os.path.join(out, "entries_by_writer.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    with open(os.path.join(out, "schedule.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["page", "기록일자", "확인일자", "기록자", "확인자", "내용근거", "연", "월"])
        for e in full:
            w.writerow([e["page"], e["rec"], e["conf"], e["writer"], e["confirmer"],
                        e["source"], e["year"], e["month"]])

    # validation summary
    from collections import Counter
    wk = Counter((e2["year"], dt.datetime.strptime(e2["rec"], "%Y. %m. %d.").date().isocalendar()[1])
                 for e2 in full)
    selfconf = [e["page"] for e in full if e["writer"] == e["confirmer"]]
    print(f"entries={len(full)} | per-writer={dict(Counter(e['writer'] for e in full))}")
    print(f"max writers/week={max(wk.values())} | self-confirmations={len(selfconf)}")
    print("wrote schedule.json, schedule.csv, entries_by_writer.json to", out)


if __name__ == "__main__":
    main()
