---
title: "Oracle 인덱스 구조 원리 - row는 디스크 어디에 어떻게 저장되나"
date: 2026-05-14 12:00:00 +0900
categories: [Database]
tags: [database, oracle, index, b-tree, oltp]
---

> 발급성 OLTP 테이블(예시 `INVITE_ISSUE`)을 다루며 "INSERT 한 row 는 디스크 어디에, 어떤 모양으로 들어가고, 인덱스는 그걸 어떻게 가리키는가" 를 따라간다. 모든 테이블/인덱스 이름은 일반화된 예시 값이다. 실행계획 읽는 법은 별도 글 「Oracle 실행계획 읽는 법」 참고.

---

## 0. 큰 그림 — 이 글이 답하는 질문

1. `INSERT` 한 row 는 디스크의 **어디에** 저장되지? (물리 저장 계층)
2. 그 row 의 주소 **ROWID** 는 어떻게 생겼지?
3. row 가 블록에 들어갈 때 **PCTFREE** 가 왜 중요하지? (row migration / chaining)
4. 인덱스(B+Tree)는 그 ROWID 를 어떻게 들고 있지?
5. 인덱스를 만들 때 쓰는 **PGA 메모리**는 SGA 와 뭐가 다르지?
6. 왜 이 모든 설계가 **OLTP** 에서 특히 중요하지?

---

## 1. 물리 저장 계층 — Database → Block

Oracle 은 데이터를 다음 계층으로 담는다. **아래로 갈수록 물리적, 위로 갈수록 논리적.**

```text
Database
  └─ Tablespace--------------------(논리 저장 단위. 예: USERS, APP_DATA)
       └─ Datafile-----------------(실제 OS 파일. tablespace = 여러 datafile)
            └─ Segment-------------(테이블/인덱스 하나 = 하나의 segment)
                 └─ Extent---------(연속된 블록 묶음. segment 가 커지면 extent 단위로 확장)
                      └─ Block-----(= Oracle I/O 최소 단위. 보통 8KB)
                           └─ Row
```

핵심 한 줄: **Oracle 이 디스크에서 읽고 쓰는 최소 단위는 "블록(block)" 이다.** row 하나만 필요해도 그 row 가 든 **블록 전체(8KB)** 를 읽는다. → 블록당 row 가 몇 개 들어가는지가 성능을 좌우한다.

| 단어 | 의미 | 비유 |
|---|---|---|
| Tablespace | 논리 저장 공간 이름 | 책장 |
| Datafile | 실제 OS 파일 | 책장의 물리 칸 |
| Segment | 테이블/인덱스 1개의 저장 영역 | 책 한 권 |
| Extent | 연속 블록 묶음 (확장 단위) | 책의 한 챕터 |
| Block | I/O 최소 단위 (8KB) | 책의 한 페이지 |

---

## 2. 블록 내부 — row 와 ROWID 가 담기는 구조

### 2-1. 데이터 블록의 내부 레이아웃

```text
+---------------------------------------------------+
| Block Header  (블록 메타: 주소, 트랜잭션 정보 ITL)    |
+---------------------------------------------------+
| Table Directory                                   |
+---------------------------------------------------+
| Row Directory (각 row 의 블록 내 위치 슬롯 배열)      |
+---------------------------------------------------+
|                                                   |
|   Free Space   <-- PCTFREE 가 지키는 영역           |
|                                                   |
+---------------------------------------------------+
| Row Data (실제 row 들이 아래에서 위로 쌓임)           |
|   Row 2 | Row 1 | Row 0 ...                       |
+---------------------------------------------------+
```

- **Row Directory**: "이 블록의 N번 row 는 블록 내 몇 byte 지점에 있다" 는 슬롯 배열. 인덱스가 가리키는 `RRR`(row number)이 이 슬롯 번호다.
- **Row Data**: 실제 row. 한 row 는 `row header + (컬럼길이 + 컬럼값) × 컬럼수` 형태.

### 2-2. ROWID — row 의 물리 주소

