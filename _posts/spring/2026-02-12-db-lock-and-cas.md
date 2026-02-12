---
title: "DB 락과 CAS - InnoDB와 PostgreSQL의 동기화 메커니즘"
date: 2026-02-12 14:00:00 +0900
categories: [Spring]
tags: [database, mysql, postgresql, innodb, cas, lock, concurrency]
---

## 개요

[이전 글](/posts/os-synchronization-basics/)에서 OS 수준의 동기화 개념을 정리했다. 이번 글에서는 DB(MySQL InnoDB)에서 말하는 락(lock)이 OS 동기화 도구 위에서 어떤 계층 구조로 구현되는지, 그리고 DB-CAS 패턴이 실제로 어떻게 동작하는지 InnoDB와 PostgreSQL을 비교하여 정리한다.

---

## 1. InnoDB 락의 계층 구조

### InnoDB의 락은 1종류가 아니다: Latch vs Transaction Lock

InnoDB 내부에서 흔히 락이라고 부르는 것은 성격이 다른 두 부류가 존재한다.

### 1-1. Latch (래치): 엔진 내부 공유 메모리 보호

InnoDB 엔진이 관리하는 공유 메모리 구조(자료구조)를 깨지지 않게 보호하기 위한 잠금이다.

**보호 대상 예시:**
- Buffer Pool 페이지/페이지 프레임
- B+Tree 인덱스 페이지 (페이지 split/merge, 탐색 포인터 갱신 등)
- Data Dictionary, Undo/Redo 관련 구조
- Lock System 자체의 해시/리스트 등 메타 구조

**특징:**
- 매우 짧게 잡고 빠르게 풀리는 엔진 내부 임계구역 보호용
- 트랜잭션의 논리적 정합성("이 좌석은 내 것")을 표현하기 위한 락이 아님

**OS 매핑:**
- Mutex / RWLock(읽기-쓰기 락) 계열과 동일한 목적
- 구현은 보통 "짧게는 스핀 → 길어지면 sleep" 형태의 하이브리드
- 핵심은 공유 메모리 구조를 망가뜨리지 않도록 상호배제를 보장하는 것

> Latch는 "데이터 레코드 소유권"이 아니라, "엔진 내부 메모리 구조 보호"를 위한 뮤텍스 성격이다.

---

### 1-2. Transaction Lock (트랜잭션 락): SQL 의미의 레코드/범위 잠금

트랜잭션들이 동시에 실행될 때 논리적 데이터 자원(행/범위/테이블)에 대한 접근을 제어해 정합성과 격리성을 보장하는 잠금이다.

**보호 대상 예시:**
- 특정 레코드(행) 자체
- 레코드 사이의 범위(gap)
- 레코드 + 범위(next-key)
- 테이블 레벨 락 등

**특징:**
- 트랜잭션이 끝날 때(Commit/Rollback)까지 유지될 수 있음 (2PL 성격)
- 충돌 시 대기(wait)가 발생할 수 있으며, 대기는 CPU를 태우는 스핀락이 아니라 블로킹(sleep)을 기본으로 함

**OS 매핑:**
- 오랫동안 기다려야 하는 상황을 처리하기 위해 Semaphore/Condition Variable(대기 큐 + sleep/wakeup) 계열과 같은 동작 모델을 가짐

> Transaction Lock은 OS에서 말하는 자원 점유 + 대기 큐 기반 동기화에 해당한다.

---

## 2. InnoDB의 락 관리

InnoDB에서 트랜잭션 락은 보통 다음 구조로 관리된다.

- Lock Manager(락 시스템)가 존재
- (어떤 레코드/범위)에 (어떤 락 모드)를 (누가) 가지고 있고, 누가 기다리고 있는지를 별도의 메모리 구조로 관리

중요한 포인트:
- 락 시스템(해시/리스트/대기열)은 공유 메모리 구조이므로
- 락 시스템을 갱신/조회하는 아주 짧은 순간에는 Latch(뮤텍스/RWLock)로 보호되어야 함

---

## 3. 대기(Waiting) 발생 시: 대기 큐 + sleep/wakeup

트랜잭션 락 충돌이 발생하면, 락이 풀릴 때까지 기다리기가 필요할 수 있다. InnoDB는 일반적으로 다음 형태로 동작한다 (개념적 모델):

