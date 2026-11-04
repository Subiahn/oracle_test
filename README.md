# Oracle TNS Hostname 조회 독립 테스트

이 디렉터리는 NETSCOUT 전체 프로젝트를 실행하지 않고 Oracle TNS 접속과 IP별 Hostname 조회만 검증하기 위한 독립 테스트 패키지다.

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
