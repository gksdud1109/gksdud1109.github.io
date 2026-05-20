---
title: "분산 환경 발급 한도 카운트 전략 - 카운터 row의 함정과 RAC Cache Fusion"
date: 2026-05-20 22:00:00 +0900
categories: [Spring]
tags: [backend, oracle, concurrency, rac, distributed-system, design]
---

> 큰 캡(cap)이 걸린 외부 연동 발급 API 를, 여러 애플리케이션 인스턴스 + Oracle RAC 환경에서
> 발급마다 한도 체크를 어떻게 할지에 대한 학습용 설계 검토 기록이다
>
> 결론: 겉보기에는 저렴한 카운터 row 가 분산 환경에서는 불리할 수 있다.
> 정답은 측정 전 재설계가 아니라, 트레이드오프를 정확히 이해하고 가장 단순한 충분해를 고르는 것.

> 예제 도메인/식별자는 학습용 가상 구성이다.

---

## 1. 배경 / 제약

| 항목 | 값 |
|---|---|
| 기능 | 외부 연동 발급 API. tenant별 큰 발급 한도 |
| 앱 | 여러 애플리케이션 인스턴스 (무상태, 공유메모리 없음) |
| DB | 단일 논리 Oracle, RAC 구성 |
| 캐시 인프라 | 외부 캐시 없음 |
| 한도 정책 | 예시 조건에서는 약간의 초과를 허용하는 soft limit |

핵심 코드 흐름(발급 1건):

```text
멱등성 조회(UK seek)         -- hit 이면 early return (한도체크 안 함)
→ checkLimit                  -- SELECT COUNT(*) WHERE TENANT_ID=?  ★ 매번
→ insert (신규 발급)
→ 잔여 임계점 알림 (approx 프리필터 후, 임계점 근처면 2차 COUNT)
```

문제의 초점: **`SELECT COUNT(*) WHERE TENANT_ID = ?` 가 발급마다 실행된다.**

---

## 2. 문제 정의

`TENANT_ID` 가 선두 컬럼인 인덱스를 사용하고, 해당 tenant의 매칭 엔트리를 모두 세는 실행계획이라면 **tenant 전체 인덱스 엔트리를 스캔**한다.

- 초반(1천건): 무시 가능
- 후반(대량 누적): 인덱스 리프 다수 블록을 읽게 되어 발급 경로의 주요 비용이 될 수 있음
- 발급마다 O(workspace_size) → 워크스페이스 생애 누적 **O(N²)**

→ 발급마다 COUNT 하는 구조는 tenant 데이터가 쌓일수록 비싸지는 패턴이다.

여기서 흔히 나오는 제안은 **카운터 컬럼/row 하나를 두고 +1 하면 O(1)** 이라는 접근이다.
이 방식이 분산 환경에서 어떤 비용을 만드는지가 이 글의 핵심이다.

---

## 3. 먼저 갈라야 할 것 — 정확성 vs 성능, 그리고 DBMS 보장의 범위

> 동시에 DB 요청이 들어와도 DBMS가 모두 같은 수준으로 직렬화해주는 것은 아니다.

DB 가 직렬화·보장해주는 것과 아닌 것을 구분해야 한다.

| 연산 | DB가 직렬화/보장? |
|---|---|
| `UPDATE ... SET STATUS=1 WHERE SAMPLE_CODE=? AND STATUS=0` (중복사용 방지) | ✅ row 배타락 + write-consistency restart → RAC 전역 보장 |
| 멱등성 UNIQUE 제약 충돌 | ✅ UK 가 클러스터 전역 강제 |
| **`SELECT COUNT(*)` 기반 한도 체크** | ❌ **스냅샷 read, 락 아님.** 여러 인스턴스가 동시에 `count < limit`을 읽고 통과할 수 있음 |

→ 현재처럼 비락 COUNT로 먼저 확인한 뒤 INSERT하는 구조에서는 한도 체크가 **근사적**이다. 조건부 UPDATE, 카운터 row, 직렬화 설계로 더 정확하게 만들 수는 있지만 그만큼 비용이 생긴다. 이 예제는 soft limit을 허용한다고 가정하므로 남은 초점은 **성능/확장성**이다.

---

## 4. 주요 대안 비교

### A. 현행 — `COUNT(*)` 매번

- 비용: O(N) 인덱스 스캔
- **락 없음 → 병렬 read 가능** (여러 인스턴스 동시 COUNT 가능, 단 CR/read 비용은 측정 필요)
- 단점: 워크스페이스가 찰수록 비싸짐(O(N²) 누적)

### B. 단일 카운터 row +1 ← 함정

```sql
UPDATE limit_counter SET cnt = cnt + 1 WHERE tenant_id = ?
```

**hot row 발생:**

