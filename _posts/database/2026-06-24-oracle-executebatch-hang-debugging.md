---
title: "Oracle 배치 INSERT가 멈췄을 때 - Exposed 자동 PK와 executeBatch 우회"
date: 2026-06-24 09:00:00 +0900
categories: [Database]
tags: [debugging, oracle, jdbc, exposed, batch, troubleshooting]
---

> Hive 기반 데이터 레이크에서 Oracle 캐시 테이블로 대량 적재하려 만든 배치가 **예외도, 타임아웃도 없이 멈췄다**. 네트워크·커넥션 풀·DB 락을 먼저 의심했지만, 같은 환경에서 정상 동작하던 선례 코드와 1:1로 대조하면서 원인을 찾아나갈 수 있었다.
>
> 여기서 배치는, 정확히는 quertz 스케줄러에 의해 주기적으로 실행되는 작업을 의미하며, Hive 원본에서 데이터를 읽어와 Oracle 데이터베이스에 대량으로 적재하는 역할을 한다.
>
> 예제의 도메인·테이블·컬럼·운영 식별자는 모두 일반화했다. 핵심은 특정 도메인이 아니라 **Oracle JDBC batch 경로, Exposed의 자동 PK 처리, 그리고 hang을 좁히는 디버깅 절차**다.

## 미리 보는 결론

겹쳐 있던 증상은 다음 두 가지였다.

1. **ORA-02289 (시퀀스가 존재하지 않습니다)** - Exposed가 INSERT SQL에 존재하지 않는 시퀀스의 `NEXTVAL`을 넣었다.
2. **executeBatch 구간 hang** - 특정 Oracle IDENTITY 테이블에 JDBC batch INSERT로 적재할 때만 멈췄고, `setQueryTimeout`도 풀어주지 못했다. 행별 `executeUpdate`로 바꾸자 정상 완료됐다.

해결 방향은 둘 다 정상 동작하던 기존 배치 패턴으로 수렴했다.

- ORM 트랜잭션에만 의존하지 않는 자체 커넥션
- 커넥션 borrow 직후 생존 확인
- 행별 `executeUpdate`
- 명시적 커밋

다만 이 글의 결론은 Oracle IDENTITY와 executeBatch가 항상 충돌한 다는 것이 아니다. 이 환경에서는 `executeBatch` 호출 경로가 유일하게 통제된 차이였고, 행별 실행으로 우회했을 때 증상이 사라졌다는 관측이 주요했다.

## 1. 증상 - 에러 없이 멈춘다

적재 배치를 수동 트리거하면 장시간 응답이 돌아오지 않았다. 로그는 적재 시작 지점에서 멈추고, 대상 테이블에는 행이 들어가지 않았다. `setQueryTimeout`을 명시해도 스레드는 풀리지 않았다.

단계 로그를 쪼개 보니 멈추는 위치가 보였다.

```text
SELECT 1 통과
DELETE 통과
COMMIT 통과
INSERT executeBatch 구간에서 정지
```

처음에는 커넥션이나 소켓의 타임아웃을 의심했으나 커넥션을 빌린 시점부터 죽어 있던 것은 아니었다. 

로그를 단계적으로 찍어보니 앞의 `SELECT 1`, `DELETE`, `COMMIT`은 통과했기 때문이다. 문제는 그 다음 batch INSERT 라운드트립에서만 발생했다.

## 2. 먼저 반증한 가설들

처음에는 환경 문제처럼 보였다. 하지만 같은 환경에서 정상 동작하던 다른 서비스의 대량 적재 job이 있었고, 그 선례와 대조하면서 다음 가설들을 하나씩 제외했다.

| 가설 | 반증 근거 |
|---|---|
| 네트워크나 소켓이 대량 패킷을 차단한다 | 같은 서버·같은 DataSource를 쓰는 다른 대량 적재 배치가 정상 완료됨 |
| 테이블 락이나 좀비 트랜잭션이 있다 | 신규 단독 테이블이고, `DELETE`는 통과했으므로 테이블 락 대기 가능성이 낮음 |
| 풀에서 처음부터 죽은 idle 소켓을 빌렸다 | `SELECT 1`, `DELETE`, `COMMIT`이 통과했으므로 borrow 직후 커넥션은 사용 가능했음 |
| ORM batchInsert의 generated keys 요청이 문제다 | 라이브러리 소스 확인 결과 해당 경로는 `NO_GENERATED_KEYS`로 실행됨 |
| IDENTITY 컬럼 자동 채번 자체가 문제다 | 같은 IDENTITY 테이블에 행별 `executeUpdate`로 넣으면 정상 완료됨 |

