"""
Constrained NL Query Agent using LangGraph.
No raw SQL generation - only whitelisted parameterized function calls.
"""
from typing import Literal, Optional
from enum import Enum
from datetime import date, datetime
from pydantic import BaseModel, Field
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, END

from app.services.query_tools import (
    get_vendor_spend,
    get_avg_tax_rate,
    list_flagged_documents,
    get_invoice_summary,
    get_top_vendors_by_spend,
)
from app.db.session import async_session_maker as AsyncSessionLocal, SyncSessionLocal
from app.models.query_log import NLQueryLog
from app.tier_config.tiers import feature_enabled


# --- Intent Classification ---

class IntentCategory(str, Enum):
    vendor_spend = "vendor_spend"
    avg_tax_rate = "avg_tax_rate"
    flagged_documents = "flagged_documents"
    invoice_summary = "invoice_summary"
    top_vendors = "top_vendors"
    unsupported = "unsupported"


class IntentResult(BaseModel):
    intent: IntentCategory
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


# --- Argument Extraction ---

class VendorSpendArgs(BaseModel):
    vendor_name: str
    date_from: date
    date_to: date


class AvgTaxRateArgs(BaseModel):
    vendor_name: Optional[str] = None
    date_from: date
    date_to: date


class FlaggedDocumentsArgs(BaseModel):
    severity: Optional[str] = None
    date_from: date
    date_to: date


class InvoiceSummaryArgs(BaseModel):
    document_id: str


class TopVendorsArgs(BaseModel):
    date_from: date
    date_to: date
    limit: int = 10


# --- Graph State ---

class QueryState(TypedDict):
    question: str
    intent: Optional[IntentResult]
    arguments: Optional[BaseModel]
    tool_result: Optional[dict]
    answer: Optional[str]
    structured_data: Optional[dict]
    error: Optional[str]


# --- Node Functions ---

async def intent_classifier_node(state: QueryState) -> QueryState:
    """Classify the question into one of the whitelisted intent categories."""
    question = state["question"].lower()
    
    # Simple keyword-based classification (in production, use LLM)
    intent = IntentCategory.unsupported
    confidence = 0.0
    reasoning = ""
    
    # Top vendors patterns - check first since "top" is specific
    if any(kw in question for kw in ["top", "highest", "biggest", "most"]) and "vendor" in question:
        intent = IntentCategory.top_vendors
        confidence = 0.85
        reasoning = "Question asks for top vendors by spend"
    
    # Vendor spend patterns - "paid", "spend", "amount" with vendor context
    # More inclusive: if question has spend/paid/total/amount/cost keywords, assume vendor spend
    # unless it clearly matches another category
    elif any(kw in question for kw in ["spend", "paid", "total", "amount", "cost"]):
        intent = IntentCategory.vendor_spend
        confidence = 0.85
        reasoning = "Question asks about vendor spend/amount paid"
    
    # Tax rate patterns
    elif any(kw in question for kw in ["tax rate", "tax", "rate"]) and "average" in question:
        intent = IntentCategory.avg_tax_rate
        confidence = 0.85
        reasoning = "Question asks about average tax rate"
    
    # Flagged documents patterns
    elif any(kw in question for kw in ["flag", "fraud", "suspicious", "flagged"]):
        intent = IntentCategory.flagged_documents
        confidence = 0.9
        reasoning = "Question asks about flagged/fraudulent documents"
    
    # Invoice summary patterns
    elif any(kw in question for kw in ["invoice", "document", "summary", "details"]) and any(kw in question for kw in ["invoice", "document", "id", "number"]):
        intent = IntentCategory.invoice_summary
        confidence = 0.8
        reasoning = "Question asks for specific invoice/document summary"
    
    # Top vendors patterns
    elif any(kw in question for kw in ["top", "highest", "biggest", "most"]) and "vendor" in question:
        intent = IntentCategory.top_vendors
        confidence = 0.85
        reasoning = "Question asks for top vendors by spend"
    
    # Default to unsupported
    else:
        intent = IntentCategory.unsupported
        confidence = 0.5
        reasoning = "Question does not match any whitelisted query category"
    
    state["intent"] = IntentResult(
        intent=intent,
        confidence=confidence,
        reasoning=reasoning
    )
    
    return state


import logging
logger = logging.getLogger(__name__)


