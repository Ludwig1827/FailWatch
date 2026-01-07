import logging
import os
import sys
import uuid

from sdk import (
    FailWatchBlocked,
    FailWatchConnectionError,
    FailWatchRejected,
    FailWatchReviewPending,
    FailWatchSDK,
)

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("PaymentSystem")


def splunk_hook(event: str, data: dict):
    print(
        f"   📊 [AUDIT] {event} | Trace: {data.get('trace_id')} | DecID: {data.get('decision_id')}"
    )


# Init SDK
fw = FailWatchSDK(default_fail_mode="closed", default_timeout=20, on_event=splunk_hook)


# 1. Sync Function
@fw.guard(input_arg="msg", output_arg="action", policy={"limit": 1000})
def process_payment(msg, action, **kwargs):
    logger.info(f"💰 [REAL API] Charged: ${action.get('amount')}")
    return "SUCCESS"


# 2. Async Function
@fw.guard(
    input_arg="msg", output_arg="action", policy={"limit": 1000}, review_mode="async"
)
def process_async_payment(msg, action, **kwargs):
    logger.info(f"💰 [ASYNC API] Scheduled: ${action.get('amount')}")
    return "SCHEDULED"


def run_scenarios():
    trace_id = f"tr_{uuid.uuid4().hex[:6]}"
    print(f"\n--- START TEST [Trace: {trace_id}] ---")

    print("\n[SCENARIO 1] Sync Mode: High Amount ($2000 vs $1000 Limit)")
    try:
        process_payment(
            msg="Charge $2000", action={"amount": 2000}, metadata={"trace_id": trace_id}
        )
    except FailWatchRejected as e:
        logger.warning(f"🚫 REJECTED BY HUMAN | Trace: {e.context.get('trace_id')}")
    except FailWatchBlocked as e:
        logger.error(f"❌ BLOCKED | Reason: {e.analysis.get('explanation')}")
    except Exception as e:
        logger.error(f"⚠️ UNEXPECTED: {e}")

    print(
        "\n[SCENARIO 2] Async Mode: High Amount ($5000) with 'Review' Policy Override"
    )
    try:
        process_async_payment(
            msg="Async charge",
            action={"amount": 5000},
            policy={"hard_violation_action": "needs_human_review", "limit": 1000},
            metadata={"trace_id": trace_id + "_async"},
        )
    except FailWatchReviewPending as e:
        logger.info(
            f"⏳ REVIEW PENDING | Trace: {e.context.get('trace_id')} | Action paused for Slack."
        )
    except Exception as e:
        logger.error(f"⚠️ TEST FAILED: {e}")

    print("\n[SCENARIO 3] Offline Fail-Closed")
    fw.api_url = "http://localhost:9999"
    try:
        process_payment(
            msg="Offline",
            action={"amount": 500},
            metadata={"trace_id": trace_id + "_off"},
        )
    except FailWatchConnectionError as e:
        logger.critical(
            f"⚠️ FAIL-CLOSED | System Offline. Trace: {e.context.get('trace_id')}"
        )
    except Exception as e:
        logger.error(f"⚠️ UNEXPECTED: {e}")


if __name__ == "__main__":
    run_scenarios()
