---
title: "@TransactionalEventListener - 트랜잭션 커밋 이후 이벤트 발행하기"
date: 2025-12-20 12:00:00 +0900
categories: [Spring]
tags: [spring, transaction, event, transactionaleventlistener, websocket]
---

## 개요

티켓팅 서비스에서 결제가 완료되면 WebSocket을 통해 좌석 상태를 실시간으로 프론트엔드에 전달한다. 그런데 트랜잭션이 롤백되는 상황에서도 WebSocket 메시지가 먼저 전송되어 **DB 상태와 프론트 상태가 불일치**하는 문제가 발생할 수 있다.

이 글에서는 `@TransactionalEventListener`를 사용하여 **트랜잭션 커밋이 확정된 이후에만 이벤트를 발행**하는 방법과, 사용 시 주의해야 할 점들을 정리한다.

---

## 현재 구조

PaymentService를 보면 하나의 트랜잭션 안에 아래 흐름이 묶여 있다.

1. PG 결제 확인 (외부 I/O)
2. Order 상태 변경
3. Ticket 상태 전이 (DRAFT → PAID → ISSUED)
4. Seat 상태 변경 (RESERVED → SOLD)
5. Queue 완료 처리
6. 알림 이벤트 발행

### 특징

- 금전이 걸린 상태 전이
- 되돌리기 어려운 상태(좌석 SOLD, 티켓 ISSUED)
- 외부 시스템(PG) 연동
- 여러 도메인이 연쇄적으로 결합

기존 seat 단독으로 SeatService만의 짧은 트랜잭션으로 끝나는 가벼운 상태 알림이 아니다.

---

## 발생 가능한 문제

### 현재 구조의 문제점

```java
PaymentService.confirmPayment()   // @Transactional
 └─ ticketService.confirmPayment()
     └─ seatService.markSeatAsSold()
         └─ eventPublisher.publishEvent(SeatStatusMessage)  // 여기서 WebSocket 전송
```

- `seatService.markSeatAsSold()` 내부에서 `eventPublisher.publishEvent(SeatStatusMessage)` 호출
- 이 이벤트는 **트랜잭션 커밋 전에 실행될 수 있음**

### 문제 시나리오

1. Seat SOLD → WebSocket 전송
2. 직후 queueEntryProcessService에서 예외 발생
3. 트랜잭션 롤백
4. **DB 상태**: Seat는 SOLD 아님
5. **프론트 상태**: 이미 SOLD로 인식

> **결론**: 비즈니스 로직에서 커밋이 확정된 이후에 이벤트를 발행해야 한다.

---

## @TransactionalEventListener 적용

### @EventListener vs @TransactionalEventListener

**@EventListener** - 즉시 실행

```java
@EventListener
public void handleSeatStatus(SeatStatusMessage msg) {
    publisher.publish(msg);
}
```

- publishEvent() 호출 즉시, 같은 스레드에서 트랜잭션 커밋 전이라도 실행됨
- 앞선 문제 시나리오가 발생 가능

**@TransactionalEventListener(AFTER_COMMIT)** - 커밋 후 실행

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void handleSeatStatus(SeatStatusMessage msg) {
    publisher.publish(msg);
}
```

- publishEvent() 호출 시점에는 즉시 실행되지 않음
- Spring이 이벤트를 트랜잭션 동기화 큐에 저장
- Payment 트랜잭션이 정상 커밋되면 그때 실행
- **롤백되면 아예 실행되지 않음**

### 보장되는 것

| 항목 | 보장 여부 |
|------|----------|
| Payment 성공 시에만 WebSocket 발행 | O |
| 롤백 시 WebSocket 발행 안 함 | O |
| 프론트 상태 = DB 상태 일치 | O |
| WebSocket 전송 자체의 성공 | X (메시징 레이어 문제) |

---

## 주의할 점: AFTER_COMMIT에서 DB 변경

### 문제 상황

```java
@Transactional
public void savePost() {
    // ... 비즈니스 로직
    publishEvent(new PostSavedEvent());
}

