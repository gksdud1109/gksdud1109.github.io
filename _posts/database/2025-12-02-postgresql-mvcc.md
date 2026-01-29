---
title: "PostgreSQL MVCC - MySQL과의 동시성 제어 비교"
date: 2025-12-02 12:00:00 +0900
categories: [Database]
tags: [database, postgresql, mysql, mvcc, concurrency, transaction]
---

## 개요

티켓팅/결제/재고관리 등 정합성과 동시성이 중요한 시스템을 설계할 때, DB의 동시성 제어 방식을 이해하는 것이 중요하다. 이 글에서는 MVCC(Multi-Version Concurrency Control)의 개념과 MySQL InnoDB, PostgreSQL의 구현 차이점을 정리한다.

---

## 1. 동시성 제어(Concurrency Control)의 목적

여러 트랜잭션이 동시에 같은 데이터에 접근할 때 DB의 **정합성(Consistency)**과 **무결성(Integrity)**을 지키는 것이 목표다.

동시성 문제는 크게 두 축에서 발생한다:
1. 읽기 ↔ 쓰기 충돌
2. 쓰기 ↔ 쓰기 충돌

---

## 2. Lock 기반 동시성 제어

### 공유락(Shared Lock, S Lock)

- **읽기** 시 부여
- 여러 트랜잭션이 동시에 읽기 가능
- 쓰기는 불가능

### 배타락(Exclusive Lock, X Lock)

- **쓰기** 시 부여
- 쓰기 중에는 읽기도 불가능

### Lock 기반 제어의 문제점

| 문제 | 설명 |
|------|------|
| 읽기-쓰기 충돌 | SELECT가 UPDATE를 막아버림 → 동시성 급격히 저하 |
| 데드락 | 서로 락을 기다리다 멈춤 |
| 확장성 문제 | 많은 트랜잭션이 같은 데이터를 읽을 때 병목 발생 |

> **Lock만으로는 고성능·고동시성 서비스를 만들 수 없음 → MVCC 등장**

---

## 3. MVCC가 해결하는 문제

MVCC는 말 그대로 **데이터의 버전을 여러 개 유지**하는 방식이다.

- 읽기(SELECT)는 **과거 버전**
- 쓰기(UPDATE)는 **새 버전**

이 때문에:
- **읽기는 절대 쓰기를 막지 않음**
- 읽기 일관성 유지 가능
- 동시성이 매우 높아짐

---

## 4. MySQL InnoDB MVCC — Undo Log 기반 구조

MySQL은 **Undo Log**로 이전 버전을 관리한다.

### UPDATE가 발생하면

```
1. 새로운 값은 Buffer Pool에 기록
2. 이전 값은 Undo Log에 복사
3. 아직 commit X → 다른 트랜잭션은 Undo Log의 값을 읽음
```

### 예시

| 시나리오 | 결과 |
|----------|------|
| Tx A: UPDATE member SET area="경기" | Undo Log에 "서울" 저장 |
| Tx B: SELECT … (Tx A 미커밋) | Undo Log에서 "서울" 읽음 |

### MySQL MVCC의 특징

| 특징 | 설명 |
|------|------|
| Undo Log 필요 | 이전 데이터 재구성 필요 (I/O 비용 증가) |
| 버전 재조립 필요 | 오래된 트랜잭션이 Undo Log를 길게 유지하면 성능 저하 |
| Isolation Level 영향 큼 | READ COMMITTED / REPEATABLE READ 동작이 Undo Log 기반 |

**장점:**
- 구현 단순
- 읽기 성능 좋음 (Undo Log 기반)

**단점:**
- Undo Log 유지 비용 → 동시성 높아지면 성능 저하
- Snapshot 충돌 감지가 PostgreSQL보다 약함
- Lost Update 방지 능력 제한적

---

## 5. PostgreSQL MVCC — Tuple Versioning 구조

PostgreSQL은 Undo Log가 없다. 대신 **한 row가 여러 버전을 테이블 내부에 저장**한다.

### 예시

| Version | xmin | xmax | 값 |
|---------|------|------|----|
| v1 | 10 | 20 | area="서울" |
| v2 | 20 | ∞ | area="경기" |

트랜잭션은 xmin/xmax를 기준으로 보이는 버전을 선택한다.

### PostgreSQL MVCC 특징

| 특징 | 설명 |
|------|------|
| Undo Log 없음 | Undo 재조립 비용 없음 |
| 버전이 row 자체에 존재 | 읽기 비용 감소, 읽기 성능 안정 |
| Snapshot Isolation 기본 제공 | write-write conflict 자동 감지 |
| Vacuum으로 오래된 버전 제거 | 디스크 공간 회수 |

**장점:**
- Snapshot 기반 동시성 제어 우수
- Phantom read 문제도 거의 없음
- Write-write 충돌 자동 해결 (first-updater-wins)

**단점:**
- 테이블 내부 버전 증가 → VACUUM 필요
- 구조가 상대적으로 복잡

---

## 6. Isolation Level과 MVCC의 관계

### SQL 표준 4단계

| Level | Dirty Read | Non-repeatable Read | Phantom Read |
|-------|------------|---------------------|--------------|
| Read Uncommitted | O | O | O |
| Read Committed | X | O | O |
| Repeatable Read | X | X | O |
| Serializable | X | X | X |

---

## 7. 이상현상들 (Anomalies)

