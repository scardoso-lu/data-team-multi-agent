import json
CHARS_PER_TOKEN = 4
PROTECTED_KEYS = {"business_io_examples","acceptance_criteria","user_stories","tables","relationships","pipelines","execution_mode"}
MAX_FREE_TEXT_CHARS=2000

def estimate_tokens(payload)->int:
    text = payload if isinstance(payload,str) else json.dumps(payload, ensure_ascii=False)
    return len(text)//CHARS_PER_TOKEN

def payload_exceeds_budget(payload, max_tokens:int)->bool:
    return estimate_tokens(payload) > max_tokens

def compress_payload(payload):
    if not isinstance(payload, dict):
        return payload
    result={}
    for k,v in payload.items():
        if k in PROTECTED_KEYS: result[k]=v
        elif isinstance(v,str) and len(v)>MAX_FREE_TEXT_CHARS: result[k]=v[:MAX_FREE_TEXT_CHARS]+" [truncated]"
        elif isinstance(v,dict): result[k]=compress_payload(v)
        else: result[k]=v
    return result
