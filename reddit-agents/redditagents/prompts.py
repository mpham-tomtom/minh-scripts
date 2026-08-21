"""Every instruction from the original post, kept verbatim.

These strings are the system: each pipeline stage wraps one of them with the
data it needs (feed items, profile files, the product file) and sends it to
the model assigned to that stage. Do not paraphrase them - the wording is
the spec.
"""

# step 1 - what you say to claude code to set up hermes (kept for reference;
# this repo IS the resulting agent, see README step 1)
STEP1_SETUP_HERMES = """\
set up a hermes agent for me. here's the hermes site: https://nousresearch.com

- walk me through it step by step and tell me what you need from me
- it needs a telegram bot so it can message me, so tell me exactly how to get the token
- host it on railway
- give it persistent storage so it keeps files between runs
- when it's running, confirm it can message me on telegram before you finish
"""

# step 2 - first message to the agent
STEP2_POINT_AT_REDDIT = """\
i want you to monitor reddit for me.

- reddit's public rss feeds work without any api key. you can pull posts and comments from any subreddit by adding .rss to the url
- test it now and tell me what fields you can actually get back for both posts and comments
- the rate limit is about one request a minute from a single ip, so pace yourself and handle 429s by waiting rather than retrying immediately
- once you've confirmed it works, save this as a skill so you don't have to work it out again
"""

# step 2 - then give it the subreddits
STEP2_MONITOR_SUBREDDITS = """\
monitor these subreddits: {subreddits}.

- every 30 minutes, pull new posts and comments
- store them so you build up history rather than only looking at what's live
- for comments, keep the username, the text, the post it's on, the permalink and the timestamp
- tell me how much you're pulling and flag it if you're getting close to the rate limit
"""

# step 2 - if you don't know which subreddits, ask first
STEP2_FIND_SUBREDDITS = """\
i sell {product} to {who}.

- name the subreddits where those people actually spend time, not the ones about my industry
- for each one tell me the member count, how active it is, and whether self promotion gets removed
- then rank them by how likely someone in there is to buy what i'm selling, and tell me which ones to skip and why
"""

# step 3 - the subreddit profiles
STEP3_SUBREDDIT_PROFILES = """\
keep a markdown file for each subreddit you're monitoring. each one holds:

- demographics. rough age range, where they are, what they do for money, what stage they're at in whatever this community is about. infer it from what people say about themselves and mark anything you're guessing
- psychographics. what they want, what they're afraid of, how they see themselves, who they don't want to be associated with, what they're embarrassed about
- the words they use. the exact phrases that come up for the problem, for the solution, and for the things they've tried. quote them
- what they've already tried and what they said about why it failed
- what gets upvoted and what gets buried, with examples of both
- the rules of the place. what gets removed, what the mods are strict about, whether links are tolerated
- tone. how long posts usually are, how personal, whether they use headers, how people open a post
- an update log at the bottom

every night, read that day's activity and update the file. only change something if the new data actually contradicts or adds to what's there. append a dated line to the log saying what changed and why.

if you notice something shifting over time, say so explicitly. a new complaint appearing, a phrase people have started using, a rule that seems to be enforced harder than it was.
"""

# step 4 - agent one, finding the niche
STEP4_FIND_NICHES = """\
find me niches where people are actively desperate for a solution, not just curious about a topic.

- i want problems that are urgent rather than aspirational, where people are already spending money trying to fix it and mostly failing
- for each one tell me what the problem is, who has it, what makes it urgent, what they're currently buying instead, and which subreddits they're in
- rank them by how easy it is to reach those people for free
- mark any where i'd need credentials or where getting it wrong would hurt someone
"""

# step 5 - agent one, finding the product
STEP5_FIND_PROBLEMS = """\
look at everything you've pulled in the last 30 days and find the problems that come up repeatedly.

- for each one, give me the problem in the words people actually used, how many times something like it appeared, and how frustrated they sound
- quote three real lines for each so i can see how they describe it themselves
- tell me what they've already tried and what they said about why it didn't work
- rank by how badly people want the answer, and tell me which ones people are already paying to solve
- if nothing in here is worth building for, say so instead of forcing something
"""