1. 대기자가 생기면, 락 시스템이 대기열(Waiting Queue)에 등록
2. 등록이 끝나면 대기 스레드는 sleep(block) 상태로 들어가 CPU를 반납
3. 선점자가 Commit/Rollback으로 락을 해제하면
4. 락 시스템이 대기자 중 일부를 wakeup(signal)하여 실행 가능 상태로 올림

OS에서 배운 세마포어 구현과 대응하면:
- `wait()`: 대기열에 넣고 sleep
- `signal()`: 대기열에서 꺼내 wakeup

주의할 점:
- InnoDB는 OS 세마포어 변수 S 하나로 단순화되는 구현은 아님
- 락 객체별 대기열 + 이벤트/조건변수(futex류 포함) 기반 sleep/wakeup 형태
- 하지만 개념적으로는 세마포어/조건변수 모델(블로킹 동기화)로 보는 게 맞음

---

## 4. Record Lock / Gap Lock / Next-Key Lock

InnoDB 트랜잭션 락은 단순히 "행(레코드) 하나만 잠근다"로 끝나지 않는다. 특히 인덱스를 기반으로 조건 검색을 수행할 때, 격리 수준과 쿼리 형태에 따라 범위까지 잠글 수 있다.

| 락 종류 | 설명 |
|--------|------|
| Record Lock | 특정 레코드(행) 자체에 대한 잠금 |
| Gap Lock | 레코드와 레코드 사이의 구간(삽입 가능 범위) 잠금 |
| Next-Key Lock | (레코드 + 그 앞의 gap)을 함께 잠그는 형태 |

**범위 락에 여러 종류가 존재하는 이유:**
- 팬텀(Phantom) 문제와 같은 범위 내 새 레코드 삽입으로 인한 결과 변화를 제어하기 위해
- 단순한 상호배제뿐 아니라 격리 수준(Isolation) 보장과 연결됨

**실무적으로 기억할 포인트:**
- PK/UNIQUE로 정확히 1건을 집는 갱신은 보통 Record Lock 중심
- 반면 범위 조건(`>`, `BETWEEN` 등)이나 다건 스캔 기반 갱신은 Next-Key/Gap Lock의 영향으로 동시성이 더 떨어질 수 있음

---

## 5. DB-CAS(Compare-And-Swap) 쿼리 실행 시 내부 동작

앞서 InnoDB 잠금이 Latch(엔진 내부 자료구조 보호)와 Transaction Lock(논리적 데이터 잠금)의 2계층으로 구성되고, 대기는 대기 큐 + sleep/wakeup(세마포어/조건변수 계열)로 처리된다는 점을 정리했다. 이제 애플리케이션에서 구현한 DB-CAS가 실제 DB 엔진에서 어떻게 처리되는지 살펴본다.

### DB-CAS 예시 코드 (좌석 상태 전이)

좌석이 AVAILABLE일 때만 RESERVED로 바꾼다를 SQL 한 방으로 원자적으로 실행한다.

```java
int updated = seatRepository.updateSeatStatusIfMatch(
   eventId, seatId,
   SeatStatus.AVAILABLE, SeatStatus.RESERVED
);

if (updated == 0) {
   // CAS 실패: 이미 누가 바꿨거나/상태가 다르거나/없음
}
```

```java
@Modifying(clearAutomatically = true, flushAutomatically = true)
@Query("""
  update Seat s
  set s.seatStatus = :toStatus,
  s.version = s.version + 1
  where s.event.id = :eventId
  and s.id = :seatId
  and s.seatStatus = :fromStatus
""")
int updateSeatStatusIfMatch(
    Long eventId,
    Long seatId,
    SeatStatus fromStatus,
    SeatStatus toStatus
);
```

- `updated == 1`: 기대 상태(AVAILABLE)였다 → 내가 RESERVED로 바꿨다 (CAS 성공)
- `updated == 0`: 기대 상태가 아니었다(RESERVED/SOLD 등) 또는 레코드가 없었다 (CAS 실패)

---

## 6. InnoDB에서의 DB-CAS 동작 (MySQL)

