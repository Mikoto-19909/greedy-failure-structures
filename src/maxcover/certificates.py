"""Validated known-optimum certificates for constructed instances."""

from __future__ import annotations

from dataclasses import dataclass

from .model import MaximumCoverageInstance


@dataclass(frozen=True, slots=True)
class KnownOptimumCertificate:
    """A feasible solution paired with a validated optimum upper-bound proof."""

    value: int
    selected: tuple[int, ...]
    source: str
    proof_kind: str


def validate_known_optimum_certificate(
    instance: MaximumCoverageInstance,
    certificate: KnownOptimumCertificate,
) -> None:
    """Reject a certificate that does not prove its claimed optimum."""

    if certificate.proof_kind not in {"covers_universe", "disjoint_anchors"}:
        raise ValueError("unsupported known-optimum proof kind")
    if certificate.source != "constructed_certificate":
        raise ValueError("unsupported known-optimum certificate source")
    if isinstance(certificate.value, bool) or not isinstance(certificate.value, int):
        raise ValueError("certificate value must be an integer")
    selected = tuple(certificate.selected)
    if any(isinstance(index, bool) or not isinstance(index, int) for index in selected):
        raise ValueError("certificate selected indices must be integers")
    if tuple(sorted(set(selected))) != selected or len(selected) > instance.k:
        raise ValueError("certificate selected indices must be sorted, unique, and feasible")
    try:
        coverage = instance.coverage(selected)
    except IndexError as error:
        raise ValueError("certificate selected index is outside the instance") from error
    if coverage != certificate.value:
        raise ValueError("certificate selected sets do not cover the claimed value")
    if certificate.proof_kind == "covers_universe":
        if certificate.value != instance.universe_size:
            raise ValueError("covers_universe certificate value must equal universe_size")
        return

    if instance.family != "dominated_heavy":
        raise ValueError("disjoint_anchors proof requires a dominated_heavy instance")
    integer_parameters: dict[str, int] = {}
    for name in ("anchor_count", "anchor_size", "child_count"):
        value = instance.parameters.get(name)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"dominated_heavy {name} must be an integer")
        integer_parameters[name] = value
    anchor_count = integer_parameters["anchor_count"]
    anchor_size = integer_parameters["anchor_size"]
    child_count = integer_parameters["child_count"]
    if anchor_count <= 0 or anchor_size <= 0 or child_count < 0:
        raise ValueError("dominated_heavy certificate parameters are outside bounds")
    if instance.k > anchor_count:
        raise ValueError("dominated_heavy certificate requires k <= anchor_count")
    if instance.universe_size != anchor_count * anchor_size:
        raise ValueError("dominated_heavy universe conflicts with its anchors")
    if instance.set_count != anchor_count * (child_count + 1):
        raise ValueError("dominated_heavy set count conflicts with child_count")

    anchors = instance.sets[:anchor_count]
    if any(anchor.bit_count() != anchor_size for anchor in anchors):
        raise ValueError("dominated_heavy anchors have the wrong size")
    if any(
        left & right
        for index, left in enumerate(anchors)
        for right in anchors[index + 1 :]
    ):
        raise ValueError("dominated_heavy anchors must be pairwise disjoint")
    if sum(anchors, 0) != (1 << instance.universe_size) - 1:
        raise ValueError("dominated_heavy anchors must partition the universe")
    for offset, child in enumerate(instance.sets[anchor_count:]):
        owner = offset // child_count if child_count else 0
        anchor = anchors[owner]
        if child == anchor or child & ~anchor:
            raise ValueError("dominated_heavy child is not a proper anchor subset")

    expected_selected = tuple(range(instance.k))
    expected_value = instance.k * anchor_size
    if (
        certificate.selected != expected_selected
        or certificate.value != expected_value
    ):
        raise ValueError("disjoint_anchors certificate does not match the anchor optimum")


def known_optimum_certificate(
    instance: MaximumCoverageInstance,
) -> KnownOptimumCertificate | None:
    """Return and validate a construction-defined optimum certificate, if any."""

    version = instance.parameters.get("construction_version", 1)
    if instance.family == "adversarial" and version == 2:
        block_size = instance.parameters.get("block_size")
        if isinstance(block_size, bool) or not isinstance(block_size, int):
            raise ValueError("version-2 adversarial block_size must be an integer")
        if instance.universe_size != 2 * block_size or instance.k != 2:
            raise ValueError("version-2 adversarial dimensions conflict with block_size")
        if instance.set_count < 3:
            raise ValueError("version-2 adversarial instance is missing certificate sets")
        certificate = KnownOptimumCertificate(
            value=2 * block_size,
            selected=(1, 2),
            source="constructed_certificate",
            proof_kind="covers_universe",
        )
    elif instance.family == "controlled_adversarial":
        block_size = instance.parameters.get("block_size")
        if isinstance(block_size, bool) or not isinstance(block_size, int):
            raise ValueError("controlled adversarial block_size must be an integer")
        if instance.universe_size != 2 * block_size or instance.k != 2:
            raise ValueError(
                "controlled adversarial dimensions conflict with block_size"
            )
        if instance.set_count < 4:
            raise ValueError(
                "controlled adversarial instance is missing certificate sets"
            )
        certificate = KnownOptimumCertificate(
            value=2 * block_size,
            selected=(1, 2),
            source="constructed_certificate",
            proof_kind="covers_universe",
        )
    elif instance.family == "dominated_heavy":
        anchor_size = instance.parameters.get("anchor_size")
        if isinstance(anchor_size, bool) or not isinstance(anchor_size, int):
            raise ValueError("dominated_heavy anchor_size must be an integer")
        certificate = KnownOptimumCertificate(
            value=instance.k * anchor_size,
            selected=tuple(range(instance.k)),
            source="constructed_certificate",
            proof_kind="disjoint_anchors",
        )
    else:
        return None
    validate_known_optimum_certificate(instance, certificate)
    return certificate
