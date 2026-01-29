---
title: "Payment V2 아키텍처 - PG 연동 결제 흐름과 장애 대응 전략"
date: 2026-01-04 12:00:00 +0900
categories: [Spring]
tags: [spring, payment, toss, architecture, transaction, circuit-breaker]
---

## 개요

PG(Toss Payments) 연동 결제 흐름의 전체 아키텍처, 트랜잭션 설계 이유, 장애 상황별 처리 방식, 그리고 각 클래스가 어떤 책임과 동작을 가져가는지 설명한다.

### 핵심 설계 목표

1. PG API 호출과 DB 트랜잭션을 분리
2. 외부 장애가 DB 트랜잭션을 오염시키지 않도록 설계
3. 결제 성공 / 실패를 각각 하나의 트랜잭션으로 처리
4. 상태 전이(order/ticket/seat/queue)가 항상 일관되게 유지되도록 보장

---

## 1. 전체 아키텍처

### 전체 결제 시퀀스

```
[Client]
  │
  │ 1️⃣ 주문 생성 요청
  ▼
POST /v2/orders
  │
  ▼
OrderService.v2_createOrder()
  │
  │  (V2_Order 생성, status=PENDING)
  ▼
V2_Order(orderId 발급)
  │
  │ 2️⃣ 결제창 오픈 (클라이언트)
  ▼
[Client → Toss 결제창]
  │
  │ 3️⃣ Toss 내부에서 결제 승인
  ▼
[Toss Payments]
  │
  │ 4️⃣ 결제 완료 후 redirect
  ▼
POST /v2/payments/confirm
  │
  ▼
PaymentService.v2_confirmPayment()
```

### 1-1. POST /v2/orders

- Ticket DRAFT 상태 검증
- 금액 검증 (seat.price == client amount)
- v2_order 생성
  - orderId(UUID)
  - ticket
  - amount
  - status=PENDING

### 1-2. Toss 결제창 호출

```json
{
  "orderId": "v2_order_id",
  "amount": 30000,
  "orderName": "콘서트 티켓"
}
```

- Toss에서 결제 진행
- 결제 완료 후 redirect URL로 이동
- 이때 paymentKey, orderId, amount가 포함되어야 함

### 1-3. POST /v2/payments/confirm

이후 상세 설명.

---

## 2. Payment 전체 구조

```
client
→ PaymentController
→ PaymentService(트랜잭션 X / 흐름 제어)
    - OrderService(중복 or pending 존재여부 검증 / Read Transaction)
    - TossPaymentService(PG호출 / Circuit Breaker)
    - PaymentTransactionService(Write Transaction 전담)
        - order
        - payment
        - ticket & seat
        - queue
        - eventpublish
        - 트랜잭션으로 위 다섯가지 처리 보장
```

---

## 3. PaymentTransactionService로 트랜잭션 분리한 이유

### 분리하지 않았을 때의 문제

```java
@Transactional
public void 결제컨펌() {
    PG_API_호출();  // 외부 의존성, 제어 불가
    Order 상태 변경;
    Ticket 발급;
}
```

| 문제 | 설명 |
|------|------|
| DB 커넥션 장시간 점유 | PG 타임아웃 등 장애 시 다른 요청이 밀림 |
| 전체 트랜잭션 롤백 | 외부 API 실패 시 전체 롤백 |
| 장애 전파 | DB 커넥션 등 한정된 자원 고갈 |
| 결합도 증가 | DB + 외부 시스템 결합 |

---

## 4. 결제 전체 흐름 (성공 시나리오)

### 4-1. Order 검증

```java
@Transactional(readOnly = true)
public Long v2_validateAndGetTicketId(String orderId, Long userId, Long clientAmount) {
    V2_Order order = v2_getOrderForPayment(orderId, userId, clientAmount);
    return order.getTicket().getId();
}
```

검증 항목:
- order 존재 여부
- 주문 소유자 일치
- 주문 상태 PENDING 확인
- 금액 일치

### 4-2. PG 결제 승인 요청

