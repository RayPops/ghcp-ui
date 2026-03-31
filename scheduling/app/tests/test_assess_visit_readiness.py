"""Unit tests for Skill C: Assess visit readiness."""

from app.skills.assess_visit_readiness import assess_visit_readiness


def test_fttp_new_install_basic():
    """Standard FTTP installation should return fibre splicer and base tools."""
    result = assess_visit_readiness(
        service_type="FTTP Installation",
        job_type="new line installation",
        driveway_surface_hint="tarmac",
        photo_provided_flag=True,
        customer_notes="Standard install. No issues.",
    )
    assert "fibre splicer" in result.required_tools
    assert result.estimated_duration_minutes >= 90
    assert result.confidence == "high"


def test_gravel_adds_ground_mat():
    """Gravel surface should add ground mat tool and extra time."""
    result = assess_visit_readiness(
        service_type="FTTP Installation",
        job_type="new line installation",
        driveway_surface_hint="gravel",
        photo_provided_flag=True,
        customer_notes="",
    )
    assert "ground mat" in result.required_tools
    assert result.estimated_duration_minutes > 120  # base 120 + 15


def test_duct_blockage_reduces_confidence():
    """Duct blockage in notes should reduce confidence to low."""
    result = assess_visit_readiness(
        service_type="Ethernet Bearer",
        job_type="provision",
        driveway_surface_hint="",
        photo_provided_flag=True,
        customer_notes="Duct blockage found on previous survey.",
    )
    assert result.confidence == "low"
    assert result.estimated_duration_minutes > 180


def test_long_cable_run_adds_materials():
    """Long cable run mentioned in notes should add extra materials."""
    result = assess_visit_readiness(
        service_type="FTTP Installation",
        job_type="new line installation",
        driveway_surface_hint="",
        photo_provided_flag=False,
        customer_notes="Rural property. Long garden run approx 80m from pole.",
    )
    materials_joined = " ".join(result.required_materials)
    assert "80m" in materials_joined
    assert result.estimated_duration_minutes > 120


def test_broadband_repair_basic():
    """Broadband repair should return cable tester and repair tools."""
    result = assess_visit_readiness(
        service_type="Broadband Repair",
        job_type="repair",
        driveway_surface_hint="",
        photo_provided_flag=False,
        customer_notes="Intermittent connection dropping.",
    )
    assert "cable tester" in result.required_tools
    assert result.estimated_duration_minutes >= 60


def test_no_photo_reduces_confidence():
    """Long job without photo should have reduced confidence."""
    result = assess_visit_readiness(
        service_type="Ethernet Bearer",
        job_type="provision",
        driveway_surface_hint="",
        photo_provided_flag=False,
        customer_notes="Complex install.",
    )
    assert result.confidence in ("medium", "low")
