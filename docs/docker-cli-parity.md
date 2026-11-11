# Таблица соответствия CLI: docker ⇄ udocker

Сгенерировано `utils/docker_cli_probe.py` по живому `--help` реальных бинарей: Docker version 29.9.3, build 5457199 · 5.7.0.

Обозначения: ✅ работает · 🔶 принимается, эффект не проверен · 🔷 принимается без эффекта (флаг отброшен шимом) · ❌ нет · ⛔ явный root-only отказ · 💥 падение · ➖ вне scope.

Флаги и команды проверяются запуском udocker, а не перечислены по памяти: docker-сторона снимается из `--help` реальных бинарей (`utils/docker_cli_census.py`), udocker-сторона — пробами (`utils/docker_cli_probe.py`).

Вне гарантии (нужен демон/root/swarm): `swarm`, `stack`, `service`, `node`, `secret`, `config`, `context`, `plugin`, `checkpoint`, `builder`, `manifest create/push/rm` — такие страницы помечены ➖, а неприменимые флаги применимых команд отвечают явной ошибкой (⛔), а не молча игнорируются.

Колонка **проверка** — это вывод, по которому проба поставила отметку; пустая колонка означает успешный запуск.

## Сводка

| состояние | флагов |
|---|---|
| ✅ ok | 60 |
| 🔶 accepted | 295 |
| 🔷 ignored | 156 |
| ⛔ root-only | 230 |
| ➖ excluded | 340 |
| всего | 1081 |

Команд-страниц с рабочим udocker: **70**; отсутствуют: **0**.

## По командам

### `docker build` → `udocker build` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--add-host` | list | да | 🔷 ignored | no | Error: build context directory not found: /nonexistent-context |
| `--build-arg` | list | да | 🔶 accepted | yes | Error: build context directory not found: /nonexistent-context |
| `--cache-from` | strings | да | 🔷 ignored | no | Error: build context directory not found: /nonexistent-context |
| `--cgroup-parent` | string | да | 🔷 ignored | no | Error: build context directory not found: /nonexistent-context |
| `--compress` | — | да | 🔷 ignored | no | Error: build context directory not found: /nonexistent-context |
| `--cpu-period` | int | да | ⛔ root-only | no | Error: --cpu-period: CPU limits need cgroup delegation |
| `--cpu-quota` | int | да | ⛔ root-only | no | Error: --cpu-quota: CPU limits need cgroup delegation |
| `-c, --cpu-shares` | int | да | ⛔ root-only | no | Error: --cpu-shares: CPU limits need cgroup delegation |
| `--cpuset-cpus` | string | да | 🔷 ignored | no | Error: build context directory not found: /nonexistent-context |
| `--cpuset-mems` | string | да | ⛔ root-only | no | Error: --cpuset-mems: CPU limits need cgroup delegation |
| `-f, --file` | string | да | 🔶 accepted | yes | Error: build context directory not found: /nonexistent-context |
| `--force-rm` | — | да | 🔷 ignored | no | Error: build context directory not found: /nonexistent-context |
| `--iidfile` | string | да | 🔷 ignored | no | Error: build context directory not found: /nonexistent-context |
| `--isolation` | string | да | 🔷 ignored | no | Error: build context directory not found: /nonexistent-context |
| `--label` | list | да | 🔶 accepted | no | Error: build context directory not found: /nonexistent-context |
| `-m, --memory` | bytes | да | ⛔ root-only | no | Error: --memory: resource limits need cgroup delegation |
| `--memory-swap` | bytes | да | ⛔ root-only | no | Error: --memory-swap: resource limits need cgroup delegation |
| `--network` | string | да | 🔷 ignored | no | Error: build context directory not found: /nonexistent-context |
| `--no-cache` | — | да | 🔶 accepted | no | Error: build context directory not found: /nonexistent-context |
| `--platform` | string | да | 🔶 accepted | yes | Error: build context directory not found: /nonexistent-context |
| `--pull` | — | да | 🔶 accepted | no | Error: build context directory not found: /nonexistent-context |
| `-q, --quiet` | — | да | 🔷 ignored | no | Error: build context directory not found: /nonexistent-context |
| `--rm` | — | да | 🔷 ignored | no | Error: build context directory not found: /nonexistent-context |
| `--security-opt` | strings | да | 🔷 ignored | no | Error: build context directory not found: /nonexistent-context |
| `--shm-size` | bytes | да | 🔷 ignored | no | Error: build context directory not found: /nonexistent-context |
| `--squash` | — | да | 🔷 ignored | no | Error: build context directory not found: /nonexistent-context |
| `-t, --tag` | list | да | 🔶 accepted | yes | Error: build context directory not found: /nonexistent-context |
| `--target` | string | да | 🔶 accepted | no | Error: build context directory not found: /nonexistent-context |
| `--ulimit` | ulimit | да | 🔷 ignored | no | Error: build context directory not found: /nonexistent-context |

### `docker commit` → `udocker commit` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-a, --author` | string | да | 🔶 accepted | yes | Error: container not found: nosuchct |
| `-c, --change` | list | да | 🔶 accepted | no | Error: container not found: nosuchct |
| `-m, --message` | string | да | 🔶 accepted | yes | Error: container not found: nosuchct |
| `--no-pause` | — | да | 🔶 accepted | no | Error: container not found: nosuchct |

### `docker cp` → `udocker cp` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-a, --archive` | — | да | 🔶 accepted | no | Error: one of source or destination must be a container |
| `-L, --follow-link` | — | да | 🔶 accepted | no | Error: one of source or destination must be a container |
| `-q, --quiet` | — | да | 🔶 accepted | no | Error: one of source or destination must be a container |

### `docker create` → `udocker create` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--add-host` | list | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `--annotation` | map | да | 🔷 ignored | no | Error: create container: imagerepo is invalid |
| `-a, --attach` | list | да | 🔷 ignored | no | Error: create container: imagerepo is invalid |
| `--blkio-weight` | uint16 | да | ⛔ root-only | no | Error: --blkio-weight: resource limits need cgroup delegation |
| `--blkio-weight-device` | list | да | ⛔ root-only | no | Error: --blkio-weight-device: resource limits need cgroup delegation |
| `--cap-add` | list | да | ⛔ root-only | no | Error: --cap-add: privileges and capabilities need root |
| `--cap-drop` | list | да | ⛔ root-only | no | Error: --cap-drop: privileges and capabilities need root |
| `--cgroup-parent` | string | да | 🔷 ignored | no | Error: create container: imagerepo is invalid |
| `--cgroupns` | string | да | 🔷 ignored | no | Error: create container: imagerepo is invalid |
| `--cidfile` | string | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `--cpu-count` | int | да | ⛔ root-only | no | Error: --cpu-count: CPU limits need cgroup delegation |
| `--cpu-percent` | int | да | ⛔ root-only | no | Error: --cpu-percent: CPU limits need cgroup delegation |
| `--cpu-period` | int | да | ⛔ root-only | no | Error: --cpu-period: CPU limits need cgroup delegation |
| `--cpu-quota` | int | да | ⛔ root-only | no | Error: --cpu-quota: CPU limits need cgroup delegation |
| `--cpu-rt-period` | int | да | ⛔ root-only | no | Error: --cpu-rt-period: CPU limits need cgroup delegation |
| `--cpu-rt-runtime` | int | да | ⛔ root-only | no | Error: --cpu-rt-runtime: CPU limits need cgroup delegation |
| `-c, --cpu-shares` | int | да | ⛔ root-only | no | Error: --cpu-shares: CPU limits need cgroup delegation |
| `--cpus` | decimal | да | ⛔ root-only | no | Error: --cpus: CPU limits need cgroup delegation |
| `--cpuset-cpus` | string | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `--cpuset-mems` | string | да | ⛔ root-only | no | Error: --cpuset-mems: CPU limits need cgroup delegation |
| `--device` | list | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `--device-cgroup-rule` | list | да | 🔷 ignored | no | Error: create container: imagerepo is invalid |
| `--device-read-bps` | list | да | ⛔ root-only | no | Error: --device-read-bps: resource limits need cgroup delegation |
| `--device-read-iops` | list | да | ⛔ root-only | no | Error: --device-read-iops: resource limits need cgroup delegation |
| `--device-write-bps` | list | да | ⛔ root-only | no | Error: --device-write-bps: resource limits need cgroup delegation |
| `--device-write-iops` | list | да | ⛔ root-only | no | Error: --device-write-iops: resource limits need cgroup delegation |
| `--dns` | list | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `--dns-option` | list | да | 🔷 ignored | no | Error: create container: imagerepo is invalid |
| `--dns-search` | list | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `--domainname` | string | да | 🔷 ignored | no | Error: create container: imagerepo is invalid |
| `--entrypoint` | string | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `-e, --env` | list | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `--env-file` | list | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `--expose` | list | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `--group-add` | list | да | ⛔ root-only | no | Error: --group-add: privileges and capabilities need root |
| `--health-cmd` | string | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `--health-interval` | duration | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `--health-retries` | int | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `--health-start-interval` | duration | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `--health-start-period` | duration | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `--health-timeout` | duration | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `--help` | — | да | ✅ ok | no | create: extract image layers and create a container |
| `-h, --hostname` | string | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `--init` | — | да | 🔷 ignored | no | Error: create container: imagerepo is invalid |
| `-i, --interactive` | — | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `--io-maxbandwidth` | bytes | да | ⛔ root-only | no | Error: --io-maxbandwidth: resource limits need cgroup delegation |
| `--io-maxiops` | uint | да | ⛔ root-only | no | Error: --io-maxiops: resource limits need cgroup delegation |
| `--ip` | ip | да | ⛔ root-only | no | Error: --ip: container networking is host-only |
| `--ip6` | ip | да | ⛔ root-only | no | Error: --ip6: container networking is host-only |
| `--ipc` | string | да | 🔷 ignored | no | Error: create container: imagerepo is invalid |
| `--isolation` | string | да | 🔷 ignored | no | Error: create container: imagerepo is invalid |
| `-l, --label` | list | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `--label-file` | list | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `--link` | list | да | ⛔ root-only | no | Error: --link: container networking is host-only |
| `--link-local-ip` | list | да | ⛔ root-only | no | Error: --link-local-ip: container networking is host-only |
| `--log-driver` | string | да | 🔷 ignored | no | Error: create container: imagerepo is invalid |
| `--log-opt` | list | да | 🔷 ignored | no | Error: create container: imagerepo is invalid |
| `--mac-address` | string | да | ⛔ root-only | no | Error: --mac-address: container networking is host-only |
| `-m, --memory` | bytes | да | ⛔ root-only | no | Error: --memory: resource limits need cgroup delegation |
| `--memory-reservation` | bytes | да | ⛔ root-only | no | Error: --memory-reservation: resource limits need cgroup delegation |
| `--memory-swap` | bytes | да | ⛔ root-only | no | Error: --memory-swap: resource limits need cgroup delegation |
| `--memory-swappiness` | int | да | ⛔ root-only | no | Error: --memory-swappiness: resource limits need cgroup delegation |
| `--mount` | mount | да | 🔶 accepted | no | Error: invalid --mount (no target): /tmp |
| `--name` | string | да | 🔶 accepted | yes | Error: create container: imagerepo is invalid |
| `--network` | network | да | 🔷 ignored | no | Error: create container: imagerepo is invalid |
| `--network-alias` | list | да | ⛔ root-only | no | Error: --network-alias: container networking is host-only |
| `--no-healthcheck` | — | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `--oom-kill-disable` | — | да | ⛔ root-only | no | Error: --oom-kill-disable: resource limits need cgroup delegation |
| `--oom-score-adj` | int | да | ⛔ root-only | no | Error: --oom-score-adj: resource limits need cgroup delegation |
| `--pid` | string | да | 🔷 ignored | no | Error: create container: imagerepo is invalid |
| `--pids-limit` | int | да | ⛔ root-only | no | Error: --pids-limit: resource limits need cgroup delegation |
| `--platform` | string | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `--privileged` | — | да | ⛔ root-only | no | Error: --privileged: privileges and capabilities need root |
| `-p, --publish` | list | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `-P, --publish-all` | — | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `--pull` | string | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `-q, --quiet` | — | да | 🔷 ignored | no | Error: create container: imagerepo is invalid |
| `--read-only` | — | да | ⛔ root-only | no | Error: --read-only: a read-only root filesystem needs a mount namespace |
| `--restart` | string | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `--rm` | — | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `--runtime` | string | да | ⛔ root-only | no | Error: --runtime: the execution mode is selected with --execmode |
| `--security-opt` | list | да | 🔷 ignored | no | Error: create container: imagerepo is invalid |
| `--shm-size` | bytes | да | 🔷 ignored | no | Error: create container: imagerepo is invalid |
| `--stop-signal` | string | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `--stop-timeout` | int | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `--storage-opt` | list | да | 🔷 ignored | no | Error: create container: imagerepo is invalid |
| `--sysctl` | map | да | ⛔ root-only | no | Error: --sysctl: privileges and capabilities need root |
| `--tmpfs` | list | да | ⛔ root-only | no | Error: --tmpfs: tmpfs mounts need a mount namespace (use -v /some/dir:/path instead) |
| `-t, --tty` | — | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `--ulimit` | ulimit | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `--umask` | umask | да | 🔷 ignored | no | Error: create container: imagerepo is invalid |
| `--use-api-socket` | — | да | 🔷 ignored | no | Error: create container: imagerepo is invalid |
| `-u, --user` | string | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `--userns` | string | да | 🔷 ignored | no | Error: create container: imagerepo is invalid |
| `--uts` | string | да | 🔷 ignored | no | Error: create container: imagerepo is invalid |
| `-v, --volume` | list | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `--volume-driver` | string | да | 🔷 ignored | no | Error: create container: imagerepo is invalid |
| `--volumes-from` | list | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |
| `-w, --workdir` | string | да | 🔶 accepted | no | Error: create container: imagerepo is invalid |

