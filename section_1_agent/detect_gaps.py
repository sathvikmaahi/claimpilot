import datetime as dt


def _t(hhmmss: str) -> dt.time:
    h, m, s = (int(x) for x in hhmmss.split(":"))
    return dt.time(h, m, s)


def detect_gaps(extraction: dict, shift: dict, medications: list) -> list[dict]:
    gaps = []
    transcript = extraction.get("transcript", "").lower()
    start, end = _t(shift["start"]), _t(shift["end"])


    # 1. Medication — only meds scheduled WITHIN the shift window count.
    in_window = [m for m in medications if start <= _t(m["time"]) <= end]
    med_mentioned = any(w in transcript for w in ("med", "medication", "pill"))
    if in_window and not med_mentioned:
        names = ", ".join(f'{m["name"]} {m["time"][:5]}' for m in in_window)
        gaps.append({"type": "medication", "severity": "high",
                     "message": f"Scheduled medication(s) within shift not mentioned: {names}"})

    # 2. Sparse / vague activities.
    if len(extraction.get("activities_performed", [])) <= 1:
        gaps.append({"type": "activities", "severity": "medium",
                     "message": "Few or vague activities described."})

    # 3. No timestamps captured.
    if not extraction.get("activity_timestamps"):
        gaps.append({"type": "timestamps", "severity": "low",
                     "message": "No activity times were captured."})

    # 4. Support level not inferable.
    if extraction.get("support_level") == "unknown":
        gaps.append({"type": "support_level", "severity": "medium",
                     "message": "Support level not inferable from the narration."})

    return gaps