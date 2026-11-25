# Live publishing (proposal, pending reviewer review)

Draft by reviewer, 2026-11-25. Owner decisions already taken: Cloudflare Pages
hosts the static front end, Cloudflare R2 hosts the ranking JSON; every
refresh records the top 200 in the prediction registry; the site shows the
top 50 with "show more" up to 200
([action plan §5bis](ACTION_PLAN.md#5bis-feature-nuove-e-giochi-mai-visti)).
Nothing here is implemented or installed yet.

## Problem

`rank` (`predictions.rank_pool`) scores one game × UTC day × cutoff pool and
records every clip of the pool. GTA VI adds about 145k clips a day, so a
15-minute refresh would write millions of registry rows a day. Evaluations do
not need those rows: c1 and c2 rebuild full orders from sealed exports.

## Proposed design

1. **Live pool.** Per game, the clips created in the last 24 hours whose
   60-minute cutoff has passed, each scored with features observed by its own
   cutoff (the existing `dataset.candidate` rules). A rolling window avoids
   the empty ranking a UTC-day pool shows after midnight.
2. **Registry record.** One sealed run per refresh with `pool_size`, the
   window bounds and only the top 200 predictions. `link-outcomes` keeps
   working on the recorded rows. The run declares `top_k = 200`, so nobody
   reads it as a full pool.
3. **Cadence.** A systemd timer every 15 minutes, falling back to 30 if a
   GTA VI refresh is too slow (to be measured on a synthetic day of 145k
   clips). It reads collector databases with `mode=ro` and `query_only`, so
   the single writer per collector database is unchanged.
4. **Method per game.** The scorer is the method that passed its own test for
   that game (c2, else c1, else the declared `latest_views` baseline), set in
   a reviewed configuration file, never chosen automatically.
5. **Publication.** `viralclip publish` writes per-game JSON and the index
   atomically to a staging directory, then uploads it to R2 (object writes
   in index-last order). The site is deployed to Pages only when the front
   end changes. Credentials: an R2 API token scoped to one bucket, in a
   root-only environment file.

## Open questions for review

- Registry schema: add `top_k` and window columns additively, or a separate
  live table? Effect on `link-outcomes`, `shortlist` and the demo.
- Accounts and permissions: the GTA V database is `0600` for its service
  user. Run one ranking unit per game as that game's collector account with
  a per-game registry, then a publisher account that reads the registries?
- Upload client: `boto3` in a separate publisher venv, `rclone`, or
  Cloudflare's `wrangler`? Collector installs must stay unchanged.
- Disk: about 29 MB/day for five games at 15-minute refreshes (estimate).
- Live timeliness: report how many ranked clips already have a 24-hour
  outcome observed at scoring time (none should, in a 24-hour window).
