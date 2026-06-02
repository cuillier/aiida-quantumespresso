---
name: commit-conventions
description: Use when making commits, creating branches, or preparing pull requests for aiida-quantumespresso.
---

# Commit and PR conventions for aiida-quantumespresso

## Branching and versioning

- All development happens on `main` through pull requests.
- Recommended branch naming convention: `<prefix>/<short_description>` or `<prefix>/<issue>/<short_description>`
  - Prefixes: `feature/`, `fix/`, `docs/`, `ci/`, `refactor/`
  - Issue number is optional: `fix/querybuilder-improvements` or `fix/1234/querybuilder-improvements`
- Versioning follows [SemVer](https://semver.org/) (major.minor.patch).

## Commit style (not enforced)

Follow the **50/72 rule**:

- Subject line: max 50 characters, imperative mood ("Add feature", not "Added feature"), capitalized, no period
- Body: wrap at 72 characters, explain *what* and *why* (the code shows *how*)
- Merged PRs (via squash) append the PR number: `Fix bug in PwBaseWorkChain (#1234)`

```
Short summary in imperative mood (50 chars)

More detailed explanation wrapped at 72 characters. Focus on
why the change was made, not how.
```

## Emoji prefixes

Most commits use an emoji as a one-character semantic type prefix.
The emoji *is* the type indicator — write `🐛 PwBaseWorkChain: fix magnetization build`, not `🐛 Fix: PwBaseWorkChain: fix magnetization build`.

| Emoji | Meaning | Branch prefix |
|-------|---------|---------------|
| `✨` | New feature | `feature/` |
| `🐛` | Bug fix | `fix/` |
| `🚑` | Hotfix (urgent production fix) | `hotfix/` |
| `👌` | Improvement (no breaking changes) | `improve/` |
| `💥` | Breaking change | `breaking/` |
| `📚` | Documentation | `docs/` |
| `🔧` | Maintenance (typos, CI, etc.) | `chore/` |
| `🧪` | Tests or CI changes only | `test/` |
| `♻️` | Refactoring | `refactor/` |
| `⬆️` | Dependency upgrade | `deps/` |
| `📦` | Dependency bump (lower/upper bound change) | `deps/` |
| `🚀` | Release | `release/` |

The CHANGELOG uses these same emojis as section headers (e.g. `### 💥 Breaking changes`, `### 🐛 Bug fixes`), so commits flow directly into their CHANGELOG category.

## Pull request requirements

When submitting changes:

1. **Description**: Include a meaningful description explaining the change and link to related issues
2. **Tests**: Include test cases for new functionality or bug fixes
3. **Documentation**: Update docs if behaviour changes or new features are added
4. **Code quality**: Ensure `uv run pre-commit run --all-files` passes

Merging (maintainers): **Squash and merge** for single-issue PRs, **rebase and merge** for multi-commit PRs with individually significant commits.

## Git tooling

The `.git-blame-ignore-revs` file lists commits that should be ignored by `git blame` (e.g., bulk reformatting).
When landing a large-scale formatting-only commit, add its SHA to this file.