이 단계의 핵심은 **환경을 넓게 의심하기 전에, 같은 환경에서 되는 코드와 안 되는 코드의 차이를 먼저 본다**는 점이었다.

## 3. 조회 쪽 문제를 먼저 걷어냈다

이 배치는 처음부터 적재 단계까지 도달한 것이 아니었다. 초기에는 데이터 레이크 조회 단계에서 실패했고, 조회 쿼리 자체를 여러 번 의심했다.

- 파티션 조건 바인딩 방식 문제인가?
- 드라이버가 바인드 변수를 기대대로 처리하지 못하나?
- CTE(`WITH` 절)가 실행 계획이나 드라이버와 맞지 않나?

각 가설에 맞춰 쿼리를 수정했지만 증상은 해소되지 않았다. 결국 복잡한 집계 쿼리를 계속 고치는 대신, JOIN·윈도우·집계를 모두 제거한 단일 테이블 `SELECT ... LIMIT 100` baseline으로 줄였다. 이 단순 쿼리가 더 명확한 오류를 드러냈다.

검증 콘솔이 없는 상황에서는 배포가 곧 진단이 된다. 그래서 한 번의 배포로 최대한 많은 가설을 줄일 수 있게, 큰 수정 대신 **작은 baseline 쿼리와 단계 로그**를 먼저 넣는 편이 효과적이었다.

## 4. 쿼리가 아니라 데이터 엔드포인트였다(허무)

baseline SELECT가 반환한 오류의 성격이 바뀐 순간이 결정적이었다. 데이터 엔드포인트를 바꾸자 오류가 다음처럼 달라졌다.

```text
이전: 실행 단계에서 실패
이후: Wrong FS: hdfs://<actual-cluster> ... expected: hdfs://<expected-cluster>
```

오류가 실행 단계에서 컴파일·시맨틱 단계로 앞당겨졌다는 것은, 쿼리 문법이나 CTE 문제가 아니라 **배치가 데이터 위치와 맞지 않는 엔드포인트로 붙고 있다**는 뜻이었다.

엔드포인트를 바로잡고 원래 쿼리로 되돌리자 조회는 통과했다. 여기까지의 시행착오는 적재 hang의 원인이 아닌 단순한 삽질이었다. 다만 이후 디버깅에서 중요한 교훈을 남겼다.

> 오류 메시지의 내용만 보지 말고, 오류가 발생한 단계가 어떻게 바뀌었는지를 본다. 단계가 바뀌면 원인 후보도 바뀐다.

## 5. 데이터 정제 후 실제 hang이 드러났다

조회가 통과하자 변환 단계에서 빈 문자열을 숫자로 바꾸려다 `NumberFormatException`이 발생했다. 입력 데이터에 빈 코드 값이 섞여 있었고, 정규식 필터로 제외하자 변환도 통과했다.

그 다음부터 적재 단계가 예외 없이 멈췄다. 이 시점부터가 실제 JDBC hang이었다.

타임아웃으로 예외를 만들려는 시도는 실패했다.

- `queryTimeout`을 짧게 설정해도 스레드가 풀리지 않음
- 커넥션 레벨 타임아웃을 시도해도 기대한 진단 로그가 남지 않음

그래서 전략을 바꿨다. 예외를 강제로 만들기보다, **어디까지 실행됐는지 관측**하는 방식으로 접근했다.

먼저 큰 단계별로 로그를 넣었다. 커넥션 획득 -> DELETE -> batch INSERT 순으로 수행되던 로직의 각 단계 직전과 직후에 로그를 심었다.

```text
STEP 1: 커넥션 획득 전
STEP 2: 커넥션 획득 후
STEP 3: DELETE 전
STEP 4: DELETE 후
STEP 5: batch INSERT 전
STEP 6: batch INSERT 후
```

batch INSERT를 감싸던 `catch`가 실행되지 않는다는 사실도 단서였다. 실패라면 예외가 던져져야 한다. 그런데 예외도 로그도 없다는 것은, 실행 스레드가 응답을 기다리는 상태에 머물러 있다는 뜻에 가깝다.

