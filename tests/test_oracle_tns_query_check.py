from pathlib import Path
import importlib.util


MODULE = Path(__file__).parents[1] / "tools" / "oracle_tns_query_check.py"
SPEC = importlib.util.spec_from_file_location("oracle_tns_query_check", MODULE)
check = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(check)


def test_build_script_contains_tns_login_and_query() -> None:
    config = {
        "username": "TEST_USER",
        "connect_identifier": "TESTDB",
        "sql": "SELECT HOSTNAME FROM HOSTS WHERE IP = '{{IP}}'",
    }
    script = check.build_script(config, "secret", "192.168.0.10")
    assert 'CONNECT TEST_USER/"secret"@TESTDB' in script
    assert "WHERE IP = '192.168.0.10'" in script
    assert "__TNS_LOGIN_OK__" in script


def test_extract_result_found() -> None:
    output = "\n".join(["__TNS_LOGIN_OK__", check.RESULT_BEGIN, "host-a", check.RESULT_END])
    assert check.extract_result(output) == (True, "host-a")


def test_extract_result_no_data() -> None:
    output = "\n".join(["__TNS_LOGIN_OK__", check.RESULT_BEGIN, check.RESULT_END])
    assert check.extract_result(output) == (True, "")
