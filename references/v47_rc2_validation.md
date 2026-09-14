# v47-rc2 observed validation — 2026-09-14

Candidate engineering results, not a demonstrated one-hour formal-report release. Do not load these test answers into fresh generation contexts.

## Implemented changes

- Host code derives query IDs and audit rows from actual tool results, preserves original monitoring fields, verifies site-restricted result domains, and hashes query-cache logs. Model narrative is not proof of a search.
- One multi-topic author request replaces repeated filesystem read loops. Models return small semantic decisions; scripts compile evidence records and formal prose.
- New source IDs qualify quotation ranges by the original document. Sentence-v2 segmentation retains every character but does not split a sentence at formatting line breaks. Legacy line-v1 mapping remains reproducible.
- Duplicate voices in the same cluster keep the first author-ordered formal claim; later claims remain audited reserves. Different-cluster conflicts still require semantic correction.
- Selected-field repairs preserve source identity and untouched topics, require matching source/decision hashes, and remain inside cumulative budgets. Invalid shape is repairable; permission and timeout failures do not blindly retry.
- Reading order prioritizes interpretive title cues and delays duplicate titles/high-overlap text. No article is automatically labelled semantically excluded; all source records remain indexed.
- Standard-workbook mode reallocates 870 unused raw-normalization seconds: workbook 30, authoring 1290 and independent review 600. Total remains 3600 seconds, research cutoff 2700; other stage allocations and the delivery reserve are unchanged.
- Deterministic prose avoids duplicate exact-name attribution and uses a neutral reported-judgment heading frame, without inventing agreement or criticism.
- Public-comment HTTP-200 error/malformed payloads no longer count as empty successful pages.
- The process watchdog covers blocked stdin communication and checks both elapsed and wall time. Only the owned process tree is terminated.
- Independent-review rejection can trigger one local author repair and a fresh changed-item review inside the same cumulative stage budget. Separate repaired output, source-identity comparison, exact rejection set and unchanged prior verdicts are checked by the controller. No original hash is patched to match a new claim.
- Retained Weibo and Toutiao response normalizers preserve raw provenance and exclude non-human disclosed AI replies, emoji-only rows, out-of-window dates and repeat captures. The small-corpus semantic adapter compiles all sentiment/handoff files; platform coverage remains a separate actual collector audit.

## Real model observations

| Run | Observed outcome |
|---|---|
| Fresh standard-input complete invocation | 587.797 s, four-topic semantic response returned; duplicate-speaker compilation failure prevented independent review. Not a completed report. |
| Author repairs using that observed response | 373.515 s plus 222.687 s; separately recompiled draft passed source/coverage/density gates. Recovery only, not a fresh full-run timing. |
| Independent review with 300 s stage allowance | Request timed out at 291.594 s after cleanup margin, no completed response. |
| Independent review with 600 s stage allowance | 470.234 s; 15 fully supported and 5 partially supported verdicts. Original source inspection found four genuine missing-range problems and one mistaken segment reading. Rejected verdicts were preserved, so formal delivery remained blocked. |
| Public comment access | Direct public endpoint and browser attempts failed; an approved process-local fetch remained without a completed result until its timeout. User subsequently authorized a fresh isolated domestic-platform login. A live government-account post exposed a 16-comment count but an empty selected-comment list; the count was not converted into quotations. |
| Legacy large-stdin timeout reproduction | A 0.3 s inner timeout remained stuck until a 3 s outer safety watchdog fired (3.938 s including cleanup). The fixed same-input case exited in 1.156 s including process-tree cleanup. This reproduces a Windows timeout defect, not proof of the cause of the historical nine-hour run. |
| Further independent continuation | 481.609 s full diagnostic, including a 466.610 s reviewer call: 19/20 claims fully supported, one quote still ended before its last supporting paragraph. Formal delivery correctly remained blocked. |
| Authorized isolated Weibo capture | 16 real public posts; normalized capture retained 60 non-emoji, in-window rows for semantic review and 59 excluded rows (including one explicitly disclosed platform AI reply). These are capture/eligibility figures, not completed semantic labels or population sentiment. |
| New no-login Toutiao probe | Eight historical seed URLs returned 34 actual new comment responses within the monitoring window. Historical seed labels were not reused; this is a live adapter regression, not fresh discovery or a fresh end-to-end benchmark. |
| Small-corpus reviewer probes | A 60-row request timed out at 291.734 s without final labels. A 34-row request with process-local reasoning/output settings also timed out at 180.797 s. Host settings are not evidence that the backend honored a token limit. |

No formal Word/workbench package has yet passed the complete forward test. Independent review, real comment availability, overseas review, hotword review and final artifact QA remain acceptance conditions, not optional checks. Word generation without packaged page rendering is not visual QA success. Unit tests do not establish cross-model reliability, semantic correctness or a runtime speedup percentage.

Public-checkout validation before candidate publication: Skill validation passed, runtime preflight passed, and **416 tests passed / 7 environment skips** in 23.88 seconds. A simplified eight-comment probe also timed out at 91.109 seconds without final labels. The current complete invocation is still a diagnostic continuation; no fresh full-report success is claimed.
