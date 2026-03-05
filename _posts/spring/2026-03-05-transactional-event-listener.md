---
title: "트랜잭션 커밋 이후에만 WebSocket을 발행하라 — @TransactionalEventListener와 애플리케이션 레벨 EDA"
date: 2026-03-05 14:00:00 +0900
categories: [Spring]
tags: [spring, event-listener, websocket, transaction, eda, waitfair, transactional]
pin: true
---

> "좌석 예약이 성공했습니다"라는 WebSocket 알림이 날아갔는데, DB에는 실패로 기록되어 있다면?

티켓팅 서비스를 개발하면서 이 질문을 진지하게 마주했다. 결론부터 말하면 `@TransactionalEventListener(AFTER_COMMIT)` 하나로 해결했는데, 그 과정에서 **트랜잭션 생명주기와 부가 작업(Side Effect)의 관계**를 제대로 이해하게 되었다.

---

## 배경: 실시간 좌석 상태가 필요한 티켓팅 서비스

WaitFair는 추첨제 대기열 기반의 티켓팅 플랫폼이다. 여러 사용자가 동시에 같은 좌석을 선점하려 하기 때문에 **좌석 상태(AVAILABLE / RESERVED / SOLD)가 실시간으로 변한다**. 다른 사용자의 좌석 선택이 내 화면에도 즉시 반영되어야 하고, 이를 위해 STOMP WebSocket 브로드캐스팅을 사용하고 있다.

문제는 이 WebSocket 발행을 **어디서, 어느 시점에** 하느냐였다.

---

## 1단계 — 가장 단순한 구현: 한 메서드 안에 다 넣기

처음에는 가장 단순하게 생각했다. 좌석 상태를 DB에 업데이트하고, 바로 아래에서 WebSocket도 발행하면 되지 않을까?

```java
@Transactional
public Seat reserveSeat(Long eventId, Long seatId, Long userId) {
    // 1. DB 업데이트
    int updated = seatRepository.updateSeatStatusIfMatch(...);

    // 2. 바로 WebSocket 발행
    simpMessagingTemplate.convertAndSend("/topic/events/" + eventId + "/seats", message);

    return seat;
}
```

동작은 한다. 하지만 두 가지 심각한 문제가 숨어 있었다.

### 문제 1: 단일 책임 원칙(SRP) 위배

`SeatService`는 좌석 도메인의 상태를 관리하는 서비스다. 그런데 `SimpMessagingTemplate`이라는 인프라 레이어 의존성이 핵심 도메인 코드에 직접 들어오면서 두 가지 책임이 뒤섞였다. 테스트를 작성할 때도 WebSocket 관련 Mock이 함께 필요해졌다.

### 문제 2: 트랜잭션 롤백 시 데이터 불일치 (치명적)

더 큰 문제가 있다. `@Transactional` 메서드 안에서 WebSocket을 먼저 발행하면, 이후 예외가 발생해서 **DB 트랜잭션이 롤백되어도 WebSocket은 이미 날아간 상태**다.

```
[실행 순서]
1. DB UPDATE 실행 (아직 commit 전)
2. WebSocket 발행 → 프론트엔드: "A 좌석 RESERVED!" 표시
3. 이후 로직에서 예외 발생
4. 트랜잭션 롤백 → DB: A 좌석은 여전히 AVAILABLE
5. 결과: 프론트는 RESERVED, DB는 AVAILABLE → 상태 불일치
```

예약 롤백이 발생했는데 사용자 화면에는 이미 "예약 완료" 상태로 보이는 상황. 티켓팅 서비스에서 이건 치명적이다.

---

## 2단계 — 결합도 해소: Spring Event Bus 도입

해결 방향은 분명했다. **비즈니스 로직(좌석 상태 변경)과 부가 작업(WebSocket 발행)을 분리**하는 것이다.

Spring의 `ApplicationEventPublisher`를 활용하면 서비스 간 직접 의존 없이 이벤트를 발행할 수 있다.

### 구조 변경 후 흐름

```
SeatService
  └─ updateSeatStatusIfMatch() [CAS 원자적 업데이트]
  └─ eventPublisher.publishEvent(SeatStatusMessage)
       │
       ▼
  [Spring Event Bus]
       │
       ▼
  SeatEventHandler
  └─ handleSeatStatus(SeatStatusMessage)
  └─ seatWebSocketPublisher.publish(msg)
       │
       ▼
  SeatWebSocketPublisher
  └─ simpMessagingTemplate.convertAndSend(...)
```

이제 `SeatService`는 WebSocket의 존재를 전혀 모른다. 단지 이벤트를 발행할 뿐이다.

### 이벤트 페이로드

