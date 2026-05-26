---
title: "SEQUENCE가 한도 체크 도구로 적합한가 - 도구 의도 vs 사용 케이스 미스매치"
date: 2026-05-26 18:00:00 +0900
categories: [Database]
tags: [database, oracle, sequence, rac, concurrency, design]
description: "발급 한도 체크 비용을 줄이려고 SEQUENCE NEXTVAL을 떠올렸을 때 생기는 도구 의도와 사용 케이스의 미스매치를 정리한다. 5가지 옵션을 O(1) vs O(N) 너머의 비용 차원에서 비교한다."
---

> 발급마다 `COUNT(*)`가 무거우니 SEQUENCE NEXTVAL로 한도 체크하면 비용을 줄일 수 있지 않을까. 합리적으로 보이는 직관이지만, **SEQUENCE는 monotonic ID 생성 도구지 한도 체크 도구가 아니다.** 도구의 원래 의도와 지금 쓰려는 용도의 미스매치를 짚는 글이다.
>
> 「분산 환경 발급 한도 카운트 전략」 글의 후속편이다. 이 글은 **SEQ가 한도 도구로 어긋나는 이유**와 **카운터 테이블의 장단점**을 조금 더 좁혀서 본다.
>
> 예제 도메인/식별자는 학습용 가상 구성이다.

---

## 0. TL;DR

```
COUNT(*) 매번이 무겁다는 직관에서 출발한 3가지 대안:

  SEQ NEXTVAL 캡            → ❌ ID 생성 도구를 한도 도구로 — 의도 미스매치
  카운터 테이블 + UPDATE    → ✅ 정석에 가까움. 단 RAC hot-row 트레이드오프
  소프트 한도 (현행 COUNT)  → ✅ 단순함 우선

선택 기준:
  hard limit + 트래픽 견딜만 → 카운터 테이블
  hard limit + 고트래픽 RAC  → 샤딩 카운터 또는 SEQUENCE 캐시 게이트
  soft limit OK               → COUNT (단순)
  1인 1회 같은 UK 강제 케이스 → 한도 코드 자체 불필요
```

---

## 1. 동기 - 두 비용을 같은 차원으로 본 직관

발급마다 `SELECT COUNT(*) WHERE TARGET_ID = ?`가 인덱스 scan O(N)이라 부담된다는 인식 후, 자연스러운 가설:

> ID 생성에 쓰는 SEQUENCE도 atomic counter에 가깝다. 그 번호로 한도 체크하면 O(1) 아닌가?

→ **두 비용을 같은 차원에서 본 직관**이다. 맞는 부분과 놓친 부분을 나눠 봐야 한다.

---

## 2. SEQUENCE NEXTVAL vs COUNT(*) - 다른 차원의 비용

### 비교표

| 항목 | **SEQUENCE NEXTVAL** | **COUNT(*) by targetId** |
|---|---|---|
| 용도 | PK 생성 (monotonic ID) | 비즈니스 한도 체크 |
| 호출 시점 | 매 INSERT 1회 | 매 발급 요청 시 (검증용) |
| 비용 | 낮음 — cache 덕분에 대부분 메모리에서 처리 | **row 수에 비례** — 인덱스 있어도 range scan |
| Race condition | 없음 (Oracle atomic) | **있음** — count → insert 사이 race window |
| 분산 환경 우려 | 거의 없음 (RAC 노드별 cache range) | **있음** — race guard 필요 |
| 부담 변화 추이 | 트래픽 무관 (항상 가벼움) | 대상 누적 row 증가에 비례해 ↑ |
| 도구 의도 | 고유 번호 부여 (monotonic, never reuse) | 비즈니스 카운트 |

→ SEQUENCE 호출 비용과 COUNT 비용은 성격이 다르다. 같은 차원으로 비교하면 판단이 흐려진다.

### SEQUENCE가 분산환경에서 어떻게 동작하나

