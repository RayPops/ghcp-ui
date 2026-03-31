"""Unit tests for Skill D: Assess safety and feasibility."""

from app.skills.assess_safety import assess_safety_and_feasibility


def test_dog_on_site_flag():
    """Dog on site flag should add safety risk."""
    result = assess_safety_and_feasibility(
        dog_on_site_flag=True,
        heavy_ppe_hint="",
        exchange_visit_flag=False,
        customer_notes="",
    )
    assert "dog on site" in result.safety_risks
    assert result.extra_engineer_required is False


def test_confined_space_requires_extra_engineer():
    """Confined space hint should require extra engineer and rescue kit."""
    result = assess_safety_and_feasibility(
        dog_on_site_flag=False,
        heavy_ppe_hint="confined space",
        exchange_visit_flag=False,
        customer_notes="",
    )
    assert result.extra_engineer_required is True
    assert "confined space rescue kit" in result.safety_equipment
    assert "confined space working" in result.safety_risks


def test_overhead_work_adds_hard_hat():
    """Overhead work should add hard hat with chin strap."""
    result = assess_safety_and_feasibility(
        dog_on_site_flag=False,
        heavy_ppe_hint="overhead work",
        exchange_visit_flag=False,
        customer_notes="Fibre route goes up external wall to 3rd floor.",
    )
    assert "hard hat with chin strap" in result.safety_equipment
    assert "working at height" in result.safety_risks


def test_asbestos_in_notes():
    """Asbestos mentioned in notes should flag risk and require extra engineer."""
    result = assess_safety_and_feasibility(
        dog_on_site_flag=False,
        heavy_ppe_hint="",
        exchange_visit_flag=False,
        customer_notes="Asbestos survey flagged on floor 2 - do not access without clearance.",
    )
    assert result.extra_engineer_required is True
    assert "potential asbestos exposure" in result.safety_risks


def test_exchange_visit_adds_key():
    """Exchange visit should add access key to equipment."""
    result = assess_safety_and_feasibility(
        dog_on_site_flag=False,
        heavy_ppe_hint="",
        exchange_visit_flag=True,
        customer_notes="",
    )
    assert "exchange access key" in result.safety_equipment


def test_dog_in_notes_but_flag_not_set():
    """Dog mentioned in notes without flag should still be caught."""
    result = assess_safety_and_feasibility(
        dog_on_site_flag=False,
        heavy_ppe_hint="",
        exchange_visit_flag=False,
        customer_notes="Guard dog reported by survey engineer.",
    )
    assert any("dog" in r for r in result.safety_risks)


def test_no_hazards():
    """No hazards should return standard PPE and no risks."""
    result = assess_safety_and_feasibility(
        dog_on_site_flag=False,
        heavy_ppe_hint="",
        exchange_visit_flag=False,
        customer_notes="Standard installation. No issues expected.",
    )
    assert result.safety_risks == []
    assert "standard PPE" in result.safety_equipment
    assert result.extra_engineer_required is False
