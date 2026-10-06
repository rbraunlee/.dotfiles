> **Historical copy (2026-10-06)** of root `docs/m2-qualification.md`. Dated sandbox qualification and host-path record; neither S0 nor full M2 accepted. No live action authorized.
> Original root note remains ignored and untouched. Paths written as `docs/...` below refer to original drafting locations; use [the package history index](../README.md) for relocated files.

# M2 qualification checkpoint — 2026-10-04

**Status:** component evidence recorded; full M2 and Gate A not accepted.

The user explicitly approved building the worker image and running disposable
container tests after granting Docker socket access. At the initial component
checkpoint, no daemon configuration, firewall, existing user container, host
OpenCode service, GitHub or credentials were changed. That private build context
contained only the four worker assets and the approved local OpenCode binary;
the Docker client used an isolated empty home. The separately approved XFS
migration and subsequent storage-transport revision are recorded below.

## Pinned build identities

- Debian bookworm-slim amd64 manifest:
  `sha256:f3034a6ec3c1205360777c4aae76234998866ad18806ae62b63a3f84ccad782b`.
- OpenCode: V2.0.22, `/usr/bin/opencode` ELF binary SHA-256:
  `358eec329b5340e1755b8590e5e731864f6c041401e8c1e66a681f5fd2133996`.
- Current storage-transport worker assets fingerprint:
  `003d77aa930b293ec524ef20531c650af1912e96c67a9c59eb421c61f1f552af`.
- Current classic image ID:
  `sha256:a486873099a315518029719c1b1cce2aea1ad9a917556b55e710ea150305d096`.
- Earlier proxy-bundle fingerprint/image (retained):
  `5f1b17efea08238e77ba016bab0641357a41da0f5bea4873404b4aa2a5f92639` /
  `sha256:a180e8d83b9eddbe6d3ee59879bd37581e07c542fe15d08a6f574e03f8856e9d`
  (containerd identity; migrated classic identity recorded below).
- Earlier deadline-cleanup image/bundle (retained):
  `sha256:aab5a3b6d84c3f77542320ee10bc82f5dddee14f8106b1497039be03a33f26c9` /
  `4301a28cbdd0600ba745a07939911b183a568352d8f0f61218fd86c9d7bcb36c`.
- Intermediate deadline revision (retained with the failed component result):
  `sha256:5182070f9318d3dcebc841f39ce834d2853d4e47be74a877608107e87849a639`.
- Earlier input-snapshot image:
  `sha256:5b0951b2edb7e0dd5ed8ee1296b2b48b28003adcccf099bfcc3e2078f51dc3d5`.
- Earlier authenticated image (before read-only input support):
  `sha256:50f024d7b76a0c9067e4372560355e5c9b61e40dab3d343b11c4a65bbb133add`.
- Earlier image, retained for the authentication regression:
  `sha256:e79f43983fbcc8a40df1cc637d9f95fb384ff4ea631f8ebd5e8d2dacc6b9ee1e`.

Build logs and exact input/result records are retained in
`/tmp/opencode/routine-m2-qualification-lya335w_/`. Private diagnostic logs may
contain **expired container-local** server passwords; do not publish them as
verification evidence. The application exports only allowlisted metadata/hashes.

The proxy revision's private four-asset build context, empty Docker administration
home, build inputs, image ID and build logs are retained in
`/tmp/opencode/routine-m2-proxy-build-mrhjtqh7/`. The first build attempt failed
because the sanitized `/nonexistent` home is unsuitable for Buildx; the retry used
a new empty home/config **inside that temporary directory**, never user Docker
configuration or credentials. No packages were installed on the host.

## Negative storage qualification

Docker 29.8.2 reports `overlayfs` with
`driver-type=io.containerd.snapshotter.v1`. Creating a container with
`--storage-opt size=64M` succeeds, but an isolated non-root container successfully
wrote **100,663,296 bytes (96 MiB)** into its writable layer under that purported
67,108,864-byte limit. This is not an enforced quota.

Evidence: `quota-fill-probe.json` and `quota-fill-container-inspect.json` in the
qualification directory. The storage probe contained no checkout and was removed
after recording its evidence. `launcher-preflight.json` demonstrates that the
updated actual launcher reports `disk_quota_unavailable` before worker dispatch.

The current production path admits only the classic `overlay2`/XFS storage
backend; Docker must also accept the requested quota with project quotas enabled.
That backend still needs real fill/exhaustion qualification. Never treat the
presence of a quota option in inspection output as proof of enforcement.

## Positive service-component qualification

Reproduction (explicit opt-in; Docker access and the pinned local image required):

```sh
OPENCODE_ROUTINE_COMPONENT_IMAGE=sha256:a180e8d83b9eddbe6d3ee59879bd37581e07c542fe15d08a6f574e03f8856e9d \
  python3 -B -m unittest discover -s linux/opencode-routine/tests -v
```

Result: **112 passed, one full-baseline smoke test skipped**. Without opt-in, 105
tests pass and eight live tests skip. Latest service-component
evidence: `/tmp/opencode/routine-m2-component-zzodumzc/qualification.json` and
`container-inspect.json`, including the image, bundle and probe-script hashes.

The component test deliberately has a **read-only root** and bounded RAM-backed
test directories (384 MiB `/home/worker`, 32 MiB `/tmp`), not an unbounded writable
layer. Memory is bounded at 768 MiB, CPU at one core, PIDs at 64; there are no host
project/home/socket mounts, published ports, capabilities, networking, model
credentials or PR keys. Only the disposable approved input snapshot is bind-mounted
read-only at `/handoff` and `/inputs/fixture.data`.
It does not launch a production baseline or claim to preserve a product checkout.

Real container-local service shell execution verifies:

- V2.0.22 server identity and its container PID, authenticated through the built-in
  CLI using the foreground server's generated password, never the host service.
- UID 10001, read-only root/global/project-control configuration, tmpfs capacity,
  and the actual cgroup memory/PID limit files.
- Host-only filesystem canary and Docker socket are inaccessible; the tool writes
  its locality canary only inside the container.
- A private disposable host `Store` ledger and its real lock file are not mounted.
  Container-local shell attempts to open both for reading and writing fail; host
  file hashes are unchanged afterward. No real user ledger is used.
- Only loopback is present; attempted Docker-host/LAN/public IPv4/public IPv6
  connections fail. This proves deny-all behavior only, not approved proxy egress.