| 이상현상 | 설명 |
|----------|------|
| **Dirty Read** | 커밋되지 않은 데이터를 읽음 |
| **Non-repeatable Read** | 같은 row를 두 번 읽을 때 값이 달라짐 |
| **Phantom Read** | 같은 조건으로 조회했는데 row 개수가 달라짐 |
| **Read Skew** | 관련된 값을 따로 읽었는데 시점이 달라 일관성 깨짐 |
| **Write Skew** | 서로 다른 row를 수정해서 제약조건을 깨뜨림 |
| **Lost Update** | 두 트랜잭션이 수정 → 하나의 결과가 덮여 사라짐 |

> **PostgreSQL은 Snapshot Isolation에서 Lost Update를 자동 방지**
> **MySQL Repeatable Read는 기본적으로 방지 못함**

---

## 8. Snapshot Isolation

> 트랜잭션 시작 시점의 snapshot을 자신의 세계처럼 사용한다

- 읽기: snapshot 기준
- 쓰기: 커밋할 때 write-write conflict 감지

**충돌 해결:**
```
먼저 commit한 트랜잭션만 인정
나중에 commit하려는 트랜잭션은 abort
```

- PostgreSQL Repeatable Read = Snapshot Isolation
- Oracle Serializable = Snapshot Isolation
- **MySQL은 Snapshot Isolation을 완전히 지원하진 않음**

---

## 9. MySQL vs PostgreSQL Snapshot 동작 차이

| 항목 | MySQL InnoDB | PostgreSQL |
|------|--------------|------------|
| MVCC 방식 | Undo Log 기반 | Tuple Versioning |
| 스냅샷 시점 | 쿼리마다(RC) / 트랜잭션 전체(RR) | 트랜잭션 전체 스냅샷 |
| Phantom Read 방지 | Gap Lock 필요 | MVCC 자체로 대부분 해결 |
| Lost Update 방지 | X (기본 RR도 방지 못함) | O (first-updater-wins) |
| 읽기 성능 | 동시성 높아지면 Undo 재조립 비용 증가 | 스냅샷 접근이 빠르고 안정 |

---

## 10. Row-Level Lock

MVCC는 **읽기에는 락을 사용하지 않지만**, 쓰기 충돌을 막기 위해 row-level lock이 필요할 때가 있다.

### PostgreSQL의 row-level lock 종류

| 명령 | 설명 |
|------|------|
| FOR UPDATE | 해당 row 쓰기 독점 |
| FOR NO KEY UPDATE | Key 제외한 수정만 보호 |
| FOR SHARE | 읽기 공유 락 |
| FOR KEY SHARE | key 변경 방지만 막음 |

모든 락은 **트랜잭션 종료 시 해제**된다.

---

## 11. Phantom Read가 발생하는 이유

조건을 만족하는 row 집합이 **시간에 따라 달라지기 때문**이다.

```
Tx1 → SELECT * FROM seats WHERE price < 10000
Tx2 → 새로운 row insert (price = 9000)
Tx1 → 같은 SELECT → 결과가 달라짐 ⬅ Phantom!
```

- **PostgreSQL**: MVCC version scan 덕분에 대부분 자동 방지됨
- **MySQL**: Gap lock / Next-Key Lock 없으면 쉽게 발생

---

## 12. Lost Update 문제

### MySQL 기본 Repeatable Read

- 트랜잭션 시작 시 snapshot 고정
- UPDATE는 실제 row 재검증을 하지 않음
- → Write-write conflict 감지가 매우 약함
- → **Overwrite 발생 가능** (충돌 감지 실패)

### PostgreSQL

- UPDATE 시 version이 변경되었으면 충돌로 판단
- → "먼저 업데이트한 사람이 승자"

> **티켓팅/재고관리 등에서는 PostgreSQL이 훨씬 안정적**

---

## 13. Vacuum / Purge 개념 비교

| DB | 역할 |
|----|------|
| PostgreSQL VACUUM | 오래된 tuple version 제거, 디스크 공간 회수 |
| MySQL Purge Thread | 오래된 Undo Log 삭제 |

둘 다 MVCC가 사용한 "이전 버전"을 정리하는 역할을 수행한다.

---

## 정리

1. Lock 기반 제어는 동시성·성능 면에서 한계가 있어 **MVCC 등장**
2. MySQL은 **Undo Log 기반** MVCC → 버전 재조립 비용이 큼
3. PostgreSQL은 **Tuple Versioning** → 버전이 row에 바로 존재
4. PostgreSQL은 **Snapshot Isolation이 기본** → write 충돌 자동 방지
5. MySQL은 기본 Repeatable Read여도 **lost update 가능**
6. Phantom read는 PostgreSQL에서 거의 발생하지 않으나 **MySQL은 gap lock 필요**
7. Row-level lock은 MVCC로도 해결 못하는 **쓰기 충돌을 해결**하기 위해 필요
8. MVCC는 읽기-쓰기 충돌 최소화하지만 **버전 정리(VACUUM/Purge)가 필요**
9. Serializable은 가장 안전하지만 **성능 희생 큼**
10. **고동시성(티켓팅, 결제 등)에서는 PostgreSQL이 더 유리**

---

## 참고

- [[Database] MVCC(다중 버전 동시성 제어)란?](https://mangkyu.tistory.com/53)
- [[PostgreSQL] PostgreSQL이란?](https://mangkyu.tistory.com/71)
- [MySQL의 InnoDB가 MVCC를 구현하는 법](https://velog.io/@kny8092/MySQL%EC%9D%98-InnoDB%EA%B0%80-MVCC%EB%A5%BC-%EA%B5%AC%ED%98%84%ED%95%98%EB%8A%94-%EB%B2%95)
- [snapshot isolation](https://velog.io/@alsry922/snapshot-isolation)
- [[PostgreSQL] Lock의 종류](https://kwanok.me/blog/postgresql-lock/)
