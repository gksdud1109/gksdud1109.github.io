---
title: "@Transactional에서 catch했는데 왜 롤백될까 — MyBatis·JPA·Exposed의 서로 다른 사례"
date: 2026-06-11 21:00:00 +0900
categories: [Spring]
tags: [spring, transaction, jpa, jdbc, mybatis, exposed]
description: "@Transactional 안에서 예외를 catch해도 UnexpectedRollbackException이 나는 진짜 조건. rollback-only를 누가 찍는지, MyBatis·JPA·Exposed가 트랜잭션 관리자에 따라 어떻게 갈리는지 정리한다."
---

> 최근 신규 프로젝트 좋아요 기능을 만들다 `UnexpectedRollbackException`을 만났다. 분명히 `try-catch`로 예외를 삼켰는데 트랜잭션 전체가 롤백됐다. RuntimeException은 catch해도 롤백된다는 흔한 지식이 있지만, 진짜 답은 **어떤 데이터 접근 기술과 트랜잭션 관리자를 쓰느냐**에 따라 더 자세한 케이스로 갈린다.

## 들어가며 — 분명히 try-catch 했는데

좋아요는 멱등해야 한다. 동시 첫 요청 2개가 거의 동시에 오면, 둘 다 기존 데이터가 아직 없으므로 통과하고 둘 다 INSERT를 시도해 하나가 유니크 제약을 위반한다. 그걸 `catch`로 무시하려 했다. (아래 코드는 좋아요를 일반화한 멱등 등록 예시다.)

```kotlin
@Transactional
fun register(userId: Long, targetId: Long): RecordResponse {
    if (!records.existsByTargetIdAndUserId(targetId, userId)) {
        try {
            records.saveAndFlush(Record(targetId, userId))
        } catch (e: DataIntegrityViolationException) {
            // 경쟁에서 패배 — 이미 존재하므로 무시(no-op)하려는 의도
        }
    }
    return RecordResponse(count = countFor(targetId), registered = true)
}
```

그런데 예외를 분명히 삼켰는데도 `UnexpectedRollbackException`이 터지며 500이 난다. 왜?

## 1. Spring 트랜잭션 aspect는 메서드 경계만 본다

`@Transactional`은 AOP 프록시다. 메서드 진입 시 트랜잭션을 시작하고, 정상 반환이면 commit, 예외가 밖으로 전파되면 rollback한다. 여기서 물리 트랜잭션(실제 DB 커넥션)과 논리 트랜잭션(`@Transactional` 경계)을 구분해야 한다. 기본 전파 옵션 `REQUIRED`로 중첩되면 여러 논리 트랜잭션이 **하나의 물리 트랜잭션을 공유**한다.

핵심은 — aspect는 메서드의 진입/퇴장 시점에만 발동한다. 메서드 내부에서 일어나는 `throw`/`catch`는 보지 못한다.

## 2. rollback-only

트랜잭션에 <커밋 금지 도장>(rollback-only)이 찍히는 대표적 경로는 둘이다.

- **중첩 @Tx의 inner aspect** — inner 메서드가 `REQUIRED`로 외부 트랜잭션에 *참여*한 상태에서 예외를 던지면, inner는 자기가 시작한 트랜잭션이 아니라 롤백 권한이 없다. 대신 **"전체를 rollback-only"로 마킹하고 예외를 다시 던진다.** outer가 그 예외를 `catch`해도 도장은 남아, 메서드가 정상 반환할 때 commit이 거부되며 `UnexpectedRollbackException`이 난다.
- **JPA provider의 flush 예외** — `flush` 중 제약 위반 등 대부분의 `PersistenceException`은 **JPA 규약상** 활성 트랜잭션을 rollback-only로 표시한다.

둘 중 하나라도 거치면 `catch`는 소용없다. 살린 건 "예외"일 뿐, 트랜잭션의 플래그는 그대로이기 때문이다.

## 3. ★ MyBatis와 JPA

여기가 이 글의 핵심! 똑같은 `try-catch` 코드라도 데이터 접근 기술에 따라 결과가 달라진다.

