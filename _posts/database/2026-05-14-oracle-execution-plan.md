---
title: "Oracle 실행계획 읽는 법 - EXPLAIN PLAN과 옵티마이저"
date: 2026-05-14 13:00:00 +0900
categories: [Database]
tags: [database, oracle, sql, execution-plan, optimizer]
---

> 샘플 OLTP 테이블(예시 `SAMPLE_TXN`)의 쿼리로 실행계획을 떠보고 읽는다. 모든 테이블/인덱스/식별자는 학습용 예시 값이다. 인덱스 물리 구조·PGA·OLTP 는 별도 글 「Oracle 인덱스 구조 원리」 참고.

---

## 0. 실행계획이 필요한 이유

SQL 은 **선언적 언어**다. 원하는 결과를 선언하고, 데이터를 가져오는 구체적인 경로는 DB의 **옵티마이저(Optimizer)** 가 정한다.

인덱스를 만들 때 예상한 접근 경로와 옵티마이저의 실제 판단은 다를 수 있다. 그 차이를 눈으로 확인하는 도구가 **실행계획(Execution Plan)** 이다.

> ⚠️ 용어가 처음이면 먼저 **마지막 11장 「초심자 키워드 사전」** 부터 읽고 와도 좋다. (parse / cursor / bind / cardinality 등)

---

## 1. INDEX SCAN vs TABLE FULL SCAN — 가장 먼저 보는 것

`FULL SCAN` 이라는 단어 때문에 둘 다 비효율적으로 보이지만 **읽는 대상이 다르다.**

| | TABLE FULL SCAN | INDEX (FULL/FAST FULL) SCAN |
|:---|:---|:---|
| 읽는 대상 | 테이블 데이터 블록 전부 | 인덱스 leaf 블록 전부 |
| 블록당 row 수 | 한 행에 **모든 컬럼** → row 큼 → 블록당 적게 | 인덱스 **키 컬럼만** → row 작음 → 블록당 많이 |
| 정렬 | 없음 (heap 순서) | 인덱스 키 순서로 정렬되어 나옴 |
| I/O 방식 | multi-block read | single-block 기본 (FAST FULL 은 multi-block) |

```sql
SELECT COUNT(*) FROM SAMPLE_TXN WHERE TENANT_ID = ?;
```

- `IDX_SAMPLE_TENANT(TENANT_ID)` 있으면 → **INDEX RANGE SCAN** (해당 영역 leaf 만 훑음)
- 인덱스 없으면 → **TABLE FULL SCAN** (대상 테이블 row를 전부 읽어 비교)

테이블 row 가 200 byte, 인덱스 entry 가 20 byte 면 **읽을 블록 수가 약 10배 차이**. → 필요한 컬럼이 인덱스에 다 있으면(index-only) 빠른 이유.

> **INDEX FAST FULL SCAN**: 인덱스 정렬 순서를 사용하지 않고 multi-block read 로 인덱스 전체를 읽는다. `COUNT(*)`처럼 순서가 필요 없는 경우 후보가 될 수 있다.

---

## 2. 실행계획은 어디에 저장되나 — 두 가지를 구분하라

| | 어디 저장 | 영구? | 조회 |
|---|---|---|---|
| **EXPLAIN PLAN 결과** (예측) | `PLAN_TABLE` 이라는 **실제 테이블** | 직접 정리하기 전까지 남을 수 있음 | `DBMS_XPLAN.DISPLAY()` |
| **실제 실행된 plan** | **SGA → Shared Pool → Library Cache (메모리)** | 캐시에서 밀리면 사라짐 | `V$SQL_PLAN` 동적 뷰 |

```sql
EXPLAIN PLAN FOR
SELECT COUNT(*) FROM SAMPLE_TXN WHERE TENANT_ID = 'TENANT_A';
-- 위 한 줄이 PLAN_TABLE 에 id 0,1,2... row 로 INSERT 됨

SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY());
-- PLAN_TABLE 을 읽어 표로 포맷
```

→ EXPLAIN 순간 `PLAN_TABLE` 에 row 로 저장된다. `DBMS_XPLAN.DISPLAY()`는 보통 최근 또는 지정한 statement_id의 계획을 읽어 보여주며, 필요하면 `PLAN_TABLE` 데이터를 직접 정리한다.

