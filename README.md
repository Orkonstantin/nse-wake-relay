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

This repository holds three workflows. `.github/workflows/wake.yml` is copied byte for byte from the project's reviewed
`ops/wake-relay` template (its header comment still calls it a template; here it is the real thing); it is the precise
path and needs the token below. `.github/workflows/wake-early.yml` is a backup that needs no token at all (see "Backup
that needs no token" further down). `.github/workflows/activity-evidence.yml` wakes nothing: it records what the service's
public health page shows during the trading day (see "Evidence without a computer awake" further down). There are no
secrets here and none are needed. A token limited to this repository can neither read nor change anything else; it can only
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
* Cost: runner time is free for a public repository; up to three runners can sit waiting on a weekday, for up to about 3
  hours in summer time and up to about 4 hours after the clock change in November (the earliest slot starts 05:11 UTC, the
  rescue is at 08:00:30 or 09:00:30 UTC). Render normally sees two tiny requests per run (the wake and the rescue), six
  for three runs; at most eighteen if every attempt of every run fails.
* Rehearse it by hand (this starts the sleeping service, 15 instance minutes): in the Actions tab choose `wake-early`, Run
  workflow, and fill `wake_at` and `rescue_at` with UTC times a few minutes ahead (for example `2026-10-04T07:00:00Z` and
  `2026-10-04T07:07:30Z`); `skip` leaves a stage out. Leaving both fields empty runs the production defaults (03:53:00 and
  04:00:30 New York time of today), including the same checks a scheduled run makes; use that to rehearse the real thing.
* GitHub disables scheduled workflows of a public repository after 60 days without repository activity. The first sign
  would be that no `wake-early` run appears on a weekday morning; pushing any commit re-enables them.

## Evidence without a computer awake: `activity-evidence`

`.github/workflows/activity-evidence.yml` wakes nothing. It reads the **public** health page of the service
(`https://nse-api-n959.onrender.com/health`) at fixed New York times and judges what it shows, so that the evidence of a
trading day exists even when no computer is awake. It needs no token, no secret and no repository permission, and it does
not use the operator fields (those need the internal key).

**A running server is not a ready worker, so three levels are judged separately:**

| Level | Question | Evidence on the page | Checks |
|---|---|---|---|
| Server live | Does the web process answer? | HTTP 200 from `/health` in under 30 s, and `supervisor.last_started_at`, when the supervisor of the window loop started: the start of the web process while `supervisor.restarts` is 0, so the page itself shows that the server was up before 08:00:00Z, without the Render log. A slower answer from a supervisor that started after the request was sent means the request woke the service: FAIL inside the window, allowed (`N/A`) while no window is open. A slow answer from one that started earlier was a stall: FAIL. The same start is `Application startup complete` in the service log, which this workflow does not read | `server_live` |
| Worker started | Did the duty cycle start the worker when the session window opened? | `duty_cycle.phase`, `windows_run`, `last_started_at`: set when the window loop calls the worker, before the worker has finished booting | `window_open`, `worker_started` |
| Worker ready | Has the worker finished booting, is its heartbeat fresh, and does the service judge itself healthy? | `worker.ok` and `booted_at`, `readiness.status` and `startup_grace`, job freshness, `catch_up`, `supervisor`, failed Telegram sends | `worker_heartbeat`, `readiness_status`, `startup_grace_over`, `jobs_fresh`, `catch_up_done`, `supervisor_stable`, `telegram_delivery` |

`supervisor.running` is true from the start of the process (it supervises the window loop, not the worker), so it is never
used as a sign of a running worker.

**Result words.** `PASS`: measured on time and the criterion holds. `FAIL`: measured and it does not hold. `DEGRADED`:
measured and partly wrong (the service says DEGRADED, stale jobs, a restart, failed sends). `MISSING`: not measured, or not
measured at the checkpoint: no answer, a field absent, still inside the 600 s startup grace (stale jobs are hidden then), a
probe that arrived more than two minutes late, a run that never started, and **a weekday on which the service says there is
no session window** (a market holiday would explain it, but the service decides that from its own exchange calendar, which
is the thing being checked, and this workflow has no calendar of its own). `N/A`: does not apply (a weekend has no session
window; no wake-up gap to catch up on; a sleeping service woken while no window is open). **MISSING is never a pass.** A
run is green only if every checkpoint is `PASS` or `N/A`. A red run makes GitHub e-mail the owner (if notifications are
on), so it means "look at it", not "it is broken".

**Checkpoints** (New York time, computed on the runner, so the clock change needs no edit; the cron entries are UTC and
early enough for both offsets, and every slot exists twice because GitHub delays and drops scheduled runs):

| Id | Time | Judged as | Cron slots (UTC) |
|---|---|---|---|
| C1 | 04:05:00 | early: server, worker started, heartbeat, readiness, restarts. Jobs and catch-up are `N/A` (the first minutes are inside the grace) | 06:30 and 07:30 |
| C2 | 04:30:00 | steady: all checks, including job freshness after the grace and the wake-up catch-up. Not earlier: the interval jobs make their first poll one interval after the start, and a job that has not polled yet counts as stale once the 600 s grace is over (on 2026-10-02 readiness showed `stale jobs: gdelt` at 08:15:04Z and was HEALTHY at 08:20:07Z, 08:25:12Z and 08:30:14Z) | same runs as C1 |
| C3 | 13:00:00 | steady (regular session; the IEX stream is part of the service's own readiness) | 15:30 and 16:30 |
| C4 | 19:50:00 | steady, ten minutes before the window closes | 20:30 and 22:30 |
| C5 | 20:02:00 | closing: window closed, worker stopped on schedule, readiness `IDLE`, no restart all day | same runs as C4 |

A run that starts after a checkpoint reads at once, but only while the service is expected to be awake, because any request
wakes a sleeping service: until 20:00 New York time for C1 to C4 (the regular end of the window; for C4 that is ten minutes)
and for eight minutes after C5. Later than that the checkpoint is `MISSING` and nothing is sent. What the service keeps
(first start, restarts, the catch-up result, the stop) is still judged from a late read; everything about "now" becomes
`MISSING`. A slot that GitHub never starts leaves no run at all: count a checkpoint without any run as `MISSING`.

**Holidays and early closes.** On a weekday without a window (a market holiday, or an early-close day at 19:50, when the
window ended at 17:00) `window_open` is `MISSING` and the later checkpoint of the same run sends nothing more. The first
read of a group that finds the service asleep wakes it (about 15 instance minutes; reported as `N/A` for `server_live`).
Expect a red `MISSING` run on such days; it is the honest answer, and it is also the answer if the service's calendar were
wrong on a real trading day. On an early-close day C5 therefore cannot show the stop. If the duty cycle is switched off in
the service (`duty_cycle.enabled` false) `window_open` is a `FAIL`, because the free-tier hours budget assumes the window.

**Reading it.** Every checkpoint logs a `CHECKPOINT` line, one `CHECK` line per check and one `EVIDENCE` line (JSON with the
reduced snapshot: no error texts, no job payloads), and the run summary has a table:

```
gh run list -R Orkonstantin/nse-wake-relay --workflow activity-evidence.yml --created 2026-10-05 --json databaseId,event,createdAt,conclusion
gh run view RUN_ID -R Orkonstantin/nse-wake-relay --log | grep -E 'CHECKPOINT|CHECK |EVIDENCE'
```

GitHub keeps run logs for 90 days by default. The repository is public, so the logs are public: they hold only what the
public health page already shows.

**What it cannot see.** The bandwidth tripwire's day total and the kernel transmit counters are operator fields
(`X-Internal-Api-Key`) and are not read here. Render's hourly bandwidth series, memory series and service log are Render's
and are read there. A checkpoint shows one minute plus what the service retains; it is not a continuous watch.

**Cost.** One read per checkpoint, up to ten a day while both slots of a group run. The size of each answer is logged
(`bytes`). On the service a read is a database read and one low-priority Alpaca snapshot request (that is how `/health`
works). C5 runs two minutes after the close, so that evening's idle shutdown follows C5 by about 15 minutes instead of the
close. On a weekday without a window, the first read of group B and of group C each wake the sleeping service (see above).

**Rehearse or re-run by hand** (this starts the service if it sleeps): Actions -> `activity-evidence` -> Run workflow.
`group` takes `A`, `B` or `C` and runs that group's real checkpoints of today. `times` takes UTC times
(`C1=2026-10-05T08:05:00Z,C2=2026-10-05T08:30:00Z`); C1 is judged as the early checkpoint, C5 as the closing one, any other
name as a steady one. Outside the window a rehearsal on a weekend shows `window_open N/A` and a green run, and on a weekday
`MISSING` and a red one: it exercises the mechanics, not the PASS path.

**Switch it off:** disable the workflow in the Actions tab, or delete the file.

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