|                          | MyBatis mapper 등      | Spring Data JPA repository                                       |
| ------------------------ | --------------------- | ---------------------------------------------------------------- |
| 호출 대상이 `@Transactional`? | ❌ mapper는 트랜잭션 경계가 아님 | ✅ `SimpleJpaRepository`의 `save`/`saveAndFlush`가 `@Transactional` |
| 예외가 터지는 시점               | mapper 호출 시           | `saveAndFlush`=즉시 flush(그 자리) / `save`=flush 지연(외부 커밋 시점일 수 있음)  |
| 단일 메서드 내부 catch          | **조건부** 안전            | **위험**                                                           |

- **MyBatis(mapper)**: mapper 호출은 자체 트랜잭션 경계가 없어서, 단일 메서드 내부에서 `catch`하면 `2번`의 경로를 거치지 않는다. 단 *무조건* 안전한 건 아니고, **그 DB가 statement 실패 후에도 트랜잭션을 계속 사용할 수 있을 때**(예: Oracle/H2의 중복 키)로 한정된다.
- **JPA**: `SimpleJpaRepository.saveAndFlush()`는 **그 자체가 `@Transactional`**이다. 즉 `@Transactional` 서비스에서 `repository.saveAndFlush()`를 부르는 순간 **이미 중첩 호출**이 되고, flush 예외는 규약에 따라 rollback-only를 만든다. → **단일 메서드처럼 보여도 위험하다.** (게다가 `save()`는 flush를 지연하므로 예외가 `catch` 블록 *밖*, 외부 커밋에서 터질 수도 있다.)

> 흔한 함정: "RuntimeException을 catch하면 안전/위험"을 단정하는 것. **MyBatis 경험을 Spring Data JPA에 그대로 적용하면 빗나간다.**

## 4. 해법 — `REQUIRES_NEW`로 격리

중첩이 불가피하거나 멱등 삽입을 헬퍼로 빼고 싶다면, inner를 **`REQUIRES_NEW`**로 선언한다. 외부 트랜잭션을 suspend시키고 **새 커넥션·새 트랜잭션**에서 실행하므로, 실패해도 inner 트랜잭션만 롤백되고 예외는 밖으로 전파돼 `catch`로 잡힌다. **외부 트랜잭션은 깨끗이 commit**된다.

```kotlin
@Component
class DuplicateSafeInserter {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    fun <T : Any> insert(repo: JpaRepository<T, *>, entity: T) = repo.saveAndFlush(entity)
}
```

```kotlin
@Service
class RecordService(
    private val records: RecordRepository,
    private val inserter: DuplicateSafeInserter,   // 별도 빈으로 주입
) {
    @Transactional
    fun register(userId: Long, targetId: Long): RecordResponse {
        if (!records.existsByTargetIdAndUserId(targetId, userId)) {
            try {
                inserter.insert(records, Record(targetId, userId))
            } catch (e: DataIntegrityViolationException) {
                // DataIntegrityViolationException은 FK·NOT NULL 등 모든 무결성 위반의 상위 타입이다.
                // 예상한 유니크 제약 위반만 no-op, 나머지는 다시 던진다.
                if (!isExpectedUniqueViolation(e, "uk_record_user_target")) throw e
            }
        }
        return RecordResponse(count = countFor(targetId), registered = true)
    }
}
```

> ⚠️ `DataIntegrityViolationException`을 통째로 삼키면 FK·NOT NULL·CHECK 위반까지 "성공"으로 처리돼 버그가 숨는다. **예상한 유니크 위반인지 확인하고 나머지는 re-throw**해야 한다. 단 제약명으로 판별하는 방식은 DB·JPA provider에 종속적이므로 실제 cause 구조를 확인해야 한다.

**왜 별도 빈인가** — `REQUIRES_NEW`는 프록시를 통과해야 적용된다. 같은 클래스에서 `this.insert()`로 자기 자신을 호출하면 프록시를 우회해(self-invocation) 무시된다(기본 프록시 모드 기준). 그래서 **별도 `@Component`로 분리**하는 게 일반적 해법이다(그 외 `TransactionTemplate`, AspectJ 모드 등 대안도 있다).

