---
title: "Spring EventListener 기반 WebSocket 실시간 브로드캐스트 구현"
date: 2025-12-08 12:00:00 +0900
categories: [Spring]
tags: [spring, websocket, eventlistener, stomp, realtime]
---

## 개요

좌석 예약, 실시간 알림 등 상태 변경을 클라이언트에 즉시 전파해야 하는 경우, **Spring Event System**과 **WebSocket**을 조합하면 깔끔하게 구현할 수 있다. 이 글에서는 Spring EventListener 기반의 WebSocket 브로드캐스트 구현 방법과 커스텀 Broadcaster 방식과의 비교를 정리한다.

---

## 1. 전체 흐름

```
SeatService.selectSeat()
        ↓
EventPublisher.publishEvent(new SeatStatusMessage(...))
        ↓
Spring Event System
        ↓
@EventListener 메서드 호출 (SeatStatusEventHandler)
        ↓
SeatWebSocketPublisher.publish(message)
        ↓
웹소켓 브로드캐스트 (convertAndSend)
```

---

## 2. Spring EventListener 방식 구현

### 2.1 SeatService - 이벤트 발행

```java
@Service
@RequiredArgsConstructor
public class SeatService {

    private final SeatRepository seatRepository;
    private final EventPublisher eventPublisher;

    @Transactional
    public Seat selectSeat(Long eventId, Long seatId, Long userId) {

        Seat seat = seatRepository.findByEventIdAndId(eventId, seatId)
                .orElseThrow(() -> new ErrorException(SeatErrorCode.NOT_FOUND_SEAT));

        seat.markAsReserved();

        Seat saved = seatRepository.save(seat);

        // Spring 이벤트 발행
        eventPublisher.publishEvent(new SeatStatusMessage(
            eventId,
            seatId,
            "RESERVED",
            seat.getPrice(),
            seat.getGrade().name()
        ));

        return saved;
    }
}
```

### 2.2 EventPublisher - Spring Event 시스템에 발행

```java
@Component
@RequiredArgsConstructor
public class EventPublisher {
    private final ApplicationEventPublisher publisher;

    public <T> void publishEvent(T event) {
        publisher.publishEvent(event);
    }
}
```

### 2.3 EventListener - 이벤트 자동 수신

```java
@Component
@RequiredArgsConstructor
public class SeatEventHandler {

    private final SeatWebSocketPublisher publisher;

    @EventListener
    public void handleSeatStatus(SeatStatusMessage msg) {
        publisher.publish(msg);
    }
}
```

### 2.4 WebSocketPublisher - 실제 브로드캐스트

```java
@Service
@RequiredArgsConstructor
public class SeatWebSocketPublisher {

    private final SimpMessagingTemplate messagingTemplate;

    public void publish(SeatStatusMessage msg) {
        messagingTemplate.convertAndSend(
                "/topic/events/" + msg.eventId() + "/seats",
                msg
        );
    }
}
```

---

## 3. 커스텀 Broadcaster 인터페이스 방식

Spring Event를 사용하지 않고 직접 인터페이스를 정의하여 호출하는 방식도 있다.

### 3.1 Broadcaster 인터페이스

```java
public interface Broadcaster<T> {
    void onCreated(T event);
}
```

### 3.2 WebSocket Publisher 구현체

```java
@Service
@RequiredArgsConstructor
public class SeatWebSocketPublisher implements Broadcaster<SeatStatusMessage> {

    private final SimpMessagingTemplate simpMessagingTemplate;

    @Override
    public void onCreated(SeatStatusMessage msg) {
        simpMessagingTemplate.convertAndSend(
            "/topic/events/" + msg.eventId() + "/seats",
            msg
        );
    }
}
```

### 3.3 SeatService에서 직접 호출

