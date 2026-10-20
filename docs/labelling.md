# Durable labelling: DataMatrix vs QR, and a label-stock spec

The P5 deliverable this covers: *"Evaluate DataMatrix against QR for small,
oily, curved surfaces, and specify a label stock that survives a machine
room for twenty years. A passport is only as permanent as the thing
carrying its identifier."*

> **Status.** This is a research/specification document, not code - there
> is nothing to run or test. It is a judgement call recorded for review,
> the same way the P4 threat model and this document's sibling governance
> documents are.

---

## 1. The actual question

The Digital Product Passport identifier
(`urn:kone:dpp:1:{component_id}`, see `docs/compliance.md` §"DPP
conformance") has to survive on a physical label for the component's entire
service life - which, per this platform's own installation-date data, can
be decades. The label substrate and print method matter at least as much as
the symbology choice; a perfectly chosen symbology printed on a label that
delaminates in five years is still a failure.

## 2. DataMatrix vs QR

| Criterion | QR Code | DataMatrix |
|---|---|---|
| Minimum reliably-scannable size | ~15-20mm square at typical print resolution | As small as ~5mm square - the reason DataMatrix is the standard for direct part marking in electronics and aerospace |
| Damage tolerance | Reed-Solomon error correction, up to ~30% at the highest ECC level | Also Reed-Solomon based; comparable damage tolerance at equivalent code sizes |
| Scanning hardware | Any smartphone camera, no special app needed for the URL payload | Needs a barcode-capable scan path; most modern smartphone camera apps also decode DataMatrix, but with less universal out-of-the-box support than QR |
| Existing investment in this codebase | `html5-qrcode` (frontend), `qrcode[pil]` (backend PNG generation) - both QR-only libraries already in production use | Would need a new library on both ends |
| Direct part marking (laser-etched, dot-peen) | Rarely used this way in practice | The industry-standard choice - most direct part marking on metal components uses DataMatrix specifically because of its small reliable size |

**Recommendation: keep QR for the printed label, do not add DataMatrix in
this pass.** The components this platform tracks (motors, steel ropes,
brakes, governors, door operators, sheaves)
are large enough that QR's larger minimum size is not the binding
constraint labelling in this domain has - unlike, say, a screw or a
connector pin, where DataMatrix's small-size advantage would be decisive.
Switching now would mean maintaining two symbologies, two libraries, and
two scan paths for a size advantage this product does not need. **The one
exception worth flagging for a future revision:** if a future component
category this platform tracks is genuinely too small for a legible QR
label (a bearing race, a small sensor), DataMatrix is the right call for
that category specifically, not a wholesale replacement.

## 3. Label stock specification

A label stock recommendation for a "survives a machine room for twenty
years" requirement, based on standard industrial labelling practice (not
validated against a specific KONE-approved supplier or spec, since this
build has no access to KONE's actual facilities-materials standards):

| Property | Specification | Why |
|---|---|---|
| Substrate | Polyester (PET) film, not paper or vinyl | Paper degrades with moisture and abrasion; vinyl can shrink/embrittle over decades; PET is the standard choice for asset tags rated 10+ years |
| Adhesive | Permanent acrylic, rated for the substrate (steel, cast iron, painted surfaces) | Must not release on a warm, vibrating machine-room surface over years |
| Print method | Thermal transfer with a resin ribbon, not direct thermal or inkjet | Direct thermal fades with heat exposure (a real risk near a motor or brake); resin thermal-transfer print is abrasion- and chemical-resistant |
| Overlaminate | Clear polyester laminate over the print | Protects the printed code from the oil, dust and incidental abrasion the plan's "small, oily, curved surfaces" wording names directly |
| Operating temperature range | -40°C to +150°C | Elevator machine rooms and motor housings run hot; a label rated only for ambient room temperature is the wrong choice |
| Curved-surface conformability | Specify a stock rated for the minimum radius on a Steel Rope or Sheave, not a flat-panel-only stock | The plan names curved surfaces specifically - a generic flat asset tag stock will crack or lift on a tight radius |

**This is a specification to validate against actual supplier datasheets
and a real sample survival test, not a purchase order.** No physical label
was printed or tested as part of this pass - that is real, physical
follow-on work a document cannot substitute for.

## 4. What would make this real

1. Get datasheets from 2-3 industrial label suppliers against the spec
   above and compare actual accelerated-aging test data (most label
   manufacturers publish ASTM/ISO durability test results).
2. Print a small batch on the shortlisted candidate substrates, apply them
   to a sample steel rope and sheave, and run an actual accelerated-aging
   or field trial - not just a paper specification.
3. Confirm QR remains the right call once real components from a real
   pilot are in hand, in case a specific part category (a small sensor, a
   bearing) turns out to need DataMatrix after all.