### `docker events` → `udocker events` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --filter` | filter | да | ✅ ok | yes |  |
| `--format` | string | да | ✅ ok | yes |  |
| `--since` | string | да | ✅ ok | yes |  |
| `--until` | string | да | ✅ ok | yes |  |

### `docker exec` → `udocker exec` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-d, --detach` | — | да | 🔶 accepted | no | Error: container not found: nosuchct |
| `--detach-keys` | string | да | 🔷 ignored | no | Error: container not found: nosuchct |
| `-e, --env` | list | да | 🔶 accepted | yes | Error: container not found: nosuchct |
| `--env-file` | list | да | 🔶 accepted | no | Error: container not found: nosuchct |
| `-i, --interactive` | — | да | 🔶 accepted | no | Error: container not found: nosuchct |
| `--privileged` | — | да | 🔷 ignored | no | Error: container not found: nosuchct |
| `-t, --tty` | — | да | 🔶 accepted | no | Error: container not found: nosuchct |
| `-u, --user` | string | да | 🔶 accepted | yes | Error: container not found: nosuchct |
| `-w, --workdir` | string | да | 🔶 accepted | yes | Error: container not found: nosuchct |

### `docker export` → `udocker export` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-o, --output` | string | да | 🔶 accepted | no | Error: invalid container id |

### `docker history` → `udocker history` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--format` | string | да | 🔶 accepted | no | Error: image not found: nosuchimg |
| `-H, --human` | — | да | 🔶 accepted | no | Error: image not found: nosuchimg |
| `--no-trunc` | — | да | 🔶 accepted | yes | Error: image not found: nosuchimg |
| `--platform` | string | да | 🔶 accepted | no | Error: image not found: nosuchimg |
| `-q, --quiet` | — | да | 🔶 accepted | no | Error: image not found: nosuchimg |

### `docker images` → `udocker images` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-a, --all` | — | да | ✅ ok | yes | REPOSITORY                     TAG                  IMAGE ID     CREATED              SIZE |
| `--digests` | — | да | 🔷 ignored | no | REPOSITORY                     TAG                  IMAGE ID     CREATED              SIZE |
| `-f, --filter` | filter | да | ✅ ok | no | REPOSITORY                     TAG                  IMAGE ID     CREATED              SIZE |
| `--format` | string | да | ✅ ok | yes |  |
| `--no-trunc` | — | да | ✅ ok | yes | REPOSITORY                     TAG                  IMAGE ID     CREATED              SIZE |
| `-q, --quiet` | — | да | ✅ ok | yes |  |
| `--tree` | — | да | 🔷 ignored | no | REPOSITORY                     TAG                  IMAGE ID     CREATED              SIZE |

### `docker import` → `udocker import` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-c, --change` | list | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `-m, --message` | string | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--platform` | string | да | 🔶 accepted | yes | Error: must specify image:tag or repository/image:tag |

### `docker info` → `udocker info` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --format` | string | да | ✅ ok | yes | { |

### `docker inspect` → `udocker inspect` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --format` | string | да | 🔶 accepted | yes | Error: no such object: nosuchobj |
| `-s, --size` | — | да | 🔶 accepted | yes | Error: no such object: nosuchobj |
| `--type` | string | да | 🔶 accepted | yes | Error: no such object: nosuchobj |

### `docker kill` → `udocker kill` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-s, --signal` | string | да | 🔶 accepted | yes | Error: container not found: nosuchct |

### `docker load` → `udocker load` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-i, --input` | string | да | 🔶 accepted | yes | Error: image file does not exist: x |
| `--platform` | strings | да | 🔶 accepted | no | Error: failed to extract container: - |
| `-q, --quiet` | — | да | 🔷 ignored | no | Error: failed to extract container: - |

### `docker login` → `udocker login` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-p, --password` | string | да | 🔶 accepted | yes | Error: login needs a terminal or --username/--password/--password-stdin |
| `--password-stdin` | — | да | 🔶 accepted | yes | Error: login needs a terminal or --username/--password/--password-stdin |
| `-u, --username` | string | да | 🔶 accepted | yes | /home/i.sulin/.homebrew/opt/python@3.15/lib/python3.15/getpass.py:150: GetPassWarning: Can not control echo on the terminal. |

### `docker logs` → `udocker logs` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--details` | — | да | 🔶 accepted | yes | Error: container not found: nosuchct |
| `-f, --follow` | — | да | 🔶 accepted | yes | Error: container not found: nosuchct |
| `--since` | string | да | 🔶 accepted | yes | Error: container not found: nosuchct |
| `-n, --tail` | string | да | 🔶 accepted | yes | Error: container not found: nosuchct |
| `-t, --timestamps` | — | да | 🔶 accepted | yes | Error: container not found: nosuchct |
| `--until` | string | да | 🔶 accepted | yes | Error: container not found: nosuchct |

### `docker ps` → `udocker ps` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-a, --all` | — | да | ✅ ok | yes | CONTAINER ID   IMAGE                    COMMAND                CREATED              STATUS                 PORTS                    NAMES |
| `-f, --filter` | filter | да | ✅ ok | yes | CONTAINER ID   IMAGE                    COMMAND                CREATED              STATUS                 PORTS                    NAMES |
| `--format` | string | да | ✅ ok | yes |  |
| `-n, --last` | int | да | ✅ ok | no | CONTAINER ID   IMAGE                    COMMAND                CREATED              STATUS                 PORTS                    NAMES |
| `-l, --latest` | — | да | ✅ ok | no | CONTAINER ID   IMAGE                    COMMAND                CREATED              STATUS                 PORTS                    NAMES |
| `--no-trunc` | — | да | ✅ ok | yes | CONTAINER ID   IMAGE                    COMMAND                CREATED              STATUS                 PORTS                    NAMES |
| `-q, --quiet` | — | да | ✅ ok | yes |  |
| `-s, --size` | — | да | ✅ ok | no | CONTAINER ID   IMAGE                    COMMAND                CREATED              STATUS                 PORTS                    NAMES         SIZE |

### `docker pull` → `udocker pull` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-a, --all-tags` | — | да | 🔶 accepted | no | Error: in download: %s curl: (6) Could not resolve host: nonexistent.invalid (Domain name not found) |
| `--platform` | string | да | 🔶 accepted | yes | Error: in download: %s curl: (6) Could not resolve host: nonexistent.invalid (Domain name not found) |
| `-q, --quiet` | — | да | 🔷 ignored | no | Error: in download: %s curl: (6) Could not resolve host: nonexistent.invalid (Domain name not found) |

### `docker push` → `udocker push` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-a, --all-tags` | — | да | ⛔ root-only | no | Error: push --all-tags is not available rootless |
| `--platform` | string | да | 🔶 accepted | no | Error: image not found: nosuchimg:zzz |
| `-q, --quiet` | — | да | 🔷 ignored | no | Error: image not found: nosuchimg:zzz |

### `docker restart` → `udocker restart` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-s, --signal` | string | да | 🔶 accepted | no | Error: container not found: nosuchct |
| `-t, --timeout` | int | да | 🔶 accepted | no | Error: container not found: nosuchct |

### `docker rm` → `udocker rm` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --force` | — | да | 🔶 accepted | yes | Error: invalid container id |
| `-l, --link` | — | да | 🔷 ignored | yes | Error: invalid container id |
| `-v, --volumes` | — | да | 🔶 accepted | yes | Error: invalid container id |

### `docker rmi` → `udocker rmi` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --force` | — | да | 🔶 accepted | yes | Error: deleting image |
| `--no-prune` | — | да | 🔶 accepted | yes | Error: deleting image |
| `--platform` | strings | да | 🔶 accepted | no | Error: deleting image |

### `docker run` → `udocker run` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--add-host` | list | да | 🔶 accepted | yes | Error: image or container not found: nosuchct |
| `--annotation` | map | да | 🔷 ignored | no | Error: image or container not found: nosuchct |
| `-a, --attach` | list | да | 🔷 ignored | no | Error: image or container not found: nosuchct |
| `--blkio-weight` | uint16 | да | ⛔ root-only | no | Error: --blkio-weight: resource limits need cgroup delegation |
| `--blkio-weight-device` | list | да | ⛔ root-only | no | Error: --blkio-weight-device: resource limits need cgroup delegation |
| `--cap-add` | list | да | ⛔ root-only | no | Error: --cap-add: privileges and capabilities need root |
| `--cap-drop` | list | да | ⛔ root-only | no | Error: --cap-drop: privileges and capabilities need root |
| `--cgroup-parent` | string | да | 🔷 ignored | no | Error: image or container not found: nosuchct |
| `--cgroupns` | string | да | 🔷 ignored | no | Error: image or container not found: nosuchct |
| `--cidfile` | string | да | 🔶 accepted | no | Error: image or container not found: nosuchct |
| `--cpu-count` | int | да | ⛔ root-only | no | Error: --cpu-count: CPU limits need cgroup delegation |
| `--cpu-percent` | int | да | ⛔ root-only | no | Error: --cpu-percent: CPU limits need cgroup delegation |
| `--cpu-period` | int | да | ⛔ root-only | no | Error: --cpu-period: CPU limits need cgroup delegation |
| `--cpu-quota` | int | да | ⛔ root-only | no | Error: --cpu-quota: CPU limits need cgroup delegation |
| `--cpu-rt-period` | int | да | ⛔ root-only | no | Error: --cpu-rt-period: CPU limits need cgroup delegation |
| `--cpu-rt-runtime` | int | да | ⛔ root-only | no | Error: --cpu-rt-runtime: CPU limits need cgroup delegation |
| `-c, --cpu-shares` | int | да | ⛔ root-only | no | Error: --cpu-shares: CPU limits need cgroup delegation |
| `--cpus` | decimal | да | ⛔ root-only | no | Error: --cpus: CPU limits need cgroup delegation |
| `--cpuset-cpus` | string | да | 🔶 accepted | yes | Error: image or container not found: nosuchct |
| `--cpuset-mems` | string | да | ⛔ root-only | no | Error: --cpuset-mems: CPU limits need cgroup delegation |
| `-d, --detach` | — | да | 🔶 accepted | yes | Error: image or container not found: nosuchct |
| `--detach-keys` | string | да | 🔷 ignored | no | Error: image or container not found: nosuchct |
| `--device` | list | да | 🔶 accepted | yes | Error: image or container not found: nosuchct |
| `--device-cgroup-rule` | list | да | 🔷 ignored | no | Error: image or container not found: nosuchct |
| `--device-read-bps` | list | да | ⛔ root-only | no | Error: --device-read-bps: resource limits need cgroup delegation |
| `--device-read-iops` | list | да | ⛔ root-only | no | Error: --device-read-iops: resource limits need cgroup delegation |
| `--device-write-bps` | list | да | ⛔ root-only | no | Error: --device-write-bps: resource limits need cgroup delegation |
| `--device-write-iops` | list | да | ⛔ root-only | no | Error: --device-write-iops: resource limits need cgroup delegation |
| `--dns` | list | да | 🔶 accepted | yes | Error: image or container not found: nosuchct |
| `--dns-option` | list | да | 🔷 ignored | no | Error: image or container not found: nosuchct |
| `--dns-search` | list | да | 🔶 accepted | yes | Error: image or container not found: nosuchct |
| `--domainname` | string | да | 🔷 ignored | no | Error: image or container not found: nosuchct |
| `--entrypoint` | string | да | 🔶 accepted | yes | Error: image or container not found: nosuchct |
| `-e, --env` | list | да | 🔶 accepted | yes | Error: image or container not found: nosuchct |
| `--env-file` | list | да | 🔶 accepted | yes | Error: image or container not found: nosuchct |
| `--expose` | list | да | 🔶 accepted | no | Error: image or container not found: nosuchct |
| `--group-add` | list | да | ⛔ root-only | no | Error: --group-add: privileges and capabilities need root |
| `--health-cmd` | string | да | 🔶 accepted | yes | Error: image or container not found: nosuchct |
| `--health-interval` | duration | да | 🔶 accepted | yes | Error: image or container not found: nosuchct |
| `--health-retries` | int | да | 🔶 accepted | yes | Error: image or container not found: nosuchct |
| `--health-start-interval` | duration | да | 🔶 accepted | no | Error: image or container not found: nosuchct |
| `--health-start-period` | duration | да | 🔶 accepted | yes | Error: image or container not found: nosuchct |
| `--health-timeout` | duration | да | 🔶 accepted | yes | Error: image or container not found: nosuchct |
| `--help` | — | да | ✅ ok | no | run: execute a container |
| `-h, --hostname` | string | да | 🔶 accepted | yes | Error: image or container not found: nosuchct |
| `--init` | — | да | 🔷 ignored | no | Error: image or container not found: nosuchct |
| `-i, --interactive` | — | да | 🔶 accepted | yes | Error: image or container not found: nosuchct |
| `--io-maxbandwidth` | bytes | да | ⛔ root-only | no | Error: --io-maxbandwidth: resource limits need cgroup delegation |
| `--io-maxiops` | uint | да | ⛔ root-only | no | Error: --io-maxiops: resource limits need cgroup delegation |
| `--ip` | ip | да | ⛔ root-only | no | Error: --ip: container networking is host-only |
| `--ip6` | ip | да | ⛔ root-only | no | Error: --ip6: container networking is host-only |
| `--ipc` | string | да | 🔷 ignored | no | Error: image or container not found: nosuchct |
| `--isolation` | string | да | 🔷 ignored | no | Error: image or container not found: nosuchct |
| `-l, --label` | list | да | 🔶 accepted | yes | Error: image or container not found: nosuchct |
| `--label-file` | list | да | 🔶 accepted | no | Error: image or container not found: nosuchct |
| `--link` | list | да | ⛔ root-only | no | Error: --link: container networking is host-only |
| `--link-local-ip` | list | да | ⛔ root-only | no | Error: --link-local-ip: container networking is host-only |
| `--log-driver` | string | да | 🔷 ignored | no | Error: image or container not found: nosuchct |
| `--log-opt` | list | да | 🔷 ignored | no | Error: image or container not found: nosuchct |
| `--mac-address` | string | да | ⛔ root-only | no | Error: --mac-address: container networking is host-only |
| `-m, --memory` | bytes | да | ⛔ root-only | no | Error: --memory: resource limits need cgroup delegation |
| `--memory-reservation` | bytes | да | ⛔ root-only | no | Error: --memory-reservation: resource limits need cgroup delegation |
| `--memory-swap` | bytes | да | ⛔ root-only | no | Error: --memory-swap: resource limits need cgroup delegation |
| `--memory-swappiness` | int | да | ⛔ root-only | no | Error: --memory-swappiness: resource limits need cgroup delegation |
| `--mount` | mount | да | 🔶 accepted | no | Error: image or container not found: nosuchct |
| `--name` | string | да | 🔶 accepted | yes | Error: image or container not found: nosuchct |
| `--network` | network | да | 🔷 ignored | no | Error: image or container not found: nosuchct |
| `--network-alias` | list | да | ⛔ root-only | no | Error: --network-alias: container networking is host-only |
| `--no-healthcheck` | — | да | 🔶 accepted | no | Error: image or container not found: nosuchct |
| `--oom-kill-disable` | — | да | ⛔ root-only | no | Error: --oom-kill-disable: resource limits need cgroup delegation |
| `--oom-score-adj` | int | да | ⛔ root-only | no | Error: --oom-score-adj: resource limits need cgroup delegation |
| `--pid` | string | да | 🔷 ignored | no | Error: image or container not found: nosuchct |
| `--pids-limit` | int | да | ⛔ root-only | no | Error: --pids-limit: resource limits need cgroup delegation |
| `--platform` | string | да | 🔶 accepted | yes | Error: image or container not found: nosuchct |
| `--privileged` | — | да | ⛔ root-only | no | Error: --privileged: privileges and capabilities need root |
| `-p, --publish` | list | да | 🔶 accepted | yes | Error: image or container not found: nosuchct |
| `-P, --publish-all` | — | да | 🔶 accepted | yes | Error: image or container not found: nosuchct |
| `--pull` | string | да | 🔶 accepted | yes | Error: image or container not found: nosuchct |
| `-q, --quiet` | — | да | 🔷 ignored | no | Error: image or container not found: nosuchct |
| `--read-only` | — | да | ⛔ root-only | no | Error: --read-only: a read-only root filesystem needs a mount namespace |
| `--restart` | string | да | 🔶 accepted | no | Error: image or container not found: nosuchct |
| `--rm` | — | да | 🔶 accepted | yes | Error: image or container not found: nosuchct |
| `--runtime` | string | да | ⛔ root-only | no | Error: --runtime: the execution mode is selected with --execmode |
| `--security-opt` | list | да | 🔷 ignored | no | Error: image or container not found: nosuchct |
| `--shm-size` | bytes | да | 🔷 ignored | no | Error: image or container not found: nosuchct |
| `--sig-proxy` | — | да | 🔷 ignored | no | Error: manifest not found or not authorized |
| `--stop-signal` | string | да | 🔶 accepted | yes | Error: image or container not found: nosuchct |
| `--stop-timeout` | int | да | 🔶 accepted | yes | Error: image or container not found: nosuchct |
| `--storage-opt` | list | да | 🔷 ignored | no | Error: image or container not found: nosuchct |
| `--sysctl` | map | да | ⛔ root-only | no | Error: --sysctl: privileges and capabilities need root |
| `--tmpfs` | list | да | ⛔ root-only | no | Error: --tmpfs: tmpfs mounts need a mount namespace (use -v /some/dir:/path instead) |
| `-t, --tty` | — | да | 🔶 accepted | yes | Error: image or container not found: nosuchct |
| `--ulimit` | ulimit | да | 🔶 accepted | yes | Error: image or container not found: nosuchct |
| `--umask` | umask | да | 🔷 ignored | no | Error: image or container not found: nosuchct |
| `--use-api-socket` | — | да | 🔷 ignored | no | Error: image or container not found: nosuchct |
| `-u, --user` | string | да | 🔶 accepted | yes | Error: image or container not found: nosuchct |
| `--userns` | string | да | 🔷 ignored | no | Error: image or container not found: nosuchct |
| `--uts` | string | да | 🔷 ignored | no | Error: image or container not found: nosuchct |
| `-v, --volume` | list | да | 🔶 accepted | yes | Error: image or container not found: nosuchct |
| `--volume-driver` | string | да | 🔷 ignored | no | Error: image or container not found: nosuchct |
| `--volumes-from` | list | да | 🔶 accepted | yes | Error: image or container not found: nosuchct |
| `-w, --workdir` | string | да | 🔶 accepted | yes | Error: image or container not found: nosuchct |

