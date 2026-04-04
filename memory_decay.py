# memory_decay.py
"""
Memory decay and expiry system for Samuel.

- Temporary memories auto-expire after a configurable TTL (default 24 h).
- Adaptive memories slowly lose importance when never accessed/updated.
- Core memories are NEVER decayed or deleted.

Call run_decay() once at startup, and optionally start_decay_thread()
for an automatic background pass every hour.
"""

import time
import threading
from typing import Optional

import Samuel_AI.core.samuel_store as store

# ---- CONFIG ----
TEMPORARY_TTL_HOURS      = 24.0   # temp memories live this long
ADAPTIVE_DECAY_DAYS      = 30.0   # adaptive memories start losing importance after N idle days
ADAPTIVE_DECAY_RATE      = 0.05   # importance cut per idle day beyond threshold
ADAPTIVE_MIN_IMPORTANCE  = 0.30   # never decay below this floor
LOW_IMPORTANCE_PURGE     = 0.20   # purge adaptive memories below this floor
DECAY_INTERVAL_SECONDS   = 3600   # background thread interval


def expire_temporary_memories(ttl_hours: float = TEMPORARY_TTL_HOURS) -> int:
    """Delete saved temporary memories older than ttl_hours. Returns count deleted."""
    store.init_db()
    cutoff = int(time.time()) - int(ttl_hours * 3600)
    conn = store._connect()
    try:
        with conn:
            rows = conn.execute(
                "SELECT id FROM saved_memories WHERE stability='temporary' AND updated_ts<?;",
                (cutoff,),
            ).fetchall()
            ids = [r["id"] for r in rows]
            if ids:
                conn.executemany("DELETE FROM saved_memories WHERE id=?;", [(i,) for i in ids])
            return len(ids)
    finally:
        conn.close()


def expire_temporary_chat_memories(chat_id=None, ttl_hours: float = TEMPORARY_TTL_HOURS) -> int:
    """Delete chat-scoped temp memories older than ttl_hours. chat_id=None cleans all chats."""
    store.init_db()
    cutoff = int(time.time()) - int(ttl_hours * 3600)
    conn = store._connect()
    try:
        with conn:
            if chat_id is not None:
                rows = conn.execute(
                    "SELECT id FROM memory_chat_current WHERE chat_id=? AND ts<?;",
                    (int(chat_id), cutoff),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id FROM memory_chat_current WHERE ts<?;", (cutoff,)
                ).fetchall()
            ids = [r["id"] for r in rows]
            if ids:
                conn.executemany("DELETE FROM memory_chat_current WHERE id=?;", [(i,) for i in ids])
            return len(ids)
    finally:
        conn.close()


def decay_adaptive_memories(
    decay_days: float  = ADAPTIVE_DECAY_DAYS,
    decay_rate: float  = ADAPTIVE_DECAY_RATE,
    min_imp: float     = ADAPTIVE_MIN_IMPORTANCE,
    purge_below: float = LOW_IMPORTANCE_PURGE,
) -> dict:
    """
    Reduce importance of adaptive memories idle longer than decay_days.
    Purge those that fall below purge_below.
    Returns {"decayed": N, "purged": N}
    """
    store.init_db()
    now = int(time.time())
    threshold_ts = now - int(decay_days * 86400)
    conn = store._connect()
    try:
        rows = conn.execute(
            "SELECT id, importance, updated_ts FROM saved_memories "
            "WHERE stability='adaptive' AND updated_ts<?;",
            (threshold_ts,),
        ).fetchall()
    finally:
        conn.close()

    decayed = purged = 0
    for r in rows:
        mem_id   = int(r["id"])
        imp      = float(r["importance"])
        idle_days = (now - int(r["updated_ts"])) / 86400.0
        extra    = max(0.0, idle_days - decay_days)
        new_imp  = imp - extra * decay_rate

        if new_imp < purge_below:
            store.delete_saved_memory_by_id(mem_id)
            purged += 1
        elif new_imp < imp:
            new_imp = max(min_imp, new_imp)
            c2 = store._connect()
            try:
                with c2:
                    c2.execute(
                        "UPDATE saved_memories SET importance=?, updated_ts=? WHERE id=?;",
                        (round(new_imp, 4), now, mem_id),
                    )
            finally:
                c2.close()
            decayed += 1

    return {"decayed": decayed, "purged": purged}


def run_decay(verbose: bool = False) -> dict:
    """Full decay pass. Call at startup and on a repeating timer."""
    t_saved  = expire_temporary_memories()
    t_chat   = expire_temporary_chat_memories()
    adaptive = decay_adaptive_memories()
    result = {
        "temporary_saved_deleted": t_saved,
        "temporary_chat_deleted":  t_chat,
        "adaptive_decayed":        adaptive["decayed"],
        "adaptive_purged":         adaptive["purged"],
    }
    if verbose:
        print(f"[DECAY] {result}")
    return result


_decay_thread = None
_stop_event   = threading.Event()
'''
def start_decay_thread(interval: int = DECAY_INTERVAL_SECONDS, verbose: bool = False):
    """
    Start a daemon background thread that calls run_decay() every `interval` seconds.
    Add to SamuelGUI.__init__:
        from memory_decay import start_decay_thread
        start_decay_thread(verbose=True)
    """
    global _decay_thread, _stop_event
    _stop_event.clear()

    def _loop():
        run_decay(verbose=verbose)
        while not _stop_event.wait(timeout=interval):
            run_decay(verbose=verbose)

    _decay_thread = threading.Thread(target=_loop, name="samuel-decay", daemon=True)
    _decay_thread.start()
    if verbose:
        print(f"[DECAY] Thread started (interval={interval}s)")
'''

def stop_decay_thread():
    _stop_event.set()
