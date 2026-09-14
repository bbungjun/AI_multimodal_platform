#!/usr/bin/env python3
"""Execute every Agent QA scenario and emit one aggregate Receipt."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"qa"/"executor"));sys.path.insert(0,str(ROOT/"qa"/"contracts"))
from aggregate import run_all  # noqa:E402
from runner import ExecutorError  # noqa:E402

def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument("--base",required=True);p.add_argument("--head",required=True);p.add_argument("--resume",action="store_true");a=p.parse_args(argv)
 try:r=run_all(a.base,a.head,ROOT,resume=a.resume)
 except(ExecutorError,OSError,ValueError)as e:print(json.dumps({"complete":False,"error":str(e)},separators=(",",":")));return 2
 print(json.dumps({"complete":True,"verdict":r.receipt["verdict"],"merge_decision":r.merge_decision,
  "scenarios":len(r.receipt["scenario_results"]),"assertions":sum(len(x["assertions"])for x in r.receipt["scenario_results"]),
  "receipt":r.report_path,"seconds":r.seconds},separators=(",",":")))
 return 0 if r.receipt["verdict"]=="PASS"else 1
if __name__=="__main__":raise SystemExit(main())
