---
title: "Gradle 중첩 include가 만든 유령 프로젝트 걷어내기"
date: 2026-08-10 12:00:00 +0900
categories: [DevOps]
tags: [gradle, kotlin, build, dependency-management, spring-boot, troubleshooting]
description: "Could not find group:artifact: 에러가 리포지토리를 선언하라고 안내했지만 리포지토리 문제가 아니었다. 콜론 뒤 빈 버전과 중첩 include가 자동 생성한 유령 프로젝트를 추적한 기록."
---

`./gradlew build`가 이 에러로 죽었다.

```text
Could not find org.jetbrains.kotlinx:kotlinx-serialization-json:

Possible solution:
 - Declare repository providing the artifact, ...
```

Gradle이 친절하게 리포지토리를 선언하라고 안내한다. 그런데 리포지토리 문제가 아니었다.

## 에러를 다시 읽는다

```text
Could not find org.jetbrains.kotlinx:kotlinx-serialization-json:
                                                              ↑ 여기 아무것도 없다
```

`group:artifact:` 뒤 **버전 자리가 빈 문자열**이다. Gradle은 버전 해석에 실패하면 리포지토리 안내를 붙인다. 여기서는 엉뚱한 힌트다. 좌표가 아직 덜 채워졌다. 리포지토리가 없는 게 아니라 **버전을 공급할 주체**가 없다.

## 중첩 include가 중간 프로젝트를 자동으로 만든다

설정 파일에는 리프 모듈만 선언돼 있었다.

```kotlin
// settings.gradle.kts
include("application:service-a")
include("application:partners-b:entry")
include("application:partners-c:fortune")
```

그런데 `./gradlew projects`로 확인하니 선언한 적 없는 프로젝트가 있었다.

```text
+--- Project ':application'                    ← include 한 적 없다. Gradle이 만들었다
|    +--- Project ':application:service-a'
|    +--- Project ':application:partners-b'    ← 이것도
```

중첩 경로를 include하면 Gradle이 중간 경로를 **컨테이너 프로젝트로 자동 생성**한다. 에러가 난 세 프로젝트가 바로 이 유령이었다.

## 유령은 빌드 파일이 없다

이 프로젝트들은 하위 모듈 디렉터리만 있고 소스도 `build.gradle.kts`도 없는 껍데기다. 빌드 파일이 없으니 플러그인을 적용할 방법 자체가 없다.

## 루트가 모든 서브프로젝트에 버전 없이 꽂는다

```kotlin
subprojects {
    dependencies {
        add("implementation", "org.jetbrains.kotlin:kotlin-reflect")              // 살아남음
        add("implementation", "org.jetbrains.kotlinx:kotlinx-serialization-json") // 죽음
    }
}
```

둘 다 버전이 없다. 그런데 하나만 죽는다.

## 글자 하나 차이로 버전 공급자가 다르다

| 의존성 | 그룹 | 버전 공급자 |
|---|---|---|
| `kotlin-reflect` | `org.jetbrains.kotlin` | Kotlin JVM 플러그인. 모든 서브프로젝트에 적용됨 |
| `kotlinx-serialization-json` | `org.jetbrains.kotlin`**`x`** | Spring Boot BOM. 리프 모듈에만 적용됨 |

**`x` 한 글자 차이로 버전을 관리하는 주체가 다르다.** Gradle 플러그인은 상속되지도 않는다. 루트에 의존성 관리 플러그인을 붙여도 자식 프로젝트로 내려가지 않는다.

추측으로 두지 않고 프로젝트별 해석 결과를 직접 재봤다.

```text
:application (유령)                :application:service-a (리프)
kotlin-reflect        → 2.3.10     kotlin-reflect        → 2.3.10
kotlinx-serialization → FAILED     kotlinx-serialization → 1.9.0
```

BOM이 적용된 리프에서는 버전이 채워진다. 플러그인이 없는 유령에서는 빈 채로 남는다.

## 여태 아무도 못 만난 이유

초기 커밋부터 있던 문제인데 아무도 못 만났다. 배포와 CI가 실행하는 gradle 명령이 레포 전체에 둘뿐이었기 때문이다.