> **Library Cache 는 SGA(공유 메모리) 안에 있다.** 동일 SQL 텍스트, 스키마/권한/세션 환경 등 재사용 조건이 맞으면 여러 세션이 캐시된 커서를 재사용할 수 있다. (SGA/PGA 구분은 「Oracle 인덱스 구조 원리」 6장 참고 — 정렬용 PGA 와 헷갈리지 말 것.)

---

## 3. 옵티마이저는 무엇을 보고 plan 을 정하나 — 통계 기반(CBO)

쿼리를 많이 실행한다는 사실만으로 옵티마이저가 학습해서 더 좋은 plan 으로 바꾸는 것은 아니다.

Oracle 옵티마이저는 **CBO(Cost-Based Optimizer)**. 데이터를 매번 직접 보는 게 아니라 **데이터의 요약 통계** 로 비용을 계산한다.

```text
DBMS_STATS.GATHER_TABLE_STATS   (자동 통계 수집 or 수동)
   ↓
통계 저장: 테이블 row 수, 블록 수, 컬럼별 distinct 수,
          데이터 분포(히스토그램), 인덱스 높이 등
   ↓
SQL 첫 실행 = hard parse
   → 옵티마이저가 통계로 비용 계산 → plan 결정
   → Library Cache 에 cursor 캐싱
   ↓
같은 SQL 재실행 = soft parse (캐시된 plan 재사용, 재계산 X)
```

**plan 이 다시 계산되는 트리거 (쿼리 빈도가 아님):**

| 트리거 | 설명 |
|---|---|
| 통계 갱신 | `DBMS_STATS` 로 통계 새로 수집 → 다음 parse 때 재계산 |
| 캐시 축출 | Library Cache 메모리 부족으로 cursor 가 밀려남 |
| DDL 변경 | 인덱스 추가/삭제, 컬럼 변경 → 관련 cursor 무효화 |
| bind 값 차이 | bind peeking / adaptive cursor sharing 등으로 값 분포에 따라 다른 plan 후보 가능 |

> 운영에서 멀쩡하던 쿼리가 갑자기 느려졌다면 통계 노후화, plan 변경, 바인드 값 분포 변화, DDL 변경 등을 함께 의심한다. `DBMS_STATS.GATHER_TABLE_STATS` 는 현재 데이터 분포를 반영하도록 통계를 갱신하는 대표적인 방법이다.

---

## 4. Operation 종류 사전

### 인덱스 접근

| Operation | 의미 | 언제 |
|---|---|---|
| `INDEX UNIQUE SCAN` | 딱 **1건** 보장하고 찾음 | PK/UK 등치. 가장 빠름 |
| `INDEX RANGE SCAN` | 정렬 인덱스에서 **여러 건/범위** | `=`(중복가능), `BETWEEN`, `>`, `LIKE 'A%'` |
| `INDEX FULL SCAN` | 인덱스 전체를 **순서대로**(single block) | ORDER BY 를 인덱스로 대체 |
| `INDEX FAST FULL SCAN` | 인덱스 전체를 **순서무시 multi-block** | `COUNT(*)` 등 순서 불필요. 전체 카운트 후보 |
| `INDEX SKIP SCAN` | 복합 인덱스 **선두 컬럼 건너뛰고** 탐색 | 선두 조건 빠졌을 때. 선두 distinct 적을 때만 이득 |

### 테이블 접근

| Operation | 의미 |
|---|---|
| `TABLE ACCESS FULL` | 테이블 전체 스캔. 결과 비율이 높거나 분석/배치 쿼리라면 정상 선택일 수 있음 |
| `TABLE ACCESS BY INDEX ROWID` | 인덱스로 ROWID 찾은 뒤 테이블 본체 접근 |

### 조인

| Operation | 의미 |
|---|---|
| `NESTED LOOPS` | 바깥 row 하나당 안쪽 반복 탐색. 한쪽이 작을 때 유리 |
| `HASH JOIN` | 한쪽으로 해시테이블 만들고 매칭. 대용량 동등조인 유리 |
| `MERGE JOIN` | 양쪽 정렬 후 머지. 비등치 조인 등 |

### 집계/기타

| Operation | 의미 |
|---|---|
| `SORT AGGREGATE` | `COUNT/SUM/MAX` 전체 집계 |
| `SORT ORDER BY` | 정렬 |
| `HASH GROUP BY` | `GROUP BY` 해시 방식 |
| `FILTER` | 조건 거르기 / 서브쿼리 처리 |

