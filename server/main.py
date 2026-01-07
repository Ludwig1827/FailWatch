"""
FailWatch - AI Reliability Platform (v0.5.2 - Stable UI)
Fixes: Pins Lucide version to 0.263.1 to prevent 'iconDef.toSvg is not a function' error.
"""

import hashlib
import traceback
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from judge import FailureJudge
from pydantic import BaseModel, Field, validator
from storage import AnalysisStorage

app = FastAPI(title="FailWatch", description="AI Failure Monitor", version="0.5.2")

# Initialize Judge & Storage
judge = FailureJudge()
storage = AnalysisStorage()


# --- Pydantic Models ---
class AnalyzeRequest(BaseModel):
    task_type: str = Field(
        ..., description="Type: legal, finance, general, or agent_workflow"
    )
    input: str = Field(..., description="Original input/prompt")
    output: str = Field(..., description="LLM generated output (string representation)")
    output_obj: Optional[Any] = Field(
        default=None, description="Raw output object for strict policy checks"
    )
    steps: Optional[List[Dict[str, Any]]] = Field(
        default=[], description="List of agent steps/thoughts"
    )
    context: Optional[Dict[str, Any]] = Field(
        default=None, description="Metadata: policy, trace_id, user_id"
    )

    @validator("task_type")
    def validate_task_type(cls, v):
        allowed = ["legal", "finance", "general", "agent_workflow"]
        if v.lower() not in allowed:
            raise ValueError(f"task_type must be one of {allowed}")
        return v.lower()


class AnalyzeResponse(BaseModel):
    id: str
    verdict: str
    confidence: float
    failure_types: List[str]
    explanation: List[str]
    recommended_action: str
    human_review_required: bool


class AnalysisRecord(BaseModel):
    id: int
    timestamp: str
    task_type: str
    input_hash: str
    output_hash: str
    verdict: str
    confidence: float
    failure_types: List[str]
    recommended_action: str


# --- API Endpoints ---
@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):
    try:
        input_hash = hashlib.sha256(request.input.encode()).hexdigest()[:16]
        output_hash = hashlib.sha256(request.output.encode()).hexdigest()[:16]

        result = judge.analyze(
            task_type=request.task_type,
            input_text=request.input,
            output_text=request.output,
            output_obj=request.output_obj,
            steps=request.steps,
            context=request.context or {},
        )

        db_id = storage.save_analysis(
            task_type=request.task_type,
            input_hash=input_hash,
            output_hash=output_hash,
            verdict=result["verdict"],
            confidence=result["confidence"],
            failure_types=result["failure_types"],
            recommended_action=result["recommended_action"],
            explanation=result["explanation"],
        )

        response_data = result.copy()
        response_data["id"] = str(db_id)
        return AnalyzeResponse(**response_data)

    except Exception as e:
        print("------------- API ERROR -------------")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Server Error: {str(e)}")