`ROWID` 는 "이 row 가 디스크 어디에 있는지" 를 가리키는 18자리(Extended ROWID) 주소다.

```text
ROWID =  OOOOOO   FFF   BBBBBB   RRR
         ▲ 6자리   ▲3    ▲6자리   ▲3
         |         |     |        └ Row number  (블록 안에서 몇 번째 row, = Row Directory 슬롯)
         |         |     └ Block number (datafile 안에서 몇 번째 블록)
         |         └ relative File number (tablespace 안에서 몇 번째 파일)
         └ data Object number (어느 세그먼트=테이블/파티션)
```

예: `AAAR3sAAEAAAACXAAA` → base64 인코딩된 18자.

**왜 중요한가:** 인덱스는 키값과 함께 **이 ROWID 를 저장**한다. `INDEX RANGE SCAN → TABLE ACCESS BY INDEX ROWID` 가 실행계획에 2단계로 잡히는 이유가 이것:

1. 인덱스에서 키로 ROWID 를 찾고 (`Object+File+Block+Row`)
2. 그 ROWID 가 가리키는 **블록을 직접 읽어** 테이블 본체 컬럼을 가져온다.

> ROWID 는 가장 빠른 단일 row 접근 경로다 (`WHERE ROWID = ...`). 인덱스 탐색조차 건너뛰고 디스크 주소로 바로 점프하기 때문.

---

## 3. `INSERT` 한 row 가 들어가는 과정

```text
1. 세그먼트의 "빈 블록 후보 목록"에서 들어갈 블록을 고름
     - 수동 관리: Freelist (빈 블록 연결 리스트)
     - 자동 관리(ASSM, 현대 기본값): 비트맵으로 여유 블록 추적
2. 고른 블록의 Free Space 에 row 를 씀 (Row Data 영역, 아래→위)
3. Row Directory 에 슬롯 추가 → 이 슬롯 번호가 ROWID 의 RRR
4. 그 row 의 키값 + ROWID 를 모든 관련 인덱스의 B+Tree 에 끼워넣음
5. (commit 시) redo/undo 정리
```

여기서 **4번 = "인덱스가 N개면 INSERT 한 번에 트리 작업 N번"** 의 출처. 인덱스 추가에 신중해야 하는 이유.

---

## 4. PCTFREE — 블록에 일부러 비워두는 공간

### 4-1. 정의

`PCTFREE` = 블록의 이 비율(%)만큼은 **INSERT 로 채우지 않고 비워둔다**. 기본값 10%.

```text
PCTFREE 10 인 블록:
  [ 90% 까지만 INSERT 로 채움 ][ 10% 는 빈 채로 예약 ]
                                 ▲
                                 기존 row 가 UPDATE 로 커질 때 쓸 자리
```

### 4-2. 왜 비워두나 — row migration / row chaining 방지

| 현상 | 언제 발생 | 결과 |
|---|---|---|
| **Row Migration** | UPDATE 로 row 가 커졌는데 그 블록에 자리가 없음 → row 를 **다른 블록으로 이사** | 원래 자리엔 "새 주소" 포인터만 남김. **ROWID 는 안 바뀜**(인덱스 갱신 회피용). 단, 그 row 조회 시 **블록을 2번 읽음** (원래 블록 → 포인터 따라 새 블록) |
| **Row Chaining** | row 가 너무 커서 블록 하나에 안 들어감 (큰 컬럼, 255개 초과 컬럼) | row 가 여러 블록에 쪼개져 저장. 조회 시 여러 블록 읽음 |

→ PCTFREE 가 너무 작으면: UPDATE 빈번한 테이블에서 **row migration 폭증 → 단건 조회가 블록 2번 read → OLTP 응답속도 저하**.
→ PCTFREE 가 너무 크면: 블록당 row 수 감소 → 같은 데이터에 블록 더 필요 → 풀스캔/캐시 효율 저하 + 디스크 낭비.

### 4-3. 짝꿍 — PCTUSED

