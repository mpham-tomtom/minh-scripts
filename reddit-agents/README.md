# reddit agents

reddit is the best free traffic there is, and there's a community for every
problem a person can have. this repo is two agents that sell to them.

- **agent one** is for when you don't have a product. it monitors the
  communities, finds the problem that keeps coming up, builds the guide and
  generates the landing page.
- **agent two** is for when you do. it learns your product, finds the people
  describing the problem it solves, and has the reply written before you've
  opened the thread.

both run on the same setup underneath: you build the core once and point it
at whichever you need.

one thing to be clear about before anything else: **the agent never logs
into reddit.** it reads, it writes, it queues everything up with the links
ready, and you do the clicking. that's not a limitation you're working
around, it's the reason the accounts survive. every action on the account
comes from a real person on a real session. it also means you read
everything before it goes out.

## how it reads reddit

no scraper. reddit publishes public rss feeds - add `.rss` to almost any
reddit url and you get structured data back. posts give the title, the OP,
the link and the body; comments give the username, the full comment, the
post it's on, a permalink straight to it, and a timestamp. that's everything
this system needs.

there's a rate limit of about one request a minute from a single ip. the
agent knows about it up front and paces itself (`RateLimiter`), and handles
429s by waiting rather than retrying immediately. the details are saved as a
skill in [`skills/reddit-monitoring.md`](skills/reddit-monitoring.md) (step 2's
"save this as a skill").

## the accounts

you need a reddit account that can actually post - a new one gets removed by
automod before anyone sees it. use an old account if you have one, or warm
one up: comment fifteen or so times a day in big general subreddits for two
weeks, answering things you actually know. running several niches? warm a
few accounts and keep them separate. the agent never touches any of them.

## step 1 - set up the agent

