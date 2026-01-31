---
title: "K6 성능테스트 - 티켓 상세 조회 API N+1 문제와 Fetch Join 개선"
date: 2025-12-19 10:00:00 +0900
categories: [Spring]
tags: [spring, performance, k6, jpa, n+1, fetch-join, hikaricp, load-testing]
---

## 개요

티켓 상세 조회 API(`GET /tickets/my/{ticketId}/details`)에 대한 K6 부하 테스트 결과를 정리한다. 고부하 환경에서 **N+1 문제와 OIV(Open-In-View)**로 인한 성능 저하를 확인하고, **Fetch Join으로 개선**한 과정을 다룬다.

---

## 1. 테스트 환경

| 항목 | 내용 |
|------|------|
| 테스트 대상 | `GET /tickets/my/{ticketId}/details` |
| 테스트 도구 | K6 + Prometheus + Grafana |
| HikariCP Pool Size | 10 |

---

## 2. 주요 결과

### 1차 테스트 (개선 전)

| 시나리오 | VU | avg | p95 | p99 | 해석 |
|----------|-----|-----|-----|-----|------|
| 저부하 | ≤100 | 106ms | 129ms | 153ms | 안정적 |
| 고부하 | ≤500 | 1s | 3s | 5s | 초 단위 지연 |

### 2차 테스트 (Fetch Join 적용 후)

| 시나리오 | VU | avg | p95 | p99 | 해석 |
|----------|-----|-----|-----|-----|------|
| 저부하 | ≤100 | 72ms | 90ms | 110ms | 32% 개선 |
| 고부하 | ≤500 | 915ms | 3s | 4s | 부분 개선 |

### 개선율 요약

| 구간 | 지표 | 1차 | 2차 | 개선율 |
|------|------|-----|-----|--------|
| 100 VU | avg | 106ms | 72ms | -32.1% |
| 100 VU | p95 | 129ms | 90ms | -30.2% |
| 100 VU | p99 | 153ms | 110ms | -28.1% |
| 500 VU | avg | 1s | 915ms | -8.5% |
| 500 VU | p99 | 5s | 4s | -20.0% |

---

## 3. Grafana 스냅샷

<!-- 이미지 첨부 필요 -->

---

## 4. 병목 분석

### 4.1 N+1 문제 (개선 전)

```java
// 요청당 4개 쿼리 발생
// 1. Active Session 조회
// 2. Ticket 조회
// 3. Event 조회 (Lazy)
// 4. Seat 조회 (Lazy)
```

**개선 전 쿼리 로그**:

```sql
-- 1. Ticket 조회
SELECT t.* FROM tickets t WHERE t.id = ?

-- 2. Event 조회 (Lazy 로딩)
SELECT e.* FROM events e WHERE e.id = ?

-- 3. Seat 조회 (Lazy 로딩)
SELECT s.* FROM seats s WHERE s.id = ?
```

### 4.2 OIV(Open-In-View) 영향

- OIV가 켜진 상태에서 **컨트롤러에서 Lazy 로딩** 가능
- TicketResponse.from() 변환 시 추가 쿼리 발생
- 고부하에서 **커넥션 재획득 대기** 발생

### 4.3 HikariCP 관측

| 지표 | 저부하 (100 VU) | 고부하 (500 VU) |
|------|-----------------|-----------------|
| Active | 5~8 | 10 (상한) |
| Pending | 0~5 | 190+ |
| Acquire Time | < 10ms | 800ms+ |

---

## 5. 개선: Fetch Join 적용

### 개선 후 Repository

```java
@Query("SELECT t FROM Ticket t " +
       "LEFT JOIN FETCH t.event e " +
       "LEFT JOIN FETCH t.seat s " +
       "WHERE t.id = :ticketId")
Optional<Ticket> findByIdWithEventAndSeat(@Param("ticketId") Long ticketId);
```

### 개선 후 쿼리 로그

```sql
-- 단일 쿼리로 통합
SELECT t.*, e.*, s.*
FROM tickets t
LEFT JOIN events e ON e.id = t.event_id
LEFT JOIN seats s ON s.id = t.seat_id
WHERE t.id = ?
```

### 쿼리 수 변화

| 구분 | 쿼리 수 |
|------|---------|
| 개선 전 | 4개 (Session + Ticket + Event + Seat) |
| 개선 후 | 2개 (Session + 통합 쿼리) |

---

## 6. 추가 개선 제안

### 개선 1: OIV 비활성화

```yaml
spring:
  jpa:
    open-in-view: false
```

- 트랜잭션 외부 Lazy 접근 시 즉시 예외 → 조기 발견

### 개선 2: DTO 변환 위치 이동

```java
// 컨트롤러가 아닌 서비스(트랜잭션 내부)에서 변환
@Transactional(readOnly = true)
public TicketResponse getTicketDetail(Long ticketId) {
    Ticket ticket = ticketRepository.findByIdWithEventAndSeat(ticketId)
        .orElseThrow(...);
    return TicketResponse.from(ticket);  // 트랜잭션 내부
}
```

### 개선 3: HikariCP 풀 조정

- maximumPoolSize: 10 → 20~30
- 근본 해결이 아닌 보조 수단

### 개선 4: 검증 실험

1. OIV off + 현 구조 유지 → 예외 발생 여부 확인
2. Fetch Join 적용 + 동일 부하 재실행 → 개선 효과 수치화

---

## 7. 병목 발생 메커니즘

```
500 VU 동시 요청
    ↓
요청당 4개 쿼리 (N+1)
    ↓
HikariCP 풀 10개 포화
    ↓
Pending 190+ / Acquire Time 800ms+
    ↓
응답시간 106ms → 1s (10배 증가)
```

---

## 정리

1. **N+1 문제**가 고부하에서 성능 저하의 주요 원인
2. **Fetch Join** 적용으로 쿼리 4개 → 2개로 축소
3. 100 VU 기준 **avg 32% 개선** 달성
4. **OIV 비활성화**로 숨은 Lazy 로딩 조기 발견 권장
5. DTO 변환은 **서비스(트랜잭션 내부)**에서 수행

---

## 참고

- JPA Fetch Join: https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#fetching-strategies
- Spring OIV 이슈: https://vladmihalcea.com/the-open-session-in-view-anti-pattern/
