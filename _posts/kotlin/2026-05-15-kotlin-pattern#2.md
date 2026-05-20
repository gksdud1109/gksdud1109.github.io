---
title: "[Kotlin 패턴#2] DTO 설계로 보는 코틀린: sealed interface · data class · companion object · init"
date: 2026-05-15 22:00:00 +0900
categories: [Kotlin]
tags: [programming, kotlin]
---

> 이전 [Kotlin 패턴#1] 글에서 만든 초대 코드 발급 API의 요청/응답 DTO를 직접 설계하며 확인한 내용을 정리했다. `sealed interface`로 DTO를 묶는 컨벤션, `data class`/`companion object`/`init {}`이 각각 무슨 일을 하는지, 그리고 자바 시선에서 자주 혼동되는 `( )` vs `{ }`까지 코틀린 ↔ 자바 대비로 풀었다. 예제 코드는 학습용으로 직접 구성했다.

---

## 살펴본 코드

요청/응답 DTO를 학습용으로 구성한 예시다.

```kotlin
sealed interface InviteResponse {

    data class Create(
        val requestId: String,
        val invite: Invite,
    ) : InviteResponse {
        data class Invite(
            val inviteCode: String,
            val expireAt: String,
        ) {
            companion object {
                fun of(inviteCode: String, expireAt: LocalDateTime) = Invite(
                    inviteCode = inviteCode,
                    expireAt = expireAt.defaultFormat,
                )
            }
        }
    }
}

sealed interface InviteRequest {

    data class Create(
        val workspaceId: String,
        val inviterId: String,
        val requestId: String,
    ) : InviteRequest {
        init {
            validateWorkspaceId(workspaceId)
            validateInviterId(inviterId)
            if (!requestId.matches(Regex("^[A-Za-z0-9_-]{1,64}$"))) {
                throw ApiException.invalidRequest()
            }
        }
    }

    data class Status(
        val workspaceId: String,
        val inviterId: String,
        val inviteCode: String,
    ) : InviteRequest {
        init {
            validateWorkspaceId(workspaceId)
            validateInviterId(inviterId)
            if (!inviteCode.matches(Regex("^[A-Z0-9]{12}$"))) {
                throw ApiException.invalidRequest()
            }
        }
    }
}

private fun validateWorkspaceId(workspaceId: String) {
    if (workspaceId.isBlank() || workspaceId.length > 64) {
        throw ApiException.invalidWorkspace()
    }
}

private fun validateInviterId(inviterId: String) {
    if (inviterId.isBlank() || inviterId.length > 64) {
        throw ApiException.invalidInviter()
    }
}
```

## 자바 시선에서 확인할 지점

1. `sealed interface` 아래에 `data class` 여러 개를 묶는 이유
2. 중첩 `data class`, `companion object`, `of()`의 역할
3. 검증 로직을 일반 `fun`이 아니라 `init {}`에 두는 이유
4. `data class Create(...) { ... }`에서 `( )`와 `{ }`가 각각 의미하는 것

---

## 1. `sealed interface` + 중첩 data class — DTO를 닫힌 집합으로 묶기

DTO 묶기 컨벤션이다. 세 가지를 동시에 얻으려는 구조다.

```kotlin
sealed interface InviteRequest {
    data class Create(...) : InviteRequest
    data class Status(...) : InviteRequest
}
```

### ① 네임스페이스 (소속 명시)

사용처에서 `InviteRequest.Create`, `InviteResponse.Create`로 쓰인다. 이름만 봐도 요청 DTO인지 응답 DTO인지 즉시 구분된다.

```kotlin
@RequestBody request: InviteRequest.Create,   // request 쪽 Create
): ApiResponse<InviteResponse.Create>          // response 쪽 Create
```

`Create`라는 같은 단어를 양쪽에 쓰면서도 소속이 달라 충돌이 없다.

### ② `sealed` = 구현체 범위 제한

Kotlin의 `sealed`는 구현체를 제한해 닫힌 계층을 만드는 제약이다. 최신 Kotlin 기준으로 직접 하위 클래스는 같은 패키지와 모듈 범위에 있어야 한다.

- 외부에서 `InviteRequest`를 멋대로 구현한 클래스를 못 만든다 → 요청 타입이 `Create`/`Status` **둘로 닫힌다(closed set)**
- `when`으로 분기할 때 컴파일러가 모든 경우가 처리됐는지(exhaustive) 검사할 수 있다

### ③ 공통 헬퍼 공유

하단 `validateWorkspaceId`, `validateInviterId`를 `Create`/`Status` 둘 다 `init`에서 호출한다. 같은 도메인 묶음이라 검증 로직을 한 파일에 모은다.

자바 대응(17+):

```java
public sealed interface InviteRequest permits Create, Status {  // Java 17+
    record Create(String workspaceId, String inviterId, String requestId)
        implements InviteRequest { }
    record Status(...) implements InviteRequest { }
}
```

자바 17 sealed + record와 가까운 개념이다. 자바 8 환경에선 직접 쓰기 어렵고 코틀린이라 간결하게 표현할 수 있는 패턴이다.

> 비교 학습: `sealed class` + 중첩 예외 클래스도 같은 철학이다. 한 도메인의 변종들을 닫힌 집합으로 묶는다. Request/Response는 상태 없는 계약이라 `sealed interface`, 예외는 공통 필드(`code` 등) 상태가 있어 `sealed class`로 표현하기 좋다.

## 2. `data class`가 자동 생성하는 것

`data` 키워드를 붙이면 컴파일러가 이 메서드들을 **자동 생성**한다.

| 자동 생성 | 용도 |
|---|---|
| `equals()` / `hashCode()` | 필드 값이 같으면 같은 객체로 취급 (값 동등성) |
| `toString()` | `Create(requestId=..., invite=...)` 형태 로그 출력 |
| `copy()` | 일부 필드만 바꿔 새 객체 (`request.copy(inviterId="X")`) |
| `componentN()` | 구조 분해 (`val (code, exp) = invite`) |

자바 + Lombok 대응:

```java
@Value          // 또는 record (Java 16+)
public class Invite {
    String inviteCode;
    String expireAt;
    // equals/hashCode/toString/getter 자동
}
```

불변 값 전달 객체에는 `data class`를 자주 쓴다. 직렬화(JSON 변환), 로그 출력, 값 비교에서 자동 생성 메서드가 유용하기 때문이다. 다만 JPA Entity처럼 식별자와 생명주기가 중요한 객체에는 신중해야 한다.

### 중첩 `Invite`는 — JSON 응답 구조를 1:1 반영

응답 JSON의 중첩 구조를 클래스 구조로 그대로 매핑한 것이다.

```kotlin
data class Create(
    val requestId: String,
    val invite: Invite,           // ← 중첩 객체
) {
    data class Invite(val inviteCode: String, val expireAt: String)
}
```

직렬화되면:

```json
{
  "requestId": "req-123",
  "invite": {
    "inviteCode": "ABC123XYZ987",
    "expireAt": "2026-05-18 23:59:59"
  }
}
```

API 규격이 `invite`를 중첩 객체로 정의했기 때문에 클래스도 똑같이 중첩으로 만든다. `Invite`를 `Create` 안에 둔 건 이 타입이 Create 응답 전용이라는 소속 표현이다.

## 3. `companion object`와 `of()` — 정적 팩토리 메서드

`companion object`는 코틀린에서 **클래스에 붙는 객체**다. 자바의 `static`처럼 `Invite.of(...)` 형태로 접근할 수 있지만, 실제로는 객체라는 점이 다르다.

```kotlin
data class Invite(val inviteCode: String, val expireAt: String) {
    companion object {
        fun of(inviteCode: String, expireAt: LocalDateTime) = Invite(
            inviteCode = inviteCode,
            expireAt = expireAt.defaultFormat,   // LocalDateTime → String 변환
        )
    }
}
```

**생성자 대신 `of()`를 두는 이유** — 타입 변환 책임을 한 곳에 캡슐화하려고:

- `Invite`의 `expireAt`은 **`String`** (이미 포맷된 문자열, JSON 응답용)
- 호출하는 쪽(서비스)이 가진 건 **`LocalDateTime`**
- `of()`가 그 사이에서 `LocalDateTime → "2026-05-18 23:59:59"` 변환을 담당

호출부 비교:

```kotlin
// of() 없으면 — 호출하는 모든 곳에서 매번 포맷 변환 (까먹기 쉬움)
Invite(inviteCode = code, expireAt = expireAt.defaultFormat)

// of() 있으면 — 변환은 of() 안에 한 번만, 호출부는 깔끔
Invite.of(inviteCode = code, expireAt = expireAt)   // LocalDateTime 그대로 넘김
```

다른 응답 DTO에서도 같은 패턴을 쓸 수 있다. 엔티티나 도메인 객체를 받아 응답 DTO로 바꾸는 책임을 DTO 쪽 팩토리에 모으면 호출부가 단순해진다.

자바 대응:

```java
public class Invite {
    private final String inviteCode;
    private final String expireAt;
    private Invite(String c, String e) { ... }          // 생성자 private

    public static Invite of(String inviteCode, LocalDateTime expireAt) {  // static factory
        return new Invite(inviteCode, format(expireAt));
    }
}
```

`companion object`의 `of()`는 자바의 **static factory method**에 가깝다. Effective Java의 정적 팩토리 메서드 패턴과 같은 의도다.

## 4. `init {}` vs `fun` — 호출 시점이 근본적으로 다르다

```kotlin
data class Create(
    val workspaceId: String,
    val inviterId: String,
    val requestId: String,
) : InviteRequest {
    init {
        validateWorkspaceId(workspaceId)    // ← 객체 생성 시 자동 실행
        validateInviterId(inviterId)
        if (!requestId.matches(Regex("^[A-Za-z0-9_-]{1,64}$"))) {
            throw ApiException.invalidRequest()
        }
    }
}
```

| | `init {}` | `fun validate()` |
|---|---|---|
| 정체 | **주 생성자의 본문** | 일반 메서드 |
| 실행 시점 | 객체 생성 시 **자동·무조건** | 누군가 명시적으로 호출해야 |
| 누락 가능? | 불가능 (생성 = 실행) | 가능 (호출 까먹으면 검증 안 됨) |

핵심은 **`init`이 함수가 아니라 생성자의 일부**라는 점이다. 코틀린 주 생성자(`class Create(...)`)는 괄호에 파라미터만 선언할 수 있고 본문이 없다. 그 본문 역할을 `init {}`이 한다.

`fun`으로 했다면:

```kotlin
val req = Create("w", "u", "r")   // ← 객체는 만들어짐 (검증 안 됨!)
req.validate()                     // ← 이걸 까먹으면 잘못된 객체가 그대로 흘러감
```

`init`을 쓰면 **객체가 존재한다 = 검증을 통과했다**는 상태를 만들 수 있다. 잘못된 요청이면 `Create` 객체 자체가 만들어지지 않는다. 이게 **DTO 생성 = 유효성 보장** 패턴의 메커니즘이다.

컨트롤러에서 `@RequestBody request: InviteRequest.Create` 역직렬화 중에 `init`이 실행된다. 검증 실패 예외는 Jackson/Kotlin 모듈과 예외 처리 방식에 따라 래핑될 수 있으므로, 전역 예외 처리에서 `cause`를 확인해야 할 수 있다.

자바 대응:

```java
public Create(String workspaceId, ...) {
    validateWorkspaceId(workspaceId);   // Java는 생성자 본문에 직접 검증
    this.workspaceId = workspaceId;
}
```

자바는 생성자 본문에 쓰는 걸, 코틀린은 주 생성자에 본문이 없으니 `init {}`으로 뺀 것. (자바의 *instance initializer block*에 대응되지만, 실무에선 거의 안 써서 "생성자 본문"으로 이해하는 게 정확하다.)

## 5. `( )`는 생성자, `{ }`는 클래스 본문 — 가장 헷갈리는 지점

```kotlin
data class Create(                         // ← (  ) : 주 생성자 (parameters)
    val workspaceId: String,
    val inviterId: String,
    val requestId: String,
) : InviteRequest {                        // ← {  } : 클래스 본문 (body) — 생성자 아님
    init {                                 //    ├ init : 생성자가 "실행하는" 코드
        validateWorkspaceId(workspaceId)
    }
}
```

| 위치 | 이름 | 정체 |
|---|---|---|
| `( ... )` | primary constructor | **생성자.** 파라미터 선언 |
| `{ ... }` | class body | 생성자 ❌. 클래스 멤버들이 사는 곳 |
| `{ }` 안의 `init { }` | initializer block | 생성자가 **실행하는** 코드 블록 |
| `{ }` 안의 `val`/`fun`/`companion`/중첩 class | 멤버들 | 생성자와 무관 |

즉 **`{}` 전체가 생성자 본문이 아니라, `{}` 안의 `init {}` 블록과 프로퍼티 이니셜라이저만 생성 과정에서 실행**된다. 나머지(`fun`, `companion`, 중첩 클래스)는 생성자와 무관한 일반 멤버다.

`Create(...)` 호출 시 실제로 일어나는 일:

| 멤버 | `Create(...)` 호출 시? |
|---|---|
| 프로퍼티 이니셜라이저 (`val x = ...`) | ✅ 실행됨 (생성자 일부) |
| `init { }` | ✅ 실행됨 (생성자 일부) |
| `fun` | ❌ 정의만 존재. 나중에 호출해야 실행 |
| `companion object` | ❌ 객체 생성과 별개 (클래스 최초 로드 시 1번) |
| 중첩 `data class` | ❌ 별도 타입 선언. 실행 개념 없음 |

## 6. 클래스 본문 규칙 — 선언만 가능하고 실행문은 금지

검증 코드를 클래스 본문에 바로 늘어놓는 방식은 **문법적으로 허용되지 않는다.** 선택이 아니라 언어 규칙이다.

> 코틀린 클래스 본문 `{ }`의 **최상위에는 선언(declaration)만 올 수 있다. 실행문(statement)은 올 수 없다.**

- **선언**: `val`, `var`, `fun`, `class`, `object`, `init`, `companion` — 클래스가 *무엇을 가지는지*
- **실행문**: `validateWorkspaceId(workspaceId)`, `if (...) throw ...`, 함수 호출 — *실행되는 동작*

```kotlin
data class Create(val workspaceId: String, ...) {
    validateWorkspaceId(workspaceId)        // ❌ 컴파일 에러 (실행문)
}
```

실행 코드를 객체 생성 시점에 돌리고 싶으면 **합법적 자리 두 곳**뿐이다:

```kotlin
// (a) 프로퍼티 이니셜라이저 — 값 계산용
val normalized: String = workspaceId.trim()

// (b) init 블록 — 검증·부수효과용
init {
    validateWorkspaceId(workspaceId)
    if (!requestId.matches(Regex("..."))) throw ApiException.invalidRequest()
}
```

검증처럼 값 반환이 아닌 동작은 (a)에 못 넣으니 `init`이 사실상 유일한 자리다.

### 선언과 실행을 분리하는 효과

선언과 실행을 분리해서:

- 클래스 본문 = **이 클래스의 구조(멤버 목록)** 를 한눈에 확인
- 실행 순서가 중요한 코드 = `init`에 **명시적으로 격리** → 객체 생성 시 실행되는 일이 한 군데 모인다

자바도 동일한 제약이 있다 — 클래스 본문에 실행문을 그냥 못 쓰고 생성자 `{ }` 안에서만 가능하다. 코틀린 `init {}` ≈ 자바 생성자 본문.

> 실행 순서: 프로퍼티 이니셜라이저와 `init` 블록은 **소스에 쓰인 순서대로** 섞여 실행된다. 그래서 `init`에서 위에 선언된 프로퍼티는 쓸 수 있지만, 아래 것은 아직 초기화 전이라 못 쓴다.

## 7. `companion object`는 클래스당 1개 — 가변 상태의 위험

```kotlin
@Service
class InviteService(...) {
    companion object {
        internal const val SAMPLE_CONFIG_KEY = "SAMPLE_INVITE"
        private const val MAX_RETRY = 3
    }
    private val random = SecureRandom()   // ← companion 아님 (인스턴스 필드)
}
```

`companion object` 안의 것은 **인스턴스를 몇 개 만들든 메모리에 단 1개만 존재**한다 (자바 `static`과 동일).

```text
    [ companion object ]  ← JVM에 1개 (SAMPLE_CONFIG_KEY, MAX_RETRY)
    
    (모든 인스턴스가 같은 걸 공유)

[인스턴스 a] [인스턴스 b] [인스턴스 c]
 random:A1   random:B7   random:C3   ← 인스턴스 필드는 각자 따로
```

### 지금 코드에서 companion이 안전한 이유 — `const val`(불변)

`SAMPLE_CONFIG_KEY`, `MAX_RETRY`는 `const val` — **읽기 전용 상수**. 1개를 공유해도 값이 안 변하니 동시 접근해도 안전하다.

### 가변필드를 담으면? — 위험 예시 (가상)

```kotlin
@Service
class InviteService(...) {
    companion object {
        // ❌ 가변 상태를 companion 에 — 모든 요청이 이 "하나"를 공유
        private val issuedCache = mutableMapOf<String, String>()
        private var lastIssuedCode: String? = null   // var = 가변
    }

    fun create(request: InviteRequest.Create): ... {
        lastIssuedCode = generateInviteCode()        // ← 동시에 100개 요청이 같은 변수에 write
        issuedCache[request.requestId] = lastIssuedCode!!  // ← race condition
    }
}
```

문제:

- `@Service`는 싱글톤 + 웹 요청은 **여러 스레드가 동시에** `create()` 호출
- `lastIssuedCode`, `issuedCache`는 companion이라 **모든 스레드가 같은 하나를 공유**
- 스레드 A가 쓴 `lastIssuedCode`를 B가 덮어씀 → A가 B의 코드를 자기 것으로 착각 → **초대 코드 섞임**
- `mutableMapOf`는 thread-safe가 아님 → 동시 put 시 데이터 깨짐

👉 **싱글톤 + 공유 가변 상태 = 동시성 버그**. 그래서 멱등성/중복 체크 같은 가변 상태는 메모리(companion)가 아니라 **DB 유니크 제약 + 예외**로 위임한다. 멀티 인스턴스에서도 안전하기 때문.

| 요소 | 위치 | 이유 |
|---|---|---|
| `SAMPLE_CONFIG_KEY` 등 | `companion object` `const val` | 불변 상수 → 공유 안전 |
| `random = SecureRandom()` | **인스턴스 필드** | thread-safe하게 설계됨 + 소속이 명확 |
| 멱등성/중복 체크 | **DB UK + 예외** | 가변 상태를 메모리에 안 두고 DB에 위임 |

원칙: companion엔 **불변 상수만, 가변 상태는 절대 안 둔다.**

---

## 정리

| 요소 | 역할 |
|---|---|
| `sealed interface` + 중첩 data class | 네임스페이스 + 닫힌 집합(exhaustive `when`) + 공통 헬퍼 공유 |
| `data class` | equals/hashCode/toString/copy 자동 → 불변 값 전달 객체에 적합 |
| 중첩 `Invite` | 응답 JSON 중첩 구조를 클래스로 1:1 반영 + 소속 표현 |
| `companion object` | 클래스에 붙는 객체. 클래스당 1개 |
| `of()` | 정적 팩토리 — `LocalDateTime→String`, `Entity→DTO` 변환 캡슐화 |
| `init {}` | 생성자 본문. 자동 실행 → 객체 존재 = 검증 통과 상태를 만들 수 있음 |
| `( )` vs `{ }` | `( )` = 생성자(파라미터), `{ }` = 그 외 멤버가 사는 집 |
| 본문 규칙 | 최상위엔 선언만, 실행문 금지 → 실행 코드는 `init`/프로퍼티 이니셜라이저뿐 |

---

## 추가 학습 포인터

1. **`object` (companion 아닌 단독)** — 코틀린의 싱글톤 선언 키워드. `companion object`는 클래스에 붙은 object, 단독 `object Foo {}`는 그 자체가 싱글톤 인스턴스다. 유틸/상수 묶음에서 자주 보인다.
2. **`const val` vs `val` in companion** — `const val`은 컴파일 타임 상수(원시타입·String만, 바이트코드에 인라인), 그냥 `val`은 런타임 초기화. `val random = SecureRandom()`에 `const`를 붙일 수 없는 이유를 보면 둘의 경계가 잡힌다.
3. **secondary constructor** (`constructor(...) { }`) — 코틀린도 본문 `{ }` 안에 `constructor` 키워드로 부 생성자를 둘 수 있다. `{ }` 안에 생성자가 들어가는 예외적인 경우다. 보통 `companion`의 `of()` 팩토리가 이를 대체하는 컨벤션이라 잘 쓰지 않는다.
