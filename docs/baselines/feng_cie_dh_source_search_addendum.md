# Feng CIE-DH Phase A source-search addendum

Search closed on 2026-09-03 after a bounded local-only pass.  The original
executable CIE-DH implementation and its numeric moving/stopped penalty
coefficients were **not recovered**.  The search did recover substantially
better primary evidence than the earlier source inventory: the paper-era
algorithm description, the revision response that says how the comparison was
created, its flowchart, and the exact 28,506-bag result workbook.

The resulting identity decision is therefore:

- the source-exact track remains `SOURCE_NOT_RECOVERED`;
- the runnable track may proceed as
  `FENG_PAPER_ENV_CIE_DH_RECONSTRUCTION`;
- undisclosed coefficients and execution details must remain frozen,
  declared reconstruction assumptions with a pre-result sensitivity envelope;
- no common-executor CIE-DH result may be relabelled as this reconstruction.

## Search surfaces and negative evidence

| Surface | Bounded check | Result |
| --- | --- | --- |
| Standalone old project | `C:\PROGRAMING\czr004\jichang_origin` | `HEAD`, `main`, and `origin/main` are the single initial commit `c5c2d2cb050f62b5160cdfb6c29895f03af12486`; no tags, alternate branches, unreachable/dangling objects, garbage, untracked files, or earlier reflog state. `git count-objects -v` reports 238 loose objects. |
| Paper-material Java project | `C:\STUDY\民航二所项目相关\冯汝琛相关材料\冯汝琛相关材料\ICS项目\代码-ICSsimulation` | Exactly 15 Java files and 28 class files.  Relative paths and SHA-256 values match the standalone project file-for-file for both sets.  There is no extra binary-only DH class. |
| Java mechanism scan | both source trees above, plus the repository's frozen mirror | No relevant `CIE-DH`, decentralized, moving/stopped, `HOLD`, `BTI`, `DDI`, 0.2-second, or penalty implementation.  The executable chain is the HCA/A* chain.  `ICS_GUI.cycle = 200` is explicitly a refresh interval and reaches `Thread.sleep(gui.getCycle())`; it is not evidence of a DH simulation tick. |
| Current repository history | all refs, code history and filenames | CIE-DH hits belong to recent adapted baselines, reports, and runners.  No historical Feng DH Java source or coefficient table was found. |
| IDE/local-history/archive pass | old project metadata, bounded `C:\PROGRAMING` and user Eclipse-history locations, Downloads archives, and the Feng material root | Only normal Eclipse project metadata was present; no Eclipse `.history` recovery.  `JAVAcode (2).zip` is unrelated tutorial code, the other inspected Downloads ZIPs are patent documents, and the Feng material root contains no source archive. |

This is a bounded non-recovery statement, not a claim that the source cannot
exist elsewhere.

## Recovered primary algorithm contract

The strongest paper-era description is in:

`C:\STUDY\民航二所项目相关\冯汝琛相关材料\冯汝琛相关材料\毕业设计\毕业论文-2019210484-冯汝琛-基于物联网的机场行李处理系统动态路由规划方法-物流工程-戚铭尧.pdf`

Section 5.2, PDF file page 43 (printed page 29), and Table 5.3 establish the
following facts:

1. the comparison used the same parameter settings and demand input, with
   conveyor speed `2.5 m/s`;
2. each bag is updated every `0.2 s` until all bags reach their destinations;
3. a bag advances when no bag is ahead or the bag ahead is moving; otherwise
   it stays and becomes stopped;
4. before leaving a node, the bag chooses the outgoing continuation with the
   least expected travel time;
5. expected travel time is free-motion time on a shortest path plus penalties
   from moving and stopped bags on that path, with stopped bags penalized more;
6. a bag waits at the node when the first position of its selected outgoing
   conveyor contains a stopped bag; and
7. the reported decentralized min/mean/max THT values are
   `3.56 / 4.43 / 8.62 min`.

Two additional revision artifacts independently preserve this mechanism:

- `C:\STUDY\民航二所项目相关\冯汝琛相关材料\冯汝琛相关材料\CIE\Detailed Response to Reviewers V2.docx`, response to reviewer comment 4, body paragraphs P108-P114 in OOXML order;
- `C:\STUDY\民航二所项目相关\冯汝琛相关材料\冯汝琛相关材料\CIE\manuscript-ics 一审修改后查验.pdf`, PDF file/printed page 25.

