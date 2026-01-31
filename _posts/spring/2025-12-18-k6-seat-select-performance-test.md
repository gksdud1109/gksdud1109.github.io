---
title: "K6 성능테스트 - 좌석 선택 API 병목 분석과 트랜잭션 최적화"
date: 2025-12-18 10:00:00 +0900
categories: [Spring]
tags: [spring, performance, k6, transaction, websocket, hikaricp, load-testing]
---

## 개요

좌석 선택 API(`POST /events/{eventId}/seats/{seatId}/select`)에 대한 K6 부하 테스트 결과를 정리한다. 200 VU 이상에서 **트랜잭션 범위 과다와 동기 WebSocket 전송**으로 인한 HikariCP 병목이 발생했다.

---

## 1. 테스트 시나리오

### 시나리오 A: Non-Competitive Baseline

- VU별 고유 좌석 할당 (경합 없음)
- 순수 API/DB 처리 한계 확인

### 시나리오 B: Controlled Contention

- 50석에 50~100 VU 경쟁
- 좌석 경합 비용 측정

---

## 2. 주요 결과

### 시나리오 A 결과

| 구간 | VU | avg | p95 | p99 | RPS | 에러율 |
|------|-----|-----|-----|-----|-----|--------|
| 저부하 | 50~100 | 155ms | 224ms | 282ms | ~67/s | 0% |
| 고부하 | 200~500 | 2s | 5s | 7s | ~116/s | 0.3% |

### 개선 후 시나리오 A 결과 (2차)

| 구간 | VU | avg | p95 | p99 | 변화 |
|------|-----|-----|-----|-----|------|
| 저부하 | 100 | 92ms | 125ms | 177ms | -40% 개선 |
| 고부하 | 500 | 1s | 3s | 4s | 부분 개선 |

### 시나리오 B 결과

| 지표 | 값 |
|------|-----|
| 총 요청수 | 4,217 |
| 실패율 | 94.5% (경합으로 인한 의도된 실패) |
| HTTP Duration avg | 121ms |
| HTTP Duration max | 369ms |

---

## 3. Grafana 스냅샷

<!-- 이미지 첨부 필요 -->

---

## 4. 병목 분석

### 4.1 과도하게 긴 트랜잭션 범위 (Primary Bottleneck)

```java
@Transactional
public Seat selectSeatAndCreateTicket(...) {
    // 1. 큐 진입 여부 확인 (Redis + DB fallback)
    // 2. Draft Ticket 조회/생성
    // 3. User/Event 엔티티 조회
    // 4. Seat 조회 및 UPDATE
    // 5. WebSocket 메시지 전송 (동기!)
    // ← 여기까지 전부 트랜잭션 내부
}
```

- DB 커넥션이 **WebSocket 전송 완료까지 반환되지 않음**
- HikariCP 10개 풀 즉시 고갈

### 4.2 트랜잭션 내 동기 WebSocket 전송 (Critical)

```java
eventPublisher.publishEvent(SeatStatusMessage.from(saved));
// ↓
@EventListener  // 동기 실행, @Async 없음
public void handleSeatStatus(SeatStatusMessage msg) {
    publisher.publish(msg);  // SimpMessagingTemplate.convertAndSend()
}
```

- WebSocket 전송이 **트랜잭션 커밋 전** 동기 실행
- DB 커넥션 점유 시간 증가

### 4.3 HikariCP 관측

| 지표 | 저부하 | 고부하 |
|------|--------|--------|
| Active Connections | 5~8 | 10 (상한) |
| Pending Threads | 0~2 | 190+ |
| Acquire Time | < 5ms | 800ms+ |

---

## 5. 개선 제안

### 개선 1: WebSocket 이벤트 비동기화 (가장 효과적)

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
@Async
public void handleSeatStatus(SeatStatusMessage msg) {
    publisher.publish(msg);
}
```

- 트랜잭션 커밋 후 비동기 실행
- DB 커넥션 점유 시간 대폭 감소

### 개선 2: 트랜잭션 범위 축소

```java
// 트랜잭션 밖
validateQueueEntry();
validateUser();

// 최소 트랜잭션만
@Transactional
public Seat reserveSeatOnly(Long seatId) {
    return seatRepository.updateAndGet(seatId);
}

// 트랜잭션 밖
publishEvent();
```

### 개선 3: 단일 조건부 UPDATE

```sql
UPDATE seat
SET status = 'RESERVED', reserved_by = ?
WHERE id = ? AND event_id = ? AND status = 'AVAILABLE'
```

- SELECT + UPDATE 대신 단일 UPDATE
- rowcount로 성공/실패 판정
- 락 경합 비용 감소

### 개선 4: HikariCP 풀 조정 (보조 수단)

- maximumPoolSize: 10 → 20~50
- 구조 개선 없이 단순 증설은 근본 해결 아님

---

## 6. 개선 효과 비교

### 100 VU 구간

| 지표 | 1차 | 4차 | 개선율 |
|------|-----|-----|--------|
| avg | 155ms | 92ms | -40% |
| p95 | 224ms | 125ms | -44% |
| p99 | 282ms | 177ms | -37% |

### 500 VU 구간

| 지표 | 1차 | 4차 | 개선율 |
|------|-----|-----|--------|
| avg | 2s | 1s | -50% |
| p95 | 5s | 3s | -40% |
| p99 | 7s | 4s | -43% |

---

## 7. 병목 발생 메커니즘

```
200+ VU 동시 요청
    ↓
10개 커넥션만 처리 가능
    ↓
각 커넥션 점유 시간 = DB 작업 + WebSocket 전송 (동기)
    ↓
190개 요청 대기 (Pending Threads ↑)
    ↓
Latency 155ms → 2s (13배 증가)
```

---

## 정리

1. **트랜잭션 범위 과다**가 핵심 병목
2. **동기 WebSocket 전송**이 커넥션 점유 시간 증가의 주요 원인
3. `@TransactionalEventListener(AFTER_COMMIT) + @Async`로 비동기화 권장
4. 트랜잭션은 **필수 DB 작업만** 포함하도록 축소
5. HikariCP 풀 증설은 **근본 해결이 아닌 보조 수단**

---

## 참고

- Spring Transaction Management: https://docs.spring.io/spring-framework/docs/current/reference/html/data-access.html#transaction
- @TransactionalEventListener: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
