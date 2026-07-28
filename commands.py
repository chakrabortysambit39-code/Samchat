"""
commands.py
Rule-based intent router. Each entry is (regex, handler). The first
matching pattern wins. Handlers take the regex match + raw text and
return a response string. This is deliberately simple regex/keyword
matching rather than a full NLU stack — easy to read, easy to extend,
and needs no extra dependencies or API keys.
"""
import ast
import operator as _op
import random
import re
from datetime import datetime

import browser
import files
import memory
import news
import reminders
import settings
import system
import weather

# Each handler: (name, compiled_regex, function(match, raw_text) -> str)
_ROUTES = []


def route(pattern):
    """Decorator to register a handler for a regex pattern (case-insensitive)."""
    compiled = re.compile(pattern, re.IGNORECASE)

    def wrapper(fn):
        _ROUTES.append((compiled, fn))
        return fn

    return wrapper


# ---------------------------------------------------------------- weather
@route(r"\b(weather|temperature)\b.*\bin\s+(?P<city>[a-zA-Z\s]+)$")
def _weather_in(m, text):
    return weather.get_weather(m.group("city").strip())


@route(r"\b(weather|temperature|forecast)\b")
def _weather_default(m, text):
    city = settings.get("city", "Pune")
    return weather.get_weather(city)


# ------------------------------------------------------------------- news
@route(r"\b(news|headlines)\b.*\babout\s+(?P<topic>.+)$")
def _news_topic(m, text):
    heads = news.search_news(m.group("topic").strip())
    return news.format_headlines(heads)


@route(r"\b(news|headlines)\b")
def _news_default(m, text):
    country = settings.get("news_country", "in").upper()
    heads = news.get_top_headlines(country)
    return news.format_headlines(heads)


# --------------------------------------------------------------- browser
@route(r"\bopen\s+(?P<site>youtube|google|gmail|github|chatgpt|claude|wikipedia|maps)\b")
def _open_site(m, text):
    return browser.open_site(m.group("site"))

@route(r"\b(search|google)\s+(for\s+)?(?P<query>.+?)\s+on\s+youtube\b")
def _yt_search(m, text):
    return browser.search_youtube(m.group("query").strip())

@route(r"\b(search|google)\s+(for\s+)?(?P<query>.+)$")
def _web_search(m, text):
    return browser.search_web(m.group("query").strip())


# ---------------------------------------------------------------- system
@route(r"\b(system status|cpu|memory|ram usage|how('?s| is) (my|the) (computer|system|pc))\b")
def _sys_status(m, text):
    return system.get_status()

@route(r"\bopen\s+(?:the\s+)?app(?:lication)?\s+(?P<app>.+)$")
def _open_app(m, text):
    return system.open_application(m.group("app").strip())

@route(r"\bshut ?down\b")
def _shutdown(m, text):
    confirm = "confirm" in text.lower()
    return system.shutdown(confirm=confirm)

@route(r"\brestart\b.*\b(computer|system|pc|machine)\b")
def _restart(m, text):
    confirm = "confirm" in text.lower()
    return system.restart(confirm=confirm)

@route(r"\block\s+(the\s+)?screen\b")
def _lock(m, text):
    return system.lock_screen()


# --------------------------------------------------------------- reminders
@route(r"\bremind me to (?P<task>.+?) in (?P<delay>[\w\s]+?)(from now)?$")
def _remind_relative(m, text):
    when = reminders.parse_relative_time(m.group("delay"))
    if not when:
        return "I didn't catch when — try 'remind me to X in 10 minutes'."
    r = reminders.add_reminder(m.group("task").strip(), when)
    return (f"Got it — I'll remind you to {m.group('task').strip()} at "
            f"{when.strftime('%H:%M')} (id {r['id']}).")

@route(r"\bremind me to (?P<task>.+?) at (?P<attime>.+)$")
def _remind_absolute(m, text):
    when = reminders.parse_absolute_time(m.group("attime"))
    if not when:
        return "I didn't catch what time — try 'remind me to X at 5pm'."
    r = reminders.add_reminder(m.group("task").strip(), when)
    day = "tomorrow" if when.date() != datetime.now().date() else "today"
    return (f"Got it — I'll remind you to {m.group('task').strip()} "
            f"{day} at {when.strftime('%H:%M')} (id {r['id']}).")

@route(r"\b(list|show)\s+(my\s+)?reminders\b")
def _list_reminders(m, text):
    items = reminders.list_reminders()
    if not items:
        return "You have no pending reminders."
    lines = [f"  - [{r['id']}] {r['text']} at {r['time']}" for r in items]
    return "Your reminders:\n" + "\n".join(lines)

@route(r"\b(cancel|delete|remove)\s+reminder\s+(?P<rid>\w+)$")
def _cancel_reminder(m, text):
    ok = reminders.cancel_reminder(m.group("rid").strip())
    return "Cancelled." if ok else "I couldn't find a reminder with that id."


# ------------------------------------------------------------------ files
@route(r"\bfind\s+(files?\s+)?(named\s+|called\s+)?(?P<frag>.+)$")
def _find_files(m, text):
    matches = files.search_files(m.group("frag").strip())
    if not matches:
        return "I couldn't find any matching files."
    shown = matches[:10]
    more = f"\n  …and {len(matches) - 10} more" if len(matches) > 10 else ""
    return "Found:\n" + "\n".join(f"  - {p}" for p in shown) + more

@route(r"\bopen\s+(file|folder)\s+(?P<path>.+)$")
def _open_path(m, text):
    return files.open_path(m.group("path").strip())