이후 단계 로그를 더 쪼갔다.

- 커넥션 획득 전후를 나누니 획득 후 로그는 찍힘 → 커넥션 획득 hang 가능성 낮음
- `DELETE`와 batch INSERT를 나누니 `DELETE`는 통과 → 테이블 락 가능성 낮음
- batch INSERT 청크 로그를 넣으니 첫 청크 완료 로그도 찍히지 않음 → 첫 batch 라운드트립에서 정지

결론은 **락 대기보다 응답 없는 I/O 대기**에 가까웠다.

## 6. ORA-02289와 executeBatch hang

마지막에는 시퀀스·커넥션·트랜잭션·batch 호출 방식을 하나씩 분리했다.

먼저 서비스 코드에서 Exposed ORM을 사용중이던, 테이블 정의에서 존재하지 않는 시퀀스의 `NEXTVAL`이 INSERT SQL에 들어가는 문제가 확인됐다. 이때 표면화된 오류가 `ORA-02289`였다. 이 문제를 고쳐도 적재 hang은 같은 위치에서 재현됐다. 즉 `ORA-02289`는 별도 문제였고, hang의 직접 원인은 아니었다.

남은 차이는 batch 호출 방식이었다.

```kotlin
// hang이 재현된 방식: 여러 행을 모아 batch로 전송
for (row in rows) {
    ps.setValues(row)
    ps.addBatch()
}
ps.executeBatch()

// 정상 완료된 방식: 행마다 즉시 실행
for (row in rows) {
    ps.setValues(row)
    ps.executeUpdate()
}
```

`addBatch/executeBatch`를 행별 `executeUpdate`로 바꾸자 적재가 완료됐고, 대상 테이블의 행 수도 기대와 맞았다.

정리하면, **이 환경에서는 executeBatch를 행별 executeUpdate로 바꾸자 hang이 사라졌다.** 다만 정확한 내부 메커니즘은 단정하지 않는다. 드라이버 버전, batch RPC 크기, 네트워크 장비, 서버 상태가 복합적으로 영향을 줬을 수 있다. 글에서 확정할 수 있는 것은 다음 정도다.

- 커넥션 borrow 자체는 성공했다.
- `DELETE`와 `COMMIT`은 통과했다.
- IDENTITY 채번 자체는 행별 INSERT에서 정상 동작했다.
- `executeBatch` 경로에서만 응답 대기가 재현됐다.

## 7. 원리 정리

### 7.1 ORA-02289 - ORM 자동 PK가 DB와 어긋날 때

Exposed의 `LongIdTable` 계열 자동 증가 id는 Oracle에서 시퀀스 기반 전략을 사용할 수 있다. 해당 버전에서는 명시 시퀀스가 없을 때 fallback 시퀀스명의 `NEXTVAL`을 INSERT SQL에 넣는 경로가 있었다.

그런데 실제 DDL은 다음과 같은 IDENTITY 방식이었다.

```sql
ID NUMBER GENERATED ALWAYS AS IDENTITY
```

Oracle IDENTITY는 내부적으로 시퀀스 객체를 사용하지만, ORM이 임의 이름으로 참조할 수 있는 일반 시퀀스가 아니다. ORM이 `CACHE_TABLE_ID_SEQ.NEXTVAL` 같은 이름을 INSERT에 넣으면 DB에는 그 이름의 시퀀스가 없어 `ORA-02289`가 난다.

해결은 ORM이 id 컬럼을 INSERT 컬럼 목록에서 제외하게 만드는 것이다.

```kotlin
object CacheTable : IdTable<Long>("CACHE_TABLE") {
    override val id = long("ID").databaseGenerated().entityId()
    override val primaryKey = PrimaryKey(id)

    val userId = varchar("USER_ID", 64)
    val targetDate = varchar("TARGET_DATE", 8)
}
```

이렇게 하면 id 값은 DB의 IDENTITY가 채운다. DDL을 바꾸지 않고 ORM 매핑만 DB의 PK 생성 방식에 맞춘다.

교훈은 단순하다. **ORM의 자동 PK 전략은 DB의 실제 PK 생성 방식과 정확히 맞아야 한다.** 문제가 생기면 ORM 설정만 보지 말고 실제 생성된 INSERT SQL을 확인해야 한다.

