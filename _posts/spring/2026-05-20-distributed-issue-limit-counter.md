---
title: "분산 환경 발급 한도 카운트 전략 - 카운터 row의 함정과 RAC Cache Fusion"
date: 2026-05-20 22:00:00 +0900
categories: [Spring]
tags: [backend, oracle, concurrency, rac, distributed-system, design]
---

> 100만건 캡(cap)이 걸린 외부 연동 발급 API 를, WAS 10 인스턴스 + 단일 논리 Oracle(2노드 RAC) 환경에서
> 발급마다 한도 체크를 어떻게 할지에 대한 설계 검토 기록이다
>
> 결론: 싸 보이는 카운터 row 가 분산 환경에선 오히려 독이 될 수 있다.
> 정답은 측정 전 재설계가 아니라, 트레이드오프를 정확히 이해하고 가장 단순한 충분해를 고르는 것.

> 예제 도메인/식별자는 학습용 가상 구성이다.

---

## 1. 배경 / 제약

| 항목 | 값 |
|---|---|
| 기능 | 외부 연동 발급 API. 워크스페이스당 발급 한도 = 1,000,000 |
| 앱 | WAS 5대 × Tomcat 2 = **10 인스턴스** (무상태, 공유메모리 없음) |
| DB | 단일 논리 Oracle, **2노드 RAC** |
| 캐시 인프라 | **없음** (Redis 등 미보유) |
| 한도 정책 | "100만건 ± 약간 초과" 운영 허용 (soft limit) — 사전 합의됨 |

핵심 코드 흐름(발급 1건):

```text
멱등성 조회(UK seek)         -- hit 이면 early return (한도체크 안 함)
→ checkIssueLimit             -- SELECT COUNT(*) WHERE WORKSPACE_ID=?  ★ 매번
→ insert (신규 발급)
→ 잔여 임계점 알림 (approx 프리필터 후, 임계점 근처면 2차 COUNT)
```

문제의 초점: **`SELECT COUNT(*) WHERE WORKSPACE_ID = ?` 가 발급마다 실행된다.**

---

## 2. 문제 정의

`WORKSPACE_ID` 는 워크스페이스당 사실상 단일값 → `IDX_INVITE_WORKSPACE` 로 **그 워크스페이스 전체 인덱스 엔트리를 스캔**.

- 초반(1천건): 무시 가능
- 후반(~100만건): 인덱스 리프 수천 블록 = **수십 ms, 발급 경로 단일 최대비용**
- 발급마다 O(workspace_size) → 워크스페이스 생애 누적 **O(N²)**

→ "발급마다 COUNT" 는 워크스페이스가 찰수록 비싸지는 전형적 안티패턴.

여기서 흔히 나오는 반사적 제안: **"카운터 컬럼/row 하나 두고 +1 하면 O(1) 인데?"**
이게 분산 환경에서 왜 함정인지가 이 글의 핵심.

---

## 3. 먼저 갈라야 할 것 — 정확성 vs 성능, 그리고 "DBMS가 알아서 해주나?"

> "동시에 DB 요청 들어오면 어차피 DBMS 가 결정하는 구조 아닌가?"

DB 가 직렬화·보장해주는 것과 아닌 것을 구분해야 한다.

| 연산 | DB가 직렬화/보장? |
|---|---|
| `UPDATE ... SET STATUS=1 WHERE INVITE_CODE=? AND STATUS=0` (중복사용 방지) | ✅ row 배타락 + write-consistency restart → RAC 전역 보장 |
| 멱등성 UNIQUE 제약 충돌 | ✅ UK 가 클러스터 전역 강제 |
| **`SELECT COUNT(*)` 기반 한도 체크** | ❌ **스냅샷 read, 락 아님.** 10 인스턴스가 동시에 "count < limit" 읽고 다 통과 → 한도 ±N 초과 |

→ 한도 체크는 본질적으로 **근사**다. DBMS 가 정확하게 만들어주지 않는다. 다행히 이 프로젝트는 "100만 ± 약간"을 운영 허용으로 사전 합의 → **정확성은 이미 해결된 전제**. 그래서 남은 건 **성능/확장성** 문제뿐.

---

## 4. 옵션 전수 분석

### A. 현행 — `COUNT(*)` 매번

- 비용: O(N) 인덱스 스캔
- **락 없음 → 완전 병렬** (10 인스턴스 동시 COUNT OK, RAC 노드 간 경합 없음)
- 단점: 워크스페이스가 찰수록 비싸짐(O(N²) 누적)

### B. 단일 카운터 row +1 ← 함정

```sql
UPDATE workspace_counter SET cnt = cnt + 1 WHERE workspace_id = ?
```

