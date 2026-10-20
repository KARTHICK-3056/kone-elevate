# Sustainability and impact model

> **Every figure produced by this module is a prototype estimate.** The
> constants are illustrative values chosen so the demo can show the *shape* of
> the circular-economy business case. They are not official KONE cost, mass or
> emission factors and they are not suitable for external sustainability
> reporting.

---

## 1. The problem being addressed

Thousands of components are removed during elevator modernisation and
maintenance: sheaves, door operators, steel ropes, motors, brakes,
governors. Many are scrapped not because they are worn out, but
because **nobody can prove they are not**.

That single evidence gap causes six downstream costs:

1. Components with remaining life are disposed of
2. New parts are bought that were not needed
3. Usable sub-components are never identified for recovery
4. Component-recovery capacity cannot be planned, because demand is invisible
5. Lifecycle records are lost the moment a component leaves the shaft
6. Sustainability reporting has no auditable component-level basis

KONE ELEVATE addresses the evidence gap: a QR-addressable passport that carries
the component's own history, an explainable AI assessment of what that history
implies, and a tamper-evident record of every decision made.

---

## 2. The impact model

`backend/app/services/impact_service.py`:

```
recovered_value = new_part_cost[type]  x  value_recovery_factor[disposition]

co2_avoided     = mass[type]  x  co2_intensity[material]
                              x  co2_avoidance_factor[disposition]
```

Both factor tables live in `backend/app/core/config.py` as Pydantic settings,
so an engineering team can replace them with validated values - or override
them per environment - without touching application code.

### Illustrative new-part cost and mass

| Component type | New part cost (INR) | Mass (kg) |
|---|---:|---:|
| Motor | 185,000 | 260 |
| Door Operator | 120,000 | 48 |
| Brake | 96,000 | 55 |
| Sheave | 88,000 | 130 |
| Governor | 78,000 | 40 |
| Steel Rope | 42,000 | 95 |

### Illustrative embodied-carbon intensity

| Material | kg CO2e per kg |
|---|---:|
| Electronic (ledger rows only) | 21.0 |
| Aluminum | 8.2 |
| Composite | 5.4 |
| Copper | 4.1 |
| Steel | 1.9 |
| Cast Iron | 1.6 |

Electronics carry a high intensity per kilogram (semiconductor fabrication).
No current component type is Electronic; the entry stays because material-flow
ledger rows for the removed control boards still reference it.

### Recovery factors by recommendation category

| Category | Value recovered | CO2 avoided |
|---|---:|---:|
| Continue Using – No Changes Required | 70% | 92% |
| Component Recovery | 20% | 35% |
| Material Recovery | 8% | 30% |
| Dispose | 0% | 0% |

The reasoning behind the shape (not the exact numbers):

- **Continue Using** avoids nearly all the embodied carbon of a replacement:
  the component stays where it is, and a new part is not bought.
- **Component Recovery** recovers only the usable sub-components, after
  inspection and testing, for lower-demand applications. The complete
  component is not supplied again, so it recovers far less value and carbon
  than continued use - but more than recovering the material alone.
- **Material Recovery** recovers material value only, and secondary
  production still costs energy, so avoidance is partial.
- **Dispose** recovers nothing. That is the baseline the whole system is
  trying to move components away from.

### Worked example

A steel motor assessed as Component Recovery:

```
value = 185,000 x 0.20                = Rs.  37,000
co2   = 260 kg x 1.9 kg/kg x 0.35     =      173 kg CO2e
```

Both numbers appear on the component passport, captioned "Prototype estimate".

---

## 3. What the dashboard reports

`GET /api/v1/dashboard/impact` aggregates across every assessed component:

| Metric | Meaning |
|---|---|
| `components_assessed` | components with at least one AI assessment |
| `components_diverted_from_disposal` | assessed Continue Using, Component Recovery or Material Recovery |
| `diversion_rate_percent` | diverted / assessed |
| `total_recovery_value` | sum of estimated recoverable value |
| `total_new_part_cost` | what replacing all of them new would cost |
| `avoided_procurement_share_percent` | recovery value as a share of that |
| `total_co2_avoided_kg` / `_tonnes` | estimated emissions avoided |
| `by_disposition` | the same three figures split by the four categories |
| `by_component_type` | the same split by component type |

On the seeded 60-component demo portfolio this produces roughly **Rs. 13.4
lakh** of recovery value and **7.4 tonnes CO2e** avoided - for sixty
components. The point of the demo is the per-component multiplier, not the
absolute figure.

Every response carries:

```json
{
  "estimate_basis": "Prototype estimate",
  "disclaimer": "Prototype estimate. Economic and CO2 figures are derived from illustrative configuration constants, not from validated KONE cost or emission data."
}
```

The UI renders that caption on **every** tile that shows a monetary or carbon
figure. It is not an optional decoration and it is not in small print at the
bottom of the page.

---

## 4. Auditable reporting

The reason a circular-economy claim is usually hard to defend is that the
underlying decisions are not traceable. Here they are.

`GET /api/v1/passports/{component_id}/report` returns a flattened record
combining:

- Component lifecycle (identity, installation, age, current status)
- Decision history (every AI assessment with confidence, health score and model
  version)
- Recovery action (condition, availability, estimated value and CO2)
- Impact estimate with its full factor breakdown
- Audit summary: record count, head hash, first and last timestamps

Because every one of those decisions also sits in the SHA-256 audit chain, a
reported figure can be traced to the assessments that produced it, and the
chain can be re-verified at any time with `GET /api/v1/audit/verify`.

### CSV exports

| Export | Endpoint |
|---|---|
| Components | `GET /api/v1/components/export` |
| Predictions | `GET /api/v1/predictions/export` |
| Audit chain | `GET /api/v1/audit/export` |

Each is also a one-click button in the UI.

---

## 5. Limitations, stated plainly

1. **The constants are illustrative.** Real figures vary by market, supplier,
   contract and year. Nothing here has been validated against KONE procurement
   or LCA data.
2. **Embodied carbon is simplified.** A real assessment uses full LCA with
   cradle-to-gate boundaries, regional grid intensities and supplier-specific
   data - not one number per material.
3. **Component-recovery cost is not modelled.** The recovery factor bundles it into
   a single ratio. A real business case needs workshop labour, parts,
   transport, testing and warranty.
4. **Transport is ignored.** Moving a 260 kg motor across the country has a
   carbon cost that could materially change a marginal decision. The matching
   engine scores location, but the impact model does not price the transport.
5. **No end-of-life credit modelling.** Material recovery yields and downcycling
   losses are approximated by a single factor.
6. **Estimates depend on AI dispositions.** They are advisory recommendations
   on synthetic-data predictions, not confirmed engineering outcomes. An
   aggregate built on them inherits every limitation in
   `docs/machine-learning.md`.

**What would make these numbers real:** validated procurement costs, supplier
LCA data, measured component-recovery costs and yields, transport modelling,
and - most importantly - reconciliation against components that *actually*
continued in use, had their parts recovered or had their material recovered,
and how they subsequently performed.

The deliverable at this stage is the framework: a per-component, auditable,
traceable structure for the calculation. Swapping in validated constants is a
configuration change; building the traceability afterwards would not be.