---

## 5. 실전: 실제 실행계획 읽기

```sql
EXPLAIN PLAN FOR
SELECT COUNT(*) FROM SAMPLE_TXN WHERE TENANT_ID = 'TENANT_A';

SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY());
```

출력:

```text
Plan hash value: 1234567890

-----------------------------------------------------------------------------------
| Id  | Operation         | Name                | Rows | Bytes | Cost (%CPU)| Time     |
-----------------------------------------------------------------------------------
|   0 | SELECT STATEMENT  |                     |    1 |    16 |     1   (0)| 00:00:01 |
|   1 |  SORT AGGREGATE   |                     |    1 |    16 |            |          |
|*  2 |   INDEX RANGE SCAN| IDX_SAMPLE_TENANT   |    5 |    80 |     1   (0)| 00:00:01 |
-----------------------------------------------------------------------------------

Predicate Information (identified by operation id):
---------------------------------------------------
   2 - access("TENANT_ID"='TENANT_A')
```

### 컬럼 의미

| 컬럼 | 의미 | 주의 |
|---|---|---|
| **Id** | operation 식별자. `*` 는 Predicate 정보 있음 | — |
| **Operation/Name** | 무슨 연산을, 어떤 객체에 | **의도한 인덱스 이름이 보이는지 1차 체크** |
| **Rows** | 그 단계가 반환할 거라 옵티마이저가 **추정한** row 수 | 실측 아님. 통계 기반 예측치 |
| **Bytes** | 그 row 들의 예상 총 크기 (Rows × 평균 row 길이) | 정렬/조인 메모리·spill 비용 계산용 |
| **Cost** | 옵티마이저가 매긴 비용 점수 (낮을수록 좋음) | 절대값보다 **대안과 비교용** |
| **Time** | 예상 소요시간 (추정치) | 실측 아님 |

**Bytes 컬럼의 의미**: 데이터 크기는 정렬(SORT), 해시조인, temp spill 비용에 영향을 준다. 작은 컬럼만 읽으면 예상 bytes가 작아져 `SELECT *`보다 필요한 컬럼만 조회하는 쿼리가 유리할 수 있다.

### Predicate Information — `access` vs `filter` (가장 중요)

```text
2 - access("TENANT_ID"='TENANT_A')
```

operation **id 2** 에서 어떤 조건을 어떻게 적용했는지를 보여준다.

| | 의미 | 효율 |
|---|---|---|
| **access** | 인덱스 **탐색 자체** 에 조건 사용 → 처음부터 해당 범위만 읽음 | 대체로 유리 |
| **filter** | 읽은 row에 조건을 추가 적용 | 읽은 양과 선택도 확인 필요 |

위는 `access`로 잡혔으므로 해당 값 영역을 탐색 조건으로 사용한다. `filter`로 보인다고 항상 나쁜 것은 아니지만, 읽은 row 수가 크면 비효율 신호가 될 수 있다.

### 읽는 순서

**들여쓰기 깊고 위에 있는 것부터 → 바깥으로** (id 2 → 1 → 0)

| Id | 해석 |
|---|---|
| **2** | `IDX_SAMPLE_TENANT` RANGE SCAN. 조건을 **access** 로 사용 → 약 5건, 80 byte. **TABLE ACCESS 없음** = index-only |
| **1** | 그 5건을 `SORT AGGREGATE` 집계 → `COUNT(*)` 1행 |
| **0** | 최종 SELECT 1행 반환 |

`Plan hash value` = 이 plan 구조의 **지문**. 같은 SQL 재측정 시 값이 바뀌면 옵티마이저가 다른 plan 을 골랐다는 신호다. 통계 변화, 바인드 값 분포, 파라미터, 힌트, DDL, 세션 환경 등을 함께 확인한다.

---

## 6. 좋은 plan / 나쁜 plan 신호

**좋은 신호**

- 인덱스 키워드(`INDEX UNIQUE/RANGE/FAST FULL SCAN`) 보임
- 의도한 인덱스 이름 보임
- 큰 OLTP 단건 조회 쿼리에서 불필요한 `TABLE ACCESS FULL` 없음
- WHERE 가 `access:` 에 잡힘 (`filter:` 아님)