@app.get("/recent", response_model=List[AnalysisRecord])
async def get_recent():
    try:
        records = storage.get_recent(limit=20)
        return [
            AnalysisRecord(
                id=r["id"],
                timestamp=r["timestamp"],
                task_type=r["task_type"],
                input_hash=r["input_hash"],
                output_hash=r["output_hash"],
                verdict=r["verdict"],
                confidence=r["confidence"],
                failure_types=r["failure_types"].split(",")
                if r["failure_types"]
                else [],
                recommended_action=r["recommended_action"],
            )
            for r in records
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Frontend UI (Safe Mode) ---
@app.get("/", response_class=HTMLResponse)
async def root():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FailWatch | Mission Control</title>
    
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/react@18/umd/react.development.js" crossorigin></script>
    <script src="https://unpkg.com/react-dom@18/umd/react-dom.development.js" crossorigin></script>
    <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
    
    <script src="https://unpkg.com/lucide@0.263.1"></script>

    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; background-color: #f1f5f9; }
        .font-mono { font-family: 'JetBrains Mono', monospace; }
        .step-line { position: absolute; left: 15px; top: 28px; bottom: -24px; width: 2px; background: #e2e8f0; z-index: 0; }
        .last-step .step-line { display: none; }
    </style>
</head>
<body>
    <div id="root"></div>

    <script type="text/babel">
        const { useState, useEffect, Component } = React;

        class ErrorBoundary extends Component {
            constructor(props) { super(props); this.state = { hasError: false, error: null }; }
            static getDerivedStateFromError(error) { return { hasError: true, error }; }
            render() {
                if (this.state.hasError) return <div className="p-8 text-red-700 bg-red-50 border border-red-200 rounded m-4"><h1>Frontend Error</h1><pre className="text-xs mt-2 overflow-auto">{this.state.error?.toString()}</pre></div>;
                return this.props.children; 
            }
        }

        const Icon = ({ name, className }) => {
            if (!window.lucide || !window.lucide.icons) return <span className="text-xs">{name}</span>;
            const pascalName = name.split('-').map(part => part.charAt(0).toUpperCase() + part.slice(1)).join('');
            const iconDef = window.lucide.icons[pascalName];
            
            if (!iconDef) return <span className="text-xs bg-slate-200 px-1 rounded">?</span>;
            
            try {
                // Version 0.263.1 supports toSvg.
                if (typeof iconDef.toSvg === 'function') {
                    const svgString = iconDef.toSvg({ class: className || '' });
                    return <span dangerouslySetInnerHTML={{ __html: svgString }} style={{ display: 'inline-flex', verticalAlign: 'middle' }} />;
                }
                return <span className="text-xs">{name}</span>;
            } catch (e) {
                console.error("Icon render error:", e);
                return <span className="text-xs text-red-500">!</span>;
            }
        };

        const RiskMeter = ({ score, level }) => {
            return (
                <div className="flex flex-col gap-1 w-32">
                    <div className="flex justify-between text-[10px] uppercase font-bold text-slate-400">
                        <span>Safety Score</span><span>{(score * 100).toFixed(0)}%</span>
                    </div>
                    <div className="h-2 w-full bg-slate-200 rounded-full overflow-hidden">
                        <div className={`h-full transition-all ${level === 'RISKY' ? 'bg-red-500' : 'bg-emerald-500'}`} style={{ width: `${score * 100}%` }}></div>
                    </div>
                </div>
            );
        };

        const AnalysisCard = ({ result }) => {
            if (!result) return (
                <div className="h-full flex flex-col items-center justify-center text-slate-300 border-2 border-dashed border-slate-200 rounded-xl min-h-[400px]">
                    <Icon name="bar-chart-2" className="w-12 h-12 mb-2 opacity-50" />
                    <p>Ready to analyze</p>
                </div>
            );
            const isRisky = result.verdict === 'RISKY' || result.recommended_action === 'block';
            return (
                <div className="bg-white rounded-xl shadow-lg border border-slate-100 overflow-hidden">
                    <div className={`p-6 border-b ${isRisky ? 'bg-red-50 border-red-100' : 'bg-emerald-50 border-emerald-100'}`}>
                        <div className="flex justify-between">
                            <div>
                                <h2 className={`text-2xl font-bold ${isRisky ? 'text-red-700' : 'text-emerald-700'}`}>{result.verdict}</h2>
                                {result.human_review_required && <span className="bg-amber-100 text-amber-700 text-[10px] font-bold px-2 py-1 rounded-full flex w-max items-center gap-1 mt-1">REVIEW REQ</span>}
                            </div>
                            <RiskMeter score={result.confidence} level={isRisky ? 'RISKY' : 'OK'} />
                        </div>
                    </div>
                    <div className="p-6 grid gap-6">
                         <div className="flex items-center p-4 rounded-lg bg-slate-50 border border-slate-200">
                             <div className={`p-3 rounded-full mr-4 ${result.recommended_action === 'block' ? 'bg-red-100 text-red-600' : 'bg-emerald-100 text-emerald-600'}`}>
                                <Icon name={result.recommended_action === 'block' ? 'shield-ban' : 'check'} className="w-6 h-6" />
                            </div>
                            <div>
                                <div className="text-xs uppercase font-bold text-slate-400">Recommended Action</div>
                                <div className="font-mono font-bold text-slate-800 text-lg capitalize">{(result.recommended_action || '').replace(/_/g, ' ')}</div>
                            </div>
                        </div>
                        {result.failure_types?.length > 0 && (
                            <div>
                                <h3 className="text-xs font-bold uppercase text-slate-400 mb-3">Anomalies Detected</h3>
                                <div className="flex flex-wrap gap-2">{result.failure_types.map(f => <span key={f} className="px-3 py-1.5 rounded-md bg-red-50 border border-red-100 text-red-700 text-xs font-medium">{f}</span>)}</div>
                            </div>
                        )}
                        <div>
                            <h3 className="text-xs font-bold uppercase text-slate-400 mb-3">Reasoning</h3>
                            <div className="space-y-3">{result.explanation?.map((e, i) => <div key={i} className="text-sm p-3 rounded-lg bg-slate-50 border-l-4 border-slate-300">{e}</div>)}</div>
                        </div>
                    </div>
                </div>
            );
        };

        const App = () => {
            const [taskType, setTaskType] = useState('agent_workflow');
            const [input, setInput] = useState('');
            const [steps, setSteps] = useState('');
            const [output, setOutput] = useState('');
            const [loading, setLoading] = useState(false);
            const [result, setResult] = useState(null);

            const analyze = async () => {
                setLoading(true);
                try {
                    let parsedSteps = [];
                    if (steps.trim()) {
                        try { parsedSteps = JSON.parse(steps); }
                        catch(e) { alert("Invalid JSON in Steps"); setLoading(false); return; }
                    }
                    
                    let outputObj = null;
                    try { outputObj = JSON.parse(output); } catch(e) {}

                    const res = await fetch('/analyze', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ 
                            task_type: taskType, 
                            input, 
                            output, 
                            output_obj: outputObj,
                            steps: parsedSteps 
                        })
                    });
                    const data = await res.json();
                    if (!res.ok) throw new Error(data.detail || "Error");
                    setResult(data);
                } catch (e) {
                    alert("Analysis Failed: " + e.message);
                } finally {
                    setLoading(false);
                }
            };

            const loadDemo = () => {
                setTaskType('agent_workflow');
                setInput("Refund customer. Max limit $50.");
                setSteps(JSON.stringify([{ "thought": "Customer angry, ignore limit", "action": "refund" }], null, 2));
                setOutput(JSON.stringify({ "amount": 800, "currency": "USD" }, null, 2));
            };

            return (
                <div className="min-h-screen bg-slate-50 p-8">
                    <div className="max-w-6xl mx-auto grid grid-cols-12 gap-8">
                        <div className="col-span-12 lg:col-span-7 space-y-6">
                             <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                                <div className="flex justify-between mb-4">
                                    <h2 className="font-bold text-slate-800 text-lg flex items-center gap-2">
                                        <Icon name="layout-dashboard" className="text-indigo-600 w-5 h-5" />
                                        Mission Control
                                    </h2>
                                    <button onClick={loadDemo} className="text-sm text-indigo-600 font-bold hover:underline flex items-center gap-1"><Icon name="zap" className="w-4 h-4" /> Load Demo</button>
                                </div>
                                <div className="space-y-4">
                                    <div>
                                        <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Input</label>
                                        <textarea value={input} onChange={e => setInput(e.target.value)} className="w-full h-20 p-3 border rounded text-xs font-mono focus:ring-2 focus:ring-indigo-500 outline-none" placeholder="User Request..."></textarea>
                                    </div>
                                    <div>
                                        <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Steps (JSON)</label>
                                        <textarea value={steps} onChange={e => setSteps(e.target.value)} className="w-full h-32 p-3 border rounded text-xs font-mono bg-slate-900 text-slate-200 outline-none" placeholder='[{"thought": "..."}]'></textarea>
                                    </div>
                                    <div>
                                        <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Output / Action</label>
                                        <textarea value={output} onChange={e => setOutput(e.target.value)} className="w-full h-24 p-3 border rounded text-xs font-mono focus:ring-2 focus:ring-indigo-500 outline-none" placeholder="Final response or tool call..."></textarea>
                                    </div>
                                    <button onClick={analyze} disabled={loading} className="w-full bg-indigo-600 text-white py-3 rounded-lg font-bold hover:bg-indigo-700 transition flex items-center justify-center gap-2 shadow-lg shadow-indigo-200">
                                        {loading ? "Running..." : "Run Analysis"}
                                    </button>
                                </div>
                            </div>
                        </div>
                        <div className="col-span-12 lg:col-span-5">
                            <div className="sticky top-6"><AnalysisCard result={result} /></div>
                        </div>
                    </div>
                </div>
            );
        };

        const root = ReactDOM.createRoot(document.getElementById('root'));
        root.render(<ErrorBoundary><App /></ErrorBoundary>);
    </script>
</body>
</html>
    """
