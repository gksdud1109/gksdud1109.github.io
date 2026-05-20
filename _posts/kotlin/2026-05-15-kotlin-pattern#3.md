---
title: "[Kotlin 패턴#3] 서비스 레이어로 보는 코틀린: 가시성·SecureRandom·컬렉션 람다·재시도·fire-and-forget"
date: 2026-05-15 23:00:00 +0900
categories: [Kotlin]
tags: [programming, kotlin]
---

> [Kotlin 패턴#1]·[#2]에서 만든 초대 코드 발급 API의 서비스 레이어를 직접 작성해보며 확인한 8가지를 정리했다. 가시성 제어자, `SecureRandom`, `firstOrNull`/`it`, `?:` vs `?.`, `?.let`, `repeat`, 재시도 패턴, 동기 fire-and-forget까지 코틀린 ↔ 자바 대비로 풀었다. 예제 코드는 학습용으로 직접 구성했다.

---

## 살펴본 코드

초대 코드 발급 서비스를 학습용으로 구성한 예시다. (멱등성 + 발급 한도 + 코드 충돌 재시도 + 잔여 알림)

```kotlin
@Service
class InviteService(
    private val repository: InviteRepository,
    private val configService: InviteConfigService,
    private val notificationService: NotificationService,
) {
    companion object {
        internal const val SAMPLE_CONFIG_KEY = "SAMPLE_INVITE"
        internal const val SAMPLE_POLICY_TYPE = "SAMPLE_POLICY"
        private const val MAX_CODE_RETRY = 3
        private const val NOTIFY_PROXIMITY = 10_000 // 예시 임계값
    }

    private val random = SecureRandom()

    fun create(request: InviteRequest.Create): InviteResponse.Create {
        debugLog("Create request: wsId=${request.workspaceId}, reqId=${request.requestId}")

        val config = configService.getConfig(SAMPLE_CONFIG_KEY, SAMPLE_POLICY_TYPE)
        config.validateActivePeriod()   // 운영 기간 검증

        val workspace = config.workspaces.firstOrNull { it.workspaceId == request.workspaceId }
            ?: throw ApiException.invalidWorkspace()

        // 1. 멱등성 조회 — hit 이면 한도 체크 없이 즉시 응답
        repository.findByIdempotencyKey(
            workspaceId = request.workspaceId,
            inviterId = request.inviterId,
            requestId = request.requestId,
        )?.let { existing ->
            debugLog("Idempotent hit: reqId=${request.requestId}, code=${existing.inviteCode}")
            return buildResponse(request.requestId, existing.inviteCode, existing.expireAt)
        }

        // 2. 발급 한도 체크 (신규 발급에만 적용)
        val issuedBefore = checkInviteLimit(workspace)

        // 3. 신규 발급 — 초대코드 UNIQUE 충돌 시 재시도
        val expireAt = LocalDate.now()
            .atTime(23, 59, 59)
            .plusDays(config.issuePolicy.expireDays.toLong() - 1)
        val inviteCode = insertWithRetry(workspace.policyId, request, expireAt)

        // 4. 발급 후 잔여 한도 알림 (실패해도 발급 결과에 영향 X)
        notifyLowStockIfNeeded(workspace, config.notification, issuedBefore)

        return buildResponse(request.requestId, inviteCode, expireAt)
    }

    private fun notifyLowStockIfNeeded(
        workspace: InviteConfig.Workspace,
        notification: InviteConfig.Notification,
        approxIssued: Int,
    ) {
        val limit = workspace.maxInviteCount ?: return    // null = 무제한
        val approxRemaining = limit - approxIssued

        // 임계점 위는 정확한 카운트 안함 → DB조회 없는 빠른 반환
        if (approxRemaining > NOTIFY_PROXIMITY) return

        val exactIssued = repository.countByWorkspace(workspace.workspaceId)
        notificationService.notifyLowStockIfThresholdHit(
            workspaceId = workspace.workspaceId,
            remaining = limit - exactIssued,
            notification = notification,
        )
    }

    private fun checkInviteLimit(workspace: InviteConfig.Workspace): Int {
        val limit = workspace.maxInviteCount ?: return 0    // null = 무제한
        val issued = repository.countByWorkspace(workspace.workspaceId)
        if (issued >= limit) {
            warnLog("Invite limit exceeded: wsId=${workspace.workspaceId}, issued=$issued, limit=$limit")
            throw ApiException.invalidWorkspace()
        }
        return issued
    }

    private fun insertWithRetry(
        policyId: String,
        request: InviteRequest.Create,
        expireAt: LocalDateTime,
    ): String {
        repeat(MAX_CODE_RETRY) { attempt ->
            val inviteCode = generateInviteCode()
            try {
                repository.insert(
                    InviteEntity.insert(
                        id = repository.getSequence(),
                        policyId = policyId,
                        workspaceId = request.workspaceId,
                        inviterId = request.inviterId,
                        requestId = request.requestId,
                        inviteCode = inviteCode,
                        expireAt = expireAt,
                    )
                )
                return inviteCode
            } catch (e: DuplicateKeyException) {
                // UK 위반 두 종류:
                //   - 멱등성 UK — 동시 race 로 다른 스레드가 먼저 INSERT 함
                //   - 초대코드 UK — 36^12 중 우연히 동일 코드 (극히 드뭄)
                repository.findByIdempotencyKey(
                    workspaceId = request.workspaceId,
                    inviterId = request.inviterId,
                    requestId = request.requestId,
                )?.let { existing ->
                    debugLog("Race resolved: reqId=${request.requestId}, code=${existing.inviteCode}")
                    return existing.inviteCode
                }
                warnLog("Invite code collision retry (attempt=${attempt + 1}): ${e.message}")
            }
        }
        throw IllegalStateException("Failed to generate unique invite code after $MAX_CODE_RETRY retries")
    }

    private fun buildResponse(
        requestId: String,
        inviteCode: String,
        expireAt: LocalDateTime,
    ) = InviteResponse.Create(
        requestId = requestId,
        invite = InviteResponse.Create.Invite.of(
            inviteCode = inviteCode,
            expireAt = expireAt,
        ),
    )

    private fun generateInviteCode(length: Int = 12): String {
        val chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        return (1..length)
            .map { chars[random.nextInt(chars.length)] }
            .joinToString("")
    }
}
```

## 자바 시선에서 확인할 8가지

1. `internal const val` / `private const val` 두 가지의 차이
2. `SecureRandom`과 `Random`의 차이, `private val`로 재사용하는 이유
3. `firstOrNull { it.workspaceId == ... }`에서 `firstOrNull`과 `it`의 의미
4. `?:`와 `?.`의 문법 차이
5. `?.let { existing -> ... }` 패턴의 동작 분해
6. `repeat`의 의미, stdlib 시그니처를 확인하는 방법
7. `insertWithRetry()`가 여러 번 시도하는 이유
8. `notifyLowStockIfNeeded()`를 동기 fire-and-forget으로 둔 이유

---

## 1. `internal const val` vs `private const val`

차이는 **가시성(visibility) 범위**뿐. `const val`(컴파일 타임 상수)인 건 동일하다.

```kotlin
companion object {
    internal const val SAMPLE_CONFIG_KEY = "SAMPLE_INVITE"      // 모듈 전체에서 보임
    internal const val SAMPLE_POLICY_TYPE = "SAMPLE_POLICY"
    private const val MAX_CODE_RETRY = 3          // 이 클래스 안에서만
}
```

| 제어자 | 보이는 범위 | 자바 근사 |
|---|---|---|
| `private` | 선언된 클래스 내부만 | `private` |
| `internal` | **같은 모듈**(같은 Gradle 모듈) 전체 | 자바엔 정확한 대응 없음 (≈ public-within-module) |

가시성을 결정하는 기준은 **실사용처**다.

- `SAMPLE_CONFIG_KEY`/`SAMPLE_POLICY_TYPE` → 같은 모듈의 다른 클래스에서 참조하는 샘플 상수이므로 `internal`.
- `MAX_CODE_RETRY` → `insertWithRetry()` 안에서만 → `private`로 최소 노출.

> 최소 가시성 원칙 — 필요한 만큼만 연다. `internal`이면 모듈을 분리할 때 이 참조가 모듈 경계를 넘는다는 사실이 가시성으로 드러난다.

## 2. `SecureRandom` vs `Random`, `private val`로 빼면 공유되는 원리

### SecureRandom vs Random

| | `java.util.Random` | `java.security.SecureRandom` |
|---|---|---|
| 시드 | 시스템 시간 등 예측 가능 | OS 엔트로피(`/dev/urandom` 등) |
| 예측 가능성 | 출력 몇 개 보면 다음 값 **예측 가능** | 암호학적으로 예측 불가 |
| 용도 | 게임, 시뮬레이션 | **초대코드·토큰·비밀번호** 등 보안 |
| 속도 | 빠름 | 상대적으로 느림 |

초대코드를 `Random`으로 만들면 공격자가 발급된 코드 몇 개로 **다음 코드를 추측 → 미발급 코드 탈취**가 가능하다. 그래서 `SecureRandom`을 쓴다.

### `private val random = SecureRandom()`로 빼면 공유되는 원리

`@Service` = Spring **싱글톤 빈** → `InviteService` 인스턴스가 앱 전체에 1개 → 그 안의 `random`도 1개. `generateInviteCode()`를 몇 번 호출하든 **같은 `SecureRandom` 인스턴스 재사용**.

매번 `SecureRandom()` 새로 안 만들고 필드로 빼는 이유:

- `SecureRandom()` 생성은 **엔트로피 수집 비용이 있다**. 호출마다 new 하면 불필요한 비용이 생긴다.
- 한 번 만들어 재사용하면 내부 엔트로피 풀을 이어 써서 효율적 + 안전.
- `SecureRandom`은 **thread-safe**(내부 동기화)라 싱글톤으로 여러 스레드가 동시에 `nextInt()`를 호출해도 안전.

[Kotlin 패턴#2]의 companion 가변 상태 경고와 달리, `SecureRandom`은 스스로 thread-safe라 싱글톤 빈에서 공유할 수 있다. 그래도 companion이 아닌 인스턴스 필드로 둔 건 서비스의 구현 세부사항이라는 소속을 명확히 하기 위해서다.

## 3. `firstOrNull { }` 와 `it`

```kotlin
val workspace = config.workspaces.firstOrNull { it.workspaceId == request.workspaceId }
```

`firstOrNull`은 코틀린 컬렉션 표준 함수: **조건을 만족하는 첫 원소를 반환, 없으면 `null`**.

- `config.workspaces` = `List<Workspace>`
- `{ it.workspaceId == request.workspaceId }` = 람다(조건). 원소를 하나씩 받아 `Boolean` 반환
- `it` = **람다의 단일 파라미터 암묵적 이름**. 파라미터가 1개면 이름을 안 짓고 `it`으로 자동 지정된다.

`it`을 풀어 쓰면:

```kotlin
config.workspaces.firstOrNull { ws -> ws.workspaceId == request.workspaceId }
//                             ws; 명시적 이름. 안 쓰면 it
```

자바 Stream 대응:

```java
config.getWorkspaces().stream()
    .filter(w -> w.getWorkspaceId().equals(request.getWorkspaceId()))
    .findFirst().orElse(null);   // firstOrNull = findFirst + orElse(null)
```

`find { }`(동일), `filter { }`(여러 개), `any { }`(존재 여부) 등이 같은 `it` 규칙을 따른다.

## 4. `?:` vs `?.` — 완전히 다른 연산자

```kotlin
val workspace = config.workspaces.firstOrNull { ... }
    ?: throw ApiException.invalidWorkspace()
```

| 연산자 | 이름 | 동작 |
|---|---|---|
| `?.` | safe call | 왼쪽이 **null이 아니면** 오른쪽 실행, null이면 **null 반환** |
| `?:` | elvis | 왼쪽이 **null이면** 오른쪽 실행/반환, null 아니면 **왼쪽 값** |

```kotlin
a?.b      // a == null → null,  a != null → a.b
a ?: b    // a == null → b,     a != null → a
```

여기선:

```kotlin
firstOrNull {...} ?: throw ...
// 결과 null (워크스페이스 못 찾음) → throw
// null 아님 (찾음)               → 그 Workspace 값을 workspace 에 할당
```

`throw`는 표현식이라 `?:` 오른쪽에 올 수 있다. 찾으면 값을 쓰고, 못 찾으면 예외를 던지는 흐름을 한 줄로 표현한다. 자바로 풀면 `...findFirst().orElseThrow(() -> new ...)` (≈ `?: throw`)에 가깝다.

> 구분법: `?.`는 **있으면 사용**, `?:`는 **없으면 대체**. 자주 같이 쓰인다: `a?.b ?: c` = `a`가 있으면 `a.b`, 그 결과가 null이면 `c`.

## 5. `?.let { existing -> ... }` 분해

```kotlin
repository.findByIdempotencyKey(...)
    ?.let { existing ->
        debugLog(...)
        return buildResponse(request.requestId, existing.inviteCode, existing.expireAt)
    }
```

단계 분해:

1. `findByIdempotencyKey(...)` → `InviteEntity?` (찾으면 엔티티, 없으면 `null`)
2. `?.` (safe call) — 결과가 **null이면 `let` 전체를 건너뜀**(다음 줄로). null 아니면 `let` 실행
3. `let { existing -> ... }` — 수신 객체를 람다 인자로 넘김. `existing` = 그 엔티티(non-null 확정)
4. 람다 안 `return` → **`create()` 메서드 자체를 종료** (멱등 히트면 즉시 응답 리턴)

```text
멱등키로 기존 발급 조회
 -> 없음(null) → ?. 가 let 스킵 → 아래 신규발급 로직으로 진행
 -> 있음        → let 진입, existing 으로 기존 코드 응답 후 return (메서드 종료)
```

`existing`은 `it`을 명시적으로 이름 지은 것(3번과 같은 규칙). 자바로는 `if (existing != null) { ... }`. 즉 `?.let { }` = **null 아닐 때만 이 블록 실행** 관용구다.

## 6. `repeat`와 `attempt` — stdlib 시그니처로 확인하기

```kotlin
repeat(MAX_CODE_RETRY) { attempt -> ... }
```

### `repeat` 정체

코틀린 stdlib 함수. 대략:

```kotlin
public inline fun repeat(times: Int, action: (Int) -> Unit) {
    for (index in 0 until times) {
        action(index)        // index = 0, 1, 2, ... times-1
    }
}
```

→ `repeat(3) { ... }` = 블록을 **3번 반복** 실행. for 루프의 축약.

### `attempt`의 의미

`repeat` 시그니처가 `action: (Int) -> Unit` — **람다가 `Int` 하나를 받는다**. 그 Int가 반복 인덱스(0,1,2). `{ attempt -> ... }`에서 `attempt`는 그 Int 파라미터에 붙인 이름.

- 안 쓰면 기본 이름 `it`: `repeat(3) { println(it) }` → 0,1,2
- 명시적 이름: `repeat(3) { attempt -> ... }` → `attempt` = 0,1,2

`warnLog("... (attempt=${attempt + 1})")`처럼 0부터 시작하는 인덱스를 로그에서는 1부터 시작하는 시도 횟수로 보여주려고 이름을 붙인 것이다.

### stdlib 동작 보는 법 (IDE)

1. `repeat`에 커서 → **Go to Declaration** (IntelliJ: `Ctrl+B` / macOS `Cmd+B`)
2. → 코틀린 stdlib `Standard.kt`의 `repeat` 정의로 점프
3. 시그니처 `(times: Int, action: (Int) -> Unit)`를 보면 두 번째 인자가 람다이고, 그 람다는 `Int`를 받는다는 사실을 확인할 수 있다

이 방법은 `firstOrNull`, `let`, `?.` 등 모든 stdlib에 동일하다. **모르는 코틀린 함수 만나면 선언으로 점프해 시그니처 확인**이 기본기다.

## 7. 로직 의도: `insertWithRetry`가 여러 번 시도하는 이유

재시도하는 이유 — **`inviteCode`가 랜덤이고 DB에 UNIQUE 제약**이 걸려 있기 때문이다:

| 충돌 종류 | 원인 | 재시도 의미 |
|---|---|---|
| **초대코드 UK 충돌** | `SecureRandom`으로 만든 12자리 코드가 우연히 이미 존재하는 코드와 겹침 (극히 드뭄) | **새 랜덤 코드로 다시 INSERT** → 재시도가 해결책 |
| **멱등성 UK 충돌** | 동시에 같은 `(workspace, inviter, requestId)` 요청이 race로 먼저 INSERT됨 | 재시도 대신 **기존 코드 조회해서 반환**(멱등 보장) |

`catch` 안에서 둘을 구분한다. 멱등키로 찾아지면(`?.let`) 그 코드 반환(동시 요청에 같은 응답), 안 찾아지면 순수 코드 충돌이니 다음 루프에서 새 코드로 재시도한다. 36^12는 약 4.7e18(약 474경)이므로 충돌 가능성은 매우 낮지만, UNIQUE 제약을 신뢰하고 예외 경로를 처리하는 편이 안전하다.

멱등성을 메모리(companion)에 두지 않고 **DB UNIQUE 제약 + `DuplicateKeyException` catch**에 위임하면 멀티 인스턴스/동시성에서도 안전하다. [Kotlin 패턴#2]에서 본 가변 상태는 DB에 위임한다는 원칙의 실제 구현이다.

## 8. `notifyLowStockIfNeeded`를 afterCommit으로 안 뺀 이유

전제 교정 — **`create()`엔 `@Transactional`이 아예 없다.** (발급은 단일 INSERT라 트랜잭션 불필요.)

→ `@TransactionalEventListener(AFTER_COMMIT)`은 일반적으로 트랜잭션 커밋 훅으로 쓰인다. 예제처럼 트랜잭션 경계가 없는 단일 INSERT 흐름에서는 afterCommit으로 분리할 대상이 명확하지 않다. 핵심은 **동기 호출 실패가 발급 결과를 깨뜨리지 않도록 격리했는가**다.

동기인데 안전한 이유 — **`NotificationService`가 fire-and-forget을 try-catch로 구현**한다. `sendSafely` 같은 내부 메서드가:

```kotlin
try {
    smsService.send(key)
} catch (e: Exception) {
    errorLog("Low stock notify exception ...", e)   // ← 예외를 삼킴 (다시 던지지 않음)
}
```

→ 알림이 실패/예외나도 `create()`로 예외가 안 올라간다. **트랜잭션 격리 대신 예외 전파를 차단하는 방식으로 격리**한 것이다.

비동기(큐/별도 스레드)로 안 뺀 이유는 **빈도 + 복잡도 트레이드오프**:

- 예시에서는 잔여 수량이 별도 임계점과 일치할 때만 알림을 보낸다고 가정한다.
- 호출 빈도가 낮은 보조 기능을 위해 비동기 인프라(스레드풀/큐/실패재처리)를 도입하면 복잡도가 더 커질 수 있다. 이 예제에서는 동기 + 예외격리로 충분하다고 본다.

| 격리 방법 | 이 코드의 선택 |
|---|---|
| `@Transactional` afterCommit | ❌ (트랜잭션 자체가 없음) |
| 비동기 큐/스레드 | ❌ (호출 빈도 극소 → 복잡도 대비 이득 없음) |
| **예외 내부 catch (fire-and-forget)** | ✅ 채택 — 단순하고 충분한 격리 |

---

## 정리

| 질문 | 답 |
|---|---|
| `internal` vs `private const val` | 둘 다 컴파일 타임 상수, 차이는 가시성(모듈 전체 vs 클래스 내부). 실사용처가 결정 |
| `SecureRandom` vs `Random` | 예측 불가(보안용) vs 예측 가능. 생성 비싸서 인스턴스 필드로 1회 생성·재사용, thread-safe |
| `firstOrNull`/`it` | 조건 만족 첫 원소 or null. `it` = 단일 람다 파라미터 암묵 이름 |
| `?.` vs `?:` | `?.` = 있으면 진행, `?:` = 없으면 대체. `?: throw`로 예외 처리 가능 |
| `?.let { }` | null 아닐 때만 블록 실행. 람다 안 `return`은 바깥 함수 종료 |
| `repeat`/`attempt` | stdlib for 축약. 람다는 인덱스(Int)를 받음 → 선언 점프로 시그니처 확인 |
| `insertWithRetry` | 랜덤 코드 + DB UNIQUE → 코드충돌은 재시도, 멱등충돌은 기존 반환 |
| 동기 fire-and-forget | 트랜잭션 없음 + 호출 극소 → 예외 내부 catch로 격리가 가장 단순·충분 |

---

## 추가 학습 포인터

1. **`inline fun`** — `repeat`, `let`, `firstOrNull` 정의에 붙은 `inline`. 람다를 객체로 만들지 않고 호출부에 코드를 펴넣어(인라이닝) 람다 오버헤드를 줄인다. stdlib에 `inline`이 많이 쓰이는 이유를 보면 코틀린 람다의 성능 모델이 잡힌다.
2. **운영적 허용 범위 트레이드오프** — 동일 임계점이 동시 발급 race로 두 번 알림 발사될 가능성은 있으나 허용 범위로 둘 수 있다. 어디까지 운영적으로 허용하고 어디부터 엄밀히 막을지 기준을 비교해보면 설계 감각이 늘어난다.
