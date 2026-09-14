import pytest
import workspace_qa_fixture as f
URL='postgresql+asyncpg://u:v@db:5432/ownership_verify_0123456789ab'
def test_owned_mock_test_target_only():assert f.validate({'operation':'prepare'},URL,'mock','test')=='prepare'
@pytest.mark.parametrize('url,provider,env',[(URL,'vertex','test'),(URL,'mock','local'),('postgresql+asyncpg://u:v@other:5432/ownership_verify_0123456789ab','mock','test')])
def test_foreign_target_refused(url,provider,env):
 with pytest.raises(ValueError,match='workspace_fixture_target_refused'):f.validate({'operation':'prepare'},url,provider,env)
def test_closed_operations():
 with pytest.raises(ValueError,match='workspace_fixture_refused'):f.validate({'operation':'prepare','identity':'bad'},URL,'mock','test')