```java
@Builder
public record SeatStatusMessage(
    Long eventId,
    Long seatId,
    String seatCode,
    String currentStatus,
    int price,
    String grade
) {
    public static SeatStatusMessage from(Seat seat) {
        return new SeatStatusMessage(
            seat.getEvent().getId(),
            seat.getId(),
            seat.getSeatCode(),
            seat.getSeatStatus().name(),
            seat.getPrice(),
            seat.getGrade().name()
        );
    }
}
```

Java 16 record를 사용해 불변 이벤트 객체로 설계했다. 이벤트는 한 번 생성되면 수정되지 않아야 하므로 record가 적합하다.

### SeatService — 이벤트 발행만 담당

```java
@Service
@RequiredArgsConstructor
public class SeatService {
    private final SeatRepository seatRepository;
    private final EventPublisher eventPublisher;
    private final BusinessMetrics businessMetrics;

    @Transactional
    public Seat reserveSeat(Long eventId, Long seatId, Long userId) {
        // CAS 기반 원자적 상태 변경 (AVAILABLE -> RESERVED)
        int updated = seatRepository.updateSeatStatusIfMatch(
            eventId, seatId,
            SeatStatus.AVAILABLE, SeatStatus.RESERVED
        );

        if (updated == 0) {
            businessMetrics.seatConcurrencyConflict(eventId);
            Seat current = seatRepository.findByEventIdAndId(eventId, seatId)
                .orElseThrow(() -> new ErrorException(SeatErrorCode.NOT_FOUND_SEAT));

            if (current.getSeatStatus() == SeatStatus.SOLD) {
                businessMetrics.seatSelectionFailure(eventId, "ALREADY_SOLD");
                throw new ErrorException(SeatErrorCode.SEAT_ALREADY_SOLD);
            }
            if (current.getSeatStatus() == SeatStatus.RESERVED) {
                businessMetrics.seatSelectionFailure(eventId, "ALREADY_RESERVED");
                throw new ErrorException(SeatErrorCode.SEAT_ALREADY_RESERVED);
            }
            throw new ErrorException(SeatErrorCode.SEAT_CONCURRENCY_FAILURE);
        }

        Seat seat = seatRepository.findByEventIdAndId(eventId, seatId)
            .orElseThrow(() -> new ErrorException(SeatErrorCode.NOT_FOUND_SEAT));

        // 이벤트 발행 — WebSocket에 대해서는 아무것도 모른다
        eventPublisher.publishEvent(SeatStatusMessage.from(seat));
        businessMetrics.seatSelectionSuccess(eventId);
        return seat;
    }
}
```

> 참고: `updateSeatStatusIfMatch()`는 `UPDATE seat SET status = 'RESERVED' WHERE id = ? AND status = 'AVAILABLE'` 형태의 원자적 쿼리다. 반환값이 0이면 다른 트랜잭션이 먼저 상태를 변경한 것으로 CAS 실패를 의미한다.

---

## 3단계 — 핵심: @EventListener가 아닌 @TransactionalEventListener를 써야 하는 이유

결합도 분리까지는 `@EventListener`로도 충분하다. 그런데 문제 2(트랜잭션 롤백 시 불일치)는 아직 해결되지 않았다.

```java
// 이렇게 쓰면 여전히 위험하다
@EventListener
public void handleSeatStatus(SeatStatusMessage msg) {
    publisher.publish(msg);  // 트랜잭션 커밋 전에 실행될 수 있음
}
```

`@EventListener`는 `eventPublisher.publishEvent()`가 호출되는 **즉시** 실행된다. 즉, DB 트랜잭션이 커밋되기 전에 WebSocket이 나간다.

### @TransactionalEventListener의 동작 원리

Spring은 `@TransactionalEventListener`를 선언한 메서드에 대해 이벤트를 **트랜잭션 동기화 큐(Transaction Synchronization)**에 등록해두고, 트랜잭션의 특정 단계에 맞춰 실행한다.

```
publishEvent() 호출
    │
    ▼
트랜잭션 동기화 큐에 이벤트 등록 (실행 보류)
    │
    ▼
@Transactional 메서드 정상 종료
    │
    ▼
DB COMMIT 완료
    │
    ▼ [AFTER_COMMIT 단계]
SeatEventHandler.handleSeatStatus() 실행
    │
    ▼
WebSocket 발행
```

롤백이 발생하면 큐에 있던 이벤트는 그냥 폐기된다.

### 실제 핸들러 코드

```java
@Slf4j
@Component
@RequiredArgsConstructor
public class SeatEventHandler {
    private final SeatWebSocketPublisher publisher;

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handleSeatStatus(SeatStatusMessage msg) {
        log.debug("SEAT_EVENT_RECEIVED eventId={} seatId={} currentStatus={}",
            msg.eventId(), msg.seatId(), msg.currentStatus());
        publisher.publish(msg);
    }
}
```

`phase = TransactionPhase.AFTER_COMMIT` 한 줄이 핵심이다. 이 설정으로 보장되는 것과 그렇지 않은 것을 명확히 구분해야 한다.