```java
TossPaymentResponse result = tossPaymentService.confirmPayment(request);
```

- 외부 API 호출
- 서킷브레이커 / 타임아웃 적용
- **DB 트랜잭션 없음**

### 4-3. 성공 시 → PaymentTransactionService.handleSuccess()

```java
@Transactional
public V2_PaymentConfirmResponse handleSuccess(
    String orderId,
    TossPaymentResponse pgResponse,
    Long userId
) {
    // Order 조회
    V2_Order order = orderRepository.findById(orderId)
        .orElseThrow(() -> new ErrorException(OrderErrorCode.ORDER_NOT_FOUND));

    // Payment 저장
    Payment payment = paymentRepository.save(
        new Payment(
            pgResponse.paymentKey(),
            orderId,
            order.getAmount(),
            pgResponse.method(),
            pgResponse.status()
        )
    );

    // Order 결제 완료
    order.setPayment(payment);
    order.markPaid(pgResponse.paymentKey());

    // Ticket 발급
    Ticket ticket = ticketService.confirmPayment(
        order.getTicket().getId(),
        userId
    );

    // Queue 완료
    queueEntryProcessService.completePayment(
        ticket.getEvent().getId(),
        userId
    );

    // 알림 발행
    eventPublisher.publishEvent(
        new OrderSuccessV2Message(userId, orderId, order.getAmount(), ticket.getEvent().getTitle())
    );

    return V2_PaymentConfirmResponse.from(order, true);
}
```

해당 트랜잭션에서 수행되는 작업:
1. Order 조회
2. Payment 엔티티 저장
3. Order 상태 PENDING → PAID 전환
4. Ticket CONFIRM
5. Queue 완료 처리
6. 결제 성공 이벤트 발행

> **중간 실패 시 전체 롤백**

### 4-4. 결제 실패 시 흐름

```java
@Transactional
public void handleFailure(String orderId, Long ticketId) {
    V2_Order order = orderRepository.findById(orderId)
        .orElseThrow(() -> new ErrorException(OrderErrorCode.ORDER_NOT_FOUND));
    order.markFailed();
    ticketService.failPayment(ticketId);
}
```

- Order → FAILED
- Ticket → FAILED
- Seat 해제(AVAILABLE)

---

## 5. 장애 대응 전략

### 타임아웃 설정

```java
HttpClient httpClient = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(3))  // 연결 타임아웃
    .build();

JdkClientHttpRequestFactory requestFactory = new JdkClientHttpRequestFactory(httpClient);
requestFactory.setReadTimeout(Duration.ofSeconds(5));  // 읽기 타임아웃
```

### 서킷브레이커 설정

```yaml
resilience4j:
  circuitbreaker:
    instances:
      tossPayment:
        slidingWindowSize: 10        # 최근 10개 요청 기준
        failureRateThreshold: 50     # 50% 실패 시 OPEN
        waitDurationInOpenState: 30s # 30초 후 HALF_OPEN
```

### Fallback 처리

```java
@CircuitBreaker(name = CIRCUIT_BREAKER_NAME, fallbackMethod = "handleFailure")
public TossPaymentResponse confirmPayment(V2_PaymentConfirmRequest request) {
    // PG API 호출
}

private TossPaymentResponse handleFailure(V2_PaymentConfirmRequest request, Throwable throwable) {
    if (throwable instanceof CallNotPermittedException) {
        // 서킷 OPEN → PG_UNAVAILABLE (503)
        throw new ErrorException(PaymentErrorCode.PG_UNAVAILABLE);
    }
    if (throwable instanceof ResourceAccessException) {
        // 연결/타임아웃 실패 → PG_TIMEOUT (504)
        throw new ErrorException(PaymentErrorCode.PG_TIMEOUT);
    }
    if (throwable instanceof RestClientException) {
        // API 오류 → PAYMENT_FAILED (400)
        throw new ErrorException(PaymentErrorCode.PAYMENT_FAILED);
    }
    throw new ErrorException(PaymentErrorCode.PAYMENT_FAILED);
}
```

### 장애 시나리오별 동작

