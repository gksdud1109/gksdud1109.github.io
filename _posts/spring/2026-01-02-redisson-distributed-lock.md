---
title: "Redisson 분산 락으로 좌석 선택 동시성 제어하기"
date: 2026-01-02 12:00:00 +0900
categories: [Spring]
tags: [spring, redis, redisson, distributed-lock, concurrency]
---

## 개요

티켓팅 서비스에서 좌석 선택은 전형적인 **경합(competition) 상황**이다. VIP 1번 좌석에 1000명이 동시에 클릭하면, DB에서 AVAILABLE → RESERVED로 바꾸는 과정에서 충돌이 발생한다.

DB의 낙관적 락(@Version)만으로 처리하면 대부분 요청이 OptimisticLockException으로 실패하고, 사용자 경험이 매우 나빠진다. 이 글에서는 **Redis 기반 Redisson 분산 락**으로 경합을 흡수하고, **DB 조건부 UPDATE**로 최종 무결성을 보장하는 구조를 설명한다.

---

## 1. 좌석 선택의 문제

- VIP 1번 좌석에 1000명이 동시에 클릭
- DB에서 AVAILABLE → RESERVED 로 바꾸는 과정에서 충돌 발생
- 충돌을 DB 낙관적 락(@Version)만으로 처리하면:
  - 대부분 요청이 OptimisticLockException으로 실패
  - 재시도 없으면 사용자 경험이 매우 나빠짐
  - DB 트랜잭션 충돌이 많아지며 DB 부하도 증가

> **경합 자체를 DB로 보내지 않고, 먼저 Redis에서 "대기 줄 세우기(락)"를 한다**

---

## 2. Redisson 분산 락이란?

### 2-1. 분산 락의 의미

서버가 여러 대(혹은 여러 스레드)여도, 어떤 자원에 대해 동시에 접근하지 못하도록 막는 락이다.

| 환경 | 방법 |
|------|------|
| 단일 서버 | synchronized / ReentrantLock |
| 다중 서버 | **Redis 같은 외부 저장소 필요** |

Redisson은 Redis를 이용해서 분산 환경에서도 동작하는 Lock API를 제공한다.

### 2-2. 락 키

좌석 하나(Seat 1개)가 동시 접근의 최소 단위이므로, **Seat 단위로 락**을 건다.

```java
seat:lock:{eventId}:{seatId}
예) seat:lock:3:12
```

---

## 3. 코드 흐름

### 3-1. SeatSelectionService: 락 획득 → 트랜잭션 실행

```java
public Ticket selectSeatAndCreateTicket(Long eventId, Long seatId, Long userId) {
    String lockKey = generateSeatLockKey(eventId, seatId);
    RLock lock = redissonClient.getLock(lockKey);

    try {
        boolean acquired = lock.tryLock(LOCK_WAIT_TIME, LOCK_LEASE_TIME, TimeUnit.SECONDS);
        if (!acquired) {
            throw new ErrorException(SeatErrorCode.SEAT_LOCK_ACQUISITION_FAILED);
        }

        return executeSelectSeat(eventId, seatId, userId);

    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        throw new ErrorException(SeatErrorCode.SEAT_LOCK_INTERRUPTED);
    } finally {
        if (lock.isHeldByCurrentThread()) {
            lock.unlock();
        }
    }
}
```

**핵심 포인트:**

**1) 락 키를 "좌석 단위"로 생성**
```java
seat:lock:{eventId}:{seatId}
```
- 같은 seatId면 동일 락을 공유 → 동시 요청이 줄 서게 된다

**2) tryLock(waitTime, leaseTime)**
- waitTime: 락을 얻기 위해 기다리는 최대 시간
- leaseTime: 락을 얻으면 최대 보유 시간 (시간 지나면 자동 해제)
- 3초 동안 기다렸는데 락을 못 얻으면 바로 실패 처리

**3) 락을 잡은 뒤에만 DB 트랜잭션 수행**
- 락을 못 잡은 요청은 DB로 내려가지 않으므로 **DB를 보호**

### 3-2. executeSelectSeat: 실제 비즈니스 트랜잭션

