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
    -> build ElementSnapshot
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

## 4. ElementSnapshot

Before generating locators, the browser side should collect a normalized snapshot.

Conceptual internal model:

```yaml
tag: button
id: checkout-submit
name: null
type: submit

role:
  explicit: button
  computed: button

accessible_name: 注文を確定
text: 注文を確定

attributes:
  data-testid: checkout-submit
  aria-label: 注文を確定
  class:
    - button
    - primary

state:
  visible: true
  enabled: true
  editable: false

relations:
  label: null
  form: 購入フォーム
  heading: ご注文内容
  row: null
  dialog: 注文確認
```

This is an internal capture model. It is not persisted wholesale into `elements.yaml`.

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

Accessible name computation should reflect browser accessibility semantics, including relevant sources such as:

- `aria-labelledby`
- `aria-label`
- associated label
- button text
- image alt text where applicable

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

`name` is common enough to justify a dedicated locator family rather than representing it only as a generic attribute.

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

Placeholder is semantically useful but normally less stable than a proper label.

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

Text should be normalized by trimming edge whitespace and collapsing unnecessary internal whitespace/newlines.

Very long text is generally unsuitable as a primary locator.

### 5.8 Href and other purposeful attributes

Useful stable attributes may be candidates, for example:

```html
<a href="/account/settings">設定</a>
```

or:

```html
<button data-action="submit-order">
```

These serialize through `attribute` when no more specific family applies.

Avoid attributes that contain tokens, session IDs, unstable query values, framework internals, or purely presentational state.

## 6. Candidate validation against current DOM

Every generated locator must be tested against the current DOM using Player-compatible matching semantics.

Record at least:

- number of matches
- whether the captured element is among those matches
- whether matched elements satisfy the expected basic semantics

A locator that does not reproduce the captured element is not a valid candidate even if it looks meaningful syntactically.

## 7. Contextual candidate generation

When a semantic locator is not unique, combine it with meaningful context rather than immediately falling back to a long CSS path.

### 7.1 Stable ancestor

Example:

```html
<section id="profile">
  <button>保存</button>
</section>
```

Conceptual candidate:

```yaml
by: relative
anchor:
  id: profile
relation: descendant
target:
  role: button
  name: 保存
```

### 7.2 Heading/section context

Example:

```html
<section>
  <h2>プロフィール</h2>
  <button>保存</button>
</section>
```

Conceptual locator:

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

### 7.3 Table/list row context

Example:

```text
山田太郎   [編集]
鈴木一郎   [編集]
```

Conceptual locator:

```yaml
by: relative
anchor:
  text: 山田太郎
relation: row
target:
  role: button
  name: 編集
```

### 7.4 Dialog context

Conceptual locator:

```yaml
by: relative
anchor:
  role: dialog
  name: 注文取消
relation: descendant
target:
  role: button
  name: 確認
```

### 7.5 Form context

Conceptual locator:

```yaml
by: relative
anchor:
  role: form
  name: ログイン
relation: descendant
target:
  role: button
  name: 送信
```

### 7.6 Nearby text/sibling context

Use nearby text when markup lacks proper label semantics.

Example:

```text
契約番号  [input]
```

A nearby-text relationship is weaker than a true label relationship and should score accordingly.

## 8. CSS fallback generation

CSS is a supported locator family, but structural CSS is generated after stronger semantic/contextual candidates.

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

Limit ancestor depth when building structural CSS. Do not walk from `body` merely to force uniqueness if a more meaningful contextual representation can be built.

## 9. Class filtering

Do not blindly use all classes.

Prefer classes that appear semantically purposeful, such as:

```text
profile-save
checkout-submit
primary-action
```

Penalize or ignore:

- obvious hash-like classes
- CSS-in-JS generated names
- framework-internal classes
- utility-only classes such as layout/spacing tokens

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

A concise semantic XPath can be stable, but when the same concept can be represented through a higher-level locator family, prefer that higher-level representation.

Absolute XPath such as:

```xpath
/html/body/div[2]/div[3]/div[1]/button[2]
```

is an extreme fallback and should be marked fragile if persisted at all.

## 11. Scoring model

Candidate ranking uses multiple independent dimensions rather than a single hard-coded selector-type priority.

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

Stability estimates whether the locator evidence is likely to preserve the same meaning across future page loads.

Typical high-value evidence:

- explicit stable test attribute
- meaningful stable ID
- associated label
- role + accessible name
- stable `name`

Typical lower-value evidence:

- presentation class
- DOM depth/path
- index/position

This is not a permanent per-type constant. The actual value matters.

Example:

```text
id=user-profile-save     -> likely stable
id=button-839274         -> suspicious
id=550e8400-e29b-...     -> highly suspicious
```

## 13. Dynamic/generated-value detection

Apply penalties for values resembling:

- UUIDs
- hashes
- long numeric sequences
- random alphanumeric IDs
- framework-generated identifiers
- CSS-in-JS class names

Examples:

```text
btn-839274
ember1837
react-select-7-input
radix-generated IDs
css-1x23kj4
```

This detection should be heuristic and diagnostic, not a claim that a particular framework can never expose stable IDs.

## 14. Uniqueness (25)

Recommended initial mapping:

| Current DOM matches | Score |
|---|---:|
| 1 | 25 |
| 2 | 12 |
| 3-5 | 5 |
| 6+ | 0 |

A non-unique semantic candidate may still be valuable as the target portion of a relative locator.

## 15. Semantic meaning (20)

This dimension asks whether the locator explains the target in human terms.

Typical high semantic value:

- label
- role + accessible name
- meaningful test ID
- meaningful ID
- visible button/link text

Typical low semantic value:

- positional CSS
- structural XPath
- arbitrary ancestor depth

The intent is that, when stability is comparable, this:

```yaml
by: role
role: button
name: 注文を確定
```

ranks above a long structural CSS path.

## 16. Target fit (10)

Target fit measures whether the candidate addresses the actionable element itself rather than an incidental child.

Examples:

- actionable button/control itself -> high
- internal `span`/`svg`/`path` -> low unless no actionable semantic parent exists

Normalization and target-fit scoring work together.

## 17. Simplicity (10)

When two locators are comparably stable and meaningful, prefer the simpler representation.

Conceptual preference:

```text
single semantic condition
> two-condition combination
> concise relative locator
> short CSS
> long CSS
> long XPath
```

Simplicity must never override correctness or uniqueness.

## 18. Fragility penalties

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

Exact numeric tuning may change after real-world tests, but the dimensions and intent should remain stable.

## 19. Hard validation before scoring

Scoring is not a substitute for basic validity.

Before ranking, reject or downgrade candidates that violate hard rules, for example:

- no match at all
- captured target is not among matches
- candidate contradicts the target's required semantics
- only hidden/non-operable matches exist for an operation that requires visibility
- candidate addresses an incidental child that should have been normalized to an actionable ancestor

The pipeline is:

```text
hard validation
    -> scoring
    -> ranking
```

## 20. Candidate-generation phases and early stopping

Do not generate every possible combination.

Recommended phased strategy:

```text
Phase 1: semantic/local candidates
    -> if enough Strong/Good independent candidates exist, stop

Phase 2: relative/context candidates
    -> if enough Strong/Good independent candidates exist, stop

Phase 3: CSS fallback

Phase 4: XPath/positional emergency fallback
```

This prevents candidate explosion and keeps diagnostics understandable.

## 21. Quality bands

Recommended initial score interpretation:

| Score | Band |
|---:|---|
| 85-100 | Strong |
| 70-84 | Good |
| 50-69 | Weak |
| 0-49 | Fragile |

Persist Strong/Good candidates preferentially.

Weak candidates are fallbacks.

Fragile candidates should only be persisted when no stronger representation exists and must be marked accordingly.

## 22. Persisted candidate count

Normal target definitions should store approximately:

- 1 primary locator
- 1-2 independent fallback locators

A large list of mechanically generated alternatives reduces maintainability without necessarily improving robustness.

## 23. Deduplication by evidence source

These are not independent fallbacks:

```text
id=profile-save
CSS #profile-save
XPath //*[@id='profile-save']
```

They all depend on the same ID.

The generator should track the underlying evidence source and retain only the best representation from a redundant group.

## 24. Fallback diversity

Prefer fallback candidates based on different evidence.

Example desirable set:

```text
Primary: role + accessible name
Fallback 1: stable test ID
Fallback 2: section/heading-relative locator
```

This improves resilience to one type of page change.

## 25. Score persistence

Raw candidate scores are primarily diagnostics/internal metadata.

They should not normally clutter `elements.yaml`.

A debug log may show:

```text
92  role(button, "ログイン")
88  id(login-submit)
61  css(form.login button)
24  absolute xpath
```

but the persisted registry should normally contain only the selected definitions.

## 26. `expect` generation

After selecting locators, generate a minimal useful expectation set.

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

## 27. Fingerprint generation

Preserve a small diagnostic fingerprint when useful source information exists, for example:

```yaml
fingerprint:
  text: 保存
  nearby_text:
    - プロフィール
  attributes:
    type: submit
```

Fingerprint is supporting evidence for diagnostics/repair, not a license for fuzzy implicit clicking. It must not be used to bypass the resolver's normal uniqueness and expectation rules.

## 28. Future observed-stability improvement

A later version may compare repeated observations of the same logical target.

Example:

```text
previous id: btn-82931
current id:  btn-93822
```

This is evidence that the ID is dynamic and should be downgraded.

Conversely, repeatedly stable semantic attributes may gain confidence.

This is a future enhancement and not required for the first implementation.