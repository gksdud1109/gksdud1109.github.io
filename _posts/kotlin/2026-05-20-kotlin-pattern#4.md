---
title: "[Kotlin 패턴#4] 서비스 트랜잭션·동시성 방어 설계: @Transactional 경계 · TOCTOU · 가중 랜덤"
date: 2026-05-20 21:00:00 +0900
categories: [Kotlin]
tags: [programming, kotlin]
---

> [Kotlin 패턴#1~#3]에서 만든 초대 코드 발급 API의 사용(redeem) 서비스를 직접 작성해보며 확인한 5가지를 정리했다. `@Transactional` 경계와 커넥션 점유, 인덱스 풀스캔으로 오해하기 쉬운 RANGE SCAN, pre-check / race guard 이중 쿼리 의도, 가중 랜덤 추첨, 그리고 TOCTOU 방어까지. 예제 코드는 학습용으로 직접 구성했다.

---

## 살펴본 코드

초대 코드 사용(redeem) 서비스를 학습용으로 구성한 예시다. (인증 → 검증 → 추첨 → 사용 처리 → 외부 보상 적립)

```kotlin
@Service
class InviteRedeemService(
    private val authService: AuthService,
    private val repository: InviteRepository,
    private val configService: InviteRedeemConfigService,
    private val rewardClient: ExternalRewardClient,
    private val rewardLogRepository: RewardLogRepository,
    private val rewardPicker: RewardPicker,
) {
    companion object {
        private const val REWARD_TYPE = "POINT"
    }

    @Transactional
    fun redeem(
        request: InviteRedeemRequest.Redeem,
        servletRequest: HttpServletRequest,
    ): InviteRedeemResponse.Redeem {
        // 1. 인증 + 조회
        val session = getSession(servletRequest)
        val invite = getInvite(request.inviteCode)
        val config = configService.getConfig()

        // 2. 검증
        validateInvite(invite)
        validateRedeemLimit(invite.workspaceId, session.userId, config.redeemLimit)

        // 3. 보상 추첨 (EXTRA_VALUE 저장을 위해 사용 처리보다 먼저)
        val rewardPoint = rewardPicker.pick(config.rewardPolicy.items)

        // 4. 사용 처리 — 보상 금액도 같이 샘플 테이블의 EXTRA_VALUE에 저장(운영 조회 편의)
        markInviteRedeemed(invite, session.userId, rewardPoint)
        // race guard — 직후 한 번 더 카운트, 동시 사용으로 한도 초과면 롤백
        verifyRedeemLimitAfterMark(invite.workspaceId, session.userId, config.redeemLimit)

        // 5. 외부 보상 적립 + 이력
        val grantResult = grantReward(invite.policyId, session.userId, rewardPoint)

        return InviteRedeemResponse.Redeem(rewardPoint = grantResult.point)
    }

    // ===== 인증/조회 =====

    private fun getSession(servletRequest: HttpServletRequest): AuthSession.User =
        authService.getAuthentication(
            request = servletRequest,
            authLevel = AuthLevel.VERIFIED,
        ) as AuthSession.User

    private fun getInvite(inviteCode: String): InviteEntity =
        repository.findByInviteCode(inviteCode)
            ?: throw ApiException.inviteNotFound()

    // ===== 검증 =====

    private fun validateInvite(invite: InviteEntity) {
        if (invite.status) throw ApiException.inviteAlreadyUsed()
        if (LocalDateTime.now() > invite.expireAt) throw ApiException.inviteExpired()
    }

    /** 일/월 한도 사전 검증. 단일 쿼리로 두 카운트 모두 조회. */
    private fun validateRedeemLimit(
        workspaceId: String,
        userId: String,
        redeemLimit: InviteRedeemConfig.RedeemLimit,
    ) {
        val counts = repository.countUsedByUser(workspaceId, userId)
        redeemLimit.daily?.let { daily ->
            if (counts.daily >= daily) throw ApiException.redeemLimitExceeded()
        }
        redeemLimit.monthly?.let { monthly ->
            if (counts.monthly >= monthly) throw ApiException.redeemLimitExceeded()
        }
    }

    /**
     * markRedeemed 직후 race guard. 동시 사용으로 한도 초과 시 트랜잭션 롤백.
     * daily(예: 3) 만 검증 — race 로 초과 가능성이 실질적으로 높은 케이스.
     * monthly(예: 10) 는 동시 burst 로 11번 commit 되어야 잡혀서 가능성 ~0, 비용 대비 가치 낮음.
     */
    private fun verifyRedeemLimitAfterMark(
        workspaceId: String,
        userId: String,
        redeemLimit: InviteRedeemConfig.RedeemLimit,
    ) {
        val daily = redeemLimit.daily ?: return
        val dailyCount = repository.countUsedTodayByUser(workspaceId, userId)
        if (dailyCount > daily) throw ApiException.redeemLimitExceeded()
    }

    // ===== 처리 =====

    private fun markInviteRedeemed(invite: InviteEntity, userId: String, rewardPoint: Int) {
        // race 보호 — 영향 row 0 이면 동시 사용으로 이미 쓰임
        val updated = repository.markRedeemed(invite.inviteCode, userId, rewardPoint.toString())
        if (updated == 0) throw ApiException.inviteAlreadyUsed()
    }

    private fun grantReward(
        policyId: String,
        userId: String,
        point: Int,
    ): RewardGrantResult {
        // 외부 보상 적립 API
        val result = rewardClient.grant(
            RewardGrantRequest(
                userId = userId,
                point = point.toString(),
                policyId = policyId,
            )
        )

        // 적립 이력 저장
        rewardLogRepository.save(
            RewardHistory.Entry(
                policyId = policyId,
                userId = userId,
                rewardType = REWARD_TYPE,
                rewardValue = point.toString(),
            )
        )

        return result
    }
}
```

가중 랜덤 추첨기:

```kotlin
/** rewardPolicy.items 의 가중치(rate) 기반 random 추첨 */
@Component
class RewardPicker {

    private val random = SecureRandom()

    fun pick(items: List<InviteRedeemConfig.RewardItem>): Int {
        require(items.isNotEmpty()) { "rewardPolicy.items is empty" }

        val totalWeight = items.sumOf { it.rate }
        require(totalWeight > 0) { "rewardPolicy total weight must be > 0" }

        val roll = random.nextInt(totalWeight)
        var cumulative = 0
        for (item in items) {
            cumulative += item.rate
            if (roll < cumulative) return item.point
        }
        return items.last().point
    }
}
```

리포지토리(핵심 쿼리만):

```kotlin
@Mapper
interface InviteRepository {

    @Select(
        """
            SELECT * FROM SAMPLE_REDEEM WHERE INVITE_CODE = #{inviteCode}
        """
    )
    fun findByInviteCode(@Param("inviteCode") inviteCode: String): InviteEntity?

    /**
     * 사용 처리. STATUS=0 인 row 만 갱신되므로 동시 사용 race 안전.
     * EXTRA_VALUE 에 보상 금액 저장 (운영 조회용 — 코드 1회 조회로 보상 확인 가능).
     */
    @Update(
        """
            UPDATE SAMPLE_REDEEM
            SET STATUS = 1,
                USER_ID = #{userId},
                USED_AT = SYSDATE,
                EXTRA_VALUE = #{rewardPoint}
            WHERE INVITE_CODE = #{inviteCode}
              AND STATUS = 0
        """
    )
    fun markRedeemed(
        @Param("inviteCode") inviteCode: String,
        @Param("userId") userId: String,
        @Param("rewardPoint") rewardPoint: String,
    ): Int

    /**
     * 사용자의 오늘 + 이번 달 사용 카운트를 **단일 쿼리**로 조회.
     * 일/월 한도 pre-check 시 round-trip 1회로 두 값 확보.
     * 인덱스 (USER_ID, WORKSPACE_ID, STATUS) 활용 → 사용자당 ~수십 row 처리.
     */
    @Select(
        """
            SELECT
                COUNT(CASE WHEN USED_AT >= TRUNC(SYSDATE) THEN 1 END) AS DAILY,
                COUNT(*) AS MONTHLY
            FROM SAMPLE_REDEEM
            WHERE WORKSPACE_ID = #{workspaceId}
              AND USER_ID      = #{userId}
              AND STATUS       = 1
              AND USED_AT >= TRUNC(SYSDATE, 'MM')
              AND USED_AT <  TRUNC(ADD_MONTHS(SYSDATE, 1), 'MM')
        """
    )
    fun countUsedByUser(
        @Param("workspaceId") workspaceId: String,
        @Param("userId") userId: String,
    ): UserUseCount

    /** 사용자의 오늘(자정 기준) 사용 카운트. race guard 전용. */
    @Select(
        """
            SELECT COUNT(*) FROM SAMPLE_REDEEM
            WHERE WORKSPACE_ID = #{workspaceId}
              AND USER_ID      = #{userId}
              AND STATUS       = 1
              AND USED_AT >= TRUNC(SYSDATE)
              AND USED_AT <  TRUNC(SYSDATE) + 1
        """
    )
    fun countUsedTodayByUser(
        @Param("workspaceId") workspaceId: String,
        @Param("userId") userId: String,
    ): Int
}
```

## 자바 시선에서 확인할 5가지

1. `@Transactional` 범위가 길어질 때의 커넥션 점유 문제
2. `countUsedByUser`가 인덱스 풀스캔인지 확인하는 방법
3. `countUsedByUser`와 `countUsedTodayByUser`를 분리한 이유
4. `RewardPicker`의 누적 가중치 추첨 동작과 `return items.last()`의 의미
5. `validateInvite` → `markRedeemed` 사이의 TOCTOU 갭, pre-check `>=` vs race guard `>` 차이

---

## 1. `@Transactional` 경계 — 커넥션 점유 vs 원자성

**커넥션 점유 우려는 타당하다. 다만 예제에서는 의도된 트레이드오프다.** `redeem()` 전체가 한 트랜잭션이고 그 안에 외부 호출이 포함되어 있다.

```kotlin
@Transactional
fun redeem(...) {
    val session = getSession(servletRequest)   // ← 외부 인증 API
    val invite  = getInvite(...)                // DB
    ...
    markInviteRedeemed(invite, userId, rewardPoint)  // ① DB UPDATE
    verifyRedeemLimitAfterMark(...)                  // DB SELECT
    val result = grantReward(...)                    // ② 외부 적립 API + ③ DB INSERT(이력)
}
```

Spring 트랜잭션 범위 안에서 DB 작업이 시작되면 커넥션이 메서드 종료까지 오래 점유될 수 있다. 외부 호출 대기 시간이 그 범위에 포함되면 커넥션 풀 관점에서는 비효율 요소가 된다.

**이렇게 둔 이유 — 원자성이 더 중요해서:**

| 묶어야 하는 것 | 안 묶으면 |
|---|---|
| ① `markRedeemed`(EXTRA_VALUE 포함) + ③ `rewardLogRepository.save`(이력 INSERT) | 사용 처리와 이력 저장이 어긋나는 데이터 불일치 |
| ② 외부 적립 먼저 실패 → 전체 롤백 | 초대만 소진되고 보상 안 들어감 방지 |

→ ③(이력 INSERT)이 실패하면 ①(사용 처리)도 롤백돼야 일관성이 맞다. 그래서 한 트랜잭션.

**상쇄 근거 — 예제에서는 호출 빈도가 낮다고 가정한다:** 사용은 사용자 단위의 명시적 동작이고, 대량 발급처럼 한꺼번에 몰리는 경로가 아니라고 두었다. 이 조건에서는 원자성 확보 이득이 커넥션 점유 비용보다 크다고 판단할 수 있다.

👉 **개선 여지(현재 안 함):**

- `getSession`(인증)은 DB write와 무관 → **트랜잭션 밖(컨트롤러)에서 먼저** 하면 트랜잭션이 짧아진다. 의미 있는 리팩토링 포인트.
- `grantReward`의 외부 호출을 `@TransactionalEventListener(AFTER_COMMIT)`로 빼면 커넥션은 빨리 놓이지만, 커밋 후 보상 실패를 별도로 보정해야 한다. 지금 예제는 보상 실패 시 전체 롤백으로 일관성을 단순하게 유지하는 쪽을 택했다.

> 전형적 딜레마: **외부 API + 원자성 요구**가 동시에 있을 때. 단순함을 택하는 것도 합리적 선택이다.

## 2. `countUsedByUser`는 풀스캔이 아니다 — INDEX RANGE SCAN

**오개념 교정 — 이건 인덱스 풀스캔이 아니라 INDEX RANGE SCAN이다.** 둘은 완전히 다르다 (별도 글 「Oracle 실행계획 읽는 법」 1장 참고).

쿼리 WHERE 절:

```sql
WHERE WORKSPACE_ID = #{workspaceId}    -- 등치
  AND USER_ID      = #{userId}          -- 등치
  AND STATUS       = 1                  -- 등치
  AND USED_AT >= TRUNC(SYSDATE,'MM')    -- 범위
  AND USED_AT <  TRUNC(ADD_MONTHS(SYSDATE,1),'MM')
```

`IDX_SAMPLE_USER_STATUS(USER_ID, WORKSPACE_ID, STATUS)` 같은 인덱스가 있으면:

```text
INDEX RANGE SCAN
  → 선두 컬럼들(USER_ID, WORKSPACE_ID, STATUS)이 전부 등치(=)
  → 인덱스에서 이 사용자 + 이 워크스페이스 + STATUS=1 영역만 좁힘
  → 그 좁혀진 범위 안에서만 USED_AT 필터
```

| | 풀스캔 | 여기서 일어나는 일 |
|---|---|---|
| 읽는 양 | 전체 row | **사용자 1인의 그 워크스페이스 사용분만** (월 한도 10이면 수~수십 row) |
| 비용 | 전체 데이터 크기에 비례 | 사용자별 소규모 범위에 비례 |

→ 예제에서는 사용자 한 명이 한 워크스페이스에서 쓰는 초대 수가 작다고 가정한다. **인덱스가 그 사용자/워크스페이스로 핀포인트로 좁히기 때문에** 전체 데이터가 커져도 실제 건드리는 건 사용자별 소규모 범위다. 풀스캔 아님, 효율적.

> 인덱스 풀스캔(`INDEX FULL/FAST FULL SCAN`)은 *인덱스 전체*를 훑는 것이고, 여기는 *인덱스의 특정 좁은 구간만* 보는 `INDEX RANGE SCAN`. 운영 데이터에서 실행계획을 떠보면 `INDEX RANGE SCAN` + `access(USER_ID=.. AND WORKSPACE_ID=.. AND STATUS=..)`로 잡힌다.

## 3. 동일해 보이는 카운트 쿼리 두 벌 — pre-check vs race guard

각각 **역할이 다르고** 그래서 모양도 다르게 최적화했다:

| 쿼리 | 호출 위치 | 계산 대상 | 설계 의도 |
|---|---|---|---|
| `countUsedByUser` | pre-check | **일+월 카운트를 한 방에** (`CASE WHEN`으로 daily, `COUNT(*)`로 monthly) | 사전 검증은 두 한도 다 봐야 함 → **round-trip 1회로 2값** |
| `countUsedTodayByUser` | race guard | **일 카운트만** | markRedeemed 직후 재확인용. 가볍게 daily만 |

### (a) pre-check는 통합 쿼리로 round-trip 절약

```sql
SELECT COUNT(CASE WHEN USED_AT >= TRUNC(SYSDATE) THEN 1 END) AS DAILY,  -- 오늘
       COUNT(*) AS MONTHLY                                              -- 이번달(WHERE가 이미 이번달)
WHERE ... AND USED_AT >= TRUNC(SYSDATE,'MM') AND USED_AT < 다음달1일
```

WHERE가 **이번 달**로 범위를 좁히고(인덱스 RANGE SCAN), SELECT 절에서 `CASE WHEN`으로 그중 오늘 것만 추가 카운트. **같은 row 스캔 1번으로 일·월 둘 다** 산출. daily/monthly 따로 2번 SELECT를 1번으로 줄인 게 이거.

### (b) race guard는 daily만 — 의도적 비대칭

- 예제에서는 daily 한도가 더 작아 동시 클릭으로 초과될 가능성이 상대적으로 높다고 가정한다
- monthly 한도까지 매번 재검증하면 비용이 늘어나므로, 여기서는 daily만 재확인하도록 단순화했다

효율 관점에서는 pre-check 통합으로 왕복을 줄이고, race guard는 예제에서 필요한 daily만 둔다. 정확성과 비용을 분리해서 조절한 설계다.

## 4. RewardPicker — 누적 가중치 추첨

**누적 가중치(cumulative weight) 알고리즘.** 가중 랜덤의 표준 기법이다.

```kotlin
val totalWeight = items.sumOf { it.rate }   // 모든 rate 합
val roll = random.nextInt(totalWeight)      // 0 ≤ roll < totalWeight
var cumulative = 0
for (item in items) {
    cumulative += item.rate
    if (roll < cumulative) return item.point
}
return items.last().point                   // 방어적 안전망
```

예시로 `items = [{100p, rate=70}, {500p, rate=20}, {1000p, rate=10}]`:

```text
totalWeight = 70 + 20 + 10 = 100
roll = random.nextInt(100)  →  0 ~ 99 중 하나

수직선에 구간 매핑:
 [0 ─────────────── 69][70 ──── 89][90 ── 99]
   100p (cumulative 70)  500p(90)   1000p(100)
        70칸                20칸       10칸

roll=45 → 45 < 70           → 100p  당첨
roll=85 → 85 ≥70, 85 <90    → 500p  당첨
roll=97 → 97 ≥90, 97 <100   → 1000p 당첨
```

각 아이템이 차지하는 **구간 너비 = rate** → 뽑힐 확률 = `rate / totalWeight`. 70%/20%/10%. rate 합이 100이 아니어도 됨(`sumOf`가 정규화) — 예: rate가 7/2/1이어도 비율 동일.

**`return items.last()`는 사실상 도달 불가능한 방어 코드:** `roll < totalWeight`가 보장되고 마지막 `cumulative == totalWeight`라 루프 안에서 반드시 return된다. 정수 연산이라 부동소수점 오차도 없다. 그래도 컴파일러 만족 + 만일의 안전망으로 두는 것.

**`SecureRandom`을 쓰는 이유**: 일반 `Random`은 시드나 출력 패턴이 예측될 수 있다. 보상 추첨처럼 예측 불가성이 중요한 경로에서는 `SecureRandom`이 더 적합하다. ([Kotlin 패턴#3]의 초대코드 생성 논리와 같다.)

## 5. TOCTOU 방어와 경계 부등호 — 추가 설계 포인트

### ① 추첨을 `markInviteRedeemed` *앞*에 둔 순서

```kotlin
val rewardPoint = rewardPicker.pick(...)             // 3. 먼저 추첨
markInviteRedeemed(invite, userId, rewardPoint)      // 4. UPDATE 에 EXTRA_VALUE 같이
```

순서가 핵심이다. 추첨이 외부 적립 뒤에 있으면 `EXTRA_VALUE`에 확정 값을 함께 남기기 어렵다. **포인트 먼저 확정 → markRedeemed UPDATE에 EXTRA_VALUE 동시 기록 → 같은 트랜잭션** 순서라 사용 처리와 보상 금액 기록이 원자적으로 묶인다. 운영 조회도 단순해진다.

### ② TOCTOU 이중 방어 — `validateInvite` + `markRedeemed WHERE STATUS=0`

```kotlin
validateInvite(invite)       // status 체크 (시점 A)
...
markInviteRedeemed(...)      // UPDATE ... WHERE STATUS=0  (시점 B)
if (updated == 0) throw ApiException.inviteAlreadyUsed()
```

검증(A)과 사용(B) 사이에 동시 요청이 끼어 먼저 쓸 수 있음(TOCTOU = Time-Of-Check to Time-Of-Use 갭). `markRedeemed`의 `WHERE STATUS=0`이 **DB 원자적 조건부 UPDATE**라, 동시에 둘이 들어와도 한쪽만 `updated=1`, 다른 쪽은 `updated=0` → 예외. **사전 검증은 빠른 실패용, 실제 race 방어는 조건부 UPDATE**가 담당한다. 발급의 DB UNIQUE 제약 위임과 같은 철학이다.

### ③ pre-check `>=` vs race guard `>`

```kotlin
if (counts.daily >= daily) throw ...     // pre-check: 내 건 아직 미반영 → >=
if (dailyCount > daily) throw ...        // race guard: markRedeemed 후 내 1건 포함 → >
```

미묘하지만 정확한 경계다. pre-check는 내 사용 전이라 이미 daily 한도에 도달했다면 막아야 하므로 `>=`. race guard는 내 1건이 이미 카운트에 포함됐으니 초과(`>`)일 때만 롤백한다. off-by-one을 피하기 위한 경계다.

### ④ `as AuthSession.User` 다운캐스팅

```kotlin
sessionService.getAuthentication(... authLevel = AuthLevel.VERIFIED) as AuthSession.User
```

`AuthSession`은 sealed (Anonymous/User). `AuthLevel.VERIFIED`를 요구하니 익명일 수 없다는 가정 하에 강제 캐스팅. 가정이 깨지면 `ClassCastException`. 인증 정책이 보장하는 구조지만, 방어적으로 `as?` + 명시적 예외가 더 안전할 수도 있다(설계 토론거리).

### ⑤ cross-system consistency는 best-effort

외부 시스템 호출과 DB 쓰기를 하나의 로컬 트랜잭션으로 완전히 묶을 수는 없다. 분산 트랜잭션 없이 가는 구조라면 커밋 순서에 따라 보상 트랜잭션, 재처리, 멱등 API 같은 보정 설계가 필요할 수 있다. 이 예제에서는 해당 한계를 일반적인 cross-system consistency 문제로만 다룬다.

---

## 정리

| 질문 | 답 |
|---|---|
| `@Transactional` 경계 | 외부 호출까지 묶어 원자성을 챙김. 사용 빈도가 낮아 커넥션 점유 손해 수용 |
| countUsedByUser는 풀스캔? | ❌ INDEX RANGE SCAN. 사용자+워크스페이스+STATUS 등치로 인덱스가 핀포인트 좁힘 |
| 카운트 쿼리 두 벌 | pre-check는 일+월 통합(round-trip 절약), race guard는 daily만(비대칭 최적화) |
| 가중 랜덤 | 누적 합 기반 구간 매핑. `SecureRandom`으로 예측 불가성 확보 |
| TOCTOU 방어 | 사전 검증 + `WHERE STATUS=0` 조건부 UPDATE(DB 원자성에 위임) + `>=`/`>` 경계 분리 |

📌 한 줄 요약: 동시성 방어는 **DB가 원자적으로 보장하는 연산(UNIQUE, 조건부 UPDATE)에 위임** + **검증은 빠른 실패용, 실제 방어는 DB 조건부 쓰기** 두 축으로 설계한다.

---

## 다음 학습 포인터

1. **`CASE WHEN`을 SELECT 절에 넣은 조건부 집계** — `countUsedByUser`의 `COUNT(CASE WHEN ... THEN 1 END)`. 한 번 스캔으로 여러 분류 카운트를 동시에 뽑는 SQL 관용구. `GROUP BY` 없이 피벗하는 효과. round-trip 줄이는 무기가 된다.
2. **`require()` vs 도메인 예외** — `RewardPicker`는 `require(items.isNotEmpty())`(IllegalArgumentException), 서비스는 `ApiException`을 던진다. 같은 검증 실패라도 설정 오류는 `require`, 사용자 입력/비즈니스 위반은 도메인 예외로 나누는 기준을 확인하면 예외 설계 감이 잡힌다.