- A secret-output canary appears only as a hash in exported check metadata.
- The actual worker verifier checks the approved file's size/hash and effective
  read-only flag at both snapshot locations before any service command. A real
  service shell command reads it and demonstrates write denial. Evidence exports
  only source/target/hash/size, not the input bytes.
- The container exits and is confirmed stopped; its inspection/evidence is retained.
- A quiet setup command with a child process exceeds its one-second deadline and
  reports `timeout`, not success. Observed return including cancellation is about
   1.15 seconds. A subsequent real service check confirms the child is gone/zombie
  and its delayed-write canary never appears. This exercises command cleanup, not
  the full retained-clone baseline admission gate.

## Resource exhaustion qualification

The same opt-in command runs five finite resource tests, each in its own non-root,
offline container with a read-only root, no host mounts, 96 MiB memory/no swap,
32 PIDs, 0.25 CPU, bounded 8 MiB tmpfs, and the local log driver configured with
1 MiB rotation, one file and compression disabled. All are confirmed stopped and
retained. No daemon settings, host firewall or existing containers are changed.

Each directory below contains `qualification.json` and `container-inspect.json`,
with exact image, bundle and probe-script hashes:

| Probe | Observed enforcement | Evidence directory |
|---|---|---|
| tmpfs fill | Bounded writes fail with ENOSPC at 8 MiB | `/tmp/opencode/routine-m2-resources-53o0ogeg/` |
| CPU | 30 throttled periods during a three-second CPU loop at 0.25 core | `/tmp/opencode/routine-m2-resources-20dxqr3r/` |
| Docker logs | 4 MiB of finite output rotates; early lines disappear and final line/summary remain within the bounded retrieval budget | `/tmp/opencode/routine-m2-resources-rv3fp218/` |
| memory | A bounded allocation child is SIGKILLed; the cgroup's OOM-kill counter increases | `/tmp/opencode/routine-m2-resources-w78h5nfu/` |
| PIDs | Finite child creation returns EAGAIN and the cgroup's limit-event counter increases; all children are killed/reaped | `/tmp/opencode/routine-m2-resources-cm457hnx/` |

These tests establish actual CPU/memory/PID control and log rotation, not just
configuration presence. The tmpfs test **does not** qualify production writable
layer quotas or persistent checkout retention. Log retrieval demonstrates rotation
and bounded output; it does not directly audit privileged daemon file sizes or
prove that all application-owned log files are separately bounded. Production
writable-layer quotas remain required for those files.

The same five probes also pass against the current proxy-bundle image. Current
evidence directories (in table order: tmpfs, CPU, logs, memory, PIDs) are
`/tmp/opencode/routine-m2-resources-r_5v468n/`,
`/tmp/opencode/routine-m2-resources-u9y6lcqx/`,
`/tmp/opencode/routine-m2-resources-aqg66zoq/`,
`/tmp/opencode/routine-m2-resources-0yo2fh60/` and
`/tmp/opencode/routine-m2-resources-1xwfdo8h/`. Earlier evidence remains retained.

## HTTPS proxy component checkpoint

The image includes `proxy.py`, bound into the immutable asset fingerprint. Twenty-nine
daemon-free tests cover exact domain/Host/443 admission, framing/header rejection,
special-use IPv4/IPv6 and transition denial, mixed public/private DNS and rebinding,
single-resolution numeric dialing and peer verification, matching visible TLS SNI,
fragmentation/real Python ClientHello, absent/different SNI/ECH/plaintext denial,
connection/request/idle/total/aggregate-byte limits, disconnect/cancellation and
killable/reaped bounded DNS subprocesses.

The opt-in real-image probe runs **offline** on a read-only root, no mounts, 96 MiB
memory/no swap, 0.25 CPU, 32 PIDs, bounded 8 MiB tmpfs and bounded local logs.
It exercises proxy socket traffic entirely on loopback with **injected DNS and
upstream peer identity**. It confirms early domain/mixed-private-DNS denials,
mismatched SNI before payload, byte-exact allowed loopback relay, capacity denial,
deadline/slot release and explicit special-use rejection on image Python 3.11.
Its private payload canary never appears in exported Docker logs/evidence.

Evidence: `/tmp/opencode/routine-m2-proxy-ptlb7gnp/qualification.json` and
`container-inspect.json`, recording the image/bundle and probe SHA-256
`9411f0c880fb6f78cb9f657317b88d8b0fc4222fad55b91ffc1bd1c963215b08`.
The container is confirmed stopped and retained. Evidence explicitly records
`injected_dns_and_peer_identity: true`, `approved_external_access_qualified: false`
and `host_firewall_qualified: false`.

No real external endpoint, firewall, per-environment network, provider or credential
has been enabled/qualified. Transparent CONNECT checks a transport endpoint and
initial visible SNI; it cannot inspect encrypted HTTP Host/URL routing. Shared-endpoint
domain fronting must be addressed through endpoint qualification or a stronger
approved transport design before granting egress. HTTP/non-443/ECH/legacy TLS are
unsupported. `baseline` still rejects all requested egress; the new component
is not a network admission grant or M2 acceptance.

## Offline launcher proxy lifecycle checkpoint

The host launcher now exposes a typed `proxy-check` for a claimed run. Profile v2
accepts explicit `network.proxy` limits; the policy contains only approved domains
and those bounded limits. The original image/bundle identities above are unchanged.
No image build, daemon/storage change, environment network, firewall rule or
credential injection was needed for this checkpoint.

Validation at this revision:

- Normal suite: **128 passed, ten live tests skipped** (138 total).
- Opt-in lifecycle suite: **25 passed**, including two real launcher/container tests.

```sh
OPENCODE_ROUTINE_COMPONENT_IMAGE=sha256:a180e8d83b9eddbe6d3ee59879bd37581e07c542fe15d08a6f574e03f8856e9d \
  python3 -B -m unittest discover -s linux/opencode-routine/tests -p test_m2_proxy_lifecycle.py -v
```

Each proxy uses UID 10001, a read-only root, one generated read-only policy file,
approved CPU/memory/PID/log bounds, no capabilities, no published ports and
`network_mode: none`. The actual health probe checks policy/worker-asset bytes,
read-only policy status and loopback-only interfaces, then requires denial of an
invalid loopback HTTP request. It never resolves or connects to an upstream.
The host validates effective container settings before accepting readiness.

