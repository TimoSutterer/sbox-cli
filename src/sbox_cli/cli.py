import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

SBOX_LABEL = "sbox=true"


DOCKER_OPTIONS_WITH_VALUES = {
    "-a",
    "--attach",
    "--add-host",
    "--annotation",
    "--blkio-weight",
    "--blkio-weight-device",
    "--cap-add",
    "--cap-drop",
    "--cgroup-parent",
    "--cgroupns",
    "--cidfile",
    "--cpu-period",
    "--cpu-quota",
    "--cpu-rt-period",
    "--cpu-rt-runtime",
    "--cpu-shares",
    "-c",
    "--cpus",
    "--cpuset-cpus",
    "--cpuset-mems",
    "--device",
    "--device-cgroup-rule",
    "--device-read-bps",
    "--device-read-iops",
    "--device-write-bps",
    "--device-write-iops",
    "--dns",
    "--dns-option",
    "--dns-search",
    "--domainname",
    "--entrypoint",
    "-e",
    "--env",
    "--env-file",
    "--expose",
    "--gpus",
    "--group-add",
    "--health-cmd",
    "--health-interval",
    "--health-retries",
    "--health-start-interval",
    "--health-start-period",
    "--health-timeout",
    "-h",
    "--hostname",
    "--ip",
    "--ip6",
    "--ipc",
    "--isolation",
    "-l",
    "--label",
    "--label-file",
    "--link",
    "--link-local-ip",
    "--log-driver",
    "--log-opt",
    "--mac-address",
    "-m",
    "--memory",
    "--memory-reservation",
    "--memory-swap",
    "--memory-swappiness",
    "--mount",
    "--name",
    "--network",
    "--network-alias",
    "--oom-score-adj",
    "--pid",
    "--pids-limit",
    "--platform",
    "-p",
    "--publish",
    "--pull",
    "--restart",
    "--runtime",
    "--security-opt",
    "--shm-size",
    "--stop-signal",
    "--stop-timeout",
    "--storage-opt",
    "--sysctl",
    "--tmpfs",
    "-u",
    "--user",
    "--userns",
    "--ulimit",
    "-v",
    "--volume",
    "--volumes-from",
    "-w",
    "--workdir",
}

DOCKER_BOOLEAN_OPTIONS = {
    "--detach",
    "-d",
    "--init",
    "-i",
    "--interactive",
    "-t",
    "--tty",
    "--privileged",
    "--publish-all",
    "-P",
    "--read-only",
    "--rm",
    "--no-healthcheck",
    "--oom-kill-disable",
    "--sig-proxy",
}


def run(args, *, capture=False, check=True, cwd=None):
    if capture:
        return subprocess.run(
            args,
            cwd=cwd,
            text=True,
            capture_output=True,
            check=check,
        )
    return subprocess.run(args, cwd=cwd, check=check)


def die(message, code=1):
    print(f"sbox: {message}", file=sys.stderr)
    raise SystemExit(code)


def docker_available():
    try:
        run(["docker", "version"], capture=True, check=True)
        return True
    except Exception:
        return False


def git(args, cwd=None, check=True):
    return run(["git", *args], capture=True, check=check, cwd=cwd)


def inside_git_repo(path):
    try:
        result = git(["rev-parse", "--is-inside-work-tree"], cwd=path)
        return result.stdout.strip() == "true"
    except subprocess.CalledProcessError:
        return False


def git_root(path):
    result = git(["rev-parse", "--show-toplevel"], cwd=path)
    return Path(result.stdout.strip()).resolve()


def sanitize_component(value, fallback):
    value = value.lower()
    value = re.sub(r"[^a-z0-9_.-]+", "-", value)
    value = value.strip(".-_")
    return value or fallback


def sanitize_image(value):
    value = value.lower()
    value = value.replace("/", "-")
    value = value.replace(":", "-")
    value = value.replace("@", "-")
    value = re.sub(r"[^a-z0-9_.-]+", "-", value)
    value = value.strip(".-_")
    return value or "image"


def validate_container_name(name):
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$", name):
        die(
            "invalid container name. Docker names should use only letters, "
            "digits, underscore, dot, and dash, and must start with a letter or digit.",
        )


def sanitize_hostname(name):
    """Convert a container name to a valid hostname (max 64 chars, alphanum and hyphens)."""
    h = re.sub(r"[^a-zA-Z0-9-]+", "-", name)
    h = h.strip("-")
    h = h[:64].rstrip("-")
    return h or "sbox"


def today():
    return datetime.datetime.now().strftime("%Y%m%d")


def project_hash(path):
    return hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:12]


