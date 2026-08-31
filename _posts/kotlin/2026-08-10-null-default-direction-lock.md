---
title: "서로 다른 null 기본값 때문에 결제 후 열람이 막힌 문제"
date: 2026-08-10 10:00:00 +0900
categories: [Kotlin]
tags: [kotlin, null-safety, domain-design, data-integrity, troubleshooting]
description: "같은 판정 함수의 두 엘비스 연산자가 null을 서로 반대로 처리하고 있었다. 데이터 저장·갱신 경로를 확인해 결제 직후부터 열람할 수 없고 이후에도 복구되지 않는 조건을 찾았다."
---

유료 콘텐츠 다시보기의 1년 만료 정책이 철회돼 만료 판정을 제거하는 작업을 맡았다. 관련 코드를 확인하던 중 **결제 직후부터 열람이 막히고 이후에도 복구되지 않는 조건**을 발견했다.

## 판정 함수 하나에 널 기본값이 서로 반대다

만료 여부를 판정하는 함수는 이렇게 생겼다.

```kotlin
fun isExpired(record: Entitlement, now: LocalDateTime): Boolean {
    val remainingCount = record.countLeft ?: return false            // 없으면 열어줌 (fail-open)
    if (remainingCount > 0) return false
    return record.lastUsedDate?.plusYears(1)?.isBefore(now) ?: true  // 없으면 막음 (fail-closed)
}
```

엘비스 연산자가 두 개인데 방향이 정반대다. 남은 횟수가 없으면 영구 열람으로 열어주고 마지막 사용일이 없으면 즉시 만료로 막는다.

한 함수 안에서 널 처리 방침이 갈리는 것 자체가 신호였다. 다만 이것만으로는 버그라고 단정할 수 없다. **그 널이 실제로 생기는지**를 쓰기 경로에서 확인해야 한다.

## 쓰기 경로를 보니 복구할 길이 없다

`last_used_date`를 쓰는 문장은 레포 전체에 둘뿐이었다.

```sql
-- 신규 부여
INSERT INTO entitlement (..., last_used_date) VALUES (..., NULL)
--                                                        ↑ 항상 NULL

-- 차감
UPDATE entitlement
SET count_left = count_left - 1, last_used_date = CURRENT_TIMESTAMP
WHERE ... AND count_left > 0
--            ↑ 이 가드 때문에 count_left = 0 인 행은 못 건드린다
```

두 문장을 겹쳐 보면 결론이 나온다.

- 신규 부여는 예외 없이 `last_used_date`를 NULL로 넣는다.
- 그 값을 채우는 유일한 문장에는 `count_left > 0` 가드가 걸려 있다.

그래서 `count_left = 0`이면서 `last_used_date`가 NULL인 행은 **어떤 경로로도 채워지지 않는다.** 판정 함수는 그 행을 영구히 만료로 본다.

## 그런 행은 이렇게 생긴다

카탈로그 검증은 0을 그대로 허용하고 있었다.

```kotlin
require(standardCount == null || standardCount >= 0)   // 0 허용
require(countLeft == null || countLeft >= 0)           // 0 허용
```

횟수제 상품의 기준 횟수가 0으로 등록되면 이렇게 흐른다.

```text
결제 → 재화 차감 커밋 → count_left=0, last_used_date=NULL 행 INSERT
     → 즉시 열람 시도 → ?: true → 만료 → HTTP 400
     → 영원히
```

돈은 나갔고 컨텐츠는 한 번도 못 본다.

여기에 하나가 겹쳐 있었다. 당시 만들던 재결제 다시보기 기능은 해제 조건이 `response_detail IS NOT NULL`이었다. **막는 조건과 푸는 조건이 서로 다른 술어를 보고 있어서** 만료로 막힌 행을 해제 쿼리가 잡지 못했다.

## 발견마다 반박을 붙였다

혼자 문제 같다고 넘기지 않으려고 발견마다 반박 전용 검토를 붙였다. 지시는 하나였다. 이 주장을 논파하라, 애매하면 논파된 것으로 하라. 인용한 파일과 줄 번호는 직접 열어 확인하게 했다.

반박 관점으로 다시 검토한 뒤에도 문제는 재현됐고, 그 과정에서 사실관계 두 개를 바로잡았다.

- 이 규칙은 작업 브랜치가 만든 게 아니라 이미 메인에 있던 동작이다. 같은 판정이 세 벌 복붙돼 있었고 전부 fail-closed였다.
- 정상적으로 소비하다가 이 상태가 되지는 않는다. 기준 횟수 0인 상품이 등록되거나 레거시 작성자가 넣은 행이어야 한다.

