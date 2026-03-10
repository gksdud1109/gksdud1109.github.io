---
title: "결제 무결성과 장애 전파 차단 검증: 동시성·멱등성·PG 장애 테스트"
date: 2026-03-10 23:00:00 +0900
categories: [Spring]
tags: [spring, payment, concurrency, idempotency, circuit-breaker, k6, optimistic-lock, test]
---

> [Payment V2 아키텍처 포스팅]({% post_url 2026-01-04-payment-v2-architecture %})에서 설계한 방어 구조가 실제로 의도대로 동작하는지 프로젝트 종료 후 개인 fork에서 사후 검증했다. 구현 당시에는 설계와 기능 완성에 집중했고, 이후 결제 파트의 무결성과 장애 대응 설계를 테스트와 수치로 다시 확인했다.

---

## 문제 정의

Payment V2의 결제 흐름은 다음과 같다.

```text
[Client] → v2_confirmPayment() (트랜잭션 밖)
               ↓
         PG API 호출 (Toss)        ← 외부 통신, 타임아웃 위험
               ↓
         handleSuccess() @Transactional
               ↓
         Payment INSERT + Order UPDATE + Ticket CONFIRM
```

설계상 안전해 보인다고 해서 실제로 안전한 것은 아니다. 이번 검증에서 확인하고 싶었던 위험 시나리오는 두 가지였다.

첫째, 동일 `orderId`로 여러 요청이 동시에 PG를 통과하면 `handleSuccess()` 안에서 `Payment` INSERT 경쟁이 발생해 중복 결제가 생길 수 있다.

둘째, PG timeout 또는 응답 불명확 상황에서 Order 상태가 정말 `PENDING`으로 유지되는지, 아니면 의도와 다르게 훼손되는지 확인이 필요했다.

즉 이번 검증의 목적은 이전의 구현에서 얼마나 응답성능이 개선되었는지 보다 다음 두 가지를 확인하는 데 있었다.

- 동일 주문에 대해 최종적으로 결제는 1건만 남는가??
- PG 장애 시 상태가 복구 가능한 형태로 일관되게 유지되는가??

---

## 방어 구조

테스트 대상이 되는 방어 레이어를 먼저 정리한다.

### Layer 1: `V2_Order @Version` 낙관적 락

```java
@Version
@Column(name = "version", nullable = false)
private Long version;
```

동시에 두 트랜잭션이 같은 `PENDING` Order를 읽더라도 하나만 커밋 가능하다. 나머지는 `ObjectOptimisticLockingFailureException`으로 실패한다.

### Layer 2: `Payment.order_id UNIQUE` DB 제약

```java
@Column(name = "order_id", nullable = false, unique = true)
private String orderId;
```

`Payment` INSERT 시 DB가 중복을 최종 차단한다. 애플리케이션 계층에서 놓치더라도 DB가 마지막 방어선이 된다.

### Layer 3: 이미 완료된 주문에 대한 멱등 응답 처리

```java
if (order.getStatus() == OrderStatus.PAID) {
    return V2_PaymentConfirmResponse.from(order, true);
}
```

이미 결제가 완료된 주문에 대해 재호출이 들어오면 기존 결과를 그대로 반환한다.

### Layer 4: `PaymentService` 동시성 예외 캐치

```java
try {
    return paymentTransactionService.handleSuccess(orderId, result, userId);
} catch (DataIntegrityViolationException | ObjectOptimisticLockingFailureException e) {
    log.warn("[Payment] 동시 결제 요청 감지 - orderId: {}, cause: {}",
        orderId, e.getClass().getSimpleName());
    return orderService.v2_findPaidOrder(orderId, userId)
        .map(paid -> new V2_PaymentConfirmResponse(orderId, true))
        .orElseThrow(() -> new ErrorException(PaymentErrorCode.PAYMENT_FAILED));
}
```

Layer 1, 2에서 예외가 발생하더라도 클라이언트에는 HTTP 500 대신 멱등 성공 응답을 반환한다. 선행 요청이 이미 결제를 완료한 상태라면, 완료된 주문을 재조회해 정상 응답으로 변환한다.

---

## 인프라 변경

Flyway 마이그레이션 파일 `V20260108_00__payment_order_id_unique_and_v2_order_version.sql`을 추가했다.

```sql
ALTER TABLE payments
ADD CONSTRAINT uq_payments_order_id UNIQUE (order_id);

ALTER TABLE v2_orders
ADD COLUMN IF NOT EXISTS version BIGINT NOT NULL DEFAULT 0;
```

이 변경으로 애플리케이션 코드뿐 아니라 DB 스키마 차원에서도 중복 결제 방어가 가능해졌다.

테스트 환경은 다음처럼 나눠서 검증했다.

