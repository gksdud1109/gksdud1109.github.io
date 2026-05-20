---
title: "[Kotlin 패턴#1] API 컨트롤러로 보는 코틀린"
date: 2026-05-15 21:00:00 +0900
categories: [Kotlin]
tags: [programming, kotlin]
---

> 자바/Spring 경험으로 코틀린 코드를 읽을 때 먼저 확인하게 되는 지점들이 있다. 코틀린/Spring으로 외부 API 인증(API Key + HMAC 서명) 컨트롤러를 직접 작성해보며 자바와 다른 3가지를 정리했다. 주제는 주 생성자, `@RequestHeader` nullable, 명명 인자(named argument)다. 예제 코드는 학습용으로 직접 구성했다.

---

## 살펴본 코드

외부 클라이언트가 호출하는 초대 코드 발급 API를 학습용으로 구성한 예시다. (API Key + 서명 검증 + 일관 응답 포맷)

```kotlin
@RestController
@RequestMapping("/api/v1/invites")
class InviteController(
    private val service: InviteService,
    private val verifier: ApiSignatureVerifier,
) {

    @PostMapping
    fun create(
        @RequestHeader("x-api-key", required = false) apiKey: String?,
        @RequestHeader("x-timestamp", required = false) timestamp: String?,
        @RequestHeader("x-signature", required = false) signature: String?,
        @RequestBody request: InviteRequest.Create,
    ): ApiResponse<InviteResponse.Create> {
        verifier.verify(
            apiKey = apiKey,
            timestamp = timestamp,
            signature = signature,
            workspaceId = request.workspaceId,
            inviterId = request.inviterId,
            subject = request.requestId,
        )
        return ApiResponse.success(service.create(request))
    }

    // 도메인 예외 → 일관된 응답 포맷으로 변환 (로컬 @ExceptionHandler)
    @ExceptionHandler(ApiException::class)
    fun handleApiException(e: ApiException): ApiResponse<Nothing> {
        warnLog("API error: code=${e.code}, message=${e.message}")
        return ApiResponse.fail(code = e.code, message = e.message)
    }

    // 마지막 안전망
    @ExceptionHandler(Exception::class)
    fun handleUnknown(e: Exception): ApiResponse<Nothing> {
        errorLog("Unexpected error", e)
        return ApiResponse.fail(code = "9999", message = "Unknown System Error Occurred.")
    }
}
```

## 자바 시선에서 확인할 3가지

1. `service`, `verifier` 생성자 주입에 `@RequiredArgsConstructor`가 보이지 않는 이유
2. `@RequestHeader(required = false)`와 nullable 타입을 함께 쓰는 이유
3. `verifier.verify()` 호출에서 인자 이름을 명시하는 이유

---

## 1. 코틀린 주 생성자 — `@RequiredArgsConstructor`가 필요 없는 이유

```kotlin
class InviteController(
    private val service: InviteService,
    private val verifier: ApiSignatureVerifier,
)
```

핵심은 **클래스 이름 뒤 괄호 `( ... )` 자체가 주 생성자(primary constructor) 선언**이라는 점이다. 코틀린 문법 레벨의 생성자라서 Lombok 같은 어노테이션이 필요 없다.

자바 + Lombok 대응:

```java
// Java (Lombok)
@RequiredArgsConstructor
public class InviteController {
    private final InviteService service;
    private final ApiSignatureVerifier verifier;
}

// Lombok 없이 Java
public class InviteController {
    private final InviteService service;
    private final ApiSignatureVerifier verifier;
    public InviteController(InviteService service,
                            ApiSignatureVerifier verifier) {
        this.service = service;
        this.verifier = verifier;
    }
}
```

위 자바 두 블록이 하는 일을 **코틀린은 클래스 헤더 한 줄로** 끝낸다.

- `val` → `final` 필드 + getter
- 괄호 안 파라미터 → 생성자 파라미터
- 생성자 본문(`this.x = x`) → 컴파일러가 자동 생성

여기에 **Spring 생성자 주입**이 겹친다. 생성자가 1개면 Spring이 `@Autowired` 없이도 그 생성자로 주입한다(Spring 4.3+). 그래서 어노테이션이 아예 안 보인다. 

`@RestController` 빈으로 등록 → 생성자 1개 → 파라미터 타입(`InviteService`, `ApiSignatureVerifier`)을 컨테이너에서 찾아 주입.

> `@RequiredArgsConstructor`는 Lombok 기반 자바 코드에서 필요한 보일러플레이트 제거 도구다. 코틀린은 주 생성자 문법으로 같은 역할을 언어 차원에서 제공한다.

## 2. `@RequestHeader(required = false)` + nullable — 의도된 설계

핵심은 **헤더 누락도 컨트롤러까지 전달한 뒤, 직접 검사해서 정해진 응답 포맷으로 처리하는 것**이다.

`required = true`(기본값)였다면:

