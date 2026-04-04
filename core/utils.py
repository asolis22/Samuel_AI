def is_command(text: str) -> bool:
    t = text.strip().lower()
    return any(t.startswith(prefix) for prefix in [
        "remember:", "forget:", "memory dump", "style:", "feedback:", "search:"
    ])

def parse_command(text: str):
    raw = text.strip()
    low = raw.lower()
    if low.startswith("remember:"):
        return ("remember", raw[len("remember:"):].strip())
    if low.startswith("forget:"):
        return ("forget", raw[len("forget:"):].strip())
    if low.startswith("style:"):
        return ("style", raw[len("style:"):].strip())
    if low.startswith("feedback:"):
        return ("feedback", raw[len("feedback:"):].strip())
    if low.startswith("search:"):
        return ("search", raw[len("search:"):].strip())
    if low.startswith("memory dump"):
        return ("memory_dump", "")
    return ("unknown", raw)