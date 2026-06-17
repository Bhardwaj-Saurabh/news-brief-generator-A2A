# Task 0 — Teaching Lesson

A plain language companion to the senior lessons. This is for someone new to AI who wants the
setup ideas explained simply.

## The lockfile and why setup is repeatable

### The idea
A project needs many helper libraries to run. We do not want to download whatever is newest each
time. Newest can break things. So we write down the exact versions once. That written down list is
called a lockfile. When a teammate runs one command they get the exact same setup you have. We use a
tool called uv. The command `uv sync` reads the lockfile and builds your environment to match. The
environment is just a private box of libraries that belongs to this project alone. It does not touch
the rest of your computer.

### Code
```toml
# pyproject.toml lists the libraries we want and a safe range of versions
dependencies = [
    "agent-framework-core>=1.8.1",
    "agent-framework-openai>=1.8.1",
    "fastmcp>=3.4.2",
    "httpx>=0.28.1",
    "pydantic>=2.11,<3",   # this range says "any stable version 2 but never version 3"
    "python-dotenv>=1,<2",
    "streamlit>=1.58.0",
]
```
The file above says what we want. A second file called `uv.lock` records the exact versions that got
chosen. You run `uv sync` and both files work together to give you the same box every time.

### A simple example
Think of baking a cake from a recipe. The recipe says use flour. That is the range. But the lockfile
says use this exact bag of this exact brand. Now every baker makes the same cake. Nobody gets a
surprise because they grabbed a different bag.

## Keeping secrets out of git with .env and .env.example

### The idea
Our app needs secret keys to talk to outside services. A key is like a password. We must never put a
real password into the code we share. So we use two files. One is called `.env` and it holds the real
secrets. We hide that file so it never gets shared. The other is called `.env.example` and it holds
only blank placeholders. We do share that one. It tells a new person which keys they need to go and
get. The real one stays on your machine only.

### Code
```bash
# .env.example shows the shape but holds no real values
NEWSAPI_KEY=            # News -> NewsAPI.org
OPENWEATHER_API_KEY=    # Weather -> OpenWeatherMap
FINNHUB_API_KEY=        # Finance -> Finnhub
YOUTUBE_API_KEY=        # Media -> YouTube Data API v3
```
```bash
# .gitignore hides the real secret file from sharing
.env
```
The example file is safe to share because it is empty. The real `.env` is listed in the ignore file so
git pretends it is not there.

### A simple example
Think of a form at a doctor office. The blank form shows you which boxes to fill in. That blank form
is the example file. Once you write your real details on it that filled copy is private. You keep it.
You do not hand it to strangers. The blank one is fine to photocopy for everyone.

## One brain in the system

### The idea
This app uses many small workers. Some go fetch news. Some go fetch weather or stock prices. Only one
worker is allowed to actually think and write the article. That thinking worker is the Publisher. It
is the only one that calls the large language model. A large language model is the smart text writer
behind the scenes. We chose a toolkit from Microsoft called the Agent Framework to power that one
worker. We did not let it take over the whole app. We use it in just one spot. That keeps the design
simple and easy to reason about.

### Code
```toml
# We only pull the pieces of Microsoft Agent Framework we need for the one thinking worker
"agent-framework-core>=1.8.1",
"agent-framework-openai>=1.8.1",
```
We did not install the giant all in one bundle. We took two small pieces. The Publisher will use them
later. Every other worker stays a plain function with no smart model inside.

### A simple example
Think of a newsroom. Many runners go out and collect facts. Photos. Scores. The weather. But only one
editor writes the final story. If every runner tried to write their own version you would get a mess.
One editor keeps the voice clear. The Publisher is that one editor.

## Why a half finished version slipped in and why that is bad

### The idea
Libraries come in two kinds of versions. A stable version is finished and tested. A pre-release
version is still being worked on. It can change or break. While installing we used a setting that told
the tool it was fine to grab unfinished versions. By accident it grabbed an unfinished version of a
very important library called pydantic. Pydantic checks that our data is shaped correctly. We do not
want our safety checker to be a half built version. So we forced it back to a finished stable version.

### Code
```toml
# This range blocks unfinished versions. It allows stable version 2 only.
"pydantic>=2.11,<3",
```
```bash
# Then we told uv to pick a finished pydantic again
uv lock --upgrade-package pydantic
# result: pydantic moved from 2.14.0a1 (unfinished) to 2.13.4 (finished)
```
The little letter a in 2.14.0a1 means alpha. Alpha means early and unfinished. The version 2.13.4 has
no such letter. That one is safe.

### A simple example
Think of buying a car. A finished car has passed all its safety tests. A test car is still being built
in the workshop. It might not have working brakes yet. You would never drive your family in the test
car. We made the same choice. We put back the finished safe version.

## Keep the folder but ignore what goes inside it

### The idea
Our app saves finished briefs into a folder called saved_briefs. We want that folder to exist the
moment someone downloads the project. But we do not want to share the saved briefs themselves. Those
are just output. So we use a trick. We tell git to ignore everything inside the folder. Then we add one
tiny empty file so the folder still exists. Git only keeps folders that have at least one file in them.

### Code
```bash
# .gitignore
saved_briefs/*            # ignore everything inside the folder
!saved_briefs/.gitkeep    # but keep this one tiny marker file
```
The star means everything in the folder. The line with the exclamation mark makes one exception. That
one marker file stays so the empty folder survives.

### A simple example
Think of a mailbox at a new house. You want the mailbox to be there on day one. But you do not want the
previous owner mail still sitting in it. So you keep the empty mailbox and throw out the letters. The
marker file is the empty mailbox. The ignored briefs are the old letters.
