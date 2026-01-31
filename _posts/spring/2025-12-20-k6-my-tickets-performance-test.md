---
title: "K6 성능테스트 - 내 티켓 목록 조회 API 성능 개선 사례"
date: 2025-12-20 10:00:00 +0900
categories: [Spring]
tags: [spring, performance, k6, jpa, hikaricp, optimization, load-testing]
---

## 개요

내 티켓 목록 조회 API(`GET /tickets/my`)에 대한 K6 부하 테스트 결과를 정리한다. 여러 차례 테스트를 통해 **N+1 잠재 위험**을 확인하고, 최종적으로 안정적인 성능을 달성한 과정을 다룬다.

---

## 1. 테스트 환경

| 항목 | 내용 |
|------|------|
| 테스트 대상 | `GET /tickets/my` (내 티켓 목록) |
| 테스트 도구 | K6 + Prometheus + Grafana |
| HikariCP Pool Size | 10 |
| 테스트 DB | Supabase |

---

## 2. 주요 결과

### 2차 테스트 (개선 전)

| 시나리오 | VU | avg | p95 | p99 | RPS |
|----------|-----|-----|-----|-----|-----|
| 저부하 | 100 | 72ms | 87ms | 119ms | ~50/s |
| 고부하 | 500 | 876ms | 2s | 3s | - |

### 4차 테스트 (최종)

| 시나리오 | VU | avg | p95 | p99 | RPS |
|----------|-----|-----|-----|-----|-----|
| 저부하 | 100 | 39ms | 52ms | 83ms | 50.61/s |
| 고부하 | 500 | 129ms | 289ms | 392ms | 222.83/s |

### 개선율 요약

| 구간 | 지표 | 2차 | 4차 | 개선율 |
|------|------|-----|-----|--------|
| 100 VU | avg | 72ms | 39ms | **-45.8%** |
| 100 VU | p95 | 87ms | 52ms | **-40.2%** |
| 100 VU | p99 | 119ms | 83ms | **-30.3%** |
| 500 VU | avg | 876ms | 129ms | **-85.3%** |
| 500 VU | p95 | 2s | 289ms | **-85.6%** |
| 500 VU | p99 | 3s | 392ms | **-86.9%** |

---

## 3. Grafana 스냅샷

<!-- 이미지 첨부 필요 -->

---

## 4. 관측 분석

### 4.1 HikariCP 관측

| 지표 | 값 |
|------|-----|
| Pool Size | 10 |
| Active max | 10 (상한 도달) |
| Pending max | 66 |
| Acquire Time | 70~80ms (피크) |
| Connection Usage Time | 30~90ms |

### 4.2 JVM/GC 관측

| 지표 | 값 | 해석 |
|------|-----|------|
| CPU 사용률 | 0.3~0.4 | 여유 있음 |
| Heap 사용 | 안정적 | 메모리 병목 없음 |
| GC STW max | 4.4ms | GC 병목 아님 |

### 4.3 Traffic 관측

- Peak RPS: **343 req/s**
- 총 요청: 54,949
- http_req_failed: **0%**

---

## 5. 왜 이렇게 빠른가? (N+1 의심에 대한 해석)

### 현재 데이터 분포의 영향

- 테스트 데이터에서 **유저당 티켓 0~1장**
- TicketResponse.from()에서 Lazy 접근해도 **추가 쿼리 몇 번**에서 끝남
- N+1이 "폭발"할 조건이 안 만들어짐

### N+1 잠재 리스크

```java
// DTO 변환에서 Lazy 접근
tickets.stream()
    .map(ticket -> {
        ticket.getEvent();  // Lazy
        ticket.getSeat();   // Lazy
        return TicketResponse.from(ticket);
    })
    .toList();
```

- 코드 구조상 N+1 잠재 리스크는 존재
- 현재 데이터 분포에서는 드러나지 않음

---

## 6. 남아있는 병목

### 500 VU 지연 패턴

```
Hikari 풀 포화 (Active=10)
    ↓
Pending 증가 (max 66)
    ↓
Acquire Time 상승 (70~80ms)
    ↓
p95/p99 상승 (289~392ms)
```

- 쿼리 폭증보다 **커넥션 풀 상한**이 주요 원인
- 500 VU에서도 꼬리 지연이 0.3~0.4s 수준으로 관리됨

---

## 7. 개선 제안

### 우선순위 1: HikariCP 풀 튜닝

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 20  # 10 → 20~30
```

- 기대효과: Pending/Acquire Time 감소 → p95/p99 추가 하락
- 주의: DB max_connections/CPU/IO 함께 확인

### 우선순위 2: N+1 조건 테스트

- 유저당 티켓 20~50장인 데이터로 테스트
- TicketResponse.from()의 Lazy 접근이 **N+1로 체감**될 가능성 검증

### 우선순위 3: 쿼리 최적화

```java
// Fetch Join
@Query("SELECT t FROM Ticket t " +
       "LEFT JOIN FETCH t.event " +
       "LEFT JOIN FETCH t.seat " +
       "WHERE t.ownerId = :userId")
List<Ticket> findByOwnerIdWithDetails(@Param("userId") Long userId);
```

### 우선순위 4: 페이지네이션

```java
Pageable pageable = PageRequest.of(0, 20);
Page<Ticket> tickets = ticketRepository.findByOwnerId(userId, pageable);
```

- 티켓 히스토리 증가 시 payload/쿼리 비용 증가 방지

### 우선순위 5: 요청당 쿼리 수 관측

- p6spy / datasource-proxy로 "요청당 쿼리 수" 측정
- N+1 논쟁 종결

---

## 8. 성능 개선 전/후 비교

| 구간 | 지표 | 2차 | 4차 | 변화 |
|------|------|-----|-----|------|
| 100 VU | avg | 72ms | 39ms | -33ms |
| 100 VU | p95 | 87ms | 52ms | -35ms |
| 500 VU | avg | 876ms | 129ms | -747ms |
| 500 VU | p95 | 2s | 289ms | -1.7s |

---

## 정리

1. 최종 결과 **100/500 VU 모두 지연이 매우 낮고 안정적**
2. 500 VU에서 병목은 **HikariCP 풀 상한** 때문
3. 현재 데이터 분포에서 **N+1이 폭발하지 않음**
4. 유저당 티켓 수 증가 시 **N+1 잠재 리스크** 존재
5. **Fetch Join + 페이지네이션**으로 선제적 대응 권장

---

## 참고

- HikariCP Configuration: https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby
- p6spy: https://github.com/p6spy/p6spy