def docker_container_exists(name):
    result = run(
        ["docker", "container", "inspect", name],
        capture=True,
        check=False,
    )
    return result.returncode == 0


def docker_ps(filters, all_containers=True):
    args = ["docker", "ps"]
    if all_containers:
        args.append("-a")

    for f in filters:
        args.extend(["--filter", f])

    args.extend(
        [
            "--format",
            "{{json .}}",
        ],
    )

    result = run(args, capture=True, check=True)
    rows = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def inspect_container(name):
    result = run(
        ["docker", "container", "inspect", name],
        capture=True,
        check=True,
    )
    data = json.loads(result.stdout)
    if not data:
        return None
    return data[0]


def get_labels(name):
    data = inspect_container(name)
    return data.get("Config", {}).get("Labels", {}) or {}


def current_project_context():
    cwd = Path.cwd().resolve()

    if inside_git_repo(cwd):
        root = git_root(cwd)
        repo_name = sanitize_component(root.name, "repo")
        return {
            "is_git": True,
            "project_root": root,
            "workdir": root,
            "repo_or_dir": repo_name,
            "branch": None,
            "project_key": project_hash(root),
        }

    dir_name = sanitize_component(cwd.name, "dir")
    return {
        "is_git": False,
        "project_root": cwd,
        "workdir": cwd,
        "repo_or_dir": dir_name,
        "branch": None,
        "project_key": project_hash(cwd),
    }


def ensure_git_exclude(root):
    info_dir = root / ".git" / "info"
    exclude_file = info_dir / "exclude"

    if not info_dir.exists():
        return

    existing = ""
    if exclude_file.exists():
        existing = exclude_file.read_text()

    if ".sbox/" not in existing:
        with exclude_file.open("a") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(".sbox/\n")


def branch_exists(root, branch):
    result = git(
        ["show-ref", "--verify", f"refs/heads/{branch}"],
        cwd=root,
        check=False,
    )
    return result.returncode == 0


def worktree_list(root):
    result = git(["worktree", "list", "--porcelain"], cwd=root)
    entries = []
    current = {}

    for line in result.stdout.splitlines():
        if not line:
            if current:
                entries.append(current)
                current = {}
            continue

        if line.startswith("worktree "):
            current["path"] = line.removeprefix("worktree ").strip()
        elif line.startswith("branch "):
            current["branch"] = line.removeprefix("branch refs/heads/").strip()

    if current:
        entries.append(current)

    return entries


def branch_checked_out_elsewhere(root, branch, desired_path):
    desired_path = str(Path(desired_path).resolve())

    for entry in worktree_list(root):
        if entry.get("branch") == branch:
            existing_path = str(Path(entry.get("path", "")).resolve())
            if existing_path != desired_path:
                return existing_path

    return None


def prepare_managed_worktree(context, branch):
    if not context["is_git"]:
        die("--sbox-worktree requires a git repository")

    root = context["project_root"]
    branch_raw = branch
    branch_component = sanitize_component(branch_raw, "branch")

    worktree_path = root / ".sbox" / "worktrees" / branch_component
    ensure_git_exclude(root)

    checked_out_at = branch_checked_out_elsewhere(root, branch_raw, worktree_path)
    if checked_out_at:
        die(f"branch '{branch_raw}' is already checked out at {checked_out_at}")

    if worktree_path.exists():
        if not (worktree_path / ".git").exists():
            die(
                f"worktree path already exists but is not a git worktree: {worktree_path}",
            )
    else:
        worktree_path.parent.mkdir(parents=True, exist_ok=True)

        if branch_exists(root, branch_raw):
            run(["git", "worktree", "add", str(worktree_path), branch_raw], cwd=root)
        else:
            run(
                ["git", "worktree", "add", "-b", branch_raw, str(worktree_path)],
                cwd=root,
            )

    return {
        **context,
        "workdir": worktree_path.resolve(),
        "branch": branch_component,
    }


def generated_name(context, image):
    repo_or_dir = context["repo_or_dir"]
    image_component = sanitize_image(image)
    date = today()

    if context.get("branch"):
        left = f"{repo_or_dir}.{context['branch']}"
    else:
        left = repo_or_dir

    return f"sbox-{left}__{image_component}-{date}"


def quote_cmd(args):
    return " ".join(shlex.quote(str(a)) for a in args)


def parsed_args(
    mode,
    *,
    docker_opts=None,
    sbox_name=None,
    sbox_ro=False,
    sbox_worktree=None,
    image=None,
    cmd=None,
):
    return {
        "mode": mode,
        "docker_opts": docker_opts or [],
        "sbox_name": sbox_name,
        "sbox_ro": sbox_ro,
        "sbox_worktree": sbox_worktree,
        "image": image,
        "cmd": cmd or [],
    }


