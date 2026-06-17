# Task 1 — Teaching Lesson

A plain language companion to the senior lessons. This one is about getting the secret keys and
handling them safely.

## What an API key is and why each service has its own

### The idea
Our app talks to other companies over the internet to get data. We ask NewsAPI for headlines. We ask
OpenWeatherMap for the weather. Each of those companies needs to know who is asking. So they give you a
secret string called an API key. You send the key with every request. The key proves it is you. It also
lets them count how much you use. Each service gives you a different key. One key does not work on
another service. So we keep one key per service.

### Code
```bash
# .env.example shows one named slot per service
NEWSAPI_KEY=            # News -> NewsAPI.org
OPENWEATHER_API_KEY=    # Weather -> OpenWeatherMap
FINNHUB_API_KEY=        # Finance -> Finnhub
YOUTUBE_API_KEY=        # Media -> YouTube Data API v3
```
Each line is a labelled box. You drop the matching key into the matching box. The app reads the box by
its name later.

### A simple example
Think of a gym membership card. The gym scans your card at the door. The card proves you are a member.
Your gym card does not open the door at a different gym. You need their card too. An API key is that
membership card. One card per place.

## Proving the keys loaded without ever showing them

### The idea
We want to check that all the keys are filled in. But we must never print the actual key on the screen.
A printed key could end up in a chat or a log where someone steals it. So we wrote a small checker. It
looks at each key and says present or missing. It never shows the value. It also gives back a pass or
fail signal so a robot pipeline can stop if something is missing.

### Code
```python
# scripts/check_keys.py
present = bool(os.environ.get(name, "").strip())
# we print only the word present or missing. never the value.
print(f"  {'✅' if present else '❌'} {name:<30} {'present' if present else 'MISSING'}")
```
The line reads the key. Then it throws the value away and keeps only a yes or no. That is the whole
trick. We learn that the key exists. We never learn what it is.

### A simple example
Think of a teacher taking attendance. The teacher calls each name. A student says here. The teacher does
not read out the student home address to the whole class. Present is enough. Our checker takes
attendance for keys. It says here or absent and nothing more.

## One code that works on your laptop and in the cloud

### The idea
On your laptop the keys live in a file called .env. In the cloud there is often no file. The keys are
handed to the program by the hosting platform instead. We want the same code to work in both places. So
we use a helper called load_dotenv. It reads the .env file and fills in any key that is not already
set. Here is the important part. If a key is already set by the cloud then the file does not replace it.
The real environment wins. That way local and cloud both just work.

### Code
```python
# scripts/check_keys.py
from dotenv import load_dotenv
load_dotenv(env_path)   # fills in keys from .env ONLY if they are not already set
# so a value provided by the cloud platform takes priority over the file
```
On your laptop the file provides the keys. In the cloud the platform provides them first. The file step
quietly does nothing. The code does not change.

### A simple example
Think of a thermostat in a rented flat. If the landlord already set the temperature then your note on
the fridge does nothing. The landlord setting wins. If the landlord set nothing then your note is used.
The cloud is the landlord. The .env file is your note on the fridge.

## Free does not mean unlimited

### The idea
These services are free but they cap how much you can use each day. That cap is called a quota. Some
caps are simple like a number of calls per minute. YouTube is trickier. YouTube gives you a budget of
points each day. Different actions cost different points. A search costs a lot. Looking up one known
video costs almost nothing. So how you ask matters. Asking the cheap way lets you do far more in a day.

### Code
```text
# from the README quota notes for YouTube Data API v3
10,000 units per day
search.list  = 100 units   (so about 100 searches a day)
videos.list  =   1 unit    (so thousands of direct lookups a day)
```
Same daily budget. Two very different costs. This is why we will prefer cheap lookups over expensive
searches when we build the media part later.

### A simple example
Think of a phone plan with a data cap. Watching video eats data fast. Sending a text uses almost
nothing. If you only had a little data left you would text not stream. We make the same choice with
YouTube. We pick the cheap action when we can.

## Put a spending limit before the first paid call

### The idea
Four of our services are free. The fifth is the smart text writer from Azure. That one charges money
for every use. It charges based on how much text goes in and comes out. So before we ever call it we set
limits. We pick a small cheap model. We cap how many words it can write back. We can also set a budget
alert in Azure. We do this first. We do not wait for a surprise bill.

### Code
```bash
# .env.example points us at a small cheaper model on purpose
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-5.4-mini
```
The word mini means the small cheaper version. The bigger model writes a bit nicer but costs more. For
this project the small one is plenty. Choosing it is our first cost guardrail.

### A simple example
Think of a taxi with a meter. The longer the ride the more it costs. A smart rider agrees a budget
before getting in. They pick the short route. They do not just see where the meter ends up. We agree our
budget before the first ride. We pick the small model and cap the length.
