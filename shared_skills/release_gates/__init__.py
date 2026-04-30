def evaluate_release_gates(*, tests_passed, policy_passed, min_success_rate, scorecard):
    success_rate = scorecard.get("success_rate", 0.0)
    passed = tests_passed and policy_passed and success_rate >= min_success_rate
    return {
        "passed": passed,
        "tests_passed": tests_passed,
        "policy_passed": policy_passed,
        "success_rate": success_rate,
        "min_success_rate": min_success_rate,
    }
