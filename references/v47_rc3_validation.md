# v47-rc3: narrower model work, incomplete full-run validation

## Changes

- Each independent-review claim now carries its exact frozen excerpt with local range IDs. Complete source context remains verbatim but without competing paragraph numbers. A two-claim diagnostic packet decreased from 21,734 to 16,180 characters (25.6%); no latency reduction is inferred from this size measurement.
- With the existing opt-in compiled transport, hotword extraction and second-pass decisions use no-filesystem model calls. Scripts validate real source links, independently verified input viewpoints, literal aliases, input-topic coverage, actual separate review runs, and retained rejection decisions. Existing scoring computes evidence counts and display weights; only host code writes the final audit. The real HY4 hotword stage has not yet been reached successfully.
- Legacy timing records without a comment-capture field now retain unknown status rather than reporting a known absence.

## Observed tests and limitations

- Full source regression: 434 passed in 32.02 seconds. This establishes code regressions, not report quality or domestic-model completion.
- Public checkout: 427 passed, 7 environment skips in 20.80 seconds; Skill validation and runtime preflight passed. Shared installed copies were not updated.
- A 19-claim independent review returned 17 fully supported and two partially supported rows in 477.859 seconds. Inspection showed both rejection rationales misread source paragraph numbers. A new two-claim local-excerpt review timed out at 241.375 seconds; no rejection was manually converted to approval. Counts were corrected against retained original JSON rather than copied from the earlier, different 20-claim input.
- Same 159-character real-comment input: requested thinking/output caps timed out at 90.829 seconds; a JSON-schema comparison timed out at 90.672 seconds. A process-local native thinking-switch experiment returned one label in 31.187 seconds but still emitted reasoning activity. An eight-comment repeat then timed out at 91.157 seconds. The native switch is not a reliable demonstrated fix and is not shipped in the reusable Skill.
- A 34-comment request with a 290-second limit finished as timeout after 847.765 seconds wall time. Windows Kernel-Power events recorded modern standby starting at 20:32:32 and resumption around 20:42; a simultaneous ordinary local command also stalled. No success is claimed and standby time is not subtracted. Local test harnesses now acquire and release a thread-scoped idle-sleep request; global power plans, the display and other workers are unchanged. Explicit user sleep can still interrupt testing.
- No formal synchronized Word/Excel/workbench package has passed a new complete run. Overseas collection still uses the ordinary collector-capable worker; model-free host collection compilation there is not implemented. Packaged Word page-rendering remains unavailable, so visual QA is not marked passed.

These are candidate changes, not a demonstrated one-hour release. Fresh tests must not reuse the observations above as semantic answers. Shared installed Skills and unrelated model windows remain untouched.

## Stepwise acceptance update

At 20:59:20, the current isolated HY4 continuation passed independent viewpoint review and the source mapping gate: all 19 input claims were accepted after a fresh 503.844-second model call. The evidence-ID set was unchanged; no rejected item was removed to obtain this result. The controller produced the verified bundle and advanced to comments. This establishes one successful review step, not a complete report or a review-speed improvement.

New research plans now copy the resolved stage budgets from the persisted input contract. Previously the plan could display raw-workbook defaults while the controller and model task correctly enforced standard-workbook limits. This alignment does not change allocations, reset clocks or modify an active job.
