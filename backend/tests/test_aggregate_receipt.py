from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'qa'/'executor'),str(ROOT/'qa'/'contracts')]
from aggregate import _latest_slice,aggregate_reports  # noqa:E402
from registry import load_registry,validate_receipt  # noqa:E402
from runner import ExecutorError  # noqa:E402

REV='1'*40
def result(sid,contract,failed=()):
 return{'scenario_id':sid,'selected':True,'verdict':'FAIL'if failed else'PASS','assertions':[{'id':a['id'],'passed':a['id']not in failed,'evidence':a['evidence']}for a in contract['assertions']],'blocked_reasons':[]}
def reports(registry):
 by=registry.by_id();auth={'revision':REV,'source_unchanged':True,'cleanup':{'browser':0,'mcp':0,'vite':0,'runtime':0},'scenario_result':result('auth_login',by['auth_login'])}
 image={'revision':REV,'source_unchanged':True,'runtime_cleanup':0,'driver_exit_code':0,'prompt_t2i_probe':{'refusal_deltas':{'jobs':1,'outbox':1,'reservations':1}},'prompt_t2i_job_probe':{'state_path':'pending,running,completed'},'browser':{'cleanup':0,'external_page_requests':0,'unexpected_console_errors':0,'checks':{'devtools_network_inspected':True,'devtools_console_inspected':True},'image':{'technical_complete':True,'checks':{'discarded':True,'empty_dom_disabled':True,'original':True,'draft':True,'edited':True,'accepted':True,'completed':True,'accepted_generation_payload_matches':True,'no_observation_failures':True,'empty_accessibility_disabled':True,'empty_prompt_confirmed':True,'empty_submit_found':True},'post_counts':{'enhancement':3,'generation':2},'file':{'mime':'image/png'},'state_path':['pending','completed'],'failures':[],'over_limit_status':201}}}
 def media(kind):return{'revision':REV,'source_unchanged':True,'runtime_cleanup':0,'driver_exit_code':0,'browser':{'cleanup':0,'external_page_requests':0,'unexpected_console_errors':0,kind:{}}}
 video=media('video');video.update(video_probe={'refusal_deltas':{'jobs':1,'outbox':1,'reservations':1}},video_job_probe={'state_path':'pending,running,completed','asset_mime':'video/mp4'});video['browser']['video']={'technical_complete':True,'product':{'empty_disabled':True,'outcome_usable':False},'empty_accessibility_disabled':True,'over_limit_status':201}
 i2v=media('i2v');i2v['i2v_job_probe']={'source_present':True,'state_path':'pending,running,completed','asset_mime':'video/mp4'};i2v['browser']['i2v']={'technical_complete':True,'no_source_accessibility_disabled':False,'source_matches':True,'usable':False}
 pipeline=media('pipeline');pipeline['pipeline_probe']={'same_owner':True,'child_path':'blocked,pending,running,completed','source_linked':True,'parent_state':'completed','child_state':'completed','reservations':1,'held':0};pipeline['browser']['pipeline']={'technical_complete':True,'phases':{'incomplete':True,'reloaded':True},'incomplete_accessibility_disabled':True}
 workspace={'revision':REV,'source_unchanged':True,'runtime_cleanup':0,'driver_exit_code':0,'master_driver_exit_code':0,'browser':{'cleanup':0,'external_page_requests':0,'unexpected_console_errors':0,'workspace':{'technical_complete':True,'phases':{'filtered':True,'page2':True,'page1':True,'usage':True,'usage_reloaded':True},'history_offsets':[0,0,20,0],'history_visible_count':20,'history_rows':20,'detail_identity':True,'delete_calls':0,'retry_error_readable':True,'usage_statuses':[200,200],'usage_values':{'before':{'available':'950','held':'0','charged':'50'},'after':{'available':'950','held':'0','charged':'50'}},'ops_statuses':[403],'master_statuses':[403],'user_admin_polls':0,'user_ops_nav_visible':True}},'master_browser':{'cleanup':0,'external_page_requests':0,'unexpected_console_errors':0,'master':{'technical_complete':True,'phases':{'navigation':True,'overview':True,'users':True,'audit':True,'ops':True},'statuses':{'overview':[200],'users':[200],'audit':[200],'ops':[200]}}},'workspace_inspect':{'usage_available':950000000,'usage_held':0,'usage_charged':50000000,'usage_meter_charged':50000000,'usage_plan':'free','original_failed_clean':True,'original_error_present':True,'retry_distinct':True,'retry_link':True,'retry_state_path':'pending,running,completed','retry_charge_once':True}}
 return auth,image,video,i2v,pipeline,workspace
def test_aggregate_is_contract_valid_and_rejects_known_product_failures():
 registry=load_registry();receipt=aggregate_reports(revision=REV,registry=registry,auth=reports(registry)[0],image=reports(registry)[1],video=reports(registry)[2],i2v=reports(registry)[3],pipeline=reports(registry)[4],workspace=reports(registry)[5]);assert validate_receipt(receipt,registry,expected_revision=REV)=='FAIL';assert len(receipt['scenario_results'])==10;assert sum(len(r['assertions'])for r in receipt['scenario_results'])==68
def test_aggregate_rejects_mixed_revisions():
 registry=load_registry();values=list(reports(registry));values[1]['revision']='2'*40
 with pytest.raises(ExecutorError,match='aggregate_revision_stale'):aggregate_reports(revision=REV,registry=registry,auth=values[0],image=values[1],video=values[2],i2v=values[3],pipeline=values[4],workspace=values[5])
def test_resume_only_reuses_exact_clean_revision(tmp_path):
 root=tmp_path;(root/'output/playwright/devtools-image-old').mkdir(parents=True);(root/'output/playwright/devtools-image-new').mkdir()
 base={'provider':'mock','runtime_cleanup':0,'source_unchanged':True,'driver_exit_code':0}
 (root/'output/playwright/devtools-image-old/receipt.json').write_text(__import__('json').dumps({**base,'revision':'2'*40}))
 (root/'output/playwright/devtools-image-new/receipt.json').write_text(__import__('json').dumps({**base,'revision':REV}))
 assert _latest_slice(root,'image',REV)['revision']==REV
 (root/'output/playwright/devtools-image-new/receipt.json').write_text(__import__('json').dumps({**base,'revision':REV,'runtime_cleanup':1}))
 assert _latest_slice(root,'image',REV)is None
