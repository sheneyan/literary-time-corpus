# extract-v2 o'clock rule design

## Goal

Fix the two concrete extraction gaps found by the first five-book local smoke
test: recognize English `o'clock` hour expressions and stop treating
`noon hours` or `midnight hours` as exact clock instants.

## Scope

This change is deliberately limited to:

- numeric hours from 1 through 12 followed by `o'clock`;
- English hour words from one through twelve followed by `o'clock`;
- straight and curly apostrophes and case-insensitive spelling;
- the approximate prefixes `about` and `approximately`; and
- the lexical period phrases `noon hour(s)` and `midnight hour(s)`.

It does not add French rules, contextual AM/PM resolution, expressions such as
`eight in the evening`, or a general natural-language time parser.

## Rule behavior

Approximate expressions such as `About 8 o'Clock` and `approximately eight
o’clock` produce one candidate with:

- `precision=approximate`;
- `status=automatically-excluded`;
- no normalized time; and
- `exclusionReasonCodes=["approximate-expression"]`.

Non-approximate expressions such as `8 o'clock` and `eleven o'Clock` produce
one candidate with:

- `precision=exact-minute-ambiguous`;
- two normalized values twelve hours apart, both at minute `00`; and
- `warningReasonCodes=["missing-meridiem"]`.

Approximate matching runs before exact-hour matching. The existing occupied
span mechanism prevents the inner `8 o'Clock` from becoming a second candidate.

The named-time rule continues to resolve standalone `noon` as `12:00` and
standalone `midnight` as `00:00`. It produces no candidate when either word is
immediately followed by singular or plural `hour`, ignoring case and allowing
ordinary whitespace.

## Versioning

The extraction contract changes from `extract-v1` to `extract-v2` in both
candidate production and candidate validation. Changed rule semantics use:

- `approx-about-oclock-v2` for approximate o'clock expressions;
- `oclock-hour-v1` for non-approximate o'clock expressions; and
- `named-noon-midnight-v2` for accepted named-time expressions.

The schema remains `time-candidate-v1`. The package version remains `0.1.0`
while this behavior is evaluated locally; a later decision may publish it as a
new software release.

## Tests and real-source smoke check

Repository tests use only synthetic sentences. They cover numeric and word
hours, both apostrophes, mixed capitalization, approximate precedence, the two
ambiguous normalized times, and rejection of singular and plural named-time
period phrases. Existing exact time families must remain unchanged apart from
their carried extraction version.

After the automated suite passes, rescan the five user-supplied local TXT files
without committing their text or outputs. The expected targeted result is:

- pg26621: two candidates, one approximate/excluded and one exact/ambiguous;
- pg37539: zero candidates after removing the `noon hours` false positive; and
- pg4852, pg46721, and pg33553: unchanged at zero candidates.

The French pg46721 result is recorded only as an exploratory run and is not an
English extraction-quality measurement.