`PCTUSED` = 블록 사용량이 이 % **밑으로 떨어지면** 다시 "INSERT 받을 후보 블록" 목록에 복귀. (현대 기본값인 ASSM 에서는 Oracle 이 자동 관리하므로 직접 설정할 일은 거의 없음. 개념만 알아두면 됨.)

### 4-4. 실무 가이드

| 테이블 성격 | PCTFREE 권장 | 이유 |
|---|---|---|
| INSERT 후 거의 UPDATE 안 함 (로그성, 발급 이력) | **낮게** (예: 5 이하) | 빈 공간 예약 불필요 → 블록 꽉 채워 효율 ↑ |
| UPDATE 로 row 가 자주 커짐 (상태/값 변경 잦음) | **높게** (예: 20~30) | migration 방지 |

> 발급 테이블처럼 "INSERT 하고 사용 시 STATUS 등 **고정 크기 컬럼만 UPDATE**" 하는 경우 → row 크기가 거의 안 변하므로 migration 위험 낮음. PCTFREE 낮게 잡아도 무방.

---

## 5. 인덱스 구조 — B-tree 라 부르지만 실제는 B+Tree

```text
              [Root Block]
              |  100  |  500  |
             /        |        \
       [Branch]    [Branch]    [Branch]
       /     \    /      \    /      \
    [Leaf]<->[Leaf]<->[Leaf]<->[Leaf]<->[Leaf]   <- leaf 끼리 양방향 linked list
     key      key      key      key      key
     +ROWID   +ROWID   +ROWID   +ROWID   +ROWID
```

**B+Tree 핵심 성질:**

1. **실제 데이터(키 + ROWID)는 leaf 에만.** branch/root 는 라우팅 정보뿐.
2. **leaf 끼리 양방향 linked list.** RANGE SCAN 시 트리 재탐색 없이 옆으로만 이동 → `BETWEEN`, `LIKE 'A%'`, `>=` 가 빠른 이유.
3. **높이 균형(balanced).** 어떤 키든 root→leaf 까지 같은 블록 수(보통 3~4).

| | B-tree | B+Tree |
|---|---|---|
| 데이터 위치 | branch 노드에도 | **leaf 에만** |
| 범위/순차 스캔 | 불리 | **유리** (leaf linked list) |

자바 `TreeMap` 은 Red-Black tree(메모리 자료구조)라 결이 다르다. 디스크 인덱스는 한 블록에 키를 최대한 많이 담아 **트리 높이를 낮춰 I/O 횟수를 줄이는 것**이 목적이라 B+Tree.

### `CREATE INDEX` 내부 동작

```sql
CREATE INDEX IDX_INVITE_WS ON INVITE_ISSUE(WORKSPACE_ID);
```

```text
1. 테이블 풀스캔 → 모든 row 의 (WORKSPACE_ID, ROWID) 쌍 추출
2. 외부 정렬(sort) → PGA work area 에서 정렬, 부족하면 임시 테이블스페이스로 spill   ← 6장 PGA 와 연결
3. 정렬된 데이터를 leaf 부터 bottom-up 으로 쌓음 (PCTFREE 만큼 빈 공간 남김)
4. data dictionary 등록 (USER_INDEXES 등)
```

- **생성 시 bottom-up**, **운영 INSERT 시 top-down split** (leaf 꽉 차면 split → 부모로 전파 → 트리 높이 증가 가능).

### 인덱스 변형

| 종류 | 용도 |
|---|---|
| **B-tree** (기본) | 거의 모든 경우. 카디널리티 높은 컬럼 |
| **Bitmap** | 카디널리티 낮은 컬럼. OLAP 전용. **OLTP 금지** (→ 7장에서 이유 상세) |
| **Function-based** | `ON t(UPPER(name))` 처럼 함수 결과 인덱싱 |
| **Reverse key** | 키를 뒤집어 저장. 단조증가 시퀀스의 hot block 분산 |

---

## 6. PGA 메모리 — SGA 와 무엇이 다른가

