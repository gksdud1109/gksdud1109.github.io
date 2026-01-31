---
title: "[성능테스트] 좌석 선택 API 동시성 제어 전략 비교 - Optimistic Lock vs CAS vs Redisson"
date: 2026-01-19 16:00:00 +0900
categories: [Spring]
tags: [spring, performance, k6, concurrency, optimistic-lock, cas, redisson, jpa]
---

# 동시성 비교실험: 3가지 구현 전략 분석

좌석 선택 API에서 동시 요청이 몰릴 때 어떤 동시성 제어 전략이 가장 효과적인지 비교 실험을 진행했습니다.

---

## 1. 실험 목적

좌석 선택 구간에서 동시 요청이 몰릴 때:
- **정합성**(1좌석 1유저)과 **공정성**을 유지하고
- **시스템 자원 사용량**(JVM/DB) 및 **tail latency**(p95~p99)를 안정적으로 제어할 수 있는 전략을 선택한다.

### 비교 대상 (동일 브랜치)

| 전략 | 설명 |
|------|------|
| **Opt-only** | JPA Dirty Checking + Optimistic Lock 예외 처리 |
| **CAS + Opt** | DB 원자적 상태 전이(`UPDATE ... WHERE status=...`) + 버전 증가 |
| **Redisson 추가** | 분산 락 선점 후 트랜잭션 실행 |

---

## 2. 응답 성능 결과 (k6, avg/p95/p99)

### 시나리오 1: VU=100

| 구분 | avg | p95 | p99 |
|------|-----|-----|-----|
| Opt-only | 110ms | 233ms | 769ms |
| CAS + Opt | 88ms | 173ms | 209ms |
| Redisson 추가 | 95ms | 190ms | 264ms |

### 시나리오 2: VU=500

| 구분 | avg | p95 | p99 |
|------|-----|-----|-----|
| Opt-only | 237ms | 1s | 1s |
| CAS + Opt | 210ms | 1s | 1s |
| Redisson 추가 | 443ms | 2s | 5s |

### 분석

- **VU=100**: CAS+Opt가 가장 안정적인 tail latency
- **VU=500**: Redisson은 p99이 5s까지 늘며 tail latency가 크게 악화, CAS+Opt가 가장 일관적

---

## 3. JVM/DB 관측 결과

### A. Opt-only vs CAS

> **핵심: Opt-only의 시스템 비용이 더 큼**

Opt-only는 구조적으로 충돌이 커밋 시점에 터지기 쉬워, 경쟁이 심해질수록 실패 요청이 오래 살아남으며 자원 비용이 커졌다.

#### CPU
- **Opt-only**: 60% 이상 유지
- **CAS**: 50% 미만 유지
- → Opt-only는 트랜잭션을 오래 끌고 가다가 커밋에서 실패해 낭비가 커짐

#### Heap / GC
- **Opt-only**: heap 120MB 이상 유지, GC pause 최대 10ms
- **CAS**: heap 120MB 미만(100MB선 증감), GC pause 최대 5ms
- → 실패 요청이 빨리 종료되지 못하고 트랜잭션/영속성 컨텍스트에 머물며 메모리/GC 부담 증가

#### DB pending thread
- **Opt-only**: peak 178
- **CAS**: peak 154
- → CAS는 DB에서 0/1 rows로 빠르게 결론이 나며 DB 대기열 스파이크가 작음

---

### B. CAS vs Redisson

> **DB 보호 기대 대비 오버헤드가 커짐**

Redisson은 "DB로 가는 트래픽을 약간 줄이는 대신" 락 경합/대기 비용 + Redis 의존성이 추가되는 구조라, 전체 시스템 관점에서는 오히려 오버헤드 패턴이 관측됐다.

#### CPU
- **CAS**: 50% 미만 유지
- **Redisson**: 60% 수준, peak 80%
- → 락 경합/스레드 대기 비용 증가

#### Heap / GC
- **CAS**: 120MB 미만 안정
- **Redisson**: 120→160MB 완만 증가
- GC pause 최대치는 5ms로 비슷하나 **빈도/지속이 더 김**
- → 락 대기/처리 지연으로 객체 생존 시간이 늘어난 전형적 패턴

#### DB pending thread
- peak 수치 차이는 작음(약 155 vs 140)
- 하지만 Redisson은 **pending 분포가 더 오래 유지(꼬리 길어짐)**
- → 순간 peak 억제는 되지만 전체 처리 완료 시간이 늘며 tail이 악화

---

## 4. 해석: 왜 이런 차이가 났나

### Opt-only (Dirty Checking 기반)

UPDATE가 커밋 시점에 실행되기 때문에, 경합 시 `ObjectOptimisticLockingFailureException`이 **커밋 단계에서 터져** try-catch로 제어가 어렵고, 실패 요청이 트랜잭션 자원을 오래 점유 → 결과적으로 **500으로 관측될 여지가 커짐**.

### CAS + Optimistic Lock

충돌을 "예외"가 아니라 **0 rows 업데이트 결과**로 모델링할 수 있어 **fail-fast**가 가능하고, 실패 요청이 빠르게 종료 → JVM/DB 비용과 tail latency가 안정화.

### Redisson

DB 보호 효과는 일부 있었지만, 고부하에서 락 대기 비용이 tail latency를 악화시키고 Redis 의존성과 운영 복잡도를 키움.

---

## 5. 결론 (최종 선택)

대기열 큐를 통해 좌석 선택 단계로 유입되는 동시 요청 수 자체가 제한된다.
따라서 **"더 큰 부하를 버티는 것"보다 정합성·공정성·예측 가능한 응답(특히 tail latency)** 을 우선 목표로 두었다.

### 제외된 전략들

**Opt-only 제외 이유:**
- 경합 시 커밋 단계 예외로 인한 자원 낭비가 커서 제외

**Redisson 제외 이유:**
1. tail latency 악화 (p99 증가)
2. Redis 의존성 및 장애 포인트 증가
3. 락 운영/튜닝/예외처리 등 코드 복잡도 증가

### 최종 선택

> **DB 원자적 CAS UPDATE + Optimistic Lock 기반의 fail-fast(409/경합 실패) 전략**

서버 보호는 락 대기보다는 **입장 제어(큐) + API 레벨 제한 정책**으로 해결하는 방향을 선택했다.

---

## 핵심 요약

| 전략 | 장점 | 단점 | 적합도 |
|------|------|------|--------|
| Opt-only | 구현 단순 | 커밋 시점 예외, 자원 낭비 | ❌ |
| CAS + Opt | fail-fast, 안정적 tail | - | ✅ **채택** |
| Redisson | DB 부하 일부 감소 | tail 악화, 운영 복잡도 | ❌ |
