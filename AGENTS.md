# Project Working Rules

## Change Scope

- Extend the existing WordPress knowledge-base stack incrementally. Do not rebuild or move the project unless the user explicitly requests it.
- Inspect the real repository state before editing, and preserve unrelated user changes.
- Never commit `.env` files, credentials, tokens, private backup workflows, personal data, or environment-specific secrets to the public repository.

## Required Verification

- Run the narrowest relevant checks for every change, such as Python tests, PHP syntax checks, CSS diff checks, and live browser verification when user-facing behavior changes.
- Review the exact files being committed. Do not include unrelated or unreviewed files merely to make the worktree clean.

## Required Publication Workflow

- After every accepted public-safe code, documentation, theme, or script update, commit the relevant files and publish the completed update before considering the task finished.
- This maintainer workspace configures `origin` with GitHub as the fetch URL and both GitHub and Gitee as push URLs. Use `git push origin main` so the same commit is sent to both repositories.
- Verify that both remote `main` branches point to the new local commit. A successful push to only one repository is incomplete.
- Skip committing or pushing only when the user explicitly requests no commit, no push, or a pause before publication.
- Keep private Google Drive backup workflows outside this public repository.
