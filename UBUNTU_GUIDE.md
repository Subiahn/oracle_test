# Ubuntu에서 Oracle TNS 로그인 및 쿼리 테스트

이 가이드는 `tools/oracle_tns_query_check.py` 한 파일로 다음 항목을 검증합니다.

1. SQL*Plus 실행 가능 여부
2. `tnsnames.ora`의 TNS 별칭을 통한 Oracle 로그인
3. IP 기반 Hostname 쿼리 실행 및 결과 반환

## 1. Oracle Instant Client 준비

Oracle에서 Ubuntu 서버 CPU에 맞는 Linux x86-64 Instant Client를 내려받습니다.

- Instant Client Basic 또는 Basic Light
- Instant Client SQL*Plus

두 패키지는 같은 디렉터리에 압축 해제해야 합니다. 배포판에 따라 `libaio1` 또는 `libaio1t64`가 필요할 수 있으므로, 설치 가능한 패키지명을 먼저 확인합니다.

```bash
apt-cache search '^libaio'
sudo apt-get update
sudo apt-get install -y libaio1
```

Ubuntu 릴리스에서 `libaio1`이 없고 `libaio1t64`만 제공되면 다음을 사용합니다.

```bash
sudo apt-get install -y libaio1t64
```

예시 설치 위치:

```text
/opt/oracle/instantclient_19_23/
  sqlplus
  libclntsh.so
  libsqlplus.so
  ...
```

공유 라이브러리 경로를 현재 셸에 설정합니다.

```bash
export LD_LIBRARY_PATH=/opt/oracle/instantclient_19_23:${LD_LIBRARY_PATH:-}
```

## 2. Python 패키지 설치

```bash
cd oracle_sqlplus_test_v0.90
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Oracle Python 드라이버는 필요하지 않습니다. Python은 SQL*Plus 프로세스만 호출합니다.

## 3. 설정 파일 생성

```bash
cp config/oracle_test.example.yaml config/oracle_test.yaml
cp config/oracle.password.example config/oracle.password
cp config/oracle_network/tnsnames.example.ora config/oracle_network/tnsnames.ora
chmod 600 config/oracle.password
```

`config/oracle_test.yaml`의 주요 값을 수정합니다.

```yaml
oracle:
  sqlplus_exe: "/opt/oracle/instantclient_19_23/sqlplus"
  username: "NETSCOUT_TEST"
  connect_identifier: "NETSCOUT_ORACLE"
  tns_admin: "./oracle_network"
  password_file: "./oracle.password"
  timeout_seconds: 120
  nls_lang: "KOREAN_KOREA.AL32UTF8"

query:
  sql_file: "../query/hostname_lookup.sql"
```

실제 쿼리는 `query/hostname_lookup.sql`에 작성합니다.

```sql
SELECT 'QUERY_EXECUTED' FROM DUAL
```

`tnsnames.ora`의 `HOST`는 Oracle DB 서버 IP입니다. 테스트할 SQL과 조건값은 SQL 파일에 직접 작성하며 별도 IP 옵션은 사용하지 않습니다.

`config/oracle.password`에는 실제 비밀번호만 한 줄로 기록합니다.

`config/oracle_network/tnsnames.ora`에는 실제 서버 정보를 기록합니다.

```text
NETSCOUT_ORACLE =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = 192.0.2.10)(PORT = 1521))
    (CONNECT_DATA =
      (SERVER = DEDICATED)
      (SERVICE_NAME = ORCL)
    )
  )
```

DB가 `SERVICE_NAME` 대신 `SID`를 제공했다면 `(SERVICE_NAME = ORCL)`을 `(SID = ORCL)`로 변경합니다.

## 4. 통합 테스트 실행

```bash
python tools/oracle_tns_query_check.py \
  --config config/oracle_test.yaml
```

정상 결과 예시:

```text
step=SQLPLUS status=OK version=SQL*Plus: Release 19...
step=TNS_LOGIN status=OK alias=NETSCOUT_ORACLE
step=QUERY status=OK result=QUERY_EXECUTED
overall=PASS
```

쿼리는 정상이나 데이터가 없는 경우:

```text
step=QUERY status=NO_DATA result=
overall=PASS
```

`NO_DATA`는 SQL 오류가 아니라 작성한 쿼리가 결과 행을 반환하지 않았다는 뜻입니다.

## 5. 오류 구분

- `SQL*Plus not found`: `sqlplus_exe` 경로 오류
- `error while loading shared libraries`: `LD_LIBRARY_PATH` 또는 Basic 패키지 문제
- `ORA-12154`: TNS 별칭 또는 `TNS_ADMIN/tnsnames.ora` 문제
- `ORA-12541`: Listener 주소·포트 또는 방화벽 문제
- `ORA-01017`: 사용자명 또는 비밀번호 문제
- `ORA-00942`: 테이블명, 스키마 또는 SELECT 권한 문제
- `ORA-00904`: 컬럼명 문제

실제 비밀번호, 실제 `tnsnames.ora`, 실행 결과는 Git에 올리지 않습니다.
