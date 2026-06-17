# Task 3 — Teaching Lesson

A plain language companion to the senior lessons. This one is about adding weather to our server.

## One server can offer more than one tool

### The idea
We already had a server with one tool for news. Now we add a second tool for weather. We do not need a
whole new server for that. We just add another function and mark it as a tool. Now the same little server
offers two actions. The AI sees both on the menu and picks the one it wants. We put news and weather
together on purpose. They both answer the same question. What is going on right now where the reader is.

### Code
```python
# servers/world_data_server.py
@mcp.tool                       # the news tool from before
async def get_top_headlines(...): ...

@mcp.tool                       # the new weather tool added to the SAME server
async def get_current_weather(city: str, units: str = "metric") -> WeatherSnapshot:
    "Current weather for a city."
    ...
```
Two functions. Two tools. One server. The second decorator is all it took to add weather to the menu.

### A simple example
Think of a coffee shop. At first it only sold coffee. Then it added tea. It did not open a second shop
across the street for tea. It just added tea to the same menu board. Same shop. More choices. Our server
is that shop.

## Always hand back metric

### The idea
Temperature can be measured two ways. Celsius or Fahrenheit. This causes confusion. A number like 15
means cold in Celsius but freezing nonsense in Fahrenheit. So we made a firm rule. No matter how the
weather is asked for we always give back Celsius. We even put the unit right in the field name. We call
it temp_c. The little c means Celsius. The wind field is wind_kph. So nobody downstream ever has to guess
the unit. The name tells them.

### Code
```python
# servers/world_data_server.py
class WeatherSnapshot(BaseModel):
    temp_c: float        # the c says this is always Celsius
    wind_kph: float      # the kph says this is always kilometres per hour
    ...
```
The field name carries the unit. So the data can never be misread. There is no guessing.

### A simple example
Think of a recipe that says add 200g of flour. The g tells you it is grams. You would never wonder if it
meant cups. Now imagine a recipe that just said add 200. That is dangerous. You might use the wrong
amount. Our weather data always says the unit. Like a good recipe.

## The server does the maths not the AI

### The idea
Sometimes the weather service gives us Fahrenheit. We do not pass that mess on. We turn it into Celsius
right here in the server before we send it out. Why do we not let the AI do the conversion. Two reasons.
The AI can make mistakes. And in our design the data fetchers are not even allowed to call the AI. Maths
like this is simple and exact. So we keep it in plain code. The AI only writes the final article. It does
no number crunching.

### Code
```python
# servers/world_data_server.py
def _to_celsius(value: float, units: str) -> float:
    # if the data came in Fahrenheit we convert it. otherwise it is already Celsius.
    return value if units == "metric" else (value - 32.0) * 5.0 / 9.0
```
The conversion is a tiny clear formula. It runs in the server. The AI never sees Fahrenheit at all.

### A simple example
Think of a money exchange desk at an airport. You hand over dollars. The desk gives you back local cash
already converted. You do not do the maths in your head later. The desk does it for you at the door. Our
server is that exchange desk for units.

## Two services hide the key in two different ways

### The idea
A key is a secret password for a service. NewsAPI lets us tuck the key into a hidden part of the request
called a header. That is nice and safe. But OpenWeatherMap is stricter. It forces the key right into the
web address. The problem is that web addresses often get written into logs. A key in a log can be stolen.
So we did one thing to protect it. We turned down the logging so the full web address is not written out.
That keeps the weather key hidden.

### Code
```python
# servers/world_data_server.py
# OpenWeatherMap forces the key into the address. so we quiet the logger that would print it.
logging.getLogger("httpx").setLevel(logging.WARNING)

resp = await client.get(f"{OWM_BASE}/weather", params={**params, "appid": key})
```
The key has to ride in the address here. So we make sure the address is never printed. The leak is closed.

### A simple example
Think of two hotels. One hotel gives you a key card you keep in your pocket. Nobody sees it. The other
hotel writes your room number on a board in the lobby. That is risky. So you ask them to wipe the board.
You cannot change their system. But you can stop it being shown. That is what turning down the log does.

## Let the weather service find the city

### The idea
We send the weather service a city name like London. We do not figure out where London is. We do not work
out its map coordinates. We let the weather service do that part. It knows how to turn a name into a
place. This keeps our tool small and simple. Finding locations is a whole hard job on its own. We choose
not to build it. We lean on the service that already does it well.

### Code
```python
# servers/world_data_server.py
data = await _request_owm({"q": city, "units": units})
# we just pass the city name as q. OpenWeatherMap resolves it to a real location for us.
```
We hand over the name. The service does the lookup. We stay out of the location business.

### A simple example
Think of ordering a taxi. You tell the driver the name of the place. The grand hotel please. You do not
hand them map coordinates. The driver already knows how to find it. We treat the weather service like
that driver. We give the name and trust them to find it.
