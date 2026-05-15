---
title: "Oracle 실행계획 읽는 법 - EXPLAIN PLAN과 옵티마이저"
date: 2026-05-14 13:00:00 +0900
categories: [Database]
tags: [database, oracle, sql, execution-plan, optimizer]
---

> 발급성 OLTP 테이블(예시 `INVITE_ISSUE`)의 쿼리로 실행계획을 떠보고 읽는다. 모든 테이블/인덱스/식별자는 일반화된 예시 값. 인덱스 물리 구조·PGA·OLTP 는 별도 글 「Oracle 인덱스 구조 원리」 참고.

---

## 0. 왜 실행계획을 봐야 하나

SQL 은 **선언적 언어**다. "무엇을 원하는지" 만 쓰고 "어떻게 가져올지" 는 안 쓴다. 그 "어떻게" 를 DB의 **옵티마이저(Optimizer)** 가 정한다.

문제는 — 내가 인덱스를 만들 때 머릿속에 그린 "이 쿼리는 이 인덱스를 탈 것이다" 라는 가정이, 옵티마이저의 실제 판단과 다를 수 있다는 것. 그 차이를 눈으로 확인하는 도구가 **실행계획(Execution Plan)** 이다.

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
SELECT COUNT(*) FROM INVITE_ISSUE WHERE WORKSPACE_ID = ?;
```

- `IDX_INVITE_WS(WORKSPACE_ID)` 있으면 → **INDEX RANGE SCAN** (해당 영역 leaf 만 훑음)
- 인덱스 없으면 → **TABLE FULL SCAN** (100만 row 전부 읽어 비교)

테이블 row 가 200 byte, 인덱스 entry 가 20 byte 면 **읽을 블록 수가 약 10배 차이**. → 필요한 컬럼이 인덱스에 다 있으면(index-only) 빠른 이유.

> **INDEX FAST FULL SCAN**: 인덱스 정렬 순서 무시, multi-block read 로 인덱스 전체를 쓸어담음. `COUNT(*)` 처럼 순서 불필요할 때 옵티마이저가 고르는 풀카운트 최속 경로.

---

## 2. 실행계획은 어디에 저장되나 — 두 가지를 구분하라

| | 어디 저장 | 영구? | 조회 |
|---|---|---|---|
| **EXPLAIN PLAN 결과** (예측) | `PLAN_TABLE` 이라는 **실제 테이블** | 임시(다음 EXPLAIN이 덮음) | `DBMS_XPLAN.DISPLAY()` |
| **실제 실행된 plan** | **SGA → Shared Pool → Library Cache (메모리)** | 캐시에서 밀리면 사라짐 | `V$SQL_PLAN` 동적 뷰 |

```sql
EXPLAIN PLAN FOR
SELECT COUNT(*) FROM INVITE_ISSUE WHERE WORKSPACE_ID = 'WS_1001';
-- 위 한 줄이 PLAN_TABLE 에 id 0,1,2... row 로 INSERT 됨

SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY());
-- PLAN_TABLE 을 읽어 표로 포맷
```

→ EXPLAIN 순간 `PLAN_TABLE` 에 row 로 저장(임시). 영구 보관하려면 SQL Plan Baseline 같은 별도 기능 필요.

> **Library Cache 는 SGA(공유 메모리) 안에 있다.** 그래서 한 세션이 만든 실행계획을 다른 세션이 재사용한다. (SGA/PGA 구분은 「Oracle 인덱스 구조 원리」 6장 참고 — 정렬용 PGA 와 헷갈리지 말 것.)

---

## 3. 옵티마이저는 무엇을 보고 plan 을 정하나 — 통계 기반(CBO)

오해 1순위: "쿼리를 많이 돌리면 옵티마이저가 학습해서 더 좋은 plan 으로 갱신한다" → **아니다.**

Oracle 옵티마이저는 **CBO(Cost-Based Optimizer)**. 데이터를 매번 직접 보는 게 아니라 **데이터의 요약 통계** 로 비용을 계산한다.

```text
DBMS_STATS.GATHER_TABLE_STATS   (야간 자동배치 or 수동)
   ↓