| Case | Result | Retained evidence directory |
|---|---|---|
| Approved policy | `proxy-check-passed`; stopping confirmed | `/tmp/opencode/routine-m2-proxy-lifecycle-dhxngvux/` |
| Policy deliberately modified before startup | `proxy-check-failed`, `proxy_readiness_failed`; stopping confirmed | `/tmp/opencode/routine-m2-proxy-lifecycle-negative-68lp734x/` |

Both directories contain private `qualification.json` and `container-inspect.json`,
and a private state ledger/artifact tree retaining policy, Compose and allowlisted
evidence. Qualification records exact host-source/test hashes, image, bundle,
profile, policy, Compose, run and evidence identities. Both stopped containers are
retained. The initial positive check from the earlier host revision is also
retained at `/tmp/opencode/routine-m2-proxy-lifecycle-j0b4akwo/`; the table identifies
the later revision's complete positive/negative evidence.

The tests also exercise malformed/unapproved limits, input drift, narrow CLI
authority, duplicate requests, shared deadlines, failed/ambiguous startup, malformed
effective configuration, interruption, ledger-write failure during stopping,
unsafe artifact paths and pre-existing container denial. Fake adapter results do
not establish isolation. A check never advances slice integration state or grants
egress; evidence explicitly records external-access/firewall qualification false.
Production network/proxy lifecycle, approved endpoints and all other M2 gates
remain open.

## Gated environment policy/service/credential checkpoint

At the subsequent host revision, profile v3 and typed `environment-plan` /
`environment-check` add a run-bound declarative network/service/credential policy
and durable component lifecycle. The image/bundle identities above remain
unchanged. Normal suite: **157 passed, ten live tests skipped** (167 total), including
29 new environment tests.

The policy explicitly requires host-input, pre-Docker forwarding, same-bridge and
container-DNS enforcement, verified interface/host-route identities, and denial of
worker DNS forwarding/direct egress, service egress, host/LAN, IPv6 and cross-slice
traffic. A pure policy oracle is tested against positive/negative flow cases; it
does not establish effective packet filtering, DNS isolation or encrypted routing.

The production adapter always refuses activation before networks, rules,
credential reads or workloads. Injected adapters test intent journaling, ordering,
ambiguity, shared/per-command deadlines, drift, reverse stopping, interruptions and
ledger-write failures. A bounded file-delivery primitive uses fake erasable byte
buffers, exports no values/actual secret lengths/secret hashes, and refuses cleanup of changed
inodes. Service checks never request provider keys; proxies receive no credentials.
Failed/uncertain stopping holds the run and retains private files for recovery.

No real service, credential source, model provider, online proxy, firewall or
network was enabled/tested in this checkpoint. Real adapters/broker/provider
configuration still need implementation, approved host setup and qualification.
Earlier live proxy evidence above is tied to its recorded **earlier host revision**;
it does not qualify the new environment layer. M2/Gate A remain unaccepted.

