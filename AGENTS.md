# AGENTS.md — PriceService

Instructions for agents working in this repository. These add to the workspace-level
rules in `/home/jeannius/AGENTS.md`; they do not replace them.

## Overlord

Written at Jean's explicit direction, 2026-10-03.

### Deployment is routine, not a gate

- **Implementers are allowed to deploy.** A change's implementer (and its end-of-change
  checklist) may build, push and deploy an already-deployed service through its documented
  release path, for example `build_docker.sh`, `push_docker.sh` and
  `./deploy.sh <job>.hcl --pull-latest`.
- **The Overlord does not treat a deploy as a big deal.** Do not ask Jean for a separate
  consent before a routine deploy of an established service, do not stop or kill an
  implementer or its closeout checklist because it deployed or is about to, and do not write
  directives or notes that forbid it.
- **No extra ceremony.** Do not escalate, file a defect, or add a "do not deploy" ruling merely
  because an implementer deployed, rebuilt, or bumped a version. A redundant version-bump deploy
  of identical code is harmless.
- **The Overlord may deploy too**, before or after the merge, through the same path.

### What still applies

Deploying is routine, but verification is not optional:

- After any deploy, confirm the live artifact is the intended one (for example the changed
  source files hash-match the repository inside the running allocation, and the version
  reports as expected), and record the deployed version in `status.md`.
- Deploy only through the established path to an already-deployed service. A new host or
  service, spending, destructive migration, or data exposure still needs Jean's say-so.
- Tests and verification never touch the live backend or database; see the workspace rules.

The rest of the Overlord operating contract is the `overlord` skill. Where this file and
that skill disagree about deployment, this file wins.