### `docker save` → `udocker save` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-o, --output` | string | да | 🔶 accepted | yes | Error: save image failed: nosuchimg:latest |
| `--platform` | strings | да | 🔶 accepted | no | Error: save image failed: nosuchimg:latest |

### `docker search` → `udocker search` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --filter` | filter | да | ✅ ok | no | NAME                                                    OFFICIAL DESCRIPTION                                                            STARS |
| `--format` | string | да | ✅ ok | no | json |
| `--limit` | int | да | ✅ ok | no | NAME                                                    OFFICIAL DESCRIPTION                                                            STARS |
| `--no-trunc` | — | да | ✅ ok | yes | NAME                                                    OFFICIAL DESCRIPTION                                                            STARS |

### `docker start` → `udocker start` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-a, --attach` | — | да | 🔷 ignored | no | Error: must specify a container |
| `--checkpoint` | string | да | ⛔ root-only | no | Error: --checkpoint: checkpointing needs CRIU and root |
| `--checkpoint-dir` | string | да | ⛔ root-only | no | Error: --checkpoint-dir: checkpointing needs CRIU and root |
| `--detach-keys` | string | да | 🔷 ignored | no | Error: container not found: nosuchct |
| `-i, --interactive` | — | да | 🔷 ignored | no | Error: container not found: nosuchct |

### `docker stats` → `udocker stats` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-a, --all` | — | да | 🔶 accepted | yes | Error: container not found: nosuchct |
| `--format` | string | да | 🔶 accepted | yes | Error: container not found: nosuchct |
| `--no-stream` | — | да | 🔶 accepted | yes | Error: container not found: nosuchct |
| `--no-trunc` | — | да | 🔷 ignored | yes | Error: container not found: nosuchct |

### `docker stop` → `udocker stop` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-s, --signal` | string | да | 🔶 accepted | no | Error: container not found: nosuchct |
| `-t, --timeout` | int | да | 🔶 accepted | no | Error: container not found: nosuchct |

### `docker version` → `udocker version` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --format` | string | да | ✅ ok | yes | { |

### `docker attach` → `udocker attach` 🔶

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--detach-keys` | string | да | ⛔ root-only | no | Error: attach is not available rootless: attaching to the container stdio needs a pty relay; use: exec -it <container> <command> |
| `--no-stdin` | — | да | ⛔ root-only | no | Error: attach is not available rootless: attaching to the container stdio needs a pty relay; use: exec -it <container> <command> |
| `--sig-proxy` | — | да | ⛔ root-only | no | Error: attach is not available rootless: attaching to the container stdio needs a pty relay; use: exec -it <container> <command> |

### `docker builder build` → `udocker builder build` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--add-host` | list | да | ➖ excluded | no | вне scope контракта |
| `--build-arg` | list | да | ➖ excluded | no | вне scope контракта |
| `--cache-from` | strings | да | ➖ excluded | no | вне scope контракта |
| `--cgroup-parent` | string | да | ➖ excluded | no | вне scope контракта |
| `--compress` | — | да | ➖ excluded | no | вне scope контракта |
| `--cpu-period` | int | да | ➖ excluded | no | вне scope контракта |
| `--cpu-quota` | int | да | ➖ excluded | no | вне scope контракта |
| `-c, --cpu-shares` | int | да | ➖ excluded | no | вне scope контракта |
| `--cpuset-cpus` | string | да | ➖ excluded | no | вне scope контракта |
| `--cpuset-mems` | string | да | ➖ excluded | no | вне scope контракта |
| `-f, --file` | string | да | ➖ excluded | no | вне scope контракта |
| `--force-rm` | — | да | ➖ excluded | no | вне scope контракта |
| `--iidfile` | string | да | ➖ excluded | no | вне scope контракта |
| `--isolation` | string | да | ➖ excluded | no | вне scope контракта |
| `--label` | list | да | ➖ excluded | no | вне scope контракта |
| `-m, --memory` | bytes | да | ➖ excluded | no | вне scope контракта |
| `--memory-swap` | bytes | да | ➖ excluded | no | вне scope контракта |
| `--network` | string | да | ➖ excluded | no | вне scope контракта |
| `--no-cache` | — | да | ➖ excluded | no | вне scope контракта |
| `--platform` | string | да | ➖ excluded | no | вне scope контракта |
| `--pull` | — | да | ➖ excluded | no | вне scope контракта |
| `-q, --quiet` | — | да | ➖ excluded | no | вне scope контракта |
| `--rm` | — | да | ➖ excluded | no | вне scope контракта |
| `--security-opt` | strings | да | ➖ excluded | no | вне scope контракта |
| `--shm-size` | bytes | да | ➖ excluded | no | вне scope контракта |
| `--squash` | — | да | ➖ excluded | no | вне scope контракта |
| `-t, --tag` | list | да | ➖ excluded | no | вне scope контракта |
| `--target` | string | да | ➖ excluded | no | вне scope контракта |
| `--ulimit` | ulimit | да | ➖ excluded | no | вне scope контракта |

### `docker builder prune` → `udocker builder prune` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-a, --all` | — | да | ➖ excluded | no | вне scope контракта |
| `--filter` | filter | да | ➖ excluded | no | вне scope контракта |
| `-f, --force` | — | да | ➖ excluded | no | вне scope контракта |
| `--keep-storage` | bytes | да | ➖ excluded | no | вне scope контракта |

### `docker checkpoint create` → `udocker checkpoint create` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--checkpoint-dir` | string | да | ➖ excluded | no | вне scope контракта |
| `--leave-running` | — | да | ➖ excluded | no | вне scope контракта |

### `docker checkpoint ls` → `udocker checkpoint ls` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--checkpoint-dir` | string | да | ➖ excluded | no | вне scope контракта |

### `docker checkpoint rm` → `udocker checkpoint rm` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--checkpoint-dir` | string | да | ➖ excluded | no | вне scope контракта |

### `docker config create` → `udocker config create` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-l, --label` | list | да | ➖ excluded | no | вне scope контракта |
| `--template-driver` | string | да | ➖ excluded | no | вне scope контракта |

### `docker config inspect` → `udocker config inspect` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --format` | string | да | ➖ excluded | no | вне scope контракта |
| `--pretty` | — | да | ➖ excluded | no | вне scope контракта |

### `docker config ls` → `udocker config ls` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --filter` | filter | да | ➖ excluded | no | вне scope контракта |
| `--format` | string | да | ➖ excluded | no | вне scope контракта |
| `-q, --quiet` | — | да | ➖ excluded | no | вне scope контракта |

### `docker container attach` → `udocker container attach` 🔶

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--detach-keys` | string | да | ⛔ root-only | no | Error: attach is not available rootless: attaching to the container stdio needs a pty relay; use: exec -it <container> <command> |
| `--no-stdin` | — | да | ⛔ root-only | no | Error: attach is not available rootless: attaching to the container stdio needs a pty relay; use: exec -it <container> <command> |
| `--sig-proxy` | — | да | ⛔ root-only | no | Error: attach is not available rootless: attaching to the container stdio needs a pty relay; use: exec -it <container> <command> |

### `docker container commit` → `udocker container commit` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-a, --author` | string | да | 🔶 accepted | yes | Error: container not found: nosuchct |
| `-c, --change` | list | да | 🔶 accepted | no | Error: container not found: nosuchct |
| `-m, --message` | string | да | 🔶 accepted | yes | Error: container not found: nosuchct |
| `--no-pause` | — | да | 🔶 accepted | no | Error: container not found: nosuchct |

### `docker container cp` → `udocker container cp` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-a, --archive` | — | да | 🔶 accepted | no | Error: one of source or destination must be a container |
| `-L, --follow-link` | — | да | 🔶 accepted | no | Error: one of source or destination must be a container |
| `-q, --quiet` | — | да | 🔶 accepted | no | Error: one of source or destination must be a container |

