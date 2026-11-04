# Oracle TNS Hostname 조회 독립 테스트

이 디렉터리는 NETSCOUT 전체 프로젝트를 실행하지 않고 Oracle TNS 접속과 IP별 Hostname 조회만 검증하기 위한 독립 테스트 패키지다.

## 검증된 프로그램 및 패키지 버전

아래 버전은 NETSCOUT 자동화 v0.90에서 분리한 시점과 2026-11-05 독립 테스트에서 확인한 값이다.

| 구분 | 프로그램/패키지 | 검증 버전 | 용도/비고 |
|---|---|---:|---|
| Runtime | Python | 3.12.3 | Oracle 조회 도구 실행 |
| Oracle Client | Oracle Instant Client Basic | 19.33.0.0.0 | GitHub 미포함, Oracle에서 별도 다운로드 |
| Oracle Client | SQL*Plus | 19.33.0.0.0 | TNS 접속 및 SQL 실행 |
| Test DB | Oracle Database XE 11g R2 | 11.2.0.2.0 | Docker Lab에서 기능 검증 |
| Container | Docker Desktop Engine | 29.6.1 | Lab 컨테이너 실행 |
| Container | Docker Compose | 5.3.0 | Lab 구성 실행 |
| Python | PyYAML | 6.0.2 | YAML 설정 및 후보 입력 처리 |
| Python | openpyxl | 3.1.5 | 조회 결과 Excel 생성 |
| Python | requests | 2.32.3 | 공통 Hostname 조회 모듈 의존성 |
| Python | urllib3 | 2.3.0 | requests 의존성 |
| Python | certifi | 2024.12.14 | CA 인증서 번들 |
| Python | charset-normalizer | 3.4.1 | HTTP 문자 인코딩 처리 |
| Python | idna | 3.10 | 국제화 도메인 처리 |

`vendor`에는 위 Python 패키지가 포함되어 있어 별도 `pip install` 없이 실행할 수 있다. 포함된 `.pyd` 파일은 CPython 3.12 Windows x64 기준이므로 다른 Python 또는 운영체제에서는 해당 환경에 맞게 패키지를 다시 설치해야 한다.

Instant Client 19c의 공식 최소 Oracle DB 서버 버전은 11.2.0.4이다. Lab의 11.2.0.2에는 기능상 접속과 조회가 성공했지만 Oracle 공식 지원 조합은 아니다. 운영 DB 버전과 공식 호환성은 별도로 확인한다.

## 포함 파일

```text
oracle_tns_test\
├─ tools\
│  ├─ oracle_query_hostname.py
│  ├─ hostname_lookup_from_candidates.py
│  └─ oracle\instantclient_19_33\
├─ config\
│  ├─ oracle_hostname.yaml
│  ├─ oracle_hostname.password
│  └─ oracle_network\tnsnames.ora
├─ input\ip_port_candidates.yaml
├─ output\
├─ vendor\
└─ README.md
```

## 현재 Lab 설정

- TNS Alias: `NETSCOUT_11G_LAB`
- Host/Port: `localhost:1521`
- Service Name: `XE`
- Oracle 사용자: `NETSCOUT_LAB`
- SQL*Plus: Instant Client 19.33

현재 설정은 `netscout-oracle11g-lab` Docker 컨테이너가 실행 중인 PC에서 사용하는 Lab 설정이다.

## 1. PowerShell에서 디렉터리 이동

```powershell
Set-Location D:\yury\netscout-api-automation\oracle_tns_test
```

모든 명령은 반드시 이 프로젝트 루트에서 실행한다. `sqlplus_command`가 루트 기준 상대 경로이기 때문이다.

## 2. SQL*Plus 실행 확인

GitHub 배포본에는 Oracle Instant Client 바이너리가 포함되지 않는다. Oracle 공식 Windows x64 다운로드 페이지에서 동일한 19c 버전의 `Basic Package`와 `SQL*Plus Package`를 받아 두 ZIP의 `instantclient_19_33` 내용을 다음 디렉터리에 합친다.

