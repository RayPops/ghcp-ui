"""Render Markdown summary for a scheduling decision."""

from __future__ import annotations

from app.models import SchedulingDecision


def render_decision_markdown(decision: SchedulingDecision) -> str:
    """Render a scheduling decision as a Markdown summary.

    Args:
        decision: A completed SchedulingDecision.

    Returns:
        Markdown string.
    """
    lines: list[str] = []

    action_label = decision.recommended_action.upper().replace("-", " ")
    lines.append(f"# Scheduling Decision: {decision.order_id}")
    lines.append("")
    lines.append(f"## Recommended Action: {action_label}")
    lines.append("")

    if decision.planned_visit_date:
        lines.append(f"**Planned Visit Date:** {decision.planned_visit_date.isoformat()}")
        lines.append("")

    # Rationale
    if decision.rationale:
        lines.append("## Rationale")
        for point in decision.rationale:
            lines.append(f"- {point}")
        lines.append("")

    # Constraints
    if decision.constraints:
        c = decision.constraints
        lines.append("## Scheduling Constraints")
        if c.earliest_allowed_date:
            lines.append(f"- **Earliest Allowed Date:** {c.earliest_allowed_date.isoformat()}")
        if c.customer_availability_window:
            lines.append(f"- **Customer Availability:** {c.customer_availability_window}")
        if c.special_instructions:
            for instr in c.special_instructions:
                lines.append(f"- **Special Instruction:** {instr}")
        if not c.earliest_allowed_date and not c.customer_availability_window and not c.special_instructions:
            lines.append("- No specific constraints extracted")
        lines.append("")

    # Delivery date assessment
    if decision.delivery_date_assessment:
        d = decision.delivery_date_assessment
        lines.append("## Delivery Date Assessment")
        lines.append(f"- **Date Change Recommended:** {'Yes' if d.date_change_recommended else 'No'}")
        if d.reason_code:
            lines.append(f"- **Reason:** {d.reason_code.replace('_', ' ')}")
        if d.revised_delivery_date:
            lines.append(f"- **Revised Date:** {d.revised_delivery_date.isoformat()}")
        if d.explanation:
            lines.append(f"- {d.explanation}")
        lines.append("")

    # Visit readiness
    if decision.visit_readiness:
        v = decision.visit_readiness
        lines.append("## Visit Preparation")
        if v.required_tools:
            lines.append(f"- **Tools:** {', '.join(v.required_tools)}")
        if v.required_materials:
            lines.append(f"- **Materials:** {', '.join(v.required_materials)}")
        lines.append(f"- **Estimated Duration:** {v.estimated_duration_minutes} minutes")
        lines.append(f"- **Confidence:** {v.confidence}")
        if v.explanation:
            lines.append(f"- {v.explanation}")
        lines.append("")

    # Safety
    if decision.safety_assessment:
        s = decision.safety_assessment
        lines.append("## Safety")
        if s.safety_equipment:
            lines.append(f"- **Equipment:** {', '.join(s.safety_equipment)}")
        lines.append(f"- **Extra Engineer Required:** {'Yes' if s.extra_engineer_required else 'No'}")
        if s.safety_risks:
            lines.append(f"- **Risks:** {', '.join(s.safety_risks)}")
        else:
            lines.append("- **Risks:** None")
        if s.explanation:
            lines.append(f"- {s.explanation}")
        lines.append("")

    return "\n".join(lines)
