---
title: "Kotlin isNullOrEmpty vs isNullOrBlank"
date: 2026-05-26 14:00:00 +0900
categories: [Kotlin]
tags: [kotlin, validation, contract, smart-cast, stdlib]
description: "외부 API 헤더 검증 코드에서 isNullOrEmpty와 isNullOrBlank의 차이를 정리한다. 검증 if 안에서 함수는 거절 조건이라, 더 많이 true를 반환하는 함수가 더 엄격한 검증이다. Kotlin contract와 smart cast 동작까지 함께 본다."
---

> 외부 API 요청 헤더(`x-api-key`, `x-signature`) 검증 코드를 작성할 때 `isNullOrEmpty`와 `isNullOrBlank`의 차이가 헷갈릴 수 있다. 특히 검증 if 안에서는 직관이 거꾸로 작동한다.
>
> 핵심은 **`isNullOrBlank=true`가 유효하다는 뜻이 아니라, 비어있다고 보고 거절해도 된다는 신호**라는 점이다. 검증 if 안에서 함수는 거절 조건이므로 **더 많이 true를 반환하는 함수 = 더 엄격한 검증**이다. 외부 입력 검증의 기본은 `isNullOrBlank`. Kotlin contract가 smart cast를 만드는 방식도 본다.

---

## 0. TL;DR

```kotlin
// 외부 입력 검증의 기본 (defensive default)
if (input.isNullOrBlank()) throw InvalidInput()

// 의도적으로 공백 valid 허용하는 경우만
if (input.isNullOrEmpty()) throw InvalidInput()
```

```
isBlank가 잡는 케이스 ⊇ isEmpty가 잡는 케이스
  isEmpty : ""
  isBlank : "" + " " + "\t" + "\n" + "　"(전각공백) + ...

→ 더 많이 잡는다 = 더 엄격 (검증 if 안에서)
→ 거절 조건이라는 의미를 기억하면 직관 오류를 피할 수 있음
```

---

## 1. 함수 정의 - stdlib `Strings.kt`

### isNullOrEmpty

```kotlin
@kotlin.internal.InlineOnly
public inline fun CharSequence?.isNullOrEmpty(): Boolean {
    contract {
        returns(false) implies (this@isNullOrEmpty != null)
    }
    return this == null || this.length == 0
}
```

→ `null`이거나 `length == 0`.

### isNullOrBlank

```kotlin
@kotlin.internal.InlineOnly
public inline fun CharSequence?.isNullOrBlank(): Boolean {
    contract {
        returns(false) implies (this@isNullOrBlank != null)
    }
    return this == null || this.isBlank()
}
```

→ `null`이거나 `isBlank()` — **공백문자만 있는 경우 포함**.

### isBlank의 실제 동작 - `Char.isWhitespace`

```kotlin
public fun CharSequence.isBlank(): Boolean = length == 0 ||
    indices.all { this[it].isWhitespace() }
```

`Char.isWhitespace()`가 true인 문자가 무엇인가가 핵심이다.

| 문자 | 코드포인트 | 비고 |
|---|---|---|
| 스페이스 ` ` | U+0020 | 일반 공백 |
| 탭 `\t` | U+0009 | |
| LF `\n` | U+000A | 개행 |
| CR `\r` | U+000D | |
| 전각 공백 ` ` (Em Space 등) | U+2000~U+200A | **Unicode whitespace** |
| Ideographic space `　` | U+3000 | 한중일 전각 공백 (자주 발생) |
| Non-breaking space | U+00A0 | HTML `&nbsp;` ← **잘 안 보임** |
| Line/Paragraph separator | U+2028, U+2029 | |
| Vertical tab | U+000B | |

→ **눈에 안 보이는 공백류가 많다.** 화면상 비슷해 보여도 실제로는 다양한 유니코드 문자일 수 있다.

⚠️ **`Char.isWhitespace()`에 안 잡히는 것:**
- Zero-width space (U+200B), Zero-width joiner (U+200D) — 보이지 않지만 whitespace가 아님
- Byte Order Mark (U+FEFF) — 보안 공격에 자주 활용
- → **`isBlank`가 모든 보이지 않는 문자를 잡지는 않는다.** 보안 검증 시 추가 검증 필요.

---

## 2. 케이스별 결과 비교