async def argument_extraction_node(state: QueryState) -> QueryState:
    """Extract and validate arguments from the question for the classified intent."""
    intent = state["intent"]
    
    if intent.intent == IntentCategory.unsupported:
        state["error"] = "Question category not supported"
        return state
    
    question = state["question"]
    
    # Extract common date range - default to current year if not specified
    today = date.today()
    default_from = date(today.year, 1, 1)
    default_to = today
    
    # Simple extraction (in production, use LLM with structured output)
    args = None
    
    try:
        if intent.intent == IntentCategory.vendor_spend:
            # Extract vendor name - simple heuristic
            words = state["question"].split()
            vendor_idx = -1
            for i, w in enumerate(words):
                if w in ["vendor", "vendor", "supplier", "for", "paid"]:
                    vendor_idx = i + 1
                    break
            vendor_name = words[vendor_idx] if vendor_idx >= 0 and vendor_idx < len(words) else "unknown"
            
            logger.info(f"vendor_spend extraction: question='{state['question']}', extracted_vendor='{vendor_name}'")
            
            args = VendorSpendArgs(
                vendor_name=vendor_name,
                date_from=default_from,
                date_to=default_to,
            )
        
        elif intent.intent == IntentCategory.avg_tax_rate:
            vendor_name = None
            if "vendor" in state["question"]:
                words = state["question"].split()
                vendor_idx = -1
                for i, w in enumerate(words):
                    if w in ["vendor", "vendor", "supplier", "for"]:
                        vendor_idx = i + 1
                        break
                vendor_name = words[vendor_idx] if vendor_idx >= 0 and vendor_idx < len(words) else None
            
            args = AvgTaxRateArgs(
                vendor_name=vendor_name,
                date_from=default_from,
                date_to=default_to,
            )
        
        elif intent.intent == IntentCategory.flagged_documents:
            sev = None
            for s in ["critical", "high", "medium", "low"]:
                if s in state["question"]:
                    sev = s
                    break
            args = FlaggedDocumentsArgs(
                severity=sev,
                date_from=default_from,
                date_to=default_to,
            )
        
        elif intent.intent == IntentCategory.invoice_summary:
            # Extract document ID - look for UUID-like pattern or invoice number
            import re
            uuid_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
            match = re.search(uuid_pattern, state["question"])
            doc_id = match.group(0) if match else "unknown"
            args = InvoiceSummaryArgs(document_id=doc_id)
        
        elif intent.intent == IntentCategory.top_vendors:
            limit = 10
            if "top" in state["question"]:
                words = state["question"].split()
                for i, w in enumerate(words):
                    if w == "top" and i + 1 < len(words) and words[i + 1].isdigit():
                        limit = int(words[i + 1])
                        break
            
            args = TopVendorsArgs(
                date_from=default_from,
                date_to=default_to,
                limit=limit,
            )
        
        state["arguments"] = args
    
    except Exception as e:
        state["error"] = f"Failed to extract arguments: {str(e)}"
    
    return state


async def tool_execution_node(state: QueryState) -> QueryState:
    """Execute the whitelisted function with validated arguments."""
    intent = state["intent"]
    args = state["arguments"]
    error = state.get("error")
    
    if error or intent.intent == IntentCategory.unsupported:
        return state
    
    if not args:
        state["error"] = "No arguments extracted"
        return state
    
    async with AsyncSessionLocal() as db:
        try:
            result = None
            
            if intent.intent == IntentCategory.vendor_spend:
                result = await get_vendor_spend(db, args.vendor_name, args.date_from, args.date_to)
            elif intent.intent == IntentCategory.avg_tax_rate:
                result = await get_avg_tax_rate(db, args.vendor_name, args.date_from, args.date_to)
            elif intent.intent == IntentCategory.flagged_documents:
                result = await list_flagged_documents(db, args.severity, args.date_from, args.date_to)
            elif intent.intent == IntentCategory.invoice_summary:
                result = await get_invoice_summary(db, args.document_id)
            elif intent.intent == IntentCategory.top_vendors:
                result = await get_top_vendors_by_spend(db, args.date_from, args.date_to, args.limit)
            
            state["tool_result"] = result
            state["structured_data"] = result
        
        except Exception as e:
            state["error"] = f"Tool execution failed: {str(e)}"
    
    return state


