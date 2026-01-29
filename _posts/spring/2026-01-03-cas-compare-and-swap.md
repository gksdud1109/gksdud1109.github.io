---
title: "CAS(Compare-And-Swap) - Optimistic Lock의 한계와 해결책"
date: 2026-01-03 12:00:00 +0900
categories: [Spring]
tags: [spring, cas, concurrency, optimistic-lock, database]
---

## 개요

좌석 선택 기능에서 `@Version` 기반 Optimistic Lock을 사용했는데, 고부하 환경에서 **예상치 못한 500 에러**가 발생했다. 이 글에서는 Optimistic Lock의 한계와, **CAS(Compare-And-Swap) 패턴**으로 문제를 해결한 과정을 정리한다.

---

## 1. CAS란?

**CAS: Compare-And-Swap**

현재 내가 기대한 값일 때만 변경하겠다는 **원자적 연산**이다.

```java
if (current == expected) {
    current = newValue;
} else {
    fail;
}
```

위와 같은 패턴을 **락 없이 단일 원자 연산**으로 수행한다.

---

## 2. DB에서의 CAS

```sql
UPDATE seats
SET seat_status = 'RESERVED'
WHERE id = ?
  AND seat_status = 'AVAILABLE';
```

- 조건이 만족 → row 1개 업데이트
- 이미 다른 트랜잭션이 바꿨으면 row 0개 업데이트

> **업데이트 된 row 개수가 CAS의 성공/실패 신호**

```java
int updated = seatRepository.updateSeatStatusIfMatch(
    eventId, seatId,
    SeatStatus.AVAILABLE, SeatStatus.RESERVED
);
```

---

## 3. 좌석 선택에서 CAS를 선택한 이유

### 좌석 선택의 문제 본질

**여러 요청 중 딱 1명만 성공해야 하는 경쟁 문제**

| 방식 | 문제점 |
|------|--------|
| Pessimistic Lock (SELECT ... FOR UPDATE) | 대기 발생, tail latency 증가 |
| Distributed Lock (Redis) | 네트워크 왕복 + 락 경합 |
| Optimistic Lock (@Version) | flush/commit 시점 예외, 500 위험 |

### CAS가 딱 맞는 이유

- 좌석 상태는 단순한 상태 전이
- 이미 누가 잡았는지만 알면 됨
- 실패해도 **정상적인 경쟁 실패** (409 응답 가능)

> **좌석 선택 = CAS가 가장 잘 맞는 도메인**

---

## 4. 기존 구현의 문제: OptimisticLockException

### 기존 코드

```java
@Transactional
public Seat reserveSeat(Long eventId, Long seatId, Long userId) {
    Seat seat = seatRepository.findByEventIdAndId(eventId, seatId)
        .orElseThrow(() -> new ErrorException(SeatErrorCode.NOT_FOUND_SEAT));

    try {
        seat.markAsReserved();
        Seat saved = seatRepository.save(seat);  // 예외가 여기서 안 터지는 경우 발생
        eventPublisher.publishEvent(SeatStatusMessage.from(saved));
        return saved;
    } catch (ObjectOptimisticLockingFailureException ex) {
        throw new ErrorException(SeatErrorCode.SEAT_CONCURRENCY_FAILURE);
    }
}
```

### 문제 상황

catch 블록에서 예외가 처리되도록 했지만, 고부하 환경에서 테스트했을 때:
- Service 내부 트랜잭션 속 Dirty Checking에서 정상 실패가 던져지지 않음
- 컨트롤러, 서비스 로직, **트랜잭션 경계 바깥 flush/commit 시점에 500 에러** 발생

> 실패가 아니라 **서버 에러로 보이게 됨** → Optimistic Lock의 한계

### 예외가 save()에서 터지지 않는 이유

- Hibernate Dirty Checking은 **트랜잭션 commit 시점**에 UPDATE 실행
- 이때 @Version mismatch를 감지하면 **try-catch 범위를 이미 벗어남**
- Spring TransactionInterceptor → Hibernate flush → DataAccessException → GlobalExceptionHandler → **500 에러!**

---

## 5. CAS 방식으로 해결

### 변경된 코드

```java
@Transactional
public Seat reserveSeat(Long eventId, Long seatId, Long userId) {
    int updated = seatRepository.updateSeatStatusIfMatch(
        eventId, seatId,
        SeatStatus.AVAILABLE, SeatStatus.RESERVED
    );

    if (updated == 0) {
        Seat current = seatRepository.findByEventIdAndId(eventId, seatId)
            .orElseThrow(() -> new ErrorException(SeatErrorCode.NOT_FOUND_SEAT));

        if (current.getSeatStatus() == SeatStatus.SOLD) {
            throw new ErrorException(SeatErrorCode.SEAT_ALREADY_SOLD);
        }
        if (current.getSeatStatus() == SeatStatus.RESERVED) {
            throw new ErrorException(SeatErrorCode.SEAT_ALREADY_RESERVED);
        }
        throw new ErrorException(SeatErrorCode.SEAT_CONCURRENCY_FAILURE);
    }

    Seat reserved = seatRepository.findByEventIdAndId(eventId, seatId)
        .orElseThrow(() -> new ErrorException(SeatErrorCode.NOT_FOUND_SEAT));

    eventPublisher.publishEvent(SeatStatusMessage.from(reserved));
    return reserved;
}
```

### Repository 쿼리

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
int updateSeatStatusIfMatch(Long eventId, Long seatId, SeatStatus fromStatus, SeatStatus toStatus);
```

### CAS 방식에서 문제가 없는 이유

```java
int updated = updateSeatStatusIfMatch(...);
if (updated == 0) {
    // 의미 있는 실패
}
```

| 항목 | Optimistic Lock | CAS |
|------|-----------------|-----|
| 실패 시점 | flush/commit 시점 | **UPDATE 직후** |
| 실패 위치 | 트랜잭션 경계 밖 | **서비스 로직 내부** |
| 실패 의미 | 예외 (500 위험) | **비즈니스 실패** (409 응답) |

> **500이 안 던져짐!**

---

## 6. 비교 요약

| 항목 | Optimistic Lock (@Version) | CAS (조건부 UPDATE) |
|------|---------------------------|---------------------|
| 실패 감지 시점 | commit 시점 | UPDATE 직후 |
| 예외 위치 | 트랜잭션 밖 | 서비스 로직 내부 |
| 에러 응답 | 500 (서버 에러) | 409 (경쟁 실패) |
| 실패 원인 분리 | 어려움 | 쉬움 (상태별 분기) |
| 적합한 상황 | 충돌이 드문 경우 | **경쟁이 많은 경우** |

---

## 정리

1. **Optimistic Lock의 한계**: flush/commit 시점에 예외가 발생하여 catch 불가
2. **CAS 패턴**: 조건부 UPDATE로 실패를 서비스 로직 내부에서 처리
3. **좌석 선택**처럼 경쟁이 많은 도메인에서는 **CAS가 가장 적합**
4. 실패 원인을 분리하여 **사용자에게 명확한 응답** 제공 가능

---

## 참고

- [CAS(Compare and Swap) 알고리즘에 관하여](https://gototech.tistory.com/2)
- [나는 몰랐던, 고성능 멀티쓰레드 동기화 기법 - CAS](https://velog.io/@joosing/high-performance-multithreaded-sync-techniques-compare-and-swap)
- [[Java] atomic과 CAS 알고리즘](https://steady-coding.tistory.com/568)
