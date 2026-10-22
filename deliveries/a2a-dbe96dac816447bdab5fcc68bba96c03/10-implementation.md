# NIU-298 implementation status

## Result

No product code was added. The requested Yggdrasil package is absent from the
specified `regin` base, so implementation cannot preserve the required
hexagonal boundaries or satisfy the declared-file contract.

## Related landed functionality

`regin` does contain a different, already-landed authenticated realm-detail
SSE stream in `src/niuu/adapters/inbound/rest_realms.py`:

- `GET /api/v1/realms/{slug}/stream`
- immediate `realm.detail` snapshot, changed-snapshot detection, and keepalive
  frames
- `realm_detail_stream_interval_seconds` configuration composed by Volundr and
  the CLI host

That implementation is not the ticket's `/api/v1/yggdrasil/...` API, does not
have the stated connection-manager/poller architecture, and cannot responsibly
be relabelled as NIU-298 completion.

## Evidence

- `find src -maxdepth 1 -type d` has no `yggdrasil` package.
- `git log --all -- src/yggdrasil tests/api/test_routes_sse.py tests/sse` is
  empty.
- `git ls-remote --heads origin '*ygg*' '*niu-298*' '*sse*'` found no matching
  branch.
- `gh pr list --repo niuulabs/niuu --state all --search 'NIU-298'` found no
  NIU-298 pull request.

## Required operator decision

Provide the repository revision/worktree containing the Yggdrasil service, or
revise NIU-298 to name the existing Niuu package and its intended API contract.
The tracker remains `In Progress`. Draft PR [#1162](https://github.com/niuulabs/niuu/pull/1162) targets `regin` and contains only this durable blocker handoff; it is not ready to merge.