@TransactionalEventListener(AFTER_COMMIT)
public void onPostSaved(PostSavedEvent event) {
    Post post = postRepository.findById(event.getPostId());
    post.changeTitle("New Title");
    postRepository.save(post);  // DB 반영 안 됨!
}
```

### 안 되는 이유

AFTER_COMMIT 시점의 상태:

| 항목 | 상태 |
|------|------|
| DB 트랜잭션 | 이미 종료 |
| 스프링 트랜잭션 동기화 컨텍스트 | 남아 있을 수 있음 |
| 영속성 컨텍스트(EntityManager) | 남아 있을 수 있음 |

- DB 트랜잭션은 이미 종료되었지만
- Spring은 "트랜잭션이 있다고 착각"할 수 있음
- 엔티티 상태 변경 → 1차 캐시만 변경
- flush / commit 불가 → **DB 반영 안 됨**

### 해결책: REQUIRES_NEW 사용

```java
@TransactionalEventListener(AFTER_COMMIT)
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void onPostSaved(PostSavedEvent event) {
    // 새로운 트랜잭션에서 실행됨
    Post post = postRepository.findById(event.getPostId());
    post.changeTitle("New Title");
    postRepository.save(post);  // 정상 동작
}
```

### 작업별 REQUIRES_NEW 필요 여부

| 작업 내용 | REQUIRES_NEW 필요 |
|-----------|-------------------|
| WebSocket 발행 | 불필요 |
| Kafka publish | 불필요 |
| Slack 알림 | 불필요 |
| 로그 기록 | 불필요 |
| 다른 테이블 UPDATE | **필요** |
| 감사 로그 저장 | **필요** |
| 통계 카운트 UPDATE | **필요** |

---

## @Async와 함께 사용할 때

### 코드 예시

```java
@Async
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void handleNotificationMessage(NotificationMessage message) {
    Notification notification = Notification.builder()
        .user(userRepository.findById(message.getUserId()).orElseThrow())
        .type(message.getNotificationType())
        .build();

    notificationRepository.save(notification);  // 정상 동작!
}
```

### @Async가 있으면 정상 동작하는 이유

**실제 실행 흐름:**

1. 원 트랜잭션 커밋
2. AFTER_COMMIT 이벤트 트리거
3. **@Async → 다른 스레드로 분리**
4. 다른 스레드에는:
   - 기존 영속성 컨텍스트 없음
   - 기존 트랜잭션 없음
5. notificationRepository.save() 호출
6. Spring이 **새 트랜잭션 생성** (REQUIRED)

> **결과적으로 REQUIRES_NEW처럼 동작**하지만, 이는 우연의 결과이므로 명시적으로 REQUIRES_NEW를 사용하는 것이 안전하다.

### 권장하는 안전한 구조

```java
@Async
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void handleNotificationMessage(NotificationMessage message) {
    // DB 작업이 필요한 경우
}
```

이 구조에서는:
- AFTER_COMMIT 이후 실행 보장
- 새로운 DB 트랜잭션 보장
- Async 유무와 무관하게 동작
- 더티 체킹 / flush / commit 정상 동작

---

## 정리

1. **트랜잭션 커밋 이후에 이벤트를 발행**하려면 `@TransactionalEventListener(AFTER_COMMIT)` 사용
2. AFTER_COMMIT 시점에는 DB 트랜잭션이 이미 종료됨
3. **DB 변경이 필요하면 REQUIRES_NEW를 명시**해야 함
4. @Async로 인해 우연히 동작하는 경우가 있지만, 이는 설계적으로 안전한 것이 아님

---

## 참고

- [Spring Event, @TransactionalEventListener 사용하기](https://wildeveloperetrain.tistory.com/246)
- [[Spring] @TransactionalEventListener(AFTER_COMMIT)에서 업데이트가 반영되지 않는 문제 해결](https://curiousjinan.tistory.com/entry/fixing-spring-transactionaleventlistener-after-commit-update-issue)