**주의** — `REQUIRES_NEW`는 외부 트랜잭션이 커넥션을 쥔 채 새 커넥션을 요구하므로, 커넥션 풀 고갈·교착 위험이 있다.

## 5. 테스트로 확인

미리 같은 행을 커밋해 두고, 중복 INSERT를 두 전파 방식으로 시도해 비교한다.

```kotlin
/** 기본 전파(REQUIRED): 외부 tx에 "참여"한다(같은 물리 tx). */
@Service
open class RequiredInserter {
    @Transactional(propagation = Propagation.REQUIRED)
    open fun insert(repo: RecordRepository, e: Record) = repo.saveAndFlush(e)
}

/** register()를 흉내낸 외부 트랜잭션. 주어진 방식으로 중복 1건을 시도하고 예외를 삼킨다. */
@Service
open class TxTrapDemo(
    private val records: RecordRepository,
    private val required: RequiredInserter,
    private val safe: DuplicateSafeInserter,
) {
    @Transactional
    open fun tryRegister(useRequiresNew: Boolean, dup: Record) {
        try {
            if (useRequiresNew) safe.insert(records, dup) else required.insert(records, dup)
        } catch (e: DataIntegrityViolationException) { /* 멱등: 무시 */ }
    }
}
```

```kotlin
@Test fun `REQUIRED - 외부 tx 오염으로 UnexpectedRollbackException`() {
    seedExisting(targetId = 1L, userId = 1L)
    assertThrows<UnexpectedRollbackException> { demo.tryRegister(useRequiresNew = false, dup = Record(1L, 1L)) }
}

@Test fun `REQUIRES_NEW - 실패 격리로 정상 커밋 + 중복 미삽입`() {
    seedExisting(targetId = 2L, userId = 2L)
    assertDoesNotThrow { demo.tryRegister(useRequiresNew = true, dup = Record(2L, 2L)) }
    assertEquals(1, records.countByTargetId(2L))
}
```

- **REQUIRED**: 외부 tx에 참여 → 충돌이 전체를 rollback-only로 → `UnexpectedRollbackException`
- **REQUIRES_NEW**: 새 tx에서 격리 → 예외만 catch로 삼켜지고 외부는 정상 커밋, DB도 1건

## 6. 더 알아둘 것

**PROPAGATION 옵션** (inner에서 throw 날 때)

| 옵션 | 동작 |
|---|---|
| `REQUIRED` (기본) | 외부 tx에 참여 → inner가 외부 tx를 rollback-only 마킹 |
| `REQUIRES_NEW` | 독립 tx → inner만 롤백, 외부 영향 없음 |
| `NESTED` | JDBC savepoint 기반. `JpaTransactionManager`에서도 제한적으로 켤 수 있지만 **savepoint가 `EntityManager` 1차 캐시까지 복원하진 않아** JPA 엔티티 쓰기 격리엔 부적합 → JPA는 `REQUIRES_NEW` |

**`noRollbackFor`의 한계** — 메서드 경계까지 전파된 예외의 롤백 규칙만 override한다. **JPA provider가 flush 예외로 이미 찍은 rollback-only는 풀지 못한다.**

**DB별 차이(JDBC 관점)** — Oracle/H2는 statement-level이라 충돌 statement만 실패하고 트랜잭션이 살아 있다(중복 키 한정). PostgreSQL은 statement 실패 시 **현재 트랜잭션이 실패 상태**가 되어, 전체 롤백 또는 savepoint 롤백 전까지 후속 statement를 실행할 수 없다. 단 **JPA는 DB의 statement 복구 여부와 무관하게 provider가 rollback-only로 만들 수 있다.**

## 7. Exposed(+커스텀 AOP 조합)

> 단, 이 절의 결론은 **Oracle의 statement-level rollback + rollback-only 플래그를 두지 않는 커스텀 AOP** 조합에 한정된다. PostgreSQL이라면 Exposed라도 statement 실패 후 트랜잭션이 실패 상태가 되어 이야기가 달라진다(6절 참고).

