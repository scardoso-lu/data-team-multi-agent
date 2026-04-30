def rank_plan_steps(steps):
    scored = []
    for step in steps:
        score = (2 if step.get("blocked") else 0) + int(step.get("impact", 0)) - int(step.get("effort", 0))
        scored.append({**step, "score": score})
    return sorted(scored, key=lambda s: s["score"], reverse=True)