- 통합 테스트: H2 + `@SpringBootTest`
- perf 부하 테스트: PostgreSQL + `SPRING_PROFILES_ACTIVE=perf`
- 부하 테스트의 PG 응답: `FakeTossPaymentService` 사용

부하 테스트에서 Fake PG를 쓴 이유는 실제 PG 네트워크 지연을 재현하려는 게 아니라, 외부 호출 영향을 제거하고 애플리케이션 내부 처리 비용과 상태 전이 동작을 보기 위해서다.

---

## 테스트 구성

### 1. 결제 동시성 통합 테스트

`PaymentConcurrencyTest.java`는 `@SpringBootTest` 기반 통합 테스트다. 테스트 메서드에 `@Transactional`을 붙이지 않은 이유는 프로덕션과 동일한 트랜잭션 경계를 유지해야 실제 충돌 지점을 재현할 수 있기 때문이다.

**`concurrentPayment_exactlyOneSucceeds`**

`CountDownLatch(1)`로 10개 스레드를 동시에 출발시킨다. 여기서 중요한 건 "몇 개의 응답이 성공했는가"보다 "최종 DB 상태가 무엇인가"다. 검증한 불변식은 아래와 같다.

- `paymentCountForOrder == 1`
- `Order.status == PAID`
- `unexpectedErrorCount == 0`
- `totalResponses == threadCount`

동시에 10개의 결제 요청이 들어가더라도 DB에는 Payment가 1건만 남고, 모든 스레드는 예외 없이 멱등 성공 응답을 받아야 한다.

**`optimisticLock_staleSave_throwsException`**

이 테스트는 `@Version`의 독립 동작을 따로 증명하기 위해 만들었다. 통합 동시성 테스트에서는 Payment UNIQUE 제약이 먼저 발동할 수 있어서, 낙관적 락이 실제로 동작했는지 분리해서 보기 어렵다. 그래서 `TransactionTemplate`으로 stale 엔티티를 저장하도록 만들고, 선행 트랜잭션이 version을 올린 뒤 `ObjectOptimisticLockingFailureException`이 발생하는지 확인했다.

### 2. 서킷 브레이커 동작 테스트

`CircuitBreakerResponseTimeTest.java`는 서킷 브레이커가 열렸을 때 fail-fast가 실제로 동작하는지 검증한다.

| 테스트 | 검증 내용 |
|--------|-----------|
| CB OPEN → 즉시 차단 | `PG_UNAVAILABLE` 예외, 100ms 이내 응답 |
| CB OPEN 평균 응답 | 서킷이 열린 상태에서 평균 응답이 수 ms~수십 ms 수준으로 즉시 차단되는지 확인 |
| CB 상태 전이 | 3/5 실패 시 자동 OPEN 전환 검증 |

이 테스트를 "전체 성능 개선"의 근거로 쓰면 안 된다. 정확한 의미는 "PG 장애 시 긴 timeout을 기다리지 않고 보호 모드로 빠르게 전환되는가"를 확인한 것이다.

### 3. PG 장애 시 상태 불변식 테스트

`PaymentPgFailureTest.java`는 PG 장애 시 상태가 어떻게 남는지를 검증한다.

| 테스트 | 검증 내용 |
|--------|-----------|
| `confirmPayment_pgTimeout_keepsOrderPending` | PG_TIMEOUT 시 Order=PENDING, Payment=0건, Ticket=DRAFT, Seat=RESERVED |
| `confirmPayment_pgUnavailable_keepsOrderPending` | CB OPEN(PG_UNAVAILABLE) 시 동일 불변식 |

이 설계의 핵심은 "불확실한 결제 상태를 성급히 FAILED로 덮어쓰지 않는다"는 점이다. PG 응답이 불명확하면 Order는 `PENDING`으로 유지하고, 클라이언트가 재확인하거나 별도 처리 흐름으로 복구할 수 있도록 했다. 즉 이번 테스트는 예외가 났다는 사실을 확인하는 게 아니라, 장애 상황에서도 최종 상태가 복구 가능한 형태로 남는지를 확인하는 테스트다.

### 4. k6 부하 테스트

`confirmPaymentOnly.test.js`는 `confirmPayment` API 자체만 단독으로 측정하기 위한 시나리오다.

구성은 다음과 같다. perf bootstrap이 Event #3 기준 `PENDING` 주문을 미리 생성하고, `/internal/seed/pending-orders?limit=N`에서 fixture를 조회한다. 이후 각 VU가 자신에게 할당된 주문 1건만 승인하는 `per-vu-iterations` 모델을 유지했다.

이 방식을 선택한 이유는 주문 생성 부하와 결제 승인 부하를 분리하기 위해서다. `setup()`에서 주문까지 같이 만들면 `confirmPayment` API 자체의 비용을 분리해서 보기 어렵다. Threshold는 `p95 < 3000ms`, `p99 < 5000ms`, error rate < 5%로 설정했다.

