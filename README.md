# FailWatch 🛡️

**The Missing Safety Layer for AI Agents**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-009688.svg)](https://fastapi.tiangolo.com)

FailWatch prevents your AI agents from performing dangerous actions (e.g., unauthorized refunds, hallucinations, logic drift) by intercepting tool calls **before** they execute.

Unlike standard evaluation tools that check output *after* the fact, FailWatch acts as a synchronous **Circuit Breaker** in your production pipeline.

---

## 🎯 Why FailWatch?

When AI agents have access to production tools (databases, payment APIs, email), a single hallucination can cause real damage:

- **E-commerce**: Agent refunds $10,000 instead of $100
- **Banking**: Transfers money to wrong account due to context drift  
- **Operations**: Deletes production database thinking it's a test environment

**FailWatch sits between your agent and dangerous actions**, enforcing safety policies in real-time.

---

## ⚡ Key Features

### 🔒 **Deterministic Policy Checks**
Hard blocks on numeric limits, regex patterns, and business rules. No LLM guessing involved.
```python
policy = {
    "limit": 1000,
    "allowed_accounts": ["checking", "savings"],
    "forbidden_keywords": ["delete_all", "drop_table"]
}
```

### 🛡️ **Fail-Closed Architecture**
Financial-grade safety. If the guard server is down or times out, the action is **blocked by default**. Money stays put.

### 👥 **Human-in-the-Loop**
Seamlessly escalate "gray area" actions to Slack, email, or CLI for human approval before execution.

### 📊 **Audit Ready**
Every decision generates a `trace_id` and `decision_id` for compliance logging and post-incident analysis.

### ⚡ **Sub-50ms Latency**
Deterministic checks run in microseconds. LLM checks (when needed) complete in <2s with caching.

---

## 🚀 Quick Start

### 1️⃣ Installation

Install the SDK via pip:
```bash
pip install failwatch
```

To run the server locally (required), clone the repo:
```bash
git clone https://github.com/Ludwig1827/FailWatch.git
cd FailWatch/server
pip install -r ../requirements.txt
```

### 2️⃣ Start the Guard Server

The stateless server handles policy evaluation and LLM-based judgment:
```bash
cd server

# Set your OpenAI API Key (required for LLM judge)
# Windows (PowerShell):
$env:OPENAI_API_KEY="sk-..."

# Mac/Linux:
export OPENAI_API_KEY="sk-..."

# Start the server
uvicorn main:app --reload
```

✅ Server running at: **http://127.0.0.1:8000**

### 3️⃣ Run the Demo Agent

Open a **new terminal** in the project root (`FailWatch/`) and run the banking agent simulation:
```bash
python examples/banking_agent.py
```

### 4️⃣ See It In Action

The demo runs three scenarios:

1. **❌ Block**: Agent tries to transfer $2,000 (Policy Limit: $1,000)  
   → FailWatch blocks it instantly

2. **⏸️ Review**: Agent tries $5,000 transfer with override flag  
   → FailWatch pauses for human approval

3. **🔒 Fail-Closed**: System simulates network outage  
   → FailWatch prevents execution (safe default)

---

## 🛠️ Usage

### Basic Integration

Wrap your sensitive functions with the `@guard` decorator:
```python
from failwatch import FailWatchSDK

# Initialize SDK
fw = FailWatchSDK(
    api_url="http://localhost:8000",   
    default_fail_mode="closed"
)

@fw.guard(
    input_arg="user_request",
    output_arg="tool_args",
    policy={
        "limit": 1000,                 
        "require_approval_above": 500
    }
)
def refund_user(user_request: str, tool_args: dict):
    """This code ONLY runs if FailWatch approves"""
    amount = tool_args['amount']
    account = tool_args['account']
    
    # Execute the actual refund
    print(f"💸 Refunding ${amount} to {account}")
    return {"status": "success", "amount": amount}
```

### Custom Policies

Define complex business logic:
```python
policy = {
    # Hard limits (deterministic)
    "limit": 1000,
    "max_daily_total": 5000,
    
    # Pattern matching
    "allowed_account_pattern": r"^[A-Z]{2}\d{8}$",
    "forbidden_keywords": ["admin", "root", "sudo"],
    
    # Contextual rules (evaluated by LLM judge)
    "require_manager_approval_if": {
        "amount_above": 500,
        "account_type": "external",
        "time_after": "18:00"
    }
}

@fw.guard(
    input_arg="user_request",
    output_arg="tool_args",
    policy=policy
)
def process_transaction(user_request: str, tool_args: dict):
    # Your transaction logic here
    pass
```

---

## 📦 Architecture
```
┌─────────────────┐
│   Your Agent    │
│   (LangChain,   │
│   LlamaIndex,   │
│   Custom)       │
└────────┬────────┘
         │
         │ @guard decorator
         ▼
┌─────────────────┐
│  FailWatch SDK  │  ◄── Lightweight client
│  (Python)       │      Handles interception
└────────┬────────┘      & fallback logic
         │
         │ HTTP/gRPC
         ▼
┌─────────────────┐
│  Guard Server   │  ◄── Policy evaluation
│  (FastAPI)      │      + LLM judgment
└────────┬────────┘
         │
         ├─► Deterministic Checks (regex, limits)
         ├─► LLM Judge (logic drift detection)
         └─► Audit Logger (PostgreSQL/S3)
```

### Components

- **SDK** (`sdk/`): Lightweight Python client with fail-safe defaults
- **Server** (`server/`): FastAPI engine for policy evaluation
- **Dashboard**: Trace visualization at `http://localhost:8000/`
- **Examples** (`examples/`): Demo agents for banking, e-commerce, ops

---

## 📋 Use Cases

### Financial Services
- Block unauthorized transactions above policy limits
- Prevent wire transfers to unverified accounts
- Require dual approval for high-value operations

### E-commerce
- Stop agents from issuing excessive refunds
- Validate discount codes before applying
- Prevent inventory over-commitment

### DevOps
- Block destructive database operations in production
- Require confirmation for infrastructure changes
- Prevent accidental data deletion

### Healthcare
- Enforce HIPAA compliance on data access
- Require attestation before PHI disclosure
- Block unauthorized prescription modifications

---

## 🧪 Testing

Run the test suite:
```bash
# Unit tests
pytest tests/unit/

# Integration tests (requires server)
pytest tests/integration/

# Load tests
pytest tests/load/ -n auto
```

---

## 📈 Roadmap

- [x] Core policy engine
- [x] LLM-based logic drift detection
- [x] Human-in-the-loop approvals
- [ ] Dashboard UI for trace analysis
- [ ] Slack/Teams integration
- [ ] Multi-LLM judge support (Claude, Gemini)
- [ ] gRPC support for lower latency
- [ ] Policy versioning & rollback
- [ ] Custom webhook integrations
- [ ] SOC2 compliance toolkit

---

## 🤝 Contributing

We're looking for design partners running agents in:
- 🏦 Fintech
- ⚖️ Legal
- 🏥 Healthcare
- 🔧 DevOps

**Want to help build the standard for AI reliability?**

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/amazing-safety-check`)
3. Commit your changes (`git commit -m 'Add amazing safety check'`)
4. Push to the branch (`git push origin feature/amazing-safety-check`)
5. Open a Pull Request

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

---

## 🐛 Troubleshooting

### Server won't start
```bash
# Check if port 8000 is in use
lsof -i :8000  # Mac/Linux
netstat -ano | findstr :8000  # Windows

# Use a different port
uvicorn main:app --port 8001
```

### OpenAI API errors
```bash
# Verify your key is set
echo $OPENAI_API_KEY  # Mac/Linux
echo $env:OPENAI_API_KEY  # Windows

# Check your OpenAI quota
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

### Import errors
```python
# If you get "ModuleNotFoundError: No module named 'failwatch'"
# Make sure you installed via pip:
pip install failwatch

# If running examples from source, use:
from sdk import FailWatchSDK
```

---

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

Built with:
- [FastAPI](https://fastapi.tiangolo.com/) - Modern web framework
- [OpenAI](https://openai.com/) - LLM judge
- [LangChain](https://www.langchain.com/) - Agent orchestration

---

## 📞 Support

- 📧 Email: beeth.xue@gmail.com
- 📝 Issues: [GitHub Issues](https://github.com/Ludwig1827/FailWatch/issues)

---

<div align="center">

**Built with ❤️ for the AI safety community**

[⭐ Star us on GitHub](https://github.com/Ludwig1827/FailWatch) • [🚀 Get Started](#-quick-start)

</div>