InnoDB는 기본적으로 MVCC + 레코드(행) 잠금(record lock)을 결합해 동시성을 처리한다. 중요한 점은 "DB-CAS도 결국 UPDATE이므로, 최종적으로는 해당 레코드를 쓰기 위해 배타 잠금(X-lock)이 필요하다"는 것이다.

두 트랜잭션이 동시에 같은 좌석을 예약하려 할 때의 전형적인 흐름:

### (1) 레코드 탐색: 인덱스(B+Tree)로 대상 행 찾기

- eventId + seatId(PK/UNIQUE에 준하는 조건)를 이용해 인덱스를 타고 레코드를 찾음
- 이 과정에서 B+Tree 페이지/버퍼풀 페이지 등 엔진 내부 자료구조를 접근하므로, 잠깐의 Latch(엔진 내부 뮤텍스/RWLock)가 잡혔다가 바로 풀릴 수 있음
- 여기서의 Latch는 좌석 소유권이 아니라 인덱스/페이지 같은 공유 메모리 구조를 안전하게 읽고 쓰기 위한 보호

### (2) 쓰기 준비: 대상 레코드에 대한 X-lock(배타 락) 요청

- UPDATE는 "쓰기"이므로, InnoDB는 대상 레코드에 대해 보통 Record X-lock을 요청
- 락 정보는 "레코드 내부에 박는 게 아니라", Lock Manager(락 시스템)의 메모리 구조에 등록
- 락 시스템 자체도 공유 메모리이므로, 등록/조회 순간에는 잠깐의 Latch가 필요

### (3) 충돌 처리: 이미 다른 트랜잭션이 X-lock을 보유 중이라면?

트랜잭션 T1이 먼저 좌석 레코드 X-lock을 잡고 UPDATE를 진행 중이면, T2가 같은 레코드를 UPDATE하려 할 때는 락 충돌이 발생한다.

InnoDB의 기본 동작:

1. T2를 락 대기열(Waiting Queue)에 등록
2. T2 스레드를 sleep(block) 상태로 전환 (CPU를 태우지 않음)
3. T1이 COMMIT/ROLLBACK으로 락을 해제하면
4. 락 매니저가 대기자(T2 등)를 wakeup(signal)

즉, OS 관점으로는 세마포어/조건변수 기반 대기 큐 + sleep/wakeup 방식이다.

### (4) 깨어난 뒤 재평가: WHERE 조건을 다시 검사 → updated=0/1 결정

여기가 DB-CAS의 CAS 느낌이 나오는 지점이다.

- T2는 락이 풀려 깨어나면 UPDATE를 이어서 수행
- 단, 락을 기다린 동안 데이터가 바뀌었을 수 있으므로, `WHERE seat_status = AVAILABLE` 조건을 현재 값 기준으로 다시 평가

결과는 두 가지:

| T1의 행동 | T2의 결과 |
|----------|----------|
| AVAILABLE → RESERVED로 바꿨음 | 조건 불만족 → updated = 0 (CAS 실패) |
| 여전히 AVAILABLE | 조건 만족 → 실제 갱신 수행 → updated = 1 (CAS 성공) |

즉 InnoDB에서 DB-CAS UPDATE 동작은 "락으로 쓰기 순서를 직렬화(serialize)하고, 조건을 마지막에 재평가해 0/1로 성공/실패를 알려주는" 형태로 동작한다.

### (5) 이 방식이 락이 없다(lock-free)는 뜻은 아님

DB-CAS는 CPU CAS처럼 락 없이 값만 바꾸는 모델이 아니다.

원자성의 근거는 CPU 명령어가 아니라:
- (필요 시) X-lock
- Redo/Undo 로그
- 트랜잭션 커밋 규칙

이 결합되어 만들어진다.

다만 장점은 분명하다:
- 애플리케이션에서 SELECT → if(status==AVAILABLE) → UPDATE 같은 체크-후-행동 레이스 구간을 제거하고
- DB가 보장하는 SQL 한 방의 원자적 상태 전이로 압축

---

## 7. PostgreSQL에서의 DB-CAS 동작

PostgreSQL도 MVCC 기반이지만, UPDATE의 구현 방식이 InnoDB와 다르다.

**핵심 차이:**
- **InnoDB**: (논리적으로) 같은 레코드를 갱신하며, undo로 과거 버전을 따라감
- **PostgreSQL**: 기존 튜플을 죽이고(old), 새 튜플을 만든다(new) → UPDATE가 내부적으로 (Old version 종료 + New version 생성) 형태

