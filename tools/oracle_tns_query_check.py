"""Oracle SQL*Plus/TNS 로그인과 단건 쿼리를 한 번에 검증한다.

Windows와 Ubuntu에서 동일하게 동작하며 Oracle Python 드라이버는 사용하지 않는다.
필요 패키지는 PyYAML뿐이고, Oracle Instant Client Basic + SQL*Plus는 별도 설치한다.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


RESULT_BEGIN = "__ORACLE_RESULT_BEGIN__"
RESULT_END = "__ORACLE_RESULT_END__"
SAFE_USERNAME = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]*$")


class CheckError(RuntimeError):
    pass


def resolve(config_path: Path, raw: str) -> Path:
    value = Path(raw).expanduser()
    return value if value.is_absolute() else (config_path.parent / value).resolve()


def load_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise CheckError(f"Config file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    oracle = data.get("oracle") or {}
    query = data.get("query") or {}
    username = str(oracle.get("username") or "").strip()
    connect_identifier = str(oracle.get("connect_identifier") or "").strip()
    executable = str(oracle.get("sqlplus_exe") or "sqlplus").strip()
    password_file = str(oracle.get("password_file") or "").strip()
    tns_admin = str(oracle.get("tns_admin") or "").strip()
    sql = str(query.get("sql") or "").strip()
    sql_file_raw = str(query.get("sql_file") or "").strip()
    if sql_file_raw:
        sql_file = resolve(path, sql_file_raw)
        if not sql_file.is_file():
            raise CheckError(f"Query SQL file not found: {sql_file}")
        sql = sql_file.read_text(encoding="utf-8").strip()
    sql = sql.rstrip(";").rstrip()
    if not SAFE_USERNAME.fullmatch(username):
        raise CheckError("oracle.username is missing or invalid")
    if not connect_identifier or any(c in connect_identifier for c in "\r\n"):
        raise CheckError("oracle.connect_identifier is missing or invalid")
    if not sql:
        raise CheckError("Query SQL is empty")
    # A bare command such as 'sqlplus' is resolved by PATH; paths are config-relative.
    sqlplus: str | Path = executable
    if "/" in executable or "\\" in executable:
        sqlplus = resolve(path, executable)
    return {
        "sqlplus": sqlplus,
        "username": username,
        "connect_identifier": connect_identifier,
        "password_file": resolve(path, password_file) if password_file else None,
        "tns_admin": resolve(path, tns_admin) if tns_admin else None,
        "nls_lang": str(oracle.get("nls_lang") or "").strip(),
        "timeout": int(oracle.get("timeout_seconds", 120)),
        "sql": sql,
        "sql_source": str(resolve(path, sql_file_raw)) if sql_file_raw else "inline query.sql",
    }


def read_password(config: dict[str, Any], override: Path | None) -> str:
    path = override or config["password_file"]
    if path is None or not Path(path).is_file():
        raise CheckError("Password file not found")
    password = Path(path).read_text(encoding="utf-8").strip()
    if not password or any(c in password for c in "\r\n"):
        raise CheckError("Password is empty or invalid")
    return password


def process_env(config: dict[str, Any]) -> dict[str, str]:
    env = os.environ.copy()
    if config["tns_admin"]:
        env["TNS_ADMIN"] = str(config["tns_admin"])
    if config["nls_lang"]:
        env["NLS_LANG"] = config["nls_lang"]
    return env


def invoke(config: dict[str, Any], arguments: list[str], script: str | None = None) -> subprocess.CompletedProcess[str]:
    command = [str(config["sqlplus"]), *arguments]
    try:
        return subprocess.run(
            command,
            input=script,
            text=True,
            capture_output=True,
            timeout=config["timeout"],
            env=process_env(config),
            check=False,
        )
    except FileNotFoundError as exc:
        raise CheckError(f"SQL*Plus not found: {config['sqlplus']}") from exc
    except subprocess.TimeoutExpired as exc:
        raise CheckError(f"SQL*Plus timed out after {config['timeout']} seconds") from exc


def quote_password(password: str) -> str:
    return '"' + password.replace('"', '""') + '"'


def build_script(config: dict[str, Any], password: str) -> str:
    sql = config["sql"]
    return "\n".join(
        [
            "SET HEADING OFF",
            "SET FEEDBACK OFF",
            "SET PAGESIZE 0",
            "SET VERIFY OFF",
            "SET ECHO OFF",
            "SET TRIMSPOOL ON",
            "WHENEVER OSERROR EXIT FAILURE",
            "WHENEVER SQLERROR EXIT SQL.SQLCODE",
            f"CONNECT {config['username']}/{quote_password(password)}@{config['connect_identifier']}",
            "PROMPT __TNS_LOGIN_OK__",
            f"PROMPT {RESULT_BEGIN}",
            sql + ";",
            f"PROMPT {RESULT_END}",
            "EXIT",
            "",
        ]
    )


def extract_result(stdout: str) -> tuple[bool, str]:
    login_ok = "__TNS_LOGIN_OK__" in stdout
    collecting = False
    values: list[str] = []
    for raw in stdout.splitlines():
        line = raw.strip()
        if line == RESULT_BEGIN:
            collecting = True
        elif line == RESULT_END:
            collecting = False
            break
        elif collecting and line:
            values.append(line)
    return login_ok, values[0] if values else ""


def check(config_path: Path, password_file: Path | None) -> int:
    config = load_config(config_path.resolve())
    version = invoke(config, ["-v"])
    if version.returncode != 0:
        raise CheckError(f"SQL*Plus version check failed: {(version.stderr or version.stdout).strip()}")
    version_text = (version.stdout or version.stderr).strip().replace("\n", " ")
    print(f"step=SQLPLUS status=OK version={version_text}")

    password = read_password(config, password_file)
    completed = invoke(config, ["-s", "/nolog"], build_script(config, password))
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-1200:]
        raise CheckError(f"TNS login or query failed (exit={completed.returncode}): {detail}")
    login_ok, value = extract_result(completed.stdout)
    if not login_ok:
        raise CheckError("SQL*Plus returned no TNS login success marker")
    print(f"step=TNS_LOGIN status=OK alias={config['connect_identifier']}")
    if value:
        print(f"step=QUERY status=OK result={value}")
    else:
        print("step=QUERY status=NO_DATA result=")
    print(f"query_source={config['sql_source']}")
    print("overall=PASS")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check SQL*Plus, Oracle TNS login, and hostname query")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--password-file", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return check(args.config, args.password_file)
    except (CheckError, OSError, ValueError, yaml.YAMLError) as exc:
        print(f"overall=FAIL error={exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