```
Oracle SEQUENCE의 cache 메커니즘:

  CREATE SEQUENCE SEQ_X CACHE 20;   -- 기본 캐시 크기 20

  RAC 노드 A:
    NEXTVAL 호출 → cache 에서 1~20 받아옴 → 클라이언트에 1
    NEXTVAL → 2
    ...
    cache 소진 → 다음 범위 21~40 받아옴

  RAC 노드 B:
    NEXTVAL 호출 → 노드 A 와 별개로 41~60 받아옴 (NOORDER 옵션 시)
    클라이언트에 41
    ...

→ 노드 간 충돌 없음. 노드별 cache range 분리.
→ 발급 순서는 1, 2, 41, 3, 4, 42, ... 같이 비순차 (NOORDER 면)
   ORDER 옵션 쓰면 노드 간 통신 → 비싸짐
```

이래서 SEQUENCE가 RAC 환경 표준. **단 이건 ID 생성에 한정.**

---

## 3. SEQ로 한도 체크 가설 검증

### 가설 A: 대상당 SEQUENCE + MAXVALUE 한도

```sql
-- 대상 생성 시
CREATE SEQUENCE SEQ_TARGET_OO MAXVALUE 1000;

-- 발급 시
DECLARE
  v_next NUMBER;
BEGIN
  SELECT SEQ_TARGET_OO.NEXTVAL INTO v_next FROM DUAL;
  -- v_next 가 1000 넘으면 ORA-08004 throw → 발급 실패
  INSERT INTO ... VALUES (v_next, ...);
END;
```

#### 장점

- DB atomic — race condition 없음
- COUNT(*) 비용 사라짐 — O(1)
- 한도 정확성 100% 보장

#### 단점 (이게 핵심)

```
1. 롤백 불가 — gap 누적
  - T1: NEXTVAL → 998 받음 → INSERT 시도
  - T2: NEXTVAL → 999 받음 → INSERT 시도
  - T1: INSERT 실패 (네트워크 오류) → 롤백

→ SEQ 값은 999 (998 영원히 사라짐)
→ 실제 발급 수 < SEQ 값
→ 한도 1000인데 실제 발급은 998에서 마감 (-2 손실)
→ 시간이 지나면 손실 ↑↑
```

| 단점 | 설명 |
|---|---|
| **롤백 불가 (gap)** | NEXTVAL 받고 INSERT 실패해도 그 번호는 영원히 소비됨. 실제 발급 수 < SEQUENCE 값 → 한도 일찍 도달 |
| **대상마다 DDL** | 대상 생성 시 SEQUENCE CREATE, 종료 시 DROP. 운영 부담 ↑ |
| **한도 변경 어려움** | `ALTER SEQUENCE MAXVALUE` 필요. 동적 한도 운영 까다로움 |
| **무제한 대상** | MAXVALUE 없는 SEQUENCE 만들면 일관성 깨짐 (한도 있는 대상과 같은 코드로 못 다룸) |
| **운영 가시성** | 현재 발급 수 / 한도를 운영자가 보기 어려움 (`USER_SEQUENCES.LAST_NUMBER`만으로는 gap 반영이 어려움) |

→ **SEQUENCE는 고유 번호 부여 도구이지 비즈니스 한도 강제 도구가 아니다.** 원래 설계 의도는 monotonic, never reuse, gap-tolerant에 가깝다.

### 가설 B: 전역 SEQUENCE로 대상별 한도 체크

→ 의미 없음. 전역 카운터로 대상별 한도 체크 불가.

### 가설 C: SEQUENCE + 별도 검증

```sql
-- NEXTVAL 받은 후 별도 CHECK
v_next := SEQ.NEXTVAL;
IF v_next > limit THEN
  ROLLBACK;
  RAISE limit_exceeded;
END IF;
```

→ 여전히 gap 문제. NEXTVAL 받은 시점에 이미 +1 소비.
→ SEQUENCE의 본질, 즉 **모든 NEXTVAL 호출은 영구히 소비된다**는 특성이 한도 체크 의도와 어긋난다.

---

## 4. 정석에 가까운 방식 - 카운터 테이블 + 조건부 UPDATE

### Schema

```sql
CREATE TABLE LIMIT_COUNTER (
    TARGET_ID  VARCHAR2(100) PRIMARY KEY,
    ISSUED_COUNT NUMBER DEFAULT 0,
    MAX_LIMIT    NUMBER         -- NULL = 무제한
);
```

### 발급 로직

