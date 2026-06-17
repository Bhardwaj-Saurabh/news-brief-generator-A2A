# Task 2 — Teaching Lesson

A plain language companion to the senior lessons. This one is about our first little server and the
news tool inside it.

## What an MCP server and a tool are

### The idea
An MCP server is a small program that offers a few named actions to the outside world. Each action is
called a tool. A tool is just a function with a clear name and clear inputs. The point of MCP is that an
AI can look at the list of tools and call the one it needs. Think of MCP as a common language for AI to
use tools. Our first server is called world data. Right now it offers one tool. The tool is named
get_top_headlines. You give it a country or a search word. It hands back recent news.

### Code
```python
# servers/world_data_server.py
mcp = FastMCP(name="world-data")   # this is the little server

@mcp.tool                          # this line turns a normal function into a tool the AI can call
async def get_top_headlines(country: str = "gb", query: str | None = None, limit: int = 5):
    "Fetch recent news headlines."
    ...
```
The decorator on top is the magic word. It says this function is now a tool. The name and the inputs
become the menu the AI reads.

### A simple example
Think of a vending machine. The machine offers a few labelled buttons. Each button does one clear thing.
You press the button for water and water comes out. You do not need to know how the machine works
inside. The tools are the buttons. The AI is the person pressing them.

## Cleaning the data into our own shape

### The idea
NewsAPI sends us messy data. The publisher name is buried inside a small box. The date has a long
technical name. We do not want the rest of our app to deal with that mess. So we copy the few fields we
care about into our own clean shape. We call that shape a Headline. While we copy we also check the data
is valid. A headline must have a title. The web link must be a real link. If something is wrong we find
out right here at the door. Not deep inside the app later.

### Code
```python
# servers/world_data_server.py
class Headline(BaseModel):
    title: str            # must exist and be text
    source: str           # the publisher name pulled out of NewsAPI's nested box
    url: HttpUrl          # must be a real web link
    published_at: datetime
    summary: str | None = None   # this one is allowed to be empty
```
We pick five clean fields. We give each a type. Pydantic checks every field for us. Bad data cannot
sneak past this gate.

### A simple example
Think of a mail room at an office. Letters arrive in all shapes and sizes. The mail room copies the key
details onto one standard slip. Who it is for. What it is about. The date. Now everyone inside reads the
same simple slip. Nobody digs through the original envelope. The Headline is that standard slip.

## One tool that knows two ways to ask

### The idea
NewsAPI actually has two different ways to get news. One way gives the top stories for a country. The
other way searches for a word across everything. We did not want to make the AI choose between two
tools. So we made one tool that decides for itself. If you give it a search word it uses the search way.
If you do not it uses the top stories way. The choice happens quietly inside the code.

### Code
```python
# servers/world_data_server.py
if query:
    path = "/everything"      # a search word was given so we search everything
else:
    path = "/top-headlines"   # no search word so we get the country top stories
```
One tool. Two paths. The caller just asks for headlines. The tool picks the right door.

### A simple example
Think of a helpful librarian. You can say give me today top books. Or you can say find me books about
space. Same librarian. They know which shelf to walk to based on what you asked. You do not need to know
the shelves. The tool is that librarian.

## A real failure is different from one bad item

### The idea
Things can go wrong in two very different ways. The whole request can fail. Maybe the key is wrong.
Maybe the news site is down. That is a real failure. We stop and raise a clear error. But sometimes the
request works and only one news item is broken. We do not throw away the good ones. We just skip the
broken one and keep going. And if the news site simply has no stories right now that is not a failure at
all. We return an empty list. Empty means there was nothing. It does not mean something broke.

### Code
```python
# servers/world_data_server.py
for article in articles:
    try:
        headlines.append(_to_headline(article))   # good item goes in
    except ValidationError as exc:
        log.warning("skipping malformed article")  # one bad item is skipped not fatal
```
The good items pile up. The bad one is logged and dropped. The whole job still finishes.

### A simple example
Think of unpacking a box of a dozen eggs. If the whole box is missing that is a real problem. You tell
the shop. But if eleven eggs are fine and one is cracked you just toss the cracked one. You still make
breakfast. And if the shop had no eggs today that is not a broken delivery. There simply were none.

## Why the key hides in a header

### The idea
Our secret key proves who we are to NewsAPI. We must send it with every request. There are two places
we could put it. We could put it in the web address. Or we could put it in a header. A header is a
hidden part of the request that does not show up in the address bar. We choose the header. Why. Because
web addresses get written into logs all the time. A key sitting in a log is a key someone can steal. A
header is much safer.

### Code
```python
# servers/world_data_server.py
resp = await client.get(
    f"{NEWSAPI_BASE}{path}",
    params=params,                       # the visible web address. no secret here.
    headers={"X-Api-Key": key},          # the secret key rides quietly in a header
)
```
The params are the public part. The key goes in the header. So our logs show the address but never the
secret.

### A simple example
Think of mailing a letter. The address on the outside is for everyone to read. You would never write
your bank password on the outside of the envelope. You put private things inside sealed. The web address
is the outside of the envelope. The header is the sealed inside.
