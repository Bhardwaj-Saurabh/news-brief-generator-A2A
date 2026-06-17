# Task 7 — Teaching Lesson

A plain language companion to the senior lessons. This one is about our first agent.

## What an agent is here

### The idea
The word agent can sound fancy. In this project it is simple. An agent is just a small worker. This one
has one job. It gathers some data and hands back one tidy package. It collects news and weather. Then it
puts them in a neat box and returns it. That is all. This worker has no AI brain of its own. It does not
think or write. It just fetches and tidies.

### Code
```python
# agents/contextualist.py
async def gather_context(request: BriefRequest, deadline: float | None = None) -> ContextBundle:
    ids = resolve_region(request.region)
    # fetch news and weather then return them in one tidy package
    headlines, weather = await asyncio.gather(...)
    return ContextBundle(headlines=headlines, weather=weather, region=request.region)
```
The worker fetches two things. It returns one bundle. The bundle is the tidy box of results.

### A simple example
Think of a runner you send to two shops. One for a newspaper. One to check the weather sign. They come
back and hand you one bag with both. They did not read the paper. They did not judge the weather. They
just fetched and bagged. That runner is our agent.

## Fetching both at the same time

### The idea
We need news and weather. We could get the news first and then the weather after. But that is slow. Each
wait adds up. Instead we ask for both at the same moment. While the news is loading the weather is also
loading. They run side by side. Then we wait for both to finish together. This is much faster. The trick
is a tool called asyncio.gather. It runs several jobs at once.

### Code
```python
# agents/contextualist.py
headlines, weather = await asyncio.gather(
    _fetch_headlines(request, ids.country_code, timeout),  # these two run
    _fetch_weather(ids.weather_city, timeout),             # at the same time
)
```
Both fetches start together. We wait once for both. No waiting in a line.

### A simple example
Think of doing laundry and cooking dinner. You would not wait for the laundry to finish before you start
cooking. You start the wash. Then you cook while it runs. Both happen together. You save loads of time.
Gather is doing both chores at once.

## If one part fails we still return the rest

### The idea
Sometimes the weather service is down. We do not want the whole job to crash just because of that. The
news might be perfectly fine. So we handle each part on its own. If weather fails we just leave that slot
empty. We still return the news. We also write a small note in the log that weather failed. The user
gets a brief with news and no weather. That is far better than no brief at all.

### Code
```python
# agents/contextualist.py
async def _fetch_weather(weather_city: str, timeout: float):
    try:
        raw = await asyncio.wait_for(call_tool(...), timeout=timeout)
        return WeatherSnapshot.model_validate(raw)
    except Exception as exc:
        log.warning("weather fetch failed (%s); weather section empty", exc)
        return None   # empty weather slot. the news is unaffected.
```
If weather breaks we return None for it. The news part never even notices. The job keeps going.

### A simple example
Think of a breakfast tray. You wanted toast and juice. The juice machine is broken. You do not throw away
the toast in a huff. You serve the toast and skip the juice. A partial breakfast beats no breakfast. We
do the same with news and weather.

## A shared time budget

### The idea
We do not want this job to run forever. So we give it a time budget. About ten seconds. If a service is
too slow we stop waiting and move on. The clever part is the budget is shared. The boss agent sets one
deadline for the whole job. It passes that same deadline down to this worker. So this worker cannot
secretly start its own fresh ten seconds. Everyone shares the one clock. That keeps the total time under
control.

### Code
```python
# agents/contextualist.py
def _remaining(deadline: float | None) -> float:
    if deadline is None:
        return DEFAULT_BUDGET            # on its own it gets the full default
    return max(0.0, deadline - time.monotonic())   # otherwise only the time left on the shared clock
```
The worker checks how much time is left on the shared clock. It never makes up its own extra time.

### A simple example
Think of a road trip with a strict arrival time. The driver does not let each passenger add their own
extra hour for snacks. There is one arrival time for everyone. Every stop fits inside it. The shared
deadline is that one arrival time.

## This worker never calls the AI

### The idea
You might expect every part of an AI app to use the AI. Not here. This gathering worker never calls the
language model. Not once. Fetching news and weather is simple exact work. It does not need a thinking
model. We save the model for the very end when we write the article. Keeping the model out here makes this
worker fast and cheap and easy to test. It also keeps things safe. Random text from the internet never
reaches the model at this stage.

### Code
```python
# agents/contextualist.py
# there is no AI import anywhere in this file. the only decision is a plain if.
if request.topic:
    args = {"query": request.topic, ...}   # search by topic
else:
    args = {"country": country_code, ...}   # or get top headlines
```
The only choice it makes is a simple if. No model. No guessing. Just plain rules.

### A simple example
Think of a librarian fetching books from a list. They do not need to read each book or review it. They
just find them and bring them. The reading and reviewing happens later by someone else. Our worker is the
fetching librarian. The AI is the reviewer who comes later.