통계 저장: 테이블 row 수, 블록 수, 컬럼별 distinct 수,
          데이터 분포(히스토그램), 인덱스 높이 등
   ↓
SQL 첫 실행 = hard parse
   → 옵티마이저가 "통계" 로 비용 계산 → plan 결정
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
| bind 값 차이 | (12c+) adaptive — 처음 본 값에 plan 맞췄다가 패턴 다르면 재적응 |

> **운영에서 멀쩡하던 쿼리가 갑자기 느려졌다 → 1순위 의심은 "통계가 낡았다".** `DBMS_STATS.GATHER_TABLE_STATS` 로 갱신하면 현재 데이터 규모에 맞는 plan 을 다시 만든다.

---

## 4. Operation 종류 사전

### 인덱스 접근

| Operation | 의미 | 언제 |
|---|---|---|
| `INDEX UNIQUE SCAN` | 딱 **1건** 보장하고 찾음 | PK/UK 등치. 가장 빠름 |
| `INDEX RANGE SCAN` | 정렬 인덱스에서 **여러 건/범위** | `=`(중복가능), `BETWEEN`, `>`, `LIKE 'A%'` |
| `INDEX FULL SCAN` | 인덱스 전체를 **순서대로**(single block) | ORDER BY 를 인덱스로 대체 |
| `INDEX FAST FULL SCAN` | 인덱스 전체를 **순서무시 multi-block** | `COUNT(*)` 등 순서 불필요. 풀카운트 최속 |
| `INDEX SKIP SCAN` | 복합 인덱스 **선두 컬럼 건너뛰고** 탐색 | 선두 조건 빠졌을 때. 선두 distinct 적을 때만 이득 |

### 테이블 접근

| Operation | 의미 |
|---|---|
| `TABLE ACCESS FULL` | 풀스캔 (작은 테이블 OK, 큰 테이블 위험 신호) |
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
SELECT COUNT(*) FROM INVITE_ISSUE WHERE WORKSPACE_ID = 'WS_1001';

SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY());
```

출력:

```text
Plan hash value: 1613623564

-----------------------------------------------------------------------------------
| Id  | Operation         | Name                | Rows | Bytes | Cost (%CPU)| Time     |
-----------------------------------------------------------------------------------
|   0 | SELECT STATEMENT  |                     |    1 |    16 |     1   (0)| 00:00:01 |
|   1 |  SORT AGGREGATE   |                     |    1 |    16 |            |          |
|*  2 |   INDEX RANGE SCAN| IDX_INVITE_WS       |    5 |    80 |     1   (0)| 00:00:01 |
-----------------------------------------------------------------------------------

Predicate Information (identified by operation id):
---------------------------------------------------
   2 - access("WORKSPACE_ID"='WS_1001')
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

**Bytes 를 왜 세나?** 데이터 크기가 비용을 좌우한다. 정렬(SORT)/해시조인 시 "PGA work area 에 다 들어가나, temp 로 spill 나나" 를 byte 로 판단한다. 작은 컬럼만 읽으면 bytes 작아 비용 낮음 → `SELECT *` 보다 필요 컬럼만 select 가 plan 상 유리.

### Predicate Information — `access` vs `filter` (가장 중요)

```text
2 - access("WORKSPACE_ID"='WS_1001')
```

"operation **id 2** 에서 어떤 조건을 어떻게 썼는가".

| | 의미 | 효율 |
|---|---|---|
| **access** | 인덱스 **탐색 자체** 에 조건 사용 → 처음부터 해당 범위만 읽음 | ✅ 좋음 |
| **filter** | 일단 읽어온 뒤 **메모리에서 버림** | ⚠️ 나쁨 (불필요 read) |

