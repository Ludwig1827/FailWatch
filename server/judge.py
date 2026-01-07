"""
Failure Judge Engine (v0.6 - Policy Aware & Configurable)
Features:
1. Deterministic Policy Check: Compares numbers (amount > limit) without LLM.
2. Configurable Severity: Policy can decide if hard violations are 'block' or 'review'.
"""

import json
import os
from typing import Any, Dict, List

from dotenv import load_dotenv

load_dotenv(override=True)


class FailureJudge:
    def __init__(self, rules_file: str = "rules.json"):
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.rules = self._load_rules(rules_file)

    def _load_rules(self, filepath: str) -> Dict[str, Any]:
        try:
            with open(filepath, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def analyze(
        self,
        task_type: str,
        input_text: str,
        output_text: str,
        output_obj: Any = None,  # Accepts raw object (e.g., {"amount": 2000})
        steps: List[Dict] = [],
        context: Dict = {},
    ) -> Dict[str, Any]:
        failures = []
        explanations = []

        # 1. Deterministic Policy Check (The "Hard Rules")
        # Checks numeric constraints before calling LLM
        policy_result = self._check_policy_violations(
            context.get("policy", {}), output_obj
        )
        if policy_result:
            failures.extend(policy_result["failures"])
            explanations.extend(policy_result["explanations"])

        # 2. Run Heuristics (Regex / Keywords)
        heuristic_result = self._heuristic_judge(task_type, input_text, output_text)
        failures.extend(heuristic_result["failure_types"])
        explanations.extend(heuristic_result["explanation"])

        # 3. Run LLM Judge (Nuance / Logic Drift)
        llm_result = self._llm_judge(task_type, input_text, output_text, steps, context)
        failures.extend(llm_result.get("failure_types", []))
        explanations.extend(llm_result.get("explanation", []))

        # 4. Final Verdict Logic
        failures = list(set(failures))
        is_hard_violation = "constraint_violation" in failures

        # Determine base verdict
        final_verdict = (
            "RISKY" if (failures or llm_result.get("verdict") == "RISKY") else "OK"
        )

        # --- Policy Configuration Logic ---
        # Default behavior for hard violation is "block", but policy can downgrade it to "review".
        policy = context.get("policy", {}) or {}
        hard_action = policy.get(
            "hard_violation_action", "block"
        )  # "block" | "needs_human_review"

        if is_hard_violation:
            if hard_action == "needs_human_review":
                recommended_action = "needs_human_review"
                human_review = True
                explanations.append(
                    f"(Policy) Hard violation escalated to Human Review (Action: {hard_action})."
                )
            else:
                recommended_action = "block"
                human_review = False

        elif final_verdict == "RISKY":
            # Soft violations (LLM suspicion) usually default to review
            recommended_action = "needs_human_review"
            human_review = True
        else:
            recommended_action = "none"
            human_review = False

        return {
            "verdict": final_verdict,
            "confidence": llm_result.get(
                "confidence", 1.0 if is_hard_violation else 0.5
            ),
            "failure_types": failures,
            "explanation": explanations,
            "recommended_action": recommended_action,
            "human_review_required": human_review,
        }

    def _check_policy_violations(self, policy: Dict, output_obj: Any) -> Dict:
        """
        Explicitly checks numeric limits against policy.
        Matches keys like 'limit', 'max_refund_amount', 'global_hard_limit'.
        """
        if not isinstance(output_obj, dict) or not policy:
            return None

        failures = []
        explanations = []

        # Normalize keys (handle standard variations in your demo)
        limit = (
            policy.get("limit")
            or policy.get("max_refund_amount")
            or policy.get("global_hard_limit")
        )
        amount = output_obj.get("amount")

        if limit is not None and amount is not None:
            try:
                limit_val = float(limit)
                amount_val = float(amount)
                if amount_val > limit_val:
                    failures.append("constraint_violation")
                    explanations.append(
                        f"Policy Violation: Amount {amount_val} exceeds limit {limit_val}"
                    )
            except Exception:
                pass

        if failures:
            return {"failures": failures, "explanations": explanations}
        return None

    def _heuristic_judge(
        self, task_type: str, input_text: str, output_text: str
    ) -> Dict[str, Any]:
        failures = []
        explanations = []

        # Domain Rule Check
        rules = self.rules.get(task_type, self.rules.get("general", {}))
        for forbidden in rules.get("forbidden_changes", []):
            if (
                forbidden.lower() in output_text.lower()
                and forbidden.lower() not in input_text.lower()
            ):
                failures.append("constraint_violation")
                explanations.append(f"Output introduced forbidden term: '{forbidden}'")

        return {"failure_types": failures, "explanation": explanations}

    def _llm_judge(
        self,
        task_type: str,
        input_text: str,
        output_text: str,
        steps: List[Dict],
        context: Dict,
    ) -> Dict[str, Any]:
        if not self.openai_api_key:
            return {}
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.openai_api_key)

            steps_text = "NO INTERMEDIATE STEPS PROVIDED"
            if steps:
                steps_text = "\n".join(
                    [f"STEP {i + 1}: {json.dumps(s)}" for i, s in enumerate(steps)]
                )

            # Inject Policy into Prompt
            policy_text = json.dumps(context.get("policy", {}))

            system_prompt = f"""You are FailWatch, an AI Reliability Engineer. 
Active Policy: {policy_text}

DETECT: 
1. Constraint Violation (Output contradicts Policy or Input).
2. Workflow Logic Drift (Thought explicitly ignores rules).
3. Omission or Hallucination.

Return JSON: {{ "verdict": "OK"|"RISKY", "confidence": 0.0-1.0, "failure_types": [], "explanation": [] }}"""

            user_prompt = f"""INPUT:\n{input_text}\n\nAGENT WORKFLOW STEPS:\n{steps_text}\n\nFINAL OUTPUT:\n{output_text}"""

            response = client.chat.completions.create(
                model=self.openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            # Fallback safe mode
            return {
                "verdict": "RISKY",
                "confidence": 0.0,
                "failure_types": ["system_error"],
                "explanation": [f"LLM Error: {str(e)}"],
            }
