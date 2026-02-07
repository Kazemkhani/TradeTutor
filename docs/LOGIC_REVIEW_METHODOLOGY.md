# Logic Review Methodology

A systematic framework for preventing data model and UX logic flaws before they ship. Created after identifying critical architecture issues in the AI Lead Qualification Voice Agent system.

## Origin

This methodology was created after discovering the following flaws:

| Flaw | Impact |
|------|--------|
| One lead name shared across 5 phone numbers | Agent called different people by the same name |
| API accepted 5 phones but silently called only the first | Users thought all 5 would be called |
| Dead `agent_spec` references in agent code | Code referenced schema fields that didn't exist |
| Single consent checkbox for multiple recipients | Legal non-compliance |

All of these flaws passed initial development and review because no one traced the data through the full system.

---

## 1. Pre-Implementation Checklist

Before writing any code, answer these questions:

### Data Model Validation

- [ ] **For every collection field (list/array)**: What entity does each item represent?
  - Bad: `phones: ["+1...", "+2...", "+3..."]` + `name: "John"` (implies one person has 3 phones)
  - Good: `leads: [{name: "John", phone: "+1..."}, {name: "Sarah", phone: "+2..."}]` (each item is a person)

- [ ] **If a form collects N items**: Does the API process ALL N items?
  - Bad: API does `phone = request.phones[0]` (silently drops items 2-5)
  - Good: API loops through all items, or rejects the request with an error if batch isn't supported

- [ ] **If a single field is shared across N items**: Are the semantics correct?
  - Ask: "Would a user entering this data expect the field to apply to ALL items?"
  - Example: `product` shared across leads is correct (same pitch for all). `name` shared across leads is wrong (different people).

- [ ] **Does the consent model match the data model?**
  - If calling 5 different people, do you need consent for each one individually?

### Silent Data Loss Detection

- [ ] **Does the API response accurately reflect what was processed?**
  - Bad: API says "Call dispatched" but only called 1 of 5 numbers
  - Good: API says "1 of 5 calls dispatched (batch not yet supported)"

- [ ] **Are any form fields silently ignored by the backend?**
  - Trace every field from the form payload to where it's actually used
  - If a field exists in the form but is never read by the consumer, it's either dead code or a bug

---

## 2. Real-World Scenario Test

Before writing code, walk through this scenario manually:

### The End-to-End Trace

1. **A user fills out the form completely** — What data did they enter? For whom?
2. **The system processes the submission** — What happens to each field?
3. **An actual call is placed** — Who picks up the phone?
4. **The person on the phone hears the agent** — Does the agent have the RIGHT information for THIS specific person?

### Example Walkthrough (Before Fix)

1. User enters: email=owner@co.com, name="John", phones=["+1111", "+2222", "+3333"]
2. API takes phone="+1111", builds context with name="John"
3. Call placed to +1111 (but +2222 and +3333 are silently dropped)
4. Person at +1111 hears: "Hi John!" — CORRECT only if that person is actually John
5. **FAILURE**: If +2222 is Sarah and +3333 is Mike, they would also hear "Hi John!"
6. **FAILURE**: +2222 and +3333 are never called at all

### Example Walkthrough (After Fix)

1. User enters: email=owner@co.com, leads=[{name:"John", phone:"+1111"}, {name:"Sarah", phone:"+2222"}]
2. API processes each lead individually, builds context per-lead
3. Call 1 placed to +1111 with context containing name="John"
4. Call 2 placed to +2222 with context containing name="Sarah"
5. Each person hears their own name — CORRECT

---

## 3. Anti-Patterns Catalog

### Anti-Pattern: Flat List Mismatch

**Symptom**: One field represents "per-batch" data, another represents "per-item" data, but they're at the same level.

**Example**:
```python
class CallRequest(BaseModel):
    name: str           # Per-batch (one name)
    phones: list[str]   # Per-item (multiple phones)
```

**Fix**: Group per-item fields into an object:
```python
class Lead(BaseModel):
    name: str
    phone: str

class CallRequest(BaseModel):
    leads: list[Lead]   # Each lead has their own name + phone
```

**Detection**: Look for any model where a `list` field coexists with a scalar field that should logically be per-item.

---

### Anti-Pattern: Silent Truncation

**Symptom**: System accepts N items but only processes a subset, without error or warning.

**Example**:
```python
phone = request.phones[0]  # Silently ignores phones[1:]
```

**Fix**: Either process all items, or reject with a clear error:
```python
if len(request.leads) > 1:
    raise HTTPException(400, "Batch calls not yet supported. Submit one lead at a time.")
```

**Detection**: Search for `[0]` indexing on list fields. Each one is a potential silent truncation.