```kotlin
// 한도 체크 + 카운트 증가 = 한 쿼리
val affected = counterRepo.tryIncrement(targetId)

// SQL 본문:
// UPDATE LIMIT_COUNTER
// SET ISSUED_COUNT = ISSUED_COUNT + 1
// WHERE TARGET_ID = ?
//   AND (MAX_LIMIT IS NULL OR ISSUED_COUNT < MAX_LIMIT)

if (affected == 0) throw LimitExceeded()
// 영향 row = 0 = 한도 초과로 통과 못 한 것. 정확.
```

### 평가표

| 항목 | 평가 |
|---|---|
| 비용 | ✅ O(1) — PK lookup + 1 row UPDATE |
| Race-safe | ✅ DB atomic. 동시 호출도 정확 |
| 롤백 | ✅ 트랜잭션 rollback 시 counter도 -1 (gap 없음) |
| 관리 부담 | ⚠️ 별도 테이블 + 발급/취소 시 counter 정합성 관리 |
| 무제한 대상 | ✅ `MAX_LIMIT IS NULL` 분기 |
| 한도 변경 | ✅ `UPDATE ... SET MAX_LIMIT = ?` 한 줄 |
| 운영 가시성 | ✅ `SELECT *` 한 줄로 현재 상태 명확 |

→ 정확한 한도, atomic update, O(1) 비용을 함께 얻는 전형적인 패턴이다.

### 단 - 분산환경의 주의점: Hot Row Problem

여기 카운터 테이블도 RAC 환경에선 **hot row 문제**가 있다.

```
시나리오: 여러 인스턴스가 동시에 같은 targetId 한도 체크/증가

  T=t      T1 시작 → SELECT ... FOR UPDATE → row 락 획득
  T=t+Δ    T2~Tn 시작 → 같은 row 락 시도 → 대기 (lock queue)
  T=t+2Δ   T1 commit → 락 해제
  T=t+3Δ   T2 락 획득 → 처리 → commit
  T=t+4Δ   T3 락 획득 → 처리 → commit
  ...

  → 요청을 동시에 받아도 같은 row 앞에서 직렬화됨
  → 대상당 동시처리율 = 1 / commit-time
```

#### RAC면 더 악화 - Cache Fusion

```
RAC 구성:
  카운터 row 는 한 데이터 블록 안에 있음.

  T1 (노드 A): row 수정 → 블록 dirty 상태로 A 메모리에 보관
  T2 (노드 B): 같은 row 수정 시도
    → 노드 B 가 노드 A 에게 해당 블록 요청
    → 노드 A 가 노드 B 로 블록 전송 (Cache Fusion via interconnect)
    → 노드 B 가 받아서 수정 → 다시 노드 B 메모리에 dirty
  T3 (노드 A): 같은 row 수정 → 또 transfer
  ...

  → 같은 블록이 노드 사이를 오가며 global cache 대기 증가
  → AWR 에서 `gc buffer busy`, `gc current block` 계열 대기 확인 가능
  → O(1) UPDATE라도 RAC hot row에서는 지연이 커질 수 있음
```

→ **카운터 테이블도 항상 충분한 것은 아니다.** 트래픽 양상에 따라 진화가 필요하다.

→ 이 부분은 「분산 환경 발급 한도 카운트 전략」 글의 주요 대안 비교와 연결된다.

---

## 5. 트래픽 양상별 선택 가이드

```
┌─────────────────────────────────────────────────────────────┐
│ 낮은 빈도 트래픽                                                │
│   → COUNT(*) (soft limit) 또는 카운터 테이블 둘 다 OK             │
│   → 단순함 우선 = COUNT(*)                                     │
├─────────────────────────────────────────────────────────────┤
│ 중간 규모 트래픽                                                │
│   → soft limit OK 면 COUNT(*) 가능                            │
│   → hard limit 필요하면 카운터 테이블                             │
│   → COUNT 가 누적되며 무거워지면 그때 카운터로 진화                   │
├─────────────────────────────────────────────────────────────┤
│ 높은 트래픽 + 단일 대상 집중                                      │
│   → 카운터 테이블이 hot-row 로 직렬화 시작                         │
│   → 샤딩 카운터 (1 row → K row 분산 +1, 읽을 땐 SUM)             │
│   → 또는 SEQUENCE CACHE NOORDER 캡 게이트                      │
├─────────────────────────────────────────────────────────────┤
│ 폭증 트래픽 + 핫 대상 + 정확 한도                                  │
│   → Redis INCR (단 인프라 비용 ↑)                               │
│   → 풀(pool) 선발급 패턴 (available → issued)                   │
│   → platform scale 영역                                      │
└─────────────────────────────────────────────────────────────┘
```