- Oracle 은 이 **한 row 에 배타적 row 락**을 commit 까지 유지
- 다른 트랜잭션은 그 row 를 만지려면 앞 트랜잭션 commit 까지 **대기**
- 여러 인스턴스가 같은 tenant 카운터를 동시에 +1 → 병렬이 아니라 **한 줄 서기**:

```text
T1 락 → +1 → commit → 해제 → T2 락 → … → T10
```

**핵심 통찰: 비효율의 원인은 race condition 자체가 아니라, race 를 막기 위해 발생하는 배타 락의 직렬화다.**

| | |
|---|---|
| race condition | 락이 **없애줌** (카운터는 오히려 정확해짐) |
| 비효율 원인 | 그 정확성을 위한 **배타 락 = 동시 요청 직렬화** |

COUNT 는 락 없이 병렬인데, 카운터는 한 row 락에 모두 줄 선다. **O(1) 인데 직렬화 / O(N) 인데 병렬** — 둘은 다른 축의 비용이다.

### B-1. RAC 가 직렬화에 얹는 추가 비용 (악화 지점)

단일 인스턴스: 락 핸드오프가 한 노드 메모리 안 → 빠름(commit/redo 가 지배).

**RAC 구성:**

- 카운터 row 는 한 데이터 블록. 발급이 양 노드로 들어오면
- 노드 A 가 블록 수정 → A 소유(dirty)
- 노드 B 가 같은 블록 수정하려면 → **인터커넥트로 블록을 A→B 전송 (Cache Fusion / block ping)**
- 증가마다 노드가 번갈면 → 매 +1 에 **네트워크 왕복**. 메모리 락 핸드오프보다 수십~수백배 느림
- 증상: AWR 의 `gc buffer busy`, `gc current block` 대기 폭증

→ 한 row 직렬화에 노드 간 current block 전송과 global cache 대기가 추가될 수 있다. 실제 영향은 AWR/ASH의 `gc current block`, `gc buffer busy` 계열 대기로 확인한다. 그래서 겉보기 O(1) 카운터가 RAC 에서는 O(N) COUNT 보다 불리할 수 있다.

### C. 샤딩 카운터 (striped counter)

- 카운터를 1 row → K row 로 분할. 발급 시 랜덤/인스턴스-핀 샤드 +1. 읽을 땐 `SUM(K)`
- 경합을 K개 블록으로 분산 → RAC Cache Fusion 완화. 단, K개 row가 서로 다른 블록/파티션에 분산되도록 설계해야 효과가 난다. **인프라 추가 없음**
- 단점: 약간 복잡, 캡이 약간 근사 (이미 soft-limit 이라 무방)

### D. Oracle SEQUENCE (CACHE NOORDER) 캡 게이트 ← DB-only 최선

- `seq.NEXTVAL` 을 발급 순번으로 사용. `nextval > limit` 이면 거절
- **RAC 친화적**: 각 노드가 시퀀스 캐시 범위를 나눠 가짐 → 노드 간 경합 낮음
- 단점: 롤백/cache loss 시 gap(보수적 카운팅), 정확한 현재 잔여 조회는 어려움, tenant별 시퀀스면 운영부담
- 성공 발급 수가 limit을 넘지 않게 하는 상한 게이트로는 유력한 대안. 다만 gap 때문에 실제 잔여 수와 일치하지 않을 수 있다.

### E. 근사 / 주기 캐시

- 매번 안 셈. count 를 수초 캐시하거나 N건마다만 검사
- 비용이 가장 낮다. soft-limit 조건과 정합도 높다.
- 단점: 한도 오차 ↑ (이미 허용 범위)

### F. 풀(pool) 선발급 + SKIP LOCKED

- 한도 수만큼 row 를 미리 `available` 로 INSERT. 발급 = `available` 한 row 를 `issued` 로 UPDATE (`FOR UPDATE SKIP LOCKED`)
- 캡이 **구조적**(풀 크기) → 런타임 카운트 불필요. 락이 풀 전체 row 로 분산 → hot-row 완화
- 단점: 큰 설계 변경, 발급 의미 변경

### G. Redis `INCR` (가정 — 현재 인프라엔 없음)

- Redis 단일 스레드 명령 직렬화 → 락 대기 큐가 아닌 인메모리 원자 연산. 수십만 ops/sec
- **RDBMS hot-row + RAC Cache Fusion 병목 자체가 사라짐**
- 그러나 **병목이 사라지는 게 아니라 트레이드오프의 종류가 바뀜:**
  - 진실의 소스 이원화(Redis vs DB row) → 재조정 필요
  - 내구성(Redis 유실 시 한도 붕괴) → DB 재구축 경로
  - INCR(Redis)+INSERT(DB) = 2시스템 분산 쓰기, 트랜잭션 불가
  - 새 장애면 + 운영비(HA/모니터링/eviction)