```text
헤더 누락 → Spring이 MissingRequestHeaderException 을 자기 방식으로 던짐
         → 우리 @ExceptionHandler 타기 전에 Spring 기본 400 응답
         → ApiResponse {code, message, data} 등의 원하는 응답 규격이 깨짐
```

`required = false` + `String?`로 받으면:

- 누락돼도 컨트롤러 메서드에 진입한다 (값은 `null`)
- `verifier.verify()`가 직접 검사한다

```kotlin
if (apiKey.isNullOrBlank()) {
    warnLog("Auth fail: missing x-api-key, subject=$subject")
    throw ApiException.unauthorized()   // ← 내가 통제하는 도메인 예외
}
```

→ `@ExceptionHandler(ApiException::class)`가 받아서 **일관된 `{code, message}` 포맷**으로 응답한다.

**nullable(`String?`)을 쓰는 이유**: `required = false`면 헤더가 없을 때 값이 `null`로 들어온다. 코틀린은 null 가능성을 타입에 명시해야 하므로 `String?`이 필요하다. `String`(non-null)으로 받으면 누락 시 컨트롤러 본문 진입 전에 바인딩 예외가 날 수 있어, `verify`에서 직접 검사하는 흐름을 타기 어렵다.

## 3. 명명 인자(named argument) — 같은 타입 파라미터의 버그 방어

```kotlin
verifier.verify(
    apiKey = apiKey,
    timestamp = timestamp,
    signature = signature,
    workspaceId = request.workspaceId,
    inviterId = request.inviterId,
    subject = request.requestId,   // ← 파라미터명(subject) ≠ 인자(requestId)
)
```

자바는 **위치 인자(positional argument)만** 지원한다(순서로 매칭). 코틀린은 **명명 인자(named argument)**, 즉 이름으로 매칭하는 것도 가능하다.

`verify()` 시그니처:

```kotlin
fun verify(
    apiKey: String?, timestamp: String?, signature: String?,
    workspaceId: String, inviterId: String, subject: String,
)
```

여기서는 **6개 파라미터가 전부 `String`/`String?`** 이다. 자바처럼 순서로만 넣으면:

```kotlin
// positional 로 했는데 실수로 workspaceId 와 inviterId 순서가 바뀜
verifier.verify(apiKey, timestamp, signature, request.inviterId, request.workspaceId, request.requestId)

// 타입이 다 String 이라 컴파일 OK → 런타임에 서명 검증이 깨지는 버그. 찾기 매우 어려움
```

타입이 전부 같아서 **컴파일러가 순서 실수를 못 잡는다.** 명명 인자를 쓰면:

- 순서가 바뀌어도 이름으로 매칭 → 버그 원천 차단
- `subject = request.requestId`처럼 **이름이 다른 매핑이 명시적**으로 읽힌다 (requestId가 서명의 subject로 쓰인다는 의도가 코드에 드러남)

자바에서는 보통 별도 파라미터 객체(DTO)로 묶어 같은 문제를 줄인다. 코틀린에서는 명명 인자로 호출부의 의도를 더 직접적으로 드러낼 수 있다.

> 관용: 코틀린에서 **동일 타입 파라미터가 여럿이거나, 파라미터명과 인자명이 다를 때** 명명 인자를 쓰는 게 컨벤션이다. boolean 여러 개(`enabled = true, cached = false`)일 때도 거의 필수.

---

## 정리

| 질문 | 코틀린 | 자바 대응 |
|:----|:----|:----|
| 생성자 주입 어노테이션이 없는 이유 | 클래스 헤더 괄호 = 주 생성자, 생성자 1개면 Spring이 자동 주입 | `@RequiredArgsConstructor`(Lombok) 또는 수동 생성자 |
| `@RequestHeader(required=false)` + `String?` | 누락도 통과시켜 verify에서 검사 → 응답 포맷 통제 | nullable 표기 없이 누락 시 프레임워크가 먼저 던짐 |
| `verify(name = value)` | 명명 인자로 순서 실수·의도 불명확 차단 | 위치 인자만 → 같은 타입 다수면 위험 |

📌 한 줄 요약: 세 가지 모두 **프레임워크 기본 동작을 코틀린 문법으로 명시적으로 통제**하는 패턴이다.

---

## 추가 학습 포인터

1. **`@ExceptionHandler` 우선순위** — 한 컨트롤러에 핸들러가 여러 개일 때, 구체 예외(`ApiException`)와 안전망(`Exception`)이 겹치면 Spring은 **가장 구체적인 타입** 핸들러를 고른다. 예외 분류와 일관 응답 설계를 볼 때 먼저 확인할 규칙이다.
2. **코틀린 trailing comma** — `verify(... subject = request.requestId,)`처럼 마지막 인자 뒤 콤마. 자바엔 없는 문법이다. diff를 깔끔하게 하려는 컨벤션인데 어디까지 허용되는지 확인해두면 좋다.
