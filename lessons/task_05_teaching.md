# Task 5 — Teaching Lesson

A plain language companion to the senior lessons. This one is about our media server. It is the last
of the three tool servers.

## The last tool server

### The idea
We now have three little servers. One for news and weather. One for money. And this new one for media.
Media means videos from YouTube. With this server done the whole tool layer is finished. That means all
the data fetchers are built. From here on we start building the parts that think and write. This media
server offers two tools. One gets trending videos. One searches for videos by a word.

### Code
```python
# servers/media_server.py
mcp = FastMCP(name="media")   # the third and final tool server

@mcp.tool
async def get_trending(region: str = "GB", limit: int = 5): ...
@mcp.tool
async def search_media(query: str, limit: int = 5): ...
```
Two tools on one media server. With this the data side of the project is complete.

### A simple example
Think of building a kitchen. First you put in the fridge. Then the stove. Now the last appliance the
oven goes in. The kitchen is ready to cook. Our three servers are those appliances. The kitchen is now
ready.

## Cutting long descriptions to a fixed size

### The idea
YouTube descriptions can be huge. Pages of links and hashtags. We do not want that mess in a short
brief. So we cut every description down to a fixed length. We also make the cut the same every time. Same
input gives the same output. We call that deterministic. It just means no surprises. The cut is exact and
repeatable. That makes it easy to test and easy to trust.

### Code
```python
# servers/media_server.py
def _truncate(text: str | None, limit: int = SUMMARY_MAX) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"   # cut to the limit then add a little … to show it was cut
```
Short text is left alone. Long text is cut to the limit. A small ellipsis shows there was more.

### A simple example
Think of a movie trailer. The full film is two hours. The trailer is always cut to about two minutes. It
gives you the gist without the whole thing. And the same trailer plays the same way every time you watch
it. Our truncation is that trailer for a description.

## A search costs more than a lookup

### The idea
YouTube does not charge money for these calls. It charges points instead. They call them units. You get
ten thousand units a day. Here is the catch. A search costs one hundred units. But looking up a known
video costs only one unit. That is a huge difference. So we lean on the cheap action when we can. Getting
trending videos is cheap. Searching is the pricey one. Knowing this shapes how we design the tools.

### Code
```python
# servers/media_server.py
# get_trending uses the cheap videos endpoint. one unit.
data = await _request_youtube("/videos", {"chart": "mostPopular", ...})
# search_media uses the search endpoint. one hundred units.
sdata = await _request_youtube("/search", {"q": query, "type": "video", ...})
```
Same budget for the day. Very different costs. We spend the cheap way whenever we can.

### A simple example
Think of a taxi versus a bus. The bus is cheap. The taxi is fast but pricey. You can take the bus many
times for the price of one taxi. So you save the taxi for when you really need it. Search is the taxi.
Trending is the bus.

## One batched lookup instead of many

### The idea
Search gives us videos but no view counts. We want the view counts too. We could ask for each video one
at a time. That would be slow and wasteful. Lucky for us YouTube lets us ask about many videos in a
single request. We just list all the video ids at once. One call. All the view counts come back together.
The finance service could not do this. YouTube can. So we use it.

### Code
```python
# servers/media_server.py
# one call gets the stats for EVERY found video at once
vdata = await _request_youtube("/videos", {"part": "statistics", "id": ",".join(ids)})
```
We join all the ids with commas. We send one request. We get every view count in one go.

### A simple example
Think of asking a class who wants pizza. You could ask each student one by one. That takes ages. Or you
just say raise your hand if you want pizza. One question. Everyone answers at once. The batched lookup is
the show of hands.

## Unknown is not the same as zero

### The idea
Sometimes a video hides its view count. Or the data is just missing. We have a choice here. We could put
zero. But zero is a lie. Zero means nobody watched. Missing means we do not know. Those are very
different. So when the count is missing we say it is unknown. In code we use a special empty value called
None. That keeps us honest.

### Code
```python
# servers/media_server.py
def _to_int(value: object) -> int | None:
    try:
        return int(value)      # a real number becomes a real count
    except (TypeError, ValueError):
        return None            # missing or odd data becomes unknown. not zero.
```
A real number stays a number. Anything missing becomes unknown. We never fake a zero.

### A simple example
Think of a survey form. One question is left blank. You would not write zero for it. Blank means they did
not answer. Zero would mean their answer was zero. Those are not the same. We treat a missing view count
like a blank. Not like a zero.