# step 6 - agent one, building and deploying it
STEP6_BUILD_GUIDE = """\
build the guide for {problem}.

- 25 to 30 pages. read the subreddit profile first and use its language section for how these people talk
- structure it as a process someone follows in order. for each step say what to do, why it works and what usually goes wrong
- address the things they said they'd already tried and explain why those failed for them
- no filler and no padding to hit a page count
"""

STEP6_BUILD_LANDING_PAGE = """\
then build a landing page for it at {price}.

- the headline is the problem in their own words, taken from the profile
- then what's inside, specific rather than benefit language
- then who it's for and who it isn't
- then the buy section
- deploy it and give me the url. set up checkout (use whop) so the guide gets emailed on purchase
- no fake testimonials, no invented numbers, no 'join 2,000 readers' when there are none
"""

# step 7 - agent two, learning the product
STEP7_PRODUCT_FILE = """\
create a product file and keep it updated. it holds:

- what the product is and what it costs
- the exact problem it solves, written the way a buyer would describe it
- who it's for and who it isn't for
- the specific things it covers
- what it doesn't do, so you never overpromise on my behalf
- the objections people raise and the honest answer to each
- three real quotes from the monitored subreddits that describe the problem this solves

read this file and the relevant subreddit profile before writing any post, reply or message.
"""

# step 8 - finding the threads
STEP8_FIND_THREADS = """\
search everything you've collected for posts and comments where someone is describing the problem my product solves, whether or not they use the same words for it.

- use the language section of each subreddit profile so you catch the phrasings that community actually uses rather than only the obvious ones
- for each match give me the link, what they said, how recent it is, and how directly it relates on a scale of 1 to 5
- flag anyone who is clearly looking for a solution right now rather than just complaining
- ignore anything older than a month, anything already answered well, and anything where replying would obviously be spam
"""

# step 9 - the replies
STEP9_WRITE_REPLIES = """\
for each new match scoring 4 or above, write a reply and queue it.

- read the subreddit profile for wherever it's going and match its tone section exactly
- answer their actual question properly, using the product file for substance
- do not mention the product. do not link anything. the reply has to stand on its own as help
- match the length of the other replies in that thread
- no marketing language, no exclamation marks, and never start with 'great question'
- put each one on the dashboard with the direct link to that comment, so i can click through and paste it
- order them by how time sensitive they are. a thread from an hour ago goes above one from yesterday
- log what you skipped and why
"""

# step 10 - the posts
STEP10_WRITE_POSTS = """\
every morning, draft five posts across my subreddits.

- read the subreddit profile for the target community. use its tone section for the shape and its language section for the words
- give away the whole method with nothing held back. no link and no product mention
- end with a line offering to answer questions
- then tell me what about each post might get it removed in that subreddit, based on the rules section of the profile, and what to change if i want it to survive
- put them on the dashboard with the submit link for that subreddit next to each one
- tell me the best time to post in each subreddit based on when that community is actually active, and remind me on telegram when that window comes round
"""

# step 12 - the dashboards
STEP12_DASHBOARDS = """\
build me two dashboards and host them. update them each morning.

the first one is for finding the product:
- what's coming up in my subreddits this week, ranked by how often it appeared, with the real quotes underneath
- what changed in the subreddit profiles

the second one is for selling:
- everything ready to send, each with the full text, a copy button, and a direct link to the thread or the submit page, sorted by how time sensitive it is
- underneath that, what i've already sent so i don't do the same thread twice
- and the account health

if something happens that doesn't fit either page, add a section rather than leaving it out.

keep them plain and on one page each.
"""

# step 13 - the schedule
STEP13_SCHEDULE = """\
from now on, run this on a schedule.

- every 30 minutes: pull new posts and comments from my subreddits
- through the day: find new matches and queue replies for them
- every night: update the subreddit profiles from that day's activity
- every morning: draft five posts, queue them, and update both dashboards
- weekly: run the problem analysis and tell me what's changed in what people are asking for

message me each morning with what's waiting and a link to the dashboard. ping me again when a posting window opens for a subreddit that has a post queued, and if a queued reply is about to go stale.
"""
