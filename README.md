# Courtside

Local auction preparation and live draft workspace for Bald mambas.

Double-click **Start Courtside.cmd**, then visit http://127.0.0.1:8765. The server binds only to this computer. Python and httpx are supplied by the existing NBA Player Stats MCP environment.

## Features
- ESPN player pool with pagination; prior-season actuals and next-season projections selected by season, source, and full-season split.
- Nine category per-game/totals view, FGA/FTA, games played, category auction estimates, sortable table, search, position/tier/status/tag/NBA-team filters. Exclude any combination of tags, tiers or positions; Reset clears these reversible filters.
- Quick tier adjustment beside each player and 1v1 comparisons of actuals, projections, shooting volume and personal evaluations.
- Autosaved evaluations, personal ranks, target/max prices, confidence, discussion flag, tiers, notes and tags.
- Tags and collection badges appear beneath player names. The Tags panel has multi-select checkboxes for tags and collections (all selected must match). The tag editor supports existing tags, adding new tags and removing assigned tags; duplicate tags are blocked regardless of capitalization or surrounding spaces.
- Named collections with overlapping membership; create, rename and delete.
- Live draft polling, all-team budgets, roster slots, maximum legal bids, manual entries/corrections, undo and explicit ESPN conflict resolution.
- Clear connection errors, last-success time, automatic retry and cookie replacement.
- Live roster category sums alongside the average of the other teams, with data coverage shown.
- SQLite persistence, daily local database backups, named research checkpoints and research-only JSON export/import.

## Saving preparation across updates
Open **Saved research**, enter a name and choose **Save checkpoint**. Each checkpoint offers **Download** for a portable JSON file and **Restore** for local recovery. After installing a new version, use **Upload research file** (or **Restore research** in the sidebar). Notes, tags, tiers, rankings, prices, collections and filters are included. Restoring first creates an automatic safety checkpoint and leaves live purchases and credentials untouched. Keep the `data` directory when replacing application files.

## Data semantics
ESPN ROTO rankings match this league's category scoring. Unpublished auction values are marked with an asterisk. Missing data is shown as a dash, not zero. Prior-season stats are source 0; projections are source 1. Stat IDs are verified against ESPN's actual payload (REB 6, AST 3, STL 2, BLK 1). Color thresholds use the active pool with at least 15 games, not a recommendation model. FG/FT percentages are never divided by games.

Polling occurs every 15 seconds, backing off to 120 seconds after failures. Player refresh occurs at startup, every six hours, and on Refresh ESPN. The app does not submit bids or change ESPN rosters. Live draft response availability/latency depends on ESPN. Pre-draft placeholder picks are ignored. Manual disagreements remain visible until the user accepts ESPN or corrects the entry.

The live comparison uses purchased players and the selected source and stat format. Counting categories sum per-game values or season totals. Team FG% and FT% use combined makes divided by combined attempts. Other-team averages weight each team equally. Empty teams count as zero for counting stats; teams without attempts are omitted from percentage averages. Missing player stats are omitted and coverage is displayed.

Credentials live in `data/connection.json`, are never sent to the browser, and are excluded from exports. All local data and credentials are ignored by the workspace `.gitignore`. Research imports do not overwrite purchases. Daily database backups contain player/research/draft data, not credentials.

The integration uses the same ESPN API as the installed MCP, with corrected filters, pagination, stat mappings, and source selection. A standalone app does not depend on an active Codex chat. The NBA stats MCP remains available for independent historical cross-checks.

Run tests with `../nba-player-stats-mcp/.venv/Scripts/python.exe -m unittest discover -s tests -v` from this folder.
