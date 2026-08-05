# Contributing

Contributions are welcome, and they are greatly appreciated!
Every little bit helps, and credit will always be given.

## Environment setup

Nothing easier!

Fork and clone the repository, then:

```bash
cd pyfsd
pdm install -d
```

> NOTE:
> If it fails for some reason,
> you'll need to install
> [PDM](https://github.com/pdm-project/pdm)
> manually.
>
> You can install it with:
>
> ```bash
> python3 -m pip install --user pipx
> pipx install pdm
> ```
>
> Now you can try running `pdm install -d` again.

You now have the dependencies installed.

You can run the application with `python -m pyfsd [ARGS...]`.

## Development

As usual:

1. create a new branch: `git switch -c feature-or-bugfix-name`
1. edit the code and/or the documentation

**Before committing:**

1. run `ruff --format .` to auto-format the code
1. run `mypy . && ruff .` to check everything (fix any warning)
1. run `python -m unittest` to run the tests (fix any issue)
1. if you updated the documentation or the project dependencies:
    1. run `mkdocs serve`
    1. go to http://localhost:8000 and check that everything looks good
1. follow our [commit message convention](#commit-message-convention)

If you are unsure about how to fix or ignore a warning,
just let the continuous integration fail,
and we will help you during review.

Don't bother updating the changelog, we will take care of this.

## Commit message convention

Commit messages must follow our convention based on the
[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/)

The commit message should be structured as follows:

---

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```
---

<br />
The commit contains the following structural elements, to communicate intent to the
consumers of your library:

1. **fix:** a commit of the _type_ `fix` patches a bug in your codebase (this correlates with [`PATCH`](http://semver.org/#summary) in Semantic Versioning).
1. **feat:** a commit of the _type_ `feat` introduces a new feature to the codebase (this correlates with [`MINOR`](http://semver.org/#summary) in Semantic Versioning).
1. **BREAKING CHANGE:** a commit that has a footer `BREAKING CHANGE:`, or appends a `!` after the type/scope, introduces a breaking API change (correlating with [`MAJOR`](http://semver.org/#summary) in Semantic Versioning).
A BREAKING CHANGE can be part of commits of any _type_.
1. _types_ other than `fix:` and `feat:` are allowed, for example [@commitlint/config-conventional](https://github.com/conventional-changelog/commitlint/tree/master/%40commitlint/config-conventional) (based on the [Angular convention](https://github.com/angular/angular/blob/22b96b9/CONTRIBUTING.md#-commit-message-guidelines)) recommends `build:`, `chore:`,
  `ci:`, `docs:`, `style:`, `refactor:`, `perf:`, `test:`, and others.
1. _footers_ other than `BREAKING CHANGE: <description>` may be provided and follow a convention similar to
  [git trailer format](https://git-scm.com/docs/git-interpret-trailers).

Additional types are not mandated by the Conventional Commits specification, and have no implicit effect in Semantic Versioning (unless they include a BREAKING CHANGE).
<br /><br />
A scope may be provided to a commit's type, to provide additional contextual information and is contained within parenthesis, e.g., `feat(parser): add ability to parse arrays`.

> This section is adapted from the Conventional Commits specification,
> Copyright (c) 2018 Conventional Changelog. Licensed under the 
> [MIT License](https://github.com/conventional-commits/conventionalcommits.org/blob/master/LICENSE)


## Pull requests guidelines

Link to any related issue in the Pull Request message.

During the review, we recommend using fixups:

```bash
# SHA is the SHA of the commit you want to fix
git commit --fixup=SHA
```

Once all the changes are approved, you can squash your commits:

```bash
git rebase -i --autosquash early-dev
```

And force-push:

```bash
git push -f
```

If this seems all too complicated, you can push or force-push each new commit,
and we will squash them ourselves if needed, before merging.
