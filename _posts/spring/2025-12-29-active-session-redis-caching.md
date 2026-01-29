---
title: "ActiveSession Redis 캐싱 - 인증 세션 최적화 전략"
date: 2025-12-29 12:00:00 +0900
categories: [Spring]
tags: [spring, redis, session, authentication, caching, performance]
---

## 개요

티켓팅 서비스에서 모든 API 요청마다 DB에서 ActiveSession을 조회하는 구조로 인해 성능 병목이 발생했다. 이 글에서는 **싱글 디바이스 로그인 정책**을 유지하면서 **Redis 캐싱을 통해 인증 성능을 최적화**한 과정과 설계 결정의 trade-off를 정리한다.

---

## 현재 인증/인가 - ActiveSession 구현 흐름

### 전체 흐름

모든 API 요청마다:

1. Access token 검증
2. 필요시 refresh token rotate
3. **activeSession(DB) 조회**
4. 싱글 디바이스 검증
5. SecurityContext 세팅 → 컨트롤러 진입

### ActiveSession DB 조회

```java
ActiveSession active = sessionGuard.requireActiveSession(userId);
```

여기서 `SELECT * FROM active_session WHERE user_id = ?` 실제 쿼리가 날아간다.
**매 요청마다 state(DB)를 다시 확인하는 구조**이다.

---

## 본질적인 Trade-off

### 요구사항

> **싱글 디바이스 강제**: 다른 기기에서 로그인했으면 즉시 기존 토큰을 죽이고 싶다(인증 차단)

이 요구사항을 만족하려면 **서버에 최신 상태 확인이 필연적**이다.
→ **Stateless 불가능**

### 서비스 트래픽 특성

실제 몰리는 트래픽은:
- 좌석 조회 / 선택
- 주문 / 결제
- 티켓 발급 / 확인

> 서비스 특성상 자주 발생하지 않을 보안 이벤트(로그인/기기 전환) 때문에 **모든 요청이 stateful로 검증**이 일어나고 있는 상태

---

## 선택지 분석

### 1. Access Token Stateless

```
Access Token 만료시간: 1시간 → 30분으로 단축
이미 발급된 Access Token은 만료될 때까지 활용
다음 갱신 시 차단
```

- **성능**: 가장 깔끔하고 성능적으로 최고
- **보안**: access token 만료시간에 의해 일시적인 중복 로그인이 허용되는 구조

### 2. Access Token Redis 캐싱

```
모든 요청에서 Redis GET activeSession
```

- **성능**: 개선 가능
- **단점**: Redis 의존도 과다, Redis 장애 시 SPOF 발생

### 3. 절충안 (선택)

```
Access Token에서도 검증은 하되, 매 요청마다 검증 X
Redis 캐싱 + TTL 기반으로 매번 검증에 제한
Refresh Token은 기존 DB 검증 유지
```

---

## 선택한 구조: Redis Cache + DB Fallback

### 설계 원칙

```
요청 → JWT 검증 (CustomAuthenticationFilter)
    → ActiveSessionCache.get()
        → Redis hit → 캐시 값 사용
        → Redis miss → DB 조회 → 새 값으로 Redis 캐싱
        → Redis 장애 → 모두가 공평하게 fast-fail
```

- **Redis가 떨어져도 Source of Truth는 DB** → 복구 가능
- Redis를 DB 세션의 TTL 기반 스냅샷으로 활용 (TTL 동안만 쓰는 사본)
- Redis 장애 시 DB fallback을 허용하면 DB 트래픽 폭증 → **fail-close 선택**

### Fail-open vs Fail-close

| 전략 | 설명 |
|------|------|
| Fail-open | 장애 시에도 일단 통과 (가용성 우선, 보안/정합성 위험) |
| Fail-close | 장애 시 차단 (보안/정합성 우선, 가용성 손해) |

> 티켓팅 서비스 특성상 **fail-close가 적합**

---

## 구현

### Redis KEY 구조

```java
active_session:{userId}
value = "{sessionId}:{tokenVersion}"

// TTL 설정: accessTokenDuration ± 10% (캐시 stampede 방지를 위한 Jitter)
```

### ActiveSessionCache