**나쁜 신호**

- 단건/소수건 조회가 목적인데 큰 테이블에 `TABLE ACCESS FULL`
- 인덱스 탔는데 `TABLE ACCESS BY INDEX ROWID` 과다 (필요 컬럼이 인덱스에 없어 row마다 테이블 왕복)
- 조건이 `filter:` 로 빠짐
- 예측 `Rows` 와 실측이 크게 어긋남 (통계 부정확 → 잘못된 조인/접근 선택)

---

## 7. 언제 실행계획을 떠봐야 하나

| 시점 | 이유 |
|---|---|
| 새 쿼리 작성 후 배포 전 | 의도한 인덱스를 타는지 |
| 신규 인덱스 추가 후 | 옵티마이저가 새 인덱스를 채택했는지 |
| 운영에서 특정 쿼리 느려질 때 | 통계 노후화 / 인덱스 무효화 / plan 변경 의심 |
| 새 컬럼·조건 추가 | WHERE 조건이 인덱스에 들어가는지 |

> 개발기는 데이터가 적어 `Rows`/`Cost` 가 작게 나온다. plan 의 *구조*(어떤 인덱스, access/filter)는 참고되지만 절대 수치는 **운영 데이터 규모에서 한 번 더** 확인이 정석.

---

## 8. 실행계획 떠보는 방법 모음

```sql
-- (A) EXPLAIN PLAN : 실제 실행 안 함, 예측만
EXPLAIN PLAN FOR <SQL>;
SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY());

-- (B) 실제 실행 후 예측 vs 실측 비교 (가장 강력)
SELECT /*+ GATHER_PLAN_STATISTICS */ ... ;
SELECT * FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(format => 'ALLSTATS LAST')
);
-- E-Rows(예측) vs A-Rows(실측) 크게 다르면 통계/카디널리티 문제

-- (C) SQL*Plus AUTOTRACE : 결과 + plan + 통계 한 번에
SET AUTOTRACE ON;
<SQL>;
```

---

## 9. 한 장 요약

| 질문 | 답 |
|---|---|
| 풀스캔 vs 인덱스스캔 | 같은 전체 읽기여도 대상이 **테이블 블록 vs 인덱스 leaf** — 후자가 더 작을 수 있음 |
| 실행계획 저장 | EXPLAIN → `PLAN_TABLE`, 실제 실행 cursor → SGA Library Cache(메모리) |
| 옵티마이저 판단 기준 | 쿼리 빈도 ❌ / **통계(CBO)** ✅, parse 시점 결정, 통계·DDL 변경 시 재계산 |
| access vs filter | access=인덱스 탐색에 사용, filter=읽은 row에 추가 조건 적용. 효율은 읽은 양과 선택도로 판단 |
| Rows / Bytes | Rows=추정 반환 건수, Bytes=그 크기(정렬/조인 메모리 비용 계산용) |
| 읽는 순서 | 들여쓰기 깊고 위 → 바깥 |

---

## 10. 더 파볼 키워드

1. **Clustering Factor** — 인덱스 키 순서와 테이블 row 물리 순서 유사도. 나쁘면 RANGE SCAN 후 TABLE ACCESS 비용 폭증.
2. **복합 인덱스 컬럼 순서** — `(A,B,C)` 는 선두(A) 조건 없으면 잘 안 탐(또는 비싼 SKIP SCAN).
3. **Cardinality 추정 오류** — `DISPLAY_CURSOR('ALLSTATS LAST')` 의 E-Rows vs A-Rows. 느린 쿼리의 가장 흔한 근본 원인.
4. **Bind Peeking & Adaptive Cursor Sharing** — `?` 자리 값의 분포에 따라 plan 후보가 달라질 수 있는 지점.
5. **`/*+ INDEX(t idx) */` 힌트** — 옵티마이저 결정 강제. 최후의 수단. 남발 시 통계 변화에 코드가 못 따라가 더 큰 사고.

---

## 11. 초심자 키워드 사전

본문에서 당연하게 쓴 용어들을 처음 보는 사람 기준으로 풀어 정리.

### Parse (파싱) — hard parse vs soft parse

SQL 한 문장이 실행되기 전 Oracle 이 거치는 준비 단계.

