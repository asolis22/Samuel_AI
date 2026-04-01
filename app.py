from llm_ollama import ollama_chat
from web_search import duckduckgo_html_search, fetch_page_text
from memory_db import init_db, add_memory, forget_memory, list_memories, retrieve_relevant_memories
from style import StyleProfile, infer_user_style_hint
from utils import is_command, parse_command

MODEL_NAME = "gemma3:1b"

SYSTEM_BASE = """You are a personal AI assistant that grows with the user over time.
You are NOT stiff. You sound human, warm, and natural.
You adapt to the user's vibe without being cringe.

Hard rules:
- If you use the web results, cite them as numbered sources like [1], [2] with their URLs.
- If unsure, ask one short follow-up OR suggest doing a web check.
- Do not invent sources.
- Keep answers helpful and practical.
"""

def build_system_prompt(style: StyleProfile, user_style_hint: str, memory_snippets: str) -> str:
    return f"""{SYSTEM_BASE}

Style profile:
- Vibe: {style.vibe}
- Rules: {style.rules}
- Extra mirroring hint: {user_style_hint}

Known user memory (use when relevant, don't force it):
{memory_snippets}
"""

def format_memory_snippets(memories: list[dict]) -> str:
    if not memories:
        return "(no relevant memories found)"
    lines = []
    for m in memories:
        lines.append(f"- [{m['category']}] {m['key']}: {m['value']}")
    return "\n".join(lines)

def decide_need_web(user_text: str) -> bool:
    t = user_text.lower()
    triggers = [
        "look up", "search", "latest", "today", "current", "news", "what is",
        "who is", "when is", "where is", "price", "release date", "schedule"
    ]
    return any(x in t for x in triggers)

def main():
    init_db()
    style = StyleProfile()

    print("\nBabyAI is running. Type 'quit' to exit.\n")
    chat_history = []

    while True:
        user = input("You: ").strip()
        if not user:
            continue
        if user.lower() in {"quit", "exit"}:
            break

        # Commands
        if is_command(user):
            cmd, payload = parse_command(user)

            if cmd == "remember":
                # Simple default parse: "category.key = value" OR just store as preference
                if "=" in payload:
                    left, value = payload.split("=", 1)
                    left = left.strip()
                    value = value.strip()
                    if "." in left:
                        category, key = left.split(".", 1)
                    else:
                        category, key = "general", left
                    add_memory(category, key, value, weight=1.5)
                    print("AI: Got it. Saved.")
                else:
                    add_memory("general", "note", payload, weight=1.0)
                    print("AI: Got it. Saved as a general note.")
                continue

            if cmd == "forget":
                # try: "category.key" or keyword contains
                if "." in payload:
                    category, key = payload.split(".", 1)
                    n = forget_memory(category=category.strip(), key=key.strip())
                else:
                    n = forget_memory(contains=payload.strip())
                print(f"AI: Deleted {n} memory item(s).")
                continue

            if cmd == "memory_dump":
                mems = list_memories(limit=200)
                if not mems:
                    print("AI: Memory is empty.")
                else:
                    print("AI: Here’s what I remember (latest first):")
                    for m in mems:
                        print(f"- [{m['category']}] {m['key']}: {m['value']}")
                continue

            if cmd == "style":
                style.vibe = payload.strip() or style.vibe
                add_memory("style", "vibe", style.vibe, weight=2.0)
                print(f"AI: Style updated to: {style.vibe}")
                continue

            if cmd == "feedback":
                # store feedback so the assistant adapts over time
                add_memory("feedback", "note", payload.strip(), weight=2.0)
                print("AI: Noted. I’ll adjust.")
                continue

            if cmd == "search":
                # manual search command
                user = payload.strip()

        # Retrieve relevant memories (keyword-based)
        relevant = retrieve_relevant_memories(user, limit=8)
        memory_snippets = format_memory_snippets(relevant)

        user_style_hint = infer_user_style_hint(user)
        system_prompt = build_system_prompt(style, user_style_hint, memory_snippets)

        # Web tool use
        sources_block = ""
        if decide_need_web(user):
            results = duckduckgo_html_search(user, max_results=4)
            sources = []
            page_texts = []
            for i, r in enumerate(results, start=1):
                sources.append(f"[{i}] {r['title']} — {r['url']}")
                try:
                    txt = fetch_page_text(r["url"], max_chars=2500)
                except Exception:
                    txt = ""
                page_texts.append(f"Source [{i}] text:\n{txt}\n")

            sources_block = "Web sources found:\n" + "\n".join(sources) + "\n\n" + "\n".join(page_texts)

        messages = [{"role": "system", "content": system_prompt}]
        # keep a small rolling context
        for m in chat_history[-8:]:
            messages.append(m)

        user_payload = user
        if sources_block:
            user_payload += "\n\n" + sources_block

        messages.append({"role": "user", "content": user_payload})

        try:
            reply = ollama_chat(MODEL_NAME, messages, temperature=style.temperature)
        except Exception as e:
            reply = f"I hit an error talking to the local model. Is Ollama running and is '{MODEL_NAME}' installed?\nError: {e}"

        print(f"\nAI: {reply}\n")

        # Save chat history (short-term memory)
        chat_history.append({"role": "user", "content": user})
        chat_history.append({"role": "assistant", "content": reply})

        # Optional: auto-learn small safe preferences if user phrases it directly
        lower = user.lower()
        if lower.startswith("i like ") and len(user) < 120:
            add_memory("preferences", "likes", user[6:].strip(), weight=1.1)
        if lower.startswith("i hate ") and len(user) < 120:
            add_memory("preferences", "dislikes", user[6:].strip(), weight=1.1)

if __name__ == "__main__":
    main()