```java
public Optional<ActiveSessionDto> get(long userId) {
    String key = getKey(userId);

    try {
        // Redis에서 조회 시도
        String cached = redisTemplate.opsForValue().get(key);
        if (cached != null) {
            return Optional.of(deserialize(cached));
        }

        // Redis miss, DB에서 조회 후 캐싱
        Optional<ActiveSession> dbSession = activeSessionRepository.findByUserId(userId);

        if (dbSession.isPresent()) {
            ActiveSessionDto dto = ActiveSessionDto.from(dbSession.get());
            set(userId, dto); // 캐싱
            return Optional.of(dto);
        }

        return Optional.empty();

    } catch (Exception e) {
        // [Fast-fail] Redis 장애 시 즉시 예외 발생
        log.error("Redis failure detected for userId: {}, failing fast", userId, e);
        throw new ErrorException(AuthErrorCode.TEMPORARY_AUTH_UNAVAILABLE);
    }
}
```

### SessionGuard

```java
public void requireAndValidateSession(long userId, String sid, long tokenVersion) {
    ActiveSessionDto session = activeSessionCache.get(userId)
        .orElseThrow(() -> new ErrorException(AuthErrorCode.UNAUTHORIZED));

    if (!session.matches(sid, tokenVersion)) {
        throw new ErrorException(AuthErrorCode.ACCESS_OTHER_DEVICE);
    }
}
```

---

## 검증 결과

### Redis ↔ DB 동기화

| 시나리오 | Redis | DB | 정합성 |
|----------|-------|----|----|
| 로그인 | write-through (set) | saveAndFlush | 동기화 |
| 로그아웃 | evict | 유지 (재사용) | 정상 |
| 회원 탈퇴 | evict | soft delete | 동기화 |
| Token rotation | 유지 (불변) | 불변 | 동기화 |
| Cache miss | DB 조회 → set | - | 자동 복구 |

### 동시성 처리

| 시나리오 | 처리 방법 | 결과 |
|----------|-----------|------|
| 동시 로그인 (최초) | 비관적 락 + UniqueConstraint catch & retry | 안전 |
| 동시 API 요청 | Redis 단일 조회 (atomic) | 안전 |
| Multi-device 로그인 | session.rotate() → 기존 토큰 무효화 | 정상 |

### 장애 시나리오

| 장애 유형 | 동작 | 영향 |
|-----------|------|------|
| Redis 완전 장애 | fast-fail (503) | DB 과부하 방지 |
| Redis 일시 지연 | Exception catch → 503 | 안전 |
| Redis 복구 | Cache miss → DB fallback → 캐싱 | 자동 복구 |
| Cache stampede | TTL jitter (±10%) | 부하 분산 |

---

## 성능 개선 효과

### Before (DB 기반)

- 모든 API 요청: DB 조회 50ms
- 로그인 직후 첫 요청: DB 조회 50ms

### After (Redis 기반)

- 대부분 API 요청: Redis hit **1-2ms** (96% 단축)
- 로그인 직후 첫 요청: Redis hit **1-2ms** (96% 단축)
- Cache miss (드물게): DB 50ms + 재캐싱

---

## 보안 강도

| 보안 기능 | 상태 |
|-----------|------|
| Single-device 로그인 | 유지 (session.rotate()) |
| 즉시 다중 기기 차단 | 유지 (ACCESS_OTHER_DEVICE) |
| 회원 탈퇴 후 즉시 차단 | 강화됨 (캐시 무효화 추가) |
| Redis 장애 시 보안 | Fast-fail (503) |

---

## 정리

1. **싱글 디바이스 정책**을 유지하면서 성능 최적화 필요
2. **Redis를 캐시로 활용**, Source of Truth는 DB 유지
3. **Fail-close 전략**: Redis 장애 시 DB fallback 대신 503 응답
4. **TTL jitter**로 캐시 stampede 방지
5. 결과: **96% 응답 시간 단축** (50ms → 1-2ms)

---

## 참고

- [PR #274 - activeSession redis 캐싱 적용](https://github.com/prgrms-web-devcourse-final-project/WEB7_9_TxI_BE/pull/274)