위는 `access` → 그 값 영역만 콕 집어 읽음. **이상적.** 같은 조건이 `filter` 였다면 다 읽고 걸렀다는 뜻이라 비효율.

### 읽는 순서

**들여쓰기 깊고 위에 있는 것부터 → 바깥으로** (id 2 → 1 → 0)

| Id | 해석 |
|---|---|
| **2** | `IDX_INVITE_WS` RANGE SCAN. 조건을 **access** 로 사용 → 약 5건, 80 byte. **TABLE ACCESS 없음** = index-only |
| **1** | 그 5건을 `SORT AGGREGATE` 집계 → `COUNT(*)` 1행 |
| **0** | 최종 SELECT 1행 반환 |

`Plan hash value` = 이 plan 구조의 **지문**. 같은 SQL 재측정 시 값이 바뀌면 옵티마이저가 다른 plan 을 골랐다는 신호 → 통계 변화 의심.

---

## 6. 좋은 plan / 나쁜 plan 신호

**좋은 신호**

- 인덱스 키워드(`INDEX UNIQUE/RANGE/FAST FULL SCAN`) 보임
- 의도한 인덱스 이름 보임
- 큰 테이블에 `TABLE ACCESS FULL` 없음
- WHERE 가 `access:` 에 잡힘 (`filter:` 아님)

**나쁜 신호**

- 큰 테이블에 `TABLE ACCESS FULL`
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
| 풀스캔 vs 인덱스스캔 | 같은 "전부 읽기"여도 대상이 **테이블 블록 vs 인덱스 leaf** — 후자가 훨씬 작음 |
| 실행계획 저장 | EXPLAIN → `PLAN_TABLE`(임시 테이블), 실제 실행 → SGA Library Cache(메모리) |
| 옵티마이저 판단 기준 | 쿼리 빈도 ❌ / **통계(CBO)** ✅, parse 시점 결정, 통계·DDL 변경 시 재계산 |
| access vs filter | access=인덱스 탐색에 사용(좋음), filter=읽고 버림(나쁨) |
| Rows / Bytes | Rows=추정 반환 건수, Bytes=그 크기(정렬/조인 메모리 비용 계산용) |
| 읽는 순서 | 들여쓰기 깊고 위 → 바깥 |

---

## 10. 더 파볼 키워드

1. **Clustering Factor** — 인덱스 키 순서와 테이블 row 물리 순서 유사도. 나쁘면 RANGE SCAN 후 TABLE ACCESS 비용 폭증.
2. **복합 인덱스 컬럼 순서** — `(A,B,C)` 는 선두(A) 조건 없으면 잘 안 탐(또는 비싼 SKIP SCAN).
3. **Cardinality 추정 오류** — `DISPLAY_CURSOR('ALLSTATS LAST')` 의 E-Rows vs A-Rows. 느린 쿼리의 가장 흔한 근본 원인.
4. **Bind Variable Peeking & Adaptive Plan** — `?` 자리 값에 따라 plan 이 달라지는 함정.
5. **`/*+ INDEX(t idx) */` 힌트** — 옵티마이저 결정 강제. 최후의 수단. 남발 시 통계 변화에 코드가 못 따라가 더 큰 사고.

---

## 11. 초심자 키워드 사전

본문에서 당연하게 쓴 용어들을 처음 보는 사람 기준으로 풀어 정리.

### Parse (파싱) — hard parse vs soft parse

SQL 한 문장이 실행되기 전 Oracle 이 거치는 준비 단계.

| | 무슨 일 | 비용 |
|---|---|---|
| **Hard parse** | 문법검사 → 권한검사 → **옵티마이저가 통계 보고 실행계획 생성** → Library Cache 에 적재 | 비쌈 (CPU·메모리, 옵티마이저 연산) |
| **Soft parse** | 같은 SQL 이 Library Cache 에 이미 있음 → **계획 재사용**, 생성 단계 건너뜀 | 쌈 |