| 입력값 | `isEmpty` | `isBlank` | `isNullOrEmpty` | `isNullOrBlank` |
|---|---|---|---|---|
| `null` | (N/A) | (N/A) | ✅ true | ✅ true |
| `""` | ✅ true | ✅ true | ✅ true | ✅ true |
| `" "` (스페이스) | ❌ false | ✅ true | ❌ false | ✅ true |
| `"\t\n"` (탭+개행) | ❌ false | ✅ true | ❌ false | ✅ true |
| `"   "` (3공백) | ❌ false | ✅ true | ❌ false | ✅ true |
| `"　"` (전각공백) | ❌ false | ✅ true | ❌ false | ✅ true |
| `"​"` (zero-width) | ❌ false | **❌ false** ⚠️ | ❌ false | **❌ false** ⚠️ |
| `"   hi"` | ❌ false | ❌ false | ❌ false | ❌ false |
| `"hi"` | ❌ false | ❌ false | ❌ false | ❌ false |

### 포함관계 시각화

```
                ┌─────────────────────────────────────┐
                │  isBlank가 잡는 범위                   │
                │  ┌──────────────┐                   │
                │  │ isEmpty가     │  공백·탭·개행·      │
                │  │ 잡는 범위       │  전각공백 등        │
                │  │ ""           │                   │
                │  └──────────────┘                   │
                └─────────────────────────────────────┘
                              ⚠️ zero-width 등 보이지 않는 일부 문자는
                                  isBlank도 못 잡음 (별도 검증 필요)
```

→ **isBlank가 더 엄격** (= 더 많은 케이스를 비어있다고 판정).
→ 단 isBlank만으로 충분하지 않다. zero-width / BOM 같은 보안 검증은 추가로 필요하다.

---

## 3. 검증 if에서 직관이 거꾸로 작동한다

처음에는 다음처럼 오해하기 쉽다.

- `isBlank()`가 `" "`에 `true`를 반환한다.
- 그러면 `" "`도 비어있는 값으로 본다.
- 따라서 `" "`를 막으려면 `isEmpty()`가 맞는 것처럼 느껴진다.

이 결론은 반대다. 검증 코드는 보통 이런 형태다.

```kotlin
if (input.isNullOrBlank()) {
    throw InvalidInput()   // ← "비어있으면 거절"
}
```

여기서 `isNullOrBlank=true`는 **거절 신호**이지 OK 신호가 아니다.

### 케이스 시뮬레이션 - input = `" "`

```kotlin
val input = " "

// 패턴 A — isNullOrEmpty 검증
if (input.isNullOrEmpty()) {           // " ".isNullOrEmpty() = false
    throw InvalidInput()
}
// → 통과. " " 가 valid 입력으로 처리됨 ❌ (보통 원하지 않음)

// 패턴 B — isNullOrBlank 검증
if (input.isNullOrBlank()) {           // " ".isNullOrBlank() = true
    throw InvalidInput()
}
// → 거절. " " 가 invalid 로 잡힘 ✅
```

→ **공백만 입력한 값을 막고 싶으면 `isNullOrBlank`가 맞다.**

### 직관 정정

| ❌ 잘못된 직관 | ✅ 올바른 해석 |
|---|---|
| `isBlank=true`면 그 값이 valid다 | `isBlank=true`면 이 값은 비어있다고 봐도 무방하다 |
| 공백 막고 싶으면 isEmpty가 더 엄격해 보인다 | isBlank가 잡는 범위가 더 넓다. 즉 더 엄격하다 |
| 함수 이름만으로 의미 추론 | 함수가 true 반환할 때 무엇을 의미하는지 + if 안에서 어느 분기로 가는지 같이 봐야 한다 |

---

## 4. 일반화 - Boolean 검증 패턴

이 패턴의 본질은 **함수가 true 반환할 때의 의미**와 **검증 if 안에서 어느 분기로 가는지**를 함께 봐야 한다는 점이다.

### 같은 패턴의 다른 stdlib 함수들

```kotlin
// 1. isNullOrEmpty / isNullOrBlank — 본 글의 케이스
if (input.isNullOrBlank()) reject()   // true = 거절

// 2. Collection.isNullOrEmpty
if (list.isNullOrEmpty()) reject()    // true = 거절 (빈 리스트도 거절)

// 3. 비슷한 패턴 — toIntOrNull
val n = input.toIntOrNull()           // null = 변환 실패
if (n == null) reject()               // null 이 거절 신호

// 4. firstOrNull
val found = list.firstOrNull { it.matches() }
if (found == null) reject()           // null = 못 찾음 = 거절
```

