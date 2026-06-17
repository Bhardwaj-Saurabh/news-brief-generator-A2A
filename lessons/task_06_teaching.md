# Task 6 — Teaching Lesson

A plain language companion to the senior lessons. This one is about how our agents talk to each other.

## Typed messages instead of loose bags of data

### The idea
Our agents need to pass data to each other. We could just pass a loose bag of values. In Python that is
called a dict. The problem is a dict has no rules. One agent might spell a key wrong. Another might
forget a field. The mistake only shows up much later. So instead we use typed messages. A typed message
has a fixed shape with named fields and rules. If something is wrong it is caught right away. These
messages are the real agreement between our agents. We call them contracts.

### Code
```python
# agents/contracts.py
class BriefRequest(BaseModel):
    topic: str | None = None          # what the user wants. can be empty.
    region: str = "UK"                # where the reader is
    lookback_hours: int = Field(default=24, ge=1, le=24 * 14)  # rules built in
    audience: str = "general"
```
Each field has a name and a type. The rules are built in. A bad value is rejected at the door.

### A simple example
Think of a paper form versus a blank sticky note. A sticky note can say anything. It is easy to forget a
detail. A form has labelled boxes you must fill in. It will not accept a blank required box. Our typed
messages are forms. Loose dicts are sticky notes.

## A fact cannot be changed once it is gathered

### The idea
When an agent fetches a fact we do not want another agent to quietly change it later. That would cause
strange bugs. So we lock every message. Once it is built it cannot be edited. We call this frozen. If
some code tries to change a frozen message it gets an error. This keeps the data trustworthy as it
travels from agent to agent.

### Code
```python
# agents/contracts.py
class Headline(BaseModel):
    model_config = ConfigDict(frozen=True)   # this line locks the data. no edits allowed.
    title: str
    source: str
    ...
```
The frozen line is the lock. After a headline is made nobody can rewrite its title.

### A simple example
Think of a printed receipt. Once it prints the numbers are set. You cannot rub one out and write a new
total. If you need a change you get a fresh receipt. Our frozen messages work the same way. You make a
new one rather than editing the old.

## An envelope that remembers what is inside

### The idea
Sometimes we want to wrap a message with extra info. Like who sent it and who it is for. We use an
envelope for that. The clever part is the envelope remembers what type of thing is inside. We tell it the
type in square brackets. So an envelope holding a report is written as AgentMessage of ScoutReport. When
we turn it into plain text to send and then read it back the report comes back as a real report. Not a
plain messy bag. The type survives the trip.

### Code
```python
# agents/contracts.py
class AgentMessage(BaseModel, Generic[T]):   # T is a placeholder for whatever is inside
    from_agent: str
    to_agent: str
    payload: T            # the real message lives here
    trace_id: str | None = None
```
The T is a stand in for the real type. You fill it in when you use the envelope. Then the inside keeps
its shape.

### A simple example
Think of a labelled lunchbox. The label says soup inside. So when you open it later you know to expect
soup and you bring a spoon. An unlabelled box leaves you guessing. The type in brackets is that label. It
tells the other side exactly what to expect.

## One word becomes the three ids each tool needs

### The idea
The user gives us one region. Like UK. But our three tools each want a different code for that place.
News wants a country code. Weather wants a city. Video wants a region code. We do not want each agent
working this out on its own. That would get messy and they might disagree. So we do it in one place. One
word goes in. The three ids come out. If we get a region we do not know we fall back to a default and we
log a note about it.

### Code
```python
# agents/regions.py
def resolve_region(region: str) -> RegionIds:
    key = (region or "").strip().upper()
    key = _ALIASES.get(key, key)         # United Kingdom also becomes UK
    ids = _REGIONS.get(key)
    if ids is None:
        log.warning("unknown region %r; falling back to %s", region, DEFAULT_REGION)
        return _REGIONS[DEFAULT_REGION]
    return ids
```
One word goes in. A neat set of three ids comes out. One place to fix if a code is wrong.

### A simple example
Think of a travel adapter. You bring one plug. Different countries have different sockets. The adapter
turns your one plug into the right shape for each wall. You do not carry three different plugs. Our region
resolver is that adapter. One region becomes the right code for each tool.

## We keep the failures inside the report

### The idea
Say we ask for three stocks and one name is fake. We could just drop the bad one and hide it. But that
would be dishonest. The person asked about that stock. They deserve to know it failed. So we keep the
failure inside the report as a small error note. The good stocks are there. The bad one is there too
marked as an error. Nothing is silently hidden.

### Code
```python
# agents/contracts.py
class SignalBundle(BaseModel):
    # the list can hold good quotes AND error notes. failures are not dropped.
    quotes: list[QuoteResult] = Field(default_factory=list)
```
The list holds both. A working stock and a failed one sit side by side. The truth travels with the data.

### A simple example
Think of a delivery with three parcels. One is damaged. A good service does not quietly bin the broken
one and say nothing. They deliver the two good ones and hand you a note about the damaged one. Now you
know the full story. We keep the error note for the same reason.