Network implementation references reviewed:
[Docker bridge behavior](https://docs.docker.com/engine/network/drivers/bridge/) and
[iptables ordering/container DNS](https://docs.docker.com/engine/network/firewall-iptables/).
No daemon/firewall settings were changed or inferred to be enforcement proof.

## Defects discovered and corrected

1. Docker's `local` logging driver rejects default compression with `max-file=1`:
   explicitly set per-container `compress=false`, preserving the requested bound.
2. A foreground V2 server generates a password. The original client omitted it.
   The worker now reads that generated value from its private local startup log and
   passes it to CLI requests through `OPENCODE_PASSWORD`, not command arguments,
   Docker configuration, planning artifacts or exported evidence.
3. Docker's containerd `overlayfs` backend accepts but ignores the size option:
    reject unqualified storage before creation; do not silently remove the limit.
4. Requesting limits is insufficient when daemon capabilities are missing. Preflight
   now requires cgroup v2 and affirmative CPU CFS, memory, swap and PID support;
   unknown, disabled or non-boolean capability values fail before image dispatch.
5. The CLI's previous per-request 15-second allowance could exceed a short command
   deadline. API calls now share the command deadline. Known shell cancellation has
   a separate maximum two-second window bounded by the total runtime. Late results
   cannot become passes. Unknown creation or unconfirmed cancellation fails safely.
   Regression tests cover slow success, hanging clients and failed cancellation;
   the real setup-timeout/descendant test passes with the rebuilt image.

## Earlier storage priority and read-only inventory — 2026-10-04

The user has reprioritized the writable-layer quota blocker before further
network/service/credential implementation. Earlier provisioning deferral is
historical; no provisioning approval has replaced it. No VM, filesystem format,
mount, package installation, additional daemon or existing-daemon change was made.

Read-only reinspection confirms Docker 29.8.2 with containerd `overlayfs` and Docker
root `/var/lib/docker`. `findmnt` reports Btrfs at that root; `df` reports about
740 GiB available on the shared root/home filesystem. `dockerd`, `docker`, `losetup`
and `fallocate` are available; `mkfs.xfs`/`xfs_quota` were not found on `PATH`.
Unmounted devices are not approved formatting targets. These findings are setup
inventory, not new quota qualification.

`docs/implementation-plan.md` now specifies the storage-first proposal/approval,
finite quota-fill proof, trusted runtime binding and retained offline-baseline
qualification sequence. A file-backed XFS/project-quota filesystem plus a separate
routine-only overlay2 daemon is a **candidate to evaluate**, not an adopted or
provisioned architecture. Existing Docker state must remain untouched, and hard
limits must not be weakened.

## Approved XFS migration and writable-layer qualification — 2026-10-04

The user subsequently approved continuing a 50 GiB file-backed XFS setup and
migration of the existing Docker daemon, and executed the prepared privileged
scripts. This supersedes the earlier provisioning deferral and separate-daemon
candidate for this storage setup only. The host remains Btrfs; the XFS image is
`/var/lib/routine-storage/docker.xfs`, mounted at `/mnt/routine-docker` with
`prjquota`. Docker now reports classic `overlay2`, backing filesystem `xfs`, and
data root `/mnt/routine-docker/docker`. `/etc/fstab` retains the loop mount; a
Docker systemd drop-in requires the mount and checks XFS/project quotas before
starting. Boot/restart persistence has not yet been qualified.

The old `/var/lib/docker` and containerd stores were not deleted. The restored
old daemon was checked after the first attempt: all 37 stopped containers and ten
original image records remained present. Containerd descriptor IDs differ from
classic config IDs; the first migration rolled back after checking the wrong ID.
The corrected resume traversed hash-verified OCI metadata, verified all ten
original records against nine exact image configs, and restored all original
tags, including `rudolfbraun/lobbyregister-pull:0.1.0`. Two original descriptors
resolve to the same config. Private inventory, image archive, identity map and
rollback files are retained under
`/var/lib/routine-storage/docker-migration-20261004-rL3yYc3m/`.

That migration's worker image classic ID is
`sha256:696e71ab62c5f05630372fd27268374348afb655d1125435054b86c0b985ea4a`;
its previously recorded containerd ID was
`sha256:a180e8d83b9eddbe6d3ee59879bd37581e07c542fe15d08a6f574e03f8856e9d`.
The packaged bundle fingerprint is unchanged. Existing approved product profiles
must explicitly reapprove the new runtime identity; none were silently rewritten.
Only disposable qualification fixtures used the new ID.

| Probe | Result | Retained evidence |
|---|---|---|
| 96 MiB finite write under 64 MiB writable-layer cap | Non-root synchronized writes fail with ENOSPC at **67,043,328 bytes**; stopping confirmed | `/tmp/opencode/routine-xfs-quota-_00jx3z5/` |
| Same exhaustion, then explicit 2 MiB truncation of the disposable fill file | Same enforcement; marker remains readable from the stopped container | `/tmp/opencode/routine-xfs-quota-_y7fg8ub/` |
| Actual offline baseline, with host fixture retained for independent stopped inspection | Clone branch/commit, container-local tool marker and allowlisted evidence verified after exit under a 1024 MiB cap | `/tmp/opencode/routine-xfs-baseline-7ann1iqo/` |

The quota probes use UID 10001, no networking/host mounts/capabilities, bounded
CPU/memory/PIDs/local logs, and the exact migrated worker image. The first probe
also exposed a real failure: `docker cp` cannot create the `overlay2/.../merged`
directory on a completely full project-quota layer. Its overall retention result
is **failed**, even though disk enforcement passed. The second probe deliberately
frees 2 MiB before exit; it does **not** qualify collection from a full layer.
Both owned containers and the failed evidence are retained, not pruned.

Validation: the opted-in `test_m2.py` suite passes **35/35**, including the real
baseline/locality/plugin/secret-output canaries. A separate live smoke pass retained
its disposable host fixture at `/tmp/opencode/routine-m1-ezzc2sm0/`, including
ledger, authorization, Compose and handoff artifacts. Its stopped clone's branch
`refs/heads/routine/run-1` resolves to the approved baseline commit. Ordinary test
fixture cleanup is not retention proof. Normal validation remains **157 passed,
ten live tests skipped** (167 total).

This closes the demonstrated lack of disk enforcement on the active backend and
establishes ordinary offline-baseline retention, not full M2/Gate A acceptance.
Full-layer collection/recovery, runtime restart/persistence, existing-container
collision protection and production failure/resource/state-denial rechecks remain
open. No custom firewall, online proxy, service credentials or model provider was
enabled by this qualification.

## Still required

Production-safe retained-checkout inspection/recovery (controlled full-fixture
read-only inspection now passes) and approved daemon-restart persistence
qualification on the no-VM XFS setup, including privileged source validation and
descriptor-pinned mount handoff. Production setup failure/timeout, state denial and
CPU/memory checks have passing evidence; the historical PID pass is superseded for
current qualification by the two failures diagnosed below. Docker-log rotation still has component evidence
rather than a privileged on-disk audit. Also required: approved
service/provider/credential handling; mounts beyond approved regular-file snapshots
if needed by an approved project; enforced approved egress and cross-slice
probes, proxy lifecycle/endpoint qualification and encrypted-routing risk resolution;
and all subsequent M3/M4 acceptance gates. The subsequent storage approval covered
the recorded Docker migration, not further daemon changes or custom firewall work.

## Full-layer evidence transport and production failure qualification — 2026-10-04

The subsequent worker revision emits exactly one allowlisted JSON envelope on
stdout. Local `evidence.json` writes remain best effort; ENOSPC does not prevent
host collection through the bounded Docker log API, which requires no layer mount.
The adapter reads the entire bounded stream, rejects nonempty malformed/duplicate/
extra records and preserves existing input/check/exit validation. Only empty logs
permit the legacy file/archive path. No raw shell/service output, exception text,
input bytes or credential values are intentionally emitted by this transport.
The log channel is worker-provided evidence, not independent verification or
integration authority. Missing/rotated/malformed evidence remains failure.

Container creation now uses Compose `create --no-recreate` after an absence check;
a private preparation nonce rejects stale containers even with matching artifact
labels. Start/stop use the verified immutable container ID. A creation race or ID
replacement is refused, and pre-existing containers are held without adoption,
replacement or stopping. The old live smoke fixture reused `run-1`: the first full
suite correctly rejected its previously retained container. The fixture now uses
unique live run IDs; the prior container and failure result were not reset/deleted.

### Image preparation

The image was derived from the exact approved migrated classic image
`sha256:696e71ab62c5f05630372fd27268374348afb655d1125435054b86c0b985ea4a`,
copying only the four current worker assets, restoring their read-only permissions
and updating the bundle label. Debian/OpenCode binary/configuration are inherited
unchanged; no packages were installed. Current identities are listed at the top.
Build context, exact asset/recipe hashes, empty Docker administration home, image
ID and private logs are retained at
`/tmp/opencode/routine-m2-storage-build-t68px6ps/`.
Its `validation-summary.json` pins the final host/test hashes and the five latest
storage qualification records, checked against the current source files.

The first Buildx attempt interpreted `FROM sha256:...` as a registry name and tried
metadata resolution, then failed. No image was pulled; the failed log is retained.
The successful retry used Docker's classic builder (`DOCKER_BUILDKIT=0`) with
the exact local image ID, `--pull=false` and `--network=none`, without credentials
or inherited user Docker configuration. This changes no daemon configuration.
Only disposable qualification profiles approve the new image/bundle; existing
product authorizations were not rewritten.

### Latest validation

- Normal suite: **167 passed, 15 live tests skipped** (182 total).
- Storage suite: **15 passed**, including five actual retained launcher/container
  cases and ten daemon-free transport/ownership cases.
- Complete suite with all three image opt-ins: **182 passed**, no skips.

```sh
OPENCODE_ROUTINE_TEST_IMAGE=sha256:a486873099a315518029719c1b1cce2aea1ad9a917556b55e710ea150305d096 \
OPENCODE_ROUTINE_COMPONENT_IMAGE=sha256:a486873099a315518029719c1b1cce2aea1ad9a917556b55e710ea150305d096 \
OPENCODE_ROUTINE_STORAGE_IMAGE=sha256:a486873099a315518029719c1b1cce2aea1ad9a917556b55e710ea150305d096 \
  python3 -B -m unittest discover -s linux/opencode-routine/tests
```

Latest retained production-path cases (the entire host fixture is retained, not
just a copied report):

| Case | Result | Evidence directory |
|---|---|---|
| Finite 256 MiB attempt under a 128 MiB writable-layer cap | `sandbox-failed`; validated failure evidence collected, stopping confirmed; stopped `docker cp` still fails; no fill-file deletion/truncation or quota increase | `/tmp/opencode/routine-m2-storage-ht051evh/` |
| Pre-existing stopped container with matching artifact ID but another preparation nonce | `sandbox-held`; complete inspection remains byte-identical; no adoption/replacement/stop; duplicate dispatch refused | `/tmp/opencode/routine-m2-storage-nqf2gimv/` |
| Setup exits 7 with secret-output canary | `sandbox-failed`, `required_command_failed`; no checks executed, only output hash exported; stopping confirmed | `/tmp/opencode/routine-m2-storage-3i84_lpx/` |
| Quiet setup exceeds one-second command deadline | `sandbox-failed`; setup evidence says `timeout`; no checks executed; stopping confirmed | `/tmp/opencode/routine-m2-storage-r2ux_le3/` |
| Positive baseline with real host ledger/lock read/write probes | `baseline-passed`; actual ledger and lock hashes unchanged during execution; stopped independent-checkout marker inspected | `/tmp/opencode/routine-m2-storage-pdqca7i7/` |

Each private directory contains `qualification.json`, `container-inspect.json`,
the approved disposable project, ledger, handoff and run artifacts. Qualification
pins all host Python asset/test/probe hashes, run/profile/bundle/image/daemon
identities and allowlisted observations. Full-layer exhaustion prevents fetching
the final shell output page, so that case reports `bootstrap_failed` with service
identity but no completed command record; it does not pretend the fill command
was independently verified. The resulting full layer and its diagnostic data are
retained, and failure evidence is now recoverable without mounting that layer.
General interrupted-run recovery remains M5 work, not implemented by this change.

Current-image service/proxy/resource components were rerun successfully. Service
evidence: `/tmp/opencode/routine-m2-component-jxww73rw/`; offline proxy component:
`/tmp/opencode/routine-m2-proxy-q5sy7jdk/`. Resource evidence in tmpfs/CPU/log/memory/
PID order: `/tmp/opencode/routine-m2-resources-als0sp2i/`,
`/tmp/opencode/routine-m2-resources-7zn26ops/`,
`/tmp/opencode/routine-m2-resources-5acrsnx7/`,
`/tmp/opencode/routine-m2-resources-mkyoy225/`,
`/tmp/opencode/routine-m2-resources-jnatam86/`. These are still read-only-root
component probes, not all production baseline resource rechecks. The actual
offline proxy lifecycle positive/negative tests also passed against this revision;
they grant no external access.

**Remaining storage boundary:** stopped full-layer checkout inspection/recovery
and daemon-restart/boot persistence are not qualified. A recovery proposal must
not silently delete project bytes, raise the quota or manipulate Docker's data
directories. No daemon restart, filesystem/daemon/firewall changes, services,
provider credentials or online access were performed in this checkpoint.
M2 and Gate A remain unaccepted; network/service/credential implementation stays
paused until the storage track is completed.

## Approved read-only inspection of the stopped full fixture — 2026-10-04

After another session identified the graphdriver remount as the obstacle, the user
explicitly approved **one disposable offline inspector** mounting only the retained
full fixture's `UpperDir/home/worker/project` read-only. This mount is outside the
ordinary-worker profile policy; the approval does not change that policy or grant
a general Coordinator recovery capability. No daemon/quota change was needed.

The source is the full-layer case retained at
`/tmp/opencode/routine-m2-storage-ht051evh/`, container
`d8d3e19792aa213245d8f2457b8ef26c50b632d131f683f10247d46284e093f4`.
Fresh Docker inspection matched the saved image, ownership labels, graphdriver,
stopped state and 128 MiB writable-layer quota. Its exact checkout bind source is:

```text
/mnt/routine-docker/docker/overlay2/7eca301cb7f54c41c75a4d6bdf7a250feeab78767076abc54d148e8f26fdb3bf/diff/home/worker/project
```

The inspector uses the existing pinned storage-transport image, UID 10001,
read-only root, no networking/capabilities/privilege escalation, 0.25 CPU, 96 MiB
memory/no swap, 32 PIDs, 64 MiB own-layer quota, bounded 8 MiB `/tmp` tmpfs and
1 MiB/one-file local logs. Its only bind is that checkout at `/retained`, read-only
and nonrecursive; there is no full Docker-data-root, worker-home, socket or host
state mount. The probe runs Python/Git directly, not OpenCode or repository scripts.

Docker rejected the initial `rprivate` bind before creating a container: bind
sources beneath the daemon data root must use `rslave` or `rshared`. The successful
test used `bind-propagation=rslave,bind-recursive=disabled`, allowing only one-way
host-to-inspector propagation, not bidirectional `rshared`. Failed intent/result
and private create diagnostics are retained alongside the successful evidence;
the rejected attempts created no containers. Exactly one inspector was created:
`5c86fa9a20990b975337953c0da35fe22b86f5cc1b89b259ffe5177f433005ce`.

**Result: passed.** `tests/fixtures/full_layer_inspection.py` verifies:

- Both `HEAD` and the recorded run branch resolve to the approved baseline
  `9d1c1c31d5928b0ae985697d23f85e0e4ee1beb3`.
- Git metadata is independent, has no alternates/symlink/device entries, and
  `git fsck --full --strict --no-reflogs` confirms object connectivity.
- The retained marker is readable; the fill file remains **114,098,176 bytes**.
- Effective read-only status is present and exclusive file creation fails with
  **EROFS**, not merely ENOSPC.
- Only loopback networking is present; no Docker socket is exposed.

The original container's complete before/after inspection is byte-identical. Its
quota was not increased, checkout bytes were not deleted/truncated, and it was
never restarted. The inspector is confirmed stopped and retained. Allowlisted
evidence and identities/probe hash are at
`/tmp/opencode/routine-m2-full-layer-inspection-knbueh10/qualification-rslave.json`,
with created/stopped inspector and source before/after inspections in the same
private directory. Raw repository content is not exported.

**Qualification boundary:** this proves read access to the independent clone in
this controlled fixture's full upper layer, without Docker's failed remount.
It does not prove general merged-filesystem reconstruction or interrupted-run
recovery. Lower-layer content, whiteouts/opaque directories, untrusted source
symlinks/path races, ownership/restart exclusion and backend-specific path handling
must be addressed before enabling a production inspection API. Host permissions
prevented ancestor `lstat` beyond Docker's root, so privileged safe-path checking
was **not** performed; mount-source safety for arbitrary worker data remains
unqualified. The fixture's commands and immutable retained identities are known;
do not generalize that trust to arbitrary worker-supplied paths.

No existing worker image or runtime adapter was changed by this probe. Normal
validation remains 182 tests (167 pass, 15 live skips); the separate real inspector
is recorded evidence, not an additional discovered unit test or M2 acceptance.
Daemon restart/boot persistence and remaining M2 gates stay open.

## Durable source admission and production resource rechecks — 2026-10-04

This subsequent host revision records the private preparation nonce in the ledger
before container creation and the verified immutable container ID before marking
the run `running`. A missing returned creation ID fails and attempts stopping,
never a pass. Existing image/bundle/profile contracts are unchanged. Old retained
runs missing those durable ownership fields are **not** implicitly admitted by
the new component; no old ledger or authorization was edited to add them.

`routine/retention.py` now implements fail-closed admission and read-only descriptor
components. Admission pins trusted daemon/root/backend, completed/stopped durable
run ownership, image/quota identity, exact upper/merged/work/lower graphdriver
layout and stopped-state timestamps. Source change/restart invalidates the result.
Metadata admission is exercised against actual current stopped-container
inspections in the eight live storage cases; this does not read Docker's raw data.

The descriptor scanner is tested **only against owned local filesystem fixtures**:
administrator-controlled ancestry, `O_NOFOLLOW` directory walking, pinned directory
identity across pathname swaps, mount IDs (including same-device bind crossings),
positive absence of checkout content in every lower layer, OverlayFS xattrs,
whiteout/link/device rejection, inode-replacement detection, entry/depth/logical-
byte/deadline bounds and descriptor cleanup on failures/interruption. It neither
executes repository code nor exports paths/content as scan evidence. The initial
supported subset requires a complete raw-upper-only tree; ambiguous lower-layer
or overlay-dependent content is refused, not reconstructed speculatively.

**Production activation is unconditionally blocked.** A privileged trusted-root
descriptor/xattr observer, source restart exclusion/lease ownership, qualified
descriptor-pinned Docker bind handoff and bounded inspector lifecycle still need
approval and real qualification. Empty xattr lists from an unprivileged caller
are not proof of absent `trusted.overlay.*` metadata. No root helper/service was
installed, privilege used, new raw-layer mount created, or Coordinator operation/
profile enable flag added. The earlier single-fixture mount approval was not reused.

### Current validation and retained evidence

- Normal suite: **192 passed, 18 live tests skipped** (210 total).
- All three existing image opt-ins: **210 passed**, no skips.
- New daemon-free cases: 24 retention contracts and one missing creation-ID case.
- New actual-launcher cases: CPU throttling, bounded memory OOM and PID rejection.

Complete final verbose test log and source/test hashes are retained at
`/tmp/opencode/routine-m2-retention-validation-o8mf0msm/` (`suite.log` and
`validation-summary.json`). The same opt-in invocation documented above reproduces
the full suite using unchanged image
`sha256:a486873099a315518029719c1b1cce2aea1ad9a917556b55e710ea150305d096`.

Latest actual production-path storage cases:

| Case | Result | Retained directory |
|---|---|---|
| Full layer | Stopped `sandbox-failed`; evidence collected without remount/freeing bytes; actual stopped-source metadata passes admission | `/tmp/opencode/routine-m2-storage-o_3oxyyj/` |
| Existing named container | Held unchanged, no adoption/replacement; no container ID invented in ledger | `/tmp/opencode/routine-m2-storage-9h260ytm/` |
| CPU | Service tool command observes configured 0.25-core quota and increased throttled-period count; baseline passes | `/tmp/opencode/routine-m2-storage-wlnm57kw/` |
| Memory | Finite 1 GiB allocation attempt under **805,306,368 bytes** (768 MiB), no swap; host captures one OOM-kill event; child-specific command checks and baseline pass in this run | `/tmp/opencode/routine-m2-storage-7bjyr4fp/` |
| PIDs | Finite 128 creation attempts under 64 PIDs observe EAGAIN and increased cgroup limit-event counter; all owned children reaped; baseline passes | `/tmp/opencode/routine-m2-storage-5cqmkiv3/` |
| Setup failure | Exit 7, no checks, stopped failure with hash-only output | `/tmp/opencode/routine-m2-storage-ytj0m0i7/` |
| Setup timeout | One-second setup deadline, stopped failure, no checks | `/tmp/opencode/routine-m2-storage-7j36s8ct/` |
| Host authority/retention | Ledger/lock access denied, authority unchanged during execution; stopped marker inspected | `/tmp/opencode/routine-m2-storage-kqjiog9p/` |

Each retains the complete fixture/ledger/handoff, effective container inspection,
host/probe/test/image/profile identities and allowlisted observations. New runs'
container/preparation identities match actual inspection. No old run was reset.

### OOM failure semantics and preserved intermediate failures

The initial full run exposed a bad test assumption: Linux does not guarantee that
only the allocation child is selected as an OOM victim. Killing a service/client
can correctly produce `api_failed` and `sandbox-failed`. The corrected test opens
the owned container's actual cgroup `memory.events` read-only on the host before
allocation, samples bounded counters within the wait deadline and requires a
positive OOM-kill event plus the exact memory/no-swap limits. API failure alone is
not enforcement proof. It also requires validated worker evidence, confirmed
stopping and a durable pass **or failure**, without converting failure to success.

A separately retained current-test run at
`/tmp/opencode/routine-m2-storage-uxjpgk2i/` captures **two OOM kills** and a stopped
`sandbox-failed` outcome with validated failure evidence. This demonstrates safe
failure when a different process is selected, alongside the final child-kill/pass
case above. The historical failed suite/test checkpoints remain at
`/tmp/opencode/routine-m2-retention-validation-38w5oh53/` (child-only expectation)
and `/tmp/opencode/routine-m2-retention-validation-kr4v74qm/` (the test observer was
incorrectly reattached during stopped-container confirmation). The latter test
instrumentation bug was corrected by observing only the initial live wait. Logs,
fixtures and stopped containers were not deleted/reset to obtain a pass.

Current-image service, offline proxy lifecycle/component and bounded resource
components were also rerun. Exact retained directories are pinned in the final
validation summary. These passes do not enable network/services/credentials,
general interrupted-run recovery or integration. No daemon restart, filesystem/
daemon/firewall configuration, credential or worker-image change occurred.

**Next storage decision:** approve and qualify a narrow one-shot privileged
administration helper for trusted source resolution/xattr visibility and pinned-FD
mount handoff, rather than widening ordinary worker mounts or installing a general
privileged service. Its exact interface/permissions/mount lifecycle still require
approval. Daemon restart/boot persistence separately needs approval and evidence.
M2/Gate A remain unaccepted. The implementation pause recorded at this checkpoint
was subsequently superseded by the parallel M2 authorization below.

## Parallel S1/N1/C1 integration — 2026-10-04

The user explicitly authorized three parallel Sol high implementation agents
within M2, replacing the storage-first pause. Interfaces and ownership were agreed
before coding; isolated copies included current untracked package and ignored docs,
not just Git HEAD. Existing edits were retained and destination drift was checked
before transferring owned changes. Working copies and integration manifests remain
at `/tmp/opencode/routine-m2-parallel-b721fls7/`.
That directory also retains `offline-suite.log`, `existing-live-suite.log`,
`pid-only-recheck.log` and `validation-summary.json` with source/test hashes
(excluding the permission-denied credential source). Worker assets are unchanged.

### Implemented checkpoints

- **S1:** bounded identifier-only inspection controller, fail-closed handoff/probe
  contracts, dedicated atomic inspection records and cooperative source lock.
  Privileged source resolution/mount handoff and real inspector transport remain
  unimplemented/unqualified; production inspection always refuses.
- **N1:** concrete injectable Docker network/proxy requests, nftables batches,
  independent effective DNS/firewall readbacks, exact endpoint/namespace identity
  and owned proxy lifecycle. No privileged helper, packet or nftables syntax
  qualification is claimed; default transports refuse.
- **C1:** stopped-create/verify/start service lifecycle, scoped trusted file source,
  existing fake-secret delivery/path integration and shared durable checkpoint
  wiring. Service readiness rechecks network identity. Provider preparation is
  non-executable; actual OpenCode configuration unconditionally refuses pending
  authoritative local V2.0.22 evidence and an approved provider mapping.

The existing `credentials.py` was unchanged and was not inspected after permission
denial. Its observable interface is exercised by existing and combined offline
tests, not treated as a completed source review or live delivery qualification.
All service checks resolve development service bindings only; providers/proxies
receive no credentials. Combined positive and effective-DNS-readback denial tests
exercise both concrete adapters through the existing Environment and host ledger,
with confirmed stopping and retained protective policy. This is not live isolation.

### Combined validation

- **136 new offline tests:** 37 S1, 46 N1, 46 C1, five durable checkpoint tests and
  two combined service/network/credential lifecycle tests.
- Normal suite: **346 total, 328 passed, 18 existing live tests skipped**.
- All three existing approved image opt-ins: **345 passed, one failure**, no skips.
  The unchanged production PID probe returned `api_failed` with validated failure
  evidence and a confirmed-stopped `sandbox-failed`, rather than its required
  `baseline-passed`. No assertion, limit, ledger or retained evidence was changed.

The failed PID fixture is retained at `/tmp/opencode/routine-m2-storage-60n2y8nx/`,
container `b37f729e9e1266a9160d83b1e591339957cc24dab5709d251473e6d830e34407`.
Its failure evidence does not independently establish EAGAIN/reaping, so this live
suite is **not** reported green. The single fresh-run PID-only recheck also failed
with `api_failed` and confirmed stopping. Its fixture is retained at
`/tmp/opencode/routine-m2-storage-is0ztt4k/`, container
`cacb2994c53e92a5f2da5c6761577bb3c5ac776125be0b89a9b92f9c4d7ba748`.
No further reruns were attempted. PID qualification is now a named blocker;
the cause has not been established and the historical 210-pass checkpoint is not
a claim that this combined live suite passed.

Only previously approved offline container opt-ins were used, on unchanged image
`sha256:a486873099a315518029719c1b1cce2aea1ad9a917556b55e710ea150305d096`.
No new raw-storage mounts, privilege, restart, daemon/firewall change, external
endpoint, real credentials, image build or M3 work occurred.

### Next approval boundaries

`docs/m2-storage-proposal.md` separates privileged read-only source/mount-handoff
qualification from one bounded Docker restart/persistence test under maintenance
exclusion. `docs/m2-network-proposal.md` specifies N1-Q trusted helper/bootstrap and
finite network/DNS positive/negative qualification; exact helper identity and
permissions must be agreed before mutation. `docs/m2-services-proposal.md` specifies
delivery-source review permission, disposable fake-secret service qualification and
provider mapping/configuration prerequisites. Real credential use and external
endpoint access remain separately approved gates. M2/Gate A are not accepted;
production remains disabled and general crash/resume remains M5.

## Bounded read-only diagnosis of retained PID failures — 2026-10-04

**Outcome:** the failure boundary and an observability gap are established; the
underlying runtime cause is **not conclusively established** under the authorized
read-only/no-privilege/no-new-mount boundary. PID enforcement/reaping qualification
remains blocked. No additional test/qualification attempt was run, so the latest
counts remain **328 passed / 18 skipped offline**, **345 passed / one failed live**,
and **one failed PID-only recheck**. Historical passing checkpoints are retained,
not substituted for these failures.

### Verified retained observations

Both fixtures' qualification records, effective inspections, ledger/handoff and
allowlisted evidence were read from current files. The combined logs, seed and
integration manifests were also examined. Every source/test hash listed in
`routine-m2-parallel-b721fls7/validation-summary.json` matches the current checkout
(that list intentionally excludes the unread credential-delivery source). The PID
test, worker, `compose.py` and `sandbox.py` also match the seed identities: no
parallel-track edit to those execution files explains the change in outcome.

| Observation | Combined-suite failure (`60n2y8nx`) | PID-only failure (`is0ztt4k`) |
|---|---|---|
| Container ID | `b37f729e9e1266a9160d83b1e591339957cc24dab5709d251473e6d830e34407` | `cacb2994c53e92a5f2da5c6761577bb3c5ac776125be0b89a9b92f9c4d7ba748` |
| Started / finished (UTC) | 17:03:54.873943648 / 17:04:00.428816871 | 17:04:53.060135995 / 17:04:58.691777501 |
| Worker / durable outcome | Exit 1 / stopped `sandbox-failed` | Exit 1 / stopped `sandbox-failed` |
| Evidence SHA-256 | `4078ee6164a488a113752308334e50c12c644e6a9a421c044c6fad66186e62ae` | `5e0cff1873ab889fa7be90f3ba6c9d162cb3d528a8c835ccb306cb931ee75d70` |

Shared identities/settings:

- Probe SHA-256: `d7e58ae985c2ffc68e8e7f60f68fcea2d339c860cc5c58dba7b652438ada0593`.
- Profile SHA-256: `aa0859c53a12d99b2231c8f482656c2fa92e5416731049d0ac542abe38daf3eb`.
- Current pinned image/bundle unchanged; Docker 29.8.2, classic overlay2/XFS.
- Effective requested bounds: 64 PIDs, 805,306,368-byte memory/no swap, one CPU,
  128 MiB writable layer, 1 MiB/one-file local logs, network `none`.
- Probe command deadline: 30 seconds; both containers exit after about 5.6 seconds.
- Worker evidence: `diagnostic: api_failed`, `checks: []`, `outcome: failed`,
  verified container-local V2.0.22 service PID 12 / UID 10001 / location `/control`.
- Saved inspections: not running/paused/restarting/dead, no Docker state error,
  `OOMKilled: false`. That flag is not an independent observation of all child OOMs.
- No retained host PID-counter observation or completed probe record. The test
  writes its EAGAIN/event/reaping observations only after the baseline-pass assertion,
  which failed. No such observations exist in either qualification record.

### Failure boundary and candidate mechanism

Current `linux/opencode-routine/.local/share/opencode-routine/worker/worker.py:112–190`
starts a fresh authenticated CLI for each API
request, including 50 ms shell-status polling and the final output request.
`api_failed` has two sources: a nonzero CLI return code (`call_api`) or an invalid
shell ID (`execute_command`). It is not the diagnostic for a direct Python spawn
OSError (`bootstrap_failed`), a command/API deadline (`command_timeout` or
`runtime_timeout`), or a completed nonzero check (`required_command_failed`).
Service identity was already recorded, so failure occurred in the command/API path
after bootstrap. However, empty `checks` cannot distinguish shell creation,
polling or output retrieval; a check is appended only after the entire command
returns. It cannot prove that the probe started, reached EAGAIN or reaped children.

The finite probe deliberately competes for the same 64-task cgroup with the server,
worker and newly launched API clients. Its 128 attempts and up-to-20-second child
lifetimes allow a saturation window in which client/server process or thread
creation can fail. **Control-path starvation is the leading code-supported
hypothesis, not an observed causal event.** CLI stderr is discarded to `/dev/null`,
and neither request phase nor return code/signal is retained. Other client/server
errors or an invalid shell response cannot be ruled out. Unchanged files establish
no direct S1/N1/C1 edit to this path, not an explanation of historical timing.

### Read boundary encountered

One bounded descriptor-relative `O_NOFOLLOW` walk for each existing raw-upper
`home/worker/service.log` failed with **EACCES (errno 13)** before log contents could
be read. No permission change, privilege escalation or alternative bypass was used.
No `docker cp`, export or archive endpoint was invoked: the current adapter and
prior full-layer evidence establish that Docker archive reads can create a merged
layer mount, prohibited by this instruction. No retained container was restarted,
no live cgroup counter was reconstructed/inferred, and no external documentation,
credentials or provider configuration were accessed.

### Exact next approval and targeted follow-up

**PID-D1 (diagnostic read only, not qualification):** approve one administrator
read of the two named stopped containers' `/home/worker/service.log`. Fresh Docker
metadata through `unix:///var/run/docker.sock` must match the retained ID/image/
nonce/stopped-state records. Under source maintenance exclusion, securely walk
only these existing recorded upper directories with no-follow descriptors and the
specifically known XFS mount boundary; read only regular files, with `O_NOATIME`.
Ceilings: 30 seconds total, 256 KiB per log / 512 KiB combined. Reject unsafe or
oversized files without widening access. Return sanitized request-phase/error-class
observations only, excluding generated passwords, headers and raw repository output.
The user may instead provide administrator-produced redacted observations.

This approval includes **no new mounts**, container starts/execs, packages/helper installation,
permission/configuration changes, source-data/ledger edits, deletion, limit changes,
restart, external access, credentials or production activation. It is separate from
S1 privileged inspection/mount-handoff qualification. The operation is not authorized
by the present instruction and was not executed.

Service logs may still be inconclusive, particularly for discarded client stderr.
If so, obtain separate permission to implement bounded offline instrumentation for
fixed API phase and client exit/signal diagnostics plus an independent owned-cgroup
PID-event observer. Keep raw diagnostics private and schema-allowlisted; retain the
existing baseline-pass, EAGAIN, positive limit-event and owned-child-reaping
requirements unchanged. Image/bundle changes and **one** fresh, instrumented,
finite PID diagnostic run require a subsequent exact approval. Preserve both
failures; do not retry for a green result or accept `api_failed` as enforcement.
If starvation is confirmed, target the fresh-client control-path dependency rather
than raising limits, reducing the exhaustion requirement or accepting failure.

**Other blockers unchanged:** production retained inspection and environment
activation disabled; privileged source/mount handoff and restart persistence,
trusted firewall/namespace/DNS/start interlock and live packets, credential-delivery
source review/UID/bind qualification, and authoritative local V2.0.22 provider
mapping remain open. Executable provider configuration stays blocked. M2/Gate A
are not accepted; no M3 or M5 recovery implementation was started. Only this note
and the implementation plan were edited; agent prompts, code, tests, limits,
ledgers and retained evidence were preserved.