반대로 틀린 주장도 있었다. 응답에서 `isExpired` 필드를 지우면 JSON 계약 테스트가 실행 중 실패한다고 봤지만, 이 테스트는 명명 인자로 값을 넘기므로 테스트 실행 전 **컴파일 오류**가 발생한다. 결론(필드는 지우지 말 것)은 유지됐지만 근거는 수정했다.

주장을 세우는 일과 근거가 맞는 일은 별개다. 결론이 같아도 근거가 틀렸으면 다음 판단에서 같은 실수를 반복한다.

## 지우지 않고 함수 본문만 막았다

기획이 철회됐으므로 만료 판정을 없앴다. 다만 호출부까지 제거하지는 않았다.

```kotlin
@Suppress("UNUSED_PARAMETER")
fun isExpired(record: Entitlement, now: LocalDateTime = now()): Boolean = false
```

호출부 세 곳은 그대로 뒀다. 다음 버전에 재열람 결제가 다시 들어온다고 해서 **되돌리는 비용을 한 줄로 유지**하는 쪽을 택했다. 전부 지우면 복원할 때 파일 네 개를 되살려야 한다.

## 테스트는 지우는 대신 뒤집었다

만료 거부를 단언하던 테스트가 세 개 있었다. 그냥 지우면 무제한 열람이 아무 검증 없이 남는다. 같은 픽스처로 성공을 단언하도록 반전시키고 이번에 발견한 케이스를 하나 추가했다.

```text
serves count archive long after its last use                    (반전)
serves consumed archive that was never stamped with a last use  (신규, 이번 버그)
replays a snapshot long after the count was consumed            (반전)
replays a stored snapshot long after the count was consumed     (반전)
```

기존 규칙으로 되돌리면 네 테스트가 모두 실패했고, 수정 코드를 복원하면 모두 통과했다. 변경한 테스트가 새 동작을 실제로 검증하고 있음을 확인했다.

## 만료 게이트는 읽기 전용이 아니었다

`isExpired`를 끄면 재열람만 열릴 거라고 예상했는데 아니었다.

```kotlin
val mapping = loadAndValidate(...)       // 만료 게이트
findSnapshot(mapping)?.let { return it } // 있으면 반환
contentReader.get(...)                   // 없으면 외부 엔진으로 신규 생성
```

**만료 게이트가 신규 생성 게이트를 겸하고 있었다.** 오래전 소진된 매핑으로 지금 새로 생성하는 것까지 같이 열린다. 매핑당 1회로 제한되기는 한다. 생성되면 스냅샷이 저장되고 다음부터는 조기 반환에서 끝난다.

게이트를 끌 때는 그 게이트가 실제로 무엇을 막고 있었는지를 호출 순서로 확인해야 한다. 이름은 만료 판정이지만 위치가 생성 직전이면 생성 조건이기도 하다.

## 함정을 문서로 적어 뒀다

나중에 되살릴 사람이 볼 문서를 레포에 남겼다. 핵심은 셋이다.

1. **과금 트리거가 클라이언트 재량 값에 의존하면 안 된다.** 검토한 설계 세 개가 전부 이 이유로 탈락했다.
2. **`base.plusYears(1) < now`와 `base < now.minusYears(1)`은 서로 역이 아니다.** 2월 29일에 하루 어긋난다. 그날은 만료로 막히는데 해제 쿼리는 0행이 되어 영구 잠금이 된다.
3. **널 기본값을 fail-closed로 두지 말 것.** 이 글의 그 버그다.

cherry-pick으로 어떤 코드를 복원할지는 찾을 수 있지만 당시 판단 근거까지 알 수는 없다. 그래서 복원할 코드보다 주의할 조건과 제외한 설계를 문서로 남겼다.

## 정리

같은 판정 함수 안에서 널 기본값이 서로 반대 방향이면, **쓰기 경로가 그 널을 항상 만들어내는지**를 반드시 확인해야 한다.

여기서는 INSERT가 항상 NULL을 넣었고 그 값을 채우는 UPDATE에 가드가 걸려 있었다. 판정 로직만 읽으면 조건 분기 하나로 보이지만 쓰기 경로를 겹쳐 보면 되돌릴 수 없는 잠금이었다. 널 안전성은 문법이 아니라 데이터 수명주기의 문제다.