→ **공통 패턴**: null/empty/blank/실패를 표현하는 값이 검증 if의 분기를 결정한다.
→ 회피법: **함수 이름이 아니라 이 함수가 X 반환 → 어느 분기로 추적**한다.

### 다른 언어 비교

| 언어 | 함수 | 동작 |
|---|---|---|
| **Kotlin** | `isNullOrBlank()` | null + 공백류 |
| **Kotlin** | `isNullOrEmpty()` | null + 길이 0 |
| **Java** (Apache Commons) | `StringUtils.isBlank()` | null + 공백류 (Kotlin isNullOrBlank와 동일) |
| **Java** (Apache Commons) | `StringUtils.isEmpty()` | null + 길이 0 (Kotlin isNullOrEmpty와 동일) |
| **Java 11+** | `String.isBlank()` | 공백류 (null 별도 체크 필요) |
| **JavaScript** | `str?.trim() === ""` | trim 후 빈 문자열 체크 (관용구) |
| **Python** | `not str or str.isspace()` | None 체크 + isspace |
| **Go** | `strings.TrimSpace(s) == ""` | trim 후 빈 체크 |

→ **언어 무관 패턴**: 공백류 포함 비어있음 체크는 여러 언어와 라이브러리에서 별도로 제공한다.
→ Apache Commons `StringUtils.isBlank`는 Java 진영에서 널리 쓰이는 기준이고, Kotlin의 `isNullOrBlank`와 의미가 같다.

---

## 5. 언제 어느 것을 쓰나

| 상황 | 권장 함수 | 이유 |
|---|---|---|
| **외부 API 파라미터 검증** | `isNullOrBlank` | 공백류 입력 방어 |
| **사용자 입력 (UI 폼) 검증** | `isNullOrBlank` | 스페이스만 친 거 거절 |
| **HTTP 헤더 (`x-api-key` 등) 검증** | `isNullOrBlank` | 외부 통신 = 가장 보수적인 기본값 |
| **CSV / TSV 파싱 (의도적 공백 valid)** | `isNullOrEmpty` | 공백이 의미 있는 데이터일 수 있음 |
| **정확한 byte/length 의미가 중요 (해시 64자 등)** | `isNullOrEmpty` + 길이/정규식 | 형식 검증이 우선 |
| **보안 검증 (zero-width / BOM 차단)** | `isNullOrBlank` + Unicode 정규화 + 별도 검증 | isBlank만으론 부족 |

**기본 원칙: 외부 입력은 `isNullOrBlank`.** 공백만 들어오면 거절하는 쪽이 대체로 안전한 디폴트다.

### `isNullOrEmpty`를 선택할 수 있는 경우

학습용 HMAC 시그니처 검증 코드가 `isNullOrEmpty`를 쓴다면 가능한 이유는 다음과 같다.

- HMAC 헤더는 정확한 hex 64자 형식이라 공백 섞일 일 없음
- 트리밍이 다른 곳에서 (예: 필터/인터셉터) 이미 처리
- 또는 그냥 의도 안 한 선택

→ **실용 권장**: 외부 입력은 일관되게 `isNullOrBlank`. 더 안전하고 추가 비용이 거의 없다. 단 형식 검증(regex, 길이)이 더 우선시되면 `isNullOrEmpty`도 선택할 수 있다.

---

## 6. 보안 관점 - isBlank만으론 부족한 케이스

### Zero-width 공격

```kotlin
val attackerInput = "​admin"   // U+200B (zero-width space) + "admin"

attackerInput.isBlank()         // ❌ false (zero-width 는 whitespace 아님)
attackerInput.isNullOrBlank()   // ❌ false

// → 검증 통과 → 사람이 보기엔 admin처럼 보이지만 실제 저장값은 다른 문자열
//    → 향후 비교 시 mismatch (보안·운영 문제)
```

### BOM (Byte Order Mark) 공격

```kotlin
val bomPrefixed = "﻿hello"   // U+FEFF + "hello"

bomPrefixed.isBlank()           // ❌ false
bomPrefixed.length              // 6 (BOM 포함)
"hello".length                  // 5

// → 길이 검증 우회, 비교 우회 등 보안 이슈
```

