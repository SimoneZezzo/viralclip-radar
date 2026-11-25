# Catalog collectors

One additional Twitch category per collector, added one at a time (owner
decision 2026-11-25, [action plan §5bis](ACTION_PLAN.md#5bis-feature-nuove-e-giochi-mai-visti)).
Each catalog collector runs the existing legacy discovery path, which is
adequate for the observed-at-cutoff population; category-wide coverage is
not certified. GTA V and GTA VI keep their own units and are never touched by
these steps. Every VPS step needs the owner's authorization for that game.

## Naming

For category ID `<ID>` (digits only, the exact Twitch category ID):

| Item | Value |
| --- | --- |
| Unit | `viralclip-game@<ID>.service` from [deploy/viralclip-game@.service](../deploy/viralclip-game@.service) |
| Account | system user and group `vcg-<ID>` (also the reliability profile) |
| Database | `/var/lib/viralclip-game-<ID>/game.sqlite3` |
| Settings | `/etc/viralclip/game-<ID>.env` from [deploy/game.env.example](../deploy/game.env.example), root:root 0600 |
| Start gate | `/etc/viralclip/game-<ID>-authorized` |
| Runtime | `/opt/viralclip-catalog` (own release and venv; the GTA trees stay as they are) |

Each collector uses its own Twitch application: Helix rate limits follow the
client ID.

## 1. Choose the game

With the new application's credentials in the environment (never in Git or
chat), estimate volume without any database:

```text
uv run --offline --no-sync python -m viralclip probe-volume --game-id <ID> [--game-id <ID2> ...]
```

The probe samples eight one-hour windows from the last day. Truncated windows
mean the estimate is a lower bound. Prefer a non-GTA game with recurring
activity, many broadcasters and well over 50 clips a day (the c1 catalog rule
needs informative daily pools). Check the estimated MB/day against free disk
with a 10 GB reserve; `df -h /` on the VPS gives the current margin.

## 2. Install (authorized VPS session)

Run a read-only preflight of both GTA collectors first
([dual-collector operations](DUAL_COLLECTOR_OPERATIONS.md)). Then, with a
reviewed release unpacked and verified at `/opt/viralclip-catalog` as in
[package a reviewed revision](MILESTONE_1_ROLLOUT.md#package-a-reviewed-git-revision):

```bash
set -e
ID=<ID>
test -n "$ID" && [[ "$ID" =~ ^[0-9]+$ ]]
test ! -e "/var/lib/viralclip-game-$ID"
sudo -n useradd --system --no-create-home --shell /usr/sbin/nologin "vcg-$ID"
sudo -n install -d -o "vcg-$ID" -g "vcg-$ID" -m 0700 "/var/lib/viralclip-game-$ID"
sudo -n install -o root -g root -m 0600 /dev/stdin "/etc/viralclip/game-$ID.env" < game.env
sudo -n -u "vcg-$ID" /opt/viralclip-catalog/.venv/bin/python -B -m viralclip \
    --db "/var/lib/viralclip-game-$ID/game.sqlite3" init-db
sudo -n systemd-analyze verify /opt/viralclip-catalog/deploy/viralclip-game@.service
sudo -n install -o root -g root -m 0644 /opt/viralclip-catalog/deploy/viralclip-game@.service \
    /etc/systemd/system/   # once, for the first catalog game
sudo -n systemctl daemon-reload
sudo -n touch "/etc/viralclip/game-$ID-authorized"
sudo -n systemctl enable --now "viralclip-game@$ID.service"
```

`game.env` is the filled template, prepared in the session from a secure
input and removed afterwards. The unit's preflight refuses a missing database,
missing credentials, any other category, a changed cadence or a database that
holds another game.

## 3. Verify

```bash
systemctl status "viralclip-game@$ID.service" --no-pager
sudo -n journalctl -u "viralclip-game@$ID.service" --since '15 minutes ago' --no-pager
sudo -n -u "vcg-$ID" /opt/viralclip-catalog/.venv/bin/python -B -m viralclip \
    --db "/var/lib/viralclip-game-$ID/game.sqlite3" health
```

Expect advancing discovery, scheduled snapshots and no 429s. Record the UTC
start time: the game's c1 2/2/7 calendar starts at the first full UTC day
after it ([c1 protocol](CHRONOLOGICAL_EVALUATION.md#challenger-protocol-c1)).
Enable the five-minute monitor once the reliability runtime has a release
that knows catalog profiles:

```bash
sudo -n systemctl start "viralclip-reliability@vcg-$ID.service"
sudo -n journalctl -u "viralclip-reliability@vcg-$ID.service" -n 35 --no-pager
sudo -n systemctl enable --now "viralclip-reliability@vcg-$ID.timer"
```

For the first days, check daily: discovery delay, overdue jobs, label
coverage and database growth. Add the next game only when these hold.

## Stop or roll back

```bash
sudo -n systemctl disable --now "viralclip-game@$ID.service" "viralclip-reliability@vcg-$ID.timer"
sudo -n rm -f "/etc/viralclip/game-$ID-authorized"
```

Keep the database: deleting collected data is a separate owner decision.
