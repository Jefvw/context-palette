# Model selection for AI work

This guide defines how to recommend models for Context Palette work and how to
select a model when delegated execution is explicitly requested. Model
availability varies by Codex surface and account, so treat the roles below as
the durable rule and the model names as the currently preferred mapping.

Last reviewed: 2026-07-27.

## Default recommendation

Use the least expensive available model that can complete the task reliably,
including diagnosis, implementation, and verification. A clear request is not
automatically a simple task: risk, code-path breadth, and the cost of detecting
a mistake matter as much as prompt clarity.

| Work shape | Recommended model | Reasoning | Typical examples |
| --- | --- | --- | --- |
| Ambiguous, cross-cutting, or costly to get wrong | GPT-5.6 Sol (`gpt-5.6` or `gpt-5.6-sol`) | High; increase only for unusually difficult work | Architecture, security or data-integrity review, subtle diagnosis, multi-module refactoring, final synthesis of conflicting findings |
| Clear and bounded, but still requiring engineering judgment | GPT-5.6 Terra (`gpt-5.6-terra`) | Medium | Focused bug fixes, ordinary feature work, test design, documentation updates, codebase exploration, well-scoped refactoring |
| Mechanical, repetitive, low-risk, and cheaply verifiable | GPT-5.6 Luna (`gpt-5.6-luna`), when available | Low | Formatting, exact transformations, classification, boilerplate, or high-volume processing with deterministic checks |

If the chosen Codex surface does not offer the recommended model, use the
closest available role. Prefer Terra over an older small model for code changes
that still require judgment.

## Quick decision rule

1. Use Sol when the correct task or design must first be discovered, the change
   crosses boundaries, or a plausible mistake could survive normal tests.
2. Use Terra when the scope, constraints, acceptance criteria, and verification
   path are clear but implementation judgment remains.
3. Use Luna only when the work is mechanical and an objective check will catch
   mistakes cheaply.
4. Escalate the model or reasoning effort if evidence conflicts, the task grows
   beyond its stated boundary, or verification is inconclusive.

The practical cost test is: if reviewing and repairing a weaker model's likely
mistake would cost more than the model savings, use the stronger model.

## When writing a prompt or task brief

After the prompt, include:

```text
Recommended model: GPT-5.6 Terra
Reasoning effort: medium
Why: The task is bounded and testable but still requires implementation judgment.
Upgrade to Sol if: Diagnosis is unresolved or the change becomes cross-cutting.
```

Choose the model for the work the prompt will cause, not for the apparent
simplicity of writing the prompt. For example, drafting a short security-review
prompt is easy, but carrying out that prompt is high-risk and normally warrants
Sol.

A useful execution prompt names:

- the outcome and acceptance criteria;
- the files, systems, or people in scope;
- behavior and data that must not change;
- available evidence and known uncertainties;
- required tests or manual verification;
- approval boundaries and prohibited actions;
- the expected final report.

## When Codex performs the task

For work in the active thread, Codex uses the thread's selected model; it cannot
silently replace that active model. A clear direct request should still be
executed without pausing for model discussion.

If the user asks for a model recommendation as part of the task, state the
recommended model and reasoning effort before starting. Continue in the active
thread unless the user also asks for a new thread or delegated execution; the
recommendation does not itself switch the active model.

When the user explicitly asks Codex to delegate, use subagents only for
independent, bounded work:

- Prefer Terra for read-heavy exploration, focused scans, test runs, and other
  supporting work that returns a concise result.
- Prefer Sol for ambiguous investigation, security or correctness review,
  architectural judgment, and integration of conflicting results.
- Use Luna for delegated work only when that model is available on the current
  surface and the task is mechanical with deterministic verification.
- Keep the main agent responsible for scope, integration, verification, and the
  final answer.
- Avoid parallel write-heavy tasks that are likely to touch the same files.

Codex may pass a model and reasoning override when the current delegation tool
supports it. Otherwise, the delegated agent inherits configured or parent
settings. An explicit user choice always wins.

## Sources

- [OpenAI model guidance](https://developers.openai.com/api/docs/guides/latest-model)
  describes Sol as the flagship GPT-5.6 model, Terra as the lower-cost balanced
  option, and Luna as the efficient high-volume option.
- [Codex subagent guidance](https://developers.openai.com/codex/subagents)
  documents per-agent model and reasoning choices, recommends Terra for lighter
  supporting work, and explains explicit model overrides and inheritance.