같은 멱등 삽입을 JPA가 아니라 **Exposed**(JetBrains의 Kotlin SQL 프레임워크)로 짜면, 위 조합에서는 rollback-only 함정이 사라진다. 왜인지 보면 거꾸로 JPA 함정의 정체가 드러난다.

**쓰기 지연은 똑같다.** Exposed DAO의 `Entity.new {}`도 INSERT를 즉시 실행하지 않고 flush 시점까지 미룬다. 그래서 제약 위반을 `try` 안에서 잡으려면 **즉시 flush**해야 한다(JPA `saveAndFlush`와 같은 이유).

```kotlin
fun save(...): RecordEntity = RecordEntity.new { /* ... */ }
    .also { it.flush() }   // INSERT 즉시 실행 → UK 위반을 호출자가 catch 가능
```

**결정적 차이는 트랜잭션 관리자다.** Exposed의 `transaction {}`은 블록이 정상 반환하면 commit, 예외가 전파되면 rollback한다 — 그게 전부다.

```kotlin
@Around("@annotation(ExposedTransaction)")
fun withTransaction(pjp: ProceedingJoinPoint): Any? =
    transaction(database) {          // database: Exposed Database
        pjp.proceed()                // 정상 반환 → commit / 예외 전파 → rollback
    }
```

여기엔 **`rollback-only` 같은 상태 기계가 없다.** 현재 `Transaction`을 ThreadLocal에 바인딩하고 그 트랜잭션이 JDBC 커넥션을 관리하는 단순한 구조라, INSERT가 실패해도(Oracle 기준 statement-level rollback) 트랜잭션 자체는 멀쩡하다. 서비스가 제약 위반을 잡아 409를 던지면 `transaction {}`이 rollback할 뿐 — **"오염된 트랜잭션이 commit을 거부"하는 단계가 어디에도 없다.**

```kotlin
return try {
    repo.save(/* ... */)                       // flush 덕에 여기서 제약 위반이 터진다
} catch (e: ExposedSQLException) {
    if (isExpectedUniqueViolation(e, "uk_record_user_target")) throw AlreadyExistsException(e)  // 409
    throw e                                     // FK·NOT NULL 등 다른 위반은 그대로 전파(500)
}
```

> 즉 **JPA의 rollback-only 함정은 JPA 규약과 Spring 트랜잭션 경계가 rollback-only를 관리한 결과**다(대부분의 `PersistenceException`이 트랜잭션을 rollback-only로 표시하도록 규약에 명시돼 있다). 영속성 컨텍스트의 일관성을 지키는 그 장치가, rollback-only를 두지 않는 단순한 커스텀 트랜잭션 모델엔 애초에 없다. **`flush`로 예외 시점만 앞당기면 단일 `catch`가 그대로 동작한다.**

(참고: `it.flush()`는 Exposed `Entity` 객체의 메서드일 뿐 Spring 빈 호출이 아니므로 self-invocation 프록시 우회와 무관하다. 현재 트랜잭션은 ThreadLocal로 찾는다. 또 Exposed 버전에 따라 `flush()`가 같은 테이블의 다른 pending INSERT까지 함께 내보낼 수 있으니 주의한다.)

## 마치며

이 글의 큰 교훈은 트랜잭션 그 자체보다 — **"흔히 듣는 단순화된 룰"을 그대로 믿으면 위험하다**는 것이다. "RuntimeException → rollback" 같은 룰은 *언제·어디서·어떤 경계에서, 그리고 어떤 데이터 접근 기술·트랜잭션 관리자로* 발동하는지까지 알아야 정확하다.

> 한 줄 요약: `@Transactional` 안에서 RuntimeException을 catch했을 때 rollback-only는 — **그 throw가 inner @Tx 경계(또는 JPA flush)를 거쳤느냐**가 갈림길이다. 트랜잭션 경계가 없는 MyBatis mapper면 단일 catch가 조건부 안전하지만, Spring Data JPA(repository가 @Tx + flush 예외)면 단일처럼 보여도 위험하다 → `REQUIRES_NEW`로 격리. 반대로 rollback-only 상태기계가 없는 단순한 커스텀 모델(Oracle + Exposed AOP)이라면 `flush`만으로 단일 catch가 동작한다.