| 보장되는 것 | 보장되지 않는 것 |
|---|---|
| DB 커밋 성공 후에만 WebSocket 발행 | WebSocket 전송 자체의 성공 여부 |
| 롤백 시 WebSocket 미발행 | 메시지 유실 없는 전달 (이건 메시징 레이어 문제) |
| 프론트 상태 = DB 상태 일치 | 네트워크 단절 시 재전송 |

WebSocket 전송 실패까지 보장하려면 별도의 메시징 레이어(예: Redis Pub/Sub, Kafka)가 필요하다. 이 프로젝트에서는 WebSocket 미수신 시 사용자가 다시 조회하는 방식으로 처리했다.

### WebSocket 발행

```java
@Slf4j
@Service
@RequiredArgsConstructor
public class SeatWebSocketPublisher {
    private final SimpMessagingTemplate messagingTemplate;

    public void publish(SeatStatusMessage msg) {
        String destination = "/topic/events/" + msg.eventId() + "/seats";
        log.debug("WS_PUBLISH destination={} seatId={} status={}",
            destination, msg.seatId(), msg.currentStatus());
        messagingTemplate.convertAndSend(destination, msg);
    }
}
```

STOMP의 `/topic` prefix를 사용해 특정 이벤트의 좌석 채널을 구독 중인 모든 사용자에게 브로드캐스팅한다.

---

## 확장성: 핵심 코드 한 줄 변경 없이 기능 추가

이 구조의 실질적인 이점은 **OCP(개방-폐쇄 원칙)** 적용이다.

WaitFair에서는 좌석 상태 변경 시 알림 이벤트도 함께 발행해야 했다. `SeatService` 코드는 한 줄도 건드리지 않고 핸들러만 추가했다.

```java
// 기존 WebSocket 핸들러 (변경 없음)
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void handleSeatStatus(SeatStatusMessage msg) {
    publisher.publish(msg);
}

// 새로 추가된 알림 핸들러
@Async
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void handleNotification(SeatStatusMessage msg) {
    notificationService.send(msg);
}
```

> 주의: `@Async + @TransactionalEventListener` 조합에서 새 핸들러 내부에서 DB 작업이 필요하다면 `@Transactional(propagation = REQUIRES_NEW)`를 명시해야 한다. AFTER_COMMIT 단계는 원래 트랜잭션이 종료된 상태이기 때문에 `REQUIRED`만으로는 새 트랜잭션이 생성되지 않을 수 있다.

---

## 더 넓은 시야: Micro EDA와 Macro EDA

이 패턴을 적용하면서 EDA를 두 레벨로 이해하게 됐다.

| 구분 | Micro EDA (이 포스팅) | Macro EDA |
|---|---|---|
| 범위 | 단일 애플리케이션 내부 | 서비스 간 / 시스템 간 |
| 기술 | Spring Event Bus | Kafka, RabbitMQ, AWS SNS/SQS |
| 목적 | 도메인 간 결합도 완화 | 서비스 간 비동기 통신 |
| 내구성 | 메모리 기반 (프로세스 죽으면 소실) | 디스크 기반 (Replay 가능) |
| 분산 추적 | MDC (단일 서버 내 요청 추적) | Jaeger, Zipkin, Grafana Tempo |

Spring Event는 단일 애플리케이션 내에서 **도메인 로직과 부가 로직의 결합을 끊는** 도구다. Kafka 같은 외부 메시지 브로커가 **서비스 간 통신 복잡도를 낮추는** 것과 같은 철학이지만 레벨이 다르다.

두 레벨을 모두 이해하면 "EDA를 안다"는 말의 의미가 달라진다. 단순히 Kafka를 써봤다는 게 아니라, **결합도를 낮춘다는 철학을 코드 레벨부터 아키텍처 레벨까지 적용할 줄 안다**는 뜻이 된다.

---

## 정리

`@TransactionalEventListener(phase = AFTER_COMMIT)`를 도입하면서 얻은 것:

1. **트랜잭션 정합성 보장** — DB 커밋 확정 후에만 WebSocket 발행, 롤백 시 자동 폐기
2. **도메인 로직 순수성** — `SeatService`는 WebSocket, 알림, 메트릭에 대해 아무것도 모른다
3. **OCP 준수** — 새 부가 기능은 핸들러 추가만으로 확장 가능

한 줄짜리 애노테이션이지만, 트랜잭션 생명주기를 이해하지 못하면 쓸 수 없다. `@EventListener`와의 차이를 모르고 쓰다가 데이터 불일치를 만나는 것보다, 처음부터 **"커밋 이후에만 Side Effect를 실행한다"** 는 원칙을 코드에 명시하는 게 낫다.

---

*참고: WaitFair 프로젝트의 좌석 동시성 제어(CAS 기반 원자적 업데이트)에 대해서는 별도 포스팅에서 다룰 예정이다.*