→ SQL 문자열이 매번 달라지면(값을 문자열로 박은 SQL) hard parse 폭증 → CPU 낭비. **바인드 변수**를 쓰면 SQL 문자열이 동일해져 soft parse 로 재사용된다.

### Cursor (커서)

"하나의 SQL + 그 실행계획 + 실행 상태" 를 담는 **메모리 핸들**. Library Cache 에 캐싱되는 단위가 cursor. "cursor 가 캐시에서 밀려났다" = 그 SQL 의 계획이 메모리에서 빠져 다음에 hard parse 해야 함.

### Bind variable (바인드 변수)

SQL 의 값 자리를 `?`(JDBC) / `:1`(Oracle) 같은 **자리표시자**로 두는 것.

```sql
-- 바인드 X : 값마다 다른 SQL 문자열 → 매번 hard parse
SELECT * FROM INVITE_ISSUE WHERE WORKSPACE_ID = 'WS_1001';
SELECT * FROM INVITE_ISSUE WHERE WORKSPACE_ID = 'WS_1002';

-- 바인드 O : 문자열 동일 → soft parse 재사용
SELECT * FROM INVITE_ISSUE WHERE WORKSPACE_ID = :1;
```

MyBatis `#{param}`, JDBC `PreparedStatement` 가 이걸 해 준다. → 보안(SQL Injection 방지) + 성능(parse 재사용) 둘 다 이득.

### Predicate (술어)

WHERE/JOIN 의 **조건식**을 부르는 말. `WORKSPACE_ID = 'WS_1001'` 같은 것. 실행계획의 "Predicate Information" = "각 조건을 어디서 어떻게 적용했나(access/filter)".

### Cardinality (카디널리티)

"어떤 단계가 반환할 **row 수**" 의 추정치. 실행계획의 `Rows` 컬럼이 이것. 옵티마이저는 이 추정으로 조인 방식·인덱스 사용 여부를 결정 → **추정이 빗나가면 plan 이 통째로 틀어진다**(느린 쿼리 1순위 원인).

### Selectivity (선택도)

"조건이 전체 중 몇 비율을 남기나" (0~1).

- 선택도 낮음(=결과 적음) → 인덱스 유리 (예: `INVITE_CODE = ?` 는 1건, 선택도 매우 낮음)
- 선택도 높음(=결과 많음) → 풀스캔이 나을 수도 (예: `STATUS = 0` 이 전체의 90%)

옵티마이저는 통계로 selectivity 를 추정해 cardinality 를 계산한다.

### Histogram (히스토그램)

컬럼 값 **분포** 통계. 값이 고르게 퍼졌는지, 특정 값에 쏠렸는지를 기록.

- 히스토그램 없으면 옵티마이저는 "값이 균등 분포" 라고 가정 → 쏠린 데이터에서 오판.
- 예: `STATUS` 가 99% 가 0, 1% 가 1 → 히스토그램 있어야 `STATUS=1` 조건에 인덱스를 옳게 선택.

### CBO vs RBO

| | 판단 기준 |
|---|---|
| **RBO** (Rule-Based, 구식·폐기) | 정해진 규칙 우선순위 (예: 인덱스 있으면 무조건 인덱스) |
| **CBO** (Cost-Based, 현재 표준) | **통계 기반 비용 계산** 후 최저 비용 plan 선택 |

지금 Oracle 은 전부 CBO. 그래서 "통계가 정확해야 좋은 plan 이 나온다" 가 핵심 명제.

### Cost (비용)

옵티마이저가 매기는 **상대 점수**. I/O·CPU·메모리를 종합한 추정치. 단위는 의미 없음(초도 아님). **대안 plan 끼리 비교용** (Cost 100 vs Cost 5 → 후자를 고른다).

---

## 참고

- Oracle Database SQL Tuning Guide — *Reading Execution Plans* / *DBMS_XPLAN* (Oracle 공식 문서)
- 별도 글: 「Oracle 인덱스 구조 원리 — row는 디스크 어디에 어떻게 저장되나」
