---
title: "K6 성능테스트 - 로그인 API 병목 분석과 개선 방안"
date: 2025-12-15 10:00:00 +0900
categories: [Spring]
tags: [spring, performance, k6, bcrypt, hikaricp, jwt, load-testing]
description: "로그인 API를 k6로 부하테스트해 BCrypt 검증, HikariCP 커넥션 풀 고갈, JWT 키 재생성이 겹치는 병목을 분석하고 RefreshToken Redis 이전 등 개선안을 정리한다."
---

## 개요

로그인 API(`POST /api/v1/auth/local/login`)에 대한 K6 부하 테스트 결과를 정리한다. 테스트 결과 100~200 VU 환경에서 **BCrypt, HikariCP, JWT 생성** 세 가지 병목이 동시에 발생하는 것을 확인했다.

---

## 1. 테스트 환경

| 항목 | 내용 |
|------|------|
| 테스트 대상 | `POST /api/v1/auth/local/login` |
| 테스트 도구 | K6 + Prometheus + Grafana |
| 환경 | Local Docker Compose (Spring Boot 3.3, MySQL 8, HikariCP) |
| 데이터 | PerfUser 200명 |
| HikariCP Pool Size | 10 |

---

## 2. 주요 결과

### VU별 응답시간 지표

| VU | avg | p95 | max | RPS | 에러율 |
|----|-----|-----|-----|-----|--------|
| 10 | 278ms | 412ms | 683ms | 35/s | 0% |
| 50 | 1s | 1s | 1s | 40/s | 0% |
| 100 | 1s | 1s | 3s | 47/s | 0% |
| 200 | 2s | 3~4s | 6~8s | 41/s | 0% |

### 관측 포인트

- **HTTP 오류 0%**: 안정성은 높음
- **CPU 100% 고정**: 100 VU 이상에서 즉시 포화
- **HikariCP Active 10/10**: Connection Pool 완전 포화
- **Pending Threads 80~200**: DB 병목 진입
- **RPS 정체**: 포화 상태에서 처리량 증가 멈춤

---

## 3. Grafana 스냅샷

<!-- 이미지 첨부 필요 -->

---

## 4. 병목 분석

### 4.1 BCrypt 검증 비용 (CPU-bound)

```java
passwordEncoder.matches(request.password, user.password)
```

- cost=10 기준 **100~300ms per call**
- 동시성 100에서 CPU 코어 수 초과 → 즉시 포화

### 4.2 RefreshToken DB UPDATE (DB-bound)

```java
user.updateRefreshToken(refreshToken);  // DB UPDATE 발생
```

- 로그인마다 `UPDATE user SET refresh_token = ...` 실행
- HikariCP 10개 풀 즉시 고갈
- Pending threads 80~200 발생 → 응답시간 1~4초 스파이크

### 4.3 JWT SecretKey 매번 재생성 (GC pressure)

```java
Keys.hmacShaKeyFor(Decoders.BASE64.decode(secret))
```

- Access Token + Refresh Token = 요청당 2회 키 생성
- 매 요청마다 secret decode + HMAC 키 생성 → CPU/GC 부하

---

## 5. 병목 메커니즘

```
200 VU 동시 요청
    ↓
BCrypt 검증 (CPU 포화)
    ↓
RefreshToken DB UPDATE (Connection Pool 고갈)
    ↓
JWT 키 재생성 (GC pressure)
    ↓
응답시간 2~4초로 급증
```

---

## 6. 개선 제안

| 순위 | 개선안 | 기대 효과 |
|------|--------|----------|
| 1 | RefreshToken 저장을 DB → Redis로 이전 | DB UPDATE 제거, Pool 병목 80% 해결 |
| 2 | BCrypt cost factor 10 → 8 조정 | 로그인 속도 2배 개선 |
| 3 | JWT SecretKey 캐싱 | JWT 생성 2~3배 가벼워짐 |
| 4 | Login 트랜잭션 readOnly 분리 | flush/commit 비용 감소 |
| 5 | UserRepository.findByEmail projection 기반 경량화 | 매핑 비용 감소 |

---

## 7. 체크리스트

| 항목 | 상태 | 비고 |
|------|------|------|
| 응답시간 증가 | ⚠ | BCrypt + DB UPDATE 병목 |
| HTTP 오류 없음 | ✅ | timeout/5xx 없음 |
| CPU 포화 | ⚠ | 100 VU 이상 100% |
| GC 증가 | 🟡 | 키 재생성 영향 |
| Connection Pool 포화 | ⚠ | 10개 고정, 대기 증가 |
| RPS 정체 | ⚠ | 포화 상태 진입 |

---

## 정리

1. **BCrypt + DB UPDATE + JWT 생성**이 동시에 병목으로 작용
2. 100 VU 이상에서 **CPU/Connection Pool 포화** 확인
3. HTTP 오류는 없지만 **응답시간이 초 단위로 증가**
4. **RefreshToken Redis 이전**이 가장 효과적인 개선안
5. 로그인 API는 **CPU-bound + DB-bound + GC pressure**가 겹치는 전형적 패턴

---

## 참고

- K6 Load Testing: https://k6.io/
- HikariCP: https://github.com/brettwooldridge/HikariCP
- BCrypt Cost Factor: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