| 시나리오 | HTTP 레벨 | 서킷브레이커 | 사용자 응답 | Order 상태 |
|----------|-----------|--------------|-------------|------------|
| Toss 서버 다운 | 연결 타임아웃 3초 | 실패 기록 | PG_TIMEOUT (504) | PENDING 유지 |
| Toss 응답 지연 | 읽기 타임아웃 5초 | 실패 기록 | PG_TIMEOUT (504) | PENDING 유지 |
| 50% 이상 실패 | - | OPEN (30초) | PG_UNAVAILABLE (503) | PENDING 유지 |
| Toss 4xx/5xx | 즉시 응답 | 실패 기록 | PAYMENT_FAILED (400) | PENDING 유지 |
| PG 정상 승인 거절 | 즉시 응답 | CLOSED | PAYMENT_FAILED (400) | **FAILED** |
| PG 정상 승인 | 즉시 응답 | CLOSED | 200 OK | **PAID** |

### 상태 변경 원칙

> **Order / Ticket / Seat을 FAILED로 만드는 유일한 조건: PG가 명시적으로 실패 응답할 때만**

```java
if (result.status() != ApproveStatus.DONE) {
    paymentTransactionService.handleFailure(orderId, ticketId);
    throw new ErrorException(PaymentErrorCode.PAYMENT_FAILED);
}
```

CircuitBreaker의 fallback에서는 상태 변경 없이 예외만 던진다.

**이유:**
- 중복 결제 방지: 이미 PG에서는 성공했을 수도 있음
- 상태 정합성: 확정되지 않은 실패는 반영하지 않음
- 상태 조회 후 재시도를 위해

---

## 6. 중복 결제 검증

Toss Payments에서는 기본적으로 key에 의한 멱등성을 보장한다. 우리 서비스 도메인인 Order에 대한 멱등성 로직만 필요하다.

### 1단계: Order 생성 중복 방어

```java
Optional<V2_Order> existingOrder =
    v2_orderRepository.findByTicket_IdAndStatus(draft.getId(), PENDING);

if (existingOrder.isPresent()) {
    return V2_OrderResponseDto.from(existingOrder.get());
}
```

→ PENDING 주문이 여러 개 생기지 않도록

### 2단계: 이미 결제된 주문 빠른 체크

```java
Optional<V2_Order> paidOrder = orderService.v2_findPaidOrder(orderId, userId);
if (paidOrder.isPresent()) {
    return new V2_PaymentConfirmResponse(orderId, true);
}
```

→ 이미 끝난 결제면 PG를 호출하지 않음 (외부 호출 비용/리스크 절감)

### 3단계: 최종 멱등성 보장

```java
@Transactional
public V2_PaymentConfirmResponse handleSuccess(...) {
    V2_Order order = orderRepository.findById(orderId);

    if (order.getStatus() == PAID) {
        return V2_PaymentConfirmResponse.from(order, true);
    }

    // 이 아래는 단 한 번만 실행되어야 하는 영역
    paymentRepository.save(...);
    order.markPaid(...);
    ticketService.confirmPayment(...);
    // ...
}
```

- order.markPaid()를 호출할 수 있는 곳이 하나
- 두 개의 스레드가 동시에 들어와도 DB의 격리 수준에서 하나만 PAID로 변경 가능
- **최종 중복 방어선**

---

## 정리

1. **PG API 호출과 DB 트랜잭션을 분리**하여 외부 장애가 DB를 오염시키지 않도록 설계
2. **성공/실패를 각각 하나의 트랜잭션**으로 처리하여 상태 일관성 보장
3. **PG 명시적 실패 응답 시에만** Order/Ticket/Seat 상태를 FAILED로 변경
4. **타임아웃 + 서킷브레이커**로 장애 전파 방지
5. **3단계 멱등성 검증**으로 중복 결제 방지

---

## 참고

- [Toss Payments 개발자 문서](https://docs.tosspayments.com/)
- [Resilience4j Circuit Breaker](https://resilience4j.readme.io/docs/circuitbreaker)
