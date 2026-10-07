# Profile cards

The GitHub activity and chess cards are original SVG artwork generated with Python's standard library. They contain no scripts, remote fonts, shared card endpoints, personal access tokens, or private repository access. Both themes have separate mobile artwork. Motion honors `prefers-reduced-motion`; all content remains visible when animation is disabled.

## Data and scope

- **Visible contributions** and **active days** cover exactly 365 dates, ending on the update date in UTC. An active day has at least one contribution. The source is the publicly accessible [GitHub contribution calendar](https://github.com/users/HenriqueMayer/contributions). The generator matches each dated cell with its accessible tooltip, checks every date and count, and rejects incomplete or changed markup. GitHub's HTML fragment is not a versioned API, so this validation is necessary. The native graph may display extra days to complete calendar weeks; those days are excluded from these metrics.
- The calendar shows the most recent 16 weeks on desktop and 12 weeks on mobile, ending on the same snapshot date. Empty future positions in the current week are subdued and have no contribution count. Dates remain UTC.
- Contributions are **not a count of commits or a public-only total**. They use what GitHub makes visible on the profile. This can include anonymized private contributions if the account enables them. No private repository names, code, or activity details are fetched. See [GitHub's contribution scope](https://docs.github.com/en/account-and-profile/concepts/contributions-on-your-profile).
- **Public repositories** comes from the [public user API](https://api.github.com/users/HenriqueMayer), checked against a paginated list of owned public repositories. It includes the profile repository.
- **Public code by bytes** aggregates the [languages API](https://docs.github.com/en/rest/repos/repos#list-repository-languages) for owned public repositories, excluding forks and the profile repository. The three largest languages are shown individually; remaining bytes appear as Other. This describes the source code GitHub detects, not skill, time spent, or professional work in private repositories.
- **Puzzle Rush best** is the personal best returned by [Chess.com's public player statistics API](https://api.chess.com/pub/player/hrmayer/stats). It has no connection to the illustrated board. The board is decorative, the knight follows legal L-shaped moves, and it never represents a live game. See [Chess.com PubAPI documentation](https://support.chess.com/en/articles/9650547-what-is-the-pubapi-and-how-do-i-use-it). Chess.com responses may be cached for up to 12 hours.
- **Rapid rating** is the last rating returned by that same statistics API for the rapid category. It is not an exclusive 10-minute rating pool. The card separately shows the time control and UTC date of the most recent rated standard rapid game, verified against the public monthly archive containing the statistics timestamp. Statistics and archive timestamps must agree within 60 seconds; their caches can differ, so a mismatch fails the refresh rather than displaying an unverified time control.
- On 2026-10-07, rapid rating was **1304** and the [last rated rapid game](https://www.chess.com/game/live/130813803837) ended on **2025-01-17 at 01:03:55 UTC**. Its [public archive](https://api.chess.com/pub/player/hrmayer/games/2025/01) reports `time_control: "600"`, meaning 10 minutes per player with no increment. The rating statistics timestamp is one second later. The visible last-game date avoids implying that an inactive rating was earned or changed on the latest profile refresh. A later game with another control will show its actual length and increment instead.

The public snapshot is saved in `assets/profile-data.json`, with its update date, exact contribution period, language byte counts, and source URLs. The chess record additionally keeps its own fetch date, rapid rating, last game's URL, archive URL, exact control, end timestamp, and rating-update timestamp. SVG title and description elements carry accessible scope and dates. A chess-only editorial update can preserve the existing GitHub snapshot and its date while refreshing the chess record and four chess SVGs.

## Refresh

From the repository root:

```sh
python3 scripts/update-profile.py
```

For an explicit historical ending date:

```sh
python3 scripts/update-profile.py --date 2026-10-06
```

The explicit date controls the contribution window and snapshot label. Repository and chess data are fetched when the command runs; this option does not retrieve historical versions of those APIs. GitHub must still expose every date in the requested contribution period.

The workflow refreshes once daily at 06:23 UTC and supports manual dispatch. Changes to the generator or workflow also trigger a refresh after reaching `main`. Scheduling and dispatch do not run on the draft development branch. It uses the built-in `GITHUB_TOKEN`, with `contents: write` limited to the refresh job, and commits only the nine generated files. The official checkout action is pinned to the verified v6 commit. No installation step or extra secret is needed.

Fetching and rendering complete before any existing generated file is replaced. An API, parsing, or data-validation failure exits with an error and preserves the previous snapshot and all cards. Each changed output is replaced atomically. If a scheduled refresh fails, inspect its Actions log and rerun it after repairing the source or generator; the previously committed images keep rendering on the profile.

GitHub schedules can be delayed and can be disabled after 60 days without repository activity. [Official scheduling behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule). Refresh commits update the profile repository's activity; those contributions naturally enter later snapshots.
