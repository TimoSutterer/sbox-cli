# sbox-cli

Project-scoped Docker sandboxes for development and AI-agent workflows.

`sbox` creates persistent Docker containers for the current project, mounts the project into the container, and makes it easy to resume or list those sandboxes later.

```sh
sbox python:3.12
sbox
sbox ls
```

## Features

- Persistent Docker containers by default
- Current project mounted into the container
- Workdir inside the container matches the host project path
- Project-aware sandbox lookup using Docker labels
- Optional read-only project mounts
- Git worktree support for branch-isolated agent work
- Docker flag pass-through
- Installable Python package powered by `uv`

## Requirements

- [uv](https://docs.astral.sh/uv/)
- Docker
- Git, for worktree support

## Installation

Install the `sbox-cli` package as a uv tool to make the `sbox` command available:

```sh
uv tool install sbox-cli
```

## Usage

Create a sandbox:

```sh
sbox python:3.12
```

Create a sandbox and run a command:

```sh
sbox python:3.12 bash
sbox alpine sh
```

Resume or select an existing stopped sandbox for the current project:

```sh
sbox
```

List sandboxes for the current project:

```sh
sbox ls
```

## Options

### `--sbox-name NAME`

Use an exact Docker container name.

```sh
sbox --sbox-name auth-agent python:3.12 bash
```

The container will be named exactly:

```text
auth-agent
```

No prefix, suffix, project name, image name, or date is added.

### `--sbox-ro`

Mount the project read-only.

```sh
sbox --sbox-ro python:3.12 bash
```

Useful for inspection, review, or read-only agent runs.

### `--sbox-worktree BRANCH`

Create or reuse a managed Git worktree and run the sandbox there.

```sh
sbox --sbox-worktree feature-auth python:3.12 bash
```

Managed worktrees live at:

```text
<repo>/.sbox/worktrees/<branch>
```

The container mounts that worktree instead of the main checkout.

## Docker flag pass-through

Docker options can be passed before the image:

```sh
sbox -p 127.0.0.1:8000:8000 python:3.12 bash
sbox --network none alpine sh
sbox --rm ubuntu:24.04 bash
sbox -e FOO=bar python:3.12 bash
```

`sbox` does not add `--rm` by default. Containers are kept unless you pass `--rm` yourself.

## Naming

Generated container names use:

```text
sbox-<repo-or-dir>__<image>-<YYYYMMDD>
sbox-<repo-or-dir>.<branch>__<image>-<YYYYMMDD>  # with --sbox-worktree
```

Examples:

```text
sbox-shop-api__python-3.12-20260611
sbox-shop-api.feature-auth__python-3.12-20260611
sbox-scripts__alpine-20260611
```

If `--sbox-name` is provided, that exact name is used instead.

## Project detection

If run inside a Git repository, `sbox` uses the Git root as the project.

Otherwise, it uses the current working directory.

Sandboxes are associated with projects using Docker labels, so lookup does not rely only on container names.

## Worktrees

`sbox` supports both user-managed and managed Git worktrees.

User-managed worktree:

```sh
git worktree add ../shop-api.feature-auth -b feature-auth
cd ../shop-api.feature-auth
sbox python:3.12 bash
```

Managed worktree:

```sh
cd shop-api
sbox --sbox-worktree feature-auth python:3.12 bash
```

Managed worktrees are stored under:

```text
.sbox/worktrees/
```

`sbox` adds `.sbox/` to `.git/info/exclude`, not `.gitignore`.

## Lifecycle

Create a sandbox:

```sh
sbox python:3.12 bash
```

Exit the container shell when done.

Later, resume it from the same project:

```sh
sbox
```

If the matching sandbox is stopped, `sbox` starts and attaches to it.

If the matching sandbox is already running, `sbox` prints a message and does nothing.

Remove containers manually with Docker:

```sh
docker ps -a --filter label=sbox=true
docker rm CONTAINER
```

Remove managed worktrees manually with Git:

```sh
git worktree remove .sbox/worktrees/<branch>
```

## Detach keys

`sbox` uses `--detach-keys=ctrl-@` instead of Docker's default (`Ctrl-p, Ctrl-q`), which interferes with normal terminal usage of `Ctrl-p` (previous history, readline backward-char, etc.) inside the container.

## Timezone

If `$TZ` is set, `sbox` passes it into the container:

```sh
export TZ=Asia/Tokyo
sbox python:3.12 bash
```

If `$TZ` is not set, no timezone variable is passed.

## Security notes

`sbox` adds:

```sh
--security-opt no-new-privileges
--init
```

The project directory is bind-mounted into the container. In normal mode, it is writable.

For read-only access:

```sh
sbox --sbox-ro IMAGE
```

Avoid passing dangerous Docker options unless you understand the consequences, especially:

```sh
-v /var/run/docker.sock:/var/run/docker.sock
--privileged
```

Docker containers are not a hard security boundary.

## Troubleshooting

### Docker is not available

Check Docker:

```sh
docker version
```

### `uv` is not found

Check `uv`:

```sh
uv --version
```

### Container already exists

The generated or custom name already exists.

Resume/select it:

```sh
sbox
```

Or remove it manually:

```sh
docker rm CONTAINER
```

### Sandbox is already running

`sbox` does not automatically enter running containers.

Use Docker directly if you intentionally want another shell:

```sh
docker exec -it CONTAINER sh
```

### Permission issues on Linux

Some images run as root and may create root-owned files in the mounted project.

You can pass Docker's user option:

```sh
sbox --user "$(id -u):$(id -g)" IMAGE
```

## Development

Run the CLI from a checkout:

```sh
uv run sbox ls
```

Format and auto-fix style issues:

```sh
npm run style:fix
```

Run tests and checks:

```sh
npm run test
npm run syntax:check
npm run package:check
npm run style:check
```

Preview the next semantic release without publishing:

```sh
npm run release:check
```

This requires the checkout to have an `origin` remote, matching the GitHub
Actions release environment.

## Release

Releases are automated from Conventional Commits on `main` and published as the
`sbox-cli` package on PyPI.

Python Semantic Release updates `pyproject.toml`,
`uv.lock`, and `CHANGELOG.md` automatically.

Recommended branch protection checks for `main`:

- `Lint Commits`
- `Static Checks`
- `Test Python 3.11`
- `Test Python 3.12`
- `Test Python 3.13`
- `Test Python 3.14`

## License

MIT