### `docker container create` → `udocker container create` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--add-host` | list | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--annotation` | map | да | 🔷 ignored | no | Error: must specify image:tag or repository/image:tag |
| `-a, --attach` | list | да | 🔷 ignored | no | Error: must specify image:tag or repository/image:tag |
| `--blkio-weight` | uint16 | да | ⛔ root-only | no | Error: --blkio-weight: resource limits need cgroup delegation |
| `--blkio-weight-device` | list | да | ⛔ root-only | no | Error: --blkio-weight-device: resource limits need cgroup delegation |
| `--cap-add` | list | да | ⛔ root-only | no | Error: --cap-add: privileges and capabilities need root |
| `--cap-drop` | list | да | ⛔ root-only | no | Error: --cap-drop: privileges and capabilities need root |
| `--cgroup-parent` | string | да | 🔷 ignored | no | Error: must specify image:tag or repository/image:tag |
| `--cgroupns` | string | да | 🔷 ignored | no | Error: must specify image:tag or repository/image:tag |
| `--cidfile` | string | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--cpu-count` | int | да | ⛔ root-only | no | Error: --cpu-count: CPU limits need cgroup delegation |
| `--cpu-percent` | int | да | ⛔ root-only | no | Error: --cpu-percent: CPU limits need cgroup delegation |
| `--cpu-period` | int | да | ⛔ root-only | no | Error: --cpu-period: CPU limits need cgroup delegation |
| `--cpu-quota` | int | да | ⛔ root-only | no | Error: --cpu-quota: CPU limits need cgroup delegation |
| `--cpu-rt-period` | int | да | ⛔ root-only | no | Error: --cpu-rt-period: CPU limits need cgroup delegation |
| `--cpu-rt-runtime` | int | да | ⛔ root-only | no | Error: --cpu-rt-runtime: CPU limits need cgroup delegation |
| `-c, --cpu-shares` | int | да | ⛔ root-only | no | Error: --cpu-shares: CPU limits need cgroup delegation |
| `--cpus` | decimal | да | ⛔ root-only | no | Error: --cpus: CPU limits need cgroup delegation |
| `--cpuset-cpus` | string | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--cpuset-mems` | string | да | ⛔ root-only | no | Error: --cpuset-mems: CPU limits need cgroup delegation |
| `--device` | list | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--device-cgroup-rule` | list | да | 🔷 ignored | no | Error: must specify image:tag or repository/image:tag |
| `--device-read-bps` | list | да | ⛔ root-only | no | Error: --device-read-bps: resource limits need cgroup delegation |
| `--device-read-iops` | list | да | ⛔ root-only | no | Error: --device-read-iops: resource limits need cgroup delegation |
| `--device-write-bps` | list | да | ⛔ root-only | no | Error: --device-write-bps: resource limits need cgroup delegation |
| `--device-write-iops` | list | да | ⛔ root-only | no | Error: --device-write-iops: resource limits need cgroup delegation |
| `--dns` | list | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--dns-option` | list | да | 🔷 ignored | no | Error: must specify image:tag or repository/image:tag |
| `--dns-search` | list | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--domainname` | string | да | 🔷 ignored | no | Error: must specify image:tag or repository/image:tag |
| `--entrypoint` | string | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `-e, --env` | list | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--env-file` | list | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--expose` | list | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--group-add` | list | да | ⛔ root-only | no | Error: --group-add: privileges and capabilities need root |
| `--health-cmd` | string | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--health-interval` | duration | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--health-retries` | int | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--health-start-interval` | duration | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--health-start-period` | duration | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--health-timeout` | duration | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--help` | — | да | ✅ ok | no | create: extract image layers and create a container |
| `-h, --hostname` | string | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--init` | — | да | 🔷 ignored | no | Error: must specify image:tag or repository/image:tag |
| `-i, --interactive` | — | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--io-maxbandwidth` | bytes | да | ⛔ root-only | no | Error: --io-maxbandwidth: resource limits need cgroup delegation |
| `--io-maxiops` | uint | да | ⛔ root-only | no | Error: --io-maxiops: resource limits need cgroup delegation |
| `--ip` | ip | да | ⛔ root-only | no | Error: --ip: container networking is host-only |
| `--ip6` | ip | да | ⛔ root-only | no | Error: --ip6: container networking is host-only |
| `--ipc` | string | да | 🔷 ignored | no | Error: must specify image:tag or repository/image:tag |
| `--isolation` | string | да | 🔷 ignored | no | Error: must specify image:tag or repository/image:tag |
| `-l, --label` | list | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--label-file` | list | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--link` | list | да | ⛔ root-only | no | Error: --link: container networking is host-only |
| `--link-local-ip` | list | да | ⛔ root-only | no | Error: --link-local-ip: container networking is host-only |
| `--log-driver` | string | да | 🔷 ignored | no | Error: must specify image:tag or repository/image:tag |
| `--log-opt` | list | да | 🔷 ignored | no | Error: must specify image:tag or repository/image:tag |
| `--mac-address` | string | да | ⛔ root-only | no | Error: --mac-address: container networking is host-only |
| `-m, --memory` | bytes | да | ⛔ root-only | no | Error: --memory: resource limits need cgroup delegation |
| `--memory-reservation` | bytes | да | ⛔ root-only | no | Error: --memory-reservation: resource limits need cgroup delegation |
| `--memory-swap` | bytes | да | ⛔ root-only | no | Error: --memory-swap: resource limits need cgroup delegation |
| `--memory-swappiness` | int | да | ⛔ root-only | no | Error: --memory-swappiness: resource limits need cgroup delegation |
| `--mount` | mount | да | 🔶 accepted | no | Error: invalid --mount (no target): /tmp |
| `--name` | string | да | 🔶 accepted | yes | Error: must specify image:tag or repository/image:tag |
| `--network` | network | да | 🔷 ignored | no | Error: must specify image:tag or repository/image:tag |
| `--network-alias` | list | да | ⛔ root-only | no | Error: --network-alias: container networking is host-only |
| `--no-healthcheck` | — | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--oom-kill-disable` | — | да | ⛔ root-only | no | Error: --oom-kill-disable: resource limits need cgroup delegation |
| `--oom-score-adj` | int | да | ⛔ root-only | no | Error: --oom-score-adj: resource limits need cgroup delegation |
| `--pid` | string | да | 🔷 ignored | no | Error: must specify image:tag or repository/image:tag |
| `--pids-limit` | int | да | ⛔ root-only | no | Error: --pids-limit: resource limits need cgroup delegation |
| `--platform` | string | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--privileged` | — | да | ⛔ root-only | no | Error: --privileged: privileges and capabilities need root |
| `-p, --publish` | list | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `-P, --publish-all` | — | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--pull` | string | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `-q, --quiet` | — | да | 🔷 ignored | no | Error: must specify image:tag or repository/image:tag |
| `--read-only` | — | да | ⛔ root-only | no | Error: --read-only: a read-only root filesystem needs a mount namespace |
| `--restart` | string | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--rm` | — | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--runtime` | string | да | ⛔ root-only | no | Error: --runtime: the execution mode is selected with --execmode |
| `--security-opt` | list | да | 🔷 ignored | no | Error: must specify image:tag or repository/image:tag |
| `--shm-size` | bytes | да | 🔷 ignored | no | Error: must specify image:tag or repository/image:tag |
| `--stop-signal` | string | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--stop-timeout` | int | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--storage-opt` | list | да | 🔷 ignored | no | Error: must specify image:tag or repository/image:tag |
| `--sysctl` | map | да | ⛔ root-only | no | Error: --sysctl: privileges and capabilities need root |
| `--tmpfs` | list | да | ⛔ root-only | no | Error: --tmpfs: tmpfs mounts need a mount namespace (use -v /some/dir:/path instead) |
| `-t, --tty` | — | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--ulimit` | ulimit | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--umask` | umask | да | 🔷 ignored | no | Error: must specify image:tag or repository/image:tag |
| `--use-api-socket` | — | да | 🔷 ignored | no | Error: must specify image:tag or repository/image:tag |
| `-u, --user` | string | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--userns` | string | да | 🔷 ignored | no | Error: must specify image:tag or repository/image:tag |
| `--uts` | string | да | 🔷 ignored | no | Error: must specify image:tag or repository/image:tag |
| `-v, --volume` | list | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--volume-driver` | string | да | 🔷 ignored | no | Error: must specify image:tag or repository/image:tag |
| `--volumes-from` | list | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `-w, --workdir` | string | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |

### `docker container exec` → `udocker container exec` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-d, --detach` | — | да | 🔶 accepted | no | Error: container not found: nosuchct |
| `--detach-keys` | string | да | 🔷 ignored | no | Error: container not found: nosuchct |
| `-e, --env` | list | да | 🔶 accepted | yes | Error: container not found: nosuchct |
| `--env-file` | list | да | 🔶 accepted | no | Error: container not found: nosuchct |
| `-i, --interactive` | — | да | 🔶 accepted | no | Error: container not found: nosuchct |
| `--privileged` | — | да | 🔷 ignored | no | Error: container not found: nosuchct |
| `-t, --tty` | — | да | 🔶 accepted | no | Error: container not found: nosuchct |
| `-u, --user` | string | да | 🔶 accepted | yes | Error: container not found: nosuchct |
| `-w, --workdir` | string | да | 🔶 accepted | yes | Error: container not found: nosuchct |

### `docker container export` → `udocker container export` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-o, --output` | string | да | 🔶 accepted | no | Error: invalid container id |

### `docker container inspect` → `udocker container inspect` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --format` | string | да | 🔶 accepted | yes | Error: no such object: nosuchobj |
| `-s, --size` | — | да | 🔶 accepted | yes | Error: no such object: nosuchobj |

### `docker container kill` → `udocker container kill` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-s, --signal` | string | да | 🔶 accepted | yes | Error: must specify a container |

### `docker container logs` → `udocker container logs` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--details` | — | да | 🔶 accepted | yes | Error: container not found: nosuchct |
| `-f, --follow` | — | да | 🔶 accepted | yes | Error: container not found: nosuchct |
| `--since` | string | да | 🔶 accepted | yes | Error: container not found: nosuchct |
| `-n, --tail` | string | да | 🔶 accepted | yes | Error: container not found: nosuchct |
| `-t, --timestamps` | — | да | 🔶 accepted | yes | Error: container not found: nosuchct |
| `--until` | string | да | 🔶 accepted | yes | Error: container not found: nosuchct |

### `docker container ls` → `udocker container ls` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-a, --all` | — | да | ✅ ok | yes | CONTAINER ID   IMAGE                    COMMAND                CREATED              STATUS                 PORTS                    NAMES |
| `-f, --filter` | filter | да | ✅ ok | yes | CONTAINER ID   IMAGE                    COMMAND                CREATED              STATUS                 PORTS                    NAMES |
| `--format` | string | да | ✅ ok | yes |  |
| `-n, --last` | int | да | ✅ ok | no | CONTAINER ID   IMAGE                    COMMAND                CREATED              STATUS                 PORTS                    NAMES |
| `-l, --latest` | — | да | ✅ ok | no | CONTAINER ID   IMAGE                    COMMAND                CREATED              STATUS                 PORTS                    NAMES |
| `--no-trunc` | — | да | ✅ ok | yes | CONTAINER ID   IMAGE                    COMMAND                CREATED              STATUS                 PORTS                    NAMES |
| `-q, --quiet` | — | да | ✅ ok | yes |  |
| `-s, --size` | — | да | ✅ ok | no | CONTAINER ID   IMAGE                    COMMAND                CREATED              STATUS                 PORTS                    NAMES         SIZE |

### `docker container prune` → `udocker container prune` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--filter` | filter | да | 🔷 ignored | no | Error: prune requires -f when stdin is not a terminal (use -f) |
| `-f, --force` | — | да | ✅ ok | no | Total reclaimed space: 0B |

### `docker container restart` → `udocker container restart` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-s, --signal` | string | да | 🔶 accepted | no | Error: must specify a container |
| `-t, --timeout` | int | да | 🔶 accepted | no | Error: must specify a container |

### `docker container rm` → `udocker container rm` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --force` | — | да | 🔶 accepted | yes | Error: invalid container id |
| `-l, --link` | — | да | 🔷 ignored | yes | Error: invalid container id |
| `-v, --volumes` | — | да | 🔶 accepted | yes | Error: invalid container id |