```text
Dockerfile:16       ./gradlew :app:bootJar --no-daemon
build_push.yml:58   ./gradlew test --no-daemon
```

둘 다 유령 프로젝트의 설정을 **해석하지 않는다.** 유령은 누구의 의존성도 아니라서 태스크 그래프에 들어오지 않는다. `./gradlew build`처럼 전체 프로젝트를 도는 순간에만 터진다. 사람이 손으로 칠 때만 만난다.

자동화가 특정 경로만 밟으면 그 바깥의 구성 오류는 시간이 지나도 아무도 못 찾는다.

## 이렇게 고쳤다

```kotlin
// 중첩 include로 Gradle이 자동 생성하는 컨테이너 프로젝트는
// 자체 소스도 build.gradle.kts도 없어 의존성을 붙일 대상이 아니다.
if (buildFile.exists()) {
    dependencies { ... }
}
```

BOM이 적용된 곳에만 추가하는 방법도 있었다.

```kotlin
plugins.withId("io.spring.dependency-management") { dependencies { ... } }
```

동작은 같지만 앞쪽을 골랐다. 실제 의도가 **빌드 파일 없는 껍데기는 건너뛴다**인데 이 조건이 그 의도를 그대로 드러낸다. BOM 조건은 우연히 같은 결과를 내는 우회에 가깝다.

## 첫 에러 뒤에 두 번째 문제가 숨어 있었다

첫 에러가 사라지자 다음이 나왔다.

```text
Execution failed for task ':bootJar'.
> Main class name has not been configured and it could not be resolved from classpath
```

**루트 프로젝트가 자기 자신에게 Spring Boot 플러그인을 적용하고 있었다.** 루트는 소스가 0줄이라 만들 실행 jar가 없다. 진짜 애플리케이션은 별도 모듈이다.

```kotlin
id("org.springframework.boot") version "4.0.3" apply false
//                                              ↑ 버전 선언만 남기고 루트에는 적용하지 않음
```

`apply false`는 플러그인을 적용하지 않으면서 버전 선언은 클래스패스에 남긴다. 그래서 서브프로젝트는 자기 `plugins {}` 블록에서 버전 없이 같은 플러그인을 쓸 수 있다.

## 안전한지 숫자로 확인했다

런타임 코드는 0줄이지만 루트 빌드 파일은 모든 모듈에 영향이 간다. 그래서 괜찮아 보인다로 끝내지 않고 변경 전후를 측정했다.

| 검증 | 결과 |
|---|---|
| 실행 모듈 runtimeClasspath 1,087줄 diff | 완전 동일 |
| 리프 모듈 compileClasspath 489줄 diff | 완전 동일 |
| 실사용 9개 모듈의 kotlinx 버전 | 전부 1.9.0 유지 |
| CI 명령 그대로 실행 | 통과 |
| Dockerfile 명령 그대로 실행 | 통과 |
| 실행 jar 크기와 Start-Class | 정상 |
| 루트 bootJar를 부르는 스크립트 | 전수 grep 0건 |

바뀐 것은 하나뿐이다. **안 되던 `./gradlew build`가 된다.** 잃은 능력은 없다.

빌드 스크립트 수정은 영향 범위가 넓은데 결과가 눈에 안 보인다. 의존성 해석 결과를 텍스트로 뽑아 diff를 뜨면 바뀐 게 없다고 증명할 수 있다.

## 정리

Gradle이 `Could not find group:artifact:`로 죽으면서 리포지토리를 언급하면 **콜론 뒤가 비었는지부터 본다.** 비어 있으면 문제는 리포지토리가 아니다. 그 프로젝트에 버전 공급자가 없다.

그리고 세 가지가 겹쳐 있었다.

- 중첩 include는 선언하지 않은 중간 프로젝트를 만든다.
- 플러그인은 상속되지 않으므로 BOM은 적용된 프로젝트에서만 버전을 채운다.
- `subprojects {}`는 그 유령까지 포함한다.

에러 메시지의 안내는 힌트일 뿐 진단이 아니다. 좌표가 어떻게 생겼는지를 먼저 읽는 편이 빠르다.