```text
tools\oracle\instantclient_19_33\
```

Oracle 다운로드 페이지:

```text
https://www.oracle.com/database/technologies/instant-client/winx64-64-downloads.html
```

```powershell
.\tools\oracle\instantclient_19_33\sqlplus.exe -V
```

정상 예:

```text
SQL*Plus: Release 19.0.0.0.0 - Production
Version 19.33.0.0.0
```

## 3. Docker Lab 상태 확인

```powershell
docker ps --filter "name=netscout-oracle11g-lab"
```

상태가 `healthy`여야 한다. 실제 운영 DB를 사용할 때는 이 단계가 필요 없다.

## 4. TNS 설정 확인

`config\oracle_network\tnsnames.ora`의 Alias와 `config\oracle_hostname.yaml`의 `connect_identifier`가 같아야 한다.

```yaml
connect_identifier: "NETSCOUT_11G_LAB"
```

```ora
NETSCOUT_11G_LAB =
  (DESCRIPTION = ...)
```

## 5. Hostname 조회 실행

```powershell
python .\tools\oracle_query_hostname.py `
  --config .\config\oracle_hostname.yaml `
  --ip-candidates-yaml .\input\ip_port_candidates.yaml `
  --output .\output\oracle_hostname_result.xlsx
```

Lab 정상 결과:

```text
completed ip_count=4 found_count=3 not_found_count=1
```

결과 파일:

```text
output\oracle_hostname_result.xlsx
```

Excel의 `Hostname_Lookup` 시트에서 다음 열을 확인한다.

- `IP`, `Port`, `Hostname`
- `Found`, `Site`, `Source URL`, `Error`
- `Source URL`은 `oracle:NETSCOUT_11G_LAB`

## 6. 운영 Oracle로 변경

### config\oracle_network\tnsnames.ora

DBA가 제공한 TNS 내용을 그대로 입력한다.

```ora
HOSTNAME_DB =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = 실제_DB_IP)(PORT = 1521))
    (CONNECT_DATA =
      (SERVER = DEDICATED)
      (SERVICE_NAME = 실제_서비스명)
    )
  )
```

DBA가 SID를 제공하면 `SERVICE_NAME` 대신 `SID`를 사용한다.

### config\oracle_hostname.yaml

다음 항목을 운영값으로 바꾼다.

```yaml
oracle:
  connect_identifier: "HOSTNAME_DB"
  username: "실제_읽기전용_계정"
  tns_admin: "oracle_network"
  password_file: "oracle_hostname.password"

query:
  sql: >-
    SELECT HOSTNAME
    FROM 실제_HOSTNAME_테이블
    WHERE IP_ADDRESS = '{{IP}}'
      AND ROWNUM = 1
```

`{{IP}}`는 반드시 정확히 한 번 존재해야 한다.

### config\oracle_hostname.password

비밀번호 한 줄만 입력한다. 따옴표나 `KEY=` 형식은 사용하지 않는다.

```text
실제_DB_비밀번호
```

## 7. 실제 NETSCOUT 후보 사용

검증된 `ip_port_candidates.yaml`을 `input`에 복사한다.

```powershell
Copy-Item "원본경로\ip_port_candidates.yaml" ".\input\ip_port_candidates.yaml" -Force
```

입력 예:

```yaml
unique_ip_ports:
  - ip: "192.168.10.10"
    port: 443
    applications:
      - HTTPS
```

## 오류 확인

- `ORA-12154`: TNS Alias 불일치 또는 `tnsnames.ora` 탐색 실패
- `ORA-12514`: SERVICE_NAME이 Listener에 등록되지 않음
- `ORA-12541`: Host/Port에 Listener가 없음
- `ORA-01017`: 사용자 이름 또는 비밀번호 오류
- `ORA-28040`: 클라이언트와 DB 인증 프로토콜 불일치
- `SQL*Plus command not found`: `sqlplus_command` 경로 오류

비밀번호와 실제 `tnsnames.ora`는 Git이나 메일에 그대로 포함하지 않는다.
