---
name: code-insight
description: Explain code through static structure and dynamic execution views.
disable-model-invocation: true
---

# Code Insight

Read code through two complementary views:

- A **Static View** explains what the system is made of and how its structural units relate.
- A **Dynamic View** explains how one concrete scenario executes and progresses toward a logical result.

Establish enough static context to name the participating boundaries before tracing a dynamic flow. Keep the requested view in focus rather than expanding every part of the codebase.

## Static View

A Static View describes architecture or a selected structural unit independently of any single execution. Explain its responsibilities, capabilities, boundaries, ownership, and dependencies.

### Layers

A **layer** is a responsibility boundary at a particular level of abstraction. It is not merely a directory or another frame in a call stack.

For example, a system may expose an RPC service layer, delegate transport-independent work to core application logic, pass through an outer subsystem facade, and then reach a Raft core or replicated state machine. Treat this only as an example: derive the actual layers and dependency direction from the code.

For each relevant layer, identify:

- what responsibility and behavior it owns;
- which interfaces or entry points it exposes;
- which lower-level capabilities it depends on;
- which state or resources it owns;
- what boundary is crossed when control enters or leaves it.

### Module Scope

A **module** is a scope-relative unit of analysis, not a unit with one fixed size. Depending on the question, it may refer to:

- an entire process or service;
- a subsystem inside a process;
- a cohesive layer or component;
- the transport-independent operation behind one RPC endpoint.

State the selected scope before explaining a module. Describe what it provides, its inputs and outputs, its callers and dependencies, and the state it owns. Distinguish structural containment, source-level dependency, runtime calls, shared-data coupling, and deployment boundaries rather than labeling all of them simply as dependencies.

## Dynamic View

A Dynamic View follows a concrete scenario through calls, data changes, triggers, and state transitions. Trace the scenario to its **logical completion**, which may occur either inside or after the initiating request.

The terms below classify completion semantics. They do not by themselves specify blocking I/O, thread usage, or other implementation mechanics.

### Logically Synchronous Flow

In a **logically synchronous** flow, the initiating request returns only after the requested operation reaches a terminal outcome from the caller's perspective. A successful response means the operation is complete, while an error response represents a definite failure outcome.

Explain this flow as an end-to-end request path: entry point, participating layers and modules, important calls and state changes, completion condition, and final response.

### Logically Asynchronous Flow

In a **logically asynchronous**, or **detached**, flow, the initiating request accepts or records work and returns before the requested operation reaches its terminal outcome. The response means "accepted" or "submitted", not "completed".

Later execution segments continue the operation through a scheduler, queue, event, callback, worker, or reconciliation loop. Durable state such as `CREATING`, together with an operation identifier, connects these otherwise separate executions until the operation reaches `COMPLETED`, `FAILED`, or another terminal state.

Explain this flow as one end-to-end workflow split at its asynchronous boundaries. Identify:

- where the initiating request returns and what that response guarantees;
- what work and state are persisted before the return;
- what trigger starts each continuation;
- how later execution segments recover context and advance state;
- what condition defines logical completion;
- how the caller observes the intermediate and final results.

Do not confuse **request completion** with **logical operation completion**. A synchronous flow normally aligns the two boundaries; a detached flow deliberately separates them.