→ **현재 트래픽에 맞는 도구를 골라야 한다.** 미래 트래픽을 추측해서 미리 점프하면 over-engineering이 된다.

---

## 6. 한도 도구 의사결정 트리

```
한도 정책이 있는가?
├─ No (또는 UK가 자체 강제)
│   └─ 별도 한도 코드 X. UK + DuplicateKeyException 멱등 처리.
│
└─ Yes
    │
    ├─ soft limit (±N 초과 OK)?
    │   └─ Yes → COUNT(*)
    │       단점: 대상 누적 row 증가에 비례해 비용 ↑
    │       → 측정 후 비용 부담되면 다음 단계
    │
    └─ No (hard limit 필수)
        │
        ├─ 낮은 빈도 트래픽인가?
        │   └─ Yes → 카운터 테이블 + 조건부 UPDATE
        │
        ├─ 트래픽 중간 + 단일 대상 집중도 낮음?
        │   └─ Yes → 카운터 테이블 충분
        │
        ├─ 트래픽 고 + 단일 대상 집중도 높음?
        │   └─ Yes → 샤딩 카운터 (1 row → K row)
        │       또는 SEQUENCE CACHE NOORDER 캡 게이트
        │
        └─ 폭증 트래픽 + Redis 인프라 보유?
            └─ Yes → Redis INCR + DB 권위 원장
                또는 풀(pool) 선발급 패턴
```

---

## 7. 진화 경로 - Stage별 선택이 다름

```
[Stage 0] MVP / 낮은 빈도
  → COUNT(*) 사용. 단순함 우선. soft limit 합의.

[Stage 1] 트래픽 ↑ — COUNT 가 무거워지기 시작
  → 카운터 테이블로 진화.
  → 정확성도 같이 확보.

[Stage 2] 단일 대상 집중 ↑ — hot-row 문제 시작
  → 샤딩 카운터 또는 SEQUENCE 캡 게이트.
  → RAC Cache Fusion 완화.

[Stage 3] Platform scale
  → Redis INCR (사전 게이트) + DB 권위 원장 (재조정).
  → 또는 풀 선발급.
  → 인프라 + 운영 모델 추가.

→ 미래 Stage를 추측해서 미리 점프하면 over-engineering.
   현 Stage에 맞는 도구 선택, 측정으로 다음 Stage 트리거 확인.
```

---

## 8. 운영 관측성 비교 - 현재 상태 보기

| 도구 | 현재 발급 수 조회 | 한도 변경 |
|---|---|---|
| **COUNT(*)** | `SELECT COUNT(*) FROM ... WHERE TARGET_ID = ?` — 직관적 | config 변경 한 줄 |
| **카운터 테이블** | `SELECT ISSUED_COUNT, MAX_LIMIT FROM counter WHERE TARGET_ID = ?` — 즉시 | `UPDATE counter SET MAX_LIMIT = ?` |
| **샤딩 카운터** | `SELECT SUM(ISSUED_COUNT) FROM counter_shards WHERE TARGET_ID = ?` — K 합산 필요 | K shard 모두 한도 분할 |
| **SEQUENCE 캡** | `SELECT LAST_NUMBER FROM USER_SEQUENCES WHERE ...` — 운영자 SEQ 권한 + gap으로 부정확 | `ALTER SEQUENCE MAXVALUE` |
| **Redis INCR** | `GET target:OO:count` — 빠르나 DB 권위 원장과 재조정 필요 | Redis + DB 양쪽 |

→ **운영 관측성도 도구 선택의 중요 변수**다. 코드 측면의 O(1)만 보면 놓치는 비용이 생긴다.

---