### (1) 레코드 탐색: 인덱스로 CTID(튜플 위치) 탐색

eventId + seatId 조건을 인덱스(B-Tree)로 탐색하여 힙(Heap)에 있는 튜플의 위치(CTID)를 찾는다.

### (2) MVCC 가시성 검사 + 수정 충돌 확인

- PostgreSQL은 읽기 시점마다 "이 튜플이 내 트랜잭션 스냅샷에서 보이는가"를 체크
- 동시에 누군가 같은 튜플을 UPDATE 중이면, 기본 격리수준(Read Committed)에서는 대체로 그 트랜잭션이 끝날 때까지 기다렸다가 그 결과를 반영해 다시 조건을 평가

### (3) 조건 평가 + "새 버전 생성" 업데이트 수행

조건(seat_status = AVAILABLE)이 만족되면 PostgreSQL은:

1. 기존 튜플(Old tuple)에 대해 "이 버전은 종료됨"을 표시 (삭제된 것처럼 처리)
2. 변경값(RESERVED, version+1)을 가진 새 튜플(New tuple)을 힙에 생성
3. 인덱스가 새 튜플을 가리키도록 필요한 경우 갱신 (단, HOT update이면 인덱스 변경을 최소화할 수도 있음)

즉 PostgreSQL에서 UPDATE는 실질적으로 "old 죽이고 new 만든다"는 것이 핵심이다.

### (4) updated=0/1 반환 방식은 동일, 내부 원리는 다름

- 조건이 맞아 새 버전을 만들면 `updated=1`
- 조건이 맞지 않거나(이미 RESERVED/SOLD) 대상이 없으면 `updated=0`

겉으로는 InnoDB와 동일하게 영향 row 수로 성공/실패를 판단하지만, 내부 동작이 다르므로 쓰기 패턴(죽은 튜플 정리 필요, vacuum)과 인덱스/HOT 여부에 따른 비용이 다른 성질을 갖는다.

---

## 8. InnoDB vs PostgreSQL: DB-CAS 관점 핵심 비교

| 구분 | InnoDB (MySQL) | PostgreSQL |
|-----|----------------|------------|
| UPDATE 모델 | 같은 레코드를 갱신 (undo로 과거 버전) | old 튜플 종료 + new 튜플 생성 |
| 락 정보 저장 | Lock Manager의 메모리 구조 | 튜플 헤더/멀티락(MultiXact) 메커니즘 중심 |
| 충돌 시 대기 | 락 대기열 등록 후 sleep/wakeup | 튜플 수정 충돌 시 대기 후 재평가 (Read Committed 기준) |
| updated=0의 의미 | 락 대기 후 조건 재평가 결과 불일치 | 대기 후 조건 재평가 결과 불일치 |
| 개발자가 얻는 효과 | 상태 전이 1쿼리로 레이스 제거 | 동일 |
| 엔진 내부 비용의 특징 | 락/로그 기반 + 레코드 잠금 비용 | 새 버전 생성 + vacuum 비용/패턴 영향 |

---

## 9. 결론: DB-CAS가 좌석 선점에 적합한 이유

좌석 선점은 결국 "1좌석 1유저"가 핵심이다. DB-CAS는 이를 다음 방식으로 만족시킨다.

- "AVAILABLE이면 RESERVED로 바꾼다"를 단일 원자 연산(SQL 한 방)으로 만든다
- 동시에 들어오는 N명 중 정확히 1명만 `updated=1`을 받고
- 나머지는 `updated=0`으로 빠르게 실패 처리할 수 있다
- 애플리케이션이 레이스를 직접 다루지 않고 (SELECT→UPDATE 사이 구멍 제거), DB가 제공하는 트랜잭션/락/MVCC 메커니즘에 위임한다

---

## 마무리

OS 동기화 개념(Mutex, Semaphore, 대기 큐)이 DB 엔진 내부에서 어떻게 활용되는지 살펴보았다. DB-CAS는 CPU의 CAS 명령어처럼 완전히 lock-free한 것은 아니지만, 애플리케이션 레벨에서 레이스 컨디션을 제거하고 동시성 제어를 DB에 위임하는 효과적인 패턴이다.
