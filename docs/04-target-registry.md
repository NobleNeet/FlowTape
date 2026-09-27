# FlowTape Target Registry

Status: initial specification before implementation

## 1. Principle

A scenario `target` is a logical human-readable name, not a selector.

Example:

```yaml
- action: click
  target: 保存
```

The DOM information required to locate `保存` is stored separately in the scenario-local `elements.yaml`.

Conceptually:

```text
scenario package
    -> identify current page
    -> resolve page-scoped logical target
    -> locator candidates
    -> current DOM element
```

## 2. Scenario-local ownership

The first implementation uses one DOM registry per scenario package rather than one global registry shared by unrelated scenarios.

Recommended layout:

```text
scenarios/
  注文処理/
    scenario.yaml
    elements.yaml
```

The `elements.yaml` located beside `scenario.yaml` is implicitly associated with that scenario.

Benefits:

- unrelated scenarios may use the same logical target names safely
- DOM repair impact stays local
- scenarios are portable as directories
- deletion/rename/reference validation remains predictable

Shared site/project registries may be introduced later as an explicit feature.

## 3. Page-scoped registry shape

A single scenario may navigate through URLs and DOM structures that differ substantially. Therefore targets are grouped by logical page scope.

Recommended initial format:

```yaml
version: 1

pages:
  login:
    identify:
      url:
        contains: /login

    elements:
      ユーザーID:
        kind: input
        locate:
          - by: label
            value: ユーザーID
          - by: name
            value: username
        expect:
          tag: input
          editable: true
        fingerprint:
          text: ユーザーID

      ログイン:
        kind: button
        locate:
          - by: role
            role: button
            name: ログイン
        expect:
          role: button
          enabled: true
        fingerprint:
          text: ログイン

  order_confirm:
    identify:
      all:
        - url:
            contains: /orders/
        - exists:
            role: heading
            name: 注文確認
        - exists:
            role: button
            name: 注文を確定

    elements:
      注文を確定:
        kind: button
        locate:
          - by: role
            role: button
            name: 注文を確定
        expect:
          role: button
          enabled: true
        fingerprint:
          text: 注文を確定
```

The separation between page identification, `locate`, `expect`, context, and diagnostic fingerprint data is intentional.

## 4. Page identification

A page definition may be identified by:

- URL conditions
- DOM conditions
- both together

URL alone must not be required because SPA-style interfaces may substantially change screen state without changing URL.

DOM evidence should be semantic where practical, such as distinctive headings, roles, labels, or controls.

Resolution rule:

```text
0 matching page definitions  -> UnknownPage
1 matching page definition   -> use it
2+ matching page definitions -> AmbiguousPage
```

The registry order must not be used as an implicit tie-breaker.

Page names are registry identifiers such as `login`, `dashboard`, or `order_confirm`. Normal scenario steps do not need to repeat them because FlowTape identifies the current page before target resolution.

## 5. Logical target names

Target names are user-facing and may be Japanese.

Examples:

```text
メールアドレス
ログイン
保存
注文を確定
```

A logical target name needs to be unique only within its page scope.

Thus this is valid:

```text
profile page:      保存
notification page: 保存
```

Within one page, contextual namespacing remains preferred when the same human-facing concept appears multiple times:

```text
配送先/編集
支払方法/編集
```

The `/` separator is a readable naming convention rather than a DOM path.

## 6. `kind`

`kind` is a semantic classification used for readability and action compatibility checks.

Initial useful kinds include:

- `button`
- `input`
- `textarea`
- `select`
- `checkbox`
- `radio`
- `link`
- `menu`
- `tab`
- `file`
- `element`

It is not itself a locator.

The validator may reject or warn about clearly incompatible operations, such as `input` against a button or `upload` against a non-file target.

## 7. `locate`

`locate` is an ordered list of independently useful ways to find a target.

Initial locator families include:

- `testid`
- `id`
- `name`
- `role`
- `label`
- `text`
- `placeholder`
- `attribute`
- `relative`
- `css`
- `xpath`

Example:

```yaml
locate:
  - by: role
    role: button
    name: 保存

  - by: testid
    value: profile-save
```

The Target Resolver tries persisted candidates in order while still applying uniqueness and expectation rules.

## 8. `expect`

`expect` describes what the resolved element is supposed to be.

It answers a different question from `locate`:

- `locate`: where/how can the target be found?
- `expect`: is the found element acceptable?

Example:

```yaml
expect:
  tag: input
  role: textbox
  input_type: email
  visible: true
  enabled: true
  editable: true
  attributes:
    autocomplete: email
```

Not every field should be emitted for every element. Expectations should prevent mistaken matches without over-constraining incidental presentation details.

## 9. Relative locators

