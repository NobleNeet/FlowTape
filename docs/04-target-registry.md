# FlowTape Target Registry

Status: initial specification before implementation

## 1. Principle

A scenario `target` is a logical human-readable name, not a selector.

Example:

```yaml
- action: click
  target: ログイン
```

The DOM information required to locate `ログイン` is stored separately in `elements.yaml`.

Conceptually:

```text
scenario target name
    -> target definition
    -> locator candidates
    -> current DOM element
```

## 2. Why the registry is separate

A single real-world target may require multiple kinds of information to resolve reliably:

- role
- accessible name
- label
- id
- name
- test attribute
- visible text
- stable ancestor context
- dialog/table-row/form context
- iframe path
- shadow-root path
- CSS
- XPath

Putting all of that into every scenario step would make scenario YAML difficult to read and maintain.

The registry therefore stores DOM knowledge while scenario YAML stores procedure logic.

## 3. Initial file shape

Recommended initial format:

```yaml
version: 1

elements:
  メールアドレス:
    kind: input

    locate:
      - by: label
        value: メールアドレス

      - by: id
        value: email

      - by: name
        value: email

      - by: css
        value: 'input[type="email"]'

    expect:
      tag: input
      role: textbox
      input_type: email
      editable: true

  ログイン:
    kind: button

    locate:
      - by: testid
        value: login-submit

      - by: role
        role: button
        name: ログイン

      - by: text
        value: ログイン
        exact: true

    expect:
      role: button
      enabled: true
```

The exact schema can evolve, but the separation between `locate`, `expect`, and optional diagnostic/fingerprint information is intentional.

## 4. `kind`

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

It is not itself a Selenium locator.

Example:

```yaml
kind: button
```

The validator may reject or warn about clearly incompatible operations, such as using `input` against a target registered as a button.

## 5. `locate`

`locate` is an ordered list of independently useful ways to find the target.

Supported initial locator families should include:

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

The Target Resolver tries persisted locator candidates in order, while still applying match-count and expectation rules.

## 6. `expect`

`expect` describes what the resolved element is supposed to be.

It answers a different question from `locate`:

- `locate`: where/how can the target be found?
- `expect`: is the found element really an acceptable target?

Potential fields include:

```yaml
expect:
  tag: input
  role: textbox
  text: メールアドレス
  input_type: email
  visible: true
  enabled: true
  editable: true
  attributes:
    autocomplete: email
```

Not every field should be emitted for every element.

Expectations must remain strong enough to prevent mistaken matches but not so strict that incidental presentation changes break otherwise-correct targets.

## 7. Relative locators

When an element is not uniquely identifiable by itself, FlowTape may use surrounding semantic context.

Example table:

```text
山田太郎   [編集]
鈴木一郎   [編集]
```

A useful definition is conceptually:

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
- nearby label/text

Relative locators are not automatically weak. A semantically stable row/section relationship may be stronger than a structural CSS path.

## 8. Context: iframe and Shadow DOM

Traversal context is separate from the element locator itself.

Example iframe context:

```yaml
決済/支払う:
  kind: button

  context:
    frame:
      - id: payment-frame

  locate:
    - by: role
      role: button
      name: 支払う
```

Conceptual shadow context:

```yaml
context:
  shadow:
    - css: app-shell
    - css: payment-panel
```

Resolution order is:

```text
enter context
    -> locate candidate
    -> expectation validation
```

Nested/mixed frame-shadow rules need exact implementation details before those advanced cases are coded, but the persisted model must leave room for them.

## 9. Logical target names

Target names are user-facing and may be Japanese.

Examples:

```text
メールアドレス
ログイン
次へ
注文を確定
```

When the same visible concept occurs in multiple places, use contextual namespacing:

```text
プロフィール/保存
通知設定/保存
```

The separator `/` is intended as a readable namespace convention rather than a DOM path.

## 10. Unbound targets

Scenario YAML may temporarily reference a target that is not present in the registry.

Example:

```yaml
- action: click
  target: 注文を確定
```

If `注文を確定` has no registry definition, it is an `UnboundTarget` state.

This is valid while authoring but prevents successful normal execution of that step.

Bind mode lets the user select the real element and creates the missing definition through the Element Capture Engine.

## 11. Multiple matches

No locator is allowed to mean "use the first match" by default.

For each locator candidate:

1. search current DOM within its context
2. inspect matches
3. apply expectations where applicable
4. accept only one resulting target

If more than one acceptable element remains, that locator has not resolved the target uniquely.

If later locators cannot resolve the ambiguity, execution fails with an ambiguity diagnostic.

## 12. Positional matching

Position/index matching may be supported as a last resort.

Example:

```yaml
- by: role
  role: button
  name: 編集
  index: 3
  fragile: true
```

Rules:

- never generate positional matching as a preferred candidate when a semantic alternative exists
- mark persisted positional definitions as fragile
- expose the fragility in diagnostics

`nth-child`, absolute DOM position, and similar selectors are treated similarly.

## 13. Fingerprint

The registry may preserve a small amount of auxiliary information not used as a primary search condition.

Example:

```yaml
fingerprint:
  text: 保存
  nearby_text:
    - プロフィール
  attributes:
    type: submit
```

Potential uses:

- DOM-change diagnostics
- explaining ambiguous matches
- assisting repair/rebinding

Fingerprint information must not become a hidden fuzzy-click system that bypasses the unique-resolution rules.

## 14. What not to persist normally

The registry should not become a full browser dump.

Do not normally persist:

- complete DOM HTML
- every attribute of the target
- complete ancestor chain
- screen coordinates as the primary identity
- every generated locator candidate
- candidate score tables
- rejected candidates

Those belong in diagnostics/logs where needed.

## 15. Candidate diversity

Multiple saved locators should represent genuinely different evidence where practical.

Bad fallback set:

```text
id=profile-save
CSS #profile-save
XPath //*[@id='profile-save']
```

All three fail together if the ID changes.

Better fallback set:

```text
role + accessible name
stable test attribute
heading/section-relative locator
```

The Element Capture Engine should deduplicate candidates based on their underlying evidence, not just their serialized syntax.

## 16. Persistence philosophy

`elements.yaml` should remain editable and understandable, but it is primarily machine-generated.

Normal creation/update paths are:

- Recorder
- Picker
- Bind
- Rebind/repair

Users may hand-edit it, but they should not be required to write complex DOM definitions from scratch.