---

### Anti-Pattern: Shared Consent

**Symptom**: One consent mechanism covers multiple distinct recipients who may have different consent statuses.

**Example**: "I confirm I have consent to call these numbers" — single checkbox for 5 different people.

**Fix**: Either per-recipient consent tracking, or clear legal language that the checkbox covers ALL listed recipients.

**Detection**: Check if consent is collected once but applied to multiple entities.

---

### Anti-Pattern: Dead Code References

**Symptom**: Code reads from fields or keys that don't exist in the schema.

**Example**:
```python
if context and "agent_spec" in context:  # agent_spec doesn't exist in ContextInstance
    spec = context["agent_spec"]
```

**Fix**: Trace every field access back to its schema definition. If the field doesn't exist in the schema, the code is dead.

**Detection**: Search for string-based dictionary access (`context["field"]`, `data.get("field")`) and verify each key exists in the corresponding Pydantic model.

---

### Anti-Pattern: Form-API Divergence

**Symptom**: Form collects data the API doesn't use, or API expects data the form doesn't provide.

**Example**: Form has "Lead Name" field but API builds context without using it for personalization.

**Fix**: Maintain a field mapping document:

| Form Field | API Field | Builder Field | Agent Usage |
|-----------|-----------|---------------|-------------|
| Lead Name | lead.name | context.name | Opening line greeting |
| Phone | lead.phone | context.phone | SIP dial target |
| Company | lead.company | context.lead_company | Personalization |

**Detection**: For each form field, trace it through the entire stack. If it dead-ends anywhere, it's either unused or broken.

---

## 4. Cross-Layer Data Trace

For every new feature, trace data through ALL layers:

```
Web Form (HTML/JS)
    ↓ HTTP POST payload
API (FastAPI)
    ↓ CallRequest → Lead objects
Context Builder (DSPy)
    ↓ ContextInstance JSON
Voice Agent (LiveKit)
    ↓ Agent instructions, opening line
Phone Call (SIP)
    → What the recipient actually hears
```

### Trace Checklist

- [ ] Form field name matches API schema field name
- [ ] API validates the field (not just passes it through)
- [ ] Context builder uses the field in context generation
- [ ] Agent receives and uses the field during the call
- [ ] The recipient's experience reflects the field value

---

## 5. Schema Change Review Process

When modifying Pydantic schemas:

1. **Search all consumers** of the old field names before changing
2. **Update tests FIRST** (TDD) — write failing tests, then fix the code
3. **Verify JSON serialization** still works (model_dump_json / model_validate_json)
4. **Check web form payload** matches the new schema
5. **Run the full test suite** — not just the package you changed

### Cross-Package Impact Checklist

When changing `shared/schemas.py`:

- [ ] `packages/shared/tests/test_schemas.py` — updated
- [ ] `packages/context_builder/src/context_builder/builder.py` — uses the schema
- [ ] `packages/context_builder/tests/test_builder.py` — updated
- [ ] `apps/api/src/api/main.py` — validates and processes the schema
- [ ] `apps/web/index.html` — sends data matching the schema
- [ ] `src/agent.py` — reads context built from the schema
- [ ] `packages/voice_agent/src/voice_agent/agent.py` — reads context

---

## 6. Testing Requirements for Logic-Critical Code

### Must-Have Tests

1. **Per-entity data isolation**: If system handles multiple items, verify each item's data is independent
   ```python
   def test_different_leads_get_different_opening_lines():
       leads = [Lead(name="Alice"), Lead(name="Bob")]
       contexts = build_contexts_for_submission(request)
       assert "Alice" in contexts[0].opening_line
       assert "Bob" in contexts[1].opening_line
   ```

2. **No silent data loss**: Verify all submitted items are processed
   ```python
   def test_builds_contexts_for_all_leads():
       request = make_request(leads=[lead1, lead2, lead3])
       contexts = build_contexts_for_submission(request)
       assert len(contexts) == 3
   ```

3. **Schema contract tests**: Verify required fields haven't silently changed
   ```python
   def test_call_request_required_fields():
       schema = CallRequest.model_json_schema()
       assert "leads" in schema.get("required", [])
   ```

---

## 7. Review Checklist (Pre-PR)

Before submitting any PR that touches data flow:

- [ ] Ran the Real-World Scenario Test (Section 2)
- [ ] Checked for Silent Truncation anti-pattern
- [ ] Checked for Flat List Mismatch anti-pattern
- [ ] Traced every new/changed field through all layers (Section 4)
- [ ] Updated tests in all affected packages
- [ ] Verified form payload matches API schema
- [ ] All tests pass (`task test`)
- [ ] Code formatted (`task format`) and linted (`task lint`)