| | 무슨 일 | 비용 |
|---|---|---|
| **Hard parse** | 문법검사 → 권한검사 → **옵티마이저가 통계 보고 실행계획 생성** → Library Cache 에 적재 | 비용 높음 (CPU·메모리, 옵티마이저 연산) |
| **Soft parse** | 같은 SQL 이 Library Cache 에 이미 있음 → **계획 재사용**, 생성 단계 건너뜀 | 비용 낮음 |

→ SQL 문자열이 매번 달라지면(값을 문자열로 박은 SQL) hard parse가 늘어 CPU를 낭비한다. **바인드 변수**를 쓰면 SQL 문자열이 동일해져 soft parse 재사용 가능성이 높아진다.

### Cursor (커서)

하나의 SQL, 실행계획, 실행 상태를 담는 **메모리 핸들**. Library Cache 에 캐싱되는 단위가 cursor. cursor 가 캐시에서 밀려나면 다음 실행 때 hard parse가 필요할 수 있다.

### Bind variable (바인드 변수)

SQL 의 값 자리를 `?`(JDBC) / `:1`(Oracle) 같은 **자리표시자**로 두는 것.

```sql
-- 바인드 X : 값마다 다른 SQL 문자열 → 매번 hard parse
SELECT * FROM SAMPLE_TXN WHERE TENANT_ID = 'TENANT_A';
SELECT * FROM SAMPLE_TXN WHERE TENANT_ID = 'TENANT_B';

-- 바인드 O : 문자열 동일 → soft parse 재사용
SELECT * FROM SAMPLE_TXN WHERE TENANT_ID = :1;
```

MyBatis `#{param}`, JDBC `PreparedStatement` 가 이걸 해 준다. → 보안(SQL Injection 방지) + 성능(parse 재사용) 둘 다 이득.

### Predicate (술어)

WHERE/JOIN 의 **조건식**을 부르는 말. `TENANT_ID = 'TENANT_A'` 같은 것. 실행계획의 Predicate Information은 각 조건을 어디서 어떻게 적용했는지(access/filter)를 보여준다.

### Cardinality (카디널리티)

어떤 단계가 반환할 **row 수**의 추정치. 실행계획의 `Rows` 컬럼이 이것. 옵티마이저는 이 추정으로 조인 방식·인덱스 사용 여부를 결정한다. 추정이 크게 빗나가면 plan 이 틀어질 수 있다.

### Selectivity (선택도)

조건이 전체 중 몇 비율을 남기는지 나타내는 값(0~1).

- 선택도 낮음(=결과 적음) → 인덱스 유리 (예: 고유 업무 키 조건은 보통 선택도가 매우 낮음)
- 선택도 높음(=결과 많음) → 풀스캔이 나을 수도 (예: `STATUS = 0` 이 전체의 90%)

옵티마이저는 통계로 selectivity 를 추정해 cardinality 를 계산한다.

### Histogram (히스토그램)

컬럼 값 **분포** 통계. 값이 고르게 퍼졌는지, 특정 값에 쏠렸는지를 기록.

- 히스토그램 없으면 옵티마이저는 값이 균등 분포한다고 가정할 수 있어 쏠린 데이터에서 오판할 수 있다.
- 예: `STATUS` 가 99% 가 0, 1% 가 1 → 히스토그램 있어야 `STATUS=1` 조건에 인덱스를 옳게 선택.

### CBO vs RBO

| | 판단 기준 |
|---|---|
| **RBO** (Rule-Based, 구식·폐기) | 정해진 규칙 우선순위 (예: 인덱스 있으면 무조건 인덱스) |
| **CBO** (Cost-Based, 현재 표준) | **통계 기반 비용 계산** 후 최저 비용 plan 선택 |

현재 Oracle 옵티마이저의 중심은 CBO다. 그래서 통계 품질이 좋은 plan의 핵심 전제다.

### Cost (비용)

옵티마이저가 매기는 **상대 점수**. I/O·CPU·메모리를 종합한 추정치. 단위는 의미 없음(초도 아님). **대안 plan 끼리 비교용** (Cost 100 vs Cost 5 → 후자를 고른다).

---

## 참고

- Oracle Database SQL Tuning Guide — *Reading Execution Plans* / *DBMS_XPLAN* (Oracle 공식 문서)
- 별도 글: 「Oracle 인덱스 구조 원리 — row는 디스크 어디에 어떻게 저장되나」