### `docker container run` → `udocker container run` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--add-host` | list | да | 🔶 accepted | yes | Error: must specify container_id or image:tag |
| `--annotation` | map | да | 🔷 ignored | no | Error: must specify container_id or image:tag |
| `-a, --attach` | list | да | 🔷 ignored | no | Error: must specify container_id or image:tag |
| `--blkio-weight` | uint16 | да | ⛔ root-only | no | Error: --blkio-weight: resource limits need cgroup delegation |
| `--blkio-weight-device` | list | да | ⛔ root-only | no | Error: --blkio-weight-device: resource limits need cgroup delegation |
| `--cap-add` | list | да | ⛔ root-only | no | Error: --cap-add: privileges and capabilities need root |
| `--cap-drop` | list | да | ⛔ root-only | no | Error: --cap-drop: privileges and capabilities need root |
| `--cgroup-parent` | string | да | 🔷 ignored | no | Error: must specify container_id or image:tag |
| `--cgroupns` | string | да | 🔷 ignored | no | Error: must specify container_id or image:tag |
| `--cidfile` | string | да | 🔶 accepted | no | Error: must specify container_id or image:tag |
| `--cpu-count` | int | да | ⛔ root-only | no | Error: --cpu-count: CPU limits need cgroup delegation |
| `--cpu-percent` | int | да | ⛔ root-only | no | Error: --cpu-percent: CPU limits need cgroup delegation |
| `--cpu-period` | int | да | ⛔ root-only | no | Error: --cpu-period: CPU limits need cgroup delegation |
| `--cpu-quota` | int | да | ⛔ root-only | no | Error: --cpu-quota: CPU limits need cgroup delegation |
| `--cpu-rt-period` | int | да | ⛔ root-only | no | Error: --cpu-rt-period: CPU limits need cgroup delegation |
| `--cpu-rt-runtime` | int | да | ⛔ root-only | no | Error: --cpu-rt-runtime: CPU limits need cgroup delegation |
| `-c, --cpu-shares` | int | да | ⛔ root-only | no | Error: --cpu-shares: CPU limits need cgroup delegation |
| `--cpus` | decimal | да | ⛔ root-only | no | Error: --cpus: CPU limits need cgroup delegation |
| `--cpuset-cpus` | string | да | 🔶 accepted | yes | Error: must specify container_id or image:tag |
| `--cpuset-mems` | string | да | ⛔ root-only | no | Error: --cpuset-mems: CPU limits need cgroup delegation |
| `-d, --detach` | — | да | 🔶 accepted | yes | Error: must specify container_id or image:tag |
| `--detach-keys` | string | да | 🔷 ignored | no | Error: must specify container_id or image:tag |
| `--device` | list | да | 🔶 accepted | yes | Error: must specify container_id or image:tag |
| `--device-cgroup-rule` | list | да | 🔷 ignored | no | Error: must specify container_id or image:tag |
| `--device-read-bps` | list | да | ⛔ root-only | no | Error: --device-read-bps: resource limits need cgroup delegation |
| `--device-read-iops` | list | да | ⛔ root-only | no | Error: --device-read-iops: resource limits need cgroup delegation |
| `--device-write-bps` | list | да | ⛔ root-only | no | Error: --device-write-bps: resource limits need cgroup delegation |
| `--device-write-iops` | list | да | ⛔ root-only | no | Error: --device-write-iops: resource limits need cgroup delegation |
| `--dns` | list | да | 🔶 accepted | yes | Error: must specify container_id or image:tag |
| `--dns-option` | list | да | 🔷 ignored | no | Error: must specify container_id or image:tag |
| `--dns-search` | list | да | 🔶 accepted | yes | Error: must specify container_id or image:tag |
| `--domainname` | string | да | 🔷 ignored | no | Error: must specify container_id or image:tag |
| `--entrypoint` | string | да | 🔶 accepted | yes | Error: must specify container_id or image:tag |
| `-e, --env` | list | да | 🔶 accepted | yes | Error: must specify container_id or image:tag |
| `--env-file` | list | да | 🔶 accepted | yes | Error: must specify container_id or image:tag |
| `--expose` | list | да | 🔶 accepted | no | Error: must specify container_id or image:tag |
| `--group-add` | list | да | ⛔ root-only | no | Error: --group-add: privileges and capabilities need root |
| `--health-cmd` | string | да | 🔶 accepted | yes | Error: must specify container_id or image:tag |
| `--health-interval` | duration | да | 🔶 accepted | yes | Error: must specify container_id or image:tag |
| `--health-retries` | int | да | 🔶 accepted | yes | Error: must specify container_id or image:tag |
| `--health-start-interval` | duration | да | 🔶 accepted | no | Error: must specify container_id or image:tag |
| `--health-start-period` | duration | да | 🔶 accepted | yes | Error: must specify container_id or image:tag |
| `--health-timeout` | duration | да | 🔶 accepted | yes | Error: must specify container_id or image:tag |
| `--help` | — | да | ✅ ok | no | run: execute a container |
| `-h, --hostname` | string | да | 🔶 accepted | yes | Error: must specify container_id or image:tag |
| `--init` | — | да | 🔷 ignored | no | Error: must specify container_id or image:tag |
| `-i, --interactive` | — | да | 🔶 accepted | yes | Error: must specify container_id or image:tag |
| `--io-maxbandwidth` | bytes | да | ⛔ root-only | no | Error: --io-maxbandwidth: resource limits need cgroup delegation |
| `--io-maxiops` | uint | да | ⛔ root-only | no | Error: --io-maxiops: resource limits need cgroup delegation |
| `--ip` | ip | да | ⛔ root-only | no | Error: --ip: container networking is host-only |
| `--ip6` | ip | да | ⛔ root-only | no | Error: --ip6: container networking is host-only |
| `--ipc` | string | да | 🔷 ignored | no | Error: must specify container_id or image:tag |
| `--isolation` | string | да | 🔷 ignored | no | Error: must specify container_id or image:tag |
| `-l, --label` | list | да | 🔶 accepted | yes | Error: must specify container_id or image:tag |
| `--label-file` | list | да | 🔶 accepted | no | Error: must specify container_id or image:tag |
| `--link` | list | да | ⛔ root-only | no | Error: --link: container networking is host-only |
| `--link-local-ip` | list | да | ⛔ root-only | no | Error: --link-local-ip: container networking is host-only |
| `--log-driver` | string | да | 🔷 ignored | no | Error: must specify container_id or image:tag |
| `--log-opt` | list | да | 🔷 ignored | no | Error: must specify container_id or image:tag |
| `--mac-address` | string | да | ⛔ root-only | no | Error: --mac-address: container networking is host-only |
| `-m, --memory` | bytes | да | ⛔ root-only | no | Error: --memory: resource limits need cgroup delegation |
| `--memory-reservation` | bytes | да | ⛔ root-only | no | Error: --memory-reservation: resource limits need cgroup delegation |
| `--memory-swap` | bytes | да | ⛔ root-only | no | Error: --memory-swap: resource limits need cgroup delegation |
| `--memory-swappiness` | int | да | ⛔ root-only | no | Error: --memory-swappiness: resource limits need cgroup delegation |
| `--mount` | mount | да | 🔶 accepted | no | Error: must specify container_id or image:tag |
| `--name` | string | да | 🔶 accepted | yes | Error: must specify container_id or image:tag |
| `--network` | network | да | 🔷 ignored | no | Error: must specify container_id or image:tag |
| `--network-alias` | list | да | ⛔ root-only | no | Error: --network-alias: container networking is host-only |
| `--no-healthcheck` | — | да | 🔶 accepted | no | Error: must specify container_id or image:tag |
| `--oom-kill-disable` | — | да | ⛔ root-only | no | Error: --oom-kill-disable: resource limits need cgroup delegation |
| `--oom-score-adj` | int | да | ⛔ root-only | no | Error: --oom-score-adj: resource limits need cgroup delegation |
| `--pid` | string | да | 🔷 ignored | no | Error: must specify container_id or image:tag |
| `--pids-limit` | int | да | ⛔ root-only | no | Error: --pids-limit: resource limits need cgroup delegation |
| `--platform` | string | да | 🔶 accepted | yes | Error: must specify container_id or image:tag |
| `--privileged` | — | да | ⛔ root-only | no | Error: --privileged: privileges and capabilities need root |
| `-p, --publish` | list | да | 🔶 accepted | yes | Error: must specify container_id or image:tag |
| `-P, --publish-all` | — | да | 🔶 accepted | yes | Error: must specify container_id or image:tag |
| `--pull` | string | да | 🔶 accepted | yes | Error: must specify container_id or image:tag |
| `-q, --quiet` | — | да | 🔷 ignored | no | Error: must specify container_id or image:tag |
| `--read-only` | — | да | ⛔ root-only | no | Error: --read-only: a read-only root filesystem needs a mount namespace |
| `--restart` | string | да | 🔶 accepted | no | Error: must specify container_id or image:tag |
| `--rm` | — | да | 🔶 accepted | yes | Error: must specify container_id or image:tag |
| `--runtime` | string | да | ⛔ root-only | no | Error: --runtime: the execution mode is selected with --execmode |
| `--security-opt` | list | да | 🔷 ignored | no | Error: must specify container_id or image:tag |
| `--shm-size` | bytes | да | 🔷 ignored | no | Error: must specify container_id or image:tag |
| `--sig-proxy` | — | да | 🔷 ignored | no | Error: must specify container_id or image:tag |
| `--stop-signal` | string | да | 🔶 accepted | yes | Error: must specify container_id or image:tag |
| `--stop-timeout` | int | да | 🔶 accepted | yes | Error: must specify container_id or image:tag |
| `--storage-opt` | list | да | 🔷 ignored | no | Error: must specify container_id or image:tag |
| `--sysctl` | map | да | ⛔ root-only | no | Error: --sysctl: privileges and capabilities need root |
| `--tmpfs` | list | да | ⛔ root-only | no | Error: --tmpfs: tmpfs mounts need a mount namespace (use -v /some/dir:/path instead) |
| `-t, --tty` | — | да | 🔶 accepted | yes | Error: must specify container_id or image:tag |
| `--ulimit` | ulimit | да | 🔶 accepted | yes | Error: must specify container_id or image:tag |
| `--umask` | umask | да | 🔷 ignored | no | Error: must specify container_id or image:tag |
| `--use-api-socket` | — | да | 🔷 ignored | no | Error: must specify container_id or image:tag |
| `-u, --user` | string | да | 🔶 accepted | yes | Error: must specify container_id or image:tag |
| `--userns` | string | да | 🔷 ignored | no | Error: must specify container_id or image:tag |
| `--uts` | string | да | 🔷 ignored | no | Error: must specify container_id or image:tag |
| `-v, --volume` | list | да | 🔶 accepted | yes | Error: must specify container_id or image:tag |
| `--volume-driver` | string | да | 🔷 ignored | no | Error: must specify container_id or image:tag |
| `--volumes-from` | list | да | 🔶 accepted | yes | Error: must specify container_id or image:tag |
| `-w, --workdir` | string | да | 🔶 accepted | yes | Error: must specify container_id or image:tag |

### `docker container start` → `udocker container start` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-a, --attach` | — | да | 🔷 ignored | no | Error: must specify a container |
| `--checkpoint` | string | да | ⛔ root-only | no | Error: --checkpoint: checkpointing needs CRIU and root |
| `--checkpoint-dir` | string | да | ⛔ root-only | no | Error: --checkpoint-dir: checkpointing needs CRIU and root |
| `--detach-keys` | string | да | 🔷 ignored | no | Error: container not found: nosuchct |
| `-i, --interactive` | — | да | 🔷 ignored | no | Error: container not found: nosuchct |

### `docker container stats` → `udocker container stats` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-a, --all` | — | да | 🔶 accepted | yes | Error: container not found: nosuchct |
| `--format` | string | да | 🔶 accepted | yes | Error: container not found: nosuchct |
| `--no-stream` | — | да | 🔶 accepted | yes | Error: container not found: nosuchct |
| `--no-trunc` | — | да | 🔷 ignored | yes | Error: container not found: nosuchct |

### `docker container stop` → `udocker container stop` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-s, --signal` | string | да | 🔶 accepted | no | Error: container not found: nosuchct |
| `-t, --timeout` | int | да | 🔶 accepted | no | Error: container not found: nosuchct |

### `docker container update` → `udocker container update` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--blkio-weight` | uint16 | да | ⛔ root-only | no | Error: --blkio-weight: resource limits need cgroup delegation |
| `--cpu-period` | int | да | ⛔ root-only | no | Error: --cpu-period: CPU limits need cgroup delegation |
| `--cpu-quota` | int | да | ⛔ root-only | no | Error: --cpu-quota: CPU limits need cgroup delegation |
| `--cpu-rt-period` | int | да | ⛔ root-only | no | Error: --cpu-rt-period: CPU limits need cgroup delegation |
| `--cpu-rt-runtime` | int | да | ⛔ root-only | no | Error: --cpu-rt-runtime: CPU limits need cgroup delegation |
| `-c, --cpu-shares` | int | да | ⛔ root-only | no | Error: --cpu-shares: CPU limits need cgroup delegation |
| `--cpus` | decimal | да | ⛔ root-only | no | Error: --cpus: CPU limits need cgroup delegation |
| `--cpuset-cpus` | string | да | ⛔ root-only | no | Error: update requires cgroup delegation and is not available without root/daemon |
| `--cpuset-mems` | string | да | ⛔ root-only | no | Error: --cpuset-mems: CPU limits need cgroup delegation |
| `-m, --memory` | bytes | да | ⛔ root-only | no | Error: --memory: resource limits need cgroup delegation |
| `--memory-reservation` | bytes | да | ⛔ root-only | no | Error: --memory-reservation: resource limits need cgroup delegation |
| `--memory-swap` | bytes | да | ⛔ root-only | no | Error: --memory-swap: resource limits need cgroup delegation |
| `--pids-limit` | int | да | ⛔ root-only | no | Error: --pids-limit: resource limits need cgroup delegation |
| `--restart` | string | да | ⛔ root-only | no | Error: update requires cgroup delegation and is not available without root/daemon |

### `docker context create` → `udocker context create` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--description` | string | да | ➖ excluded | no | вне scope контракта |
| `--docker` | stringToString | да | ➖ excluded | no | вне scope контракта |
| `--from` | string | да | ➖ excluded | no | вне scope контракта |

### `docker context inspect` → `udocker context inspect` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --format` | string | да | ➖ excluded | no | вне scope контракта |

### `docker context ls` → `udocker context ls` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--format` | string | да | ➖ excluded | no | вне scope контракта |
| `-q, --quiet` | — | да | ➖ excluded | no | вне scope контракта |

### `docker context rm` → `udocker context rm` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --force` | — | да | ➖ excluded | no | вне scope контракта |

### `docker context update` → `udocker context update` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--description` | string | да | ➖ excluded | no | вне scope контракта |
| `--docker` | stringToString | да | ➖ excluded | no | вне scope контракта |

