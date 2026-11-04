"""Oracle SQL*Plus로 NETSCOUT IP 후보의 Hostname을 조회한다.

Oracle 드라이버를 설치하지 않고 외부 ``sqlplus`` 프로세스를 사용한다.
입력과 출력 형식은 ``hostname_lookup_from_candidates.py``와 동일하다.
"""

from __future__ import annotations

import argparse
import getpass
import ipaddress
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError:
    ROOT = Path(__file__).resolve().parents[1]
    VENDOR = ROOT / "vendor"
    if VENDOR.exists():
        sys.path.insert(0, str(VENDOR))
    import yaml

from hostname_lookup_from_candidates import (
    HostnameLookupError,
    load_ip_applications_from_xlsx,
    load_ip_applications_from_yaml,
    load_yaml,
    write_results_xlsx,
)


BEGIN_PREFIX = "__NETSCOUT_BEGIN__"
END_PREFIX = "__NETSCOUT_END__"
SAFE_USERNAME = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]*$")


class OracleHostnameError(RuntimeError):
    """Oracle Hostname 조회 구성 또는 SQL*Plus 실행 오류."""


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise OracleHostnameError(f"Config file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise OracleHostnameError("Oracle config root must be a mapping.")

    oracle = data.get("oracle") or {}
    query = data.get("query") or {}
    output = data.get("output") or {}
    username = str(oracle.get("username") or "").strip()
    connect_identifier = str(oracle.get("connect_identifier") or "").strip()
    command = oracle.get("sqlplus_command", ["sqlplus", "-s", "/nolog"])
    sql = str(query.get("sql") or "").strip()

    if not SAFE_USERNAME.fullmatch(username):
        raise OracleHostnameError("oracle.username is missing or invalid.")
    if not connect_identifier or "\n" in connect_identifier or "\r" in connect_identifier:
        raise OracleHostnameError("oracle.connect_identifier is missing or invalid.")
    if not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
        raise OracleHostnameError("oracle.sqlplus_command must be a non-empty string list.")
    if sql.count("{{IP}}") != 1:
        raise OracleHostnameError("query.sql must contain exactly one {{IP}} placeholder.")
    if sql.rstrip().endswith(";"):
        sql = sql.rstrip()[:-1].rstrip()

    tns_admin = str(oracle.get("tns_admin") or "").strip()
    if tns_admin:
        tns_path = Path(tns_admin)
        if not tns_path.is_absolute():
            tns_admin = str((path.parent / tns_path).resolve())

    return {
        "username": username,
        "connect_identifier": connect_identifier,
        "sqlplus_command": command,
        "password_file": str(oracle.get("password_file") or "").strip(),
        "tns_admin": tns_admin,
        "nls_lang": str(oracle.get("nls_lang") or "").strip(),
        "timeout": int(oracle.get("timeout", 120)),
        "sql": sql,
        "source_name": str(output.get("source_name") or "Oracle SQL*Plus"),
    }


def read_password(config: dict[str, Any], config_path: Path, password_file: Path | None) -> str:
    selected = password_file
    if selected is None and config["password_file"]:
        selected = Path(config["password_file"])
        if not selected.is_absolute():
            selected = config_path.parent / selected
    if selected is not None:
        if not selected.exists():
            raise OracleHostnameError(f"Password file not found: {selected}")
        password = selected.read_text(encoding="utf-8").strip()
    else:
        password = getpass.getpass("Oracle password: ")
    if not password or "\n" in password or "\r" in password:
        raise OracleHostnameError("Oracle password is empty or invalid.")
    return password


def quote_password(password: str) -> str:
    return '"' + password.replace('"', '""') + '"'


def build_sql_script(ip_values: list[str], config: dict[str, Any], password: str) -> str:
    lines = [
        "SET HEADING OFF",
        "SET FEEDBACK OFF",
        "SET PAGESIZE 0",
        "SET LINESIZE 32767",
        "SET TRIMSPOOL ON",
        "SET VERIFY OFF",
        "SET ECHO OFF",
        "WHENEVER OSERROR EXIT FAILURE",
        "WHENEVER SQLERROR EXIT SQL.SQLCODE",
        f"CONNECT {config['username']}/{quote_password(password)}@{config['connect_identifier']}",
    ]
    for ip_value in ip_values:
        normalized = str(ipaddress.ip_address(ip_value))
        sql = config["sql"].replace("{{IP}}", normalized)
        lines.extend((f"PROMPT {BEGIN_PREFIX}{normalized}", sql + ";", f"PROMPT {END_PREFIX}{normalized}"))
    lines.extend(("EXIT", ""))
    return "\n".join(lines)


def parse_sqlplus_output(stdout: str, ip_values: list[str]) -> dict[str, str]:
    expected = {str(ipaddress.ip_address(ip_value)) for ip_value in ip_values}
    results = {ip_value: "" for ip_value in expected}
    current = ""
    values: list[str] = []

    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if line.startswith(BEGIN_PREFIX):
            current = line[len(BEGIN_PREFIX) :].strip()
            values = []
            continue
        if line.startswith(END_PREFIX):
            finished = line[len(END_PREFIX) :].strip()
            if current and finished == current and current in results:
                results[current] = values[0] if values else ""
            current = ""
            values = []
            continue
        if current and line:
            values.append(line)
    return results


def run_sqlplus(ip_values: list[str], config: dict[str, Any], password: str) -> dict[str, str]:
    script = build_sql_script(ip_values, config, password)
    process_env = os.environ.copy()
    if config.get("tns_admin"):
        process_env["TNS_ADMIN"] = config["tns_admin"]
    if config.get("nls_lang"):
        process_env["NLS_LANG"] = config["nls_lang"]
    try:
        completed = subprocess.run(
            config["sqlplus_command"],
            input=script,
            text=True,
            capture_output=True,
            timeout=config["timeout"],
            check=False,
            env=process_env,
        )
    except FileNotFoundError as exc:
        raise OracleHostnameError(f"SQL*Plus command not found: {config['sqlplus_command'][0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise OracleHostnameError(f"SQL*Plus timed out after {config['timeout']} seconds.") from exc

    if completed.returncode != 0:
        error = (completed.stderr or completed.stdout).strip()
        raise OracleHostnameError(f"SQL*Plus failed with exit code {completed.returncode}: {error[-1000:]}")
    return parse_sqlplus_output(completed.stdout, ip_values)


def load_yaml_candidate_rows(path: Path) -> list[dict[str, Any]]:
    """IP/Port 후보 행을 보존해 Registration Excel까지 전달한다."""
    data = load_yaml(path)
    candidates = data.get("unique_ip_ports", data.get("unique_ips", []))
    if not isinstance(candidates, list):
        raise OracleHostnameError("ip candidates YAML field 'unique_ip_ports' must be a list.")
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in candidates:
        if isinstance(item, dict):
            raw_ip = str(item.get("ip") or "").strip()
            port = str(item.get("port") or "").strip()
            applications = item.get("applications", [])
            if not isinstance(applications, list):
                applications = [applications] if applications else []
            app_names = [str(value).strip() for value in applications if str(value or "").strip()]
        else:
            raw_ip, port, app_names = str(item or "").strip(), "", []
        if not raw_ip:
            continue
        normalized = str(ipaddress.ip_address(raw_ip))
        key = (normalized, port)
        if key in seen:
            continue
        seen.add(key)
        rows.append({"IP": normalized, "Port": port, "Applications": app_names})
    return rows


def lookup_hostnames(
    config_path: Path,
    output_path: Path,
    ip_candidates_yaml: Path | None = None,
    ip_candidates_xlsx: Path | None = None,
    password_file: Path | None = None,
) -> tuple[Path, int, int]:
    if bool(ip_candidates_yaml) == bool(ip_candidates_xlsx):
        raise OracleHostnameError("Provide exactly one of --ip-candidates-yaml or --ip-candidates-xlsx.")
    config = load_config(config_path)
    password = read_password(config, config_path, password_file)
    try:
        if ip_candidates_yaml:
            candidate_rows = load_yaml_candidate_rows(ip_candidates_yaml)
            ip_applications = load_ip_applications_from_yaml(ip_candidates_yaml)
        else:
            ip_applications = load_ip_applications_from_xlsx(ip_candidates_xlsx)  # type: ignore[arg-type]
            candidate_rows = [
                {"IP": ip_value, "Port": "", "Applications": applications}
                for ip_value, applications in ip_applications.items()
            ]
    except HostnameLookupError as exc:
        raise OracleHostnameError(str(exc)) from exc

    hostnames = run_sqlplus(list(ip_applications), config, password)
    source = f"oracle:{config['connect_identifier']}"
    rows = []
    for candidate in candidate_rows:
        normalized = str(ipaddress.ip_address(candidate["IP"]))
        applications = candidate["Applications"]
        hostname = hostnames.get(normalized, "")
        rows.append(
            {
                "IP": normalized,
                "Port": candidate["Port"],
                "Hostname": hostname,
                "Applications": ", ".join(applications),
                "Found": bool(hostname),
                "Site": config["source_name"] if hostname else "",
                "Source URL": source if hostname else "",
                "Error": "" if hostname else "No matching hostname",
            }
        )
    path = write_results_xlsx(rows, output_path)
    found_count = sum(1 for row in rows if row["Found"])
    return path, len(rows), found_count


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query hostnames from Oracle through SQL*Plus.")
    parser.add_argument("--config", required=True, type=Path)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--ip-candidates-yaml", type=Path)
    inputs.add_argument("--ip-candidates-xlsx", type=Path)
    parser.add_argument("--password-file", type=Path, help="Optional password-only file; otherwise prompt securely.")
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        path, ip_count, found_count = lookup_hostnames(
            args.config,
            args.output,
            args.ip_candidates_yaml,
            args.ip_candidates_xlsx,
            args.password_file,
        )
    except (OracleHostnameError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        f"completed ip_count={ip_count} found_count={found_count} "
        f"not_found_count={ip_count - found_count} output={path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
