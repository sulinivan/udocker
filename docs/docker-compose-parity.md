# `docker compose` ↔ `udocker compose` — таблица соответствия

Отметки ставятся прогоном `udocker compose` по живой `--help`-поверхности
docker compose v5.7.0 (36 страниц, 232 опции), не по памяти.

Ground truth: `.manual-test/dockercli/docker-compose` v5.7.0, help tree in
`.manual-test/docker-cli-census.json` (key `compose`: 36 pages, 232 options).
Everything below is measured, not remembered.

## Reproduce

```
python3 utils/docker_compose_probe.py            # ~30 s, writes docs/docker-compose-flags.csv
python3 utils/docker_compose_probe.py --check    # exit 1 if something is missing
.venv/bin/python -m unittest tests.unit.test_compose   # 53 tests
```

The probe runs every option of every page against `udocker compose` in a
throwaway /tmp project whose only image does not exist in the repository and
whose service is not in the file, so each command fails right after the
argument parsing (no container is created, stopped or removed). It uses
`.venv/bin/python` for the child even when started with the system `python3`
(no PyYAML/pycurl needed by the probe itself).

## Current table (docs/docker-compose-flags.csv)

| state | count | meaning |
|-------|-------|---------|
| works | 44 | option accepted, command exited 0 |
| accepted | 203 | option parsed, command then failed for an unrelated reason (usually `no such service`) |
| missing | 0 | option or command rejected as unknown |
| root-only | 5 | explicit "requires root privileges" error |
| n-a | 37 | explicit "not applicable to rootless udocker" error |

`missing among applicable: 0/247 (0.0%)`. "Applicable" = all rows except
root-only and n-a.

## What was added to udocker/compose.py

* Command pages: all 36 docker compose pages are recognized. Implemented:
  `up, create, down, start, stop, restart, kill, pause, unpause, rm, ps,
  logs, config, build, pull, push, run, exec, images, ls, volumes, top,
  port, cp, commit, export, events, wait, stats, version`.
* Global options before the command: `-f/--file` (repeatable, models merged
  with docker override semantics: mappings deep-merge, sequences for ports/
  volumes/environment/... append, `command`/`entrypoint` replaced),
  `-p/--project-name`, `--project-directory`, `--env-file` (repeatable),
  `--profile` (`*` enables all), `--ansi`, `--progress`, `--parallel`,
  `--compatibility`, `--all-resources`, `--dry-run`.
* Per-command options: every option from the census is in `DOCKER_OPTIONS`;
  short options resolved per page (`-f` is `--follow` for logs, `--format`
  for version, `--file` globally). `--option=value`, `--option value`,
  `--flag=false` work. For `exec`/`run` option parsing stops at the service
  name, so `sh -c ...` is passed through untouched.
* Implemented option effects: `--wait/--wait-timeout`, `--no-start`,
  `--no-deps`, `--force-recreate`, `--remove-orphans`, `--build`,
  `--build-arg`, `--pull`, `--push`, `--with-dependencies`, `--no-cache`
  (udocker never caches), `--rm`, `--service-ports`, `-e/-u/-w/-v/-p`,
  `--timeout/-t`, `--tail/-n`, `--signal/-s`, `--rmi`, `-v/--volumes`,
  `--profile`, `--env-file`, `--no-interpolate`, `--no-env-resolution`,
  `--no-path-resolution`, `-q/--quiet`, `-a/--all`, `--status`, `--filter`,
  `--since/--until/--timestamps` (forwarded to `udocker logs`, which grew
  those flags in cli.py/supervisor.py), `--services`, `--format` (`table`,
  `json`, docker Go-templates incl.
  `table TEMPLATE` via `udocker.utils.gotemplate`), `config --hash`,
  `--images/--volumes/--profiles/--environment/-o`, `version --short`,
  `version --format json`, `events --json/--since/--until`, `wait
  --down-project`, `stats --format json/--all`, `--dry-run` (prints the
  command, starts nothing).
* Explicit errors instead of "unknown option"/"syntax error" for
  non-applicable flags (see tables `ROOT_ONLY_OPTIONS`,
  `NOT_APPLICABLE_OPTIONS`, `NOT_APPLICABLE_COMMANDS` in compose.py):
  * root-only: `build --memory`, `exec --privileged`, `run --cap-add`,
    `run --cap-drop` → "requires root privileges: ...".
  * n-a flags: `up/--abort-on-container-exit`, `--abort-on-container-failure`,
    `--exit-code-from`, `--renew-anon-volumes`, `--scale`, `--watch`;
    `create/pull --scale`;
    `build --check/--builder/--print/--provenance/--sbom/--ssh`;
    `commit --change`; `config --lock-image-digests/--resolve-image-digests/
    --models/--variables`; `stats --aggregate/--all-projects`.
  * n-a commands: `attach`, `bridge`, `publish`, `scale`, `watch` → "…
    is not applicable to rootless udocker: <reason>".

## Deliberate differences / open tails

* No compose networks beyond the host stack; `config` prints our normalized
  plan (adds `container_name`, `depends_conditions`, ...), not docker's exact
  model. Default output is YAML like docker; `--format json` for JSON.
* No scaling/anonymous volumes; only tcp ports with a host port are
  published; images are pulled only on request (`--pull`,
  `compose pull`). `stats` is a one-shot snapshot (docker streams unless
  `--no-stream`).
* `compose run` creates its own container (auto name, `--name` honoured);
  no `_run_<hash>` suffix. `compose export` needs `-o/--output` (a tar
  stream on stdout is not supported).
* `compose commit` without `REPOSITORY[:TAG]` reuses the service image name.
* `logs --timestamps/--since/--until` depend on the timestamped log
  sidecar written by the supervisor (Lead's cli.py/supervisor.py work);
  until it is written for new containers, `udocker logs` warns and falls
  back to the untimestamped log.
* Existing udocker quirks observed while smoking (outside compose.py):
  `udocker export -o` prints "Error: creating tar file"/"Error: exporting
  container file system" although rc=0 and the tar is valid; `udocker port`
  prints the same mapping twice. Both were left untouched (cli.py zone).
* No new cli.py run flag was needed: every compose action delegates to an
  existing udocker subcommand.