the original recipe stands up a hermes agent (https://nousresearch.com) on
railway with telegram and persistent storage. this repo *is* that agent,
already written, so setup is:

1. create a telegram bot: message **@BotFather**, send `/newbot`, copy the
   token it gives you. message your new bot once, then get your chat id from
   `https://api.telegram.org/bot<TOKEN>/getUpdates` (the `chat.id` field).
2. on railway: new project from this repo (root directory `reddit-agents`),
   attach a **volume mounted at `/data`** so it keeps files between runs.
3. set the environment variables: `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`,
   `TELEGRAM_CHAT_ID`, and optionally `GEMINI_API_KEY` and `MOONSHOT_API_KEY`.
4. copy `config.example.yaml` to `config.yaml` and fill it in.
5. before you finish, confirm it can message you:
   `python -m redditagents test-telegram`

## step 2 - point it at reddit

```
python -m redditagents test-rss        # confirms the feeds and reports the fields
```

then give it the subreddits by listing them in `config.yaml`. every 30
minutes it pulls new posts and comments and stores them (sqlite in `/data`)
so it builds up history rather than only looking at what's live. for
comments it keeps the username, the text, the post it's on, the permalink
and the timestamp. it logs how much it's pulling and pings telegram if the
subreddit count gets close to the rate limit.

if you don't know which subreddits, ask first - set `product` and `audience`
in `config.yaml` and run:

```
python -m redditagents find-subreddits
```

## step 3 - the subreddit profiles

a subreddit is a group of people with a shared situation. r/smallbusiness
and r/entrepreneur look similar from outside and the people in them are
nothing alike. the agent keeps a markdown profile of each community in
`/data/profiles/<sub>.md` - demographics, psychographics, the exact words
they use, what they've tried and why it failed, what gets upvoted, the
rules, the tone, and a dated update log - and updates it every night from
that day's activity, only changing what the new data contradicts or adds to.

**that file is the thing to read every morning.** it's a live document about
a few thousand people who might buy from you, written from what they
actually said. everything below reads from it.

## agent one - when you don't have a product

```
python -m redditagents find-niches        # step 4: who is desperate enough to pay
```

don't start from whatever subreddits you happen to be watching - this ranks
niches by urgency and by how easy the people are to reach for free, and
names the ones to stay out of (anywhere you'd need credentials, or where
getting it wrong would hurt someone). pick one, point `config.yaml` at its
subreddits, let it run for a week before you look.

```
python -m redditagents analyze-problems   # step 5: the question asked over and over
```

repetition is the whole signal. this reads everything pulled in the last 30
days and reports each recurring problem in the words people actually used,
with three real quoted lines, what they've tried, and which problems people
already pay to solve. if nothing in there is worth building for, it says so
instead of forcing something.

```
python -m redditagents build-guide --problem "..." --subreddit <sub> --price '$29'
```

step 6: writes the 25-30 page guide (in the community's own language, no
filler) and generates the landing page - headline in their own words, what's
inside in specific terms, who it's for and who it isn't, then the buy
section. no fake testimonials, no invented numbers. deploy the html
anywhere, create the product on whop so the guide gets emailed on purchase,
and paste your checkout link over the `WHOP_CHECKOUT_URL` placeholder.

## agent two - when you do have a product

```
python -m redditagents init-product       # step 7: creates /data/product.md
```

fill it in by hand: what it is and costs, the exact problem it solves the
way a buyer would say it, who it's for and isn't, what it covers, what it
*doesn't* do so the agent never overpromises on your behalf, the objections
and honest answers, and three real quotes from the monitored subreddits.
that file is the difference between an agent that sounds like you and one
that sounds like a bot - spend an hour getting it right. the agent reads it
and the relevant subreddit profile before writing anything.

- **step 8 - finding the threads** (`match`): haiku scores everything
  collected, 1-5, for how directly it describes your problem - using each
  profile's language section to catch the community's own phrasings - flags
  who's clearly looking for a solution right now, and ignores anything older
  than a month, already answered well, or where replying would obviously be
  spam (skips are logged with reasons).
- **step 9 - the replies** (`draft-replies`): every match at 4+ gets a reply
  drafted in that community's tone that answers the actual question
  properly. no product mention, no links, no marketing language, no
  exclamation marks, never "great question". queued on the dashboard with
  the direct link, newest threads first.
- **step 10 - the posts** (`draft-posts`): five a morning across your
  subreddits. the whole method given away, nothing held back, no link, ends
  offering to answer questions - plus what might get each one removed in
  that subreddit and what to change. queued with the submit link, and
  telegram pings you when that community's active window comes round
  (computed from the collected timestamps). pick the two you'd actually
  stand behind and post them.

## step 11 - the dms

when a post does well people message you. dms aren't public - there's no
feed - so the agent can't see any of this. block out time and answer them
yourself. these are the conversations that turn into sales, and the best
market research you'll ever get; paste the good ones back into the subreddit
profile yourself.

## step 12 - the dashboards

two dashboards, plain, one page each, regenerated every morning and served
at the railway url (`python -m redditagents run` serves them on `$PORT`):

- **finding** - what's coming up in your subreddits this week ranked by
  frequency with the real quotes underneath, and what changed in the
  subreddit profiles.
- **selling** - everything ready to send with full text, a copy button and
  the direct link, sorted by time sensitivity; what you've already sent so
  you don't do the same thread twice; and account health. removals and rule
  changes show up as their own section (`log-health`).

after you post something, `mark-sent <id>`; if it doesn't look right,
`mark-skipped <id>`.

## step 13 - the schedule

`python -m redditagents run` (what railway starts) runs it all:

- every 30 minutes: pull new posts and comments
- through the day: find new matches and queue replies for them
- every night: update the subreddit profiles from that day's activity
- every morning: draft five posts, queue them, update both dashboards, and
  message you on telegram with what's waiting and the dashboard link
- weekly: the problem analysis, with what's changed in what people ask for
- pings when a posting window opens for a subreddit with a post queued, and
  when a queued reply is about to go stale

you open the dashboard, work down the list clicking and pasting, and skip
whatever doesn't look right. ten to twenty minutes a day.

## which models do what

running one model for all of it is how the cost gets away from you:

| role | model | why |
|---|---|---|
| orchestrator | claude opus 5 | decides the order of things, runs the analyses |
| feed matching | claude haiku 4.5 | high volume, low difficulty |
| posts, replies, profiles | claude sonnet 5 | where the quality actually shows |
| volume reading | gemini 2.5 flash | a few thousand comments to find patterns |
| landing page + dashboard | kimi k3 | page building |

gemini and kimi are optional; without their keys those roles fall back to
the claude models. the rss feeds are free, the matching is haiku across a
lot of text, the writing is sonnet on maybe fifty generations a day, railway
is a few dollars - it runs at well under $100/month, and the only thing that
scales is how many subreddits you're watching.

## where to start

one subreddit and one product. no product? let it collect for a week before
you look. have one? get the product file right first - everything downstream
reads from it. and read the subreddit profile every morning: that file is
the actual product of this whole system. the money follows from
understanding those people.

## the exact prompts

every instruction from the original post is preserved verbatim in
[`redditagents/prompts.py`](redditagents/prompts.py) - the pipeline stages
wrap those strings with data and send them to the models. the wording is
the spec.