When an element is not uniquely identifiable by itself, FlowTape may use surrounding semantic context.

Example:

```yaml
- by: relative
  anchor:
    text: 山田太郎
  relation: row
  target:
    role: button
    name: 編集
```

Typical relative contexts include:

- row
- dialog
- form
- section
- descendant of stable ancestor
- heading-associated area
- nearby text

A semantically stable relative locator may be stronger than a structural CSS path.

## 10. Ordered iframe and Shadow DOM context

Traversal context is separate from the element locator and is represented as an ordered sequence so mixed nesting can be expressed.

Example:

```yaml
context:
  - frame:
      id: payment-frame
  - shadow:
      css: app-shell
  - shadow:
      css: payment-panel
```

Conceptual resolution:

```text
current document
    -> enter frame
    -> enter shadow root
    -> enter shadow root
    -> apply locator candidate
    -> expectation validation
```

This representation also leaves room for mixed sequences such as frame -> shadow -> frame.

## 11. Unbound targets

Scenario YAML may temporarily reference a target that is not present in the applicable page scope.

This is valid while authoring but prevents successful normal execution.

Bind mode lets the user reach the intended page, select the real element, and create the missing definition through the Element Capture Engine.

## 12. Multiple matches

No ordinary locator means "use the first match" by default.

For each single-target locator candidate:

1. search within the current page/traversal/dynamic scope
2. inspect matches
3. apply expectations
4. accept only one resulting target

If multiple acceptable elements remain and later candidates cannot resolve the ambiguity, execution fails.

## 13. Positional matching

Position/index matching is supported only as a last-resort fragile fallback.

Example:

```yaml
- by: role
  role: button
  name: 編集
  index: 3
  fragile: true
```

Rules:

- never generate positional matching as the preferred candidate when a semantic alternative exists
- persisted positional definitions must be marked `fragile: true`
- fragility must be visible in diagnostics
- `nth-child`, absolute DOM position, and absolute XPath are treated similarly

## 14. Fingerprint

Each normal target definition should preserve a small diagnostic fingerprint when useful source information exists.

Example:

```yaml
fingerprint:
  text: 保存
  nearby_text:
    - プロフィール
  attributes:
    type: submit
```

Fingerprint uses include:

- DOM-change diagnostics
- explaining ambiguous or failed matches
- assisting repair/rebinding

Fingerprint is not a hidden fuzzy-click mechanism and must never bypass unique-resolution rules.

The registry should not store a full DOM snapshot merely to create a fingerprint.

## 15. What not to persist normally

Do not normally persist:

- complete DOM HTML
- every target attribute
- complete ancestor chains
- screen coordinates as identity
- every generated candidate
- candidate score tables
- rejected candidates

Those belong in diagnostics/logs where needed.

## 16. Candidate diversity

Persisted locator fallbacks should represent genuinely different evidence.

Bad fallback set:

```text
id=profile-save
CSS #profile-save
XPath //*[@id='profile-save']
```

All depend on the same ID.

Better:

```text
role + accessible name
stable test attribute
heading/section-relative locator
```

The Element Capture Engine should deduplicate by underlying evidence, not merely serialized syntax.

## 17. Collection definitions

`for_each` source definitions are semantically different from ordinary single-element targets.

A collection source may be captured by selecting one representative row/item and deriving candidate definitions that match the corresponding set.

Before persistence, FlowTape should preview/highlight current members so the user can confirm the intended collection.

Collection resolution intentionally permits multiple members and does not inherit the ordinary single-target uniqueness rule.

Collection definitions still belong to the current page scope.

## 18. Dynamic execution scope

Stable reusable DOM context belongs in `elements.yaml`; execution-time context such as the current `for_each` row belongs in scenario control flow.

For example, `within: ${row}` narrows resolution of a page-scoped logical target to the current collection member without duplicating selectors in scenario YAML.

## 19. Rename semantics

Renaming a logical target through FlowTape is an atomic semantic operation inside its page scope:

```text
old registry key
    -> new registry key
    -> update all known scenario references that refer to that page-scoped target
```

Known references must not be silently left pointing at the old name.

External/manual edits may create unresolved references; validation reports them normally.

## 20. Delete semantics

Deleting a registered target must account for scenario references.

If referenced, FlowTape should either:

- block deletion and show referencing locations, or
- require explicit destructive confirmation that knowingly leaves references unbound

Silent deletion of a referenced target is not allowed.

## 21. Persistence philosophy

`elements.yaml` should remain editable and understandable, but it is primarily machine-generated.

Normal creation/update paths are:

- Recorder
- Picker
- Bind
- Rebind/repair

Users may hand-edit it, but they should not be required to write complex DOM definitions from scratch.