```java
@Transactional
public Seat selectSeat(Long eventId, Long seatId, Long userId) {
    Seat seat = ...;

    seat.markAsReserved();
    seatRepository.save(seat);

    // 직접 Broadcaster 호출 필요
    broadcaster.onCreated(
        new SeatStatusMessage(eventId, seatId, "RESERVED", seat.getPrice(), seat.getGrade().name())
    );

    return seat;
}
```

### 3.4 Dispatcher를 추가하면 Spring Event와 결합 가능

```java
@Component
@RequiredArgsConstructor
public class BroadcasterDispatcher {

    private final List<Broadcaster<SeatStatusMessage>> broadcasters;

    @EventListener
    public void handle(SeatStatusMessage msg) {
        broadcasters.forEach(b -> b.onCreated(msg));
    }
}
```

---

## 4. 두 방식 비교

| 비교 항목 | Spring EventListener 방식 | Broadcaster 방식 |
|----------|--------------------------|-----------------|
| 이벤트 전달 | Spring이 자동 처리 | 직접 호출 or Dispatcher 필요 |
| 코드 복잡도 | 낮음 | 높음 |
| 유지보수성 | 매우 높음 | 중간 (구조가 커지면 어려움) |
| 팀원이 이해하기 | 쉬움 | 어려울 수 있음 |
| 확장성 | 뛰어남 (Listener 여러 개 추가 가능) | 인터페이스마다 Dispatcher 필요 |
| 결합도 | SeatService ↛ WebSocketPublisher (낮음) | SeatService → Broadcaster (높음) |

---

## 5. Spring EventListener 방식의 장점

### 낮은 결합도

```java
// Service는 이벤트만 발행
eventPublisher.publishEvent(new SeatStatusMessage(...));

// 누가 받는지 Service는 모름
// WebSocket, 알림, 로깅 등 여러 Listener가 받을 수 있음
```

### 쉬운 확장

```java
@EventListener
public void handleSeatStatus(SeatStatusMessage msg) {
    publisher.publish(msg);  // WebSocket
}

@EventListener
public void sendNotification(SeatStatusMessage msg) {
    notificationService.send(msg);  // 알림
}

@EventListener
public void logSeatChange(SeatStatusMessage msg) {
    log.info("Seat changed: {}", msg);  // 로깅
}
```

### 테스트 용이

- Service 테스트 시 이벤트 발행 여부만 확인
- Listener 테스트는 별도로 진행

---

## 6. WebSocket 설정

```java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureMessageBroker(MessageBrokerRegistry config) {
        config.enableSimpleBroker("/topic");
        config.setApplicationDestinationPrefixes("/app");
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOriginPatterns("*")
                .withSockJS();
    }
}
```

---

## 7. 클라이언트 구독 예시

```javascript
const socket = new SockJS('/ws');
const stompClient = Stomp.over(socket);

stompClient.connect({}, function(frame) {
    // 특정 이벤트의 좌석 상태 구독
    stompClient.subscribe('/topic/events/1/seats', function(message) {
        const seatStatus = JSON.parse(message.body);
        console.log('Seat updated:', seatStatus);
        // UI 업데이트
    });
});
```

---

## 정리

1. **Spring Event System**을 활용하면 Service와 WebSocket Publisher 간 결합도를 낮출 수 있음
2. **@EventListener**로 이벤트를 수신하여 WebSocket 브로드캐스트 수행
3. 커스텀 Broadcaster 방식보다 **유지보수성과 확장성이 뛰어남**
4. 여러 Listener를 추가하여 **알림, 로깅 등 다양한 처리**를 쉽게 확장 가능
5. **SimpMessagingTemplate**의 `convertAndSend`로 특정 토픽에 메시지 전송

---

## 참고

- [Spring WebSocket 공식 문서](https://docs.spring.io/spring-framework/docs/current/reference/html/web.html#websocket)
- [STOMP over WebSocket](https://stomp.github.io/)
- [Spring Events](https://docs.spring.io/spring-framework/docs/current/reference/html/core.html#context-functionality-events)