- 정석 패턴: **Redis = 빠른 사전 게이트, DB = 권위 원장, 주기적 재조정.** 그 자체로 하나의 아키텍처
- **기능 하나를 위해 Redis를 도입하는 것은 측정된 필요가 있을 때만 정당화된다.**

---

## 5. 옵션 요약표

| | 원리 | 비용 | 동시성 | RAC | 인프라 |
|---|---|---|---|---|---|
| A COUNT(*) | 매번 인덱스 카운트 | O(N) | 병렬(락X) | hot row 쓰기 경합은 없음. CR/read 비용은 측정 필요 | X |
| B 카운터 row | 단일 row +1 | O(1) | **직렬화** | **악화(fusion)** | X |
| C 샤딩 카운터 | K row 분산 +1, SUM | O(1)+O(K) | 분산 | 완화 | X |
| D 시퀀스 캡 | NEXTVAL>limit 거절 | O(1) | 노드별 캐시 | **친화** | X |
| E 근사/주기 | 캐시·N건마다 | ~0 | 무관 | 무난 | X |
| F 풀 선발급 | available→issued | O(1) | 분산락 | 무난 | X |
| G Redis INCR | 인메모리 원자 | O(1) | 직렬(단일스레드, 빠름) | 무관 | **필요** |

---

## 6. 의사결정 원칙 (이게 진짜 배운 것)

1. **겉보기 비용이 낮아도 분산에선 비쌀 수 있다.** O(1) 카운터의 실제 비용은 연산 자체보다 **직렬화 + RAC 노드 간 블록 이동**에서 나올 수 있다. 복잡도 분석에 동시성/분산 축을 포함해야 한다.
2. **DBMS 보장의 범위를 구분해야 한다.** 락 기반 경로(UK, 조건부 UPDATE)는 DB가 직렬화·보장하지만, 비락 스냅샷 read(COUNT 한도)는 정확한 한도 보장을 자동으로 만들어주지 않는다.
3. **명백히 더 나은 대안이 없으면 재설계하지 않는다.** A↔B 는 트레이드(O(N) 병렬 vs O(1) 직렬+fusion). 측정 없는 전환은 추측 기반 최적화이며 RAC 에선 역효과 가능 → 과설계.
4. **요구사항(soft-limit 허용)과 정합하는 가장 단순한 해를 고른다.** 이미 한도 ±오차가 허용됐다면 정확성 비용을 더 지불할 이유가 없다.
5. **다음 액션은 코드가 아니라 데이터.** 발급 처리량/버스트 프로파일을 먼저 확인한다. 낮은 빈도라면 A(현행) 가 충분할 수 있다. 버스트로 측정상 병목이 확인되면 그때 **D(시퀀스 캡) → C(샤딩)** 순으로 무인프라 선에서 검토한다. Redis 는 실제 규모와 운영 준비가 있을 때만 고려한다.

---

## 7. 예시 조건에서의 결론

- **COUNT(*) 유지.** 예시 조건에서는 발급 빈도가 낮다고 가정하므로, 후반 COUNT 비용을 흡수할 수 있다. 가장 단순하고 코드 변경이 없다.
- 무비용 개선 1개만: 임계점 알림의 2차 COUNT 를 `previousCount + 1` 재사용으로 제거(신규 발급당 COUNT 1회로)
- 병목은 **측정으로 입증되기 전까지 재설계하지 않는다.** 입증되면 D(시퀀스 캡 게이트)부터 검토한다.

---

## 8. 한 줄 요약 / 일반화

> **분산 환경에서 카운트는 연산 복잡도(O(N) vs O(1))만이 아니라 경합 지점이 어디에 생기느냐로 평가해야 한다.**
> 단일 카운터 row 는 race 를 없애는 대신 동시성을 한 row 락에 묶어 직렬화하고, RAC 는 그 직렬화에 노드 간 네트워크를 얹어 악화시킨다.
> 겉보기 O(1)이 병렬 가능한 O(N)보다 느릴 수 있다. 그래서 측정 없는 재설계는 위험하다.

---

## 부록: 키워드

`hot block` · `RAC Cache Fusion` · `gc buffer busy` · `row lock serialization` · `striped/sharded counter` · `Oracle SEQUENCE CACHE NOORDER` · `FOR UPDATE SKIP LOCKED` · `snapshot read vs locking read` · `soft limit / eventual cap` · `premature optimization` · `측정 우선(measure first)` · `2-system consistency`

---

## 참고

- 별도 글: 「Oracle 인덱스 구조 원리」 (B+Tree, Cache Fusion 맥락)
- 별도 글: 「Oracle 실행계획 읽는 법」 (COUNT 비용·access vs filter)
- Oracle Database Concepts — *Real Application Clusters: Cache Fusion*