---

## 검증 결과

### 동시성 테스트

```text
===== 결제 동시성 테스트 결과 =====
동시 요청 수:      10개
성공(멱등 포함):   10건
예상 외 오류:      0건
DB Payment:       1건
중복결제:          ✅ 0건
===================================
```

동일 주문에 대해 동시에 결제가 들어와도 Payment는 1건만 남고, 동시성 충돌이 발생해도 500 에러 대신 멱등 성공 응답으로 수렴하는 것을 확인했다.

### 서킷 브레이커 응답 시간

```text
CB OPEN 상태 응답 시간: ~9ms
Toss API 타임아웃:     5,000ms
응답 시간 단축:        ~99.8%
```

"정상 상태에서 빨라졌다"가 아니라, "PG 장애 시 긴 timeout을 기다리지 않고 즉시 차단된다"는 의미다.

### confirmPaymentOnly 부하 테스트

| 구간 | VU | 성공률 | p95 | p99 |
|------|----|--------|-----|-----|
| before | 100 | 100% | 2.36s | 2.58s |
| after  | 100 | 100% | 2.56s | 2.66s |

정상 구간 latency는 before/after가 거의 비슷했다. 이 결과만 보면 `방어 구조 도입으로 성능이 개선됐다`고 말할 수는 없다.

이건 오히려 설계 목적과 맞는다. 이번 구조는 정상 상태의 순수 latency 최적화보다 외부 PG 장애 시 장애 전파 차단과 결제 무결성 확보를 목표로 했기 때문이다. 따라서 이 작업의 핵심 증빙은 동일 주문 동시 결제 시 `Payment 1건`만 남는 멱등성 보장, 그리고 PG timeout/unavailable 시 `Order=PENDING, Payment=0, Ticket=DRAFT, Seat=RESERVED` 불변식 유지 두 가지다.

---

## 한계와 해석

이번 검증에도 한계는 있다. k6 부하 테스트는 Fake PG 응답 기반이므로 실제 외부 PG 네트워크 지연을 포함하지 않는다. 100 VU 실험은 정상 구간 비교 기준선으로는 의미가 있지만, 고장 전파 완화 효과를 전부 설명하지는 못한다. 동시성 테스트는 처리량보다 무결성 불변식 검증을 목표로 설계했기 때문에 10개 동시 요청 수준에서 재현성과 해석 가능성을 우선했다.

그럼에도 이번 검증은 충분히 의미가 있었다. "설계상 안전하다"는 판단을 실제 테스트 코드와 결과로 다시 확인했고, 결제 시스템에서 더 중요한 무결성과 장애 대응 특성을 문서화할 수 있었기 때문이다.

---

## 정리

이 작업으로 확인한 것은 정상 상태에서 더 빨라졌다는 것이 아니었다. 대신 결제 시스템에서 더 중요한 세 가지를 검증했다.

- 동일 주문 동시 결제 시 Payment는 1건만 남는다.
- PG timeout/unavailable 시 상태는 PENDING으로 보존된다.
- Circuit Breaker OPEN 상태에서는 fail-fast가 동작한다.

프로젝트 종료 후 진행한 사후 검증이었지만, 결제 설계 판단을 테스트와 수치로 다시 확인했다는 점에서 충분히 의미 있는 작업이었다.

---

## 파일 변경 요약

| 파일 | 변경 유형 | 내용 |
|------|-----------|------|
| `V2_Order.java` | 수정 | `@Version` 낙관적 락 필드 추가 |
| `Payment.java` | 수정 | `order_id UNIQUE` 제약 추가 |
| `PaymentRepository.java` | 수정 | `findAllByOrderId()` 추가 |
| `PaymentService.java` | 수정 | 동시성 예외 catch → 멱등 응답 |
| `V20260108_00__*.sql` | 생성 | Flyway: UNIQUE + version 컬럼 |
| `PaymentConcurrencyTest.java` | 생성 | 동시성 통합 테스트 |
| `CircuitBreakerResponseTimeTest.java` | 생성 | CB fail-fast 검증 |
| `PaymentPgFailureTest.java` | 생성 | PG 장애 시 상태 불변식 테스트 |
| `PerfPaymentConfig.java` | 생성 | perf 프로파일 Fake PG 응답 |
| `PerfPendingOrderDataInitializer.java` | 생성 | confirmPaymentOnly용 PENDING order 선생성 |
| `SeedController.java` | 수정 | perf fixture 조회 endpoint 추가 |
| `confirmPayment.js` | 생성 | k6 결제 확인 시나리오 |
| `confirmPaymentOnly.test.js` | 생성 | confirmPayment 단일 API 부하 테스트 |
