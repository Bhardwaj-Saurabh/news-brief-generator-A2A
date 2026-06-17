# Task 4 — Teaching Lesson

A plain language companion to the senior lessons. This one is about our money server.

## A second server with its own door

### The idea
We built a brand new server just for finance. It is separate from the news and weather one. It runs on
its own port. A port is just a numbered door on your computer. World data uses door 8801. Finance uses
door 8802. Two servers. Two doors. They run at the same time and never bump into each other. Why keep
finance apart. Because money is a different job. It uses a different data company. If finance has a bad
day we do not want it to drag news and weather down too.

### Code
```python
# servers/finance_server.py
mcp = FastMCP(name="finance")          # a whole new server just for money

port = int(os.environ.get("FINANCE_PORT", "8802"))   # its own door. world data is on 8801.
mcp.run(transport="http", host="127.0.0.1", port=port)
```
A new server. A new port. It lives on its own and stays out of the way of the others.

### A simple example
Think of a shopping street. The bakery and the bank are separate shops with separate front doors. You
would not run a bank counter inside the bakery. If the bank closes for the day the bakery still sells
bread. Our finance server is the bank. The world data server is the bakery.

## Some win and a bad one does not ruin it

### The idea
Sometimes you ask for several stocks at once. Maybe Apple and Microsoft and a typo. We do not want one
bad name to crash the whole request. So we handle each stock on its own. The good ones come back as real
quotes. The bad one comes back as a small error note. Everything stays in one list. The caller can see
which ones worked and which one failed. Nothing blows up.

### Code
```python
# servers/finance_server.py
async def get_market_summary(symbols: list[str]) -> list[Quote | QuoteError]:
    # each symbol becomes either a Quote or a QuoteError. one bad symbol never crashes the rest.
    results = await asyncio.gather(*(_fetch_one(s) for s in symbols))
    return list(results)
```
The list can hold good quotes and error notes together. A bad symbol is just one error note in the list.
The good data still comes back.

### A simple example
Think of handing in three forms at an office. Two are filled in fine. One is blank. The clerk does not
rip up all three and send you home. They process the two good ones. They hand the blank one back with a
note. You still got most of your work done.

## Money needs exact numbers

### The idea
Computers store normal decimal numbers in a slightly fuzzy way. For most things that is fine. For money
it is not. Tiny errors can creep in. A price could end up as a long ugly number that is a hair off. So we
use a special exact number type called Decimal. We also build it from text not from the fuzzy number.
Building from text keeps the value exactly as the data company sent it. No drift. No surprise extra
digits.

### Code
```python
# servers/finance_server.py
def _dec(value: object) -> Decimal:
    # we go through str() so the exact price is kept. Decimal(189.95) would add fuzzy digits.
    return Decimal(str(value)) if value is not None else Decimal("0")
```
We turn the price into text first. Then into a Decimal. This keeps it exact. Money should never drift.

### A simple example
Think of copying a phone number. If you say it out loud fast and rewrite it you might get a digit wrong.
But if you read it straight off the screen character by character you copy it perfectly. Going through
text is reading it character by character. The price stays exact.

## When the data company will not say not found

### The idea
You would expect a service to clearly say that stock does not exist. Finnhub does not do that. If you ask
for a fake ticker it still says ok. It just sends back a price of zero and an empty company profile. So
we cannot trust it to tell us. We check for ourselves. If there is no company name we know the ticker is
fake. Then we mark it as unknown.

### Code
```python
# servers/finance_server.py
name = (profile or {}).get("name")
if not name:
    # Finnhub returns an empty profile for a fake ticker. no name means unknown.
    return QuoteError(symbol=sym, error="unknown symbol")
```
No name means the stock is not real. We catch that ourselves. We do not wait for the service to admit it.

### A simple example
Think of looking someone up in a phone book. A good phone book says not found. A lazy one just hands you
a blank page. You have to notice the page is blank yourself. The empty profile is that blank page. We
notice it and say unknown.

## Carry the data own time stamp

### The idea
A stock price is true only at a moment. Free data is often a little old. We do not want to pretend it is
fresh. So every quote carries the time it was actually measured. We call that as_of. We take that time
from the data company. We never just stamp it with right now. That way anyone reading the quote can see
how old it really is.

### Code
```python
# servers/finance_server.py
"as_of": datetime.fromtimestamp(quote.get("t") or 0, tz=timezone.utc),
# t is the time the price was measured. we keep that. we do not use the current time.
```
The quote remembers when it was true. So old data is honest about being old.

### A simple example
Think of milk in the fridge. The carton has a date printed on it. You trust that date. You would not
peel it off and write today on it just to feel better. That would be a lie. The as_of time is the date on
the carton. It tells the truth about freshness.
