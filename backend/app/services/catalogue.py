"""Catalogue of objects a side-scan sonar survey actually encounters.

Each entry carries the survey characteristics that let an operator sanity-check
a detection: what the object typically measures, how it presents acoustically,
and what it means operationally.

The dimension ranges are used for corroboration, not decoration. A detector can
be confident and still be wrong about *what* it found -- a 180 m contact
labelled "cargo container" is a misclassification regardless of the softmax
score. `assess()` compares measured size against the expected range and returns
that as a separate signal, so the dashboard can show model confidence and
physical plausibility as two independent numbers rather than blending them into
one score that hides the disagreement.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models.schemas import AnomalyClass, Severity


@dataclass(frozen=True)
class CatalogueEntry:
    """Survey reference data for one class of seabed object."""

    key: AnomalyClass
    display_name: str
    category: str
    severity: Severity
    # Typical along-track extent (length) in metres, as seen on a swath.
    length_range_m: tuple[float, float]
    acoustic_signature: str
    operational_note: str
    aliases: tuple[str, ...] = field(default=())


CATALOGUE: dict[AnomalyClass, CatalogueEntry] = {
    AnomalyClass.SHIPWRECK: CatalogueEntry(
        key=AnomalyClass.SHIPWRECK,
        display_name="Shipwreck",
        category="Wreck",
        severity=Severity.CRITICAL,
        length_range_m=(15.0, 300.0),
        acoustic_signature=(
            "Strong specular return from hull plating with a long, well-defined "
            "acoustic shadow; internal structure often resolves as regular ribbing."
        ),
        operational_note=(
            "Navigational hazard and potential protected site. Report to the "
            "hydrographic office for Notice to Mariners assessment."
        ),
        aliases=("ship", "wreck", "vessel"),
    ),
    AnomalyClass.AIRCRAFT: CatalogueEntry(
        key=AnomalyClass.AIRCRAFT,
        display_name="Aircraft Fuselage",
        category="Wreck",
        severity=Severity.CRITICAL,
        length_range_m=(8.0, 70.0),
        acoustic_signature=(
            "Compact high-intensity return with symmetric wing returns either "
            "side of a linear fuselage; shadow shorter than a vessel of similar length."
        ),
        operational_note=(
            "Treat as a potential accident site. Do not disturb; escalate to the "
            "relevant civil or military authority before any intervention."
        ),
        aliases=("aircraft", "plane", "fuselage"),
    ),
    AnomalyClass.SAR_CONTACT: CatalogueEntry(
        key=AnomalyClass.SAR_CONTACT,
        display_name="SAR Contact",
        category="Search & Rescue",
        severity=Severity.CRITICAL,
        length_range_m=(1.2, 2.5),
        acoustic_signature=(
            "Small, low-contrast return close to the seabed with a faint shadow; "
            "easily lost in ripple texture at long range."
        ),
        operational_note=(
            "Possible person in water. Escalate immediately to the coordinating "
            "rescue authority; do not delay for further survey passes."
        ),
        aliases=("human", "person", "diver"),
    ),
    AnomalyClass.CONTAINER: CatalogueEntry(
        key=AnomalyClass.CONTAINER,
        display_name="Cargo Container",
        category="Debris",
        severity=Severity.HIGH,
        length_range_m=(6.0, 13.0),
        acoustic_signature=(
            "Rectangular return with hard right-angled corners and a crisp, "
            "box-shaped shadow -- geometry is the giveaway."
        ),
        operational_note=(
            "Lost overboard cargo. Snagging hazard for trawlers; may contain "
            "hazardous goods. Position for recovery."
        ),
        aliases=("container", "cargo"),
    ),
    AnomalyClass.PIPELINE: CatalogueEntry(
        key=AnomalyClass.PIPELINE,
        display_name="Subsea Pipeline",
        category="Infrastructure",
        severity=Severity.MEDIUM,
        length_range_m=(40.0, 5000.0),
        acoustic_signature=(
            "Continuous linear return running across multiple pings with a narrow, "
            "parallel shadow; free spans show as gaps beneath the line."
        ),
        operational_note=(
            "Charted infrastructure. Check against the asset register; report free "
            "spans or exposure to the operator."
        ),
        aliases=("pipeline", "cable", "umbilical"),
    ),
    AnomalyClass.GHOST_NET: CatalogueEntry(
        key=AnomalyClass.GHOST_NET,
        display_name="Ghost Net / Fishing Gear",
        category="Debris",
        severity=Severity.HIGH,
        length_range_m=(3.0, 120.0),
        acoustic_signature=(
            "Diffuse, irregular return with no coherent shadow; often drapes over "
            "relief and follows seabed contour rather than sitting proud of it."
        ),
        operational_note=(
            "Derelict fishing gear. Continues to catch marine life and fouls "
            "propellers. Flag for removal."
        ),
        aliases=("net", "ghost net", "trawl"),
    ),
    AnomalyClass.ANCHOR_DEBRIS: CatalogueEntry(
        key=AnomalyClass.ANCHOR_DEBRIS,
        display_name="Anchor & Chain Debris",
        category="Debris",
        severity=Severity.MEDIUM,
        length_range_m=(2.0, 60.0),
        acoustic_signature=(
            "Bright compact return with a trailing beaded line of chain links; "
            "frequently accompanied by drag scars in the sediment."
        ),
        operational_note=(
            "Lost ground tackle. Minor snagging hazard; note drag scars as evidence "
            "of anchoring in a restricted area."
        ),
        aliases=("anchor", "chain"),
    ),
    AnomalyClass.DEBRIS_FIELD: CatalogueEntry(
        key=AnomalyClass.DEBRIS_FIELD,
        display_name="Debris Field",
        category="Debris",
        severity=Severity.HIGH,
        length_range_m=(5.0, 400.0),
        acoustic_signature=(
            "Cluster of small unconnected returns with inconsistent shadow "
            "directions, spread over an area rather than a single footprint."
        ),
        operational_note=(
            "Often the scatter surrounding a primary wreck. Survey outward to "
            "locate the parent structure."
        ),
        aliases=("debris", "scatter"),
    ),
    AnomalyClass.UXO: CatalogueEntry(
        key=AnomalyClass.UXO,
        display_name="Ordnance (UXO)",
        category="Hazard",
        severity=Severity.CRITICAL,
        length_range_m=(0.5, 6.0),
        acoustic_signature=(
            "Small cylindrical return with a disproportionately long shadow for "
            "its size, indicating an object standing proud of the seabed."
        ),
        operational_note=(
            "Suspected unexploded ordnance. Establish an exclusion zone and refer "
            "to EOD. Do not approach or attempt recovery."
        ),
        aliases=("uxo", "ordnance", "mine"),
    ),
    AnomalyClass.BOULDER: CatalogueEntry(
        key=AnomalyClass.BOULDER,
        display_name="Boulder",
        category="Geology",
        severity=Severity.LOW,
        length_range_m=(0.5, 12.0),
        acoustic_signature=(
            "Rounded return with a soft-edged shadow and no internal structure; "
            "usually one of many across a glacial or reef seabed."
        ),
        operational_note=(
            "Natural seabed feature. Record for cable and pipeline routing; no "
            "escalation required."
        ),
        aliases=("boulder", "rock"),
    ),
    AnomalyClass.UNKNOWN: CatalogueEntry(
        key=AnomalyClass.UNKNOWN,
        display_name="Unclassified Contact",
        category="Unclassified",
        severity=Severity.MEDIUM,
        length_range_m=(0.5, 500.0),
        acoustic_signature=(
            "Return does not match a catalogued signature with sufficient margin."
        ),
        operational_note=(
            "Queue for human adjudication before the line is signed off. Consider "
            "a reciprocal-heading pass at reduced range scale."
        ),
        aliases=("unknown",),
    ),
}


# Reverse index so a trained model's own vocabulary resolves without a second map.
_ALIAS_INDEX: dict[str, AnomalyClass] = {
    alias: entry.key for entry in CATALOGUE.values() for alias in entry.aliases
}
_ALIAS_INDEX.update({entry.key.value: entry.key for entry in CATALOGUE.values()})


def resolve(name: str) -> AnomalyClass:
    """Map a raw class name (model vocabulary or alias) onto the taxonomy."""
    return _ALIAS_INDEX.get((name or "").strip().lower(), AnomalyClass.UNKNOWN)


def entry_for(label: AnomalyClass) -> CatalogueEntry:
    return CATALOGUE.get(label, CATALOGUE[AnomalyClass.UNKNOWN])


def size_plausibility(label: AnomalyClass, length_m: float) -> float:
    """How well a measured length agrees with the catalogued range, 0-1.

    Deliberately separate from model confidence. The network scores how much
    the image looks like a class; this scores whether the object is the right
    size to be one. Blending them would let a confident misclassification hide
    behind a single number.
    """
    low, high = entry_for(label).length_range_m
    if length_m <= 0:
        return 0.0
    if low <= length_m <= high:
        return 1.0
    # Grade down on the log ratio: an order of magnitude out scores ~0.
    reference = low if length_m < low else high
    ratio = max(length_m, reference) / max(min(length_m, reference), 1e-6)
    return round(max(0.0, 1.0 - (ratio - 1.0) / 9.0), 3)


def as_dict(label: AnomalyClass) -> dict:
    entry = entry_for(label)
    return {
        "key": entry.key.value,
        "display_name": entry.display_name,
        "category": entry.category,
        "severity": entry.severity.value,
        "typical_length_m": list(entry.length_range_m),
        "acoustic_signature": entry.acoustic_signature,
        "operational_note": entry.operational_note,
    }


def catalogue_listing() -> list[dict]:
    """The whole catalogue, for the dashboard's reference panel."""
    return [as_dict(key) for key in CATALOGUE]
