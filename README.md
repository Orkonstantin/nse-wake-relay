# nse-wake-relay

Starts the sleeping free-tier `nse-api` service at 03:50 New York time on weekdays, without any computer being awake.

cron-job.org is punctual, but Render's routing layer refuses its request to a sleeping service (HTTP 429 and 503
`hibernate-wake-error`, no instance started; the cause is not established). The same request from a GitHub runner starts
the service in about 60 seconds. GitHub's own `schedule` trigger is often late, but a dispatch through the API starts a
run within seconds. So:

```
cron-job.org (03:50 America/New_York, weekdays)
  -> POST api.github.com/repos/Orkonstantin/nse-wake-relay/actions/workflows/wake.yml/dispatches   (204, about 1 s)
    -> GitHub runner: GET https://nse-api-n959.onrender.com/livez    (cold start, about 60-70 s, 4 attempts)
```

This repository holds nothing else: `.github/workflows/wake.yml` is copied byte for byte from the project's reviewed
`ops/wake-relay` template (its header comment still calls it a template; here it is the real thing). There are no secrets
here and none are needed. A token limited to this repository can neither read nor change anything else; it can only
trigger Actions in this repository.

## One-time setup (the repository and the workflow already exist)

1. **Create the token.** GitHub -> Settings -> Developer settings -> Personal access tokens -> Fine-grained tokens ->
   Generate new token:
   * Name: `cron-job-org-wake`
   * Expiration: 1 year (put a reminder in your calendar two weeks before)
   * Repository access: **Only select repositories** -> `nse-wake-relay`
   * Permissions -> Repository permissions -> **Actions: Read and write** (Metadata: Read-only is added by GitHub).
     Nothing else.
   * Copy the token once. Never paste it into a chat, a commit or a log.
2. **Create the cron-job.org job** (a new job; leave the old one alone). Console -> Cronjobs -> Create cronjob ->
   **Import from cURL** and paste this, with your own value for `TOKEN`:

   ```
   curl -X POST \
     -H "Accept: application/vnd.github+json" \
     -H "Authorization: Bearer TOKEN" \
     -H "X-GitHub-Api-Version: 2022-11-28" \
     -H "User-Agent: nse-wake-relay" \
     -H "Content-Type: application/json" \
     -d '{"ref":"main"}' \
     https://api.github.com/repos/Orkonstantin/nse-wake-relay/actions/workflows/wake.yml/dispatches
   ```

   Then set, on the three tabs:

   | Tab | Field | Value |
   |---|---|---|
   | Common | Title | `nse wake via GitHub dispatch` |
   | Common | Save responses in job history | on |
   | Common | Schedule | Custom: Days of month every, Months every, **Days of week Monday-Friday, Hours 3, Minutes 50** (crontab `50 3 * * 1-5`) |
   | Notifications | execution of the cronjob fails | on, notify after **1** subsequent failure |
   | Notifications | execution of the cronjob succeeds after it failed before | on |
   | Advanced | Time zone | **America/New_York** (so 03:50 stays 03:50 when the clocks change) |
   | Advanced | Request method / Request body | `POST` / `{"ref":"main"}` (filled by the import; check them) |
   | Advanced | Timeout | 30 seconds |

3. **Test run** (Test run button). The expected answer is **HTTP 204** with an empty body. Then look at this
   repository's Actions tab: a `wake` run appeared a few seconds later. A 401 means the token is wrong or expired, a 403
   or 404 means the token cannot see the repository or lacks Actions write, a 422 means the workflow file is not on `main`.
4. **Check the first real run.** On the next weekday after 03:50 New York time (07:50 UTC in summer, 08:50 UTC in
   winter): the run's creation time in the Actions tab is within a few seconds of that time, and the Render log of
   `nse-api` shows the instance starting about then. A manual test run is a rehearsal; only this one shows that the
   schedule works unattended.
5. **Keep the other paths.** The existing cron-job.org job `nse-api wake (duty cycle)` is the outage check, not a waker:
   it GETs `/livez` at 03:55 and 03:57 and e-mails when the service is still asleep, which after this relay is the signal
   that the relay failed (a dispatch at 03:50 has the service answering by about 03:52). A Mac agent and a backup
   workflow in the main project stay as independent second paths; each wake request is idempotent.

## Operating notes

* **What a dispatch can do:** send one GET to `https://nse-api-n959.onrender.com/livez` (up to four attempts, at most
  about eight minutes). The workflow has no inputs, no secrets and no repository permissions. A leaked token could start,
  cancel or re-run workflow runs in this one repository (and so wake the service when nobody asked, which uses free
  instance hours); it could not change code or touch any other repository. Delete the token on GitHub and the job on
  cron-job.org to revoke it.
* **Cost:** one wake is under 0.2 MB of Render outbound bandwidth (measured 2026-10-03) and 15 instance minutes; the
  runner time is free for a public repository.
* **Holidays and weekends:** the cron-job.org schedule is Monday-Friday only. A market holiday wakes the service once for
  nothing; it sleeps again 15 minutes later.
* **When it fails:** cron-job.org e-mails after the first failed run. Fix the token (renew yearly) or look at the run in
  the Actions tab.
* **Remove it:** delete the cron-job.org job, the token and this repository.