async def response_formatter_node(state: QueryState) -> QueryState:
    """Format the tool result into a natural language answer."""
    error = state.get("error")
    intent = state["intent"]
    tool_result = state.get("tool_result")
    
    # Handle unsupported intent first
    if intent and intent.intent == IntentCategory.unsupported:
        state["answer"] = "I'm unable to answer that question. My capabilities are limited to: vendor spend queries, average tax rate calculations, flagged document listings, invoice summaries, and top vendor listings."
        return state
    
    if error:
        state["answer"] = f"I encountered an error: {error}"
        return state
    
    if not tool_result:
        state["answer"] = "No results found for your query."
        return state
    
    # Format based on intent
    if intent.intent == IntentCategory.vendor_spend:
        r = tool_result
        state["answer"] = f"We've paid {r['vendor']} a total of ${r['total_spend']} across {r['invoice_count']} invoices from {r['period']}."
    
    elif intent.intent == IntentCategory.avg_tax_rate:
        r = tool_result
        vendor_text = f" for {r['vendor']}" if r.get('vendor') and r['vendor'] != "all" else ""
        state["answer"] = f"The average tax rate{vendor_text} is {r['avg_tax_rate']} across {r['invoice_count']} invoices from {r['period']}."
    
    elif intent.intent == IntentCategory.flagged_documents:
        r = tool_result
        if not r:
            sev_text = f" with severity {state['arguments'].severity}" if state.get('arguments') and state['arguments'].severity else ""
            state["answer"] = f"No flagged documents found{sev_text} from {default_from} to {default_to}."
        else:
            flag_parts = []
            for d in r:
                flag_strs = [f"{f['type']} [{f['severity']}]" for f in d['flags']]
                flag_parts.append(f"{d['filename']} ({', '.join(flag_strs)})")
            state["answer"] = f"Found {len(r)} flagged document(s): " + "; ".join(flag_parts)
    
    elif intent.intent == IntentCategory.invoice_summary:
        r = tool_result
        if "error" in r:
            state["answer"] = "Invoice not found."
        else:
            state["answer"] = (
                f"Invoice {r.get('invoice_number', 'N/A')} from {r.get('vendor_name', 'N/A')} "
                f"dated {r.get('invoice_date', 'N/A')} for ${r.get('total_amount', 'N/A')}. "
                f"Status: {r.get('status', 'N/A')}. "
                f"Fraud flags: {len(r.get('fraud_flags', []))}. "
                f"Rule violations: {r.get('rule_violations', 0)}."
            )
    
    elif intent.intent == IntentCategory.top_vendors:
        r = tool_result
        if not r:
            state["answer"] = f"No vendor spend data found for the period."
        else:
            vendor_list = ", ".join([f"{v['vendor']} (${v['total_spend']})" for v in r[:5]])
            state["answer"] = f"Top vendors by spend: {vendor_list}" + (f" and {len(r) - 5} more" if len(r) > 5 else "") + f" from {default_from} to {default_to}."
    
    return state


# --- Build Graph ---

def build_nl_query_graph() -> StateGraph:
    """Build the NL query agent graph."""
    graph = StateGraph(QueryState)
    
    graph.add_node("intent_classifier", intent_classifier_node)
    graph.add_node("argument_extraction", argument_extraction_node)
    graph.add_node("tool_execution", tool_execution_node)
    graph.add_node("response_formatter", response_formatter_node)
    
    graph.set_entry_point("intent_classifier")
    graph.add_edge("intent_classifier", "argument_extraction")
    graph.add_edge("argument_extraction", "tool_execution")
    graph.add_edge("tool_execution", "response_formatter")
    graph.add_edge("response_formatter", END)
    
    return graph.compile()


# --- Main Entry Point ---

async def run_nl_query(question: str, user_id: str) -> dict:
    """Run the NL query agent and log the result."""
    if not feature_enabled("nl_query"):
        return {
            "answer": "Natural language query feature is not enabled in your current tier.",
            "structured_data": None,
            "intent": "unsupported",
            "error": "feature_disabled"
        }
    
    graph = build_nl_query_graph()
    
    initial_state = QueryState(
        question=question,
        intent=None,
        arguments=None,
        tool_result=None,
        answer=None,
        structured_data=None,
        error=None,
    )
    
    result = await graph.ainvoke(initial_state)
    
    # Log to nl_query_log
    intent_obj = result.get("intent")
    intent_value = intent_obj.intent if intent_obj else "unknown"
    intent_str = intent_value.value if hasattr(intent_value, 'value') else str(intent_value)
    
    with SyncSessionLocal() as db:
        log = NLQueryLog(
            user_id=user_id,
            question_text=question,
            resolved_intent=intent_str,
            tool_called=intent_str if intent_str != "unsupported" else None,
            tool_args=str(result.get("arguments", {})),
            response_text=result.get("answer", ""),
        )
        db.add(log)
        db.commit()
    
    return {
        "answer": result.get("answer", "No answer generated"),
        "structured_data": result.get("structured_data"),
        "intent": intent_str,
        "error": result.get("error"),
    }


# Default date range for formatter
default_from = date.today().replace(month=1, day=1)
default_to = date.today()