## 9. 의도된 선택 사례 - Soft Limit + COUNT

학습용 예시에서는 다음과 같이 단순한 COUNT로 간다고 가정한다.

```kotlin
private fun checkTargetLimit(target: Target): Int {
    val limit = target.maxIssueCount ?: return 0   // null = 무제한
    val issued = repository.countByTarget(target.targetId)  // 매 발급마다 COUNT(*)

    if (issued >= limit) {
        throw InvalidTargetException()
    }
    return issued
}
```

### 의도된 trade-off

```
선택지 평가:
  ┌─────────────────────────────────────────────────────┐
  │ COUNT(*) 매번                                        │
  │   비용: 대상 row 누적에 비례 ↑                     │
  │   정확성: ±N race (soft limit 허용 가정)              │
  │   복잡도: 가장 단순                                  │
  │   → 낮은 빈도 트래픽 + soft limit 허용 → 단순함 우위 │
  └─────────────────────────────────────────────────────┘

  vs 카운터 테이블:
    비용: O(1) but 별도 테이블 정합성 관리 부담
    정확성: hard limit
    복잡도: 발급/취소 시 counter 같이 관리
    → 정합성 관리 부담 > 비용 절감 → 채택 X
```

이 선택은 **정확함보다 단순함을 우선한 의도적 절충안**이다. SEQ가 아니라 카운터 테이블이 실제 대안이고, 그것조차 아직 선택하지 않은 상태다.
→ 결정의 본질 = 현 Stage에서는 COUNT가 충분하고, 진화는 측정 후 진행한다는 패턴.

---

## 10. 또 다른 케이스 - 한도 체크 자체가 불필요한 경우

다음과 같은 정책이라면 한도 코드 자체가 dead code가 된다.

```
[1] 1인 1회만 (대상 종료까지)
  → UK (TARGET_ID, USER_ID) 가 자체 강제

[2] 대상 총량 제한 없음
  → 한도 체크 자체 불필요
```

```kotlin
// 이 경우 한도 체크는 사실상 이걸로 끝
repository.insert(entity)
  // UK 위반하면 DuplicateKeyException
  // → 멱등 응답 (ALREADY_REGISTERED) 처리
```

→ `countByTarget` 같은 카운트 메서드도 만들지 않는 게 낫다. 운영 통계용 카운트는 별개다. 실시간 트래픽 경로가 아닌 운영 조회라면 부하 성격도 달라진다.

**핵심 교훈: 한도 체크 도구 비교가 의미 있는 건 한도 정책이 있을 때만이다.** UK가 자체 차단하는 케이스엔 도구 비교 자체가 무의미하다.

---

## 11. 의사결정 원칙

1. **도구의 원래 의도를 살펴봐라.** SEQUENCE는 monotonic ID 생성용(gap 허용 + rollback 무관). 한도 체크 용도면 의도 미스매치가 생긴다.
2. **O(1) vs O(N)만 비교하지 마라.** 동시성·롤백·운영 가시성·gap·관리 부담 모두 비용 차원이다. 단순 시간 복잡도로만 비교하면 놓치는 비용이 생긴다.
3. **DB가 정확하게 해주는 것과 해주지 않는 것을 구분한다.**
   - Atomic operation (UK, 조건부 UPDATE) → DB가 정확 보장
   - Snapshot read (COUNT) → DB가 정확 보장 안 함 (race 발생)
4. **요구사항이 정확한 한도를 요구하는지부터 확인.** soft-limit 허용이면 COUNT가 충분. 정확해야 하면 카운터 테이블. 트래픽에 따라 샤딩.
5. **현재 Stage에 맞는 도구 선택.** 미래 Stage 추측해서 미리 점프 = over-engineering.
6. **측정 우선 (measure first).** 병목이 측정으로 입증되기 전까지 재설계하지 않는다.
7. **정말 한도 체크가 필요한가?** UK가 자체 차단하면 별도 한도 코드 불필요. 미리 만들면 dead code.

---

## 12. 자가 진단 체크리스트

