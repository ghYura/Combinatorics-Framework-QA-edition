# sieve3d_complex_bodies — deep manipulation suite

Companion to `sieve3d_external_api` (Automation). That pair of specs sweeps
API *routes* over six fixed extrusions with known-good poses; this suite
attacks the actual subject — **complex-surface 3D bodies vs the 2D
sieve** — with long multi-action stuffing campaigns and physical
invariants.

Run (no fwgen needed, plain unittest):

```bash
cd generator_trunk
python3 test_sieve3d_complex_manipulations_usecase.py
```

`BUNDLE_SUT_ROOT` is the parent directory containing
`3Dprofile-VS-2Dsieve/`. `SIEVE3D_ROOT` overrides that complete project path
directly, and `SIEVE3D_REC_OUT_DIR` selects where the hook campaign's
recorded `.rec` artifact is copied. If the external project path does not
exist, the unittest classes are skipped; a zero exit with skips is not
verification.

## The zoo (complex_cases.py)

| body | surface complexity |
|---|---|
| wave_bar | formula: side view is a sinusoid |
| flower / twisted_flower | polar r(t) / r(t,z) — lobes screwed along the axis |
| hook120 / snake / croissant | plasticine bends (incl. the S-chain) |
| helix_bar | square bar twisted 120° |
| pierced_cube / half_pipe | boolean-carved (through-bore; tube cut open — concave C) |
| plug | tri-projection solid (circle ∩ square ∩ triangle) |

Holes are matched-but-not-identical: wave slot, polar flower hole,
needle eyes, snug squares, annulus-with-island.

## What is asserted (beyond exit codes)

* **Invariants**: exact mass conservation under bend/twist/stretch
  chains; boolean removal = πr²h; sections ⊆ shadow at any orientation;
  passed-volume % monotone during descent; unassigned bodies land ON
  the plate and cannot cross it.
* **Pose equivalence classes**: 4-fold square symmetry, 3-fold flower
  symmetry + antiphase collision, mirror bends give mirror silhouettes.
* **Predicate ↔ simulation agreement**: a certain positive `fits`
  clearance must drop through; a deep deficit must jam (L0 vs L3).
* **Manipulation safety**: order violations; a 45° turn *inside* a snug
  hole is caught mid-path (blocked_at) while 2° is fine; re-manufacture
  (inflate) while the piston sits in the bore — physical mode refuses,
  geometric mode flags the new conflict; parallel batch double-stuffing
  with per-hole volume-flux accounting.
* **Campaign matrix with strategy escalation** (direct → wiggle ladder →
  full threading): sinusoid phase-locks into its wave slot; the plug
  enters by triangle AND square faces; the twisted flower and the
  twisted square bar must be *screwed* through; the S-snake steers
  through a 0.5 mm-margin eyelet (~64 actions); hopeless pairs stay
  blocked across the declared anchor poses, direct drop, and bounded wiggle
  campaign. This is a regression anchor for those sampled strategies, not a
  universal proof that no continuous trajectory can pass. The hook campaign
  is wrapped in the record action/cut contract and saves its `.rec`.

## Historical findings retained as regressions

Earlier runs exposed the following defects, and the assertions now preserve
them as regression targets. Re-run against the current external SUT before
claiming the fixes still hold:

1. Experiment bodies used to *spawn at z=0, embedded in the plate*; the
   corrected behavior spawns them hovering above it.
2. Twist discretization (5°/quality per slab) consumed the whole in-plane
   rotation tolerance of snug holes, making a physically screwable helix
   unpassable at coarse quality; the recorded correction refined it to 2.5°.
