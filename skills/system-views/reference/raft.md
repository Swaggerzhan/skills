# Raft

Raft appears in system views in two placements, and its flows come in two
patterns. Pin down both before drawing.

## Placement

**Single-raft (node-level)** — one node hosts exactly one replica of one
raft group. The node is the replica: process boundary and raft membership
coincide, so a view may draw the node as the group member.

**Multi-raft** — one node hosts several replicas belonging to different
raft groups. Example: nodes A, B, C each carry 3 replicas — 9 replicas
forming 3 groups:

```text
        group 1   group 2   group 3
node A    r1        r2        r3
node B    r1        r2        r3
node C    r1        r2        r3
```

Each group's replicas are scattered across different nodes, so one node's
loss costs any group at most one replica and the group keeps quorum. Which
replica lands on which node is typically decided by an external module
(placement/scheduler/master), not by the group itself.

In multi-raft, the group and the node are different units: a flow targets
a group (whose leader may live on any node), while capacity and failure
are per node. Do not draw the node as the raft member.

## Flow patterns: who acts

The decisive question in any raft-based flow: after the log replicates,
who performs the action — every replica, or the leader only?

### State machine write — every replica applies

The leader checks the request and rejects on failure; on success it syncs
the write to the followers, and every replica applies it to its own state
machine. Applying a deterministic state transition is safe on all
replicas.

```mermaid
sequenceDiagram
    Client->>Leader: write (leader checks; rejects on failure)
    Leader->>Follower: sync — every replica applies the write
    Leader-->>Client: success
```

### External write — leader only, resumed through a Handle

An external effect (an RPC to another service, a DB write) must not run on
every replica — it would execute once per replica. So:

- the leader checks the request and rejects on failure
- on success it replicates a **Handle** — a durable "external write
  pending" marker
- only the leader performs the external write
- on completion it replicates delete-Handle and replies

```mermaid
sequenceDiagram
    Client->>Leader: external write (leader checks; rejects on failure)
    Leader->>Follower: sync Handle
    Leader->>External: rpc / db write
    Leader->>Follower: sync delete-Handle
    Leader-->>Client: success
```

If the leader crashes while the Handle is pending, the new leader finds
the Handle after election and resumes the external write:

```text
on(leader failover with pending Handle)
  new leader scans replicated Handles
  for each pending Handle
    resume the external write      # idempotency required
  replicate delete-Handle
```

The cost: the external write must be **idempotent** — the new leader may
repeat what the old leader already completed before crashing.

## When a view involves raft, pin down

1. placement — single-raft or multi-raft; if multi-raft, who controls
   replica placement
2. who acts after replication — all replicas (state machine apply) or
   leader only (external effects)
3. if leader only — what marker is replicated, how failover resumes it,
   and whether the external action is idempotent