### 방어 패턴 - Unicode 정규화

```kotlin
import java.text.Normalizer

val normalized = Normalizer.normalize(input, Normalizer.Form.NFKC)
val stripped = normalized.filter {
    !it.isISOControl() && it.code !in setOf(0x200B, 0x200C, 0x200D, 0xFEFF)
}

if (stripped.isNullOrBlank()) throw InvalidInput()
```

→ **외부 입력 보안 검증 = `isNullOrBlank` + Unicode 정규화 + zero-width/BOM 필터.**
일반 비즈니스 검증은 `isNullOrBlank`로 충분, 보안 검증은 한 단계 더.

---

## 7. 보너스 - `contract { returns(false) implies (...) }`

함수 정의에 있던 이 부분.

```kotlin
contract {
    returns(false) implies (this@isNullOrBlank != null)
}
```

### 한 줄 정의

**컴파일러에게 이 함수의 의미를 알려주는 정적 분석 힌트.** 런타임 동작은 아니다.

읽으면: **`isNullOrBlank()`가 `false`를 반환했다면 → `this`는 `null`이 아니었다**는 뜻이다.

논리적으로 맞다. `this == null`이었으면 무조건 `true` 반환하므로, false가 나왔다는 건 not-null이라는 증거.

### Smart cast - contract의 가치

**contract가 있어서:**

```kotlin
val s: String? = readLine()
if (!s.isNullOrBlank()) {
    println(s.length)      // ✅ s 가 String 으로 자동 smart cast — !! 불필요
    println(s.uppercase()) // ✅ 모든 non-null 메서드 호출 가능
}
```

**contract가 없었다면:**

```kotlin
if (!s.isNullOrBlank()) {
    println(s.length)   // ❌ s 는 여전히 String?
    println(s!!.length) // !! 강제 필요
}
```

일반 함수라면 컴파일러는 이 함수 호출 후 null 체크가 끝났다고 단정하기 어렵다. contract가 그 정보를 명시적으로 알려준다.

### Kotlin Contract DSL 종류

| 형태 | 의미 | 사용 사례 |
|---|---|---|
| `returns()` | 정상 리턴(예외 X) 했다면 | 검증 함수 |
| `returns(true)` / `returns(false)` / `returns(null)` | 특정 값 리턴했다면 | `isNullOrBlank`, `isNullOrEmpty` 등 |
| `returnsNotNull()` | non-null 리턴했다면 | safe-call 패턴 |
| `implies (조건)` | 그 조건이 참이라는 힌트 | smart cast 힌트 |
| `callsInPlace(lambda, InvocationKind.X)` | 이 람다는 X번 호출됨 | `let`, `run`, `apply`, `also` 등 |

### Contract가 쓰이는 다른 stdlib 함수들

```kotlin
// let, run, apply, also — callsInPlace contract
inline fun <T, R> T.let(block: (T) -> R): R {
    contract { callsInPlace(block, InvocationKind.EXACTLY_ONCE) }
    return block(this)
}

// → 람다 안에서 val 초기화 가능 (컴파일러가 정확히 1회 호출됨을 안다)
val x: Int
run { x = computeX() }   // ✅ x 가 1회 초기화됨을 컴파일러가 이해
println(x)
```

### Labeled `this`의 의미

`this@isNullOrBlank`는 **labeled `this`** — `inline` 확장함수 안에서 어느 `this`인지 명시(`this@함수명`). contract 안에서 self를 명확히 가리키기 위해 사용된다.

### 일반 애플리케이션에서 contract를 직접 쓸 일

거의 없다. `@ExperimentalContracts` 마커 필요하고, 잘못 쓰면 컴파일러가 잘못된 추론을 한다. **stdlib/라이브러리 만드는 사람용** 도구.

→ 일반 사용자는 **contract가 있는 inline 함수 = smart cast 정보를 컴파일러에 제공하는 stdlib 함수** 정도로 이해하면 충분하다.

---

## 8. 코드 리뷰 체크리스트 - 외부 입력 검증