### `docker image build` → `udocker image build` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--add-host` | list | да | 🔷 ignored | no | Error: build context directory not found: /nonexistent-context |
| `--build-arg` | list | да | 🔶 accepted | yes | Error: build context directory not found: /nonexistent-context |
| `--cache-from` | strings | да | 🔷 ignored | no | Error: build context directory not found: /nonexistent-context |
| `--cgroup-parent` | string | да | 🔷 ignored | no | Error: build context directory not found: /nonexistent-context |
| `--compress` | — | да | 🔷 ignored | no | Error: build context directory not found: /nonexistent-context |
| `--cpu-period` | int | да | ⛔ root-only | no | Error: --cpu-period: CPU limits need cgroup delegation |
| `--cpu-quota` | int | да | ⛔ root-only | no | Error: --cpu-quota: CPU limits need cgroup delegation |
| `-c, --cpu-shares` | int | да | ⛔ root-only | no | Error: --cpu-shares: CPU limits need cgroup delegation |
| `--cpuset-cpus` | string | да | 🔷 ignored | no | Error: build context directory not found: /nonexistent-context |
| `--cpuset-mems` | string | да | ⛔ root-only | no | Error: --cpuset-mems: CPU limits need cgroup delegation |
| `-f, --file` | string | да | 🔶 accepted | yes | Error: build context directory not found: /nonexistent-context |
| `--force-rm` | — | да | 🔷 ignored | no | Error: build context directory not found: /nonexistent-context |
| `--iidfile` | string | да | 🔷 ignored | no | Error: build context directory not found: /nonexistent-context |
| `--isolation` | string | да | 🔷 ignored | no | Error: build context directory not found: /nonexistent-context |
| `--label` | list | да | 🔶 accepted | no | Error: build context directory not found: /nonexistent-context |
| `-m, --memory` | bytes | да | ⛔ root-only | no | Error: --memory: resource limits need cgroup delegation |
| `--memory-swap` | bytes | да | ⛔ root-only | no | Error: --memory-swap: resource limits need cgroup delegation |
| `--network` | string | да | 🔷 ignored | no | Error: build context directory not found: /nonexistent-context |
| `--no-cache` | — | да | 🔶 accepted | no | Error: build context directory not found: /nonexistent-context |
| `--platform` | string | да | 🔶 accepted | yes | Error: build context directory not found: /nonexistent-context |
| `--pull` | — | да | 🔶 accepted | no | Error: build context directory not found: /nonexistent-context |
| `-q, --quiet` | — | да | 🔷 ignored | no | Error: build context directory not found: /nonexistent-context |
| `--rm` | — | да | 🔷 ignored | no | Error: build context directory not found: /nonexistent-context |
| `--security-opt` | strings | да | 🔷 ignored | no | Error: build context directory not found: /nonexistent-context |
| `--shm-size` | bytes | да | 🔷 ignored | no | Error: build context directory not found: /nonexistent-context |
| `--squash` | — | да | 🔷 ignored | no | Error: build context directory not found: /nonexistent-context |
| `-t, --tag` | list | да | 🔶 accepted | yes | Error: build context directory not found: /nonexistent-context |
| `--target` | string | да | 🔶 accepted | no | Error: build context directory not found: /nonexistent-context |
| `--ulimit` | ulimit | да | 🔷 ignored | no | Error: build context directory not found: /nonexistent-context |

### `docker image history` → `udocker image history` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--format` | string | да | 🔶 accepted | no | Error: image not found: nosuchimg |
| `-H, --human` | — | да | 🔶 accepted | no | Error: image not found: nosuchimg |
| `--no-trunc` | — | да | 🔶 accepted | yes | Error: image not found: nosuchimg |
| `--platform` | string | да | 🔶 accepted | no | Error: image not found: nosuchimg |
| `-q, --quiet` | — | да | 🔶 accepted | no | Error: image not found: nosuchimg |

### `docker image import` → `udocker image import` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-c, --change` | list | да | 🔶 accepted | no | Error: must specify tar filename |
| `-m, --message` | string | да | 🔶 accepted | no | Error: must specify tar filename |
| `--platform` | string | да | 🔶 accepted | yes | Error: must specify tar filename |

### `docker image inspect` → `udocker image inspect` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --format` | string | да | 🔶 accepted | yes | Error: no such object: nosuchobj |
| `--platform` | string | да | 🔶 accepted | no | Error: no such object: nosuchobj |

### `docker image load` → `udocker image load` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-i, --input` | string | да | 🔶 accepted | yes | Error: image file does not exist: x |
| `--platform` | strings | да | 🔶 accepted | no | Error: failed to extract container: - |
| `-q, --quiet` | — | да | 🔷 ignored | no | Error: failed to extract container: - |

### `docker image ls` → `udocker image ls` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-a, --all` | — | да | ✅ ok | yes | REPOSITORY                     TAG                  IMAGE ID     CREATED              SIZE |
| `--digests` | — | да | 🔷 ignored | no | REPOSITORY                     TAG                  IMAGE ID     CREATED              SIZE |
| `-f, --filter` | filter | да | ✅ ok | no | REPOSITORY                     TAG                  IMAGE ID     CREATED              SIZE |
| `--format` | string | да | ✅ ok | yes |  |
| `--no-trunc` | — | да | ✅ ok | yes | REPOSITORY                     TAG                  IMAGE ID     CREATED              SIZE |
| `-q, --quiet` | — | да | ✅ ok | yes |  |
| `--tree` | — | да | 🔷 ignored | no | REPOSITORY                     TAG                  IMAGE ID     CREATED              SIZE |

### `docker image prune` → `udocker image prune` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-a, --all` | — | да | 🔶 accepted | no | Error: prune requires -f when stdin is not a terminal (use -f) |
| `--filter` | filter | да | 🔷 ignored | no | Error: prune requires -f when stdin is not a terminal (use -f) |
| `-f, --force` | — | да | ✅ ok | no | Total reclaimed space: 0B |

### `docker image pull` → `udocker image pull` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-a, --all-tags` | — | да | 🔶 accepted | no | Error: must specify image:tag or repository/image:tag |
| `--platform` | string | да | 🔶 accepted | yes | Error: must specify image:tag or repository/image:tag |
| `-q, --quiet` | — | да | 🔷 ignored | no | Error: must specify image:tag or repository/image:tag |

### `docker image push` → `udocker image push` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-a, --all-tags` | — | да | ⛔ root-only | no | Error: push --all-tags is not available rootless |
| `--platform` | string | да | 🔶 accepted | no | Error: image not found: nosuchimg:zzz |
| `-q, --quiet` | — | да | 🔷 ignored | no | Error: image not found: nosuchimg:zzz |

### `docker image rm` → `udocker image rm` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --force` | — | да | 🔶 accepted | yes | Error: deleting image |
| `--no-prune` | — | да | 🔶 accepted | yes | Error: deleting image |
| `--platform` | strings | да | 🔶 accepted | no | Error: deleting image |

### `docker image save` → `udocker image save` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-o, --output` | string | да | 🔶 accepted | yes | Error: save image failed: nosuchimg:latest |
| `--platform` | strings | да | 🔶 accepted | no | Error: save image failed: nosuchimg:latest |

### `docker manifest annotate` → `udocker manifest annotate` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--arch` | string | да | ➖ excluded | no | вне scope контракта |
| `--os` | string | да | ➖ excluded | no | вне scope контракта |
| `--os-features` | strings | да | ➖ excluded | no | вне scope контракта |
| `--os-version` | string | да | ➖ excluded | no | вне scope контракта |
| `--variant` | string | да | ➖ excluded | no | вне scope контракта |

### `docker manifest create` → `udocker manifest create` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-a, --amend` | — | да | ➖ excluded | no | вне scope контракта |
| `--insecure` | — | да | ➖ excluded | no | вне scope контракта |

### `docker manifest inspect` → `udocker manifest inspect` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--insecure` | — | да | ➖ excluded | no | вне scope контракта |
| `-v, --verbose` | — | да | ➖ excluded | no | вне scope контракта |

### `docker manifest push` → `udocker manifest push` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--insecure` | — | да | ➖ excluded | no | вне scope контракта |
| `-p, --purge` | — | да | ➖ excluded | no | вне scope контракта |

### `docker network connect` → `udocker network connect` 🔶

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--alias` | strings | да | ⛔ root-only | no | Error: network connect is not available without root/daemon; udocker uses the host network stack |
| `--driver-opt` | strings | да | ⛔ root-only | no | Error: network connect is not available without root/daemon; udocker uses the host network stack |
| `--gw-priority` | int | да | ⛔ root-only | no | Error: network connect is not available without root/daemon; udocker uses the host network stack |
| `--ip` | ip | да | ⛔ root-only | no | Error: --ip: container networking is host-only |
| `--ip6` | ip | да | ⛔ root-only | no | Error: --ip6: container networking is host-only |
| `--link` | list | да | ⛔ root-only | no | Error: --link: container networking is host-only |
| `--link-local-ip` | ipSlice | да | ⛔ root-only | no | Error: --link-local-ip: container networking is host-only |

### `docker network create` → `udocker network create` 🔶

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--attachable` | — | да | ⛔ root-only | no | Error: network create is not available without root/daemon; udocker uses the host network stack |
| `--aux-address` | map | да | ⛔ root-only | no | Error: network create is not available without root/daemon; udocker uses the host network stack |
| `--config-from` | string | да | ⛔ root-only | no | Error: network create is not available without root/daemon; udocker uses the host network stack |
| `--config-only` | — | да | ⛔ root-only | no | Error: network create is not available without root/daemon; udocker uses the host network stack |
| `-d, --driver` | string | да | ⛔ root-only | no | Error: network create is not available without root/daemon; udocker uses the host network stack |
| `--gateway` | ipSlice | да | ⛔ root-only | no | Error: network create is not available without root/daemon; udocker uses the host network stack |
| `--ingress` | — | да | ⛔ root-only | no | Error: network create is not available without root/daemon; udocker uses the host network stack |
| `--internal` | — | да | ⛔ root-only | no | Error: network create is not available without root/daemon; udocker uses the host network stack |
| `--ip-range` | ipNetSlice | да | ⛔ root-only | no | Error: network create is not available without root/daemon; udocker uses the host network stack |
| `--ipam-driver` | string | да | ⛔ root-only | no | Error: network create is not available without root/daemon; udocker uses the host network stack |
| `--ipam-opt` | map | да | ⛔ root-only | no | Error: network create is not available without root/daemon; udocker uses the host network stack |
| `--ipv4` | — | да | ⛔ root-only | no | Error: network create is not available without root/daemon; udocker uses the host network stack |
| `--ipv6` | — | да | ⛔ root-only | no | Error: network create is not available without root/daemon; udocker uses the host network stack |
| `--label` | list | да | ⛔ root-only | no | Error: network create is not available without root/daemon; udocker uses the host network stack |
| `-o, --opt` | map | да | ⛔ root-only | no | Error: network create is not available without root/daemon; udocker uses the host network stack |
| `--scope` | string | да | ⛔ root-only | no | Error: network create is not available without root/daemon; udocker uses the host network stack |
| `--subnet` | strings | да | ⛔ root-only | no | Error: network create is not available without root/daemon; udocker uses the host network stack |

### `docker network disconnect` → `udocker network disconnect` 🔶

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --force` | — | да | ⛔ root-only | no | Error: network disconnect is not available without root/daemon; udocker uses the host network stack |

### `docker network inspect` → `udocker network inspect` 🔶

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --format` | string | да | 🔶 accepted | no | Error: no such network: nosuchnet |
| `-v, --verbose` | — | да | 🔶 accepted | no | Error: no such network: nosuchnet |