**hot row 발생:**

- Oracle 은 이 **한 row 에 배타적 row 락**을 commit 까지 유지
- 다른 트랜잭션은 그 row 를 만지려면 앞 트랜잭션 commit 까지 **대기**
- 10 인스턴스가 같은 워크스페이스 카운터를 동시에 +1 → 병렬이 아니라 **한 줄 서기**:

```text
T1 락 → +1 → commit → 해제 → T2 락 → … → T10
```

**핵심 통찰: 비효율의 원인은 race condition 이 아니라, race 를 막으려고 거는 "배타 락의 직렬화" 다.**

| | |
|---|---|
| race condition | 락이 **없애줌** (카운터는 오히려 정확해짐) |
| 비효율 원인 | 그 정확성을 위한 **배타 락 = 동시 요청 직렬화** |

COUNT 는 락 없이 병렬인데, 카운터는 한 row 락에 모두 줄 선다. **O(1) 인데 직렬화 / O(N) 인데 병렬** — 둘은 다른 축의 비용이다.

### B-1. RAC 가 직렬화에 얹는 추가 비용 (악화 지점)

단일 인스턴스: 락 핸드오프가 한 노드 메모리 안 → 빠름(commit/redo 가 지배).

**RAC 2노드:**

- 카운터 row 는 한 데이터 블록. 발급이 양 노드로 들어오면
- 노드 A 가 블록 수정 → A 소유(dirty)
- 노드 B 가 같은 블록 수정하려면 → **인터커넥트로 블록을 A→B 전송 (Cache Fusion / block ping)**
- 증가마다 노드가 번갈면 → 매 +1 에 **네트워크 왕복**. 메모리 락 핸드오프보다 수십~수백배 느림
- 증상: AWR 의 `gc buffer busy`, `gc current block` 대기 폭증

→ "한 줄 서기"에 "매 차례 노드 간 블록 배송"까지 붙는다. **그래서 싸 보이는 O(1) 카운터가 RAC 에선 O(N) COUNT 보다 더 느려질 수 있다.** 전형적 RAC hot-block 안티패턴.

### C. 샤딩 카운터 (striped counter)

- 카운터를 1 row → K row(예: 16) 로 분할. 발급 시 랜덤/인스턴스-핀 샤드 +1. 읽을 땐 `SUM(K)`
- 경합을 K개 블록으로 분산 → RAC Cache Fusion 완화. **인프라 추가 없음**
- 단점: 약간 복잡, 캡이 약간 근사 (이미 soft-limit 이라 무방)

### D. Oracle SEQUENCE (CACHE NOORDER) 캡 게이트 ← DB-only 최선

- `seq.NEXTVAL` 을 발급 순번으로 사용. `nextval > limit` 이면 거절
- **RAC 친화적**: 각 노드가 시퀀스 캐시 범위를 나눠 가짐 → 노드 간 경합 없음, 매우 쌈
- 단점: 롤백 시 gap(과counting=보수적 캡이라 오히려 안전 방향), 정확한 "현재 잔여" 조회는 어려움, 워크스페이스별 시퀀스면 운영부담
- **하드 캡 게이트 용도로는 RAC 환경의 교과서적 정답**

### E. 근사 / 주기 캐시

- 매번 안 셈. count 를 수초 캐시하거나 N건마다만 검사
- 가장 쌈. **이미 합의된 soft-limit 과 정합도 가장 높음**
- 단점: 한도 오차 ↑ (이미 허용 범위)

### F. 풀(pool) 선발급 + SKIP LOCKED

- 100만 row 를 미리 `available` 로 INSERT. 발급 = `available` 한 row 를 `issued` 로 UPDATE (`FOR UPDATE SKIP LOCKED`)
- 캡이 **구조적**(풀 크기) → 런타임 카운트 불필요. 락이 풀 전체 row 로 분산 → hot-row 없음
- 단점: 큰 설계 변경, 발급 의미 변경

### G. Redis `INCR` (가정 — 현재 인프라엔 없음)

- Redis 단일 스레드 명령 직렬화 → 락 대기 큐가 아닌 인메모리 원자 연산. 수십만 ops/sec
- **RDBMS hot-row + RAC Cache Fusion 병목 자체가 사라짐**
- 그러나 **병목이 사라지는 게 아니라 트레이드의 종류가 바뀜:**
  - 진실의 소스 이원화(Redis vs DB row) → 재조정 필요
  - 내구성(Redis 유실 시 한도 붕괴) → DB 재구축 경로
  - INCR(Redis)+INSERT(DB) = 2시스템 분산 쓰기, 트랜잭션 불가
  - 새 장애면 + 운영비(HA/모니터링/eviction)