```java
@Transactional
protected Ticket executeSelectSeat(Long eventId, Long seatId, Long userId) {
    // 대기열 진입 검증
    if (!queueEntryReadService.isUserEntered(eventId, userId)) {
        throw new ErrorException(SeatErrorCode.NOT_IN_QUEUE);
    }

    // Draft Ticket을 "항상 1개만" 유지
    Ticket ticket = ticketService.getOrCreateDraft(eventId, userId);
    Seat oldSeat = ticket.getSeat();

    // 새 좌석 예약
    Seat newSeat = seatService.reserveSeat(eventId, seatId, userId);

    // 티켓에 새 좌석 할당
    ticket.assignSeat(newSeat);

    // 이전 좌석 해제 (새 좌석 확보 후에만)
    if (oldSeat != null) {
        seatService.markSeatAsAvailable(oldSeat);
    }

    return ticket;
}
```

**가장 중요한 안전 순서:**
1. 새 좌석 확보 (RESERVED 성공)
2. 티켓에 새 좌석 할당
3. 이전 좌석 해제

### 3-3. SeatService.reserveSeat: DB에서 최종 무결성 보장

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

**Repository 쿼리:**

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

**핵심 포인트:**

**1) 조건부 UPDATE로 원자적 상태 변경**
- AVAILABLE일 때만 RESERVED로 변경
- 락이 있더라도(혹은 락이 꼬이더라도) **DB는 이 조건으로 최종적으로 1명만 RESERVED 성공**

**2) update 결과(updated==0)면 상태를 확인해 실패 원인 분리**
- SOLD라서 실패인지
- 이미 RESERVED라서 실패인지
- 기타 경합인지
- 클라이언트에 다른 메시지 전달 가능

**3) 상태 변경 후 WebSocket 이벤트 발행**
- 실시간 좌석 UI 갱신에 사용

---

## 4. Redisson 설정

```java
@Bean
public RedissonClient redissonClient() {
    Config config = new Config();
    String address = "redis://" + host + ":" + port;

    config.useSingleServer()
        .setAddress(address)
        .setPassword(password.isBlank() ? null : password)
        .setTimeout(timeout)
        .setConnectTimeout(timeout)
        .setRetryAttempts(0)   // 재시도 없음
        .setRetryInterval(0);

    return Redisson.create(config);
}
```

**핵심: fast-fail 전략**
- Redis 장애/지연 시 재시도(=대기)하지 않는다
- 락이 느려지면 요청이 쌓이며 DB까지 같이 죽을 수 있기 때문

> Redis가 죽으면 좌석 선택은 실패시키고, 사용자는 재시도한다

---

## 5. 장점과 Trade-off

### 장점

| 항목 | 설명 |
|------|------|
| DB 충돌 감소 | 좌석 경합을 Redis 락으로 흡수 |
| 최종 무결성 | DB에서 원자적 조건 업데이트로 보장 |
| DB 보호 | 락 획득 실패 시 DB 접근 자체를 줄임 |
| 확장성 | 좌석 단위라 다른 좌석은 병렬 처리 가능 |

### Trade-off

| 항목 | 설명 |
|------|------|
| Redis 의존도 | Redis 장애 시 좌석 선택 불가 |
| leaseTime 조절 필요 | 트랜잭션이 길어질 때 위험할 수 있음 |

---

## 6. 운영/관측 포인트

- 락 획득 실패율 (SEAT_LOCK_ACQUISITION_FAILED)
- 락 대기 시간 증가 여부
- DB 커넥션 풀 대기 시간
- 좌석 예약 성공률/실패율 (RESERVED/SOLD/CONCURRENCY)
- WebSocket 전파 성공률

---

## 정리

1. **Redisson 분산 락**으로 경합을 Redis에서 흡수
2. **DB 조건부 UPDATE**로 최종 무결성 보장
3. 두 단계 방어로 **실패율 감소, DB 부하 감소**
4. **fast-fail 전략**으로 장애 전파 방지

---

## 참고

- [풀필먼트 입고 서비스팀에서 분산락을 사용하는 방법 - Spring Redisson](https://helloworld.kurly.com/blog/distributed-redisson-lock/)
- [[Spring] Redis(Redisson) 분산락을 활용하여 동시성 문제 해결하기](https://velog.io/@juhyeon1114/Spring-RedisRedisson-%EB%B6%84%EC%82%B0%EB%9D%BD%EC%9D%84-%ED%99%9C%EC%9A%A9%ED%95%98%EC%97%AC-%EB%8F%99%EC%8B%9C%EC%84%B1-%EB%AC%B8%EC%A0%9C-%ED%95%B4%EA%B2%B0%ED%95%98%EA%B8%B0)