인덱스 생성·정렬·해시조인이 쓰는 메모리가 **PGA** 다. SGA 와 헷갈리기 쉬우니 정확히 구분한다.

> Oracle 인스턴스 메모리 = **SGA + PGA**. (Oracle 공식 *Database Concepts* 의 "Oracle Database Memory Structures" 다이어그램 참고.)

| | SGA (System Global Area) | PGA (Program Global Area) |
|---|---|---|
| 공유 여부 | **모든 프로세스가 공유** | **서버 프로세스 1개 전용 (비공유)** |
| 언제 생성 | 인스턴스 startup 시 1개 | 프로세스(세션) 생길 때마다 1개씩 |
| 담는 것 | Buffer Cache, **Shared Pool(Library Cache 등)**, Redo Log Buffer ... | **SQL Work Area**(sort/hash), 세션 메모리, Private SQL Area(커서 상태·바인드 변수) |
| 예시 역할 | 캐시된 데이터 블록, 캐시된 실행계획 공유 | 내 세션의 ORDER BY 정렬, 해시조인 작업판 |

> 실행계획이 캐싱되는 **Library Cache** 는 SGA 안의 Shared Pool 소속(= 공유).
> 정렬/해시조인 작업판인 **Work Area** 는 PGA 소속(= 내 세션 전용).
> 이 구분이 「Oracle 실행계획 읽는 법」의 "실행계획 어디 저장되나" 와 직접 연결된다.

### PGA Work Area — 정렬/해시가 일어나는 곳

`ORDER BY`, `GROUP BY`, `CREATE INDEX`(정렬), `HASH JOIN` 은 모두 PGA work area 에서 처리:

```text
데이터가 work area 메모리에 다 들어감     → "optimal"  (가장 빠름, 메모리 내 완결)
조금 넘쳐서 temp tablespace 1회 왕복      → "one-pass" (디스크 1회)
많이 넘쳐서 temp 여러 번 왕복             → "multi-pass"(디스크 여러 번, 매우 느림)
```

→ 실행계획의 **Bytes** 컬럼이 큰 의미를 갖는 이유: 옵티마이저가 "이 정렬이 work area 에 들어갈까, temp 로 spill 날까" 를 byte 크기로 추정해 비용을 매긴다. `CREATE INDEX` 가 큰 테이블에서 느린 것도 정렬 단계가 work area 를 넘쳐 temp 로 spill 나기 때문.

---

## 7. OLTP — 왜 이 모든 게 OLTP 에서 특히 중요한가

### 7-1. OLTP vs OLAP

| | **OLTP** (Online Transaction Processing) | **OLAP** (Online Analytical Processing) |
|---|---|---|
| 트랜잭션 | 짧고 **매우 많음** (초당 수백~수천) | 길고 적음 |
| 접근 패턴 | 인덱스로 **단건/소수건 핀포인트** read/write | 대량 집계, 풀스캔/병렬 |
| 동시성 | **매우 높음** (동시 사용자 다수) | 낮음 |
| 예시 | 발급/사용, 주문, 결제 | 일별 통계 배치, 리포트 |
| 핵심 관심사 | **응답속도 + 동시성** | **처리량(throughput)** |

발급/사용 API 는 전형적 OLTP. "한 사용자의 한 건" 을 인덱스로 핀포인트 조회하고, 짧은 트랜잭션이 동시에 쏟아진다.

### 7-2. OLTP 에서 앞 내용들이 갖는 의미

| 앞에서 본 것 | OLTP 에 미치는 영향 |
|---|---|
| **블록이 I/O 최소 단위** | 단건 조회도 블록 1개 read. 인덱스로 정확히 1블록만 건드리게 설계해야 동시성 유지 |
| **ROWID 2단계 접근** | `INDEX SCAN → TABLE ACCESS BY ROWID` 가 row 마다 발생. 필요 컬럼을 인덱스에 다 넣으면(커버링) 테이블 접근 생략 → OLTP 응답 단축 |
| **Row Migration** | UPDATE 많은 OLTP 에서 PCTFREE 부족 시 단건 조회가 블록 2번 read → 누적되면 응답 저하 |
| **인덱스 N개 = INSERT 트리작업 N번** | INSERT 폭주하는 발급 테이블에서 인덱스 남발 = 쓰기 지연. **꼭 필요한 인덱스만** |
| **PGA work area** | OLTP 는 큰 정렬/해시가 드물어야 정상. 불필요한 `ORDER BY`/`DISTINCT` 가 끼면 세션마다 PGA 소모 → 동시성 저하 |

