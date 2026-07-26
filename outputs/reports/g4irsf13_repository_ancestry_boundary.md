# G4IRSF13 Repository Ancestry Boundary

Status: `RECORDED_NON_BLOCKING_BOUNDARY`.

- Scientific branch: `codex/czr005-rewrite` at phase start `f05e5432c5faa85d8b11d2d153e7da96f340d34c`.
- Upstream scientific branch: `origin/codex/czr005-rewrite` at the same phase-start SHA.
- Local `main`: `236f7b10bdf40f708d45f60ddd6cea912c462c21`.
- Local-main merge base: `236f7b10bdf40f708d45f60ddd6cea912c462c21`.
- `origin/main`: `c5c2d2cb050f62b5160cdfb6c29895f03af12486`.
- Origin-main merge base: `NONE`.

The live audit differs slightly from the planning assumption: the local
`main` ref shares history with the scientific branch, while `origin/main`
has no common ancestor with the phase-start commit. The remote boundary is
the publishing constraint. G4IRSF13 will not force-push, merge unrelated
histories, or rewrite the scientific history. This boundary does not block
the algorithm work; any cross-history pull request requires an explicit
review-base decision.