```
[1] nullable 입력값에 isNullOrBlank 또는 isNullOrEmpty가 적용됐는가?
    □ Yes → 다음
    □ No → null check 누락 가능

[2] 둘 중 적절한 함수를 골랐는가?
    □ 공백 차단 필요 → isNullOrBlank ✅
    □ 공백 valid 허용 (CSV 등) → isNullOrEmpty ✅
    □ 모호 → isNullOrBlank (더 안전한 기본값)

[3] 검증 if의 의미가 직관적인가?
    □ true 반환 = 거절 의미 명확
    □ 부정형 표현 (`if (!input.isNullOrBlank())`)은 줄이는 편이 가독성 높음

[4] 추가 형식 검증이 있는가?
    □ 길이 (max length)
    □ 정규식 (영문/숫자/특수문자 제약)
    □ 정규화 (Unicode NFKC)
    □ Zero-width / BOM 차단 (보안 민감 시)

[5] 검증 실패 시 응답 코드가 명확한가?
    □ 400 INVALID_REQUEST (형식 오류)
    □ 401 UNAUTHORIZED (인증 누락) 같은 도메인 의미 매칭

[6] 로깅이 마스킹되는가?
    □ Signature / Token 같은 비밀값은 로그에 마스킹
```

---

## 9. 의사결정 원칙

1. **함수 이름이 아니라 이 함수가 true 반환하면 무엇을 의미하는가 + if 안에서 어느 분기로 가는지로 판단.**
2. **검증 코드의 if 안에 들어가는 함수는 거절 조건이다.** 그래서 더 많이 true 반환하는 함수 = 더 엄격한 검증.
3. **외부 입력 검증의 default는 `isNullOrBlank`.** 추가 비용 거의 0, 공백 케이스 안전.
4. **stdlib 함수의 KDoc과 동작을 외우기보다 contract까지 읽어보면** smart cast의 동작 조건을 이해할 수 있다.
5. **`isBlank`만으로 충분하지 않은 케이스가 있다.** Zero-width / BOM 같은 보이지 않는 문자는 별도 검증. 보안 민감하면 Unicode 정규화 추가.
6. **같은 패턴이 다른 stdlib 함수에도 있다.** `isNullOrEmpty`, `firstOrNull`, `toIntOrNull` 등 — null/empty/failure를 표현하는 값이 if 분기를 결정한다.

---

## 10. 한 줄 요약 / 일반화

> **isBlank가 잡는 범위는 isEmpty의 상위집합이다.** 검증 코드에 쓸 때는 true 반환 = 거절이므로 더 많이 잡는 isBlank가 더 엄격하다.
> 공백만 있는 값까지 막고 싶다 → isBlank, 길이 0만 막는다 → isEmpty.
> 외부 입력 검증의 디폴트는 **`isNullOrBlank`**. 단 zero-width / BOM 같은 보안 케이스는 추가 검증.
> `contract { returns(false) implies (... != null) }`는 컴파일러에 smart cast 힌트를 주는 장치다. 일반 애플리케이션 코드에서 직접 쓸 일은 드물지만, stdlib의 nullable 확장함수가 smart cast되는 메커니즘을 이해하는 데 도움이 된다.

---

## 부록: 더 찾아볼 키워드

`isNullOrEmpty` · `isNullOrBlank` · `Char.isWhitespace` · `CharSequence` · `Apache Commons StringUtils.isBlank` · `Kotlin contract` · `smart cast` · `nullable extension function` · `inline function` · `labeled this (this@functionName)` · `Unicode whitespace` · `zero-width space (U+200B)` · `BOM (U+FEFF)` · `Unicode normalization (NFKC)` · `callsInPlace contract` · `InvocationKind.EXACTLY_ONCE`

---

## 참고

- Kotlin stdlib `Strings.kt` 원본
- Kotlin docs — *Contracts*: <https://kotlinlang.org/docs/whatsnew13.html#contracts>
- Kotlin KEEP — *Contracts Proposal*: <https://github.com/Kotlin/KEEP/blob/master/proposals/kotlin-contracts.md>
- Apache Commons Lang — `StringUtils.isBlank` JavaDoc (Java 진영 비교)
- Unicode Standard — *Whitespace Characters* (<https://unicode.org/charts/>)
- OWASP — *Input Validation Cheat Sheet*
- 사이드바 Kotlin 카테고리의 「Kotlin 패턴 #1 ~ #4」 시리즈 — 같은 도메인의 API 컨트롤러 / 인증 검증 / 트랜잭션 설계