- 정석 패턴: **Redis = 빠른 사전 게이트, DB = 권위 원장, 주기적 재조정.** 그 자체로 하나의 아키텍처
- **기능 하나 위해 Redis 도입 = 측정된 필요 없는 인프라 추가 = 과설계**

---

## 5. 옵션 요약표

| | 원리 | 비용 | 동시성 | RAC | 인프라 |
|---|---|---|---|---|---|
| A COUNT(*) | 매번 인덱스 카운트 | O(N) | 병렬(락X) | 무난 | X |
| B 카운터 row | 단일 row +1 | O(1) | **직렬화** | **악화(fusion)** | X |
| C 샤딩 카운터 | K row 분산 +1, SUM | O(1)+O(K) | 분산 | 완화 | X |
| D 시퀀스 캡 | NEXTVAL>limit 거절 | O(1) | 노드별 캐시 | **친화** | X |
| E 근사/주기 | 캐시·N건마다 | ~0 | 무관 | 무난 | X |
| F 풀 선발급 | available→issued | O(1) | 분산락 | 무난 | X |
| G Redis INCR | 인메모리 원자 | O(1) | 직렬(단일스레드, 빠름) | 무관 | **필요** |

---

## 6. 의사결정 원칙 (이게 진짜 배운 것)

1. **"싸 보이는 것" 이 분산에선 비쌀 수 있다.** O(1) 카운터의 진짜 비용은 연산이 아니라 **직렬화 + RAC 노드 간 네트워크**. 복잡도 분석에 "동시성/분산" 축을 반드시 포함해야 한다.
2. **DBMS 가 다 해주지 않는다.** 락 기반 경로(UK, 조건부 UPDATE)는 DB가 직렬화·보장하지만, 비락 스냅샷 read(COUNT 한도)는 DB가 정확하게 만들어주지 않는다. "어차피 DB가" 라는 가정은 위험.
3. **명백히 더 나은 대안이 없으면 재설계하지 않는다.** A↔B 는 트레이드(O(N) 병렬 vs O(1) 직렬+fusion). 측정 없는 전환은 추측 기반 최적화이며 RAC 에선 역효과 가능 → 과설계.
4. **요구사항(soft-limit 허용)과 정합하는 가장 단순한 해를 고른다.** 이미 한도 ±오차가 허용됐다면 정확성 비용을 더 지불할 이유가 없다.
5. **다음 액션은 코드가 아니라 데이터.** 발급 처리량/버스트 프로파일을 먼저 확인. 트리클이면 A(현행) 가 최선. 버스트로 측정상 병목이 확인되면 그때 **D(시퀀스 캡) → C(샤딩)** 순으로 무인프라 선에서 검토. Redis 는 진짜 스케일 + 인프라 기보유 시에만.

---

## 7. 현 프로젝트 결론

- **현행 COUNT(*) 유지.** 외부 서버-서버 발급은 트리클 트래픽으로 추정 → 후반 수십 ms COUNT 흡수 가능. 가장 단순, 코드 변경 0
- 무비용 개선 1개만: 임계점 알림의 2차 COUNT 를 `issuedBefore+1` 재사용으로 제거(진짜 신규 발급당 COUNT 1회로)
- 병목은 **측정으로 입증되기 전까지 재설계하지 않는다.** 입증되면 D(시퀀스 캡 게이트)부터

---

## 8. 한 줄 요약 / 일반화

> **분산 환경에서 "카운트"는 연산 복잡도(O(N) vs O(1))만이 아니라 "경합 지점이 어디에 생기느냐"로 평가해야 한다.**
> 단일 카운터 row 는 race 를 없애는 대신 동시성을 한 row 락에 묶어 직렬화하고, RAC 는 그 직렬화에 노드 간 네트워크를 얹어 악화시킨다.
> "싸 보이는 O(1)"이 "병렬 가능한 O(N)"보다 느릴 수 있다 — 그래서 측정 없는 재설계는 최적화가 아니라 도박이다.

---

## 부록: 키워드

`hot block` · `RAC Cache Fusion` · `gc buffer busy` · `row lock serialization` · `striped/sharded counter` · `Oracle SEQUENCE CACHE NOORDER` · `FOR UPDATE SKIP LOCKED` · `snapshot read vs locking read` · `soft limit / eventual cap` · `premature optimization` · `측정 우선(measure first)` · `2-system consistency`

---

## 참고

- 별도 글: 「Oracle 인덱스 구조 원리」 (B+Tree, Cache Fusion 맥락)
- 별도 글: 「Oracle 실행계획 읽는 법」 (COUNT 비용·access vs filter)
- Oracle Database Concepts — *Real Application Clusters: Cache Fusion*