# ----------------------------------------------------------------- memory
@route(r"\bremember (that\s+)?(?P<key>.+?)\s+is\s+(?P<value>.+)$")
def _remember(m, text):
    memory.remember_fact(m.group("key").strip(), m.group("value").strip())
    return f"Got it, I'll remember that {m.group('key').strip()} is {m.group('value').strip()}."

@route(r"\bwhat('?s| is)\s+(?P<key>.+?)\??$")
def _recall(m, text):
    val = memory.recall_fact(m.group("key").strip())
    if val:
        return f"{m.group('key').strip()} is {val}."
    return None  # let it fall through to ai.py chit-chat

@route(r"\bforget\s+(that\s+)?(?P<key>.+)$")
def _forget(m, text):
    ok = memory.forget_fact(m.group("key").strip())
    return "Done, forgotten." if ok else "I didn't have that stored."


# ------------------------------------------------------------------- time
@route(r"\b(what('?s| is) the time|current time)\b")
def _time(m, text):
    return datetime.now().strftime("It's %H:%M.")

@route(r"\b(what('?s| is) the date|today'?s date|what day is it)\b")
def _date(m, text):
    return datetime.now().strftime("Today is %A, %d %B %Y.")


# --------------------------------------------------------------- settings
@route(r"\b(set|change)\s+my\s+city\s+to\s+(?P<city>.+)$")
def _set_city(m, text):
    settings.set("city", m.group("city").strip())
    return f"Done — your default city is now {m.group('city').strip()}."

@route(r"\b(call me|set my name to|my name is)\s+(?P<name>.+)$")
def _set_name(m, text):
    settings.set("user_name", m.group("name").strip())
    return f"Got it, I'll call you {m.group('name').strip()} from now on."


# ------------------------------------------------------------ calculator
_ALLOWED_OPS = {
    ast.Add: _op.add, ast.Sub: _op.sub, ast.Mult: _op.mul, ast.Div: _op.truediv,
    ast.Pow: _op.pow, ast.Mod: _op.mod, ast.USub: _op.neg, ast.UAdd: _op.pos,
    ast.FloorDiv: _op.floordiv,
}


def _safe_eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPS:
        return _ALLOWED_OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPS:
        return _ALLOWED_OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("unsupported expression")


@route(r"\b(calculate|calc|what('?s| is))\s+(?P<expr>[\d\s+\-*/().^%]+)\??$")
def _calculate(m, text):
    expr = m.group("expr").strip().rstrip("?").replace("^", "**")
    if not expr or not re.search(r"\d", expr):
        return None  # not actually a math expression, let it fall through
    try:
        tree = ast.parse(expr, mode="eval")
        result = _safe_eval(tree.body)
        result = int(result) if isinstance(result, float) and result.is_integer() else result
        return f"{expr} = {result}"
    except (SyntaxError, ValueError, ZeroDivisionError, TypeError):
        return None  # let ai.py take a shot at it instead


# --------------------------------------------------------- unit conversion
@route(r"\bconvert\s+(?P<val>-?\d+(\.\d+)?)\s*(?P<from>c|f|celsius|fahrenheit)\s+to\s+(?P<to>c|f|celsius|fahrenheit)\b")
def _convert_temp(m, text):
    val = float(m.group("val"))
    frm = m.group("from")[0].lower()
    to = m.group("to")[0].lower()
    if frm == to:
        return f"{val}°{frm.upper()} is already in that unit."
    if frm == "c":
        result = val * 9 / 5 + 32
    else:
        result = (val - 32) * 5 / 9
    return f"{val}°{frm.upper()} is {round(result, 1)}°{to.upper()}."


# ---------------------------------------------------------------- fun/help
_JOKES = [
    "Why do programmers prefer dark mode? Because light attracts bugs.",
    "I'd tell you a UDP joke, but you might not get it.",
    "There are 10 kinds of people: those who understand binary and those who don't.",
]


@route(r"\b(tell me a joke|make me laugh|joke)\b")
def _joke(m, text):
    return random.choice(_JOKES)


@route(r"\b(help|what can you do|list commands)\b")
def _help(m, text):
    return (
        "Here's what I can do:\n"
        "  - Weather: 'weather in Mumbai', 'weather'\n"
        "  - News: 'news', 'news about cricket'\n"
        "  - Web: 'open youtube', 'search for python tutorials'\n"
        "  - System: 'system status', 'open app calculator', 'lock the screen'\n"
        "  - Reminders: 'remind me to X in 10 minutes', 'remind me to X at 5pm', "
        "'list reminders', 'cancel reminder <id>'\n"
        "  - Files: 'find files named report', 'open file notes.txt'\n"
        "  - Memory: 'remember my wifi password is X', 'what's my wifi password', 'forget X'\n"
        "  - Math: 'calculate 12 * 7', 'convert 100 f to c'\n"
        "  - Settings: 'set my city to Mumbai', 'call me Sam'\n"
        "  - Time/date: 'what's the time', 'what day is it'\n"
        "  - Anything else turns into normal chat."
    )


# ---------------------------------------------------------- generic open
# Catch-all for "open <something>" that didn't match a known site, app
# keyword, or file/folder phrasing above — try launching it as an app.
# Registered last so more specific routes always get first refusal.
@route(r"\bopen\s+(?P<app>.+)$")
def _open_generic(m, text):
    return system.open_application(m.group("app").strip())


def handle(text: str):
    """Try every route in registration order; return the first non-None
    response, or None if nothing matched (caller should fall back to ai.py)."""
    text = text.strip()
    if not text:
        return None
    for pattern, fn in _ROUTES:
        m = pattern.search(text)
        if m:
            result = fn(m, text)
            if result is not None:
                return result
    return None
