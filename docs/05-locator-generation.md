# FlowTape Locator Generation and Scoring

Status: initial specification before implementation

## 1. Purpose

The Element Capture Engine converts one user-indicated DOM element into a small set of stable, meaningful locator candidates.

It is not a CSS-selector generator. Its job is to answer:

> What evidence makes this element identifiable as the user's intended target?

The preferred result should remain understandable to a human and reproducible by the Player.

## 2. Processing pipeline

Conceptual flow:

```text
raw event target
    -> normalize actionable target
    -> build/receive ElementSnapshot
    -> generate semantic candidates
    -> validate candidates against current DOM
    -> generate contextual candidates if needed
    -> generate CSS fallback if needed
    -> generate XPath fallback if needed
    -> score/rank
    -> deduplicate by evidence source
    -> diversify fallbacks
    -> select top candidates
    -> generate expect/fingerprint
```

## 3. Target normalization

The deepest browser event target is not always the intended control.

Example:

```html
<button aria-label="保存">
  <svg>
    <path />
  </svg>
</button>
```

A click on the path should normally normalize to the actionable `button`.

The normalizer should examine ancestors for actionable semantics such as:

- `button`
- `a[href]`
- `input`
- `textarea`
- `select`
- `summary`
- `[contenteditable]`
- common interactive ARIA roles (`button`, `link`, `checkbox`, `radio`, `tab`, `menuitem`, etc.)

Generic JavaScript-clickable elements may be accepted as fallbacks when no better semantic target exists.

Recorder and Player must share or mirror this normalization behavior.

## 4. ElementSnapshot boundary

`ElementSnapshot` is the internal normalized browser-side capture model consumed by locator generation.

The **canonical runtime structure and field meanings are defined in `08-recorder-protocol.md`**. This document does not define a second DTO shape.

The locator generator may consume both the lightweight Stage 1 snapshot and, where still obtainable, the detailed Stage 2 snapshot described by the Recorder protocol.

Typical semantic evidence available through the canonical snapshot includes:

```text
tag/type
important attributes
explicit/computed role
accessible name
associated label
visible text
visible/enabled/editable/checked/selected state
meaningful heading/form/dialog/row context
frame/shadow traversal evidence
```

A full DOM snapshot is not required and must not be persisted wholesale into `elements.yaml`.

If an operation immediately navigates away, Stage 1 evidence captured at event time may be the only available source. Locator generation must therefore tolerate missing optional Stage 2 context instead of requiring the old DOM to remain alive.

## 5. Candidate generation order

Candidate generation proceeds from semantic/local evidence toward structural fallback.

### 5.1 Explicit test attributes

Recognize known automation-oriented attributes such as:

- `data-testid`
- `data-test`
- `data-cy`
- `data-qa`

Example:

```html
<button data-testid="checkout-submit">
```

Candidate:

```yaml
by: testid
value: checkout-submit
```

Do not treat every `data-*` attribute as a high-quality test ID.

### 5.2 Stable ID

Example:

```html
<input id="email">
```

Candidate:

```yaml
by: id
value: email
```

IDs that appear generated or session-dependent are heavily penalized.

### 5.3 ARIA role + accessible name

Example:

```html
<button>保存</button>
```

Candidate:

```yaml
by: role
role: button
name: 保存
```

Accessible-name computation must use the shared DOM semantics defined for Recorder/Player and may draw from `aria-labelledby`, `aria-label`, associated labels, control text, image alt text, and other applicable accessibility sources.

### 5.4 Associated label

Example:

```html
<label for="email">メールアドレス</label>
<input id="email">
```

Candidate:

```yaml
by: label
value: メールアドレス
```

Nested-label and equivalent accessible-label relationships should also be recognized.

### 5.5 `name`

Example:

```html
<input name="email">
```

Candidate:

```yaml
by: name
value: email
```

`name` is common enough to justify a dedicated locator family.

### 5.6 Placeholder

Example:

```html
<input placeholder="メールアドレスを入力">
```

Candidate:

```yaml
by: placeholder
value: メールアドレスを入力
```

Placeholder is useful but normally weaker than a proper label.

### 5.7 Visible text