def require_arg_value(argv, i, option):
    if i >= len(argv):
        die(f"missing value for {option}", code=2)
    return argv[i]


def parse_ls_args(argv):
    if len(argv) > 1:
        die("usage: sbox ls", code=2)
    return parsed_args("ls")


def consume_sbox_option(argv, i, state):
    arg = argv[i]

    if arg == "--sbox-name":
        state["sbox_name"] = require_arg_value(argv, i + 1, arg)
        return i + 2, True

    if arg.startswith("--sbox-name="):
        state["sbox_name"] = arg.split("=", 1)[1]
        return i + 1, True

    if arg == "--sbox-ro":
        state["sbox_ro"] = True
        return i + 1, True

    if arg == "--sbox-worktree":
        state["sbox_worktree"] = require_arg_value(argv, i + 1, arg)
        return i + 2, True

    if arg.startswith("--sbox-worktree="):
        state["sbox_worktree"] = arg.split("=", 1)[1]
        return i + 1, True

    if arg.startswith("--sbox-"):
        die(f"unknown sbox option: {arg}", code=2)

    return i, False


def consume_docker_option(argv, i, docker_opts):
    arg = argv[i]
    if not arg.startswith("-"):
        return i, False

    docker_opts.append(arg)

    if "=" in arg or arg in DOCKER_BOOLEAN_OPTIONS:
        return i + 1, True

    if arg in DOCKER_OPTIONS_WITH_VALUES:
        value = require_arg_value(argv, i + 1, f"Docker option {arg}")
        docker_opts.append(value)
        return i + 2, True

    # Conservative fallback: unknown Docker-looking flags are treated as booleans.
    # If the user needs to pass an unknown flag with a value, use --flag=value.
    return i + 1, True


def image_after_separator(argv, i):
    image_i = i + 1
    if image_i >= len(argv):
        die("missing image after --", code=2)
    return argv[image_i], argv[image_i + 1 :]


def parse_create_args(argv):
    state = {
        "docker_opts": [],
        "sbox_name": None,
        "sbox_ro": False,
        "sbox_worktree": None,
    }
    i = 0
    image = None
    cmd = []

    while i < len(argv):
        arg = argv[i]

        if arg == "--":
            image, cmd = image_after_separator(argv, i)
            break

        i, handled = consume_sbox_option(argv, i, state)
        if handled:
            continue

        i, handled = consume_docker_option(argv, i, state["docker_opts"])
        if handled:
            continue

        image = arg
        cmd = argv[i + 1 :]
        break

    if not image:
        die("missing image", code=2)

    return parsed_args("create", image=image, cmd=cmd, **state)


def parse_args(argv):
    if not argv:
        return parsed_args("enter")

    if argv[0] == "ls":
        return parse_ls_args(argv)

    return parse_create_args(argv)


def sbox_filters_for_context(context):
    return [
        "label=sbox=true",
        f"label=sbox.project_key={context['project_key']}",
    ]


def find_sboxes(context):
    rows = docker_ps(sbox_filters_for_context(context), all_containers=True)

    sandboxes = []
    for row in rows:
        name = row.get("Names", "")
        labels = get_labels(name)
        sandboxes.append(
            {
                "name": name,
                "status": row.get("Status", ""),
                "state": row.get("State", ""),
                "image": labels.get("sbox.image", row.get("Image", "")),
                "branch": labels.get("sbox.branch", ""),
                "created_date": labels.get("sbox.created_date", ""),
                "workdir": labels.get("sbox.workdir", ""),
            },
        )

    return sorted(sandboxes, key=lambda s: s["name"])


def is_running(sandbox):
    return sandbox.get("state") == "running"


def print_sandbox_table(sandboxes):
    if not sandboxes:
        print("sbox: no sandboxes found for this project")
        return

    headers = ["STATUS", "NAME", "IMAGE", "BRANCH"]
    rows = []

    for s in sandboxes:
        status = "running" if is_running(s) else "stopped"
        branch = s.get("branch") or "-"
        rows.append([status, s["name"], s.get("image", ""), branch])

    widths = [
        max(len(headers[i]), *(len(row[i]) for row in rows))
        for i in range(len(headers))
    ]

    print(
        f"{headers[0]:<{widths[0]}}  "
        f"{headers[1]:<{widths[1]}}  "
        f"{headers[2]:<{widths[2]}}  "
        f"{headers[3]:<{widths[3]}}",
    )

    for row in rows:
        print(
            f"{row[0]:<{widths[0]}}  "
            f"{row[1]:<{widths[1]}}  "
            f"{row[2]:<{widths[2]}}  "
            f"{row[3]:<{widths[3]}}",
        )


