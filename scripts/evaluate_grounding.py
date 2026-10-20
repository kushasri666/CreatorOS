"""Reproducible zero-call evaluation. Optional --predictions reads captured responses."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from self_evaluation import evaluate,markdown,export_prompts,QUESTIONS,FIXTURES,REPORT


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions",type=Path,default=QUESTIONS)
    parser.add_argument("--predictions",type=Path,default=FIXTURES)
    parser.add_argument("--output",type=Path,default=REPORT)
    parser.add_argument("--check-recorded",action="store_true",help="Recompute and fail if saved metrics or code/data fingerprints differ")
    parser.add_argument("--export-prompts",type=Path,help="Write gold-free generation inputs only; no AI calls")
    args=parser.parse_args()
    if args.export_prompts:
        args.export_prompts.parent.mkdir(parents=True,exist_ok=True)
        args.export_prompts.write_text(json.dumps(export_prompts(args.questions),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print("Exported gold-free prompts. No AI calls made.")
        return
    result=evaluate(args.questions,args.predictions)
    if args.check_recorded:
        if not args.output.exists():raise SystemExit("Recorded result is missing; run the evaluator to record it.")
        recorded=json.loads(args.output.read_text(encoding="utf-8"))
        expected={k:v for k,v in result.items() if k!="evaluated_at"}
        saved={k:v for k,v in recorded.items() if k!="evaluated_at"}
        if saved!=expected:raise SystemExit("Recorded evaluation is stale or changed. Review the diff and regenerate the report.")
        print("Recorded metrics, per-case decisions and source/code fingerprints reproduce exactly. No AI calls.")
        return
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    args.output.with_suffix(".md").write_text(markdown(result),encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("dataset_id","case_count","question_count","prediction_origin","ai_calls","validation_spend_usd","before","after")},indent=2))


if __name__=="__main__":main()
