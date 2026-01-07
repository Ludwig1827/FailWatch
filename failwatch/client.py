import functools
import inspect
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Union

import requests

from .exceptions import (
    FailWatchBlocked,
    FailWatchConnectionError,
    FailWatchRejected,
    FailWatchReviewPending,
)


# --- Default Review Handler ---
def cli_review_handler(analysis: Dict, input_text: str, output_text: str) -> bool:
    print(
        f"\n[FailWatch] ⚠️ Review Required. Risk: {int(analysis.get('confidence', 0) * 100)}%"
    )
    print(f"Reason: {analysis.get('explanation', ['Unknown'])[0]}")
    return input(">> Approve execution? (y/n): ").lower() == "y"


# --- Serialization Helpers ---
def safe_json_serialize(obj: Any) -> Any:
    """Safe serializer for the 'output_obj' field (keeps object structure if possible)."""
    try:
        json.dumps(obj)
        return obj
    except (TypeError, OverflowError):
        return {"_unserializable_repr": str(obj)}


def normalize_output_text(obj: Any) -> str:
    """
    UPGRADE 3: Smart stringifier for the 'output' text field.
    Prefer JSON for dicts so LLM can read it easily. Fallback to str().
    """
    if isinstance(obj, (dict, list)):
        try:
            return json.dumps(obj, ensure_ascii=False, default=str)
        except Exception:
            pass
    return str(obj or "")