def select_sandbox(sandboxes):
    if not sandboxes:
        print("sbox: no sandboxes found for this project")
        print("sbox: create one with: sbox <image>")
        return None

    if len(sandboxes) == 1:
        return sandboxes[0]

    print("sbox: select sandbox")
    for idx, sandbox in enumerate(sandboxes, start=1):
        indicator = "●" if is_running(sandbox) else "○"
        status = "running" if is_running(sandbox) else "stopped"
        branch = sandbox.get("branch") or "-"
        image = sandbox.get("image") or "-"
        print(
            f"{idx}) {indicator} {status:<7} {sandbox['name']}  image={image} branch={branch}",
        )

    while True:
        choice = input("> ").strip()

        if choice == "":
            return None

        try:
            n = int(choice)
        except ValueError:
            print("sbox: enter a number, or press Enter to cancel")
            continue

        if 1 <= n <= len(sandboxes):
            return sandboxes[n - 1]

        print("sbox: invalid selection")


def enter_existing(context):
    sandboxes = find_sboxes(context)
    sandbox = select_sandbox(sandboxes)

    if not sandbox:
        return

    if is_running(sandbox):
        print(f"sbox: sandbox is already running: {sandbox['name']}")
        return

    run(["docker", "start", "-ai", "--detach-keys=ctrl-@", sandbox["name"]])


def ls_sboxes(context):
    print_sandbox_table(find_sboxes(context))


def matching_older_sboxes(context, image, candidate_name):
    image_component = sanitize_image(image)
    repo_or_dir = context["repo_or_dir"]

    if context.get("branch"):
        prefix = f"sbox-{repo_or_dir}.{context['branch']}__{image_component}-"
    else:
        prefix = f"sbox-{repo_or_dir}__{image_component}-"

    matches = []
    for sandbox in find_sboxes(context):
        name = sandbox["name"]
        if name == candidate_name:
            continue
        if name.startswith(prefix):
            matches.append(sandbox)

    return matches


def confirm_create_with_older(matches):
    print("sbox: found existing sandbox for this project/image:")
    for s in matches:
        status = "running" if is_running(s) else "stopped"
        print(f"  {s['name']}  {status}")

    answer = input("create a new sandbox anyway? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def create_sandbox(parsed):
    context = current_project_context()

    if parsed["sbox_worktree"]:
        context = prepare_managed_worktree(context, parsed["sbox_worktree"])

    image = parsed["image"]

    if parsed["sbox_name"]:
        name = parsed["sbox_name"]
    else:
        name = generated_name(context, image)

    validate_container_name(name)

    if docker_container_exists(name):
        die(f"container already exists: {name}")

    older = matching_older_sboxes(context, image, name)
    if older and not parsed["sbox_name"]:
        if not confirm_create_with_older(older):
            return

    mount = f"type=bind,source={context['workdir']},target={context['workdir']}"
    if parsed["sbox_ro"]:
        mount += ",readonly"

    labels = {
        "sbox": "true",
        "sbox.project_key": context["project_key"],
        "sbox.project_root": str(context["project_root"]),
        "sbox.workdir": str(context["workdir"]),
        "sbox.repo_or_dir": context["repo_or_dir"],
        "sbox.image": image,
        "sbox.created_date": today(),
    }
    if context.get("branch"):
        labels["sbox.branch"] = context["branch"]

    cmd = [
        "docker",
        "run",
        "-it",
        "--detach-keys=ctrl-@",
        "--name",
        name,
        "--hostname",
        sanitize_hostname(name),
        "--init",
        "--security-opt",
        "no-new-privileges",
    ]

    for key, value in labels.items():
        cmd.extend(["--label", f"{key}={value}"])

    if os.environ.get("TZ"):
        cmd.extend(["-e", f"TZ={os.environ['TZ']}"])

    cmd.extend(
        [
            "--mount",
            mount,
            "--workdir",
            str(context["workdir"]),
        ],
    )

    cmd.extend(parsed["docker_opts"])
    cmd.append(image)
    cmd.extend(parsed["cmd"])

    run(cmd)


def main():
    if not docker_available():
        die("docker is not available or not running")

    parsed = parse_args(sys.argv[1:])
    context = current_project_context()

    if parsed["mode"] == "enter":
        enter_existing(context)
    elif parsed["mode"] == "ls":
        ls_sboxes(context)
    elif parsed["mode"] == "create":
        create_sandbox(parsed)
    else:
        die(f"unknown mode: {parsed['mode']}", code=2)


if __name__ == "__main__":
    main()