### 7-3. Bitmap 인덱스가 OLTP 에서 금지인 이유

- Bitmap 인덱스는 **한 키값이 다수 row 를 비트맵으로 커버**한다.
- 한 row 의 해당 컬럼을 DML(INSERT/UPDATE/DELETE) 하면 → 그 **비트맵 세그먼트 조각 전체에 락**이 걸린다.
- OLTP 는 같은 영역에 동시 DML 이 쏟아지는데, 이 락이 **동시 트랜잭션을 직렬화** → 동시성 붕괴.
- 반면 OLAP 은 읽기 위주 + DML 이 배치성이라 이 락이 문제 안 됨 → bitmap 이 오히려 유리(압축·집계 강점).

→ 결론: **OLTP 테이블 인덱스는 거의 전부 평범한 B-tree** 여야 한다 (예: `UK_INVITE_WS_REQ`, `UK_INVITE_CODE`, `IDX_INVITE_WS`, `IDX_INVITE_WS_STATUS`).

---

## 8. 한 장 요약

| 질문 | 답 |
|---|---|
| row 저장 위치 | Database→Tablespace→Datafile→Segment→Extent→**Block**(I/O 최소 단위 8KB) |
| ROWID 구조 | `Object(6) + File(3) + Block(6) + Row(3)` = row 의 물리 주소. 인덱스가 이걸 저장 |
| 인덱스→테이블 | 인덱스에서 ROWID 찾고 → 그 블록 직접 read (`TABLE ACCESS BY INDEX ROWID`) |
| PCTFREE | 블록에 UPDATE 대비 빈 공간 예약. 부족하면 row migration → 단건 조회 2블록 read |
| B+Tree | 데이터는 leaf 에만, leaf 끼리 linked list → 범위검색 빠름. 높이 균형 |
| SGA vs PGA | SGA=공유(Buffer Cache, Library Cache). PGA=세션 전용(정렬/해시 work area) |
| OLTP 함의 | 핀포인트 인덱스 설계 + 인덱스 최소화 + bitmap 금지 + 큰 정렬 회피 |

---

## 9. 더 파볼 키워드

1. **ASSM vs Freelist** — 세그먼트 빈 공간 관리 방식. 현대 기본은 ASSM(비트맵), 동시 INSERT 시 freelist 경합 줄임.
2. **ITL (Interested Transaction List)** — 블록 헤더 안의 트랜잭션 슬롯. 동시 DML 이 한 블록에 몰리면 ITL 부족으로 대기 발생 (`INITRANS` 파라미터).
3. **Index Clustering Factor** — 인덱스 키 순서와 테이블 row 물리 순서의 유사도. 나쁘면 RANGE SCAN 후 테이블 접근 비용 폭증. `USER_INDEXES.CLUSTERING_FACTOR`.
4. **Covering Index (Index-Only Scan)** — SELECT/WHERE 가 필요로 하는 컬럼을 인덱스에 전부 포함 → `TABLE ACCESS BY ROWID` 생략. OLTP 응답 단축의 핵심 기법.
5. **PGA_AGGREGATE_TARGET / WORKAREA_SIZE_POLICY** — PGA work area 크기를 인스턴스 차원에서 관리하는 파라미터. spill 빈도와 직결.

---

## 참고

- Oracle Database Concepts — *Data Blocks, Extents, and Segments* / *Memory Architecture* (Oracle 공식 문서)
- 별도 글: 「Oracle 실행계획 읽는 법 — EXPLAIN PLAN」
