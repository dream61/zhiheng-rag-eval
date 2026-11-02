import math
from collections import Counter, defaultdict
from .fingerprints import sample_fingerprint

DIMENSIONS = ("rule_passed", "refusal_passed", "citation_exists", "correctness", "groundedness", "citation_support")

def effective(result):
    reviews = list(result.reviews.all())
    latest = max(reviews, key=lambda r:r.id) if reviews else None
    return latest.passed if latest else result.scores.get("passed")

def outcome(result):
    if result.status == "execution_failed":
        return "execution_failed"
    if result.status != "succeeded":
        return "pending"
    verdict = effective(result)
    if verdict is False:
        return "failed"
    if verdict is True:
        return "passed"
    return "scoring_failed" if result.scoring_status == "failed" else "pending_review"

def metric(values):
    values = [v for v in values if type(v) is bool]
    return {"passed": sum(values), "judged": len(values), "rate": sum(values)/len(values) if values else None}

def report(experiment):
    items = list(experiment.results.prefetch_related("reviews"))
    successful = [r for r in items if r.status == "succeeded"]
    states = Counter(outcome(r) for r in items)
    types = defaultdict(list)
    for r in items:
        types[r.sample["type"]].append(r)
    latency = sorted(r.trace["latency_ms"] for r in successful if "latency_ms" in r.trace)
    def percentile(q):
        return latency[max(0, math.ceil(len(latency)*q)-1)] if latency else None
    retrieval = [r.scores["evidence_recall"] for r in successful if r.scores.get("evidence_recall") is not None]
    return {
        "experiment_id": experiment.id, "name": experiment.name, "status": experiment.status,
        "mode": experiment.config.get("backend"), "config": experiment.config,
        "total":len(items), "completed":sum(r.status in ("succeeded","execution_failed") for r in items),
        "execution_success":len(successful), "execution_failed":states["execution_failed"],
        "execution_success_rate":len(successful)/len(items) if items else None,
        "quality_passed":states["passed"], "quality_failed":states["failed"],
        "pending_review":states["pending_review"], "scoring_failed":sum(r.scoring_status == "failed" for r in successful),
        "dimensions":{d:metric([r.scores.get(d) for r in successful]) for d in DIMENSIONS},
        "evidence_recall":{"samples":len(retrieval), "macro_average":sum(retrieval)/len(retrieval) if retrieval else None},
        "refusal":{"correct_refusal":metric([r.trace.get("refused") for r in successful if r.sample["should_refuse"]]),
                   "false_refusal":metric([r.trace.get("refused") for r in successful if not r.sample["should_refuse"]])},
        "latency_ms":{"mean":sum(latency)/len(latency) if latency else None,"p50":percentile(.5),"p95":percentile(.95)},
        "tokens":{"reported_samples":sum(bool(r.trace.get("usage")) for r in successful),
                  "total":sum(r.trace.get("usage",{}).get("total_tokens",0) or 0 for r in successful)},
        "by_type":{t:{"total":len(rs),"outcomes":dict(Counter(outcome(r) for r in rs)),"dimensions":{d:metric([r.scores.get(d) for r in rs if r.status=="succeeded"]) for d in DIMENSIONS}} for t,rs in types.items()},
        "dimension_basis":"原始自动评分；整体质量判定优先采用最新人工复核，各维度未判定项不计入分母"
    }

def compare(left, right):
    if left.knowledge.product != right.knowledge.product:
        raise ValueError("只能比较同一产品的实验")
    a = {r.sample_id:r for r in left.results.prefetch_related("reviews")}
    b = {r.sample_id:r for r in right.results.prefetch_related("reviews")}
    rows = []
    transitions = {("passed","failed"):"新增失败",("failed","passed"):"已修复",("failed","failed"):"持续失败",("passed","passed"):"持续通过"}
    for sid in sorted(a.keys() | b.keys()):
        x,y = a.get(sid),b.get(sid)
        if x is None: label="新增样本"
        elif y is None: label="删除样本"
        elif sample_fingerprint(x.sample) != sample_fingerprint(y.sample): label="样本已修改"
        else: label=transitions.get((outcome(x),outcome(y)),"异常或待判定")
        def detail(r):
            return {"result_id":r.id,"question":r.sample["question"],"trace":r.trace,"scores":r.scores,"outcome":outcome(r)} if r else None
        rows.append({"sample_id":sid,"change":label,"left":detail(x),"right":detail(y)})
    l,r=report(left),report(right)
    deltas={}
    for d in DIMENSIONS:
        lv,rv=l["dimensions"][d]["rate"],r["dimensions"][d]["rate"]
        deltas[d]=rv-lv if lv is not None and rv is not None else None
    return {"left":l,"right":r,"summary":dict(Counter(row["change"] for row in rows)),"dimension_rate_delta":deltas,"rows":rows,
            "warning":"仅将问题及标注内容一致的样本归类为新增/修复失败；跨样本集合的整体指标变化不能单独证明配置提升"}
