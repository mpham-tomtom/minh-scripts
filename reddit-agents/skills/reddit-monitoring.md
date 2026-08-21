# skill: reddit monitoring over public rss

saved after confirming the feeds work (step 2), so this never has to be
worked out again.

## the feeds

add `.rss` to almost any reddit url and structured atom xml comes back, no
api key and no login:

- new posts in a subreddit: `https://www.reddit.com/r/{sub}/new/.rss`
- new comments in a subreddit: `https://www.reddit.com/r/{sub}/comments/.rss`

## fields that actually come back

posts: title, the OP (author name), the link to the thread, the body
(html inside `<content>`), and a timestamp (`<updated>`).

comments: the username, the full comment text, the post it's on (in the
title, "u/x on <post title>"), a permalink straight to the comment, and a
timestamp.

that's everything this system needs. entry `<id>` values are stable and
unique - use them for dedup.

## the rate limit

about one request a minute from a single ip; going over returns 429.

- pace every request: minimum 60 seconds between requests, globally
- handle 429 by waiting (honour `retry-after`, default 120s) rather than
  retrying immediately
- send a descriptive user-agent; the default python one gets throttled harder
- sixty requests an hour is far more than this needs: two requests per
  subreddit per 30-minute pull means 15 subreddits fits inside the limit

## implementation in this repo

`redditagents/reddit_rss.py` - `RateLimiter` does the pacing, `RedditRSS`
fetches and parses, `RedditRSS.test()` reports the fields back.
