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

This repository holds two workflows. `.github/workflows/wake.yml` is copied byte for byte from the project's reviewed
`ops/wake-relay` template (its header comment still calls it a template; here it is the real thing); it is the precise
path and needs the token below. `.github/workflows/wake-early.yml` is a backup that needs no token at all (see "Backup
that needs no token" further down). There are no secrets here and none are needed. A token limited to this repository can
neither read nor change anything else; it can only trigger Actions in this repository.

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
   that the relay failed (a dispatch at 03:50 has the service answering by about 03:52). The `wake-early` workflow
   of this repository (no token needed, wake at 03:53, rescue at 04:00:30), a Mac agent and a backup workflow in the main
   project stay as independent further paths; each wake request is idempotent.

## Backup that needs no token: `wake-early`

`.github/workflows/wake-early.yml` needs nothing from the owner: no token, no secret, no cron-job.org job, and no computer
awake. GitHub starts it from its own `schedule` trigger, which is not punctual (in the main project's history, 20 mornings:
the first scheduled run at or after 07:50 UTC came 46 minutes late at the median, 92 at the 90th percentile and 222 at
worst; about one hourly slot in three was never delivered). So the workflow does not need to be on time. It is scheduled
hours early (05:11, 06:11 and 07:11 UTC on weekdays) and the runner then waits for the exact New York time:

| New York time | What the runner does |
|---|---|
| 03:53:00 | `GET /livez`, up to 4 attempts 60 s apart (the wake) |
| 04:00:30 | `GET /livez` once more, up to 2 attempts 30 s apart (the rescue: the market window opens at 04:00, so if nothing woke the service by then this does; if the service is up it is one tiny response) |

* A slot that starts after 03:53 sends at once; one that starts after 11:00 New York time does nothing. If the wake request
  itself runs past 04:00:30 there is no second request.
* New York time is computed on the runner, so the clock change needs no edit. The cron entries are UTC and early enough for
  both offsets.
* Several slots can wait at the same moment; their requests are identical and idempotent (a request to an up service costs
  one tiny response). Each run prints one `RESULT` line per request with the send time, HTTP status, seconds and a class:
  `already_up` (answered in under 10 s) or `cold_start` (took 10 s or more, so the request met a sleeping or booting
  service). A class is that request's own result; whether it caused the start is read from the service's own log.
* A run fails (and GitHub e-mails the owner, if notifications are on) only when its last request got no live answer.
* Cost: runner time is free for a public repository; up to three runners can sit waiting for up to about 3 hours on a
  weekday. Render sees at most six tiny requests.
* Rehearse it by hand (this starts the sleeping service, 15 instance minutes): in the Actions tab choose `wake-early`, Run
  workflow, and fill `wake_at` and `rescue_at` with UTC times a few minutes ahead (for example `2026-10-04T07:00:00Z` and
  `2026-10-04T07:07:30Z`); `skip` leaves a stage out.
* GitHub disables scheduled workflows of a public repository after 60 days without repository activity. The first sign
  would be that no `wake-early` run appears on a weekday morning; pushing any commit re-enables them.

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
