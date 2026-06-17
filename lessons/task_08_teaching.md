# Task 8 — Teaching Lesson

A plain language companion to the senior lessons. This one is about the boss worker that ties it all
together.

## The boss worker that gathers everything

### The idea
We have small workers that each fetch one kind of data. Now we need one worker to run them all. We call
it the Scout. It is the boss worker. It asks the news and weather worker for its bundle. At the same
time it asks the finance tool for stock prices. And it asks the media tool for videos. Then it packs all
of it into one big report. That report is everything the writer will need later.

### Code
```python
# agents/scout.py
context, quotes, media = await asyncio.gather(
    gather_context(request, deadline),   # the news and weather worker
    _fetch_quotes(symbols, timeout),     # the finance tool
    _fetch_media(request, ids.media_region, timeout),  # the media tool
)
report = ScoutReport(context=context, signals=SignalBundle(quotes=quotes, media_items=media), request=request)
```
The Scout fires off all three at once. Then it packs the results into one report. One neat package.

### A simple example
Think of planning a party. You send one friend for the cake. Another for drinks. Another for music. They
all go at the same time. Then they bring everything back to you. You lay it all out on one table. The
Scout is you laying out the party table.

## One clock for the whole job

### The idea
The Scout is in charge of time. It sets one deadline for the whole job. Something like ten seconds from
now. Then it shares that same deadline with every worker. Nobody gets their own fresh ten seconds. They
all race against the one clock. This keeps the total time short. If a worker is too slow it gets cut off.
The report still comes back on time.

### Code
```python
# agents/scout.py
start = time.monotonic()
deadline = start + BUDGET            # one deadline for the whole job
timeout = max(0.0, deadline - time.monotonic())
context = await gather_context(request, deadline)   # the SAME deadline is shared down
```
The Scout sets the deadline once. It hands the same one to the workers. Everyone shares the clock.

### A simple example
Think of a group cooking a meal with one oven timer. The timer is set for the whole dinner. Each cook
works against that one timer. No cook resets it for their own dish. So dinner is ready all at once. The
shared deadline is that single oven timer.

## Choosing stocks with a simple list not the AI

### The idea
The report needs some stock prices. But which stocks. We pick them from the topic. If the topic mentions
energy we grab energy stocks. If it mentions tech we grab tech stocks. We do this with a plain lookup
list. We do not ask the AI to choose. Why not. Because the AI is slow and costs money and can be
unpredictable. A simple list is fast and free and always the same. We save the AI for writing the article
at the very end.

### Code
```python
# agents/scout.py
_KEYWORD_TICKERS = {
    "tech": _TECH, "technology": _TECH,
    "energy": _ENERGY, "oil": _ENERGY,
    ...
}
DEFAULT_WATCHLIST = ["SPY", "AAPL", "MSFT"]   # used when nothing matches
```
A word in the topic points to a set of stocks. No AI needed. If nothing matches we use a safe default
list.

### A simple example
Think of a coffee shop menu with set combos. You say breakfast combo and you get the fixed set. The
cashier does not invent a new meal each time. They read the menu. Our keyword list is that menu. The topic
picks the combo.

## Matching whole words so retail does not become ai

### The idea
We have to be careful how we match words. The letters a and i sit inside the word retail. So a sloppy
match could think a retail story is about ai. That would pull the wrong stocks. To avoid this we match
whole words only. We chop the topic into separate words first. Then we check for the exact word ai. The
word retail is one whole word. It is not the word ai. So no mix up.

### Code
```python
# agents/scout.py
tokens = set(re.findall(r"[a-z0-9]+", topic.lower()))   # split topic into whole words
for keyword, tickers in _KEYWORD_TICKERS.items():
    if keyword in tokens:        # match a whole word. not letters hidden inside a word.
        return tickers
```
We split the topic into real words. Then we look for the exact word. So retail stays retail. It never
becomes ai.

### A simple example
Think of searching a class list for a student named Al. You would not flag the name Alice or Walter just
because they contain a and l. You look for the whole name Al. Whole word matching is looking for the whole
name. Not random letters inside other words.

## A report still comes back if one source fails

### The idea
Three sources feed the report. News and weather. Stocks. Videos. Any one of them could fail. We do not
let that stop the whole report. If the stock service is down we just leave the stocks empty. The news and
videos still go in. We write a small note in the log. The user still gets a useful report. A partial
report beats no report.

### Code
```python
# agents/scout.py
async def _fetch_quotes(symbols, timeout):
    try:
        raw = await asyncio.wait_for(call_tool(...), timeout=timeout)
    except Exception as exc:
        log.warning("finance fetch failed (%s); quotes section empty", exc)
        return []   # empty stocks. the rest of the report is fine.
```
If stocks fail we return an empty list. The news and videos are untouched. The report still gets built.

### A simple example
Think of a newspaper going to print. The sports writer is out sick today. The paper does not cancel the
whole edition. It prints with a smaller sports page. The readers still get their paper. Our report works
the same way. One missing part does not stop the rest.
