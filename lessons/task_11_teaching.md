# Task 11 — Teaching Lesson

A plain language companion to the senior lessons. This one is about making the finished brief nice to
read. It is the last task.

## Clear sections instead of a wall of text

### The idea
A long block of text is hard to read. The eye gets lost. So we break the brief into clear sections. Each
section has a heading. Then a short body under it. This is easy for us because the brief already arrives
in neat parts. The Publisher gave us a list of sections earlier. We just show each one with its heading.
We do not have to chop up a big blob of text. The parts were ready for us.

### Code
```python
# app/streamlit_app.py
for section in brief.sections:      # the brief already comes as a list of sections
    st.subheader(section.heading)  # show the heading bigger
    st.markdown(section.body_markdown)  # then the body under it
```
We loop through the ready made sections. Each gets a heading and a body. Clean and easy to scan.

### A simple example
Think of a recipe card. Imagine it written as one long paragraph. Ingredients and steps all mashed
together. Awful. Now picture it with clear headings. Ingredients here. Steps here. Much easier. Our brief
gets the same clear headings.

## Signs that help the reader trust it

### The idea
This brief was made by an AI from data off the internet. A reader should be able to judge it. So we show
some helpful signs. We show when it was made. We show how many sources it used. We list those sources and
group them by website. Now the reader can see it is fresh and where the facts came from. These signs are
not decoration. They help people decide how much to trust the brief.

### Code
```python
# app/streamlit_app.py
st.caption(f"Region {req.region} · audience {req.audience} · {len(brief.sources)} sources · generated {brief.generated_at:%Y-%m-%d %H:%M UTC}")
# and the sources grouped by website
for domain in sorted(by_domain):
    st.markdown(f"**{domain}**")
```
We print when it was made and how many sources. Then we list those sources by website. Honest and clear.

### A simple example
Think of food packaging. It shows a use by date. It lists the ingredients. You glance at it and decide if
you want to eat it. The date and ingredients help you trust the food. Our timestamp and sources do the
same for the brief.

## Rewrite it without fetching everything again

### The idea
Maybe the reader wants the brief shorter. Or longer. Or written for a different crowd. We let them tweak
it. Here is the smart part. We do not go and fetch all the news and weather and stocks again. That was
the slow expensive part. We already have that data saved. We just ask the AI to write it again in the new
style. Same facts. New wording. So a tweak is quick and cheap.

### Code
```python
# app/streamlit_app.py
def _republish(report, new_request):
    new_report = report.model_copy(update={"request": new_request})  # reuse the SAME gathered data
    brief = asyncio.run(publish(new_report))  # only the writing step runs again. no re-fetch.
    return new_report, brief
```
We keep the gathered data. We only run the writing step again. The tweak is fast because we skip the
fetching.

### A simple example
Think of a photographer at a shoot. They took all the photos already. Now you want them in black and
white. They do not redo the whole shoot. They just re edit the photos they have. Reusing the gathered
data is like re editing photos you already took.

## Looking nice is not the same as being right

### The idea
This whole task is about making the brief look good. Clear sections. Nice links. A copy button. But there
is something we are not doing here. We are not checking if the facts are true. That is a different job. A
pretty layout cannot fix a wrong fact. The truth of the brief comes from earlier steps. The real data and
the careful writing. Our job now is only to present it well. We must never let a nice look fool people
into trusting bad content.

### Code
```python
# app/streamlit_app.py
# this file only formats and re-requests. it never edits or fact checks the content.
st.markdown(section.body_markdown)   # show the words. we do not change them.
```
We only show and arrange the words. We do not change them or check them. That happens upstream.

### A simple example
Think of a fancy picture frame. A beautiful frame makes any photo look special. But the frame cannot fix
a blurry photo. The photo has to be good on its own. Our UI is the frame. The brief has to be good on its
own from the earlier steps.