# --- SDK Class ---
class FailWatchSDK:
    def __init__(
        self,
        api_url: str = "http://localhost:8000",
        default_fail_mode: str = "open",
        default_timeout: int = 15,
        default_review_mode: str = "sync",
        review_handler: Callable = cli_review_handler,
        on_event: Optional[Callable[[str, Dict], None]] = None,
    ):
        self.api_url = api_url
        self.fail_mode = default_fail_mode
        self.timeout = default_timeout
        self.review_mode = default_review_mode
        self.review_handler = review_handler
        self.on_event = on_event
        self.logger = logging.getLogger("FailWatch")

    def _emit(self, event_type: str, base_data: Dict, extra_details: Dict = None):
        """Helper to emit detailed audit events."""
        if self.on_event:
            try:
                payload = base_data.copy()
                if extra_details:
                    payload.update(extra_details)
                self.on_event(event_type, payload)
            except Exception as e:
                self.logger.error(f"on_event callback failed: {e}")

    def guard(
        self,
        input_arg: str = "prompt",
        steps_arg: str = "steps",
        output_arg: str = "proposed_output",
        task_type: str = "agent_workflow",
        policy: Optional[Dict] = None,
        metadata: Optional[Dict] = None,
        policy_arg_name: str = "policy",
        metadata_arg_name: str = "metadata",
        fail_mode: Optional[str] = None,
        timeout: Optional[int] = None,
        review_mode: Optional[str] = None,  # UPGRADE 1: Restored per-guard override
        fast_check: Optional[
            Callable[[str, List, Any, Dict], Union[bool, Dict]]
        ] = None,
    ):
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                timestamp = datetime.utcnow().isoformat() + "Z"
                decision_id = f"dec_{uuid.uuid4().hex[:8]}"  # UPGRADE 2: Decision ID

                # 1. Argument Extraction
                sig = inspect.signature(func)
                try:
                    bound = sig.bind_partial(*args, **kwargs)
                    bound.apply_defaults()
                    all_args = bound.arguments
                except Exception as e:
                    self.logger.warning(f"Arg binding failed ({e}). Using raw kwargs.")
                    all_args = kwargs

                runtime_kwargs = all_args.get("kwargs", {})
                if not isinstance(runtime_kwargs, dict):
                    runtime_kwargs = {}

                def get_arg(name):
                    if name in all_args:
                        return all_args[name]
                    if name in runtime_kwargs:
                        return runtime_kwargs[name]
                    return None

                user_input = str(get_arg(input_arg) or "Unknown Input")
                agent_steps = get_arg(steps_arg) or []
                proposed_output_obj = get_arg(output_arg)

                # UPGRADE 3: Better string normalization for LLM
                proposed_output_str = normalize_output_text(proposed_output_obj)

                # 2. Policy & Metadata Merge
                final_policy = policy.copy() if policy else {}
                runtime_policy = get_arg(policy_arg_name)
                if isinstance(runtime_policy, dict):
                    final_policy.update(runtime_policy)

                final_metadata = metadata.copy() if metadata else {}
                runtime_metadata = get_arg(metadata_arg_name)
                if isinstance(runtime_metadata, dict):
                    final_metadata.update(runtime_metadata)

                trace_id = final_metadata.get("trace_id")
                if not trace_id:
                    trace_id = f"tr_{uuid.uuid4().hex[:8]}"
                    final_metadata["trace_id"] = trace_id

                # Context & Audit Base
                ctx = final_metadata.copy()
                ctx.update(
                    {
                        "action_name": func.__name__,
                        "policy": final_policy,
                        "timestamp": timestamp,
                        "decision_id": decision_id,
                    }
                )

                # UPGRADE 2: Standard Base Event Payload
                audit_base = {
                    "trace_id": trace_id,
                    "decision_id": decision_id,
                    "action": func.__name__,
                    "timestamp": timestamp,
                }

                # 3. Fast Path
                if fast_check:
                    try:
                        fast_result = fast_check(
                            user_input, agent_steps, proposed_output_obj, final_policy
                        )
                        is_allowed = False
                        reason = "Fast check passed"

                        if isinstance(fast_result, bool):
                            is_allowed = fast_result
                        elif isinstance(fast_result, dict):
                            is_allowed = fast_result.get("allow", False)
                            reason = fast_result.get("reason", "Fast check passed")

                        if is_allowed:
                            self._emit("FAST_ALLOW", audit_base, {"reason": reason})
                            self.logger.info(
                                f"[{trace_id}] ⚡ Fast-Path Allow: {reason}"
                            )
                            return func(*args, **kwargs)
                    except Exception as e:
                        self.logger.warning(f"[{trace_id}] Fast check error: {e}")

                # 4. API Call
                current_fail_mode = fail_mode or self.fail_mode
                current_timeout = timeout or self.timeout
                current_review_mode = (
                    review_mode or self.review_mode
                )  # Use overridden value

                data = None
                api_error = None
                safe_output_obj = safe_json_serialize(proposed_output_obj)

                for attempt in range(2):
                    try:
                        payload = {
                            "task_type": task_type,
                            "input": user_input,
                            "output": proposed_output_str,  # Normalized JSON string
                            "output_obj": safe_output_obj,
                            "steps": agent_steps,
                            "context": ctx,
                        }
                        res = requests.post(
                            f"{self.api_url}/analyze",
                            json=payload,
                            timeout=current_timeout,
                        )

                        if res.status_code == 200:
                            data = res.json()
                            # Capture Server Analysis ID
                            if "id" in data:
                                ctx["analysis_id"] = data["id"]
                                audit_base["analysis_id"] = data["id"]
                            break
                        elif 400 <= res.status_code < 500:
                            api_error = f"HTTP {res.status_code}: {res.text}"
                            break
                        else:
                            api_error = f"HTTP {res.status_code}"

                    except Exception as e:
                        api_error = str(e)
                        if attempt == 0:
                            time.sleep(0.5)

                # 5. Fail Mode Handling
                if not data:
                    msg = f"FailWatch Unavailable ({api_error}). Mode: {current_fail_mode}"
                    self.logger.warning(msg)

                    if current_fail_mode == "closed":
                        self._emit("FAIL_CLOSED", audit_base, {"error": msg})
                        raise FailWatchConnectionError(msg, context=ctx)

                    elif current_fail_mode == "open_warn":
                        self._emit("FAIL_OPEN_WARN", audit_base, {"error": msg})
                        self.logger.warning(
                            f"[{trace_id}] ⚠️ FAIL-OPEN WARN: Bypass due to system offline."
                        )
                        return func(*args, **kwargs)

                    else:  # open
                        self._emit("FAIL_OPEN", audit_base, {"error": msg})
                        return func(*args, **kwargs)

                # 6. Verdict Enforcement
                action = data.get("recommended_action", "none")
                explanation = data.get("explanation", ["Unknown reason"])

                if action == "block":
                    self._emit("BLOCK", audit_base, {"reason": explanation})
                    raise FailWatchBlocked(
                        message=f"Blocked: {'; '.join(explanation)}",
                        analysis=data,
                        context=ctx,
                    )

                elif action == "needs_human_review":
                    self._emit("REVIEW_REQ", audit_base, {"reason": explanation})

                    if current_review_mode == "async":
                        raise FailWatchReviewPending(
                            "Action paused for async review.",
                            analysis=data,
                            context=ctx,
                        )

                    approved = self.review_handler(
                        data, user_input, proposed_output_str
                    )

                    if not approved:
                        self._emit("REVIEW_REJECT", audit_base)
                        raise FailWatchRejected(
                            "Reviewer rejected this action.", analysis=data, context=ctx
                        )

                    self._emit("REVIEW_APPROVE", audit_base)
                    print("✅ [FailWatch] Approved. Executing...")
                    return func(*args, **kwargs)

                # Allow
                self._emit("ALLOW", audit_base)
                return func(*args, **kwargs)

            return wrapper

        return decorator
