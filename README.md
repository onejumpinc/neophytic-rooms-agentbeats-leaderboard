# Neophytic Rooms AgentBeats Leaderboard

Neophytic Rooms evaluates whether a participant can navigate generated room
graphs from obfuscated live state. This fork stages the independently verified
One Jump deterministic participant for the upstream leaderboard's exact public
`tutorial`, `no_loops = true`, five-system scenario.

The participant release workflow ran two fresh copies of that scenario and
completed all 10 generated systems successfully. Its exhaustive source tests
also cover every topology, start, and exit the public generator can produce.
See [release run 35696457098](https://github.com/onejumpinc/neophytic-rooms-deterministic-agent/actions/runs/35696457098).

## Submission workflow

The workflow is deliberately manual-only and currently inert.
`NEOPHYTIC_ROOMS_AGENT_ID` remains a non-UUID placeholder in the workflow,
`scenario.toml`, and `scenario.ci.toml`. After the immutable participant is
registered on AgentBeats, replace all three occurrences with its lowercase
UUIDv7 and dispatch the workflow once from `main`.

Register the participant as a deterministic purple game agent with no declared
AI model. The registration must expose the exact digest-pinned image and this
commit-pinned manifest URL:

`https://raw.githubusercontent.com/onejumpinc/neophytic-rooms-deterministic-agent/c146108ebcc1266824a857110aeee50b77e7b4bf/amber-manifest.json5`

Before a submission branch can be created, the workflow verifies:

- the fork, branch, first run attempt, exact scenario, green registration,
  purple registration owner/category/repository/image/manifest, and manifest
  checksum;
- immutable green, participant, and AgentBeats client image digests, including
  the participant image ID that passed the release gates;
- a closed three-service Compose topology with no secrets, registry login,
  build context, host ports, override file, or unpinned runtime image;
- exactly five generated tutorial trees, their encodings, every action and
  observation history, exact action accounting, and 5/5 successful exits in at
  most nine execution actions each;
- participant action logs in the exact history order and complete immutable
  image and GitHub Actions provenance.

Evaluation runs with read-only repository permission. A separate write-scoped
job re-verifies the downloaded evidence and can add exactly three files to one
deterministically named branch based on the audited upstream commit. It neither
opens nor merges a pull request.

No model, benchmark, or registry secret is required. The green registration's
mutable `latest` tag is independently required to resolve to the audited green
digest before every run; if it changes, the workflow fails closed pending a
new review.

## Pinned runtime

- Green agent:
  `ghcr.io/enspikondplus/neophytic-rooms-green@sha256:258a3123ff252ac1d1288a9e4043275da20bee48bce8142cbdadd47f21b8a695`
- Participant:
  `ghcr.io/onejumpinc/neophytic-rooms-deterministic-agent@sha256:6938a4ceb7e7edbc898c8781613730fdada064f804b4fd82cfedce9c8cd9ada9`
- AgentBeats client:
  `ghcr.io/agentbeats/agentbeats-client@sha256:13dfe3ef4e583a80e7ce2fe3becd0ce3b879841368a7f4fa40b6ebbabeeb014e`

The workflow stays undispatched until the participant has a real AgentBeats
registration UUID.