### `docker network ls` → `udocker network ls` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --filter` | filter | да | ✅ ok | no | NETWORK ID     NAME       DRIVER     SCOPE |
| `--format` | string | да | ✅ ok | no | {"Attachable": false, "ConfigFrom": {"Network": ""}, "ConfigOnly": false, "Containers": {}, "Created": "", "Driver": "host", "EnableIPv6": false, "IPAM": {"Conf |
| `--no-trunc` | — | да | ✅ ok | no | NETWORK ID     NAME       DRIVER     SCOPE |
| `-q, --quiet` | — | да | ✅ ok | no | NETWORK ID     NAME       DRIVER     SCOPE |

### `docker network prune` → `udocker network prune` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--filter` | filter | да | 🔷 ignored | no | WARNING! This will remove all networks not used by containers. |
| `-f, --force` | — | да | ✅ ok | no |  |

### `docker network rm` → `udocker network rm` 🔶

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --force` | — | да | ⛔ root-only | no | Error: network rm is not available without root/daemon; udocker uses the host network stack |

### `docker node inspect` → `udocker node inspect` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --format` | string | да | ➖ excluded | no | вне scope контракта |
| `--pretty` | — | да | ➖ excluded | no | вне scope контракта |

### `docker node ls` → `udocker node ls` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --filter` | filter | да | ➖ excluded | no | вне scope контракта |
| `--format` | string | да | ➖ excluded | no | вне scope контракта |
| `-q, --quiet` | — | да | ➖ excluded | no | вне scope контракта |

### `docker node ps` → `udocker node ps` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --filter` | filter | да | ➖ excluded | no | вне scope контракта |
| `--format` | string | да | ➖ excluded | no | вне scope контракта |
| `--no-resolve` | — | да | ➖ excluded | no | вне scope контракта |
| `--no-trunc` | — | да | ➖ excluded | no | вне scope контракта |
| `-q, --quiet` | — | да | ➖ excluded | no | вне scope контракта |

### `docker node rm` → `udocker node rm` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --force` | — | да | ➖ excluded | no | вне scope контракта |

### `docker node update` → `udocker node update` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--availability` | string | да | ➖ excluded | no | вне scope контракта |
| `--label-add` | list | да | ➖ excluded | no | вне scope контракта |
| `--label-rm` | list | да | ➖ excluded | no | вне scope контракта |
| `--role` | string | да | ➖ excluded | no | вне scope контракта |

### `docker plugin create` → `udocker plugin create` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--compress` | — | да | ➖ excluded | no | вне scope контракта |

### `docker plugin disable` → `udocker plugin disable` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --force` | — | да | ➖ excluded | no | вне scope контракта |

### `docker plugin enable` → `udocker plugin enable` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--timeout` | int | да | ➖ excluded | no | вне scope контракта |

### `docker plugin inspect` → `udocker plugin inspect` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --format` | string | да | ➖ excluded | no | вне scope контракта |

### `docker plugin install` → `udocker plugin install` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--alias` | string | да | ➖ excluded | no | вне scope контракта |
| `--disable` | — | да | ➖ excluded | no | вне scope контракта |
| `--grant-all-permissions` | — | да | ➖ excluded | no | вне scope контракта |

### `docker plugin ls` → `udocker plugin ls` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --filter` | filter | да | ➖ excluded | no | вне scope контракта |
| `--format` | string | да | ➖ excluded | no | вне scope контракта |
| `--no-trunc` | — | да | ➖ excluded | no | вне scope контракта |
| `-q, --quiet` | — | да | ➖ excluded | no | вне scope контракта |

### `docker plugin rm` → `udocker plugin rm` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --force` | — | да | ➖ excluded | no | вне scope контракта |

### `docker plugin upgrade` → `udocker plugin upgrade` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--grant-all-permissions` | — | да | ➖ excluded | no | вне scope контракта |
| `--skip-remote-check` | — | да | ➖ excluded | no | вне scope контракта |

### `docker secret create` → `udocker secret create` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-d, --driver` | string | да | ➖ excluded | no | вне scope контракта |
| `-l, --label` | list | да | ➖ excluded | no | вне scope контракта |
| `--template-driver` | string | да | ➖ excluded | no | вне scope контракта |

### `docker secret inspect` → `udocker secret inspect` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --format` | string | да | ➖ excluded | no | вне scope контракта |
| `--pretty` | — | да | ➖ excluded | no | вне scope контракта |

### `docker secret ls` → `udocker secret ls` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --filter` | filter | да | ➖ excluded | no | вне scope контракта |
| `--format` | string | да | ➖ excluded | no | вне scope контракта |
| `-q, --quiet` | — | да | ➖ excluded | no | вне scope контракта |

### `docker service create` → `udocker service create` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--cap-add` | list | да | ➖ excluded | no | вне scope контракта |
| `--cap-drop` | list | да | ➖ excluded | no | вне scope контракта |
| `--config` | config | да | ➖ excluded | no | вне scope контракта |
| `--constraint` | list | да | ➖ excluded | no | вне scope контракта |
| `--container-label` | list | да | ➖ excluded | no | вне scope контракта |
| `-d, --detach` | — | да | ➖ excluded | no | вне scope контракта |
| `--dns` | list | да | ➖ excluded | no | вне scope контракта |
| `--dns-option` | list | да | ➖ excluded | no | вне scope контракта |
| `--dns-search` | list | да | ➖ excluded | no | вне scope контракта |
| `--endpoint-mode` | string | да | ➖ excluded | no | вне scope контракта |
| `--entrypoint` | command | да | ➖ excluded | no | вне scope контракта |
| `-e, --env` | list | да | ➖ excluded | no | вне scope контракта |
| `--env-file` | list | да | ➖ excluded | no | вне scope контракта |
| `--generic-resource` | list | да | ➖ excluded | no | вне scope контракта |
| `--group` | list | да | ➖ excluded | no | вне scope контракта |
| `--health-cmd` | string | да | ➖ excluded | no | вне scope контракта |
| `--health-interval` | duration | да | ➖ excluded | no | вне scope контракта |
| `--health-retries` | int | да | ➖ excluded | no | вне scope контракта |
| `--health-start-interval` | duration | да | ➖ excluded | no | вне scope контракта |
| `--health-start-period` | duration | да | ➖ excluded | no | вне scope контракта |
| `--health-timeout` | duration | да | ➖ excluded | no | вне scope контракта |
| `--host` | list | да | ➖ excluded | no | вне scope контракта |
| `--hostname` | string | да | ➖ excluded | no | вне scope контракта |
| `--init` | — | да | ➖ excluded | no | вне scope контракта |
| `--isolation` | string | да | ➖ excluded | no | вне scope контракта |
| `-l, --label` | list | да | ➖ excluded | no | вне scope контракта |
| `--limit-cpu` | decimal | да | ➖ excluded | no | вне scope контракта |
| `--limit-memory` | bytes | да | ➖ excluded | no | вне scope контракта |
| `--limit-pids` | int | да | ➖ excluded | no | вне scope контракта |
| `--log-driver` | string | да | ➖ excluded | no | вне scope контракта |
| `--log-opt` | list | да | ➖ excluded | no | вне scope контракта |
| `--max-concurrent` | uint | да | ➖ excluded | no | вне scope контракта |
| `--memory-swap` | bytes | да | ➖ excluded | no | вне scope контракта |
| `--memory-swappiness` | int | да | ➖ excluded | no | вне scope контракта |
| `--mode` | string | да | ➖ excluded | no | вне scope контракта |
| `--mount` | mount | да | ➖ excluded | no | вне scope контракта |
| `--name` | string | да | ➖ excluded | no | вне scope контракта |
| `--network` | network | да | ➖ excluded | no | вне scope контракта |
| `--no-healthcheck` | — | да | ➖ excluded | no | вне scope контракта |
| `--no-resolve-image` | — | да | ➖ excluded | no | вне scope контракта |
| `--oom-score-adj` | int | да | ➖ excluded | no | вне scope контракта |
| `--placement-pref` | pref | да | ➖ excluded | no | вне scope контракта |
| `-p, --publish` | port | да | ➖ excluded | no | вне scope контракта |
| `-q, --quiet` | — | да | ➖ excluded | no | вне scope контракта |
| `--read-only` | — | да | ➖ excluded | no | вне scope контракта |
| `--replicas` | uint | да | ➖ excluded | no | вне scope контракта |
| `--replicas-max-per-node` | uint | да | ➖ excluded | no | вне scope контракта |
| `--reserve-cpu` | decimal | да | ➖ excluded | no | вне scope контракта |
| `--reserve-memory` | bytes | да | ➖ excluded | no | вне scope контракта |
| `--restart-condition` | string | да | ➖ excluded | no | вне scope контракта |
| `--restart-delay` | duration | да | ➖ excluded | no | вне scope контракта |
| `--restart-max-attempts` | uint | да | ➖ excluded | no | вне scope контракта |
| `--restart-window` | duration | да | ➖ excluded | no | вне scope контракта |
| `--rollback-delay` | duration | да | ➖ excluded | no | вне scope контракта |
| `--rollback-failure-action` | string | да | ➖ excluded | no | вне scope контракта |
| `--rollback-max-failure-ratio` | float | да | ➖ excluded | no | вне scope контракта |
| `--rollback-monitor` | duration | да | ➖ excluded | no | вне scope контракта |
| `--rollback-order` | string | да | ➖ excluded | no | вне scope контракта |
| `--rollback-parallelism` | uint | да | ➖ excluded | no | вне scope контракта |
| `--secret` | secret | да | ➖ excluded | no | вне scope контракта |
| `--stop-grace-period` | duration | да | ➖ excluded | no | вне scope контракта |
| `--stop-signal` | string | да | ➖ excluded | no | вне scope контракта |
| `--sysctl` | list | да | ➖ excluded | no | вне scope контракта |
| `-t, --tty` | — | да | ➖ excluded | no | вне scope контракта |
| `--ulimit` | ulimit | да | ➖ excluded | no | вне scope контракта |
| `--update-delay` | duration | да | ➖ excluded | no | вне scope контракта |
| `--update-failure-action` | string | да | ➖ excluded | no | вне scope контракта |
| `--update-max-failure-ratio` | float | да | ➖ excluded | no | вне scope контракта |
| `--update-monitor` | duration | да | ➖ excluded | no | вне scope контракта |
| `--update-order` | string | да | ➖ excluded | no | вне scope контракта |
| `--update-parallelism` | uint | да | ➖ excluded | no | вне scope контракта |
| `-u, --user` | string | да | ➖ excluded | no | вне scope контракта |
| `--with-registry-auth` | — | да | ➖ excluded | no | вне scope контракта |
| `-w, --workdir` | string | да | ➖ excluded | no | вне scope контракта |

### `docker service inspect` → `udocker service inspect` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --format` | string | да | ➖ excluded | no | вне scope контракта |
| `--pretty` | — | да | ➖ excluded | no | вне scope контракта |

### `docker service logs` → `udocker service logs` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--details` | — | да | ➖ excluded | no | вне scope контракта |
| `-f, --follow` | — | да | ➖ excluded | no | вне scope контракта |
| `--no-resolve` | — | да | ➖ excluded | no | вне scope контракта |
| `--no-task-ids` | — | да | ➖ excluded | no | вне scope контракта |
| `--no-trunc` | — | да | ➖ excluded | no | вне scope контракта |
| `--raw` | — | да | ➖ excluded | no | вне scope контракта |
| `--since` | string | да | ➖ excluded | no | вне scope контракта |
| `-n, --tail` | string | да | ➖ excluded | no | вне scope контракта |
| `-t, --timestamps` | — | да | ➖ excluded | no | вне scope контракта |

### `docker service ls` → `udocker service ls` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --filter` | filter | да | ➖ excluded | no | вне scope контракта |
| `--format` | string | да | ➖ excluded | no | вне scope контракта |
| `-q, --quiet` | — | да | ➖ excluded | no | вне scope контракта |

### `docker service ps` → `udocker service ps` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --filter` | filter | да | ➖ excluded | no | вне scope контракта |
| `--format` | string | да | ➖ excluded | no | вне scope контракта |
| `--no-resolve` | — | да | ➖ excluded | no | вне scope контракта |
| `--no-trunc` | — | да | ➖ excluded | no | вне scope контракта |
| `-q, --quiet` | — | да | ➖ excluded | no | вне scope контракта |

### `docker service rollback` → `udocker service rollback` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-d, --detach` | — | да | ➖ excluded | no | вне scope контракта |
| `-q, --quiet` | — | да | ➖ excluded | no | вне scope контракта |

### `docker service scale` → `udocker service scale` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-d, --detach` | — | да | ➖ excluded | no | вне scope контракта |

### `docker service update` → `udocker service update` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--args` | command | да | ➖ excluded | no | вне scope контракта |
| `--cap-add` | list | да | ➖ excluded | no | вне scope контракта |
| `--cap-drop` | list | да | ➖ excluded | no | вне scope контракта |
| `--config-add` | config | да | ➖ excluded | no | вне scope контракта |
| `--config-rm` | list | да | ➖ excluded | no | вне scope контракта |
| `--constraint-add` | list | да | ➖ excluded | no | вне scope контракта |
| `--constraint-rm` | list | да | ➖ excluded | no | вне scope контракта |
| `--container-label-add` | list | да | ➖ excluded | no | вне scope контракта |
| `--container-label-rm` | list | да | ➖ excluded | no | вне scope контракта |
| `-d, --detach` | — | да | ➖ excluded | no | вне scope контракта |
| `--dns-add` | list | да | ➖ excluded | no | вне scope контракта |
| `--dns-option-add` | list | да | ➖ excluded | no | вне scope контракта |
| `--dns-option-rm` | list | да | ➖ excluded | no | вне scope контракта |
| `--dns-rm` | list | да | ➖ excluded | no | вне scope контракта |
| `--dns-search-add` | list | да | ➖ excluded | no | вне scope контракта |
| `--dns-search-rm` | list | да | ➖ excluded | no | вне scope контракта |
| `--endpoint-mode` | string | да | ➖ excluded | no | вне scope контракта |
| `--entrypoint` | command | да | ➖ excluded | no | вне scope контракта |
| `--env-add` | list | да | ➖ excluded | no | вне scope контракта |
| `--env-rm` | list | да | ➖ excluded | no | вне scope контракта |
| `--force` | — | да | ➖ excluded | no | вне scope контракта |
| `--generic-resource-add` | list | да | ➖ excluded | no | вне scope контракта |
| `--generic-resource-rm` | list | да | ➖ excluded | no | вне scope контракта |
| `--group-add` | list | да | ➖ excluded | no | вне scope контракта |
| `--group-rm` | list | да | ➖ excluded | no | вне scope контракта |
| `--health-cmd` | string | да | ➖ excluded | no | вне scope контракта |
| `--health-interval` | duration | да | ➖ excluded | no | вне scope контракта |
| `--health-retries` | int | да | ➖ excluded | no | вне scope контракта |
| `--health-start-interval` | duration | да | ➖ excluded | no | вне scope контракта |
| `--health-start-period` | duration | да | ➖ excluded | no | вне scope контракта |
| `--health-timeout` | duration | да | ➖ excluded | no | вне scope контракта |
| `--host-add` | list | да | ➖ excluded | no | вне scope контракта |
| `--host-rm` | list | да | ➖ excluded | no | вне scope контракта |
| `--hostname` | string | да | ➖ excluded | no | вне scope контракта |
| `--image` | string | да | ➖ excluded | no | вне scope контракта |
| `--init` | — | да | ➖ excluded | no | вне scope контракта |
| `--isolation` | string | да | ➖ excluded | no | вне scope контракта |
| `--label-add` | list | да | ➖ excluded | no | вне scope контракта |
| `--label-rm` | list | да | ➖ excluded | no | вне scope контракта |
| `--limit-cpu` | decimal | да | ➖ excluded | no | вне scope контракта |
| `--limit-memory` | bytes | да | ➖ excluded | no | вне scope контракта |
| `--limit-pids` | int | да | ➖ excluded | no | вне scope контракта |
| `--log-driver` | string | да | ➖ excluded | no | вне scope контракта |
| `--log-opt` | list | да | ➖ excluded | no | вне scope контракта |
| `--max-concurrent` | uint | да | ➖ excluded | no | вне scope контракта |
| `--memory-swap` | bytes | да | ➖ excluded | no | вне scope контракта |
| `--memory-swappiness` | int | да | ➖ excluded | no | вне scope контракта |
| `--mount-add` | mount | да | ➖ excluded | no | вне scope контракта |
| `--mount-rm` | list | да | ➖ excluded | no | вне scope контракта |
| `--network-add` | network | да | ➖ excluded | no | вне scope контракта |
| `--network-rm` | list | да | ➖ excluded | no | вне scope контракта |
| `--no-healthcheck` | — | да | ➖ excluded | no | вне scope контракта |
| `--no-resolve-image` | — | да | ➖ excluded | no | вне scope контракта |
| `--oom-score-adj` | int | да | ➖ excluded | no | вне scope контракта |
| `--placement-pref-add` | pref | да | ➖ excluded | no | вне scope контракта |
| `--placement-pref-rm` | pref | да | ➖ excluded | no | вне scope контракта |
| `--publish-add` | port | да | ➖ excluded | no | вне scope контракта |
| `--publish-rm` | port | да | ➖ excluded | no | вне scope контракта |
| `-q, --quiet` | — | да | ➖ excluded | no | вне scope контракта |
| `--read-only` | — | да | ➖ excluded | no | вне scope контракта |
| `--replicas` | uint | да | ➖ excluded | no | вне scope контракта |
| `--replicas-max-per-node` | uint | да | ➖ excluded | no | вне scope контракта |
| `--reserve-cpu` | decimal | да | ➖ excluded | no | вне scope контракта |
| `--reserve-memory` | bytes | да | ➖ excluded | no | вне scope контракта |
| `--restart-condition` | string | да | ➖ excluded | no | вне scope контракта |
| `--restart-delay` | duration | да | ➖ excluded | no | вне scope контракта |
| `--restart-max-attempts` | uint | да | ➖ excluded | no | вне scope контракта |
| `--restart-window` | duration | да | ➖ excluded | no | вне scope контракта |
| `--rollback` | — | да | ➖ excluded | no | вне scope контракта |
| `--rollback-delay` | duration | да | ➖ excluded | no | вне scope контракта |
| `--rollback-failure-action` | string | да | ➖ excluded | no | вне scope контракта |
| `--rollback-max-failure-ratio` | float | да | ➖ excluded | no | вне scope контракта |
| `--rollback-monitor` | duration | да | ➖ excluded | no | вне scope контракта |
| `--rollback-order` | string | да | ➖ excluded | no | вне scope контракта |
| `--rollback-parallelism` | uint | да | ➖ excluded | no | вне scope контракта |
| `--secret-add` | secret | да | ➖ excluded | no | вне scope контракта |
| `--secret-rm` | list | да | ➖ excluded | no | вне scope контракта |
| `--stop-grace-period` | duration | да | ➖ excluded | no | вне scope контракта |
| `--stop-signal` | string | да | ➖ excluded | no | вне scope контракта |
| `--sysctl-add` | list | да | ➖ excluded | no | вне scope контракта |
| `--sysctl-rm` | list | да | ➖ excluded | no | вне scope контракта |
| `-t, --tty` | — | да | ➖ excluded | no | вне scope контракта |
| `--ulimit-add` | ulimit | да | ➖ excluded | no | вне scope контракта |
| `--ulimit-rm` | list | да | ➖ excluded | no | вне scope контракта |
| `--update-delay` | duration | да | ➖ excluded | no | вне scope контракта |
| `--update-failure-action` | string | да | ➖ excluded | no | вне scope контракта |
| `--update-max-failure-ratio` | float | да | ➖ excluded | no | вне scope контракта |
| `--update-monitor` | duration | да | ➖ excluded | no | вне scope контракта |
| `--update-order` | string | да | ➖ excluded | no | вне scope контракта |
| `--update-parallelism` | uint | да | ➖ excluded | no | вне scope контракта |
| `-u, --user` | string | да | ➖ excluded | no | вне scope контракта |
| `--with-registry-auth` | — | да | ➖ excluded | no | вне scope контракта |
| `-w, --workdir` | string | да | ➖ excluded | no | вне scope контракта |

### `docker stack config` → `udocker stack config` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-c, --compose-file` | strings | да | ➖ excluded | no | вне scope контракта |
| `--skip-interpolation` | — | да | ➖ excluded | no | вне scope контракта |

### `docker stack deploy` → `udocker stack deploy` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-c, --compose-file` | strings | да | ➖ excluded | no | вне scope контракта |
| `-d, --detach` | — | да | ➖ excluded | no | вне scope контракта |
| `--prune` | — | да | ➖ excluded | no | вне scope контракта |
| `-q, --quiet` | — | да | ➖ excluded | no | вне scope контракта |
| `--resolve-image` | string | да | ➖ excluded | no | вне scope контракта |
| `--with-registry-auth` | — | да | ➖ excluded | no | вне scope контракта |

### `docker stack ls` → `udocker stack ls` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--format` | string | да | ➖ excluded | no | вне scope контракта |

### `docker stack ps` → `udocker stack ps` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --filter` | filter | да | ➖ excluded | no | вне scope контракта |
| `--format` | string | да | ➖ excluded | no | вне scope контракта |
| `--no-resolve` | — | да | ➖ excluded | no | вне scope контракта |
| `--no-trunc` | — | да | ➖ excluded | no | вне scope контракта |
| `-q, --quiet` | — | да | ➖ excluded | no | вне scope контракта |

### `docker stack rm` → `udocker stack rm` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-d, --detach` | — | да | ➖ excluded | no | вне scope контракта |

### `docker stack services` → `udocker stack services` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --filter` | filter | да | ➖ excluded | no | вне scope контракта |
| `--format` | string | да | ➖ excluded | no | вне scope контракта |
| `-q, --quiet` | — | да | ➖ excluded | no | вне scope контракта |

### `docker swarm ca` → `udocker swarm ca` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--cert-expiry` | duration | да | ➖ excluded | no | вне scope контракта |
| `-d, --detach` | — | да | ➖ excluded | no | вне scope контракта |
| `-q, --quiet` | — | да | ➖ excluded | no | вне scope контракта |
| `--rotate` | — | да | ➖ excluded | no | вне scope контракта |

### `docker swarm init` → `udocker swarm init` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--advertise-addr` | string | да | ➖ excluded | no | вне scope контракта |
| `--autolock` | — | да | ➖ excluded | no | вне scope контракта |
| `--availability` | string | да | ➖ excluded | no | вне scope контракта |
| `--cert-expiry` | duration | да | ➖ excluded | no | вне scope контракта |
| `--data-path-addr` | string | да | ➖ excluded | no | вне scope контракта |
| `--data-path-port` | uint32 | да | ➖ excluded | no | вне scope контракта |
| `--default-addr-pool` | ipNetSlice | да | ➖ excluded | no | вне scope контракта |
| `--default-addr-pool-mask-length` | uint32 | да | ➖ excluded | no | вне scope контракта |
| `--dispatcher-heartbeat` | duration | да | ➖ excluded | no | вне scope контракта |
| `--force-new-cluster` | — | да | ➖ excluded | no | вне scope контракта |
| `--max-snapshots` | uint | да | ➖ excluded | no | вне scope контракта |
| `--snapshot-interval` | uint | да | ➖ excluded | no | вне scope контракта |
| `--task-history-limit` | int | да | ➖ excluded | no | вне scope контракта |

### `docker swarm join` → `udocker swarm join` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--advertise-addr` | string | да | ➖ excluded | no | вне scope контракта |
| `--availability` | string | да | ➖ excluded | no | вне scope контракта |
| `--data-path-addr` | string | да | ➖ excluded | no | вне scope контракта |
| `--token` | string | да | ➖ excluded | no | вне scope контракта |

### `docker swarm join-token` → `udocker swarm join-token` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-q, --quiet` | — | да | ➖ excluded | no | вне scope контракта |
| `--rotate` | — | да | ➖ excluded | no | вне scope контракта |

### `docker swarm leave` → `udocker swarm leave` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --force` | — | да | ➖ excluded | no | вне scope контракта |

### `docker swarm unlock-key` → `udocker swarm unlock-key` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-q, --quiet` | — | да | ➖ excluded | no | вне scope контракта |
| `--rotate` | — | да | ➖ excluded | no | вне scope контракта |

### `docker swarm update` → `udocker swarm update` ➖

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--autolock` | — | да | ➖ excluded | no | вне scope контракта |
| `--cert-expiry` | duration | да | ➖ excluded | no | вне scope контракта |
| `--dispatcher-heartbeat` | duration | да | ➖ excluded | no | вне scope контракта |
| `--max-snapshots` | uint | да | ➖ excluded | no | вне scope контракта |
| `--snapshot-interval` | uint | да | ➖ excluded | no | вне scope контракта |
| `--task-history-limit` | int | да | ➖ excluded | no | вне scope контракта |

### `docker system df` → `udocker system df` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--format` | string | да | ✅ ok | no | {"BuildCache": {"Active": 0, "Reclaimable": 0, "Size": "0B", "TotalCount": 0}, "Containers": {"Active": 0, "Reclaimable": 0, "Size": "0B", "TotalCount": 0}, "Im |
| `-v, --verbose` | — | да | 🔷 ignored | no | TYPE               TOTAL   ACTIVE         SIZE        RECLAIMABLE |

### `docker system events` → `udocker system events` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --filter` | filter | да | ✅ ok | yes |  |
| `--format` | string | да | ✅ ok | yes |  |
| `--since` | string | да | ✅ ok | yes |  |
| `--until` | string | да | ✅ ok | yes |  |

### `docker system info` → `udocker system info` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --format` | string | да | ✅ ok | yes | { |

### `docker system prune` → `udocker system prune` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-a, --all` | — | да | 🔶 accepted | no | Error: prune requires -f when stdin is not a terminal (use -f) |
| `--filter` | filter | да | 🔷 ignored | no | Error: prune requires -f when stdin is not a terminal (use -f) |
| `-f, --force` | — | да | ✅ ok | no | Total reclaimed space: 0B |
| `--volumes` | — | да | 🔶 accepted | no | Error: prune requires -f when stdin is not a terminal (use -f) |

### `docker update` → `udocker update` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--blkio-weight` | uint16 | да | ⛔ root-only | no | Error: --blkio-weight: resource limits need cgroup delegation |
| `--cpu-period` | int | да | ⛔ root-only | no | Error: --cpu-period: CPU limits need cgroup delegation |
| `--cpu-quota` | int | да | ⛔ root-only | no | Error: --cpu-quota: CPU limits need cgroup delegation |
| `--cpu-rt-period` | int | да | ⛔ root-only | no | Error: --cpu-rt-period: CPU limits need cgroup delegation |
| `--cpu-rt-runtime` | int | да | ⛔ root-only | no | Error: --cpu-rt-runtime: CPU limits need cgroup delegation |
| `-c, --cpu-shares` | int | да | ⛔ root-only | no | Error: --cpu-shares: CPU limits need cgroup delegation |
| `--cpus` | decimal | да | ⛔ root-only | no | Error: --cpus: CPU limits need cgroup delegation |
| `--cpuset-cpus` | string | да | ⛔ root-only | no | Error: update requires cgroup delegation and is not available without root/daemon |
| `--cpuset-mems` | string | да | ⛔ root-only | no | Error: --cpuset-mems: CPU limits need cgroup delegation |
| `-m, --memory` | bytes | да | ⛔ root-only | no | Error: --memory: resource limits need cgroup delegation |
| `--memory-reservation` | bytes | да | ⛔ root-only | no | Error: --memory-reservation: resource limits need cgroup delegation |
| `--memory-swap` | bytes | да | ⛔ root-only | no | Error: --memory-swap: resource limits need cgroup delegation |
| `--pids-limit` | int | да | ⛔ root-only | no | Error: --pids-limit: resource limits need cgroup delegation |
| `--restart` | string | да | ⛔ root-only | no | Error: update requires cgroup delegation and is not available without root/daemon |

### `docker volume create` → `udocker volume create` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--availability` | string | да | 🔶 accepted | no | Error: unknown volume create option: --availability=x |
| `-d, --driver` | string | да | 🔶 accepted | no | Error: only the local volume driver is available: x |
| `--group` | string | да | 🔶 accepted | no | Error: unknown volume create option: --group=x |
| `--label` | list | да | ✅ ok | no | a72abe0b96e84dc4 |
| `--limit-bytes` | bytes | да | 🔶 accepted | no | Error: unknown volume create option: --limit-bytes=1 |
| `-o, --opt` | map | да | 🔶 accepted | no | Error: unknown volume create option: --opt=x |
| `--required-bytes` | bytes | да | 🔶 accepted | no | Error: unknown volume create option: --required-bytes=1 |
| `--scope` | string | да | 🔶 accepted | no | Error: unknown volume create option: --scope=x |
| `--secret` | map | да | 🔶 accepted | no | Error: unknown volume create option: --secret=x |
| `--sharing` | string | да | 🔶 accepted | no | Error: unknown volume create option: --sharing=x |
| `--topology-preferred` | list | да | 🔶 accepted | no | Error: unknown volume create option: --topology-preferred=x |
| `--topology-required` | list | да | 🔶 accepted | no | Error: unknown volume create option: --topology-required=x |
| `--type` | string | да | 🔶 accepted | no | Error: unknown volume create option: --type=image |

### `docker volume inspect` → `udocker volume inspect` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --format` | string | да | 🔶 accepted | no | Error: no such volume: nosuchvol |

### `docker volume ls` → `udocker volume ls` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--cluster` | — | да | ✅ ok | no | DRIVER     VOLUME NAME |
| `-f, --filter` | filter | да | ✅ ok | no | DRIVER     VOLUME NAME |
| `--format` | string | да | ✅ ok | no | [{"CreatedAt": "2026-11-11T07:38:34Z", "Driver": "local", "Labels": {"a": "b"}, "Mountpoint": "/home/i.sulin/Storage/.opt/udocker/.manual-test/probe-repo/volume |
| `-q, --quiet` | — | да | ✅ ok | no | DRIVER     VOLUME NAME |

### `docker volume prune` → `udocker volume prune` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-a, --all` | — | да | 🔶 accepted | no | Error: prune requires -f when stdin is not a terminal (use -f) |
| `--filter` | filter | да | 🔷 ignored | no | Error: prune requires -f when stdin is not a terminal (use -f) |
| `-f, --force` | — | да | ✅ ok | no | Deleted Volumes: |

### `docker volume rm` → `udocker volume rm` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `-f, --force` | — | да | 🔶 accepted | no | Error: no such volume: nosuchvol |

### `docker volume update` → `udocker volume update` ✅

| флаг | аргумент | docker | udocker | в `--help` | проверка |
|---|---|---|---|---|---|
| `--availability` | string | да | 🔶 accepted | no | Error: unknown volume subcommand: update |