Example:

```html
<button>注文を確定</button>
```

Candidate:

```yaml
by: text
value: 注文を確定
exact: true
```

Text is normalized according to shared DOM semantics. Very long or obviously volatile text is normally unsuitable as a primary locator.

### 5.8 Purposeful attributes

Stable attributes such as a meaningful `href` or `data-action` may become `attribute` candidates when no more specific locator family applies.

Avoid tokens, session IDs, unstable query values, framework internals, and presentation-only state.

## 6. Candidate validation against current DOM

Every generated locator must be tested against the current DOM using Player-compatible matching semantics.

Record at least:

- match count
- whether the captured target is among the matches
- whether matched elements satisfy expected basic semantics

A locator that cannot reproduce the captured target is invalid even if it looks meaningful syntactically.

## 7. Contextual candidate generation

When a semantic locator is not unique, combine it with meaningful context before falling back to long structural selectors.

Supported initial semantic relationships include:

- stable ancestor / descendant
- heading/section context
- table/list row context
- dialog context
- form context
- nearby-text context

Examples:

```yaml
by: relative
anchor:
  role: heading
  name: プロフィール
relation: section
target:
  role: button
  name: 保存
```

```yaml
by: relative
anchor:
  text: 山田太郎
relation: row
target:
  role: button
  name: 編集
```

A nearby-text relationship is weaker than a true label relationship and should score accordingly.

## 8. CSS fallback generation

CSS is supported after stronger semantic/contextual candidates.

Prefer short selectors based on meaningful attributes/classes.

Good fallback examples:

```css
button[data-action="save"]
.profile-panel > button.save
```

Avoid by default:

```css
body > div:nth-child(3) > div:nth-child(2) > button
```

Do not walk from `body` merely to force uniqueness when meaningful context is available.

## 9. Class filtering

Do not blindly use all classes.

Prefer classes that appear semantically purposeful, such as:

```text
profile-save
checkout-submit
primary-action
```

Penalize or ignore obvious hash/generated classes, framework-internal classes, and utility/layout classes.

Examples commonly unsuitable as identity evidence:

```text
css-18a91pf
MuiButton-root
px-4
text-sm
flex
```

## 10. XPath fallback generation

XPath is a valid fallback, not an error by definition.

Prefer higher-level semantic locator families when they express the same concept.

Absolute XPath such as:

```xpath
/html/body/div[2]/div[3]/div[1]/button[2]
```

is an extreme fallback and should be marked fragile if persisted at all.

## 11. Scoring model

Candidate ranking uses multiple independent dimensions.

Recommended total: 100 points.

| Dimension | Maximum |
|---|---:|
| Stability | 35 |
| Uniqueness | 25 |
| Semantic meaning | 20 |
| Target fit | 10 |
| Simplicity | 10 |

Penalties are then applied for known fragility signals.

## 12. Stability (35)

High-value evidence typically includes explicit stable test attributes, meaningful stable IDs, associated labels, role + accessible name, and stable `name` values.

Lower-value evidence includes presentation classes, DOM depth/path, and positional/index dependence.

Dynamic/generated-value detection is heuristic and should penalize UUID/hash/random/numeric/framework-generated patterns without claiming that any particular framework is always unstable.

## 13. Uniqueness (25)

Recommended initial mapping:

| Current DOM matches | Score |
|---|---:|
| 1 | 25 |
| 2 | 12 |
| 3-5 | 5 |
| 6+ | 0 |

A non-unique semantic candidate may still be valuable as part of a relative locator.

## 14. Semantic meaning (20)

High semantic value includes labels, role + accessible name, meaningful test IDs/IDs, and visible control text.

Low semantic value includes positional CSS, structural XPath, and arbitrary ancestor depth.

When stability is comparable, a semantic representation should rank above a long structural selector.

## 15. Target fit (10)

Target fit measures whether the candidate addresses the actionable element itself rather than an incidental child.

Actionable control itself -> high.

Internal `span`/`svg`/`path` -> low unless no actionable semantic parent exists.

## 16. Simplicity (10)

When correctness/stability are comparable, prefer simpler representations:

```text
single semantic condition
> small semantic combination
> concise relative locator
> short CSS
> long CSS
> long XPath
```

Simplicity never overrides correctness or uniqueness.

## 17. Fragility penalties

Recommended initial penalty signals include:

| Signal | Example penalty |
|---|---:|
| UUID-like value | -25 |
| random/hash-like value | -20 |
| mostly numeric dynamic ID | -15 |
| CSS-in-JS class | -20 |
| `nth-child` dependence | -25 |
| explicit index dependence | -25 |
| absolute XPath | -35 |
| CSS path from body/root | -25 |
| excessive class conjunction | -10 |
| highly locale-sensitive/volatile text | -5 to -15 |
| current value/state used as identity | -20 |

Exact numeric tuning may change after real-world tests, but the dimensions and intent remain stable.

## 18. Hard validation before scoring

Scoring is not a substitute for basic validity.

Reject or downgrade candidates that violate hard rules, including:

- no match
- captured target not among matches
- contradiction with target semantics
- only hidden/non-operable matches for an action that requires operability
- incidental child selected where actionable normalization should have chosen a parent

Pipeline:

```text
hard validation
    -> scoring
    -> ranking
```

## 19. Candidate-generation phases and early stopping

Avoid candidate explosion.

Recommended phases:

```text
Phase 1: semantic/local candidates
Phase 2: relative/context candidates
Phase 3: CSS fallback
Phase 4: XPath/positional emergency fallback
```

If enough independent Strong/Good candidates exist, stop before lower-quality phases.

## 20. Quality bands

Recommended initial score interpretation:

| Score | Band |
|---:|---|
| 85-100 | Strong |
| 70-84 | Good |
| 50-69 | Weak |
| 0-49 | Fragile |

Persist Strong/Good candidates preferentially. Weak candidates are fallbacks. Fragile candidates are retained only when necessary and must be marked.

## 21. Persisted candidate count

Normal target definitions should store approximately:

- 1 primary locator
- 1-2 independent fallback locators

Large mechanically generated candidate lists reduce maintainability without guaranteeing robustness.

## 22. Deduplication by evidence source

These are not independent fallbacks:

```text
id=profile-save
CSS #profile-save
XPath //*[@id='profile-save']
```

They all depend on the same ID.

Retain only the best representation from redundant evidence groups.

## 23. Fallback diversity

Prefer fallbacks based on genuinely different evidence.

Desirable example:

```text
Primary: role + accessible name
Fallback 1: stable test ID
Fallback 2: section/heading-relative locator
```

## 24. Score persistence

Raw candidate scores are diagnostics/internal metadata and should not normally clutter `elements.yaml`.

The persisted registry contains selected locator definitions; scoring/rejected-candidate detail belongs in diagnostics.

## 25. `expect` generation

Generate a minimal useful expectation set.

Button example:

```yaml
expect:
  role: button
  enabled: true
```

Input example:

```yaml
expect:
  tag: input
  input_type: email
  editable: true
```

Do not over-constrain incidental presentation details.

## 26. Fingerprint generation

Preserve a small diagnostic fingerprint when useful source information exists, for example:

```yaml
fingerprint:
  text: 保存
  nearby_text:
    - プロフィール
  attributes:
    type: submit
```

Fingerprint supports diagnostics/repair only. It is not a hidden fuzzy locator and must never bypass normal resolver uniqueness/expectation rules.

## 27. Recorder/Player compatibility requirement

Candidate validation must use matching semantics that the Player can reproduce.

The generator must not emit a persisted primary candidate whose accessible-name, role, visibility, label, context traversal, or locator behavior depends on Recorder-only logic.

Shared DOM semantics and the canonical ElementSnapshot boundary are specified in `08-recorder-protocol.md`; persisted locator/expect shapes are specified in `07-data-schema.md`; runtime fallback and uniqueness behavior are specified in `09-runtime-semantics.md`.

## 28. Future observed-stability improvement

A later version may compare repeated observations of the same logical target.

Changing values across observations can provide evidence that an ID/attribute is dynamic; repeatedly stable semantic evidence may gain confidence.

This is a future enhancement and not required for the first implementation.