```
[1] 한도 정책 자체가 있는가?
    □ No → 한도 코드 X (UK 멱등 처리)
    □ Yes → 다음 단계

[2] soft limit (±N 초과 OK) 허용인가?
    □ Yes → COUNT(*) 가장 단순
    □ No (hard limit) → 다음 단계

[3] 현재 트래픽이 낮은 빈도인가?
    □ Yes → 카운터 테이블
    □ No → 다음 단계

[4] 단일 대상에 트래픽 집중도가 높은가?
    □ No → 카운터 테이블 OK
    □ Yes → 샤딩 카운터 또는 SEQUENCE 캡 게이트

[5] RAC 환경인가?
    □ Yes + 단일 대상 집중 → Cache Fusion 위험. 샤딩 필수
    □ No → 카운터 테이블 안전

[6] Redis 등 분산 캐시 인프라가 이미 있는가?
    □ Yes + 폭증 트래픽 → Redis INCR + DB 권위 원장
    □ No → 인프라 추가 비용 > 효익 가능성 큼

[7] 운영자가 현재 발급 수를 자주 보는가?
    □ Yes → SEQUENCE 캡 게이트 권장 낮음 (gap으로 부정확)
    □ No → SEQUENCE 캡 게이트도 옵션
```

---

## 13. 정리표 - 5가지 옵션

| 패턴 | 비용 | Race-safe | 롤백 | 관리 부담 | 운영 가시성 | 추천 시점 |
|---|---|---|---|---|---|---|
| **SEQ (대상당)** | O(1) | ✅ | ❌ gap | ❌ DDL 폭증 | ❌ gap으로 부정확 | ❌ 한도 도구로 부적합 |
| **COUNT(*)** | O(N) (인덱스) | ❌ (soft limit) | ✅ | ✅ 단순 | ✅ 직관 | soft-limit 허용 + 낮은 빈도 |
| **카운터 테이블** | O(1) | ✅ | ✅ | ⚠️ 별도 테이블 | ✅ 즉시 | hard limit + 트래픽 견딜만 |
| **샤딩 카운터** | O(1)+O(K) | ✅ | ✅ | ⚠️ 복잡 | ⚠️ SUM 필요 | RAC + 고트래픽 |
| **Redis INCR** | O(1) | ✅ | ⚠️ 이원화 | ❌ 인프라 추가 | ✅ 빠름 | platform scale + Redis 보유 |

→ **SEQ로 한도 체크하는 방식은 표에서 가장 부적합하다.**

---

## 14. 한 줄 요약 / 일반화

> **SEQUENCE와 COUNT(*) 한도 체크는 다른 차원의 도구다.**
> SEQ는 monotonic ID 생성 (gap 허용 · rollback 무관), COUNT는 비즈니스 카운트 (정확 read).
> O(1)이라고 모두 같은 게 아니고, 롤백 없음 + gap 허용 + 대상별 DDL 같은 SEQ의 본질적 특성이 한도 도구로 부적합하게 만든다.
> **기본 대안은 카운터 테이블 + 조건부 UPDATE다. 단 RAC hot-row 트레이드오프로 트래픽 양상에 따라 샤딩/Redis로 진화한다.**

---

## 부록: 더 찾아볼 키워드

`Oracle SEQUENCE` · `CACHE NOORDER` · `monotonic counter` · `gap-tolerant` · `COUNT(*) by index range scan` · `snapshot read vs locking read` · `counter table + conditional UPDATE` · `hot row` · `RAC Cache Fusion` · `gc buffer busy` · `striped/sharded counter` · `soft limit / eventual cap` · `idempotency UK as natural limit` · `tool intent vs use case mismatch` · `measure first principle` · `stage-appropriate tooling`

---

## 참고

- Oracle Docs — *CREATE SEQUENCE*: <https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-SEQUENCE.html>
- Oracle Docs — *Cache Fusion in RAC*
- AWR Wait Events — *gc buffer busy*, *gc current block* (RAC 진단)
- Martin Kleppmann — *Designing Data-Intensive Applications* (Chapter 7: 트랜잭션, Chapter 9: 일관성)
- 별도 글: 「분산 환경 발급 한도 카운트 전략」 — 7가지 옵션(A~G) 비교
- 별도 글: 「Oracle 인덱스 구조 원리」 — COUNT(*) 비용의 인덱스 측 이해