### 7.2 executeBatch hang과 queryTimeout의 한계

`setQueryTimeout`은 만능 타임아웃이 아니다. Oracle JDBC 문서에 따르면 `Statement.setQueryTimeout`은 내부적으로 `Statement.cancel`에 의존한다. 그런데 `cancel`은 네트워크와 DB가 정상적으로 응답한다는 전제가 있어야 동작한다. 네트워크가 끊겼거나 DB 서버가 hung 상태인데 JDBC가 `IOException`도 받지 못하는 경우에는, timeout이 실행 스레드를 풀어주지 못할 수 있다.

이런 종류의 무한 read를 줄이려면 statement timeout만으로는 부족하다. 운영 중인 드라이버와 풀 설정에서 지원하는 socket read timeout을 명시적으로 검토해야 한다.

- `oracle.jdbc.ReadTimeout` 연결 프로퍼티
- 환경에 따라 `oracle.net.READ_TIMEOUT`
- 커넥션 풀의 validation / maxLifetime / idleTimeout
- 필요 시 Oracle Net keepalive 또는 DCD 설정

이 글의 사례에서는 read timeout 설정만으로 원인을 해결한 것이 아니라, 정상 동작하던 선례 패턴을 모사해 **batch 전송 경로를 행별 전송 경로로 바꾸는 우회**를 택했다.

### 7.3 행별 executeUpdate의 trade-off

행별 `executeUpdate`는 batch보다 느릴 수 있다. 대신 다음 장점이 있었다.

- 첫 행부터 성공/실패 위치를 관측하기 쉽다.
- batch 드라이버 경로를 피할 수 있다.
- 청크 커밋과 조합하면 장시간 트랜잭션을 피할 수 있다.

반대로 청크 커밋은 적재 중 실패 시 캐시 테이블이 부분 상태가 될 수 있다. 이 경우에는 적재 완료 플래그, 기준일 가드, 재실행 정책 같은 운영 안전장치가 필요하다. 원자성이 더 중요하면 끝에서 한 번만 커밋하고, undo/redo 부담을 감수하는 쪽이 맞을 수 있다.

## 8. 재사용할 디버깅 방법론

1. **되는 선례를 먼저 찾아 1:1로 대조한다.** 같은 환경에서 되는 코드가 있으면 환경 전체보다 그 차이가 더 강한 단서다.
2. **추측을 코드와 소스로 검증한다.** ORM이 만드는 SQL, JDBC 호출 옵션, generated keys 사용 여부는 소스와 로그로 확인할 수 있다.
3. **변수를 하나씩 제거한다.** 이 사례에서는 `executeBatch → executeUpdate` 한 줄 차이가 원인을 좁히는 결정적 실험이었다.
4. **관측 가능한 비대칭을 본다.** 조회는 통과하지만 적재만 멈춤, `DELETE`는 통과하지만 batch INSERT만 멈춤, 예외는 없지만 로그도 진행되지 않음 같은 비대칭이 가설을 줄인다.
5. **hang은 예외와 다르게 다룬다.** try-catch와 queryTimeout만 믿지 말고, 단계 로그로 어디까지 갔는지를 먼저 확보한다.
6. **검증 환경이 없을수록 실험을 작게 만든다.** baseline SELECT, STEP 로그, batch size 축소처럼 한 번의 배포로 가설 공간을 줄이는 장치를 먼저 넣는다.

## 정리

이번 문제는 하나의 원인으로 깔끔하게 설명되지 않았다.

- 조회 실패는 데이터 엔드포인트 불일치였다.
- 변환 실패는 빈 코드 값 데이터 문제였다.
- `ORA-02289`는 Exposed 자동 PK 전략과 Oracle IDENTITY DDL의 불일치였다.
- 최종 적재 hang은 이 환경에서 `executeBatch` 경로를 탈 때만 재현됐고, 행별 `executeUpdate`로 우회했다.

가장 중요한 교훈은 **환경을 의심하기 전에 같은 환경에서 되는 선례와 1:1로 대조하는 것**이다. 그리고 hang처럼 예외가 없는 문제는, 예외 처리보다 단계 관측이 먼저다.

## 참고

- Oracle JDBC Developer's Guide - Troubleshooting: <https://docs.oracle.com/en/database/oracle/oracle-database/26/jjdbc/JDBC-troubleshooting.html>