The response says the comparison simulator was developed **“from scratch”**
for the revision, using the same parameters and demand profile.  It also says
the location/state of all bags is updated **“one by one”**.  The Chinese thesis
says “一次更新所有行李的位置和状态”.  These wordings establish that every
bag is updated during the 0.2-second cycle, but they do not uniquely specify
container traversal order, mutation visibility, or a snapshot/simultaneous
commit; in particular, they cannot be used to infer container-order mutation.
Consequently, a deterministic snapshot/plan/resolve/commit cycle is a
reasonable reconstruction choice, but it is not a recovered source-exact
semantic and must not be labelled `FROZEN_PAPER_SEMANTIC`.

The paper-era flowchart is:

`C:\STUDY\民航二所项目相关\冯汝琛相关材料\冯汝琛相关材料\ICS项目\ICS相关文档\分散启发式方法.graffle`

It is a zipped OmniGraffle document, SHA-256
`688C7121EAF0D0550E7738098165960E3AC5B7504163BEE19C41D2F778DF262C`.
Its visible labels confirm only the coarse loop—initialize, update bag
position/state, test arrival at a node, determine the outgoing conveyor, test
all tasks complete, end.  It contains no scorer formula or penalty value.

## Recovered exact historical output

The comparison workbook exists at two byte-identical paper-material paths:

- `C:\STUDY\民航二所项目相关\冯汝琛相关材料\冯汝琛相关材料\毕业设计\仿真结果数据整理（与分散启发式方法对比）.xlsx`;
- `C:\STUDY\民航二所项目相关\冯汝琛相关材料\冯汝琛相关材料\ICS项目\项目仿真（数据+分析）\仿真结果数据整理（与分散启发式方法对比）.xlsx`.

Both are 6,914,970 bytes, last modified 2022-05-26 19:41:49 +08:00, and
have SHA-256
`E8EE03FE5C75FFF2BEC88251566521E3E6283D549F5676BE624C55E050F771FB`.
Read-only OOXML inspection of sheet `分散启发式算法` found:

- dimension `A1:O43605` and 43,603 segment records;
- 28,506 raw task IDs, exactly `0..28505`;
- 13,409 one-segment and 15,097 two-segment tasks, with no other multiplicity;
- 28,506 cached per-task THT values in column `I`;
- cached aggregation cells
  `J2=MAX(I:I)/60=8.6200000000000117`,
  `J3=AVERAGE(I:I)/60=4.4265355246849669`, and
  `J4=MIN(I:I)/60=3.5549999999999877`.

The workbook's segment aggregation formula is:

```text
_xlfn.IFS(
  COUNTIF($A:$A,$A2)=1, $E2-$D2,
  COUNTIF($A:$A,$A2)=2, $E2-$D2+$E3-$D3
)
```

Thus the historical Table 5.3 THT view sums each segment's own
`end - start` duration.  For a two-segment bag it does **not** include the gap
between the end of the first segment and the start of the second.  This supports
the reconstruction's separate processed-segment view, while requiring raw-entry
and scheduled-release views to remain separately labelled.

The workbook contains cached outputs and spreadsheet aggregation only: no VBA,
external link, embedded simulator, moving/stopped coefficient, or other route
decision code.

## What the references do not recover

The thesis identifies its comparison as adapted from Tarău et al.'s 2009 route
choice work.  Local copies of the closely related 2009/2010 Tarău papers and the
Tarău thesis describe junction-local switch priorities and state that their
weighting parameters are calibrated offline or previously calibrated.  That
mechanism is not the same executable contract as Feng's simplified
moving/stopped shortest-path penalty description, and the local papers do not
disclose a numeric moving/stopped pair for the Feng simulator.  Their switch
weights therefore cannot be imported as Feng coefficients.

The following details remain undisclosed and must be represented in the
assumption ledger rather than silently inferred:

- numeric moving and stopped penalties;
- the physical meaning/length of a “position” and how carrier footprint or
  safety headway maps to it;
- within-tick iteration order and whether earlier moves are visible to later
  bags;
- merge/edge-entry contention when multiple bags request the same position;
- equal-score route tie-breaking;
- release-time rounding to the 0.2-second lattice;
- fractional edge-length handling and the exact completion instant.

## Phase B consequence

Phase A does not justify further source hunting before implementation.  It does
justify a paper-environment reconstruction anchored to the recovered `map2` and
input files, with the source facts above held fixed and every remaining choice
declared before formal results are inspected.  Validation against the workbook
is a historical-output proximity and population-accounting check; because the
source and coefficients are absent, it cannot upgrade the result to
`EXACT_SOURCE_REPRODUCTION`.
