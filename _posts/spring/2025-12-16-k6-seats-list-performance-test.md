---
title: "K6 성능테스트 - 좌석 목록 조회 API 병목 분석"
date: 2025-12-16 10:00:00 +0900
categories: [Spring]
tags: [spring, performance, k6, jpa, n+1, hikaricp, load-testing]
---

## 개요

좌석 목록 조회 API(`GET /events/{eventId}/seats`)에 대한 K6 부하 테스트 결과를 정리한다. 50~100 VU에서는 안정적이지만, 200~500 VU에서 **N+1 문제와 트랜잭션 범위**로 인한 성능 저하가 발생했다.

---

## 1. 테스트 환경

| 항목 | 내용 |
|------|------|
| 테스트 대상 | `GET /events/{eventId}/seats` |
| 테스트 도구 | K6 + Prometheus + Grafana |
| HikariCP Pool Size | 10 |
| 좌석 데이터 | Event당 600석 |

---

## 2. 주요 결과

### 시나리오별 성능 요약

| 구간 | VU | avg | p95 | RPS | 상태 |
|------|-----|-----|-----|-----|------|
| 저부하 | 50~100 | ~24ms | ~52ms | ~411/s | ✅ 안정 |
| 고부하 | 200~500 | ~192ms | ~632ms | ~257/s | ⚠ 병목 |

### 관측 포인트

- **저부하(50~100 VU)**: 응답시간 안정적, HikariCP 여유 있음
- **고부하(200~500 VU)**:
  - HikariCP Pending 급증
  - Acquire Time 상승
  - p95/p99가 수백 ms로 증가

---

## 3. Grafana 스냅샷

<!-- 이미지 첨부 필요 -->

---

## 4. 병목 분석

### 4.1 N+1 문제

```java
// Controller에서 DTO 변환
seats.stream().map(SeatResponse::from).toList()
```

- SeatResponse.from() 내부에서 **Lazy 로딩** 발생
- Event, Grade 등 연관 엔티티 접근 시 추가 쿼리
- OIV(Open-In-View)가 켜진 상태에서 트랜잭션 외부 쿼리 허용

### 4.2 전체 좌석 조회 문제

- 600석 전체를 한 번에 조회
- 페이지네이션 없음
- 고부하에서 응답 payload 증가

### 4.3 트랜잭션 범위

- 서비스 → 컨트롤러까지 트랜잭션이 확장
- DB 커넥션 점유 시간 증가
- HikariCP 대기열 발생

---

## 5. 개선 제안

### 우선순위 1: Fetch Join / DTO Projection

```java
@Query("SELECT s FROM Seat s " +
       "JOIN FETCH s.event " +
       "WHERE s.event.id = :eventId")
List<Seat> findByEventIdWithEvent(@Param("eventId") Long eventId);
```

- 또는 QueryDSL로 DTO 직접 조회
- N+1 쿼리를 1회로 축소

### 우선순위 2: OIV 비활성화

```yaml
spring:
  jpa:
    open-in-view: false
```

- 트랜잭션 외부 Lazy 접근 시 예외 발생 → 조기 발견

### 우선순위 3: 페이지네이션

```java
Pageable pageable = PageRequest.of(0, 50);
Page<Seat> seats = seatRepository.findByEventId(eventId, pageable);
```

- 한 번에 전체 조회하지 않고 필요한 만큼만
- 응답 크기 제한으로 네트워크 부하 감소

### 우선순위 4: HikariCP 풀 조정

- maximumPoolSize: 10 → 20~30
- 단, DB max_connections와 함께 조정 필요

---

## 6. 성능 비교 (개선 전/후 예상)

| 지표 | 개선 전 (500 VU) | 개선 후 목표 |
|------|------------------|--------------|
| avg | 192ms | < 50ms |
| p95 | 632ms | < 100ms |
| 쿼리 수 | N+1 (수십 회) | 1~2회 |

---

## 정리

1. **N+1 문제**가 고부하에서 성능 저하의 주요 원인
2. **OIV + Lazy 로딩** 조합이 트랜잭션 외부 쿼리 허용
3. **Fetch Join 또는 DTO Projection**으로 쿼리 최적화 필요
4. **페이지네이션** 적용으로 응답 크기 제한
5. HikariCP 풀 조정은 근본 해결이 아닌 **보조 수단**

---

## 참고

- JPA N+1 문제: https://vladmihalcea.com/n-plus-1-query-problem/
- Spring OIV: https://docs.spring.io/spring-boot/docs/current/reference/html/data.html#data.sql.jpa-and-spring-data
