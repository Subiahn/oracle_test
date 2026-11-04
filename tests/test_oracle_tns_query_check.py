from pathlib import Path
import importlib.util

import pytest


MODULE = Path(__file__).parents[1] / "tools" / "oracle_tns_query_check.py"
SPEC = importlib.util.spec_from_file_location("oracle_tns_query_check", MODULE)
check = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(check)


def test_build_script_contains_tns_login_and_query() -> None:
    config = {
        "username": "TEST_USER",
        "connect_identifier": "TESTDB",
        "sql": "SELECT 'QUERY_EXECUTED' FROM DUAL",
    }
    script = check.build_script(config, "secret")
    assert 'CONNECT TEST_USER/"secret"@TESTDB' in script
    assert "SELECT 'QUERY_EXECUTED' FROM DUAL" in script
    assert "__TNS_LOGIN_OK__" in script


def test_extract_result_found() -> None:
    output = "\n".join(["__TNS_LOGIN_OK__", check.RESULT_BEGIN, "host-a", check.RESULT_END])
    assert check.extract_result(output) == (True, "host-a")


def test_extract_result_no_data() -> None:
    output = "\n".join(["__TNS_LOGIN_OK__", check.RESULT_BEGIN, check.RESULT_END])
    assert check.extract_result(output) == (True, "")


def test_load_config_reads_external_sql_file(tmp_path: Path) -> None:
    query_dir = tmp_path / "query"
    query_dir.mkdir()
    (query_dir / "lookup.sql").write_text(
        "SELECT 'QUERY_EXECUTED' FROM DUAL;\n",
        encoding="utf-8",
    )
    config = tmp_path / "oracle.yaml"
    config.write_text(
        "oracle:\n"
        "  sqlplus_exe: sqlplus\n"
        "  username: TEST_USER\n"
        "  connect_identifier: TESTDB\n"
        "query:\n"
        "  sql_file: query/lookup.sql\n",
        encoding="utf-8",
    )
    loaded = check.load_config(config)
    assert loaded["sql"] == "SELECT 'QUERY_EXECUTED' FROM DUAL"
    assert loaded["sql_source"].endswith("lookup.sql")


def test_load_config_rejects_empty_sql(tmp_path: Path) -> None:
    sql_file = tmp_path / "query.sql"
    sql_file.write_text("\n", encoding="utf-8")
    config = tmp_path / "oracle.yaml"
    config.write_text(
        "oracle:\n"
        "  username: TEST_USER\n"
        "  connect_identifier: TESTDB\n"
        "query:\n"
        "  sql_file: query.sql\n",
        encoding="utf-8",
    )
    with pytest.raises(check.CheckError, match="empty"):
        check.load_config(config)
