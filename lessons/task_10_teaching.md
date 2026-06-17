# Task 10 — Teaching Lesson

A plain language companion to the senior lessons. This one is about the screen the user actually sees.

## The screen is the boss that runs the steps in order

### The idea
The user fills in a form and clicks a button. The screen is in charge of what happens next. First it
runs the Scout to gather all the data. Then it runs the Publisher to write the article. In that order.
The Scout and the Publisher never talk to each other directly. The screen lines them up. Gather first.
Write second. Show the result.

### Code
```python
# app/streamlit_app.py
async def _pipeline():
    report = await scout(request)     # step one. gather everything.
    return await publish(report)      # step two. write the brief.
brief = asyncio.run(_pipeline())
```
The screen calls scout then publish. Two steps in a row. The screen is the conductor.

### A simple example
Think of a relay race handover. The first runner gathers the baton round the track. Then they hand it to
the second runner who finishes. They do not run at the same time. A handover in order. The screen manages
that handover.

## Streamlit reruns the whole page every click

### The idea
Here is the surprising part. Streamlit runs your whole script again from the top every single time you
click anything. Every button. Every dropdown. The script starts fresh each time. This trips up a lot of
people. They expect their variables to stick around. They do not. Once you know the page reruns top to
bottom it all makes sense. We write the code knowing it will rerun.

### Code
```python
# app/streamlit_app.py
if submitted:           # only runs on the click that submitted the form
    ...
brief = st.session_state.get("brief")
if brief is not None:   # this part runs on EVERY rerun if a brief exists
    st.markdown(brief.markdown)
```
We use simple checks to decide what runs this time. Because the whole thing reruns again and again.

### A simple example
Think of a vending machine that resets to its home screen after every button press. You press a button
and it starts over from the welcome screen. It does not remember your half finished choice unless it was
saved. Streamlit reruns the same way. Fresh start each click.

## Showing progress so it does not look stuck

### The idea
Gathering data and writing the article takes a few seconds. During that wait the page could look frozen.
A frozen looking page makes people think it broke. So we show live progress. We print a line when the
Scout starts. Then a line when the Publisher starts. The user sees the steps tick by. They know it is
working. It is not stuck. It is just busy.

### Code
```python
# app/streamlit_app.py
with st.status("Generating brief…", expanded=True) as status:
    status.write("🔭 Scout — gathering news, weather, markets, media…")
    report = await scout(request)
    status.write("✍️ Publisher — writing the brief…")
    ...
```
We write a note before each step. The notes appear live on the page. The wait feels alive not frozen.

### A simple example
Think of a pizza tracker on a phone app. It says preparing then baking then out for delivery. The pizza
is not any faster. But you feel calm because you can see progress. Our status notes are that pizza
tracker.

## Remembering the brief so it does not vanish

### The idea
Say the brief is finished and shown on screen. Then the user clicks Save. Remember the page reruns from
the top on that click. The brief we made earlier would be gone. So we stash it in a special storage that
survives reruns. It is called session_state. We put the brief there right after we make it. Now when the
user clicks Save the brief is still there to save.

### Code
```python
# app/streamlit_app.py
st.session_state["brief"] = brief        # stash it so it survives the next rerun
...
if st.button("💾 Save brief"):
    path = save_brief(st.session_state.get("brief"))   # still here on the rerun
```
We save the brief into session_state. That box does not reset on rerun. So Save always has the brief.

### A simple example
Think of a coat check at a theatre. The show reruns the room every night. But your coat is held safely at
the desk. You collect it later with your ticket. session_state is that coat check. It holds your thing
across the resets.

## A safe filename from a messy title

### The idea
We save each brief as a file. We want to name it after the title. But titles are messy. They can have
spaces and colons and even emojis. Those make bad filenames. They can even be dangerous. So we clean the
title into a safe simple form. We call that a slug. Just lowercase letters and numbers and hyphens. Then
we add the date and time so every file is unique. Now we have a tidy safe name.

### Code
```python
# app/storage.py
def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "brief"      # never empty
# final name looks like: daily-brief-uk-economy-20260618-093015.md
```
We strip the title down to safe characters. We add a timestamp. The filename is clean and unique.

### A simple example
Think of saving a contact in your phone. Someone hands you a card covered in doodles and fancy script.
You do not type all that in. You write a plain clear name. That is the slug. The timestamp is like adding
the date you met so you can tell two similar contacts apart.
