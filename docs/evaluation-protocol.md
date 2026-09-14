# Pilot evaluation protocol

## Evaluation boundary

The development set is used to create expression rules, filters, and resolution
logic. It is not used to report final quality. The 48-work held-out set is
frozen before its first extraction run.

If a person changes extraction, normalization, or resolution behavior after
inspecting held-out results, the affected results are invalidated. The report
must identify the new version and rerun the complete held-out evaluation.

## Unit of evaluation

The primary unit is a candidate source span, not an excerpt assembled around
it. Two rules that identify the same span in the same analysis snapshot produce
one deduplicated candidate.

Human reviewers classify whether the span denotes a clock time, whether it is
minute-exact, whether AM or PM is resolved, whether the excerpt and attribution
are faithful, and whether rights evidence is complete.

## Candidate precision

For a reviewed set of automated candidates:

```text
clock precision = candidates confirmed as clock times / reviewed candidates

publishable-exact precision = candidates confirmed exact-minute-resolved
                              / reviewed candidates
```

Report both metrics overall and by rule family. Include numerator, denominator,
percentage, and a 95% Wilson confidence interval. Automatically excluded spans
are reported separately and are not added to the precision denominator unless
they were sampled for filter auditing.

If the held-out set produces at most 2,000 candidates, review all of them. If it
produces more, draw a deterministic rule-stratified sample capped at 2,000,
report sampling weights, and report the remainder as backlog.

## Recall estimate

Recall is estimated independently of extractor output:

1. select random fixed windows from held-out analysis texts using the committed
   seed `literary-time-corpus-recall-v1`;
2. annotate every clock-time expression in those windows before showing
   extractor output to the annotator;
3. reconcile the gold annotations through second review;
4. run the frozen extractor; and
5. compare deduplicated source spans.

Begin with 250,000 annotated words distributed across all held-out strata and
at least one window from every work. If this yields fewer than 30 gold minute-
exact expressions, extend the same deterministic sampling procedure in
50,000-word increments, stopping at 500,000 words. Low prevalence at the cap is
a result and must not be replaced with candidate-centered windows.

Report separately:

```text
clock recall = detected gold clock spans / all gold clock spans

publishable-exact recall = detected gold exact-minute-resolved spans
                           / all gold exact-minute-resolved spans
```

Include numerator, denominator, percentage, 95% Wilson interval, and false-
negative classes.

## Minute coverage

Coverage uses only accepted candidates whose United States and China-mainland
rights assessments both pass, whose precision is `exact-minute-resolved`, and
which have one normalized value:

```text
exact minutes covered = count(distinct normalized HH:MM values)
coverage proportion = exact minutes covered / 1440
```

Also report:

- entries and distinct works per minute;
- covered minutes per hour;
- consecutive uncovered runs;
- alternative count per covered minute;
- ambiguous reserve candidates by possible minute;
- concentration by work and author; and
- coverage before and after limiting each author to one entry per minute.

If candidate review is capped before exhaustion, label coverage as a lower
bound. Do not extrapolate missing minutes from the reviewed sample.

## Human-review cost

Measure active review time from presentation of a complete review item to its
submitted decision. Pause timing when the reviewer leaves the item inactive or
must wait for missing evidence.

Report candidate counts and time separately for:

- time interpretation review;
- excerpt and attribution review;
- rights review; and
- second review or disagreement resolution.

For each category, report median, P90, total active time, accepted-entry time,
and the proportion requiring escalation. Do not combine automated runtime with
human-review time.

## Double review and disagreement

Independently double-review all candidates proposed as publishable plus a
deterministic 20% sample of other held-out review candidates, with a minimum of
100 double-reviewed candidates when at least 100 exist.

Report raw agreement for clock/not-clock, precision class, normalized minute,
and accept/reject decision. Report Cohen's kappa only where both reviewers use
the same categorical vocabulary and the sample contains more than one observed
class. All disagreements affecting publishability require adjudication.

## False-positive and false-negative taxonomy

At minimum, distinguish:

- date or year;
- price or quantity;
- duration or elapsed time;
- age, chapter, verse, page, score, or coordinate;
- non-clock number punctuation;
- clock time without minute precision;
- exact minute with unresolved day period;
- missed numeric expression;
- missed written-number expression;
- missed `past`, `to`, `quarter`, or `half` construction;
- missed noon, midnight, or clock-strike construction; and
- context-resolution error.

New recurring classes may be added, but existing result labels must not be
renamed after held-out evaluation without a version change.

## Required report contents

The feasibility report must include:

1. frozen manifests, seeds, and software or rule versions;
2. exclusions and deviations from the pilot design;
3. precision and recall estimates with counts and intervals;
4. minute and hour coverage without extrapolation;
5. human-review cost distribution;
6. duplicate and concentration analysis;
7. rights decisions, unresolved cases, and backlog;
8. major error classes and limitations; and
9. evidence supporting a stop, revision, or scale recommendation.

The report must not define success retroactively. A product coverage threshold
may be proposed only after the first measured pilot is presented.
