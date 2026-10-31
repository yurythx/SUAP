# Issue tracker: GitLab

Issues and PRDs for this repo live as GitLab issues. Use the [`glab`](https://gitlab.com/gitlab-org/cli) CLI for all operations.

## Conventions

- **Create an issue**: `glab issue create --title "..." --description "..."`. Use a heredoc for multi-line descriptions. Pass `--description -` to open an editor.
- **Read an issue**: `glab issue view <number> --comments`. Use `-F json` for machine-readable output.
- **List issues**: `glab issue list -F json` with appropriate `--label` filters.
- **Comment on an issue**: `glab issue note <number> --message "..."`. GitLab calls comments "notes".
- **Apply / remove labels**: `glab issue update <number> --label "..."` / `--unlabel "..."`. Multiple labels can be comma-separated or by repeating the flag.
- **Close**: `glab issue close <number>`. `glab issue close` does not accept a closing comment, so post the explanation first with `glab issue note <number> --message "..."`, then close.
- **Merge requests**: GitLab calls PRs "merge requests". Use `glab mr create`, `glab mr view`, `glab mr note`, etc. - the same shape as `gh pr ...` with `mr` in place of `pr` and `note`/`--message` in place of `comment`/`--body`.

Infer the repo from `git remote -v` - `glab` does this automatically when run inside a clone.

## When a skill says "publish to the issue tracker"

Create a GitLab issue.

## When a skill says "fetch the relevant ticket"

Run `glab issue view <number> --comments`.

## Wayfinding operations

The `wayfinder` skill needs a map issue, child tickets, blocking edges, and a frontier
query. Here is how each one is expressed on this GitLab.

- **The map** is an issue labelled `wayfinder:map`. Find the open ones with
  `glab issue list --label wayfinder:map`.
- **Tickets** are ordinary issues labelled `wayfinder:<type>` (`research`, `prototype`,
  `grilling`, `task`). The five `wayfinder:*` labels already exist on `cosinf/suap`.
- **Parenthood** is a body line, not a work-item parent: every ticket opens with
  `**Mapa:** #<map>`. GitLab's native work-item hierarchy needs GraphQL and buys nothing
  the body line doesn't. Each ticket is also linked to the map with `relates_to`, so the
  map's *Linked items* panel lists them.
- **Blocking has no native form here.** This instance is GitLab CE, and the blocking link
  type is a paid feature — `POST /issues/:iid/links` with `link_type=is_blocked_by`
  answers `403 Blocked issues not available for current license`. The fallback is a body
  line on the blocked ticket, naming numbers so it can be grepped:
  `**Bloqueado por:** #16970 (rótulo curto), #16974 (rótulo curto).`
  Mirror each edge as a `relates_to` link so it shows up in the UI.
- **Create the links** (relates_to works on CE):
  ```
  glab api -X POST "projects/cosinf%2Fsuap/issues/<from>/links" \
    -f target_project_id=cosinf/suap -f target_issue_iid=<to> -f link_type=relates_to
  ```
- **The frontier** is the open, unassigned tickets of a map whose blockers are all closed.
  List the candidates, then check each one's `**Bloqueado por:**` line:
  ```
  glab issue list --label wayfinder:grilling,wayfinder:research,wayfinder:prototype,wayfinder:task -F json
  ```
  A ticket with no `**Bloqueado por:**` line is unblocked by definition.
- **Claiming a ticket**: `glab issue update <number> --assignee <usuário>` before any work.
- **Resolving**: `glab issue note <number> --message "<resposta>"`, then
  `glab issue close <number>`, then append the one-line gist to the map's
  *Decisions so far* with `glab issue update <map> --description ...`.
